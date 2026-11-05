"""Versioned, immutable data contracts for golf-swing observations."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)


SCHEMA_VERSION = "0.1.0"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
# Normalized image coordinates are not probabilities: pose models can return
# values outside the image when a landmark is just beyond a frame boundary.
NormalizedImageCoordinate = float


class CameraView(str, Enum):
    FACE_ON = "face_on"
    DOWN_THE_LINE = "down_the_line"
    UNKNOWN = "unknown"


class Handedness(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"


class FrameRateMode(str, Enum):
    CONSTANT = "constant"
    VARIABLE = "variable"
    UNKNOWN = "unknown"


class DecodeStatus(str, Enum):
    DECODED = "decoded"
    MISSING = "missing"
    CORRUPT = "corrupt"


class FrameQualityFlag(str, Enum):
    BLUR = "blur"
    DARK = "dark"
    OVEREXPOSED = "overexposed"
    OCCLUDED = "occluded"
    PARTIAL_SUBJECT = "partial_subject"
    DUPLICATE = "duplicate"


class ObservationStatus(str, Enum):
    OBSERVED = "observed"
    LOW_CONFIDENCE = "low_confidence"
    NOT_OBSERVED = "not_observed"
    INVALID = "invalid"


class ObservationLayer(str, Enum):
    RAW = "raw"
    FILTERED = "filtered"
    CORRECTED = "corrected"


class ObservationSource(str, Enum):
    MODEL = "model"
    MANUAL = "manual"
    FILTER = "filter"
    INTERPOLATION = "interpolation"


class EventSource(str, Enum):
    MANUAL = "manual"
    MODEL = "model"
    HEURISTIC = "heuristic"


class EventStatus(str, Enum):
    OBSERVED = "observed"
    UNCERTAIN = "uncertain"
    NOT_OBSERVED = "not_observed"
    INVALID = "invalid"


class EventType(str, Enum):
    ADDRESS = "address"
    TAKEAWAY = "takeaway"
    BACKSWING_START = "backswing_start"
    TOP = "top"
    DOWNSWING = "downswing"
    IMPACT = "impact"
    RELEASE = "release"
    FINISH = "finish"
    OTHER = "other"


class DistanceUnit(str, Enum):
    METRES = "metres"
    YARDS = "yards"


class ContractModel(BaseModel):
    """Strict frozen base for records written to a data-contract store."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        use_enum_values=False,
    )

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION


class VideoAsset(ContractModel):
    """Immutable identity and capture facts for one source video."""

    asset_id: Identifier
    source_filename: NonEmptyString
    source_path: NonEmptyString
    sha256: Sha256
    width_px: Annotated[int, Field(gt=0)]
    height_px: Annotated[int, Field(gt=0)]
    nominal_fps: Annotated[float, Field(gt=0)] | None
    frame_rate_mode: FrameRateMode
    duration_s: Annotated[float, Field(ge=0)]
    frame_count: Annotated[int, Field(ge=0)]
    codec: NonEmptyString | None = None
    acquisition_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    source_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_constant_rate(self) -> VideoAsset:
        if self.frame_rate_mode == FrameRateMode.CONSTANT and self.nominal_fps is None:
            raise ValueError("nominal_fps is required for constant frame-rate video")
        return self


class SwingSession(ContractModel):
    """Recording context shared by one or more swings."""

    session_id: Identifier
    subject_id: Identifier
    recording_date: date
    camera_view: CameraView
    golfer_handedness: Handedness
    camera_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    capture_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class Swing(ContractModel):
    """A swing within a session and its source-video relationship."""

    swing_id: Identifier
    session_id: Identifier
    video_asset_id: Identifier
    club_type: NonEmptyString
    shot_outcome_id: Identifier | None = None


class Frame(ContractModel):
    """One decoded or attempted source frame with its original timestamp."""

    swing_id: Identifier
    video_asset_id: Identifier
    frame_index: Annotated[int, Field(ge=0)]
    timestamp_s: Annotated[float, Field(ge=0)]
    decode_status: DecodeStatus
    quality_flags: tuple[FrameQualityFlag, ...] = ()

    @model_validator(mode="after")
    def unique_quality_flags(self) -> Frame:
        if len(self.quality_flags) != len(set(self.quality_flags)):
            raise ValueError("quality_flags must not contain duplicates")
        return self


