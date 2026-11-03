# Golf-swing package source review

Review date: 2026-11-03

Projects reviewed: PyPI releases `swing-analyzer` 0.1.2, `golftracker` 2.0, and `golftrainer` 1.0.2, plus the GitHub repositories `greggjuri/golf-swing-analyzer`, `HeleenaRobert/golf-swing-analysis`, `cavanaulton/Pose2Par`, `ryanboscobanze/GolfPosePro`, and `cavanaulton/Squat-AI`. Conclusions below come from published wheels, pinned repository commits, installed source, and executed sample workflows. Documentation-only claims are identified separately.

## Executive result

No package is a sufficient foundation for the intended full-swing, club-aware, multi-session consistency system.

- `swing-analyzer` is the strongest executable package. It automatically extracts body pose, estimates events, annotates videos, and compares two swings. Its phase logic is transparent, but impact is inferred from the hands, it has no club/ball model, and it discards most raw MediaPipe data.
- `golftracker` contains the most relevant raw-data concept: 33 body landmarks with visibility, per-frame pose labels, club-head coordinates, and point provenance. The useful club path is primarily manual labels plus straight-line interpolation. The published wheel, CLIs, dependency pins, and producer schema are broken.
- `golftrainer` 1.0.2 does not analyse a swing. The wheel is a four-module JSON/dataclass/DataFrame adapter and cannot load three of the four supplied JSON exports without modification.

The strongest reusable direction is therefore conceptual: retain golftracker-like frame data, use swing-analyzer's simple event trace only as a baseline, and replace both packages' tracking/event/storage implementations with tested, versioned components.

## Tested environments and installation outcome

| Package | Python | Package | MediaPipe | OpenCV | Other major dependencies | Outcome |
|---|---:|---:|---:|---:|---|---|
| swing-analyzer | 3.11.18 | 0.1.2 | 0.10.14 | 5.0.0 | NumPy 2.4.6, SciPy 1.17.1, pandas 3.1.0 | Installed and imported normally; pose analysis worked. Native H.264 output failed silently, so execution used a documented runtime `mp4v` fallback. |
| golftracker | 3.9.25 | 2.0 | declared 0.8.10; tested 0.10.14 | 4.11.0 | declared protobuf 3.20.0; tested 4.25.9, NumPy 1.26.4, pandas 2.3.3, sklearn 1.6.1 | Normal pip install failed. The unmodified wheel contents were inspected/executed with a compatibility stack; this is a diagnostic deviation, not a successful declared installation. |
| golftrainer | 3.11.18 | 1.0.2 | n/a | n/a | NumPy 2.4.6, pandas 3.1.0 | Installed and imported normally; only `00001.json` matched its required schema. |

`swing-analyzer` correctly declares Python `>=3.9,<3.13` because its MediaPipe 0.10.14 pin has no Python 3.13 wheel. The host default was Python 3.13.12, so an isolated 3.11 environment was necessary.

## Data and execution evidence

The public golftracker Drive folder was accessible. All four videos, four pickle databases, and four JSON exports were downloaded; file IDs, hashes, sizes, and descriptions are in `data/manifests/manifest.yaml`. Videos and pickles are intentionally ignored by Git.

Observed sample properties:

| Sample | Frames | FPS | Resolution | JSON load in golftrainer 1.0.2 | Pickle load in golftracker 2.0 |
|---|---:|---:|---:|---|---|
| 00001 | 136 | 30 | 432×768 | Yes | Yes |
| 00002 | 148 | 30 | 540×960 | No: missing `version` | Yes |
| 00003 | 78 | 59 | 1920×1080 | No: missing `version` | Yes |
| 00004 | 500 | 29 | 640×480 | No: missing `version` | Yes |

The original four PyPI notebooks and six repository-extension notebooks were cleared and executed using isolated kernels. Every code cell has an execution count, every notebook reaches its `EXECUTED_OK` marker, and no notebook contains an unhandled error output. Expected project failures are captured as subprocess output, writer-state checks, or explicit evidence tables.

## 1. swing-analyzer 0.1.2

### Architecture

The package is a small command-oriented application with one large analysis module:

- `swing_analyzer/cli.py`: `swing analyze`, `swing compare`, and `swing full` dispatch.
- `swing_analyzer/core.py`: MediaPipe wrapper, image geometry, and overlay drawing. `PoseTracker` is at line 149.
- `swing_analyzer/analyze.py`: constants, video loop, event detection, metrics, video framing/retiming, and Markdown report. Key functions are `analyze_video` (line 183), `detect_phases` (431), `summarize_metrics` (609), and `flag_issues` (692).
- `swing_analyzer/compare.py`: two independent analyses, framing match, phase-based retiming, side-by-side output, and summary-table differences. `compare` begins at line 57.
- `swing_analyzer/full.py`, `report_html.py`, and `scroll_html.py`: coaching rules and richer reports.

`analyze_video` reads a frame, runs MediaPipe Pose, derives a selected metrics dictionary, draws overlays, and appends that dictionary to `frames_data`. Its public return is `(annotated_path, frames_data, fps)`. The CLI writes video and Markdown but does not export `frames_data` as JSON/CSV.

### Algorithms

**Pose.** Legacy `mediapipe.solutions.pose.Pose` uses `model_complexity=1`, detection confidence 0.5, and tracking confidence 0.5. It detects the standard 33 landmarks but stores only selected derived data: wrist midpoint, nose, paired shoulders/hips/elbows/wrists, ankle midpoint, body box, and several angles. It discards raw `z`, visibility/confidence, knees, feet, and most face points.

**Event detection.** `detect_phases` operates on normalized wrist-midpoint `y`:

1. Keep frames with a wrist result and apply a three-frame box convolution.
2. Set peak prominence to 15% of the trace range.
3. Take the first prominent hands-high peak as top; otherwise use an early high-region/argmin fallback.
4. Take the first hands-low peak after top as impact; otherwise use maximum downward velocity or maximum return height.
5. Use the last low peak before top or a backward threshold walk as backswing start.
6. Set address to the first valid frame and finish to the last valid frame.
7. Set release to roughly 0.12 seconds after estimated impact.

Address and finish are clip boundaries, not detected poses. “Impact” has no ball or club evidence.

**Geometry.** The package calculates 2D spine angle from shoulder/hip midpoints, projected shoulder and hip line changes, head displacement, ankle displacement, lead-arm angles, reverse-spine and overswing proxies, and a release arm angle. It suppresses turn metrics for down-the-line views and when projected landmark-pair separation is too small. This suppression is a good design idea, although the remaining results are still 2D projections.

**Smoothing.** Raw metrics feed phase/summary calculations. Drawing uses per-joint EMA with weight 0.5. The wrist tracer uses EMA weight 0.6 followed by a five-point local moving average. Face blur uses EMA 0.5 and holds its last box for 12 missing frames. The phase signal uses only the three-frame convolution.

**Swing plane.** No club is detected. The DTL “plane” is a fixed line through the address wrist midpoint at a default 54° or a user-supplied angle. It is an instructional reference, not a measured plane.

**Comparison.** Two videos are analysed independently. The package matches body framing, estimates slowdown from top-to-impact duration, resamples backswing/downswing/follow-through segments to common lengths, writes a side-by-side video, and subtracts summary values. It does not compare full trajectory distributions, quantify event uncertainty, or retain a session history.

### Actual results

On sample `00001.mov`, MediaPipe returned a pose for 136/136 frames. The heuristic phases were address 0, backswing start 46, top 80, impact 89, release 93, and finish 135. These are package outputs, not validated ground truth.

The hard-coded `avc1` writer could not open on this host. `analyze_video` completed and returned a nonexistent path because it never checks `VideoWriter.isOpened()`. A runtime-only `VIDEO_FOURCC="mp4v"` override produced an annotated file. Package comparison then succeeded on samples 00001 and 00002 and produced annotated clips, a phase-warped side-by-side video, and `compare_report.md`.

### Genuine measurements versus heuristics

| Output | Classification |
|---|---|
| Selected MediaPipe normalized coordinates | Model-derived image measurements |
| Spine/arm/projected line angles and displacements | Derived 2D geometry |
| Top/impact | Wrist-height signal heuristics |
| Address/finish | First/last tracked-frame heuristics |
| Swing-plane line | Fixed/manual instructional proxy |
| `TARGETS`, issue flags, coaching text | Hard-coded instructional heuristics; not personalized or biomechanically validated here |

### Useful components

- A readable baseline event detector that can be reproduced and benchmarked against better labels.
- Separation between raw metric calculations and visual smoothing.
- Camera-view gating and foreshortening checks before reporting projected rotation.
- Phase-segmented comparison video as a qualitative review aid.
- Direct return of frame dictionaries from the Python API.

### Problems and likely failure modes

- No clubhead, shaft, clubface, ball, or outcome data.
- No full raw landmark or confidence export; the eventual target row cannot be reconstructed.
- Address/finish depend on trimming, while impact can confuse any post-top hands-low point.
- Three-frame smoothing is frame-count based, so effective duration changes with FPS.
- Hard-coded generic targets can produce overconfident coaching language.
- Right/left/lead-side inference is heuristic and can fail under occlusion or unusual finishes.
- A fixed shaft-angle reference can be mistaken visually for a detected swing plane.
- Output codec failure is silent.
- `analyze.py` is monolithic, mixing inference, metrics, drawing, file I/O, retiming, and reporting.
- Comparison is slow and summary-only; it does not support cohort consistency or anomaly detection.

### Raw-data availability

Selected per-frame data are internally available through the Python return but not exported by the CLI. `frame` exists; `timestamp` can be derived from FPS. Wrist midpoint and paired shoulder/hip/elbow/wrist points are available. Full named landmarks, visibility, clubhead coordinates, and per-frame phase are not present in one table. Recovering them requires changing the package's capture/export logic.

### Licence and maintenance

The wheel includes an MIT licence file, so reuse/adaptation is permitted under the MIT terms, including preservation of copyright/licence notice. Version 0.1.2 was released on 2026-08-10 and is the most recently maintained package in this review.

## 2. golftracker 2.0

### Architecture

The intended flow is video → pickle database → GUI labels/corrections → JSON export:

- `video_utils.py`: loads every transformed frame into a list.
- `media_pipe_operation.py:12 run`: pose extraction.
- `media_pipe_landmarks.py:11 MediaPipeLandmarks`: stores protobuf landmark lists and serializes 132 values per frame.
- `pose_model.py:8 PoseModel`: optional sklearn per-frame classifier.
- `club_head_detector.py:8 ClubHeadDetector`: applies manual labels and interpolation.
- `golf_swing.py:12 GolfSwing`: aggregate data model, drawing, and JSON output.
- `golf_swing_repository.py:9 serialize`: pickle persistence.
- `path_model.py`: path extraction, moving average, and cubic interpolation utilities.
- `geom.py`: 2D geometry and velocity helpers.

The source repository contains GUI/CLI scripts such as `create_swing_db.py`, `label_golf_poses.py`, `label_club_head.py`, and `dump_swing_db.py`, but the published wheel omits `scripts/` while registering entry points to it.

### Installation and packaging failures

- Metadata pins `mediapipe==0.8.10`, which is unavailable for the tested platform/index.
- Metadata pins `protobuf==3.20.0`, an obsolete constraint relative to the tested MediaPipe fallback.
- The `tune_line_det = scripts.tune_line_det` entry point lacks `:callable`; current pip rejects it.
- All generated wrappers fail with `ModuleNotFoundError: scripts` because the wheel excludes that package.
- PyPI 2.0 and the current repository (declaring 3.0) differ; repository behavior cannot be credited to the wheel without qualification.

