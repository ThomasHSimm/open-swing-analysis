# Component reuse map

Review date: 2026-11-03. This is a design decision record, not an implementation plan or licence opinion. “Reuse” below can mean reuse of a concept; source-code reuse still depends on the recorded licence status.

| Component | Best evidence source | Decision | Conditions and replacement work |
|---|---|---|---|
| Video provenance and frame timestamps | benchmark harness | Reuse directly | Hash input; record FPS, resolution, decode status, frame and timestamp |
| Persistent CPU pose extraction | MediaPipe probe / golftracker concept | Adapt | One model per video; long raw table; preserve x/y/z/visibility and model version |
| Alternative pose robustness check | current YOLO probe | Evaluate, do not adopt yet | Same labelled frames and hardware; resolve licence; 17-point sufficiency test |
| MMPose/3-D whole-body route | Pose2Par claim | Defer | Recover exact source/config/checkpoint and fixtures before ranking |
| Frame-aligned record | golftracker | Adapt strongly | Replace pickle/fragile JSON with validated versioned Parquet + metadata |
| Event baseline | swing-analyzer | Adapt as baseline | Time-based filtering; return probabilities/intervals; validate per view |
| Phase normalization | GolfPosePro | Adapt as experiment | Preserve full trajectories; compare against manual events; handle gaps explicitly |
| Pose2Par event logic | Pose2Par | Reproduce only after checkout repair | No production use from source-only evidence |
| Manual club labels/provenance | golftracker | Reuse concept directly | Non-destructive correction layer and per-point audit history |
| Automatic club detector | Greg Canny/Hough | Keep as negative baseline | Evaluate pixel error/precision/recall; replace for production |
| Fixed ball point | Heleena | Ignore as measurement | Permit only as a clearly labelled manual reference |
| Squat confidence gate | Squat-AI | Adapt | Gate every geometry input; propagate confidence instead of dropping silently |
| Hysteresis/state machine | Squat-AI | Adapt | Use event probabilities and time thresholds, not squat angle cut-offs |
| Camera-view gating | swing-analyzer / Squat-AI | Reuse concept directly | Store view/side/handedness and suppress inapplicable metrics |
| 2-D angles | swing-analyzer / Heleena | Adapt cautiously | Mark `derived_2d`; record points/formula/view; do not imply 3-D biomechanics |
| OpenSim TRC/MOT boundary | Pose2Par | Adapt as future interface | Require reproducible pose/enhancement, calibration, IK residuals, and no hidden offsets |
| Adjusted rotation/X-factor values | Pose2Par | Do not reuse numerically | Separate raw kinematics from correction/normalization and independently validate |
| Difference/phase video | swing-analyzer / Greg | Adapt | Align by validated events and show uncertainty; retain qualitative status |
| Middle-frame comparison | GolfPosePro | Use only for presentation | Never substitute it for continuous trajectory comparison |
| GUI worker separation | Squat-AI | Reuse concept | Separate capture, inference, feature/state, persistence, and rendering queues |

## Reuse directly where licence/API permits

- **Video/session provenance and frame timestamps:** the benchmark pattern is already independent of any analysis algorithm and prevents silent asset/version changes.
- **Manual club-label provenance:** reuse golftracker's distinction between labelled and interpolated points as a data concept, while implementing it in a stable schema.
- **Camera-view gating:** reuse the rule that a metric should be suppressed when its view/foreshortening assumptions fail.
- **Raw confidence retention:** keep MediaPipe visibility or backend confidence in every observation rather than reducing it to a pass/fail display decision.

## Reimplement based on concept

- **Frame-aligned storage:** reproduce golftracker's useful row concept, not its incompatible pickle/JSON schemas or missing-value zeros.
- **Event baselines:** independently implement the documented wrist/trajectory rules as transparent test baselines so results can be validated and versioned without copying unlicensed or tightly coupled source.
- **Annotation and correction layer:** reproduce the non-destructive manual workflow with audit history; do not embed correction state only in a GUI object.
- **Movement-state hysteresis:** use Squat-AI's entry/reset idea with golf-event probabilities and time units, not its squat angle thresholds.
- **Phase-normalized comparison:** reproduce GolfPosePro's normalized-time idea over complete trajectories and uncertainty, not one midpoint frame.

## Adapt and modernize

- **MediaPipe extraction:** retain all 33 points with a persistent video model, stable long-table output, timestamps, and explicit missingness.
- **swing-analyzer diagnostics/comparison:** retain view checks, key frames, and phase-warp visualization; replace frame-count smoothing, codec assumptions, and summary-only comparison.
- **Pose backend interface:** keep a backend-neutral observation schema so YOLO or later MMPose runs can be evaluated on identical labelled frames.
- **GUI concurrency:** separate capture, inference, temporal state, persistence, and rendering instead of moving the whole monolith into one worker thread.
- **TRC/MOT/OpenSim boundary:** consider it only after Pose2Par inputs are reproducible and calibration, inverse-kinematics residuals, and offsets are explicit.

## Do not use

- **Greg Hough club output as a measurement:** it is retained only as a negative baseline because its circle-centre error failed the manual-label audit.
- **Fixed ball coordinates or wrist-based “club” proxies:** these are references/proxies, not observations of equipment.
- **Pose2Par's configured event offsets as raw kinematics:** adjusted numbers must never replace untouched inverse-kinematics output.
- **Squat-AI's literal thresholds or misnamed torso angle:** they have neither golf relevance nor validation for this use.
- **GolfPosePro middle-frame comparison as an analysis metric:** it is a presentation shortcut and discards trajectory variation.
- **Any source lacking a verified licence file:** Greg and Squat-AI can inform an independent design review, but their code should not be copied based on README claims.

## Recommended V0.1 evidence path

1. Preserve immutable video/session provenance and decode to a timestamped frame stream.
2. Extract all 33 MediaPipe landmarks and visibility into a raw long table; keep a backend field so YOLO/MMPose can be evaluated without schema changes.
3. Add manual event and club-point annotation with provenance before training or declaring an automatic tracker.
4. Run the transparent swing-analyzer and GolfPosePro heuristics as baselines against labels, reporting frame/time error and failure rate by camera view.
5. Store filtered coordinates separately with time-aware gap limits. Never overwrite raw data.
6. Build event-normalized within-player trajectories only after event uncertainty is available.
7. Add calibrated/3-D/OpenSim stages later, with their own validation and status, rather than blending them into 2-D results.

## Licence gate

- Verified repository licence files: Heleena (MIT), GolfPosePro (MIT), Pose2Par top level (MIT).
- No licence file in the reviewed clone: Greg, Squat-AI. Do not copy source based on README badges/claims.
- Pose2Par's missing marker-enhancer code also leaves that dependency's terms unresolved.
- MediaPipe upstream is Apache-2.0. Ultralytics distribution/deployment needs a project-specific licence decision before adoption.

## Stop conditions for measurement claims

Mark a field `not_observed` or `invalid` when its source is absent, confidence is below a recorded threshold, view assumptions fail, calibration is missing, or a gap exceeds the interpolation policy. Mark events `heuristic_event` until labelled validation supports a stronger status. Keep manual labels, model estimates, interpolation, and configured offsets distinguishable at row level.
