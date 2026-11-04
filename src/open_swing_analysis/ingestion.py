"""Deterministic streaming video ingestion and capture diagnostics.

PyAV is used instead of OpenCV because it exposes decoded-frame PTS, time bases,
display rotation, codec details, and container metadata without synthesizing a
timestamp from frame number and nominal FPS.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path
from statistics import fmean, median
from time import perf_counter
from typing import Annotated, Any, Literal

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ConfigDict, Field, JsonValue, ValidationError, model_validator

from open_swing_analysis.contracts import (
    SCHEMA_VERSION,
    ContractModel,
    DecodeStatus,
    Frame,
    FrameQualityFlag,
    FrameRateMode,
    Identifier,
    VideoAsset,
)
from open_swing_analysis.storage import (
    DataContractError,
    DataIntegrityError,
    ImmutableDataError,
    LocalDataStore,
    SchemaVersionError,
)


INGESTION_SCHEMA_VERSION = "0.1.0"


class VideoIngestionError(RuntimeError):
    """Base error for video probing or decoding failures."""


class EmptyVideoError(VideoIngestionError):
    """Raised for a zero-byte file or a video with no decoded frames."""


class UnsupportedVideoError(VideoIngestionError):
    """Raised when FFmpeg cannot open a file or find a video stream."""


class VideoDecodeError(VideoIngestionError):
    """Raised when decoding fails and partial output was not requested."""


class VideoRotationError(VideoIngestionError):
    """Raised for display rotations this ingestion slice cannot apply safely."""


class FrameSelectionError(VideoIngestionError):
    """Raised when an invalid selection is supplied or selects no frames."""


class TimestampSource(str, Enum):
    ORIGINAL = "original"
    ESTIMATED_MISSING = "estimated_missing"
    ESTIMATED_DUPLICATE = "estimated_duplicate"
    ESTIMATED_NON_MONOTONIC = "estimated_non_monotonic"
    ESTIMATED_NEGATIVE = "estimated_negative"


@dataclass(frozen=True)
class FrameSelection:
    """Optional decoded-index selection while preserving source order."""

    start: int = 0
    stop: int | None = None
    step: int = 1
    indices: frozenset[int] | None = None

    def __post_init__(self) -> None:
        if self.start < 0:
            raise FrameSelectionError("selection start must be non-negative")
        if self.stop is not None and self.stop < self.start:
            raise FrameSelectionError("selection stop cannot precede start")
        if self.step <= 0:
            raise FrameSelectionError("selection step must be positive")
        if self.indices is not None and any(index < 0 for index in self.indices):
            raise FrameSelectionError("explicit frame indexes must be non-negative")

    def includes(self, frame_index: int) -> bool:
        if self.indices is not None:
            return frame_index in self.indices
        if frame_index < self.start:
            return False
        if self.stop is not None and frame_index >= self.stop:
            return False
        return (frame_index - self.start) % self.step == 0


@dataclass(frozen=True)
class DecodedVideoFrame:
    """One lazily decoded display-oriented frame."""

    frame_index: int
    raw_pts: int | None
    original_timestamp_s: float | None
    time_base_s: float | None
    rotation_degrees: int
    encoded_width_px: int
    encoded_height_px: int
    display_width_px: int
    display_height_px: int
    image: np.ndarray


class FrameCaptureDiagnostic(ContractModel):
    """Technical per-frame measurements and timestamp provenance."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        use_enum_values=False,
    )

    asset_id: Identifier
    swing_id: Identifier
    frame_index: Annotated[int, Field(ge=0)]
    raw_pts: int | None
    time_base_s: Annotated[float, Field(gt=0)] | None
    original_timestamp_s: float | None
    timestamp_s: Annotated[float, Field(ge=0)]
    timestamp_source: TimestampSource
    inter_frame_delta_s: float | None = None
    timestamp_deviation_s: Annotated[float, Field(ge=0)] | None = None
    timestamp_irregular: bool | None = None
    decode_status: DecodeStatus
    encoded_width_px: Annotated[int, Field(gt=0)]
    encoded_height_px: Annotated[int, Field(gt=0)]
    display_width_px: Annotated[int, Field(gt=0)]
    display_height_px: Annotated[int, Field(gt=0)]
    rotation_degrees: Literal[0, 90, 180, 270]
    average_brightness: Annotated[float, Field(ge=0, le=255)] | None = None
    contrast: Annotated[float, Field(ge=0)] | None = None
    blur_laplacian_variance: Annotated[float, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def validate_decoded_measurements(self) -> FrameCaptureDiagnostic:
        measurements = (
            self.average_brightness,
            self.contrast,
            self.blur_laplacian_variance,
        )
        if self.decode_status == DecodeStatus.DECODED and any(
            value is None for value in measurements
        ):
            raise ValueError("decoded frames require all capture-quality measurements")
        if self.decode_status != DecodeStatus.DECODED and any(
            value is not None for value in measurements
        ):
            raise ValueError("failed frames cannot claim image-quality measurements")
        return self


class CaptureQualitySummary(ContractModel):
    """Threshold-free technical summary of one complete decode pass."""

    asset_id: Identifier
    total_decoded_frames: Annotated[int, Field(ge=0)]
    selected_frames: Annotated[int, Field(ge=0)]
    declared_frames: Annotated[int, Field(ge=0)] | None = None
    declared_frame_shortfall: Annotated[int, Field(ge=0)] = 0
    decode_error_count: Annotated[int, Field(ge=0)] = 0
    decode_errors: tuple[str, ...] = ()
    missing_timestamp_count: Annotated[int, Field(ge=0)] = 0
    duplicate_timestamp_count: Annotated[int, Field(ge=0)] = 0
    non_monotonic_timestamp_count: Annotated[int, Field(ge=0)] = 0
    negative_timestamp_count: Annotated[int, Field(ge=0)] = 0
    irregular_interval_count: Annotated[int, Field(ge=0)] = 0
    median_inter_frame_s: Annotated[float, Field(gt=0)] | None = None
    max_timestamp_deviation_s: Annotated[float, Field(ge=0)] | None = None
    observed_fps: Annotated[float, Field(gt=0)] | None = None
    nominal_fps: Annotated[float, Field(gt=0)] | None = None
    frame_rate_mode: FrameRateMode
    mean_brightness: Annotated[float, Field(ge=0, le=255)] | None = None
    mean_contrast: Annotated[float, Field(ge=0)] | None = None
    mean_blur_laplacian_variance: Annotated[float, Field(ge=0)] | None = None
    encoded_width_px: Annotated[int, Field(gt=0)]
    encoded_height_px: Annotated[int, Field(gt=0)]
    display_width_px: Annotated[int, Field(gt=0)]
    display_height_px: Annotated[int, Field(gt=0)]
    rotation_degrees: Literal[0, 90, 180, 270]


@dataclass(frozen=True)
class IngestionPerformance:
    """Non-persisted timing data kept outside deterministic diagnostics."""

    elapsed_decode_s: float
    decoded_frames_per_s: float | None


@dataclass(frozen=True)
class VideoIngestionResult:
    """Validated metadata and scalar observations from one streaming pass."""

    asset: VideoAsset
    frames: tuple[Frame, ...]
    diagnostics: tuple[FrameCaptureDiagnostic, ...]
    summary: CaptureQualitySummary
    performance: IngestionPerformance


@dataclass(frozen=True)
class IngestionOutputPaths:
    asset_json: Path
    frames_parquet: Path
    diagnostics_parquet: Path
    summary_json: Path
    plots_png: Path | None


CAPTURE_DIAGNOSTIC_ARROW_SCHEMA = pa.schema(
    [
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("asset_id", pa.string(), nullable=False),
        pa.field("swing_id", pa.string(), nullable=False),
        pa.field("frame_index", pa.int64(), nullable=False),
        pa.field("raw_pts", pa.int64()),
        pa.field("time_base_s", pa.float64()),
        pa.field("original_timestamp_s", pa.float64()),
        pa.field("timestamp_s", pa.float64(), nullable=False),
        pa.field("timestamp_source", pa.string(), nullable=False),
        pa.field("inter_frame_delta_s", pa.float64()),
        pa.field("timestamp_deviation_s", pa.float64()),
        pa.field("timestamp_irregular", pa.bool_()),
        pa.field("decode_status", pa.string(), nullable=False),
        pa.field("encoded_width_px", pa.int64(), nullable=False),
        pa.field("encoded_height_px", pa.int64(), nullable=False),
        pa.field("display_width_px", pa.int64(), nullable=False),
        pa.field("display_height_px", pa.int64(), nullable=False),
        pa.field("rotation_degrees", pa.int64(), nullable=False),
        pa.field("average_brightness", pa.float64()),
        pa.field("contrast", pa.float64()),
        pa.field("blur_laplacian_variance", pa.float64()),
    ],
    metadata={
        b"schema_version": INGESTION_SCHEMA_VERSION.encode("ascii"),
        b"record_type": b"frame_capture_diagnostic",
    },
)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file incrementally without loading it into memory."""
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _fraction_float(value: Fraction | None) -> float | None:
    if value is None or value.denominator == 0 or value <= 0:
        return None
    return float(value)


def _normalize_rotation(value: int | float | None) -> int:
    rotation = int(round(float(value or 0))) % 360
    if rotation not in {0, 90, 180, 270}:
        raise VideoRotationError(
            f"display rotation {rotation}° is not a supported right-angle rotation"
        )
    return rotation


def _rotate_image(image: np.ndarray, rotation_degrees: int) -> np.ndarray:
    if rotation_degrees == 0:
        return image
    return np.rot90(image, k=rotation_degrees // 90).copy()


def _frame_timestamp(
    frame: av.VideoFrame,
) -> tuple[int | None, float | None, float | None]:
    raw_pts = frame.pts
    time_base_s = _fraction_float(frame.time_base)
    if raw_pts is None or time_base_s is None:
        return raw_pts, None, time_base_s
    timestamp = float(raw_pts * frame.time_base)
    return raw_pts, timestamp if math.isfinite(timestamp) else None, time_base_s


def _quality_metrics(gray: np.ndarray) -> tuple[float, float, float]:
    values = np.asarray(gray, dtype=np.float64)
    if values.ndim == 3:
        values = values[..., 0]
    brightness = float(values.mean())
    contrast = float(values.std())
    if values.shape[0] < 3 or values.shape[1] < 3:
        blur = 0.0
    else:
        centre = values[1:-1, 1:-1]
        laplacian = (
            values[:-2, 1:-1]
            + values[2:, 1:-1]
            + values[1:-1, :-2]
            + values[1:-1, 2:]
            - 4.0 * centre
        )
        blur = float(laplacian.var())
    return brightness, contrast, blur


class _TimestampNormalizer:
    def __init__(self, nominal_step_s: float | None):
        self.nominal_step_s = (
            nominal_step_s if nominal_step_s and nominal_step_s > 0 else None
        )
        self.previous_canonical: float | None = None
        self.previous_original: float | None = None
        self.last_positive_original_delta: float | None = None

    def add(
        self, original_timestamp_s: float | None
    ) -> tuple[float, TimestampSource, float | None]:
        original_delta = (
            None
            if original_timestamp_s is None or self.previous_original is None
            else original_timestamp_s - self.previous_original
        )
        if original_delta is not None and original_delta > 0:
            self.last_positive_original_delta = original_delta

        if original_timestamp_s is None:
            source = TimestampSource.ESTIMATED_MISSING
        elif original_timestamp_s < 0:
            source = TimestampSource.ESTIMATED_NEGATIVE
        elif (
            self.previous_canonical is None
            or original_timestamp_s > self.previous_canonical
        ):
            canonical = original_timestamp_s
            source = TimestampSource.ORIGINAL
            self.previous_canonical = canonical
            self.previous_original = original_timestamp_s
            return canonical, source, original_delta
        elif (
            self.previous_original is not None
            and original_timestamp_s == self.previous_original
        ):
            source = TimestampSource.ESTIMATED_DUPLICATE
        else:
            source = TimestampSource.ESTIMATED_NON_MONOTONIC

        step = self.last_positive_original_delta or self.nominal_step_s or 1e-6
        canonical = (
            0.0 if self.previous_canonical is None else self.previous_canonical + step
        )
        self.previous_canonical = canonical
        if original_timestamp_s is not None:
            self.previous_original = original_timestamp_s
        return canonical, source, original_delta


def normalize_timestamps(
    original_timestamps_s: Sequence[float | None], nominal_fps: float | None = None
) -> tuple[tuple[float, TimestampSource, float | None], ...]:
    """Expose the explicit timestamp-repair policy for testing and audit."""
    normalizer = _TimestampNormalizer(1.0 / nominal_fps if nominal_fps else None)
    return tuple(normalizer.add(timestamp) for timestamp in original_timestamps_s)


def _open_video(path: Path) -> av.container.InputContainer:
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise UnsupportedVideoError(f"video source is not a regular file: {path}")
    if path.stat().st_size == 0:
        raise EmptyVideoError(f"video source is empty: {path}")
    try:
        return av.open(str(path), mode="r")
    except av.FFmpegError as exc:
        raise UnsupportedVideoError(f"FFmpeg could not open {path}: {exc}") from exc


def _video_stream(container: av.container.InputContainer, path: Path) -> av.VideoStream:
    streams = [
        stream
        for stream in container.streams.video
        if not (stream.disposition & type(stream.disposition).attached_pic)
    ]
    if not streams:
        raise UnsupportedVideoError(f"no decodable video stream found in {path}")
    return streams[0]


class VideoReader:
    """Lazy display-oriented decoder that never retains earlier frames."""

    def __init__(self, path: str | Path, *, apply_rotation: bool = True):
        self.path = Path(path)
        self.apply_rotation = apply_rotation

    def iter_frames(
        self,
        selection: FrameSelection | None = None,
        *,
        pixel_format: str = "rgb24",
    ) -> Iterator[DecodedVideoFrame]:
        selected = selection or FrameSelection()
        container = _open_video(self.path)
        try:
            stream = _video_stream(container, self.path)
            try:
                for frame_index, frame in enumerate(container.decode(stream)):
                    if not selected.includes(frame_index):
                        continue
                    raw_pts, timestamp, time_base_s = _frame_timestamp(frame)
                    rotation = _normalize_rotation(frame.rotation)
                    image = frame.to_ndarray(format=pixel_format)
                    if self.apply_rotation:
                        image = _rotate_image(image, rotation)
                    display_height, display_width = image.shape[:2]
                    yield DecodedVideoFrame(
                        frame_index=frame_index,
                        raw_pts=raw_pts,
                        original_timestamp_s=timestamp,
                        time_base_s=time_base_s,
                        rotation_degrees=rotation,
                        encoded_width_px=frame.width,
                        encoded_height_px=frame.height,
                        display_width_px=display_width,
                        display_height_px=display_height,
                        image=image,
                    )
            except av.FFmpegError as exc:
                raise VideoDecodeError(
                    f"decoding failed for {self.path}: {exc}"
                ) from exc
        finally:
            container.close()


def _enum_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _enum_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _frame_rate_analysis(
    original_timestamps: Sequence[float | None], time_base_s: float | None
) -> tuple[FrameRateMode, float | None, float | None, int, float | None]:
    valid = [timestamp for timestamp in original_timestamps if timestamp is not None]
    deltas = [
        later - earlier for earlier, later in zip(valid, valid[1:]) if later > earlier
    ]
    if not deltas:
        return FrameRateMode.UNKNOWN, None, None, 0, None
    median_delta = float(median(deltas))
    observed_fps = (
        (len(valid) - 1) / (valid[-1] - valid[0])
        if len(valid) > 1 and valid[-1] > valid[0]
        else None
    )
    tolerance = max((time_base_s or 0.0) / 2.0, 1e-9)
    deviations = [abs(delta - median_delta) for delta in deltas]
    irregular_count = sum(deviation > tolerance for deviation in deviations)
    mode = FrameRateMode.VARIABLE if irregular_count else FrameRateMode.CONSTANT
    return (
        mode,
        median_delta,
        observed_fps,
        irregular_count,
        max(deviations, default=None),
    )


def ingest_video(
    path: str | Path,
    *,
    swing_id: str,
    asset_id: str | None = None,
    selection: FrameSelection | None = None,
    source_metadata: Mapping[str, JsonValue] | None = None,
    allow_partial: bool = True,
) -> VideoIngestionResult:
    """Stream a video once and return contracts plus threshold-free diagnostics."""
    source = Path(path)
    stat_before = source.stat() if source.exists() else None
    digest = sha256_file(source)
    resolved_asset_id = asset_id or f"asset-{digest[:16]}"
    selected = selection or FrameSelection()
    container = _open_video(source)
    start = perf_counter()
    decode_errors: list[str] = []
    diagnostics: list[FrameCaptureDiagnostic] = []
    frames: list[Frame] = []
    original_timestamps: list[float | None] = []
    timestamp_sources: list[TimestampSource] = []
    decoded_count = 0
    first_rotation = 0
    first_encoded_width = 0
    first_encoded_height = 0
    first_display_width = 0
    first_display_height = 0

    try:
        stream = _video_stream(container, source)
        nominal_fps = (
            _fraction_float(stream.base_rate)
            or _fraction_float(stream.guessed_rate)
            or _fraction_float(stream.average_rate)
        )
        nominal_step = 1.0 / nominal_fps if nominal_fps else None
        normalizer = _TimestampNormalizer(nominal_step)
        declared_frames = stream.frames or None
        stream_time_base = _fraction_float(stream.time_base)
        codec_name = stream.codec_context.name or None
        encoded_width = stream.codec_context.width or stream.width
        encoded_height = stream.codec_context.height or stream.height
        iterator = iter(container.decode(stream))
        while True:
            try:
                decoded = next(iterator)
            except StopIteration:
                break
            except av.FFmpegError as exc:
                message = f"decoder stopped after {decoded_count} frames: {exc}"
                decode_errors.append(message)
                if not allow_partial:
                    raise VideoDecodeError(message) from exc
                failure_index = decoded_count
                if selected.includes(failure_index) and first_encoded_width:
                    failure_timestamp, failure_source, failure_delta = normalizer.add(
                        None
                    )
                    timestamp_sources.append(failure_source)
                    frames.append(
                        Frame(
                            swing_id=swing_id,
                            video_asset_id=resolved_asset_id,
                            frame_index=failure_index,
                            timestamp_s=failure_timestamp,
                            decode_status=DecodeStatus.CORRUPT,
                        )
                    )
                    diagnostics.append(
                        FrameCaptureDiagnostic(
                            asset_id=resolved_asset_id,
                            swing_id=swing_id,
                            frame_index=failure_index,
                            raw_pts=None,
                            time_base_s=stream_time_base,
                            original_timestamp_s=None,
                            timestamp_s=failure_timestamp,
                            timestamp_source=failure_source,
                            inter_frame_delta_s=failure_delta,
                            decode_status=DecodeStatus.CORRUPT,
                            encoded_width_px=first_encoded_width,
                            encoded_height_px=first_encoded_height,
                            display_width_px=first_display_width,
                            display_height_px=first_display_height,
                            rotation_degrees=first_rotation,
                        )
                    )
                break

            frame_index = decoded_count
            decoded_count += 1
            raw_pts, original_timestamp, time_base_s = _frame_timestamp(decoded)
            original_timestamps.append(original_timestamp)
            canonical_timestamp, timestamp_source, original_delta = normalizer.add(
                original_timestamp
            )
            timestamp_sources.append(timestamp_source)
            rotation = _normalize_rotation(decoded.rotation)
            display_width = decoded.height if rotation in {90, 270} else decoded.width
            display_height = decoded.width if rotation in {90, 270} else decoded.height
            if decoded_count == 1:
                first_rotation = rotation
                first_encoded_width = decoded.width
                first_encoded_height = decoded.height
                first_display_width = display_width
                first_display_height = display_height

            if not selected.includes(frame_index):
                continue
            gray = decoded.to_ndarray(format="gray")
            gray = _rotate_image(gray, rotation)
            brightness, contrast, blur = _quality_metrics(gray)
            flags = (
                (FrameQualityFlag.DUPLICATE,)
                if timestamp_source == TimestampSource.ESTIMATED_DUPLICATE
                else ()
            )
            frames.append(
                Frame(
                    swing_id=swing_id,
                    video_asset_id=resolved_asset_id,
                    frame_index=frame_index,
                    timestamp_s=canonical_timestamp,
                    decode_status=DecodeStatus.DECODED,
                    quality_flags=flags,
                )
            )
            diagnostics.append(
                FrameCaptureDiagnostic(
                    asset_id=resolved_asset_id,
                    swing_id=swing_id,
                    frame_index=frame_index,
                    raw_pts=raw_pts,
                    time_base_s=time_base_s,
                    original_timestamp_s=original_timestamp,
                    timestamp_s=canonical_timestamp,
                    timestamp_source=timestamp_source,
                    inter_frame_delta_s=original_delta,
                    decode_status=DecodeStatus.DECODED,
                    encoded_width_px=decoded.width,
                    encoded_height_px=decoded.height,
                    display_width_px=display_width,
                    display_height_px=display_height,
                    rotation_degrees=rotation,
                    average_brightness=brightness,
                    contrast=contrast,
                    blur_laplacian_variance=blur,
                )
            )

        if decoded_count == 0:
            if decode_errors:
                raise VideoDecodeError(decode_errors[0])
            raise EmptyVideoError(f"video contains no decoded frames: {source}")
        if not frames:
            raise FrameSelectionError("frame selection retained no decoded frames")

        frame_rate_mode, median_delta, observed_fps, irregular_count, max_deviation = (
            _frame_rate_analysis(original_timestamps, stream_time_base)
        )
        tolerance = max((stream_time_base or 0.0) / 2.0, 1e-9)
        enriched_diagnostics = []
        for diagnostic in diagnostics:
            deviation = (
                abs(diagnostic.inter_frame_delta_s - median_delta)
                if diagnostic.inter_frame_delta_s is not None
                and median_delta is not None
                else None
            )
            enriched_diagnostics.append(
                diagnostic.model_copy(
                    update={
                        "timestamp_deviation_s": deviation,
                        "timestamp_irregular": (
                            deviation > tolerance if deviation is not None else None
                        ),
                    }
                )
            )
        diagnostics = enriched_diagnostics

        declared_shortfall = max((declared_frames or 0) - decoded_count, 0)
        if declared_shortfall:
            decode_errors.append(
                f"stream declared {declared_frames} frames but decoded {decoded_count}"
            )
        elapsed = perf_counter() - start
        source_duration = (
            float(stream.duration * stream.time_base)
            if stream.duration is not None and stream.time_base is not None
            else (
                float(container.duration / av.time_base)
                if container.duration is not None
                else frames[-1].timestamp_s + (median_delta or 0.0)
            )
        )
        source_duration = max(source_duration, 0.0)
        format_name = container.format.name if container.format is not None else None
        format_long_name = (
            container.format.long_name if container.format is not None else None
        )
        metadata = {
            "ingestion_backend": "PyAV",
            "ingestion_backend_version": av.__version__,
            "container_format": format_name,
            "container_format_long_name": format_long_name,
            "stream_index": stream.index,
            "stream_time_base": str(stream.time_base) if stream.time_base else None,
            "stream_average_rate": str(stream.average_rate)
            if stream.average_rate
            else None,
            "stream_base_rate": str(stream.base_rate) if stream.base_rate else None,
            "declared_frame_count": declared_frames,
            "decoded_frame_count": decoded_count,
            "observed_fps": observed_fps,
            "median_inter_frame_s": median_delta,
            "display_rotation_degrees": first_rotation,
            "display_width_px": first_display_width,
            "display_height_px": first_display_height,
            "timestamp_policy": "original_pts_or_explicitly_flagged_estimate",
        }
        file_metadata = {
            "file_size_bytes": stat_before.st_size
            if stat_before
            else source.stat().st_size,
            "file_mtime_ns": stat_before.st_mtime_ns
            if stat_before
            else source.stat().st_mtime_ns,
            "file_suffix": source.suffix.lower(),
            "resolved_source_path": str(source.resolve()),
        }
        asset = VideoAsset(
            asset_id=resolved_asset_id,
            source_filename=source.name,
            source_path=str(source),
            sha256=digest,
            width_px=encoded_width or first_encoded_width,
            height_px=encoded_height or first_encoded_height,
            nominal_fps=nominal_fps,
            frame_rate_mode=(
                FrameRateMode.UNKNOWN
                if frame_rate_mode == FrameRateMode.CONSTANT and nominal_fps is None
                else frame_rate_mode
            ),
            duration_s=source_duration,
            frame_count=decoded_count,
            codec=codec_name,
            acquisition_metadata=metadata,
            source_metadata={**dict(source_metadata or {}), **file_metadata},
        )
        brightness_values = [
            diagnostic.average_brightness
            for diagnostic in diagnostics
            if diagnostic.average_brightness is not None
        ]
        contrast_values = [
            diagnostic.contrast
            for diagnostic in diagnostics
            if diagnostic.contrast is not None
        ]
        blur_values = [
            diagnostic.blur_laplacian_variance
            for diagnostic in diagnostics
            if diagnostic.blur_laplacian_variance is not None
        ]
        summary = CaptureQualitySummary(
            asset_id=asset.asset_id,
            total_decoded_frames=decoded_count,
            selected_frames=len(frames),
            declared_frames=declared_frames,
            declared_frame_shortfall=declared_shortfall,
            decode_error_count=len(decode_errors),
            decode_errors=tuple(decode_errors),
            missing_timestamp_count=timestamp_sources.count(
                TimestampSource.ESTIMATED_MISSING
            ),
            duplicate_timestamp_count=timestamp_sources.count(
                TimestampSource.ESTIMATED_DUPLICATE
            ),
            non_monotonic_timestamp_count=timestamp_sources.count(
                TimestampSource.ESTIMATED_NON_MONOTONIC
            ),
            negative_timestamp_count=timestamp_sources.count(
                TimestampSource.ESTIMATED_NEGATIVE
            ),
            irregular_interval_count=irregular_count,
            median_inter_frame_s=median_delta,
            max_timestamp_deviation_s=max_deviation,
            observed_fps=observed_fps,
            nominal_fps=nominal_fps,
            frame_rate_mode=frame_rate_mode,
            mean_brightness=fmean(brightness_values) if brightness_values else None,
            mean_contrast=fmean(contrast_values) if contrast_values else None,
            mean_blur_laplacian_variance=fmean(blur_values) if blur_values else None,
            encoded_width_px=first_encoded_width,
            encoded_height_px=first_encoded_height,
            display_width_px=first_display_width,
            display_height_px=first_display_height,
            rotation_degrees=first_rotation,
        )
    finally:
        container.close()

    stat_after = source.stat()
    if stat_before and (
        stat_before.st_size != stat_after.st_size
        or stat_before.st_mtime_ns != stat_after.st_mtime_ns
    ):
        raise DataIntegrityError(f"video source changed during ingestion: {source}")
    return VideoIngestionResult(
        asset=asset,
        frames=tuple(frames),
        diagnostics=tuple(diagnostics),
        summary=summary,
        performance=IngestionPerformance(
            elapsed_decode_s=elapsed,
            decoded_frames_per_s=decoded_count / elapsed if elapsed > 0 else None,
        ),
    )


def _write_new(path: Path, content: str) -> Path:
    if path.exists():
        raise ImmutableDataError(f"refusing to overwrite immutable diagnostic: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _diagnostic_table(diagnostics: Sequence[FrameCaptureDiagnostic]) -> pa.Table:
    rows = [_enum_value(row.model_dump(mode="python")) for row in diagnostics]
    return pa.Table.from_pylist(rows, schema=CAPTURE_DIAGNOSTIC_ARROW_SCHEMA)


def write_diagnostic_plots(
    diagnostics: Sequence[FrameCaptureDiagnostic], path: str | Path
) -> Path:
    """Write the four requested threshold-free capture diagnostic plots."""
    import matplotlib.pyplot as plt

    if not diagnostics:
        raise DataIntegrityError("cannot plot an empty diagnostic sequence")
    destination = Path(path)
    if destination.exists():
        raise ImmutableDataError(f"refusing to overwrite immutable plot: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    indexes = [row.frame_index for row in diagnostics]
    timestamps = [row.timestamp_s for row in diagnostics]
    intervals = [
        row.inter_frame_delta_s
        for row in diagnostics
        if row.inter_frame_delta_s is not None and row.inter_frame_delta_s > 0
    ]
    brightness = [row.average_brightness for row in diagnostics]
    blur = [row.blur_laplacian_variance for row in diagnostics]

    figure, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    axes[0, 0].plot(indexes, timestamps, marker=".")
    axes[0, 0].set(
        title="Presentation timestamp", xlabel="Frame index", ylabel="Seconds"
    )
    if intervals:
        interval_span = max(intervals) - min(intervals)
        bins = (
            1
            if interval_span <= np.finfo(float).eps
            else min(30, max(5, len(intervals)))
        )
        axes[0, 1].hist(intervals, bins=bins)
    axes[0, 1].set(
        title="Inter-frame time distribution", xlabel="Seconds", ylabel="Count"
    )
    axes[1, 0].plot(timestamps, brightness)
    axes[1, 0].set(
        title="Average brightness", xlabel="Timestamp (s)", ylabel="Gray level (0–255)"
    )
    axes[1, 1].plot(timestamps, blur)
    axes[1, 1].set(
        title="Laplacian-variance blur proxy",
        xlabel="Timestamp (s)",
        ylabel="Variance (higher usually means more edge detail)",
    )
    for axis in axes.flat:
        axis.grid(alpha=0.2)
    figure.savefig(destination, dpi=140)
    plt.close(figure)
    return destination


def write_contact_sheet(
    frames: Sequence[DecodedVideoFrame], path: str | Path, *, columns: int = 4
) -> Path:
    """Write a small optional contact sheet from caller-selected frames."""
    import matplotlib.pyplot as plt

    if not frames:
        raise DataIntegrityError("cannot create a contact sheet without frames")
    if columns <= 0:
        raise ValueError("columns must be positive")
    destination = Path(path)
    if destination.exists():
        raise ImmutableDataError(
            f"refusing to overwrite immutable contact sheet: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = math.ceil(len(frames) / columns)
    figure, axes = plt.subplots(
        rows, columns, figsize=(3 * columns, 2.4 * rows), squeeze=False
    )
    for axis in axes.flat:
        axis.axis("off")
    for axis, frame in zip(axes.flat, frames, strict=False):
        axis.imshow(frame.image, cmap="gray" if frame.image.ndim == 2 else None)
        axis.set_title(f"frame {frame.frame_index} · {frame.original_timestamp_s!s}s")
        axis.axis("off")
    figure.tight_layout()
    figure.savefig(destination, dpi=130)
    plt.close(figure)
    return destination


def store_ingestion_result(
    store: LocalDataStore,
    session_id: str,
    swing_id: str,
    result: VideoIngestionResult,
    *,
    generate_plots: bool = True,
) -> IngestionOutputPaths:
    """Persist ingestion through the existing session/swing storage layout."""
    swing = store.read_swing(session_id, swing_id)
    if swing.video_asset_id != result.asset.asset_id:
        raise DataIntegrityError(
            "ingestion asset does not match the swing video reference"
        )
    stored_asset = store.read_video_asset(session_id, swing.video_asset_id)
    if stored_asset != result.asset:
        raise DataIntegrityError("stored VideoAsset differs from ingestion result")
    if any(frame.swing_id != swing_id for frame in result.frames):
        raise DataIntegrityError("ingested frames reference a different swing")
    if any(row.swing_id != swing_id for row in result.diagnostics):
        raise DataIntegrityError("capture diagnostics reference a different swing")

    frames_path = store.write_frames(session_id, swing_id, result.frames)
    diagnostics_directory = frames_path.parent / "diagnostics"
    diagnostics_path = diagnostics_directory / "capture_quality.parquet"
    summary_path = diagnostics_directory / "capture_quality_summary.json"
    plots_path = (
        diagnostics_directory / "capture_quality.png" if generate_plots else None
    )
    if diagnostics_path.exists():
        raise ImmutableDataError(
            f"refusing to overwrite immutable table: {diagnostics_path}"
        )
    diagnostics_directory.mkdir(parents=True, exist_ok=True)
    pq.write_table(_diagnostic_table(result.diagnostics), diagnostics_path)
    _write_new(summary_path, result.summary.model_dump_json(indent=2) + "\n")
    if plots_path is not None:
        write_diagnostic_plots(result.diagnostics, plots_path)
    asset_path = (
        store.root
        / "sessions"
        / session_id
        / "assets"
        / f"{result.asset.asset_id}.json"
    )
    return IngestionOutputPaths(
        asset_json=asset_path,
        frames_parquet=frames_path,
        diagnostics_parquet=diagnostics_path,
        summary_json=summary_path,
        plots_png=plots_path,
    )


def read_capture_diagnostics(
    store: LocalDataStore, session_id: str, swing_id: str
) -> list[FrameCaptureDiagnostic]:
    """Read and validate the capture-quality Parquet sidecar."""
    store.read_swing(session_id, swing_id)
    path = (
        store.root
        / "sessions"
        / session_id
        / "swings"
        / swing_id
        / "diagnostics"
        / "capture_quality.parquet"
    )
    table = pq.read_table(path)
    metadata = table.schema.metadata or {}
    actual_version = metadata.get(b"schema_version", b"").decode("utf-8") or None
    if actual_version != INGESTION_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"incompatible schema version in {path}: expected {INGESTION_SCHEMA_VERSION!r}, "
            f"found {actual_version!r}"
        )
    if metadata.get(b"record_type") != b"frame_capture_diagnostic":
        raise DataContractError(f"unexpected Parquet record type in {path}")
    if not table.schema.equals(CAPTURE_DIAGNOSTIC_ARROW_SCHEMA, check_metadata=False):
        raise DataContractError(f"incompatible Arrow schema in {path}")
    try:
        records = [
            FrameCaptureDiagnostic.model_validate(row) for row in table.to_pylist()
        ]
    except ValidationError as exc:
        raise DataContractError(f"invalid capture diagnostic in {path}: {exc}") from exc
    previous_index = -1
    previous_timestamp = -1.0
    for record in records:
        if record.swing_id != swing_id or record.frame_index <= previous_index:
            raise DataIntegrityError(f"invalid frame reference in {path}")
        if record.timestamp_s <= previous_timestamp:
            raise DataIntegrityError(f"unordered canonical timestamps in {path}")
        previous_index = record.frame_index
        previous_timestamp = record.timestamp_s
    return records


def read_capture_summary(
    store: LocalDataStore, session_id: str, swing_id: str
) -> CaptureQualitySummary:
    """Read and validate a capture-quality JSON summary."""
    swing = store.read_swing(session_id, swing_id)
    path = (
        store.root
        / "sessions"
        / session_id
        / "swings"
        / swing_id
        / "diagnostics"
        / "capture_quality_summary.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataContractError(f"cannot read capture summary {path}: {exc}") from exc
    actual_version = (
        payload.get("schema_version") if isinstance(payload, dict) else None
    )
    if actual_version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"incompatible schema version in {path}: expected {SCHEMA_VERSION!r}, "
            f"found {actual_version!r}"
        )
    try:
        summary = CaptureQualitySummary.model_validate(payload)
    except ValidationError as exc:
        raise DataContractError(f"invalid capture summary in {path}: {exc}") from exc
    if summary.asset_id != swing.video_asset_id:
        raise DataIntegrityError("capture summary asset does not match swing")
    return summary
