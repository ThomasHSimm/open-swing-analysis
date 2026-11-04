import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from open_swing_analysis.contracts import (
    ObservationLayer,
    ObservationSource,
    PoseObservation,
)
from open_swing_analysis.storage import (
    DataContractError,
    DataIntegrityError,
    ImmutableDataError,
    LocalDataStore,
    SchemaVersionError,
)
from open_swing_analysis.synthetic import (
    create_synthetic_dataset,
    write_synthetic_dataset,
)


@pytest.fixture
def stored_dataset(tmp_path: Path):
    store = LocalDataStore(tmp_path / "contract-store")
    dataset = write_synthetic_dataset(store)
    return store, dataset


def test_json_and_parquet_round_trip(stored_dataset) -> None:
    store, dataset = stored_dataset
    session_id = dataset.session.session_id
    swing = dataset.swings[0]

    assert store.read_session(session_id) == dataset.session
    assert store.read_video_asset(session_id, dataset.asset.asset_id) == dataset.asset
    assert store.read_swing(session_id, swing.swing_id) == swing
    assert store.read_frames(session_id, swing.swing_id) == list(
        dataset.frames[swing.swing_id]
    )
    assert store.read_pose_observations(
        session_id,
        swing.swing_id,
        ObservationLayer.RAW,
        "raw-pose-run-001",
    ) == list(dataset.pose_observations[swing.swing_id])


def test_nulls_survive_parquet_round_trip(stored_dataset) -> None:
    store, dataset = stored_dataset
    rows = store.read_pose_observations(
        dataset.session.session_id,
        dataset.swings[0].swing_id,
        ObservationLayer.RAW,
        "raw-pose-run-001",
    )
    invalid = next(row for row in rows if row.observation_status.value == "invalid")
    assert invalid.x is None
    assert invalid.y is None
    assert invalid.visibility is None
    assert invalid.confidence is None


def test_irregular_original_timestamps_are_preserved(stored_dataset) -> None:
    store, dataset = stored_dataset
    swing_id = dataset.swings[0].swing_id
    timestamps = [
        frame.timestamp_s
        for frame in store.read_frames(dataset.session.session_id, swing_id)
    ]
    assert timestamps == [0.0, 0.033, 0.071, 0.102, 0.151, 0.184]
    assert len({round(b - a, 3) for a, b in zip(timestamps, timestamps[1:])}) > 1


def _metadata_only_store(tmp_path: Path):
    store = LocalDataStore(tmp_path / "metadata-only")
    dataset = create_synthetic_dataset()
    store.write_session(dataset.session)
    store.write_video_asset(dataset.session.session_id, dataset.asset)
    store.write_swing(dataset.swings[0])
    return store, dataset


def test_frame_timestamps_must_be_ordered(tmp_path: Path) -> None:
    store, dataset = _metadata_only_store(tmp_path)
    frames = list(dataset.frames[dataset.swings[0].swing_id])
    frames[2] = frames[2].model_copy(update={"timestamp_s": frames[1].timestamp_s})
    with pytest.raises(
        DataIntegrityError, match="timestamps must be strictly increasing"
    ):
        store.write_frames(
            dataset.session.session_id, dataset.swings[0].swing_id, frames
        )


def test_pose_frame_reference_and_timestamp_are_validated(stored_dataset) -> None:
    store, dataset = stored_dataset
    raw = dataset.pose_observations[dataset.swings[0].swing_id][0]
    bad_frame = raw.model_copy(
        update={
            "frame_index": 999,
            "observation_revision": "bad-frame-reference",
        }
    )
    with pytest.raises(DataIntegrityError, match="absent frame"):
        store.write_pose_observations(
            dataset.session.session_id, dataset.swings[0].swing_id, [bad_frame]
        )

    bad_timestamp = raw.model_copy(
        update={
            "timestamp_s": raw.timestamp_s + 0.001,
            "observation_revision": "bad-timestamp-reference",
        }
    )
    with pytest.raises(DataIntegrityError, match="timestamp does not match"):
        store.write_pose_observations(
            dataset.session.session_id, dataset.swings[0].swing_id, [bad_timestamp]
        )


def test_frame_references_are_revalidated_on_read(stored_dataset) -> None:
    store, dataset = stored_dataset
    swing_id = dataset.swings[0].swing_id
    path = (
        store.root
        / "sessions"
        / dataset.session.session_id
        / "swings"
        / swing_id
        / "frames.parquet"
    )
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[0]["swing_id"] = "swing-other"
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)

    with pytest.raises(DataIntegrityError, match="invalid swing/video reference"):
        store.read_frames(dataset.session.session_id, swing_id)