The library was tested by extracting the unmodified wheel and supplying MediaPipe 0.10.14, which still provides the legacy API. This established what code can run, but it is not a successful test of the declared dependency set.

### Algorithms

**Pose extraction.** For each frame, `media_pipe_operation.run` opens a new `mp.solutions.pose.Pose` context with `static_image_mode=False`, complexity 1, segmentation enabled, and detection confidence 0.5. Reopening the object discards temporal tracking state, making `static_image_mode=False` ineffective and adding heavy model initialization overhead. Segmentation output is unused.

**Pose/event classes.** `PoseModel` flattens all 33 `(x,y,z,visibility)` landmarks, applies an external sklearn classifier, and uses a maximum probability threshold of 0.7. The repository model is a StandardScaler/RandomForest pipeline, but it is not included in the wheel and is pickle/version fragile. Classes are right/left Start, Top, Finish, and Unknown. There is no impact class, temporal smoothing, transition constraint, or event confidence export.

The supplied pickles contain long runs of repeated pose classes, apparently from classification/manual correction. For example, sample 00001 has 54 `RhStart`, 13 `RhTop`, 12 `RhFinish`, and 57 `Unknown` frames. `get_first_start_pose_frame_idx` and `get_last_finish_pose_frame_idx` select boundaries; there is no unique top/impact event algorithm.

**Clubhead.** The current `ClubHeadDetector.run` copies manually supplied points with provenance `Label`, locates invalid runs between labels, and splits the straight screen-space segment evenly to create `LinearFit` points. Sample 00001 has 24 labels, 72 linear fits, and 40 invalid frames.

This is not an OpenCV object tracker. Canny and probabilistic Hough classes exist, but are not invoked by the clubhead detector. A repository `track_golf_club.py` imports a nonexistent `club_head_detection` module. ChatGPT/experimental optical-flow files in the repository are not package pipeline code. There is no automatic initialization or manual-correction confidence model.

**Shaft and ball.** The draw routine connects the right thumb to the clubhead point. That is a visualization segment, not a detected shaft. Version 2 has no ball field, clubface, heel/toe, or grip field despite older documentation describing such concepts.

**Smoothing.** `path_model.moving_average` and cubic spline interpolation are standalone utilities, not used in the capture/export pipeline. Club interpolation is piecewise linear. Pose classes have no smoothing.

### Actual results

All four supplied pickles reconstituted successfully with their matching videos. This gives real body and club trajectories without repeating GUI labelling.

A complete automatic run of sample 00001 at 50% scale produced landmarks for 136/136 frames in 10.96 seconds. With no external model/labels, every pose remained `Unknown` and every club point remained invalid. The run generated a JSON file but exposed a producer-consumer incompatibility: golftracker 2.0 writes no `version` and serializes `mp_result` as a raw list, whereas golftrainer 1.0.2 requires a dictionary containing `landmarks` and `norm_points`.

### Useful components

- The best frame-level record concept in this review: all body landmarks, z, visibility, phase label, clubhead point, and club-point provenance.
- Supplied labelled pickle/JSON examples that enable evaluation without inventing labels.
- Explicit distinction between manual and interpolated clubhead points.
- Simple accessors for named landmark paths and independent geometry helpers.
- A manual correction workflow concept that could be redesigned as an auditable annotation tool.

### Problems and likely failure modes

- Published installation and every CLI are broken.
- Dependency pins are obsolete/unavailable; fallback execution is outside metadata.
- Frames are all loaded into memory.
- MediaPipe is recreated per frame, discarding tracker state and wasting time.
- Missing-pose rows can cause downstream accessors to raise rather than propagate quality flags.
- The pose model is external, unversioned pickle data, frame-independent, and has no impact class.
- Manual club labelling is required; linear interpolation cuts corners around a curved, fast path and creates false precision.
- Club data have no confidence or calibration and remain in normalized image space.
- Pickle deserialization is unsafe for untrusted files and fragile across module/sklearn versions.
- JSON schema drift breaks golftrainer; there is no formal schema version/migration layer.
- Handedness assignment contains code defects (`==` where assignment was intended and a wrong variable reference in one branch).
- No tests of cross-package contract, camera calibration, multi-view identity, or multi-swing sessions.

### Raw-data availability

The requested row is largely already present. `frame` is the list index and `timestamp=frame/fps` is derivable. All shoulders/wrists/etc. have x/y/z/visibility, and clubhead x/y plus `phase` are available when labelled. Data are exposed through pickle objects and JSON. Gaps remain: no explicit timestamp, no pose/club quality confidence, no shaft/ball, and the published JSON schema is inconsistent.

### Licence and maintenance

MIT is verified in both the wheel and source repository, so adaptation is allowed under MIT terms. PyPI 2.0 was released 2023-11-25. The source repository's latest cloned commit was 2024-11-10 and declares version 3.0, but no matching PyPI release was available. Maintenance is sporadic and packaging remains unresolved.

## 3. golftrainer 1.0.2

### Architecture

The installed package contains only:

- `factory.py:5 create_golf_data`: read JSON and instantiate dataclasses.
- `golf_data.py`: `VideoSpec`, `VideoInput`, `PoseResult`, `MpResult`, `ClubHeadResult`, and `GolfData`.
- empty `__init__.py` and `__version__.py`.

`GolfData` produces a 132-column MediaPipe DataFrame, a 68-column x/y-plus-club DataFrame, top-left pixel coordinates, or bottom-left Cartesian-style pixel coordinates. Missing club points become `(0,0)`, conflating missingness with an image corner.

