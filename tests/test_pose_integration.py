from __future__ import annotations

import os
from pathlib import Path

import pytest

from open_swing_analysis.contracts import CameraView
from open_swing_analysis.ingestion import FrameSelection, ingest_video
from open_swing_analysis.pose import (
    MediaPipePoseBackend,
    MediaPipePoseConfig,
    extract_pose,
)


MODEL = os.environ.get("OSA_MEDIAPIPE_MODEL")
VIDEO = os.environ.get("OSA_GOLF_SAMPLE_VIDEO")


@pytest.mark.integration
@pytest.mark.skipif(
    not MODEL or not VIDEO or not Path(MODEL).is_file() or not Path(VIDEO).is_file(),
    reason="set OSA_MEDIAPIPE_MODEL and OSA_GOLF_SAMPLE_VIDEO for real integration",
)
def test_real_golf_video_pose_integration() -> None:
    assert MODEL is not None and VIDEO is not None
    ingestion = ingest_video(
        VIDEO,
        swing_id="swing-real-integration",
        selection=FrameSelection(start=0, stop=30),
    )
    result = extract_pose(
        VIDEO,
        swing_id="swing-real-integration",
        frames=ingestion.frames,
        backend=MediaPipePoseBackend(MediaPipePoseConfig(model_asset_path=Path(MODEL))),
        observation_revision="real-integration-001",
        camera_view=CameraView.DOWN_THE_LINE,
    )
    assert result.summary.frames_processed == 30
    assert result.summary.frames_with_pose > 0
    assert len(result.observations) == 30 * 33
    assert result.summary.model_version.startswith("mediapipe-")