def test_pose_detection_is_not_required_for_every_frame(stored_dataset) -> None:
    store, dataset = stored_dataset
    session_id = dataset.session.session_id
    swing_id = dataset.swings[0].swing_id
    frame_indexes = {
        frame.frame_index for frame in store.read_frames(session_id, swing_id)
    }
    observed_indexes = {
        row.frame_index
        for row in store.read_pose_observations(
            session_id, swing_id, ObservationLayer.RAW, "raw-pose-run-001"
        )
    }
    assert frame_indexes - observed_indexes == {2}


def test_raw_and_corrected_observations_are_physically_separate(stored_dataset) -> None:
    store, dataset = stored_dataset
    session_id = dataset.session.session_id
    swing_id = dataset.swings[0].swing_id
    raw = dataset.pose_observations[swing_id][0]
    payload = raw.model_dump(mode="python")
    payload.update(
        x=0.44,
        data_layer=ObservationLayer.CORRECTED,
        observation_revision="manual-pose-correction-001",
        source=ObservationSource.MANUAL,
        source_id="annotator-synthetic-001",
        source_revision="annotation-guide-1.0",
        derived_from_revision=raw.observation_revision,
        correction_reason="Corrected synthetic wrist location.",
    )
    corrected = PoseObservation.model_validate(payload)
    corrected_path = store.write_pose_observations(session_id, swing_id, [corrected])

    assert "/corrected/" in corrected_path.as_posix()
    reread_raw = store.read_pose_observations(
        session_id, swing_id, ObservationLayer.RAW, raw.observation_revision
    )[0]
    reread_corrected = store.read_pose_observations(
        session_id,
        swing_id,
        ObservationLayer.CORRECTED,
        corrected.observation_revision,
    )[0]
    assert reread_raw.x == raw.x
    assert reread_corrected.x == 0.44
    assert reread_corrected.derived_from_revision == raw.observation_revision


def test_raw_tables_are_immutable(stored_dataset) -> None:
    store, dataset = stored_dataset
    swing_id = dataset.swings[0].swing_id
    with pytest.raises(ImmutableDataError, match="refusing to overwrite"):
        store.write_pose_observations(
            dataset.session.session_id,
            swing_id,
            dataset.pose_observations[swing_id],
        )


def test_manual_event_correction_preserves_original(stored_dataset) -> None:
    store, dataset = stored_dataset
    session_id = dataset.session.session_id
    swing_id = dataset.swings[0].swing_id
    model_event = store.read_event_annotation(
        session_id, swing_id, "event-impact-model-001"
    )
    correction = store.read_event_annotation(
        session_id, swing_id, "event-impact-manual-001"
    )

    assert model_event.frame_index == 4
    assert correction.frame_index == 3
    assert correction.corrects_annotation_id == model_event.annotation_id
    assert correction.source.value == "manual"


def test_json_schema_version_is_checked_before_model_validation(stored_dataset) -> None:
    store, dataset = stored_dataset
    path = store.root / "sessions" / dataset.session.session_id / "session.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "99.0.0"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SchemaVersionError, match="expected '0.1.0'.*'99.0.0'"):
        store.read_session(dataset.session.session_id)


def test_parquet_schema_version_is_checked(stored_dataset) -> None:
    store, dataset = stored_dataset
    swing_id = dataset.swings[0].swing_id
    path = (
        store.root
        / "sessions"
        / dataset.session.session_id
        / "swings"
        / swing_id
        / "frames.parquet"
    )
    table = pq.read_table(path)
    metadata = {**(table.schema.metadata or {}), b"schema_version": b"99.0.0"}
    pq.write_table(table.replace_schema_metadata(metadata), path)

    with pytest.raises(SchemaVersionError, match="99.0.0"):
        store.read_frames(dataset.session.session_id, swing_id)


def test_invalid_arrow_shape_has_useful_error(stored_dataset) -> None:
    store, dataset = stored_dataset
    swing_id = dataset.swings[0].swing_id
    path = (
        store.root
        / "sessions"
        / dataset.session.session_id
        / "swings"
        / swing_id
        / "frames.parquet"
    )
    table = pq.read_table(path).drop(["quality_flags"])
    pq.write_table(table, path)
    with pytest.raises(DataContractError, match="Arrow schema"):
        store.read_frames(dataset.session.session_id, swing_id)


def test_storage_layout_is_session_and_swing_scoped(stored_dataset) -> None:
    store, dataset = stored_dataset
    tree = store.tree()
    prefix = f"sessions/{dataset.session.session_id}/swings/"
    assert all(path.startswith("sessions/") for path in tree)
    assert any(path.startswith(prefix + dataset.swings[0].swing_id) for path in tree)
    assert any(path.startswith(prefix + dataset.swings[1].swing_id) for path in tree)