The `golf_trainer` wrapper targets an omitted `scripts` module and fails. Repository-only `geom.py`, `plot_utils.py`, and `swing_analysis.py` are absent from wheel 1.0.2.

### Algorithms and metrics

There are no packaged swing metrics, formulas, event detectors, smoothing functions, thresholds, scores, or coaching interpretations. Pose labels and club provenance are passed through from input. Therefore the complete list of installed derived features is:

1. predictable column naming;
2. normalized x/y table with clubhead;
3. x/y scaling into pixels;
4. optional y-axis inversion.

The repository after the release contains an experimental `SwingAnalysis` that segments club-direction changes above an angle threshold and estimates impact as nearest return to an initial club position. It is not installed functionality and has indexing/range defects, so it should not be adopted as-is.

### Actual results

`00001.json` loaded and produced DataFrames of shapes 136×132 and 136×68. Its pose distribution and club sources match the tracker pickle. Samples 00002–00004 fail with `KeyError: 'version'`. A fresh golftracker 2.0 export also fails at `version` and would next fail because its `mp_result` is a list rather than the expected dictionary.

Independent notebook plots demonstrate wrist, hip, shoulder, clubhead, phase-label, and a clearly labelled custom elbow-angle trace from the exposed tables. Those diagnostics are not credited to golftrainer.

### Useful components

- A small dataclass boundary between capture data and analysis code.
- Convenient full-landmark and x/y tables.
- Coordinate scaling without a pose-estimation dependency.

### Problems and likely failure modes

- Package name/description overstate the actual wheel.
- Broken CLI and incomplete wheel contents.
- No schema validation, defaults, migrations, or informative compatibility errors.
- Requires `version` but does not use it to branch or migrate.
- Replaces missing club points with `(0,0)`.
- Omits frame/timestamp and phase columns from returned DataFrames even though phase data exist.
- No quality handling for empty MediaPipe rows.
- No metrics, event analysis, comparison, visualization, or coaching functionality in the wheel.

### Raw-data availability

When compatible JSON exists, full pose x/y/z/visibility and clubhead x/y are exposed. Frame and timestamp must be added from row index and FPS; phase is stored separately in `pose_result.poses`. The desired table can be assembled without another pose model, but not by one packaged method. Shaft and ball remain impossible because they are absent upstream.

### Licence and maintenance

MIT is verified in the wheel and repository. PyPI 1.0.2 was released 2024-01-06; the latest cloned repository commit was 2024-02-12. The missing modules and schema mismatch indicate an unfinished alpha rather than a stable analysis library.

## Cross-package feature conclusions

| Area | Strongest | Conclusion |
|---|---|---|
| Pose extraction | golftracker | Retains the complete MediaPipe row and visibility. |
| Phase detection | swing-analyzer | Only automatic temporal event baseline that ran without an external classifier/manual labels; still heuristic. |
| Club tracking | golftracker | Only package with clubhead paths; primarily manual plus straight lines. |
| Trajectory storage | golftracker | Closest to the required continuous record. |
| Geometry | swing-analyzer | Most integrated geometry and camera-view checks. |
| Visualization | swing-analyzer | Working annotated and comparison videos after codec fallback. |
| Comparison | swing-analyzer | Basic two-video summary/phase-warp path; no consistency or anomaly model. |

## Recommended reuse strategy

### Reuse concept directly

- A frame-aligned record containing frame, timestamp, all body landmarks, visibility/confidence, event state, club coordinates, and provenance.
- Separate raw coordinates, filtered coordinates, derived features, and coaching interpretations.
- Explicit manual-label provenance and a correction audit trail.
- Camera-view gating before interpreting projected geometry.

### Adapt

- Use swing-analyzer's wrist-height detector as a transparent baseline to beat, with time-based rather than frame-based filtering and labelled validation.
- Adapt its phase-segmented comparison visualization, but operate over stored aligned trajectories and expose uncertainty.
- Turn golftracker's GUI idea into a non-destructive annotation layer for event/club corrections.
- Keep golftrainer's data-object boundary, but replace it with a validated, versioned schema and columnar tables.

### Replace

- MediaPipe lifecycle and storage in both trackers.
- Clubhead straight-line interpolation with a tracked detector plus confidence and correction states.
- Frame-independent pose classification and wrist-only impact inference.
- Pickle as the primary exchange format and both incompatible JSON formats.
- Hard-coded coaching targets and overconfident fault language.
- Codec assumptions and unchecked file I/O.

### Ignore

- Old documentation claims for automatic ball/heel/toe/grip tracking not present in golftracker 2.0.
- Unintegrated Canny/Hough/optical-flow experiments as evidence of a working tracker.
- Golftrainer's package description as evidence of installed analysis functionality.
- A fixed hands/shaft proxy as a measured swing plane.

## Minimal V0.1 architecture (proposal only)

Do not implement this architecture in the benchmark workspace. A minimal future system should contain:

1. **Ingestion and provenance**
   - Immutable video asset record, hash, FPS/timestamps, resolution, camera view, handedness, subject/session/swing IDs, and manually labelled outcome.
   - Decode frames as a stream rather than retaining the full video in RAM.

2. **Observation layer**
   - One persistent pose model per video.
   - Separate club/shaft/clubhead observations, initially allowing markers or manual correction if automatic confidence is inadequate.
   - Optional ball observation and explicit `not_observed` state.
   - Per-observation confidence, source (`model`, `manual`, `interpolated`), and quality flags.

3. **Versioned frame table**
   - `swing_id`, `frame`, `timestamp_s`, named body x/y/z/confidence, clubhead and shaft endpoints/confidence, ball coordinates/confidence, and calibration metadata.
   - Preserve raw observations; write filtered versions separately. Prefer Parquet plus a small validated metadata JSON schema.

