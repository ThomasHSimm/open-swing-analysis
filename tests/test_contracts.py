from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from open_swing_analysis.contracts import (
    SCHEMA_VERSION,
    CameraView,
    EventAnnotation,
    EventSource,
    EventStatus,
    EventType,
    FrameRateMode,
    Handedness,
    ObservationLayer,
    ObservationSource,
    ObservationStatus,
    PoseObservation,
    ShotOutcome,
    SwingSession,
    VideoAsset,
)
from open_swing_analysis.synthetic import create_synthetic_dataset


def test_contracts_have_explicit_version_and_forbid_unknown_fields() -> None:
    dataset = create_synthetic_dataset()
    assert dataset.session.schema_version == SCHEMA_VERSION
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SwingSession.model_validate(
            {**dataset.session.model_dump(mode="python"), "unversioned_extension": True}
        )


def test_contract_models_are_frozen() -> None:
    session = create_synthetic_dataset().session
    with pytest.raises(ValidationError, match="frozen"):
        session.camera_view = CameraView.DOWN_THE_LINE  # type: ignore[misc]


def test_camera_view_and_handedness_are_explicit() -> None:
    session = create_synthetic_dataset().session
    assert session.camera_view is CameraView.FACE_ON
    assert session.golfer_handedness is Handedness.RIGHT


def test_variable_frame_rate_allows_null_nominal_fps() -> None:
    asset = create_synthetic_dataset().asset
    payload = asset.model_dump(mode="python")
    payload.update(frame_rate_mode=FrameRateMode.VARIABLE, nominal_fps=None)
    parsed = VideoAsset.model_validate(payload)
    assert parsed.nominal_fps is None


def test_constant_frame_rate_requires_nominal_fps() -> None:
    asset = create_synthetic_dataset().asset
    payload = asset.model_dump(mode="python")
    payload.update(frame_rate_mode=FrameRateMode.CONSTANT, nominal_fps=None)
    with pytest.raises(ValidationError, match="nominal_fps"):
        VideoAsset.model_validate(payload)


def test_invalid_normalized_coordinate_is_rejected() -> None:
    payload = create_synthetic_dataset().invalid_observation_payloads[0]
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        PoseObservation.model_validate(payload)


def test_missing_observation_uses_null_not_zero() -> None:
    raw = create_synthetic_dataset().pose_observations["swing-synthetic-001"][0]
    payload = raw.model_dump(mode="python")
    payload.update(
        x=None,
        y=None,
        relative_z=None,
        relative_z_coordinate_system=None,
        visibility=None,
        confidence=None,
        observation_status=ObservationStatus.NOT_OBSERVED,
    )
    missing = PoseObservation.model_validate(payload)
    assert missing.x is None and missing.y is None
    assert missing.visibility is None and missing.confidence is None


def test_missing_observation_cannot_hide_coordinates() -> None:
    raw = create_synthetic_dataset().pose_observations["swing-synthetic-001"][0]
    payload = raw.model_dump(mode="python")
    payload["observation_status"] = ObservationStatus.NOT_OBSERVED
    with pytest.raises(ValidationError, match="must store coordinates as null"):
        PoseObservation.model_validate(payload)


def test_visibility_and_confidence_are_independent() -> None:
    low = next(
        row
        for row in create_synthetic_dataset().pose_observations["swing-synthetic-001"]
        if row.observation_status is ObservationStatus.LOW_CONFIDENCE
    )
    assert low.visibility == pytest.approx(0.42)
    assert low.confidence == pytest.approx(0.31)
    assert low.visibility != low.confidence


def test_relative_z_is_not_presented_as_metric_3d() -> None:
    observation = create_synthetic_dataset().pose_observations["swing-synthetic-001"][0]
    assert observation.coordinate_system == "image_normalized_top_left"
    assert observation.relative_z_coordinate_system == "model_relative_depth"


def test_raw_observation_cannot_claim_manual_or_derived_provenance() -> None:
    raw = create_synthetic_dataset().pose_observations["swing-synthetic-001"][0]
    payload = raw.model_dump(mode="python")
    payload.update(source=ObservationSource.MANUAL, derived_from_revision="earlier")
    with pytest.raises(ValidationError, match="raw observations"):
        PoseObservation.model_validate(payload)


def test_corrected_observation_requires_audit_provenance() -> None:
    raw = create_synthetic_dataset().pose_observations["swing-synthetic-001"][0]
    payload = raw.model_dump(mode="python")
    payload.update(
        data_layer=ObservationLayer.CORRECTED,
        observation_revision="manual-correction-001",
        source=ObservationSource.MANUAL,
        source_id="annotator-001",
        source_revision="guide-1.0",
        derived_from_revision=raw.observation_revision,
        correction_reason=None,
    )
    with pytest.raises(ValidationError, match="correction_reason"):
        PoseObservation.model_validate(payload)


def _event_payload() -> dict:
    return {
        "annotation_id": "event-test-001",
        "swing_id": "swing-test-001",
        "event_type": EventType.TOP,
        "frame_index": 10,
        "timestamp_s": 0.34,
        "source": EventSource.MODEL,
        "status": EventStatus.UNCERTAIN,
        "confidence": 0.7,
        "uncertainty_start_s": 0.30,
        "uncertainty_end_s": 0.38,
        "source_id": "event-model",
        "source_revision": "model-1.0",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def test_event_uncertainty_must_be_ordered_and_contain_event() -> None:
    payload = _event_payload()
    payload.update(uncertainty_start_s=0.36, uncertainty_end_s=0.32)
    with pytest.raises(ValidationError, match="cannot exceed"):
        EventAnnotation.model_validate(payload)

    payload = _event_payload()
    payload.update(uncertainty_start_s=0.35, uncertainty_end_s=0.40)
    with pytest.raises(ValidationError, match="must contain"):
        EventAnnotation.model_validate(payload)


def test_not_observed_impact_has_no_synthetic_location() -> None:
    event = create_synthetic_dataset().event_annotations[-1]
    assert event.event_type is EventType.IMPACT
    assert event.status is EventStatus.NOT_OBSERVED
    assert event.frame_index is None and event.timestamp_s is None


def test_only_manual_events_can_correct_prior_annotations() -> None:
    payload = _event_payload()
    payload["corrects_annotation_id"] = "event-original"
    with pytest.raises(ValidationError, match="only manual"):
        EventAnnotation.model_validate(payload)


def test_distance_unit_is_required_only_for_present_values() -> None:
    with pytest.raises(ValidationError, match="distance_unit"):
        ShotOutcome(
            outcome_id="outcome-test",
            swing_id="swing-test",
            club="driver",
            carry_distance=250.0,
        )

    outcome = ShotOutcome(
        outcome_id="outcome-test",
        swing_id="swing-test",
        club="driver",
    )
    assert outcome.carry_distance is None
    assert outcome.distance_unit is None
