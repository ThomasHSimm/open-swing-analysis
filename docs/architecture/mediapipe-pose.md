# V0.1 persistent MediaPipe pose extraction

Status: implemented in package version `0.1.0a3`, using data-contract version
`0.1.0`.

This layer streams display-oriented frames through one persistent MediaPipe pose
model, writes immutable raw `PoseObservation` rows, describes missingness and model
quality, and renders diagnostic overlays. It does not smooth trajectories, infer
swing events, calculate physical rotation, or provide coaching interpretations.

## API decision

The implementation uses MediaPipe Tasks `PoseLandmarker` in `VIDEO` running mode and
calls `detect_for_video`. This is the current supported video API and exposes all 33
normalized pose landmarks, model-relative z, visibility, and presence. Presence is
stored in the existing `confidence` field; it remains distinct from visibility.

Tasks video mode was selected instead of the legacy Solutions `Pose` API because it:

- has an explicit supported video mode and persistent tracking lifecycle;
- accepts a timestamp on every decoded input frame;
- exposes presence and visibility separately;
- has explicit CPU/GPU delegate configuration and a model-bundle identity;
- closes cleanly through a documented task lifecycle.

`MediaPipePoseBackend` implements a deliberately small backend-neutral interface:
`open`, `process(image, timestamp_ms)`, `close`, model identity, configuration, and a
tuple of raw landmarks. A later YOLO or MMPose implementation must produce that
boundary rather than create a second frame reader or storage schema.

The default and currently supported delegate is CPU. `MediaPipePoseConfig` records
the model-bundle path, SHA-256, number of poses (one), detection threshold, presence
threshold, tracking threshold, delegate, Tasks mode, and segmentation setting. The
stored model version combines the installed MediaPipe version with the first 16
characters of the model SHA-256; the complete hash remains in configuration.

## Model asset

Model weights are local inputs and are not versioned in Git. For example, the
official full float16 bundle can be downloaded outside the repository:

```bash
curl -fL \
  -o /tmp/pose_landmarker_full.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task
```

Record and retain the resulting SHA-256. The label `latest` is convenient for local
setup but is not a reproducibility identity; the stored hash is authoritative.

## Timestamp transformation

`PoseObservation.timestamp_s` is copied exactly from the existing `Frame` contract.
The inference layer never reconstructs it as `frame_index / FPS`.

MediaPipe Tasks requires monotonically increasing integer milliseconds. For the
model call only, the pipeline computes `round(Frame.timestamp_s * 1000)`. If two
valid source-aligned timestamps collide at millisecond precision, or rounding would
otherwise fail to increase, the later inference timestamp is the previous value plus
one millisecond. The per-frame diagnostic records both the integer inference time and
an adjustment flag. This transformed value is not written back to `Frame` or
`PoseObservation`; original PTS and any ingestion repair remain available in the
capture-quality sidecar.

Synchronous video mode is used rather than live-stream mode because live mode may
drop frames. The pipeline must return one explicit observed or missing state for each
requested frame.

## Observation semantics

Each requested frame produces exactly 33 rows in landmark-index order:

- a detected finite x/y row is `observed` or `low_confidence`;
- a missing pose or landmark is `not_observed`, with all numeric values null;
- normalized x/y values outside `[0, 1]` are retained as legitimate raw model output;
- `relative_z_coordinate_system` is `model_relative_depth` when z exists;
- no model-relative z is described as metres or calibrated world depth;
- no coordinate is clipped, filled, interpolated, averaged, or smoothed;
- every row uses `data_layer = raw` and model provenance.

The descriptive low-confidence status uses a recorded caller threshold (default
0.5) over available visibility and presence values. It does not erase the values and
does not declare a video suitable or unsuitable for analysis.

## Diagnostics and storage

Raw observations use the existing immutable path:

```text
sessions/<session_id>/swings/<swing_id>/
├── observations/raw/<revision>.parquet
└── diagnostics/pose/<revision>/
    ├── frames.parquet
    ├── summary.json
    └── trajectories.png
```

