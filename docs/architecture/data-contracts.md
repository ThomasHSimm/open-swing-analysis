# V0.1 data contracts

Status: implemented contract version `0.1.0`.

This document defines the first Open Swing Analysis implementation boundary. It
stores source-video identity, recording context, timestamped frames, pose-model
output, event annotations, and optional shot outcomes. It does not perform video
decoding, pose inference, event detection, filtering, or swing analysis.

## Record definitions

All records are strict, frozen Pydantic models. Unknown fields are rejected and each
record carries `schema_version = "0.1.0"`.

| Record | Purpose | Important constraints |
|---|---|---|
| `VideoAsset` | Immutable source-video identity and capture facts | SHA-256, pixel dimensions, frame-rate mode, duration, frame count, codec, source/acquisition metadata |
| `SwingSession` | Subject and recording context shared by swings | Explicit recording date, camera view, handedness, camera and capture metadata |
| `Swing` | Session/video relationship for one swing | Stable session, asset, and optional shot-outcome references |
| `Frame` | One decode attempt in source time | Non-negative frame index and original timestamp, decode status, quality flags |
| `PoseObservation` | One long-form landmark row | Frame/timestamp reference, normalized image x/y, optional model-relative z, separate visibility and confidence, model/revision and row provenance |
| `EventAnnotation` | Manual, model, or heuristic event record | Optional uncertainty interval, explicit not-observed state, immutable correction link |
| `ShotOutcome` | Optional manual outcome label | Club, categorical strike/flight fields, optional distances with an explicit unit |

Identifiers are caller-supplied stable strings restricted to letters, numbers, `.`,
`_`, `:`, and `-`. They are not inferred from mutable filenames or row order. The
synthetic fixture uses readable identifiers; production ingestion should derive or
allocate identifiers once and persist them.

## Coordinate conventions and units

- `Frame.timestamp_s`, event timestamps, event uncertainty, and video duration are
  seconds. Timestamps preserve the source presentation timeline and are not rebuilt
  from `frame_index / nominal_fps`.
- `width_px` and `height_px` are pixels. Frame index is zero-based and refers to the
  source asset's decoded-frame sequence.
- Pose `x` increases from left to right and `y` increases from top to bottom. Both are
  normalized to the image width/height and validated in `[0, 1]` under
  `image_normalized_top_left`.
- `relative_z` is optional model-relative depth. It is allowed only with
  `relative_z_coordinate_system = "model_relative_depth"`. It is not calibrated
  metric 3-D and must not be described as a physical depth measurement.
- Visibility expresses whether the model considers a landmark visible; confidence
  expresses observation certainty. They are separate nullable probabilities.
- Carry and total distance are optional non-negative values. A present distance must
  declare either `metres` or `yards`; missing distances remain `null`.

Coordinates outside the supported normalized image domain are rejected. A backend
that returns an unusable row records `observation_status = "invalid"` with null
coordinates, preserving the failure without inventing a boundary value. Missing
values are always null, never zero.

## Status and provenance

Frame decode states are `decoded`, `missing`, and `corrupt`. Frame quality flags are
independent and may identify blur, exposure, occlusion, partial framing, or duplicate
frames.

Pose observation statuses are:

- `observed`: usable model output;
- `low_confidence`: retained output below the calling pipeline's recorded threshold;
- `not_observed`: no landmark observation, with coordinate/confidence fields null;
- `invalid`: a failed/unusable observation, also stored with numeric fields null.

Each pose row records its model name/version, observation revision, source type,
source identity, source revision, and timestamp of record creation. Raw rows require
model provenance. Filtered rows require the raw revision in
`derived_from_revision`. Corrected rows additionally require manual provenance and a
correction reason.

Event records distinguish `manual`, `model`, and `heuristic` sources. They carry the
annotator/model identity and revision. A manual correction is a new annotation with
`corrects_annotation_id`; it never mutates or replaces the prior estimate. An event
may be explicitly `not_observed`, so impact is not assumed to exist within every
clip. Uncertainty intervals use seconds and must contain the event timestamp.

## Storage layout

`LocalDataStore` writes validated JSON metadata and explicit-schema Parquet tables:

```text
<root>/
└── sessions/<session_id>/
    ├── session.json
    ├── assets/<asset_id>.json
    └── swings/<swing_id>/
        ├── swing.json
        ├── frames.parquet
        ├── observations/
        │   ├── raw/<revision>.parquet
        │   ├── filtered/<revision>.parquet
        │   └── corrected/<revision>.parquet
        ├── annotations/events/<annotation_id>.json
        └── outcomes/<outcome_id>.json
```

Frame and pose tables use PyArrow schemas with `schema_version` and `record_type`
metadata. Pose tables additionally store their layer and revision in Parquet
metadata. Writes refuse to replace an existing record or table. This makes raw rows
immutable and makes every filtering/correction revision a separate physical object.

Reads validate the JSON/Arrow schema version, field shape, Pydantic constraints,
frame ordering, and frame/timestamp references. Unsupported versions raise
`SchemaVersionError` with the expected and encountered versions. No database server
or pickle deserialization is involved.

## Schema-version policy

Contract versions use semantic versioning independently from the Python package
version:

- patch: clarifications or compatible validation fixes that do not change stored
  fields;
- minor: backward-compatible optional fields or enumerated values;
- major: required-field, type, coordinate, unit, or semantic changes that need an
  explicit migration.

This implementation reads exactly `0.1.0`; it does not silently migrate or accept a
newer version. A future migration must read the old contract explicitly, create a
new output tree, and preserve the original data.

## Example usage

```python
from open_swing_analysis.contracts import ObservationLayer
from open_swing_analysis.storage import LocalDataStore
from open_swing_analysis.synthetic import write_synthetic_dataset

store = LocalDataStore("/tmp/open-swing-contracts")
fixture = write_synthetic_dataset(store)

rows = store.read_pose_observations(
    fixture.session.session_id,
    fixture.swings[0].swing_id,
    ObservationLayer.RAW,
    "raw-pose-run-001",
)
```

The executed [data-contract notebook](../../notebooks/analysis/01_data_contracts.ipynb)
shows the complete synthetic round trip, trajectory display, and additive manual
event correction.

## Current limitations

- Only local filesystem storage and contract version `0.1.0` are supported.
- Coordinate validation currently targets normalized 2-D image landmarks plus an
  optional model-relative depth value; calibrated world coordinates need a separate
  future contract.
- The store requires strictly increasing timestamps within a swing. It preserves
  irregular spacing but does not currently represent equal presentation timestamps.
- Cross-process write locking, migrations, streaming dataset partitioning, and
  privacy/access control are not implemented.
- Strike/outcome categories are non-empty strings until a labelled reliability study
  establishes a stable controlled vocabulary.
