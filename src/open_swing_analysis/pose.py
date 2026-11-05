"""Backend-neutral, persistent pose extraction over the PyAV video reader.

Raw landmark values are copied to :class:`PoseObservation` without smoothing.
The MediaPipe Tasks video API receives a separate, monotonic millisecond clock;
the source-aligned ``Frame.timestamp_s`` remains the stored observation time.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Annotated, Any, Protocol

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    model_validator,
)

from open_swing_analysis.contracts import (
    SCHEMA_VERSION,
    CameraView,
    ContractModel,
    DecodeStatus,
    Frame,
    Identifier,
    ObservationLayer,
    ObservationSource,
    ObservationStatus,
    PoseObservation,
    Probability,
)
from open_swing_analysis.ingestion import FrameSelection, VideoReader, sha256_file
from open_swing_analysis.storage import (
    DataContractError,
    DataIntegrityError,
    ImmutableDataError,
    LocalDataStore,
    SchemaVersionError,
)


POSE_EXTRACTION_SCHEMA_VERSION = "0.1.0"

LANDMARK_NAMES = (
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
)

POSE_CONNECTIONS = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (17, 19),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (18, 20),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (27, 29),
    (29, 31),
    (27, 31),
    (24, 26),
    (26, 28),
    (28, 30),
    (30, 32),
    (28, 32),
)


class PoseExtractionError(RuntimeError):
    """Raised when a pose backend or its source-frame alignment fails."""


@dataclass(frozen=True)
class BackendLandmark:
    """Backend-neutral raw landmark values for one model result."""

    index: int
    x: float | None
    y: float | None
    relative_z: float | None
    visibility: float | None
    confidence: float | None


@dataclass(frozen=True)
class BackendPoseResult:
    """One frame result. An empty tuple means no pose was detected."""

    landmarks: tuple[BackendLandmark, ...]


class PoseBackend(Protocol):
    """Small lifecycle boundary for future MediaPipe, YOLO, or MMPose backends."""

    @property
    def model_name(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    @property
    def source_revision(self) -> str: ...

    @property
    def configuration(self) -> Mapping[str, JsonValue]: ...

    def open(self) -> None: ...

    def process(
        self, image_rgb: np.ndarray, timestamp_ms: int
    ) -> BackendPoseResult: ...

    def close(self) -> None: ...


class MediaPipePoseConfig(BaseModel):
    """Configuration for the supported MediaPipe Tasks video API."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    model_asset_path: Path
    num_poses: Annotated[int, Field(ge=1, le=1)] = 1
    min_pose_detection_confidence: Probability = 0.5
    min_pose_presence_confidence: Probability = 0.5
    min_tracking_confidence: Probability = 0.5
    delegate: str = "CPU"

    @model_validator(mode="after")
    def require_model_file_and_cpu(self) -> MediaPipePoseConfig:
        if not self.model_asset_path.is_file():
            raise ValueError(f"model asset does not exist: {self.model_asset_path}")
        if self.delegate != "CPU":
            raise ValueError("V0.1 supports the CPU delegate only")
        return self


