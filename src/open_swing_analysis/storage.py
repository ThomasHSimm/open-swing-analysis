"""Local JSON and Parquet persistence for the V0.1 data contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, TypeVar

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, TypeAdapter, ValidationError

from open_swing_analysis.contracts import (
    SCHEMA_VERSION,
    ContractModel,
    EventAnnotation,
    Frame,
    Identifier,
    ObservationLayer,
    PoseObservation,
    ShotOutcome,
    Swing,
    SwingSession,
    VideoAsset,
)


class DataContractError(ValueError):
    """Base error for incompatible or internally inconsistent stored data."""


class SchemaVersionError(DataContractError):
    """Raised when stored data use a contract version this code cannot read."""


class DataIntegrityError(DataContractError):
    """Raised when related records disagree or reference missing data."""


class ImmutableDataError(DataContractError):
    """Raised when a caller attempts to replace an immutable stored record."""


_ModelT = TypeVar("_ModelT", bound=ContractModel)
_IDENTIFIER = TypeAdapter(Identifier)

_COMMON_METADATA = {b"schema_version": SCHEMA_VERSION.encode("ascii")}

FRAME_ARROW_SCHEMA = pa.schema(
    [
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("swing_id", pa.string(), nullable=False),
        pa.field("video_asset_id", pa.string(), nullable=False),
        pa.field("frame_index", pa.int64(), nullable=False),
        pa.field("timestamp_s", pa.float64(), nullable=False),
        pa.field("decode_status", pa.string(), nullable=False),
        pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
    ],
    metadata={**_COMMON_METADATA, b"record_type": b"frame"},
)

POSE_ARROW_SCHEMA = pa.schema(
    [
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("swing_id", pa.string(), nullable=False),
        pa.field("frame_index", pa.int64(), nullable=False),
        pa.field("timestamp_s", pa.float64(), nullable=False),
        pa.field("landmark_name", pa.string(), nullable=False),
        pa.field("landmark_index", pa.int64(), nullable=False),
        pa.field("x", pa.float64()),
        pa.field("y", pa.float64()),
        pa.field("relative_z", pa.float64()),
        pa.field("visibility", pa.float64()),
        pa.field("confidence", pa.float64()),
        pa.field("coordinate_system", pa.string(), nullable=False),
        pa.field("relative_z_coordinate_system", pa.string()),
        pa.field("pose_model", pa.string(), nullable=False),
        pa.field("pose_model_version", pa.string(), nullable=False),
        pa.field("observation_status", pa.string(), nullable=False),
        pa.field("data_layer", pa.string(), nullable=False),
        pa.field("observation_revision", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("source_id", pa.string(), nullable=False),
        pa.field("source_revision", pa.string(), nullable=False),
        pa.field("recorded_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("derived_from_revision", pa.string()),
        pa.field("correction_reason", pa.string()),
    ],
    metadata={**_COMMON_METADATA, b"record_type": b"pose_observation"},
)


def _enum_values(value: Any) -> Any:
    """Recursively make Pydantic Python dumps suitable for Arrow."""
    if isinstance(value, dict):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_values(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


class LocalDataStore:
    """A filesystem store organized by session and swing.

    Every write creates a new immutable record. Pose revisions are physically
    separated by data layer, so filtered or corrected rows cannot replace raw rows.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @staticmethod
    def _id(value: str, label: str) -> str:
        try:
            return _IDENTIFIER.validate_python(value)
        except ValidationError as exc:
            raise DataIntegrityError(f"invalid {label}: {value!r}") from exc

    def _session_dir(self, session_id: str) -> Path:
        return self.root / "sessions" / self._id(session_id, "session_id")

    def _swing_dir(self, session_id: str, swing_id: str) -> Path:
        return self._session_dir(session_id) / "swings" / self._id(swing_id, "swing_id")

    @staticmethod
    def _write_new_text(path: Path, text: str) -> Path:
        if path.exists():
            raise ImmutableDataError(f"refusing to overwrite immutable record: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @classmethod
    def _write_model(cls, path: Path, model: BaseModel) -> Path:
        return cls._write_new_text(path, model.model_dump_json(indent=2) + "\n")

    @staticmethod
    def _read_model(path: Path, model_type: type[_ModelT]) -> _ModelT:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (json.JSONDecodeError, OSError) as exc:
            raise DataContractError(f"cannot read metadata JSON {path}: {exc}") from exc
        actual = payload.get("schema_version") if isinstance(payload, dict) else None
        if actual != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"incompatible schema version in {path}: expected {SCHEMA_VERSION!r}, "
                f"found {actual!r}"
            )
        try:
            return model_type.model_validate(payload)
        except ValidationError as exc:
            raise DataContractError(
                f"invalid {model_type.__name__} in {path}: {exc}"
            ) from exc

    def write_session(self, session: SwingSession) -> Path:
        return self._write_model(
            self._session_dir(session.session_id) / "session.json", session
        )

    def read_session(self, session_id: str) -> SwingSession:
        requested_id = self._id(session_id, "session_id")
        session = self._read_model(
            self._session_dir(requested_id) / "session.json", SwingSession
        )
        if session.session_id != requested_id:
            raise DataIntegrityError("session metadata does not match its storage path")
        return session

    def write_video_asset(self, session_id: str, asset: VideoAsset) -> Path:
        self.read_session(session_id)
        path = self._session_dir(session_id) / "assets" / f"{asset.asset_id}.json"
        return self._write_model(path, asset)

    def read_video_asset(self, session_id: str, asset_id: str) -> VideoAsset:
        requested_id = self._id(asset_id, "asset_id")
        path = self._session_dir(session_id) / "assets" / f"{requested_id}.json"
        asset = self._read_model(path, VideoAsset)
        if asset.asset_id != requested_id:
            raise DataIntegrityError(
                "video asset metadata does not match its storage path"
            )
        return asset

    def write_swing(self, swing: Swing) -> Path:
        self.read_session(swing.session_id)
        self.read_video_asset(swing.session_id, swing.video_asset_id)
        path = self._swing_dir(swing.session_id, swing.swing_id) / "swing.json"
        return self._write_model(path, swing)

    def read_swing(self, session_id: str, swing_id: str) -> Swing:
        requested_session = self._id(session_id, "session_id")
        requested_swing = self._id(swing_id, "swing_id")
        swing = self._read_model(
            self._swing_dir(requested_session, requested_swing) / "swing.json", Swing
        )
        if swing.session_id != requested_session or swing.swing_id != requested_swing:
            raise DataIntegrityError("swing metadata does not match its storage path")
        return swing

    @staticmethod
    def _rows(models: Iterable[BaseModel]) -> list[dict[str, Any]]:
        return [_enum_values(model.model_dump(mode="python")) for model in models]

    @staticmethod
    def _write_parquet(
        path: Path, rows: list[dict[str, Any]], schema: pa.Schema
    ) -> Path:
        if path.exists():
            raise ImmutableDataError(f"refusing to overwrite immutable table: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(table, path)
        return path

    @staticmethod
    def _read_table(
        path: Path, expected_schema: pa.Schema, record_type: str
    ) -> pa.Table:
        table = pq.read_table(path)
        metadata = table.schema.metadata or {}
        actual_version = metadata.get(b"schema_version", b"").decode("utf-8") or None
        if actual_version != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"incompatible schema version in {path}: expected {SCHEMA_VERSION!r}, "
                f"found {actual_version!r}"
            )
        actual_type = metadata.get(b"record_type", b"").decode("utf-8") or None
        if actual_type != record_type:
            raise DataContractError(
                f"unexpected Parquet record type in {path}: expected {record_type!r}, "
                f"found {actual_type!r}"
            )
        expected_metadata = expected_schema.metadata or {}
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise DataContractError(f"incompatible Arrow metadata in {path}")
        # Parquet normalizes the nested list child name from ``item`` to
        # ``element``. Physical fields still compare equal without metadata.
        if not table.schema.equals(expected_schema, check_metadata=False):
            raise DataContractError(f"incompatible Arrow schema in {path}")
        return table

    def write_frames(
        self, session_id: str, swing_id: str, frames: Iterable[Frame]
    ) -> Path:
        swing = self.read_swing(session_id, swing_id)
        records = list(frames)
        if not records:
            raise DataIntegrityError("frame table cannot be empty")
        previous_index = -1
        previous_timestamp = -1.0
        for frame in records:
            if (
                frame.swing_id != swing.swing_id
                or frame.video_asset_id != swing.video_asset_id
            ):
                raise DataIntegrityError(
                    "frame does not reference the requested swing and video asset"
                )
            if frame.frame_index <= previous_index:
                raise DataIntegrityError("frame indexes must be strictly increasing")
            if frame.timestamp_s <= previous_timestamp:
                raise DataIntegrityError("frame timestamps must be strictly increasing")
            previous_index = frame.frame_index
            previous_timestamp = frame.timestamp_s
        return self._write_parquet(
            self._swing_dir(session_id, swing_id) / "frames.parquet",
            self._rows(records),
            FRAME_ARROW_SCHEMA,
        )

    def read_frames(self, session_id: str, swing_id: str) -> list[Frame]:
        path = self._swing_dir(session_id, swing_id) / "frames.parquet"
        table = self._read_table(path, FRAME_ARROW_SCHEMA, "frame")
        try:
            records = [Frame.model_validate(row) for row in table.to_pylist()]
        except ValidationError as exc:
            raise DataContractError(f"invalid Frame row in {path}: {exc}") from exc
        swing = self.read_swing(session_id, swing_id)
        previous_index = -1
        previous_timestamp = -1.0
        for frame in records:
            if (
                frame.swing_id != swing.swing_id
                or frame.video_asset_id != swing.video_asset_id
            ):
                raise DataIntegrityError(f"invalid swing/video reference in {path}")
            if (
                frame.frame_index <= previous_index
                or frame.timestamp_s <= previous_timestamp
            ):
                raise DataIntegrityError(f"unordered frames in {path}")
            previous_index = frame.frame_index
            previous_timestamp = frame.timestamp_s
        return records

    def write_pose_observations(
        self,
        session_id: str,
        swing_id: str,
        observations: Iterable[PoseObservation],
    ) -> Path:
        records = list(observations)
        if not records:
            raise DataIntegrityError("pose observation table cannot be empty")
        swing = self.read_swing(session_id, swing_id)
        frames = {
            frame.frame_index: frame for frame in self.read_frames(session_id, swing_id)
        }
        layer = records[0].data_layer
        revision = records[0].observation_revision
        keys: set[tuple[int, int]] = set()
        previous_frame = -1
        for observation in records:
            if observation.swing_id != swing.swing_id:
                raise DataIntegrityError(
                    "pose observation references a different swing"
                )
            if (
                observation.data_layer != layer
                or observation.observation_revision != revision
            ):
                raise DataIntegrityError(
                    "one Parquet table must contain one layer and revision"
                )
            frame = frames.get(observation.frame_index)
            if frame is None:
                raise DataIntegrityError(
                    f"pose observation references absent frame {observation.frame_index}"
                )
            if abs(frame.timestamp_s - observation.timestamp_s) > 1e-9:
                raise DataIntegrityError(
                    f"pose timestamp does not match frame {observation.frame_index}"
                )
            key = (observation.frame_index, observation.landmark_index)
            if key in keys:
                raise DataIntegrityError(f"duplicate pose landmark reference {key}")
            if observation.frame_index < previous_frame:
                raise DataIntegrityError(
                    "pose observations must be ordered by frame index"
                )
            keys.add(key)
            previous_frame = observation.frame_index
        path = (
            self._swing_dir(session_id, swing_id)
            / "observations"
            / layer.value
            / f"{revision}.parquet"
        )
        metadata = {
            **(POSE_ARROW_SCHEMA.metadata or {}),
            b"observation_layer": layer.value.encode("utf-8"),
            b"observation_revision": revision.encode("utf-8"),
        }
        return self._write_parquet(
            path,
            self._rows(records),
            POSE_ARROW_SCHEMA.with_metadata(metadata),
        )

    def read_pose_observations(
        self,
        session_id: str,
        swing_id: str,
        layer: ObservationLayer,
        revision: str,
    ) -> list[PoseObservation]:
        revision = self._id(revision, "observation_revision")
        path = (
            self._swing_dir(session_id, swing_id)
            / "observations"
            / layer.value
            / f"{revision}.parquet"
        )
        metadata = {
            **(POSE_ARROW_SCHEMA.metadata or {}),
            b"observation_layer": layer.value.encode("utf-8"),
            b"observation_revision": revision.encode("utf-8"),
        }
        table = self._read_table(
            path,
            POSE_ARROW_SCHEMA.with_metadata(metadata),
            "pose_observation",
        )
        try:
            records = [PoseObservation.model_validate(row) for row in table.to_pylist()]
        except ValidationError as exc:
            raise DataContractError(
                f"invalid PoseObservation row in {path}: {exc}"
            ) from exc
        frame_lookup = {
            frame.frame_index: frame for frame in self.read_frames(session_id, swing_id)
        }
        seen: set[tuple[int, int]] = set()
        previous_frame = -1
        for observation in records:
            if (
                observation.swing_id != self._id(swing_id, "swing_id")
                or observation.data_layer != layer
                or observation.observation_revision != revision
            ):
                raise DataIntegrityError(
                    f"pose row does not match table path/metadata in {path}"
                )
            frame = frame_lookup.get(observation.frame_index)
            if frame is None or abs(frame.timestamp_s - observation.timestamp_s) > 1e-9:
                raise DataIntegrityError(f"invalid frame reference in {path}")
            key = (observation.frame_index, observation.landmark_index)
            if key in seen or observation.frame_index < previous_frame:
                raise DataIntegrityError(f"duplicate or unordered pose row in {path}")
            seen.add(key)
            previous_frame = observation.frame_index
        return records

    def write_event_annotation(
        self, session_id: str, annotation: EventAnnotation
    ) -> Path:
        self.read_swing(session_id, annotation.swing_id)
        if annotation.frame_index is not None:
            frames = {
                frame.frame_index: frame
                for frame in self.read_frames(session_id, annotation.swing_id)
            }
            frame = frames.get(annotation.frame_index)
            if (
                frame is None
                or abs(frame.timestamp_s - (annotation.timestamp_s or 0.0)) > 1e-9
            ):
                raise DataIntegrityError(
                    "event annotation has an invalid frame/timestamp reference"
                )
        if annotation.corrects_annotation_id is not None:
            original = self.read_event_annotation(
                session_id, annotation.swing_id, annotation.corrects_annotation_id
            )
            if (
                original.swing_id != annotation.swing_id
                or original.event_type != annotation.event_type
            ):
                raise DataIntegrityError(
                    "event correction must target the same swing and event type"
                )
        path = (
            self._swing_dir(session_id, annotation.swing_id)
            / "annotations"
            / "events"
            / f"{annotation.annotation_id}.json"
        )
        return self._write_model(path, annotation)

    def read_event_annotation(
        self, session_id: str, swing_id: str, annotation_id: str
    ) -> EventAnnotation:
        requested_swing = self._id(swing_id, "swing_id")
        requested_annotation = self._id(annotation_id, "annotation_id")
        path = (
            self._swing_dir(session_id, requested_swing)
            / "annotations"
            / "events"
            / f"{requested_annotation}.json"
        )
        annotation = self._read_model(path, EventAnnotation)
        if (
            annotation.swing_id != requested_swing
            or annotation.annotation_id != requested_annotation
        ):
            raise DataIntegrityError("event annotation does not match its storage path")
        return annotation

    def read_event_annotations(
        self, session_id: str, swing_id: str
    ) -> list[EventAnnotation]:
        directory = self._swing_dir(session_id, swing_id) / "annotations" / "events"
        if not directory.exists():
            return []
        return [
            self.read_event_annotation(session_id, swing_id, path.stem)
            for path in sorted(directory.glob("*.json"))
        ]

    def write_shot_outcome(self, session_id: str, outcome: ShotOutcome) -> Path:
        swing = self.read_swing(session_id, outcome.swing_id)
        if swing.shot_outcome_id != outcome.outcome_id:
            raise DataIntegrityError(
                "shot outcome ID does not match the swing reference"
            )
        path = (
            self._swing_dir(session_id, outcome.swing_id)
            / "outcomes"
            / f"{outcome.outcome_id}.json"
        )
        return self._write_model(path, outcome)

    def read_shot_outcome(
        self, session_id: str, swing_id: str, outcome_id: str
    ) -> ShotOutcome:
        requested_swing = self._id(swing_id, "swing_id")
        requested_outcome = self._id(outcome_id, "outcome_id")
        path = (
            self._swing_dir(session_id, requested_swing)
            / "outcomes"
            / f"{requested_outcome}.json"
        )
        outcome = self._read_model(path, ShotOutcome)
        if (
            outcome.swing_id != requested_swing
            or outcome.outcome_id != requested_outcome
        ):
            raise DataIntegrityError("shot outcome does not match its storage path")
        return outcome

    def tree(self) -> list[str]:
        """Return stable relative paths for diagnostics and examples."""
        if not self.root.exists():
            return []
        return sorted(
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
            if path.is_file()
        )
