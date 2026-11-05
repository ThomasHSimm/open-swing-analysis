"""Small deterministic synthetic data for contract examples and tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from open_swing_analysis.contracts import (
    CameraView,
    DecodeStatus,
    DistanceUnit,
    EventAnnotation,
    EventSource,
    EventStatus,
    EventType,
    Frame,
    FrameQualityFlag,
    FrameRateMode,
    Handedness,
    ObservationLayer,
    ObservationSource,
    ObservationStatus,
    PoseObservation,
    ShotOutcome,
    Swing,
    SwingSession,
    VideoAsset,
)
from open_swing_analysis.storage import LocalDataStore


@dataclass(frozen=True)
class SyntheticDataset:
    """A complete in-memory fixture with two swings and known edge cases."""

    session: SwingSession
    asset: VideoAsset
    swings: tuple[Swing, ...]
    frames: dict[str, tuple[Frame, ...]]
    pose_observations: dict[str, tuple[PoseObservation, ...]]
    event_annotations: tuple[EventAnnotation, ...]
    shot_outcomes: tuple[ShotOutcome, ...]
    invalid_observation_payloads: tuple[dict[str, Any], ...]


def create_synthetic_dataset() -> SyntheticDataset:
    """Create two synthetic swings without loading or generating video media."""
    recorded_at = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    session = SwingSession(
        session_id="session-synthetic-001",
        subject_id="subject-synthetic-001",
        recording_date=date(2026, 1, 15),
        camera_view=CameraView.FACE_ON,
        golfer_handedness=Handedness.RIGHT,
        camera_metadata={"device": "synthetic-camera", "orientation": "landscape"},
        capture_metadata={"fixture": True, "redistribution": "CC0 synthetic"},
    )
    asset = VideoAsset(
        asset_id="asset-synthetic-001",
        source_filename="synthetic-session.mp4",
        source_path="synthetic/synthetic-session.mp4",
        sha256="a" * 64,
        width_px=1280,
        height_px=720,
        nominal_fps=30.0,
        frame_rate_mode=FrameRateMode.VARIABLE,
        duration_s=0.41,
        frame_count=12,
        codec="synthetic",
        acquisition_metadata={"created_by": "open_swing_analysis.synthetic"},
        source_metadata={"contains_real_person": False, "redistributable": True},
    )
    swings = (
        Swing(
            swing_id="swing-synthetic-001",
            session_id=session.session_id,
            video_asset_id=asset.asset_id,
            club_type="7-iron",
            shot_outcome_id="outcome-synthetic-001",
        ),
        Swing(
            swing_id="swing-synthetic-002",
            session_id=session.session_id,
            video_asset_id=asset.asset_id,
            club_type="driver",
        ),
    )
    timestamps = {
        swings[0].swing_id: (0.000, 0.033, 0.071, 0.102, 0.151, 0.184),
        swings[1].swing_id: (0.220, 0.253, 0.289, 0.326, 0.365, 0.401),
    }
    frames: dict[str, tuple[Frame, ...]] = {}
    for offset, swing in zip((0, 6), swings, strict=True):
        frames[swing.swing_id] = tuple(
            Frame(
                swing_id=swing.swing_id,
                video_asset_id=asset.asset_id,
                frame_index=offset + local_index,
                timestamp_s=timestamp,
                decode_status=DecodeStatus.DECODED,
                quality_flags=(FrameQualityFlag.BLUR,) if local_index == 3 else (),
            )
            for local_index, timestamp in enumerate(timestamps[swing.swing_id])
        )

    pose_observations: dict[str, tuple[PoseObservation, ...]] = {}
    for swing in swings:
        rows: list[PoseObservation] = []
        for local_index, frame in enumerate(frames[swing.swing_id]):
            # Frame 2 of the first swing deliberately has no pose rows.
            if swing == swings[0] and local_index == 2:
                continue
            for landmark_index, landmark_name, x_offset in (
                (15, "left_wrist", -0.035),
                (16, "right_wrist", 0.035),
            ):
                low_confidence = local_index == 3
                rows.append(
                    PoseObservation(
                        swing_id=swing.swing_id,
                        frame_index=frame.frame_index,
                        timestamp_s=frame.timestamp_s,
                        landmark_name=landmark_name,
                        landmark_index=landmark_index,
                        x=0.50 + x_offset + 0.015 * local_index,
                        y=(0.72, 0.54, 0.32, 0.45, 0.68, 0.58)[local_index],
                        relative_z=-0.08 + 0.01 * local_index,
                        relative_z_coordinate_system="model_relative_depth",
                        visibility=0.42 if low_confidence else 0.96,
                        confidence=0.31 if low_confidence else 0.93,
                        pose_model="synthetic-pose",
                        pose_model_version="1.0",
                        observation_status=(
                            ObservationStatus.LOW_CONFIDENCE
                            if low_confidence
                            else ObservationStatus.OBSERVED
                        ),
                        data_layer=ObservationLayer.RAW,
                        observation_revision="raw-pose-run-001",
                        source=ObservationSource.MODEL,
                        source_id="synthetic-pose",
                        source_revision="model-1.0-code-fixture",
                        recorded_at=recorded_at,
                    )
                )
        # Explicit invalid-status row: invalid numeric outputs are represented by nulls.
        last_frame = frames[swing.swing_id][-1]
        rows.append(
            PoseObservation(
                swing_id=swing.swing_id,
                frame_index=last_frame.frame_index,
                timestamp_s=last_frame.timestamp_s,
                landmark_name="synthetic_invalid_landmark",
                landmark_index=99,
                x=None,
                y=None,
                pose_model="synthetic-pose",
                pose_model_version="1.0",
                observation_status=ObservationStatus.INVALID,
                data_layer=ObservationLayer.RAW,
                observation_revision="raw-pose-run-001",
                source=ObservationSource.MODEL,
                source_id="synthetic-pose",
                source_revision="model-1.0-code-fixture",
                recorded_at=recorded_at,
            )
        )
        pose_observations[swing.swing_id] = tuple(rows)

    first_frames = frames[swings[0].swing_id]
    model_impact = EventAnnotation(
        annotation_id="event-impact-model-001",
        swing_id=swings[0].swing_id,
        event_type=EventType.IMPACT,
        frame_index=first_frames[4].frame_index,
        timestamp_s=first_frames[4].timestamp_s,
        source=EventSource.MODEL,
        status=EventStatus.UNCERTAIN,
        confidence=0.62,
        uncertainty_start_s=first_frames[3].timestamp_s,
        uncertainty_end_s=first_frames[4].timestamp_s,
        source_id="synthetic-event-model",
        source_revision="event-model-0.1",
        created_at=recorded_at,
    )
    corrected_impact = EventAnnotation(
        annotation_id="event-impact-manual-001",
        swing_id=swings[0].swing_id,
        event_type=EventType.IMPACT,
        frame_index=first_frames[3].frame_index,
        timestamp_s=first_frames[3].timestamp_s,
        source=EventSource.MANUAL,
        status=EventStatus.OBSERVED,
        source_id="annotator-synthetic-001",
        source_revision="annotation-guide-1.0",
        created_at=recorded_at,
        corrects_annotation_id=model_impact.annotation_id,
        notes="Synthetic manual correction retained beside the model estimate.",
    )
    event_annotations = (
        EventAnnotation(
            annotation_id="event-address-manual-001",
            swing_id=swings[0].swing_id,
            event_type=EventType.ADDRESS,
            frame_index=first_frames[0].frame_index,
            timestamp_s=first_frames[0].timestamp_s,
            source=EventSource.MANUAL,
            status=EventStatus.OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
        ),
        EventAnnotation(
            annotation_id="event-takeaway-manual-001",
            swing_id=swings[0].swing_id,
            event_type=EventType.TAKEAWAY,
            frame_index=first_frames[1].frame_index,
            timestamp_s=first_frames[1].timestamp_s,
            source=EventSource.MANUAL,
            status=EventStatus.OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
        ),
        EventAnnotation(
            annotation_id="event-backswing-start-manual-001",
            swing_id=swings[0].swing_id,
            event_type=EventType.BACKSWING_START,
            frame_index=first_frames[1].frame_index,
            timestamp_s=first_frames[1].timestamp_s,
            source=EventSource.MANUAL,
            status=EventStatus.OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
        ),
        EventAnnotation(
            annotation_id="event-top-manual-001",
            swing_id=swings[0].swing_id,
            event_type=EventType.TOP,
            frame_index=first_frames[1].frame_index,
            timestamp_s=first_frames[1].timestamp_s,
            source=EventSource.MANUAL,
            status=EventStatus.OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
        ),
        model_impact,
        corrected_impact,
        EventAnnotation(
            annotation_id="event-downswing-manual-001",
            swing_id=swings[0].swing_id,
            event_type=EventType.DOWNSWING,
            frame_index=first_frames[3].frame_index,
            timestamp_s=first_frames[3].timestamp_s,
            source=EventSource.MANUAL,
            status=EventStatus.OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
        ),
        EventAnnotation(
            annotation_id="event-release-manual-001",
            swing_id=swings[0].swing_id,
            event_type=EventType.RELEASE,
            frame_index=first_frames[4].frame_index,
            timestamp_s=first_frames[4].timestamp_s,
            source=EventSource.MANUAL,
            status=EventStatus.OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
        ),
        EventAnnotation(
            annotation_id="event-finish-manual-001",
            swing_id=swings[0].swing_id,
            event_type=EventType.FINISH,
            frame_index=first_frames[5].frame_index,
            timestamp_s=first_frames[5].timestamp_s,
            source=EventSource.MANUAL,
            status=EventStatus.OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
        ),
        EventAnnotation(
            annotation_id="event-impact-not-observed-002",
            swing_id=swings[1].swing_id,
            event_type=EventType.IMPACT,
            frame_index=None,
            timestamp_s=None,
            source=EventSource.MANUAL,
            status=EventStatus.NOT_OBSERVED,
            source_id="annotator-synthetic-001",
            source_revision="annotation-guide-1.0",
            created_at=recorded_at,
            notes="Impact is outside the synthetic clip.",
        ),
    )
    shot_outcomes = (
        ShotOutcome(
            outcome_id="outcome-synthetic-001",
            swing_id=swings[0].swing_id,
            club="7-iron",
            strike_quality="solid",
            strike_location="centre",
            start_direction="slightly_right",
            curvature="draw",
            carry_distance=145.0,
            total_distance=None,
            distance_unit=DistanceUnit.YARDS,
            notes="Synthetic label, not a measured shot.",
        ),
    )
    invalid_payload = {
        **pose_observations[swings[0].swing_id][0].model_dump(mode="python"),
        "x": None,
    }
    return SyntheticDataset(
        session=session,
        asset=asset,
        swings=swings,
        frames=frames,
        pose_observations=pose_observations,
        event_annotations=event_annotations,
        shot_outcomes=shot_outcomes,
        invalid_observation_payloads=(invalid_payload,),
    )


def write_synthetic_dataset(store: LocalDataStore) -> SyntheticDataset:
    """Write the deterministic fixture through the public storage API."""
    if not isinstance(store, LocalDataStore):
        raise TypeError("store must be a LocalDataStore")
    dataset = create_synthetic_dataset()
    store.write_session(dataset.session)
    store.write_video_asset(dataset.session.session_id, dataset.asset)
    for swing in dataset.swings:
        store.write_swing(swing)
        store.write_frames(
            dataset.session.session_id, swing.swing_id, dataset.frames[swing.swing_id]
        )
        store.write_pose_observations(
            dataset.session.session_id,
            swing.swing_id,
            dataset.pose_observations[swing.swing_id],
        )
    for annotation in dataset.event_annotations:
        store.write_event_annotation(dataset.session.session_id, annotation)
    for outcome in dataset.shot_outcomes:
        store.write_shot_outcome(dataset.session.session_id, outcome)
    return dataset
