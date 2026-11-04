from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import date
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from open_swing_analysis.contracts import (
    CameraView,
    FrameRateMode,
    Handedness,
    Swing,
    SwingSession,
)
from open_swing_analysis.ingestion import (
    EmptyVideoError,
    FrameSelection,
    TimestampSource,
    UnsupportedVideoError,
    VideoDecodeError,
    VideoIngestionError,
    VideoReader,
    ingest_video,
    normalize_timestamps,
    read_capture_diagnostics,
    read_capture_summary,
    sha256_file,
    store_ingestion_result,
)
from open_swing_analysis.storage import LocalDataStore


def _make_video(
    path: Path,
    timestamps_ms: list[int],
    *,
    width: int = 96,
    height: int = 64,
) -> Path:
    """Generate a tiny deterministic MP4 with caller-controlled PTS."""
    with av.open(path, mode="w") as container:
        stream = container.add_stream("libx264", rate=25)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        for index, timestamp_ms in enumerate(timestamps_ms):
            image = np.zeros((height, width, 3), dtype=np.uint8)
            image[..., 0] = 25 + index * 30
            image[:, index * 8 : index * 8 + 12, 1] = 220
            image[10:20, :, 2] = 40 + index * 20
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            frame.pts = timestamp_ms
            frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


@pytest.fixture
def cfr_video(tmp_path: Path) -> Path:
    return _make_video(tmp_path / "constant.mp4", [0, 40, 80, 120, 160, 200])


@pytest.fixture
def vfr_video(tmp_path: Path) -> Path:
    return _make_video(tmp_path / "variable.mov", [0, 40, 100, 140, 230, 270])


def test_constant_frame_rate_ingestion(cfr_video: Path) -> None:
    result = ingest_video(cfr_video, swing_id="swing-cfr")

    assert result.asset.frame_rate_mode is FrameRateMode.CONSTANT
    assert result.asset.frame_count == 6
    assert result.asset.width_px == 96
    assert result.asset.height_px == 64
    assert result.asset.codec == "h264"
    assert result.summary.median_inter_frame_s == pytest.approx(0.04)
    assert result.summary.observed_fps == pytest.approx(25.0)
    assert [frame.timestamp_s for frame in result.frames] == pytest.approx(
        [0.0, 0.04, 0.08, 0.12, 0.16, 0.20]
    )
    assert all(
        row.timestamp_source is TimestampSource.ORIGINAL for row in result.diagnostics
    )


def test_variable_frame_rate_preserves_original_pts(vfr_video: Path) -> None:
    result = ingest_video(vfr_video, swing_id="swing-vfr")
    original = [row.original_timestamp_s for row in result.diagnostics]
    canonical = [frame.timestamp_s for frame in result.frames]

    assert result.asset.frame_rate_mode is FrameRateMode.VARIABLE
    assert len({round(b - a, 3) for a, b in zip(original, original[1:])}) > 1
    assert canonical == pytest.approx(original)
    assert result.summary.irregular_interval_count > 0
    assert result.asset.acquisition_metadata["observed_fps"] == pytest.approx(
        result.summary.observed_fps
    )


def test_reader_selection_is_lazy_and_preserves_source_indexes(cfr_video: Path) -> None:
    reader = VideoReader(cfr_video)
    iterator = reader.iter_frames(FrameSelection(start=1, stop=6, step=2))
    assert iter(iterator) is iterator
    frames = list(iterator)
    assert [frame.frame_index for frame in frames] == [1, 3, 5]
    assert all(frame.image.shape == (64, 96, 3) for frame in frames)

    selected = ingest_video(
        cfr_video,
        swing_id="swing-selected",
        selection=FrameSelection(indices=frozenset({0, 4})),
    )
    assert selected.asset.frame_count == 6
    assert [frame.frame_index for frame in selected.frames] == [0, 4]
    assert selected.summary.selected_frames == 2


