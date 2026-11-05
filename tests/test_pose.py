from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date, datetime, timezone
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from open_swing_analysis.contracts import (
    CameraView,
    Handedness,
    ObservationLayer,
    ObservationStatus,
    Swing,
    SwingSession,
)
from open_swing_analysis.ingestion import ingest_video, store_ingestion_result
from open_swing_analysis.pose import (
    BackendLandmark,
    BackendPoseResult,
    LANDMARK_NAMES,
    MediaPipePoseConfig,
    PoseExtractionError,
    extract_pose,
    map_inference_timestamps,
    read_pose_diagnostics,
    read_pose_summary,
    store_pose_extraction,
    write_pose_diagnostic_plots,
)
from open_swing_analysis.pose_video import write_annotated_video
from open_swing_analysis.storage import (
    ImmutableDataError,
    LocalDataStore,
    SchemaVersionError,
)


def _make_video(path: Path, frame_count: int = 4) -> Path:
    with av.open(path, mode="w") as container:
        stream = container.add_stream("libx264", rate=25)
        stream.width = 96
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        for index in range(frame_count):
            image = np.zeros((64, 96, 3), dtype=np.uint8)
            image[..., 0] = 25 + index * 30
            image[8:56, 30:66, 1] = 150
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            frame.pts = index * 40
            frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


class FakePoseBackend:
    model_name = "fake_pose"
    model_version = "fake-1.0"
    source_revision = "fake-config-001"
    configuration = {"backend": "fake", "smoothing": False}

    def __init__(self, *, missing_call: int | None = 1):
        self.missing_call = missing_call
        self.open_count = 0
        self.close_count = 0
        self.timestamps: list[int] = []

    def open(self) -> None:
        self.open_count += 1

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> BackendPoseResult:
        call = len(self.timestamps)
        self.timestamps.append(timestamp_ms)
        if call == self.missing_call:
            return BackendPoseResult(landmarks=())
        landmarks = []
        for index in range(33):
            x = 0.10 + index / 100.0 + call / 1000.0
            y = 0.20 + index / 200.0 + call / 2000.0
            if index == 16:
                x = 1.08
                y = -0.04
            landmarks.append(
                BackendLandmark(
                    index=index,
                    x=x,
                    y=y,
                    relative_z=-index / 100.0,
                    visibility=0.2 if index == 15 else 0.9,
                    confidence=0.3 if index == 15 else 0.8,
                )
            )
        return BackendPoseResult(tuple(landmarks))

    def close(self) -> None:
        self.close_count += 1


@pytest.fixture
def pose_fixture(tmp_path: Path):
    video = _make_video(tmp_path / "pose.mp4")
    ingestion = ingest_video(video, swing_id="swing-pose")
    backend = FakePoseBackend()
    recorded_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = extract_pose(
        video,
        swing_id="swing-pose",
        frames=ingestion.frames,
        backend=backend,
        observation_revision="raw-pose-test-001",
        camera_view=CameraView.FACE_ON,
        recorded_at=recorded_at,
    )
    return video, ingestion, backend, result, recorded_at


def test_all_33_landmarks_are_indexed_and_aligned(pose_fixture) -> None:
    _, ingestion, backend, result, _ = pose_fixture
    assert backend.open_count == 1
    assert backend.close_count == 1
    assert len(result.observations) == len(ingestion.frames) * 33
    for frame in ingestion.frames:
        rows = [
            row for row in result.observations if row.frame_index == frame.frame_index
        ]
        assert [row.landmark_index for row in rows] == list(range(33))
        assert [row.landmark_name for row in rows] == list(LANDMARK_NAMES)
        assert all(row.timestamp_s == frame.timestamp_s for row in rows)
    assert backend.timestamps == [0, 40, 80, 120]


def test_missing_pose_is_explicit_null_rows_and_interval(pose_fixture) -> None:
    _, _, _, result, _ = pose_fixture
    rows = [row for row in result.observations if row.frame_index == 1]
    assert len(rows) == 33
    assert all(row.observation_status is ObservationStatus.NOT_OBSERVED for row in rows)
    assert all(
        row.x is None and row.y is None and row.visibility is None for row in rows
    )
    interval = result.summary.missing_pose_intervals[0]
    assert (
        interval.start_frame_index,
        interval.end_frame_index,
        interval.frame_count,
    ) == (1, 1, 1)
    assert result.summary.frames_with_pose == 3
    assert result.summary.pose_detection_coverage == pytest.approx(0.75)


def test_low_visibility_out_of_frame_and_raw_values_are_preserved(pose_fixture) -> None:
    _, _, _, result, _ = pose_fixture
    low = next(
        row
        for row in result.observations
        if row.frame_index == 0 and row.landmark_index == 15
    )
    outside = next(
        row
        for row in result.observations
        if row.frame_index == 0 and row.landmark_index == 16
    )
    assert low.observation_status is ObservationStatus.LOW_CONFIDENCE
    assert low.visibility == pytest.approx(0.2)
    assert low.confidence == pytest.approx(0.3)
    assert outside.x == pytest.approx(1.08)
    assert outside.y == pytest.approx(-0.04)
    assert outside.relative_z == pytest.approx(-0.16)
    assert outside.relative_z_coordinate_system == "model_relative_depth"
    assert outside.data_layer is ObservationLayer.RAW