class MediaPipePoseBackend:
    """One persistent MediaPipe Pose Landmarker Tasks instance per video."""

    def __init__(self, config: MediaPipePoseConfig):
        self.config = config
        self._landmarker: Any | None = None
        self._mediapipe: Any | None = None
        self._package_version: str | None = None
        self._model_sha256 = sha256_file(config.model_asset_path)
        revision_payload = json.dumps(self.configuration, sort_keys=True).encode(
            "utf-8"
        )
        self._source_revision = (
            f"mp-{hashlib.sha256(revision_payload).hexdigest()[:16]}"
        )

    @property
    def model_name(self) -> str:
        return "mediapipe_pose_landmarker"

    @property
    def model_version(self) -> str:
        package = self._package_version or "unknown"
        return f"mediapipe-{package};model-sha256-{self._model_sha256[:16]}"

    @property
    def source_revision(self) -> str:
        return self._source_revision

    @property
    def configuration(self) -> Mapping[str, JsonValue]:
        return {
            "api": "MediaPipe Tasks PoseLandmarker.detect_for_video",
            "running_mode": "VIDEO",
            "delegate": self.config.delegate,
            "model_asset_filename": self.config.model_asset_path.name,
            "model_asset_sha256": self._model_sha256,
            "num_poses": self.config.num_poses,
            "min_pose_detection_confidence": self.config.min_pose_detection_confidence,
            "min_pose_presence_confidence": self.config.min_pose_presence_confidence,
            "min_tracking_confidence": self.config.min_tracking_confidence,
            "output_segmentation_masks": False,
        }

    def open(self) -> None:
        if self._landmarker is not None:
            raise PoseExtractionError("MediaPipe backend is already open")
        try:
            import mediapipe as mp
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise PoseExtractionError("MediaPipe is not installed") from exc
        self._mediapipe = mp
        self._package_version = mp.__version__
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(self.config.model_asset_path),
                delegate=mp.tasks.BaseOptions.Delegate.CPU,
            ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=self.config.num_poses,
            min_pose_detection_confidence=self.config.min_pose_detection_confidence,
            min_pose_presence_confidence=self.config.min_pose_presence_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
            output_segmentation_masks=False,
        )
        try:
            self._landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(
                options
            )
        except (RuntimeError, ValueError) as exc:
            self._mediapipe = None
            raise PoseExtractionError(f"could not initialize MediaPipe: {exc}") from exc

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> BackendPoseResult:
        if self._landmarker is None or self._mediapipe is None:
            raise PoseExtractionError("MediaPipe backend is not open")
        contiguous = np.ascontiguousarray(image_rgb, dtype=np.uint8)
        image = self._mediapipe.Image(
            image_format=self._mediapipe.ImageFormat.SRGB, data=contiguous
        )
        try:
            result = self._landmarker.detect_for_video(image, timestamp_ms)
        except (RuntimeError, ValueError) as exc:
            raise PoseExtractionError(
                f"MediaPipe inference failed at {timestamp_ms} ms: {exc}"
            ) from exc
        if not result.pose_landmarks:
            return BackendPoseResult(landmarks=())
        pose = result.pose_landmarks[0]
        return BackendPoseResult(
            landmarks=tuple(
                BackendLandmark(
                    index=index,
                    x=landmark.x,
                    y=landmark.y,
                    relative_z=landmark.z,
                    visibility=landmark.visibility,
                    confidence=landmark.presence,
                )
                for index, landmark in enumerate(pose)
            )
        )

    def close(self) -> None:
        if self._landmarker is not None:
            landmarker = self._landmarker
            self._landmarker = None
            self._mediapipe = None
            try:
                landmarker.close()
            except RuntimeError as exc:
                raise PoseExtractionError(f"could not close MediaPipe: {exc}") from exc


class PoseFrameDiagnostic(ContractModel):
    """Descriptive, non-biomechanical diagnostics for one requested frame."""

    swing_id: Identifier
    frame_index: Annotated[int, Field(ge=0)]
    timestamp_s: Annotated[float, Field(ge=0)]
    inference_timestamp_ms: Annotated[int, Field(ge=0)] | None
    inference_timestamp_adjusted: bool
    decode_status: DecodeStatus
    pose_detected: bool
    returned_landmark_count: Annotated[int, Field(ge=0, le=33)]
    observed_landmark_count: Annotated[int, Field(ge=0, le=33)]
    missing_landmark_count: Annotated[int, Field(ge=0, le=33)]
    mean_visibility: Probability | None
    processing_time_ms: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def counts_sum_to_landmark_set(self) -> PoseFrameDiagnostic:
        if self.observed_landmark_count + self.missing_landmark_count != 33:
            raise ValueError("observed and missing landmark counts must sum to 33")
        if not self.pose_detected and self.returned_landmark_count != 0:
            raise ValueError("a missing pose cannot return landmarks")
        if (
            self.decode_status != DecodeStatus.DECODED
            and self.inference_timestamp_ms is not None
        ):
            raise ValueError("undecoded frames cannot claim an inference timestamp")
        return self


class MissingPoseInterval(ContractModel):
    start_frame_index: Annotated[int, Field(ge=0)]
    end_frame_index: Annotated[int, Field(ge=0)]
    start_timestamp_s: Annotated[float, Field(ge=0)]
    end_timestamp_s: Annotated[float, Field(ge=0)]
    frame_count: Annotated[int, Field(gt=0)]


