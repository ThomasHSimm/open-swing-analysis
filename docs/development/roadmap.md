# Development roadmap

The stages are provisional gates, not simultaneous feature promises. The benchmark
reports define the evidence base; implementation should advance only when the prior
stage's data and validation contracts are usable.

## First task: V0.1 contracts and fixtures — implemented

Before adding a pose dependency, define and test the immutable video/session metadata,
timestamped frame record, long-form landmark observation, event label/estimate, and
quality-status schemas. Select a small, redistributable-or-local fixture policy and a
manual event-label format. This is the recommended next implementation task.

Contract version `0.1.0` now implements these records with Pydantic, PyArrow/Parquet,
validated JSON metadata, additive corrections, synthetic fixtures, and an executed
example notebook. Media decoding and pose inference remain outside this completed
contract slice.

Acceptance criteria:

- schemas express coordinate system, units, confidence, source, model/code revision,
  camera view, handedness, and missing/invalid status;
- raw observations cannot be overwritten by filtered or corrected values;
- fixture provenance and redistribution status are explicit;
- round-trip tests preserve nulls, timestamps, and provenance;
- no video or subject data enter Git accidentally.

## V0.1 — Movement measurement

Priorities:

1. deterministic video ingestion and capture-quality reporting — implemented;
2. persistent MediaPipe 33-landmark extraction on CPU;
3. continuous raw storage and separate filtered trajectories;
4. transparent event baselines plus manual event validation;
5. annotated video and confidence/missingness diagnostics.

The ingestion slice uses PyAV streaming decode, original PTS/time-base provenance,
display rotation, hashing, validated frame/capture diagnostics, and synthetic CFR/VFR
tests. The next planned task is persistent MediaPipe 33-landmark extraction through
this interface.

Validation gates:

- labelled frame-position error and missing-detection rate on representative views;
- timestamp/FPS tests, including decode gaps;
- event timing error and failure rate versus manual labels;
- view/handedness checks and explicit `not_observable` outcomes;
- repeatable outputs from pinned model/code/config revisions.

V0.1 is accepted when a new video produces a versioned observation dataset and
diagnostics, manual reviewers can correct/validate events without destroying model
output, and all reported values have an explicit measurement status.

## V0.2 — Personal consistency

Priorities:

- align multiple swings with event uncertainty;
- normalize time without discarding the original timestamps;
- build within-player trajectory baselines and variability summaries;
- detect anomalies with interpretable contributing features;
- join manual shot-outcome labels.

Acceptance requires repeatability tests, minimum-swing guidance, uncertainty-aware
comparisons, held-out anomaly checks, and clear separation between exploratory
association and causal/coaching claims.

## V0.3 — Club tracking

Evaluate existing golf-specific detectors before training anything. Compare them on
the same manually labelled frames using detection precision, clubhead pixel error,
shaft-angle error, temporal gaps, and runtime. Store model/manual/interpolated sources
per frame and support non-destructive correction.

Acceptance requires materially outperforming the benchmark's Canny/Hough negative
baseline, documented blur/occlusion failures, and no relabelling of wrist proxies as
club measurements.

## V0.4 — Advanced analysis

Possible work includes outcome association, longitudinal/statistical models,
reference-golfer comparisons, and evidence-linked explanations. These require frozen
measurement definitions, sufficient samples, validation splits, uncertainty
propagation, and privacy/consent decisions. No LLM should invent biomechanics or hide
low-confidence inputs.

## Cross-cutting requirements

- keep raw, filtered, derived, labelled, and interpreted data separate;
- record licences for code, models, weights, and datasets;
- test CPU support first and treat accelerator paths as optional;
- use public/synthetic fixtures in Git and keep personal recordings local;
- document failures and negative results as first-class evidence;
- do not make medical or injury-prevention claims.