class PoseObservation(ContractModel):
    """Long-form pose landmark observation in explicit image coordinates."""

    swing_id: Identifier
    frame_index: Annotated[int, Field(ge=0)]
    timestamp_s: Annotated[float, Field(ge=0)]
    landmark_name: NonEmptyString
    landmark_index: Annotated[int, Field(ge=0)]
    x: NormalizedImageCoordinate | None
    y: NormalizedImageCoordinate | None
    relative_z: float | None = None
    visibility: Probability | None = None
    confidence: Probability | None = None
    coordinate_system: Literal["image_normalized_top_left"] = (
        "image_normalized_top_left"
    )
    relative_z_coordinate_system: Literal["model_relative_depth"] | None = None
    pose_model: NonEmptyString
    pose_model_version: NonEmptyString
    observation_status: ObservationStatus
    data_layer: ObservationLayer
    observation_revision: Identifier
    source: ObservationSource
    source_id: Identifier
    source_revision: Identifier
    recorded_at: datetime
    derived_from_revision: Identifier | None = None
    correction_reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> PoseObservation:
        has_xy = self.x is not None and self.y is not None
        if (self.x is None) != (self.y is None):
            raise ValueError("x and y must either both be present or both be null")
        if (
            self.observation_status
            in {
                ObservationStatus.OBSERVED,
                ObservationStatus.LOW_CONFIDENCE,
            }
            and not has_xy
        ):
            raise ValueError("observed and low-confidence rows require x and y")
        if self.observation_status in {
            ObservationStatus.NOT_OBSERVED,
            ObservationStatus.INVALID,
        } and any(
            value is not None
            for value in (
                self.x,
                self.y,
                self.relative_z,
                self.visibility,
                self.confidence,
            )
        ):
            raise ValueError(
                "not-observed and invalid rows must store coordinates as null"
            )
        if self.relative_z is not None and self.relative_z_coordinate_system is None:
            raise ValueError(
                "relative_z_coordinate_system is required when relative_z is present"
            )
        if self.relative_z is None and self.relative_z_coordinate_system is not None:
            raise ValueError("relative_z_coordinate_system requires relative_z")
        if self.data_layer == ObservationLayer.RAW:
            if (
                self.derived_from_revision is not None
                or self.correction_reason is not None
            ):
                raise ValueError(
                    "raw observations cannot derive from or correct another revision"
                )
            if self.source != ObservationSource.MODEL:
                raise ValueError("raw pose observations must have model provenance")
        else:
            if self.derived_from_revision is None:
                raise ValueError(
                    "filtered/corrected observations require derived_from_revision"
                )
        if self.data_layer == ObservationLayer.CORRECTED:
            if self.source != ObservationSource.MANUAL:
                raise ValueError("corrected observations require manual provenance")
            if self.correction_reason is None:
                raise ValueError("corrected observations require correction_reason")
        return self


class EventAnnotation(ContractModel):
    """An additive event label or estimate; corrections link to prior records."""

    annotation_id: Identifier
    swing_id: Identifier
    event_type: EventType
    frame_index: Annotated[int, Field(ge=0)] | None
    timestamp_s: Annotated[float, Field(ge=0)] | None
    source: EventSource
    status: EventStatus
    confidence: Probability | None = None
    uncertainty_start_s: Annotated[float, Field(ge=0)] | None = None
    uncertainty_end_s: Annotated[float, Field(ge=0)] | None = None
    source_id: Identifier
    source_revision: Identifier
    created_at: datetime
    corrects_annotation_id: Identifier | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_event(self) -> EventAnnotation:
        located = self.frame_index is not None and self.timestamp_s is not None
        if (self.frame_index is None) != (self.timestamp_s is None):
            raise ValueError(
                "frame_index and timestamp_s must both be present or both be null"
            )
        if self.status in {EventStatus.OBSERVED, EventStatus.UNCERTAIN} and not located:
            raise ValueError(
                "observed and uncertain events require frame and timestamp"
            )
        if self.status in {EventStatus.NOT_OBSERVED, EventStatus.INVALID} and located:
            raise ValueError(
                "not-observed and invalid events cannot claim a frame or timestamp"
            )
        interval = (self.uncertainty_start_s, self.uncertainty_end_s)
        if (interval[0] is None) != (interval[1] is None):
            raise ValueError("uncertainty interval requires both start and end")
        if interval[0] is not None:
            assert interval[1] is not None
            if interval[0] > interval[1]:
                raise ValueError("uncertainty_start_s cannot exceed uncertainty_end_s")
            if (
                self.timestamp_s is None
                or not interval[0] <= self.timestamp_s <= interval[1]
            ):
                raise ValueError("uncertainty interval must contain timestamp_s")
        if (
            self.corrects_annotation_id is not None
            and self.source != EventSource.MANUAL
        ):
            raise ValueError("only manual annotations may correct another annotation")
        return self


class ShotOutcome(ContractModel):
    """Optional manually supplied outcome associated with one swing."""

    outcome_id: Identifier
    swing_id: Identifier
    club: NonEmptyString
    strike_quality: NonEmptyString | None = None
    strike_location: NonEmptyString | None = None
    start_direction: NonEmptyString | None = None
    curvature: NonEmptyString | None = None
    carry_distance: Annotated[float, Field(ge=0)] | None = None
    total_distance: Annotated[float, Field(ge=0)] | None = None
    distance_unit: DistanceUnit | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_distances(self) -> ShotOutcome:
        has_distance = (
            self.carry_distance is not None or self.total_distance is not None
        )
        if has_distance != (self.distance_unit is not None):
            raise ValueError(
                "distance_unit is required exactly when a distance is present"
            )
        return self