class PoseExtractionSummary(ContractModel):
    """Aggregate coverage and timing for one immutable raw pose revision."""

    swing_id: Identifier
    observation_revision: Identifier
    camera_view: CameraView
    model_name: str
    model_version: str
    model_source_revision: Identifier
    model_configuration: dict[str, JsonValue]
    timestamp_policy: str
    frames_processed: Annotated[int, Field(ge=0)]
    frames_with_pose: Annotated[int, Field(ge=0)]
    pose_detection_coverage: Probability
    observed_landmark_count: Annotated[int, Field(ge=0)]
    missing_landmark_count: Annotated[int, Field(ge=0)]
    missing_landmark_counts_by_name: dict[str, int]
    visibility_count: Annotated[int, Field(ge=0)]
    visibility_mean: Probability | None
    visibility_p10: Probability | None
    visibility_median: Probability | None
    visibility_p90: Probability | None
    missing_pose_intervals: tuple[MissingPoseInterval, ...]
    inference_timestamp_adjustment_count: Annotated[int, Field(ge=0)]
    total_inference_time_s: Annotated[float, Field(ge=0)]
    mean_processing_time_ms: Annotated[float, Field(ge=0)] | None
    p95_processing_time_ms: Annotated[float, Field(ge=0)] | None


@dataclass(frozen=True)
class PoseExtractionResult:
    observations: tuple[PoseObservation, ...]
    diagnostics: tuple[PoseFrameDiagnostic, ...]
    summary: PoseExtractionSummary


@dataclass(frozen=True)
class PoseOutputPaths:
    observations_parquet: Path
    diagnostics_parquet: Path
    summary_json: Path
    plots_png: Path | None


class _InferenceTimestampMapper:
    def __init__(self) -> None:
        self.previous: int | None = None

    def map(self, timestamp_s: float) -> tuple[int, bool]:
        candidate = int(round(timestamp_s * 1000.0))
        adjusted = self.previous is not None and candidate <= self.previous
        if adjusted:
            candidate = self.previous + 1
        self.previous = candidate
        return candidate, adjusted


def map_inference_timestamps(
    timestamps_s: Sequence[float],
) -> tuple[tuple[int, bool], ...]:
    """Map source-aligned seconds to MediaPipe's monotonic integer milliseconds."""
    mapper = _InferenceTimestampMapper()
    return tuple(mapper.map(timestamp) for timestamp in timestamps_s)


def _missing_observations(
    frame: Frame,
    *,
    backend: PoseBackend,
    observation_revision: str,
    recorded_at: datetime,
) -> tuple[PoseObservation, ...]:
    return tuple(
        PoseObservation(
            swing_id=frame.swing_id,
            frame_index=frame.frame_index,
            timestamp_s=frame.timestamp_s,
            landmark_name=name,
            landmark_index=index,
            x=None,
            y=None,
            relative_z=None,
            visibility=None,
            confidence=None,
            pose_model=backend.model_name,
            pose_model_version=backend.model_version,
            observation_status=ObservationStatus.NOT_OBSERVED,
            data_layer=ObservationLayer.RAW,
            observation_revision=observation_revision,
            source=ObservationSource.MODEL,
            source_id=backend.model_name,
            source_revision=backend.source_revision,
            recorded_at=recorded_at,
        )
        for index, name in enumerate(LANDMARK_NAMES)
    )


def _observations_from_result(
    frame: Frame,
    result: BackendPoseResult,
    *,
    backend: PoseBackend,
    observation_revision: str,
    low_confidence_threshold: float,
    recorded_at: datetime,
) -> tuple[PoseObservation, ...]:
    indexed: dict[int, BackendLandmark] = {}
    for landmark in result.landmarks:
        if landmark.index < 0 or landmark.index >= len(LANDMARK_NAMES):
            raise PoseExtractionError(
                f"backend returned invalid landmark index {landmark.index}"
            )
        if landmark.index in indexed:
            raise PoseExtractionError(
                f"backend returned duplicate landmark index {landmark.index}"
            )
        indexed[landmark.index] = landmark

    observations = []
    for index, name in enumerate(LANDMARK_NAMES):
        landmark = indexed.get(index)
        present = (
            landmark is not None and landmark.x is not None and landmark.y is not None
        )
        if not present:
            observations.extend(
                _missing_observations(
                    frame,
                    backend=backend,
                    observation_revision=observation_revision,
                    recorded_at=recorded_at,
                )[index : index + 1]
            )
            continue
        assert landmark is not None
        quality_values = [
            value
            for value in (landmark.visibility, landmark.confidence)
            if value is not None
        ]
        status = (
            ObservationStatus.LOW_CONFIDENCE
            if quality_values and min(quality_values) < low_confidence_threshold
            else ObservationStatus.OBSERVED
        )
        observations.append(
            PoseObservation(
                swing_id=frame.swing_id,
                frame_index=frame.frame_index,
                timestamp_s=frame.timestamp_s,
                landmark_name=name,
                landmark_index=index,
                x=landmark.x,
                y=landmark.y,
                relative_z=landmark.relative_z,
                visibility=landmark.visibility,
                confidence=landmark.confidence,
                relative_z_coordinate_system=(
                    "model_relative_depth" if landmark.relative_z is not None else None
                ),
                pose_model=backend.model_name,
                pose_model_version=backend.model_version,
                observation_status=status,
                data_layer=ObservationLayer.RAW,
                observation_revision=observation_revision,
                source=ObservationSource.MODEL,
                source_id=backend.model_name,
                source_revision=backend.source_revision,
                recorded_at=recorded_at,
            )
        )
    return tuple(observations)