The frame diagnostic stores detection state, returned/observed/missing landmark
counts, mean visibility, inference timestamp mapping, decode status, and processing
time. The summary stores frames processed/detected, coverage, visibility quantiles,
per-landmark missing counts, consecutive missing-pose intervals, timing, camera view,
and complete model provenance. These are technical diagnostics, not biomechanical
measurements.

The six-panel plot shows unsmoothed wrist trajectories, shoulder/hip trajectories,
nose position as a head-position proxy, all-landmark visibility, missing detections,
and per-frame processing time.

## Annotated video

`write_annotated_video` re-decodes through the existing PyAV `VideoReader` and draws
from stored observations, so visualization cannot mutate or silently filter raw
data. It supports skeleton connections, optional names, bounded raw wrist traces,
frame/timestamp labels, and a descriptive detection/mean-visibility label. A
side-by-side option places the display-oriented raw frame next to its annotation.

The writer uses source-aligned timestamps mapped to a monotonic millisecond output
time base. It handles the dimensions and right-angle rotation already applied by the
reader, flushes the encoder, reopens the output, decodes every frame, checks stable
dimensions and increasing timestamps, and rejects an empty or incomplete output.

## Example

```python
from open_swing_analysis.pose import (
    MediaPipePoseBackend,
    MediaPipePoseConfig,
    extract_pose,
    store_pose_extraction,
)

backend = MediaPipePoseBackend(
    MediaPipePoseConfig(model_asset_path="/tmp/pose_landmarker_full.task")
)
result = extract_pose(
    video_path,
    swing_id=swing.swing_id,
    frames=ingestion.frames,
    backend=backend,
    observation_revision="mediapipe-full-001",
    camera_view=session.camera_view,
)
paths = store_pose_extraction(store, session.session_id, swing.swing_id, result)
```

The executed [pose notebook](../../notebooks/analysis/03_mediapipe_pose.ipynb)
demonstrates the complete ingestion, extraction, Parquet round trip, plots, selected
illustrative frames, annotated video, and performance report.

## Limitations

- Presence is MediaPipe's landmark presence output, not a calibrated cross-model
  probability or whole-frame pose-detection score.
- Monocular normalized x/y and model-relative z are not physical 3-D kinematics.
- The full model is the tested default; lite/heavy bundles may have different speed
  and tracking behavior and must use distinct revisions.
- Tasks tracking can carry temporal model state, so processing a selected subset is
  not equivalent to processing all preceding frames. Production runs should process
  the complete swing in source order.
- Detection coverage is not landmark-position accuracy. Labelled pixel-error tests
  by camera view, occlusion, blur, and golfer population are still required.
- Annotation wrist traces are display aids over raw samples, not filtered
  trajectories or swing-path measurements.

## Observed real-video performance and benchmark check

On the development host, MediaPipe 1.2.2 with the full float16 task bundle
(`sha256` beginning `4eaa5eb7a9836522`) processed the local 1920×1080 GolfPosePro
clip `IMG_0758.MP4` at 55.3 frames/s on CPU: 749 frames and 24,717 landmark rows in
13.54 seconds of measured inference time. A pose was returned for 749/749 frames and
mean landmark visibility was 0.883. This is coverage, not position accuracy. There
were 1,607 retained low-confidence rows at the default descriptive 0.5 threshold;
wrists, hands, and elbows accounted for most of them, and the minimum visibility was
0.021 for the right wrist at frame 679. No rows were missing or out of frame in this
clip.

The manifest-listed `00001.mov` was also compared with the existing benchmark CSV
generated by the older MediaPipe 0.10.14 path. Both outputs contained all 4,488
frame/landmark keys (136 frames × 33 landmarks). Against those prior values, the new
Tasks output had mean absolute differences of 0.00330 in normalized x, 0.00202 in
normalized y, 0.0406 in model-relative z, and 0.00559 in visibility. This is a schema,
indexing, and broad numerical-consistency check—not ground-truth accuracy—and exact
equality is neither expected nor required across model/runtime versions. The new run
processed all 136 frames at 59.0 inference frames/s on CPU.