def test_no_smoothing_and_repeated_fake_processing_is_deterministic(
    pose_fixture,
) -> None:
    video, ingestion, _, first, recorded_at = pose_fixture
    second = extract_pose(
        video,
        swing_id="swing-pose",
        frames=ingestion.frames,
        backend=FakePoseBackend(),
        observation_revision="raw-pose-test-001",
        camera_view=CameraView.FACE_ON,
        recorded_at=recorded_at,
    )
    assert first.observations == second.observations
    wrist = [
        row.x
        for row in first.observations
        if row.landmark_index == 15 and row.x is not None
    ]
    assert wrist == pytest.approx([0.25, 0.252, 0.253])


def test_backend_is_closed_when_inference_fails(tmp_path: Path) -> None:
    video = _make_video(tmp_path / "failure.mp4", frame_count=1)
    ingestion = ingest_video(video, swing_id="swing-failure")

    class FailingBackend(FakePoseBackend):
        def process(
            self, image_rgb: np.ndarray, timestamp_ms: int
        ) -> BackendPoseResult:
            raise PoseExtractionError("synthetic inference failure")

    backend = FailingBackend()
    with pytest.raises(PoseExtractionError, match="synthetic inference failure"):
        extract_pose(
            video,
            swing_id="swing-failure",
            frames=ingestion.frames,
            backend=backend,
            observation_revision="failure-001",
            camera_view=CameraView.UNKNOWN,
        )
    assert backend.open_count == 1
    assert backend.close_count == 1


def test_submillisecond_timestamp_mapping_is_explicit() -> None:
    assert map_inference_timestamps([0.0, 0.0004, 0.0016, 0.0021]) == (
        (0, False),
        (1, True),
        (2, False),
        (3, True),
    )


def _stored_pose_result(tmp_path: Path, pose_fixture):
    _, ingestion, _, result, _ = pose_fixture
    session = SwingSession(
        session_id="session-pose",
        subject_id="subject-synthetic",
        recording_date=date(2026, 1, 1),
        camera_view=CameraView.FACE_ON,
        golfer_handedness=Handedness.RIGHT,
    )
    swing = Swing(
        swing_id="swing-pose",
        session_id=session.session_id,
        video_asset_id=ingestion.asset.asset_id,
        club_type="7-iron",
    )
    store = LocalDataStore(tmp_path / "store")
    store.write_session(session)
    store.write_video_asset(session.session_id, ingestion.asset)
    store.write_swing(swing)
    store_ingestion_result(
        store, session.session_id, swing.swing_id, ingestion, generate_plots=False
    )
    paths = store_pose_extraction(
        store, session.session_id, swing.swing_id, result, generate_plots=False
    )
    return store, session, swing, result, paths


def test_pose_storage_round_trip_and_raw_revision_immutability(
    tmp_path: Path, pose_fixture
) -> None:
    store, session, swing, result, paths = _stored_pose_result(tmp_path, pose_fixture)
    assert store.read_pose_observations(
        session.session_id, swing.swing_id, ObservationLayer.RAW, "raw-pose-test-001"
    ) == list(result.observations)
    assert read_pose_diagnostics(
        store, session.session_id, swing.swing_id, "raw-pose-test-001"
    ) == list(result.diagnostics)
    assert (
        read_pose_summary(
            store, session.session_id, swing.swing_id, "raw-pose-test-001"
        )
        == result.summary
    )
    assert paths.observations_parquet.exists() and paths.diagnostics_parquet.exists()
    with pytest.raises(ImmutableDataError, match="overwrite"):
        store_pose_extraction(
            store, session.session_id, swing.swing_id, result, generate_plots=False
        )


def test_pose_summary_incompatible_version_is_rejected(
    tmp_path: Path, pose_fixture
) -> None:
    store, session, swing, _, paths = _stored_pose_result(tmp_path, pose_fixture)
    payload = json.loads(paths.summary_json.read_text(encoding="utf-8"))
    payload["schema_version"] = "99.0.0"
    paths.summary_json.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaVersionError, match="99.0.0"):
        read_pose_summary(
            store, session.session_id, swing.swing_id, "raw-pose-test-001"
        )


def test_diagnostic_plots_and_side_by_side_video_are_validated(
    tmp_path: Path, pose_fixture
) -> None:
    video, ingestion, _, result, _ = pose_fixture
    plot = write_pose_diagnostic_plots(
        result.observations, result.diagnostics, tmp_path / "pose.png"
    )
    rendered = write_annotated_video(
        video,
        ingestion.frames,
        result.observations,
        tmp_path / "annotated.mp4",
        side_by_side=True,
        show_landmark_names=True,
    )
    assert plot.stat().st_size > 0
    assert rendered.frame_count == 4
    assert (rendered.width_px, rendered.height_px) == (192, 64)
    assert rendered.path.stat().st_size > 0


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="rotation fixture needs ffmpeg CLI"
)
def test_pose_and_annotation_use_display_rotation(tmp_path: Path) -> None:
    source = _make_video(tmp_path / "source.mp4")
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
            str(source),
            "-c",
            "copy",
            str(rotated),
            "-y",
        ],
        check=True,
    )
    ingestion = ingest_video(rotated, swing_id="swing-rotated-pose")
    result = extract_pose(
        rotated,
        swing_id="swing-rotated-pose",
        frames=ingestion.frames,
        backend=FakePoseBackend(missing_call=None),
        observation_revision="rotated-pose-001",
        camera_view=CameraView.UNKNOWN,
    )
    rendered = write_annotated_video(
        rotated,
        ingestion.frames,
        result.observations,
        tmp_path / "rotated-annotated.mp4",
        side_by_side=True,
    )
    assert ingestion.summary.rotation_degrees == 90
    assert (rendered.width_px, rendered.height_px) == (128, 96)


def test_mediapipe_configuration_rejects_missing_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model asset does not exist"):
        MediaPipePoseConfig(model_asset_path=tmp_path / "missing.task")