def _missing_intervals(
    frames: Sequence[Frame], diagnostics: Sequence[PoseFrameDiagnostic]
) -> tuple[MissingPoseInterval, ...]:
    intervals: list[MissingPoseInterval] = []
    start: int | None = None
    for position, diagnostic in enumerate(diagnostics):
        if not diagnostic.pose_detected and start is None:
            start = position
        at_end = position == len(diagnostics) - 1
        if start is not None and (diagnostic.pose_detected or at_end):
            end = position if not diagnostic.pose_detected and at_end else position - 1
            first = frames[start]
            last = frames[end]
            intervals.append(
                MissingPoseInterval(
                    start_frame_index=first.frame_index,
                    end_frame_index=last.frame_index,
                    start_timestamp_s=first.timestamp_s,
                    end_timestamp_s=last.timestamp_s,
                    frame_count=end - start + 1,
                )
            )
            start = None
    return tuple(intervals)


def extract_pose(
    video_path: str | Path,
    *,
    swing_id: str,
    frames: Sequence[Frame],
    backend: PoseBackend,
    observation_revision: str,
    camera_view: CameraView,
    low_confidence_threshold: Probability = 0.5,
    recorded_at: datetime | None = None,
) -> PoseExtractionResult:
    """Decode selected source frames and persistently process one backend instance."""
    source_frames = tuple(frames)
    if not source_frames:
        raise DataIntegrityError("pose extraction requires at least one Frame record")
    previous_index = -1
    previous_timestamp = -1.0
    for frame in source_frames:
        if frame.swing_id != swing_id:
            raise DataIntegrityError(
                "pose extraction Frame references a different swing"
            )
        if (
            frame.frame_index <= previous_index
            or frame.timestamp_s <= previous_timestamp
        ):
            raise DataIntegrityError("pose extraction frames must be strictly ordered")
        previous_index = frame.frame_index
        previous_timestamp = frame.timestamp_s

    captured_at = recorded_at or datetime.now(timezone.utc)
    frame_lookup = {frame.frame_index: frame for frame in source_frames}
    decoded_indexes = {
        frame.frame_index
        for frame in source_frames
        if frame.decode_status == DecodeStatus.DECODED
    }
    observations_by_frame: dict[int, tuple[PoseObservation, ...]] = {}
    diagnostics_by_frame: dict[int, PoseFrameDiagnostic] = {}
    timestamp_mapper = _InferenceTimestampMapper()

    backend.open()
    try:
        if decoded_indexes:
            selection = FrameSelection(indices=frozenset(decoded_indexes))
            for decoded in VideoReader(video_path).iter_frames(selection):
                frame = frame_lookup.get(decoded.frame_index)
                if frame is None:
                    raise DataIntegrityError(
                        f"decoded frame {decoded.frame_index} has no Frame contract"
                    )
                timestamp_ms, adjusted = timestamp_mapper.map(frame.timestamp_s)
                started = perf_counter()
                backend_result = backend.process(decoded.image, timestamp_ms)
                elapsed_ms = (perf_counter() - started) * 1000.0
                observations = _observations_from_result(
                    frame,
                    backend_result,
                    backend=backend,
                    observation_revision=observation_revision,
                    low_confidence_threshold=low_confidence_threshold,
                    recorded_at=captured_at,
                )
                observations_by_frame[frame.frame_index] = observations
                observed = sum(
                    row.observation_status
                    in {ObservationStatus.OBSERVED, ObservationStatus.LOW_CONFIDENCE}
                    for row in observations
                )
                visibility = [
                    row.visibility for row in observations if row.visibility is not None
                ]
                diagnostics_by_frame[frame.frame_index] = PoseFrameDiagnostic(
                    swing_id=swing_id,
                    frame_index=frame.frame_index,
                    timestamp_s=frame.timestamp_s,
                    inference_timestamp_ms=timestamp_ms,
                    inference_timestamp_adjusted=adjusted,
                    decode_status=frame.decode_status,
                    pose_detected=bool(backend_result.landmarks),
                    returned_landmark_count=len(backend_result.landmarks),
                    observed_landmark_count=observed,
                    missing_landmark_count=33 - observed,
                    mean_visibility=fmean(visibility) if visibility else None,
                    processing_time_ms=elapsed_ms,
                )
    finally:
        backend.close()

    for frame in source_frames:
        if frame.frame_index in diagnostics_by_frame:
            continue
        missing = _missing_observations(
            frame,
            backend=backend,
            observation_revision=observation_revision,
            recorded_at=captured_at,
        )
        observations_by_frame[frame.frame_index] = missing
        diagnostics_by_frame[frame.frame_index] = PoseFrameDiagnostic(
            swing_id=swing_id,
            frame_index=frame.frame_index,
            timestamp_s=frame.timestamp_s,
            inference_timestamp_ms=None,
            inference_timestamp_adjusted=False,
            decode_status=frame.decode_status,
            pose_detected=False,
            returned_landmark_count=0,
            observed_landmark_count=0,
            missing_landmark_count=33,
            mean_visibility=None,
            processing_time_ms=0.0,
        )

    observations = tuple(
        observation
        for frame in source_frames
        for observation in observations_by_frame[frame.frame_index]
    )
    diagnostics = tuple(
        diagnostics_by_frame[frame.frame_index] for frame in source_frames
    )
    visibility_values = np.asarray(
        [row.visibility for row in observations if row.visibility is not None],
        dtype=float,
    )
    observed_count = sum(
        row.observation_status
        in {ObservationStatus.OBSERVED, ObservationStatus.LOW_CONFIDENCE}
        for row in observations
    )
    frames_with_pose = sum(row.pose_detected for row in diagnostics)
    processing_times = np.asarray(
        [
            row.processing_time_ms
            for row in diagnostics
            if row.inference_timestamp_ms is not None
        ],
        dtype=float,
    )
    missing_by_name = {
        name: sum(
            row.landmark_name == name
            and row.observation_status == ObservationStatus.NOT_OBSERVED
            for row in observations
        )
        for name in LANDMARK_NAMES
    }
    summary = PoseExtractionSummary(
        swing_id=swing_id,
        observation_revision=observation_revision,
        camera_view=camera_view,
        model_name=backend.model_name,
        model_version=backend.model_version,
        model_source_revision=backend.source_revision,
        model_configuration=dict(backend.configuration),
        timestamp_policy=(
            "PoseObservation.timestamp_s exactly matches Frame.timestamp_s; MediaPipe "
            "receives round(timestamp_s*1000) with +1 ms only to resolve non-increasing "
            "integer-millisecond collisions."
        ),
        frames_processed=len(source_frames),
        frames_with_pose=frames_with_pose,
        pose_detection_coverage=frames_with_pose / len(source_frames),
        observed_landmark_count=observed_count,
        missing_landmark_count=len(observations) - observed_count,
        missing_landmark_counts_by_name=missing_by_name,
        visibility_count=int(visibility_values.size),
        visibility_mean=float(visibility_values.mean())
        if visibility_values.size
        else None,
        visibility_p10=float(np.quantile(visibility_values, 0.10))
        if visibility_values.size
        else None,
        visibility_median=float(np.quantile(visibility_values, 0.50))
        if visibility_values.size
        else None,
        visibility_p90=float(np.quantile(visibility_values, 0.90))
        if visibility_values.size
        else None,
        missing_pose_intervals=_missing_intervals(source_frames, diagnostics),
        inference_timestamp_adjustment_count=sum(
            row.inference_timestamp_adjusted for row in diagnostics
        ),
        total_inference_time_s=float(processing_times.sum() / 1000.0),
        mean_processing_time_ms=float(processing_times.mean())
        if processing_times.size
        else None,
        p95_processing_time_ms=float(np.quantile(processing_times, 0.95))
        if processing_times.size
        else None,
    )
    return PoseExtractionResult(observations, diagnostics, summary)