4. **Temporal processing**
   - Time-aware filtering with gap limits and no interpolation across low-confidence/occluded impact regions without a flag.
   - Event model returning address, takeaway, top, downswing, impact, release, and finish with probabilities/intervals.
   - Keep the swing-analyzer wrist heuristic as a baseline test fixture.

5. **Feature layer**
   - Pure functions over explicit coordinates/calibration, with units, camera-view applicability, and missing-data behavior.
   - Distinguish image geometry, calibrated kinematics, heuristics, and coaching references in metadata.

6. **Comparison and learning layer**
   - Event-normalized continuous trajectories; within-person baseline distributions; consistency summaries; anomaly scores with explanations.
   - Join swing IDs to manually labelled outcomes without training on unavailable labels.

7. **Diagnostics and validation**
   - Tracking-confidence traces, missingness, key frames, overlay video, manual corrections, and phase uncertainty.
   - Test sets with labelled events/club points and per-camera-view error metrics before coaching claims.

This design preserves what was genuinely useful—raw continuous data, provenance, simple baseline events, and qualitative comparison—without inheriting the packages' packaging, schema, club-tracking, or biomechanics limitations.

## GitHub repository extension

Repository URLs, exact commits, dates, and licence-file status are recorded in `data/manifests/repository-manifest.yaml`. The source checkouts were read-only inputs under `/tmp`; derived evidence is in `outputs/`.

### Execution classification

| Repository | Level | What actually ran | Why it did not rank higher |
|---|---|---|---|
| HeleenaRobert/golf-swing-analysis | A | Exact script, included 465-frame video, annotated-video output | Numeric trajectories, events, club tracking, and confidence are absent |
| greggjuri/golf-swing-analyzer | B | Exact loader, motion events, club detector/tracker, and 346-test suite | Pose is a deliberate placeholder; GUI integration has incompatible calls |
| ryanboscobanze/GolfPosePro | B | Exact extraction and phase functions from notebook cells 13 and 18 on two shared clips | Colab wrapper is path/download driven; comparison is selected frames, not a continuous metric |
| cavanaulton/Pose2Par | C | Source inspection only | Two dependencies are unmapped gitlinks; exact source, weights/config, samples, and outputs are absent |
| cavanaulton/Squat-AI | C | Source inspection plus a separately labelled current-YOLO backend probe | Placeholder model path, no weights, Windows-only import, and pinned Ultralytics/checkpoint incompatibility |

### greggjuri/golf-swing-analyzer

At commit `13669643f8ed8865df74f2fe1239b126f067120c`, the implementation does not match several README claims. `PoseDetector` raises `NotImplementedError("MediaPipe integration pending")` whenever MediaPipe imports; otherwise it produces a synthetic standing pose. `ClubDetector` is Canny plus probabilistic Hough lines and Hough circles. `ClubTracker` is a causal moving average with last-value gap holding, not a Kalman filter. The event detector uses whole-frame absolute differences, not optical flow.

On shared clip 00001 with OpenCV 4.11, the event detector chose P1=20, P4=40, and P7=88. It returned a shaft on all 136 frames and a clubhead circle on 90, but high coverage was not accuracy: among the 24 manual club labels, a circle was available on 11 and only one labelled frame was within 50 px. Median available circle error was 215.2 px. The nearest shaft endpoint was within 50 px on 15/24 labels, but endpoint proximity does not establish that the Hough line is the shaft.

The suite under the repository's OpenCV 5-compatible environment produced 325 passes and 21 failures. Seven failures arise from assuming the older nested `HoughLinesP` result shape; fourteen reach the pose placeholder through pose/integration tests. The GUI additionally constructs `KeyPositionDetector` without its required loader, calls nonexistent `track_sequence` methods, treats result dataclasses as dictionaries, and passes tuple geometry into the swing-plane API. Navigation, export, and blend overlays exist, but the integrated analysis path cannot complete.

There is no licence file. An MIT badge or README statement alone is not treated as permission to reuse code.

### HeleenaRobert/golf-swing-analysis

At commit `0c551ae4d93cacd85a613b0b6d9d60aa2f333110`, the exact script completed the included 15.5 s, 734×1080, 30 fps video: 465 frames in 44.72 s, producing a readable MPEG-4 annotated video. This is the only added repository with an observed Level A run.

Each frame creates a new MediaPipe Pose context, takes the right ear, hip, and wrist, and draws the 2-D ear–hip–wrist angle. The ball is the constant pixel `(650, 927)`; it is not detected. The system exports no raw numbers, confidence, events, club/shaft, trajectory, or comparison. The implicit down-the-line/right-side view and framewise pose lifecycle constrain reuse. MIT is verified by the licence file.

### ryanboscobanze/GolfPosePro

At commit `9139e5e479a166c5ffb93abfc550f57856d8eddd`, exact notebook functions reduced MediaPipe to average visible wrist pixel Y, using visibility >0.4 and a five-frame uniform filter. Start is the first velocity sample above its 90th percentile, end is the closest post-peak return, top is a local wrist-Y minimum around a slope reversal, and impact is a post-top maximum plateau. The code then constructs six phase ranges.

The functions ran on shared clips 00001 and 00002 and produced phase-normalized outputs. This is the most useful executable seed for phase normalization among the added repositories, but not a validated event detector. It discards wrist X, individual wrists, the other 31 landmarks, confidence, and timestamps, and its “pro/student” comparison selects one midpoint frame per phase rather than comparing trajectories. MIT is verified.

### cavanaulton/Pose2Par

At commit `6d02d76c196aa0e52a06609f95b556aea48f7ba8`, `mmpose` and `marker-enhancer` are gitlinks at commits `759b39c...` and `3179260...`, but no `.gitmodules` exists. Both checkout directories are empty. No exact MMPose config/checkpoint, enhancer weights, input, or reference output is present, so pose dimensionality and enhancer architecture cannot be verified from this clone and no pipeline stage was executed.

