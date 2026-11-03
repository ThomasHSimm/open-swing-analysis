import pytest
from pydantic import ValidationError

from open_swing_analysis.contracts import (
    EventStatus,
    EventType,
    ObservationStatus,
    PoseObservation,
)
from open_swing_analysis.synthetic import create_synthetic_dataset


def test_synthetic_dataset_contains_required_edge_cases() -> None:
    dataset = create_synthetic_dataset()
    assert len(dataset.swings) == 2
    assert all(
        swing.session_id == dataset.session.session_id for swing in dataset.swings
    )

    first_swing = dataset.swings[0].swing_id
    rows = dataset.pose_observations[first_swing]
    assert any(
        row.observation_status is ObservationStatus.LOW_CONFIDENCE for row in rows
    )
    assert any(row.observation_status is ObservationStatus.INVALID for row in rows)
    assert 2 not in {row.frame_index for row in rows}

    impacts = [
        event
        for event in dataset.event_annotations
        if event.event_type is EventType.IMPACT
    ]
    assert any(event.corrects_annotation_id is not None for event in impacts)
    assert any(event.status is EventStatus.NOT_OBSERVED for event in impacts)


def test_synthetic_invalid_payload_is_actually_invalid() -> None:
    payload = create_synthetic_dataset().invalid_observation_payloads[0]
    with pytest.raises(ValidationError):
        PoseObservation.model_validate(payload)