POSE_DIAGNOSTIC_ARROW_SCHEMA = pa.schema(
    [
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("swing_id", pa.string(), nullable=False),
        pa.field("frame_index", pa.int64(), nullable=False),
        pa.field("timestamp_s", pa.float64(), nullable=False),
        pa.field("inference_timestamp_ms", pa.int64()),
        pa.field("inference_timestamp_adjusted", pa.bool_(), nullable=False),
        pa.field("decode_status", pa.string(), nullable=False),
        pa.field("pose_detected", pa.bool_(), nullable=False),
        pa.field("returned_landmark_count", pa.int64(), nullable=False),
        pa.field("observed_landmark_count", pa.int64(), nullable=False),
        pa.field("missing_landmark_count", pa.int64(), nullable=False),
        pa.field("mean_visibility", pa.float64()),
        pa.field("processing_time_ms", pa.float64(), nullable=False),
    ],
    metadata={
        b"schema_version": POSE_EXTRACTION_SCHEMA_VERSION.encode("ascii"),
        b"record_type": b"pose_frame_diagnostic",
    },
)


def _arrow_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _arrow_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_arrow_value(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _write_new_text(path: Path, content: str) -> Path:
    if path.exists():
        raise ImmutableDataError(
            f"refusing to overwrite immutable pose diagnostic: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_pose_diagnostic_plots(
    observations: Sequence[PoseObservation],
    diagnostics: Sequence[PoseFrameDiagnostic],
    path: str | Path,
) -> Path:
    """Write six descriptive raw-trajectory and extraction diagnostic panels."""
    import matplotlib.pyplot as plt

    if not observations or not diagnostics:
        raise DataIntegrityError("cannot plot empty pose extraction results")
    destination = Path(path)
    if destination.exists():
        raise ImmutableDataError(f"refusing to overwrite immutable plot: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    by_name: dict[str, list[PoseObservation]] = {name: [] for name in LANDMARK_NAMES}
    for observation in observations:
        if observation.x is not None and observation.y is not None:
            by_name[observation.landmark_name].append(observation)

    figure, axes = plt.subplots(3, 2, figsize=(13, 12), constrained_layout=True)

    def plot_xy(axis: Any, names: Sequence[str], title: str) -> None:
        for name in names:
            rows = by_name[name]
            axis.plot(
                [row.timestamp_s for row in rows],
                [row.x for row in rows],
                label=f"{name} x",
            )
            axis.plot(
                [row.timestamp_s for row in rows],
                [row.y for row in rows],
                linestyle="--",
                label=f"{name} y",
            )
        axis.set(
            title=title, xlabel="Timestamp (s)", ylabel="Normalized image coordinate"
        )
        axis.legend(fontsize=7, ncol=2)

    plot_xy(axes[0, 0], ("left_wrist", "right_wrist"), "Raw wrist trajectories")
    plot_xy(
        axes[0, 1],
        ("left_shoulder", "right_shoulder", "left_hip", "right_hip"),
        "Raw shoulder and hip trajectories",
    )
    plot_xy(axes[1, 0], ("nose",), "Raw head-position proxy (nose landmark)")

    visibility_rows = [row for row in observations if row.visibility is not None]
    axes[1, 1].scatter(
        [row.timestamp_s for row in visibility_rows],
        [row.visibility for row in visibility_rows],
        s=4,
        alpha=0.35,
    )
    axes[1, 1].set(
        title="Landmark visibility (all raw landmarks)",
        xlabel="Timestamp (s)",
        ylabel="MediaPipe visibility",
        ylim=(-0.02, 1.02),
    )
    axes[2, 0].step(
        [row.timestamp_s for row in diagnostics],
        [int(not row.pose_detected) for row in diagnostics],
        where="mid",
    )
    axes[2, 0].set(
        title="Missing pose detections",
        xlabel="Timestamp (s)",
        ylabel="Missing (1=yes)",
        yticks=(0, 1),
    )
    axes[2, 1].plot(
        [row.timestamp_s for row in diagnostics],
        [row.processing_time_ms for row in diagnostics],
        marker=".",
    )
    axes[2, 1].set(
        title="Pose processing time",
        xlabel="Timestamp (s)",
        ylabel="Milliseconds per frame",
    )
    for axis in axes.flat:
        axis.grid(alpha=0.2)
    figure.savefig(destination, dpi=140)
    plt.close(figure)
    return destination


def store_pose_extraction(
    store: LocalDataStore,
    session_id: str,
    swing_id: str,
    result: PoseExtractionResult,
    *,
    generate_plots: bool = True,
) -> PoseOutputPaths:
    """Persist raw observations and validated pose diagnostic sidecars."""
    session = store.read_session(session_id)
    if result.summary.camera_view != session.camera_view:
        raise DataIntegrityError("pose summary camera view differs from the session")
    observations_path = store.write_pose_observations(
        session_id, swing_id, result.observations
    )
    revision = result.summary.observation_revision
    directory = (
        store.root
        / "sessions"
        / session_id
        / "swings"
        / swing_id
        / "diagnostics"
        / "pose"
        / revision
    )
    diagnostics_path = directory / "frames.parquet"
    summary_path = directory / "summary.json"
    plots_path = directory / "trajectories.png" if generate_plots else None
    if diagnostics_path.exists():
        raise ImmutableDataError(
            f"refusing to overwrite immutable table: {diagnostics_path}"
        )
    directory.mkdir(parents=True, exist_ok=True)
    rows = [_arrow_value(row.model_dump(mode="python")) for row in result.diagnostics]
    pq.write_table(
        pa.Table.from_pylist(rows, schema=POSE_DIAGNOSTIC_ARROW_SCHEMA),
        diagnostics_path,
    )
    _write_new_text(summary_path, result.summary.model_dump_json(indent=2) + "\n")
    if plots_path is not None:
        write_pose_diagnostic_plots(result.observations, result.diagnostics, plots_path)
    return PoseOutputPaths(
        observations_path, diagnostics_path, summary_path, plots_path
    )


def read_pose_diagnostics(
    store: LocalDataStore, session_id: str, swing_id: str, revision: str
) -> list[PoseFrameDiagnostic]:
    store.read_swing(session_id, swing_id)
    path = (
        store.root
        / "sessions"
        / session_id
        / "swings"
        / swing_id
        / "diagnostics"
        / "pose"
        / revision
        / "frames.parquet"
    )
    table = pq.read_table(path)
    metadata = table.schema.metadata or {}
    actual_version = metadata.get(b"schema_version", b"").decode("utf-8") or None
    if actual_version != POSE_EXTRACTION_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"incompatible schema version in {path}: expected {POSE_EXTRACTION_SCHEMA_VERSION!r}, "
            f"found {actual_version!r}"
        )
    if metadata.get(b"record_type") != b"pose_frame_diagnostic":
        raise DataContractError(f"unexpected Parquet record type in {path}")
    if not table.schema.equals(POSE_DIAGNOSTIC_ARROW_SCHEMA, check_metadata=False):
        raise DataContractError(f"incompatible Arrow schema in {path}")
    try:
        records = [PoseFrameDiagnostic.model_validate(row) for row in table.to_pylist()]
    except ValidationError as exc:
        raise DataContractError(f"invalid pose diagnostic in {path}: {exc}") from exc
    previous_index = -1
    for record in records:
        if record.swing_id != swing_id or record.frame_index <= previous_index:
            raise DataIntegrityError(f"invalid frame ordering/reference in {path}")
        previous_index = record.frame_index
    return records


def read_pose_summary(
    store: LocalDataStore, session_id: str, swing_id: str, revision: str
) -> PoseExtractionSummary:
    store.read_swing(session_id, swing_id)
    path = (
        store.root
        / "sessions"
        / session_id
        / "swings"
        / swing_id
        / "diagnostics"
        / "pose"
        / revision
        / "summary.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataContractError(f"cannot read pose summary {path}: {exc}") from exc
    actual_version = (
        payload.get("schema_version") if isinstance(payload, dict) else None
    )
    if actual_version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"incompatible schema version in {path}: expected {SCHEMA_VERSION!r}, found {actual_version!r}"
        )
    try:
        summary = PoseExtractionSummary.model_validate(payload)
    except ValidationError as exc:
        raise DataContractError(f"invalid pose summary in {path}: {exc}") from exc
    if summary.swing_id != swing_id or summary.observation_revision != revision:
        raise DataIntegrityError("pose summary does not match its storage path")
    return summary