The Compose file hard-codes NVIDIA runtime and CUDA for MMPose. OpenSim itself is CPU-capable if supplied valid TRC data, and upstream MMPose supports CPU execution in principle, but those facts do not repair missing project inputs. A modern PyTorch Intel-XPU route is also not supplied by this pinned stack.

Source that is present defines address as frame 0 and finish as the final frame, forward-fills missing poses, smooths wrist Z with Savitzky–Golay window 11, selects top from the first prominent peak (fallback: early maximum), and selects impact as a post-top minimum before 85% duration. Metrics read `pelvis_rotation` and `lumbar_rotation`, derive torso as their sum and X-factor as `abs(lumbar)`, zero at frame 0, apply sign heuristics, and then add configured event offsets: top pelvis −10°/torso −20° and impact pelvis +10°/torso +15°.

`VALIDATION.md` labels event timing, wrist tracking, and top pelvis/X-factor reliable; impact is described as good for low-handicap and mixed for high-handicap golfers; finish, angular velocity, and sagittal tilt are called unreliable. These are project-authored qualitative claims without a linked protocol, dataset, error distribution, or reproducible output. They are not independent validation. The top-level repository is MIT, while the absent marker-enhancer licence remains unresolved.

### cavanaulton/Squat-AI

At commit `e1f94988ba38dc979c27cb04cfbaa0ee1e481ed9`, the two PyQt applications import Windows-only `winsound`, load a class-level model from a placeholder path, and include no checkpoint. The pinned Ultralytics 8.0.20 environment lacked the class needed to deserialize the official `yolov8n-pose.pt`. A clearly separated upgrade probe with Ultralytics 8.4.200 processed 136/136 golf frames on CPU at 17 COCO points, averaging 0.054 s/frame; this is backend compatibility evidence, not a Squat-AI run.

Source gates the right shoulder/hip/knee/ankle at confidence 0.3, calculates hip–knee–ankle knee angle, and calls hip–shoulder–knee a “torso angle” even though it is not torso versus vertical. Depth bands are >110° red, 90–110° amber, and ≤90° green. Rep counting enters below 90° and resets above 110°, a useful hysteresis pattern. Confidence gating, explicit side-view assumptions, hysteresis, and moving inference away from the UI loop can transfer conceptually. The literal thresholds, misnamed geometry, monolithic worker, and unsmoothed decisions should not. No licence file is present.

## Combined technical conclusions

### Consolidated project matrix

| Project | Pose | Club | Events | Raw trajectories | Comparison | Validation | Execution | Relevance |
|---|---|---|---|---|---|---|---|---|
| swing-analyzer 0.1.2 | MediaPipe 33, selected points retained | Wrist proxy only | Wrist-height heuristic | Selected points internal | Phase-warp video + summary | None supplied | A | Strong executable baseline |
| golftracker 2.0 | MediaPipe 33 + external pose classifier | Manual clubhead + interpolation | Framewise Start/Top/Finish classes; no impact | Full rows in pickle/JSON | No | None supplied | B | Best annotation/storage concept |
| golftrainer 1.0.2 | None; consumes tracker JSON | Clubhead passthrough | None in returned tables | Reconstructable for one compatible schema | No | None supplied | B | Data-object boundary only |
| Greg golf-swing-analyzer | Placeholder; real MediaPipe absent | Hough shaft/circle clubhead | Whole-frame motion P1/P4/P7 | Club results internally available | Fixed-offset overlays | No club accuracy validation supplied | B | Negative club baseline/utilities |
| Heleena golf-swing-analysis | MediaPipe; consumes ear/hip/wrist | None; fixed ball pixel | None | Not exported | No | None supplied | A | Minimal annotated-video baseline |
| Pose2Par | Claimed MMPose; exact config absent | None | Smoothed wrist-Z heuristic | Intended pose/CSV/TRC/MOT, not reproduced | Reference ranges/plots | Qualitative project-authored document | C | Pipeline/biomechanics design reference |
| GolfPosePro | MediaPipe; mean wrist Y retained | None | Smoothed wrist-Y phase ranges | Wrist Y internally available | Middle frame per phase | None supplied | B | Phase-normalization seed |
| Squat-AI | YOLO 17 expected | None | Knee-angle threshold state machine | Framewise points internal, not exported | No | None supplied | C | Confidence/hysteresis/UI comparison |

### Best observed implementation by component

| Component | Strongest observed source | Decision |
|---|---|---|
| Video ingestion | swing-analyzer | Most complete executed CLI/API flow, but replace unchecked codec writer and retain timestamp/decode QC |
| Pose extraction | MediaPipe long-table probe / golftracker concept | 33 points with z/visibility and complete shared-clip coverage; use one persistent model |
| Pose smoothing | swing-analyzer | Best separation of raw metrics and display smoothing, though all windows must become time-aware and validated |
| Swing event detection | swing-analyzer baseline; GolfPosePro for normalization | No validated winner; retain both as transparent baselines against manual labels |
| Club tracking | golftracker manual labels | Best ground-truth workflow, not an automatic tracker |
| Trajectory storage | golftracker | Closest existing frame record; replace pickle/schema incompatibility |
| Biomechanical metrics | swing-analyzer among executed code | View-gated 2-D geometry only; Pose2Par is more ambitious but was not reproducible and mixes configured offsets |
| Multi-swing comparison | swing-analyzer | Only executed phase-warped two-video comparison; lacks distributions, uncertainty, and history |
| Visualization | swing-analyzer | Broadest observed annotated/key-frame/comparison outputs after codec workaround |
| Validation practice | Pose2Par documentation | Best explicit reliability categorization, but not an independently reproducible validation result |