def test_missing_duplicate_non_monotonic_and_negative_timestamps_are_explicit() -> None:
    normalized = normalize_timestamps(
        [0.0, 0.04, 0.04, None, 0.02, 0.20, -0.1], nominal_fps=25.0
    )
    timestamps = [item[0] for item in normalized]
    sources = [item[1] for item in normalized]

    assert sources == [
        TimestampSource.ORIGINAL,
        TimestampSource.ORIGINAL,
        TimestampSource.ESTIMATED_DUPLICATE,
        TimestampSource.ESTIMATED_MISSING,
        TimestampSource.ESTIMATED_NON_MONOTONIC,
        TimestampSource.ORIGINAL,
        TimestampSource.ESTIMATED_NEGATIVE,
    ]
    assert all(later > earlier for earlier, later in zip(timestamps, timestamps[1:]))


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="rotation fixture needs ffmpeg CLI"
)
def test_display_rotation_is_applied_without_losing_encoded_dimensions(
    cfr_video: Path, tmp_path: Path
) -> None:
    rotated = tmp_path / "rotated.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-display_rotation:v:0",
            "90",
            "-i",
            str(cfr_video),
            "-c",
            "copy",
            str(rotated),
            "-y",
        ],
        check=True,
    )

    result = ingest_video(rotated, swing_id="swing-rotated")
    decoded = next(VideoReader(rotated).iter_frames(FrameSelection(stop=1)))
    assert result.asset.width_px == 96
    assert result.asset.height_px == 64
    assert result.summary.rotation_degrees == 90
    assert (result.summary.display_width_px, result.summary.display_height_px) == (
        64,
        96,
    )
    assert decoded.image.shape == (96, 64, 3)


def test_empty_and_unsupported_files_have_useful_errors(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(EmptyVideoError, match="empty"):
        ingest_video(empty, swing_id="swing-empty")

    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("not a video", encoding="utf-8")
    with pytest.raises(UnsupportedVideoError, match="could not open"):
        ingest_video(unsupported, swing_id="swing-unsupported")


def test_corrupted_or_truncated_input_never_succeeds_silently(
    cfr_video: Path, tmp_path: Path
) -> None:
    truncated = tmp_path / "truncated.mp4"
    content = cfr_video.read_bytes()
    truncated.write_bytes(content[: len(content) // 2])

    try:
        result = ingest_video(truncated, swing_id="swing-truncated")
    except VideoIngestionError as exc:
        assert isinstance(
            exc, (UnsupportedVideoError, VideoDecodeError, EmptyVideoError)
        )
    else:
        assert result.summary.decode_error_count > 0
        assert result.asset.frame_count < 6


def test_asset_hash_matches_independent_sha256(cfr_video: Path) -> None:
    expected = hashlib.sha256(cfr_video.read_bytes()).hexdigest()
    result = ingest_video(cfr_video, swing_id="swing-hash")
    assert sha256_file(cfr_video) == expected
    assert result.asset.sha256 == expected
    assert result.asset.asset_id == f"asset-{expected[:16]}"
    assert result.asset.source_metadata["file_size_bytes"] == cfr_video.stat().st_size


def test_storage_round_trip_uses_existing_contracts(
    cfr_video: Path, tmp_path: Path
) -> None:
    result = ingest_video(cfr_video, swing_id="swing-storage")
    session = SwingSession(
        session_id="session-ingestion",
        subject_id="subject-synthetic",
        recording_date=date(2026, 1, 2),
        camera_view=CameraView.UNKNOWN,
        golfer_handedness=Handedness.UNKNOWN,
        capture_metadata={"fixture": True},
    )
    swing = Swing(
        swing_id="swing-storage",
        session_id=session.session_id,
        video_asset_id=result.asset.asset_id,
        club_type="unknown",
    )
    store = LocalDataStore(tmp_path / "store")
    store.write_session(session)
    store.write_video_asset(session.session_id, result.asset)
    store.write_swing(swing)

    paths = store_ingestion_result(store, session.session_id, swing.swing_id, result)

    assert paths.asset_json.exists()
    assert paths.frames_parquet.exists()
    assert paths.diagnostics_parquet.exists()
    assert paths.summary_json.exists()
    assert paths.plots_png is not None and paths.plots_png.exists()
    assert (
        store.read_video_asset(session.session_id, result.asset.asset_id)
        == result.asset
    )
    assert store.read_frames(session.session_id, swing.swing_id) == list(result.frames)
    assert read_capture_diagnostics(store, session.session_id, swing.swing_id) == list(
        result.diagnostics
    )
    assert (
        read_capture_summary(store, session.session_id, swing.swing_id)
        == result.summary
    )


def test_repeated_ingestion_is_deterministic(cfr_video: Path) -> None:
    first = ingest_video(cfr_video, swing_id="swing-repeat")
    second = ingest_video(cfr_video, swing_id="swing-repeat")

    assert first.asset == second.asset
    assert first.frames == second.frames
    assert first.diagnostics == second.diagnostics
    assert first.summary == second.summary
    assert first.performance.elapsed_decode_s >= 0
    assert second.performance.elapsed_decode_s >= 0
