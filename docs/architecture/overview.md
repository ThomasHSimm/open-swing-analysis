# Architecture overview

Status: proposed architecture informed by the completed benchmark. No movement
measurement pipeline is implemented yet.

## Architectural principles

1. **Preserve observations before interpretation.** Immutable video/session
   provenance and raw frame-level model output come before smoothing, events,
   features, comparisons, or explanations.
2. **Make provenance row-level.** Model estimates, manual labels, interpolation,
   and configured corrections remain distinguishable.
3. **Expose uncertainty and observability.** Coordinates, events, and metrics carry
   confidence/status rather than silently becoming precise numbers.
4. **Gate by capture conditions.** Camera view, handedness, framing, blur, and
   calibration determine which metrics may be reported.
5. **Validate simple baselines first.** Transparent wrist-trajectory heuristics are
   benchmarks to beat, not ground truth.
6. **Keep interfaces backend-neutral.** MediaPipe is the observed V0.1 default, but
   the observation schema must allow controlled YOLO or MMPose comparisons.

These choices follow the [package review](../research/benchmarks/package-review.md)
and [reuse map](../research/benchmarks/reuse-map.md).

## Proposed data flow

```text
VideoAsset + SwingSession
        |
        v
timestamped Frame stream + CaptureQuality
        |
        v
raw PoseObservation rows (landmark, x/y/z, confidence, model revision)
        |
        +--> manual EventLabel and equipment annotations
        |
        v
filtered trajectory version (never overwrites raw observations)
        |
        v
EventEstimate with probability/interval and method revision
        |
        v
view-appropriate Feature rows with units and observability
        |
        v
phase-normalized SwingTrajectory
        |
        v
personal baseline -> variability/anomaly summaries -> OutcomeLabel association
```

## Layer responsibilities

### Ingestion and provenance

Records the immutable asset hash, source, subject/session/swing identifiers, FPS,
resolution, timestamps, camera view, handedness, and decode failures. Frame numbers
alone are insufficient for variable or inaccurate frame rates.

### Observation

V0.1 should use one persistent MediaPipe model per video and retain all 33 landmarks,
including z and visibility. An observation is a model estimate, not a physical 3-D
measurement. Equipment observations use separate schemas and can be absent.

### Temporal processing

Filtering is time-aware, versioned, and constrained by gap length/confidence. Event
detectors return a method, score or interval, and failure state. Manual validation is
stored alongside—never destructively substituted for—the model estimate.

### Feature and measurement status

Every result carries a status such as `observed_raw`, `model_estimate`, `derived_2d`,
`heuristic_event`, `manual_label`, `interpolated`, `calibrated_kinematic`,
`low_confidence`, `not_observable`, or `invalid`. Formulas, input points, units,
camera applicability, and revisions are required metadata.

### Consistency and outcomes

V0.2 compares phase-normalized continuous trajectories within one golfer. Personal
baselines and variability precede anomaly scoring. Outcome labels remain manual until
their definition and reliability are established; exploratory association is not
causation or coaching advice.

### Visualization

Overlays and diagnostic plots expose missingness, confidence, event uncertainty,
manual corrections, and raw-versus-filtered traces. Presentation must not upgrade a
proxy into a measurement.

## Deferred decisions

- The persistent storage engine and formal schemas will be selected during the V0.1
  contract task; Parquet plus validated metadata JSON is the current benchmark-led
  preference, not a committed implementation.
- Automatic club/ball tracking is deferred until V0.3 and requires labelled pixel
  error/precision tests.
- OpenSim/3-D biomechanics is not part of V0.1. It requires calibration, reproducible
  marker generation, inverse-kinematics quality measures, and independent validation.
- LLM explanations are deferred until measurements, uncertainty, and source evidence
  can be cited reliably.