### Pose backend comparison

| Criterion | MediaPipe Pose | YOLOv8 Pose | MMPose / Pose2Par route |
|---|---|---|---|
| Keypoints | 33 BlazePose body/face/hand/foot landmarks | 17 COCO person joints | Framework supports multiple definitions; exact Pose2Par config/count absent |
| Coordinates/confidence | normalized x/y, relative z, visibility (and task APIs can expose presence) | pixel or normalized x/y plus keypoint confidence and person-box confidence | Depends on config; raw coordinates/scores normally available, but no output here |
| Temporal behavior | tracking-aware video API; persistent legacy instance observed | Probe was framewise; no temporal model evaluated | Model/config dependent; project fills gaps downstream |
| CPU evidence | 136/136, 0.0266 s/frame mean | 136/136, 0.0545 s/frame mean with current version | Upstream CPU option exists; project could not be run |
| GPU requirement | None for tested path | None for tested path; acceleration optional | Project Compose hard-codes NVIDIA/CUDA |
| Occlusion | Visibility retained; 00002 wrists still disappeared in GolfPosePro | Confidence retained; no labelled occlusion benchmark | Pose2Par forward-fills, which can conceal loss; exact detector unknown |
| Motion blur | No labelled blur accuracy test | No labelled blur accuracy test | No runnable evidence |
| Installation | Successful in Python 3.11 isolated environment | Current install worked; repository pin/checkpoint did not | Broken checkout plus heavier Docker/CUDA stack |
| Raw frame data | Yes when caller retains all landmarks | Yes when caller retains `Keypoints` | Intended, not demonstrated here |
| Golf fit | Richer hips, hands, feet; best observed V0.1 fit | Useful alternative/person detector, but only 17 joints | Potentially valuable 2-D/3-D ecosystem; presently unevaluable |
| Licence/dependencies | MediaPipe upstream Apache-2.0 | Ultralytics licensing needs deployment-specific review | MMPose upstream Apache-2.0; missing enhancer terms unresolved |

The same video was used for the MediaPipe/current-YOLO probes, but this is not a controlled accuracy or speed contest: versions/environments differ and there are no body-keypoint ground-truth labels. Temporal stability, blur, and occlusion therefore remain `not_evaluated`, not assumed strengths.

### Hands, club, shaft, clubhead, and ball audit

| Project | Hands/grip | Shaft | Clubhead | Ball | Actual method |
|---|---|---|---|---|---|
| swing-analyzer | Wrists/hands as pose proxy; no grip | Fixed/manual plane line, not observed | No | No | MediaPipe wrist proxy |
| golftracker | MediaPipe hands; no grip model | No | Yes, primarily manual points + straight interpolation | No | Manual annotation/interpolation |
| golftrainer | Coordinates passed through if present | No | Passes tracker field through | No | No detector |
| Greg | Pose hands unavailable in current implementation | Hough line candidate | Hough circle candidate | No | Canny/Hough + moving average/gap hold; no Kalman |
| Heleena | Right wrist only | No | No | Fixed `(650,927)`, not observed | Pose proxy + drawing constant |
| Pose2Par | Wrist markers claimed | No | No | No | Pose/marker route only |
| GolfPosePro | Average of visible wrists; no grip | No | No | No | Pose proxy only |
| Squat-AI | Hand joints exist in 17-point backend but app does not use them | No | No | No | No golf-equipment model |

No reviewed system performs reliable automatic golf-club or ball tracking. “Hands,” “swing plane,” a Hough line, and a fixed ball pixel must not be relabelled as a measured grip, shaft, clubhead, or ball.

### Event detection audit

| Project | Event coverage | Class | Signal and temporal method |
|---|---|---|---|
| swing-analyzer | address, backswing start, top, impact, release, finish | Trajectory heuristic | Three-frame-smoothed wrist-midpoint Y; clip boundaries for address/finish; release offset after impact |
| golftracker | Start, Top, Finish, Unknown (handed variants); no impact | Learned framewise model + stored/manual correction | 33-landmark RandomForest pipeline, probability threshold 0.7, no transition/temporal smoothing |
| golftrainer | None in package output | None | Reads compatible tracker data but does not detect events |
| Greg | P1/P4/P7 | Trajectory heuristic | Gaussian-smoothed whole-frame absolute-difference magnitude; not body/club specific |
| Heleena | None | None | Framewise pose/angle drawing only |
| Pose2Par | address, top, impact, finish | Trajectory heuristic | Forward-filled, Savitzky–Golay-smoothed wrist Z; address/finish are clip boundaries |
| GolfPosePro | address, backswing, top, downswing, impact, follow-through | Trajectory heuristic | Uniform-filtered average wrist pixel Y and percentile velocity thresholds |
| Squat-AI | squat down/up and rep count | State machine | Framewise knee angle bands with <=90° entry and >110° reset hysteresis |

None uses a learned temporal golf-event model. Only golftracker uses a learned classifier, and it operates independently per frame without impact. None returns a calibrated event probability/interval suitable for multi-swing alignment.

### Raw trajectory audit

| Project | Continuous frame-level recovery | Available fields and gaps |
|---|---|---|
| swing-analyzer | Internally available / partially reconstructable | frame plus selected body points/metrics; derive timestamp from FPS; no full landmark confidence or club |
| golftracker | Directly exported in pickle/JSON | full 33 x/y/z/visibility, pose class, clubhead and source; timestamp derived; schemas incompatible |
| golftrainer | Reconstructable for compatible JSON | full pose and clubhead tables; returned tables omit frame/time/phase and use zero for missing club |
| Greg | Internally available; benchmark CSV demonstrates extraction | frame/time, Hough shaft/head/confidence; no real body pose; upstream integrated export path broken |
| Heleena | Unavailable after run without changing code | three points and angle exist only within each frame call; output is annotated video |
| Pose2Par | Intended but unavailable in reviewed checkout | promised 2-D/marker CSV, TRC and MOT; exact raw pose/frame outputs not reproduced |
| GolfPosePro | Internally available / reconstructable | frame index and average wrist Y only; our evidence adds derived timestamp/phase; most pose data discarded |
| Squat-AI | Internally available per frame, not exported | selected right-side points/confidence/angles in worker; no persistent trajectory |

Only golftracker comes close to the requested body-plus-club row, and it still needs explicit timestamps, quality status, shaft/ball fields, a stable versioned schema, and separation of manual/interpolated/model sources.

### Pose backends

| Backend | Observed result on 00001 | Data retained | Decision |
|---|---|---|---|
| MediaPipe Pose | 136/136 frames; 33 points; 0.0266 s/frame mean CPU | x/y/z/visibility | Best observed default for V0.1: richer landmarks, complete sample coverage, CPU-ready, permissive upstream licence |
| YOLOv8n-pose upgrade probe | 136/136; 17 points; 0.0545 s/frame | pixel x/y/confidence | Viable robustness comparator, but fewer points plus version/licence friction |
| Pose2Par MMPose | Not runnable | Exact config and output unknown | Do not rank from README claims |

The latency comparison is descriptive, not a controlled speed benchmark: environments and library versions differ. For future evaluation, use the same decoded frames, warm-up, hardware settings, and labelled visibility/position errors.

### Events, club tracking, and continuous data

No automatic event detector has adequate labelled validation. GolfPosePro is the best executable phase-normalization seed; `swing-analyzer` remains the simplest transparent baseline. Pose2Par contains the strongest validation language but the weakest reproducibility in this checkout.

No automatic club tracker is ready. Golftracker's manual points and provenance are the strongest annotation/ground-truth asset. Greg's Hough detector is useful as a negative baseline but its clubhead result failed the manual-label audit. A fixed ball pixel is `not_observed`, never ball tracking.

The preferred continuous record is a long, frame/timestamp-aligned table containing every named raw landmark coordinate and confidence, plus clubhead, shaft endpoints, and ball with per-frame source (`model`, `manual`, `interpolated`, `not_observed`) and confidence. Raw, filtered, event, feature, and coaching layers must remain separable.

### Required measurement statuses

Every output should carry one of: `observed_raw`, `model_estimate`, `derived_2d`, `heuristic_event`, `manual_label`, `interpolated`, `calibrated_kinematic`, `low_confidence`, `not_observed`/`not_observable`, or `invalid`. Include camera view, handedness, coordinate system/units, model and code revision, formula, confidence or interval, and correction provenance as applicable. A 2-D proxy, fixed coordinate, adjusted event metric, or documentation claim must never be presented as a physical measurement.

### Remaining development

The project still needs versioned session/frame schemas; immutable video provenance; camera/view/handedness QC; labelled event and club evaluation sets; event uncertainty; calibrated geometry; a genuine club/ball detector with manual correction; time-aware missing-data/filter rules; phase-normalized within-player distributions; consistency and anomaly models; outcome joins; and independent validation stratified by view, player group, and capture conditions. `docs/research/benchmarks/reuse-map.md` turns these findings into a component-level decision record without implementing the package.

## Final decision answers

1. **Which repositories cloned successfully?** All five: Greg, Heleena, Pose2Par, GolfPosePro, and Squat-AI. Exact commits are in `data/manifests/repository-manifest.yaml`.
2. **Which ran end to end?** Heleena only (Level A), on its included 465-frame video.
3. **Which ran partially?** Greg's loader/events/club components and GolfPosePro's exact extraction/phase functions (Level B).
4. **Which were source review only?** Pose2Par and Squat-AI (Level C). Squat-AI's current-YOLO output is a separate backend probe, not a project run.
5. **Best pose approach observed?** MediaPipe: complete shared-clip coverage, 33 landmarks with visibility/Z, CPU operation, and the least adoption friction. YOLO is a useful comparator; MMPose remains untested here.
6. **Best event-detection approach observed?** None is production-ready. GolfPosePro is the most useful executable normalization seed, and `swing-analyzer` is the clearest simple baseline. Both need labelled validation.
7. **Best club-tracking approach observed?** No automatic tracker. Golftracker's manual labels and provenance are the best ground-truth asset. Greg remains a negative automatic baseline.
8. **Most useful continuous-data representation?** Full named landmarks with frame, timestamp, coordinate system, confidence, and model revision, plus club/shaft/ball observations carrying source and confidence.
9. **Which Squat-AI ideas transfer?** Confidence gating, explicit side/view assumptions, hysteresis, and GUI/inference separation—not its thresholds or geometry labels.
10. **What still needs to be developed?** The schema, QC and annotation layer, validated events, calibrated geometry, evaluated club/ball observation, uncertainty-aware filtering, longitudinal comparison/outcome joins, and independent validation—not another unverified all-in-one demo.

## Official dependency references

- MediaPipe's landmark container documents x/y/z, visibility, and presence fields: <https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/components/containers/Landmark>.
- MediaPipe's Pose Landmarker API documents video/live-stream modes: <https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarker>.
- Ultralytics documents the 17-point human pose output and coordinate/confidence accessors: <https://docs.ultralytics.com/tasks/pose>.
- MMPose documents its model/dataset scope and CPU device option: <https://mmpose.readthedocs.io/en/latest/overview.html> and <https://mmpose.readthedocs.io/en/latest/faq.html>.
- PyTorch documents its current Intel GPU/XPU path: <https://docs.pytorch.org/docs/main/notes/get_start_xpu.html>.
- Ultralytics publishes its current licensing choices at <https://www.ultralytics.com/license>.
