# V0.1 video ingestion and capture diagnostics

Status: implemented in package version `0.1.0a2`, using data-contract version
`0.1.0` without changing raw pose-observation semantics.

This layer hashes and decodes a local video as a stream, preserves source presentation
timestamps, applies display rotation, populates `VideoAsset` and `Frame`, and writes
threshold-free technical diagnostics. It does not run pose inference, identify swing
events, or classify a recording as suitable or unsuitable for analysis.

## Backend decision: PyAV rather than OpenCV

Both options use FFmpeg on common Python platforms, but their public boundaries are
different:

| Requirement | PyAV | OpenCV `VideoCapture` |
|---|---|---|
| Original presentation timestamps | Exposes each decoded frame's integer PTS and rational time base | Commonly exposes a backend-derived millisecond position |
| Variable frame rate | Individual PTS values remain available | FPS and frame-position APIs encourage constant-rate reconstruction |
| Rotation metadata | Decoded frame exposes the FFmpeg display-matrix rotation | Auto-rotation behavior depends on backend/build properties |
| Codec/container metadata | Direct stream, codec-context, duration, time-base and container access | Smaller property interface with backend-dependent support |
| Streaming | Packet/frame decoder yields one frame at a time | `read()` is also streaming |
| Dependency scope | Video/FFmpeg binding only | Broad computer-vision package before inference is required |

PyAV is therefore the V0.1 ingestion backend. OpenCV was not added as a dependency.
The interface is intentionally package-local so a future backend comparison can
produce the same contracts and diagnostics.

## Streaming and frame order

`VideoReader.iter_frames()` opens the first non-attached video stream and yields
decoded frames in decoder presentation order. It retains only the current NumPy
array. `FrameSelection` supports a start/stop/step range or explicit decoded indexes;
the decoder still advances through the source so indexes and codec state remain
correct.

`ingest_video()` makes one full streaming pass. It retains scalar frame metadata and
quality measurements, not frame images. This is linear in frame count for the small
diagnostic table but does not scale memory with video pixel data.

FFmpeg/PyAV errors are surfaced as `UnsupportedVideoError`, `EmptyVideoError`, or
`VideoDecodeError`. With partial decoding enabled, a decoder exception is recorded in
the summary and, when selected, as a `corrupt` frame attempt. A declared-versus-
decoded frame shortfall is reported but does not invent one missing row per declared
frame because container frame counts are not always authoritative.

## Timestamp policy

For each decoded frame the sidecar preserves:

- raw integer PTS;
- the frame's rational time base in seconds;
- the original PTS-derived timestamp, which may be null, duplicate, non-monotonic,
  or negative;
- the canonical non-negative, strictly increasing `Frame.timestamp_s`;
- a `TimestampSource` describing whether the canonical value is original or an
  estimate for a missing, duplicate, non-monotonic, or negative source timestamp.

Original valid PTS is never replaced. When the existing `Frame` contract cannot hold
a source timestamp, the estimate uses the most recent positive original delta, then
the stream's nominal interval, and finally one microsecond if neither exists. This is
an explicit repair recorded in `capture_quality.parquet`; it is never silently
computed as `frame_index / FPS`.

Frame-rate mode is inferred from positive original PTS intervals. An interval differs
when its deviation from the median exceeds half one stream time-base tick (minimum
numeric tolerance `1e-9` seconds). This is a representation-aware equality test, not
a video-quality threshold. Observed FPS is `(valid_timestamp_count - 1) / elapsed
source timestamp span`; nominal FPS uses the stream base/guessed rate with its
reported average rate as a fallback. All three source values remain in metadata.

## Rotation and dimensions

The source `VideoAsset.width_px` and `height_px` retain encoded dimensions. Per-frame
diagnostics retain encoded and display-oriented dimensions. Display-matrix rotations
of 0°, 90°, 180°, and 270° are applied with NumPy when images are yielded; 90° and
270° correctly swap display width and height. Other angles raise a specific error
rather than applying an undocumented resampling transform.

## Capture-quality measurements

Measurements are computed from an 8-bit grayscale decode:

- `average_brightness`: arithmetic mean, with range 0–255;
- `contrast`: population standard deviation of grayscale values;
- `blur_laplacian_variance`: variance of a four-neighbour discrete Laplacian;
- encoded/display dimensions and rotation;
- source/canonical timestamps, intervals, timestamp deviation and irregularity;
- decode status and timestamp provenance.

These values are diagnostics. High or low brightness, contrast, or Laplacian variance
is not by itself a pass/fail result and is not a claim about pose detectability. No
darkness, blur, or minimum-resolution thresholds are applied in this slice. The
`duplicate` frame quality flag is set only from the factual timestamp condition.

## Asset metadata and hashing

SHA-256 is calculated incrementally. If no asset ID is supplied, the stable default
is `asset-` plus the first 16 hash characters. The `VideoAsset` fields store codec,
encoded dimensions, nominal FPS, inferred frame-rate mode, source duration and actual
decoded-frame count. Existing metadata dictionaries retain:

- file size, modification timestamp, suffix and resolved source path;
- PyAV version and container/codec stream identity;
- rational time base, nominal/base rates and declared frame count;
- observed FPS, median source interval, rotation and display dimensions;
- the explicit timestamp policy.

The source file's size and modification time are checked again after decoding. An
in-place change aborts ingestion rather than combining a hash and frames from
different file states.

## Diagnostic storage

The existing store remains authoritative for asset JSON and canonical frames:

```text
sessions/<session_id>/
├── assets/<asset_id>.json
└── swings/<swing_id>/
    ├── frames.parquet
    └── diagnostics/
        ├── capture_quality.parquet
        ├── capture_quality_summary.json
        └── capture_quality.png
```

The diagnostic Parquet table has an explicit Arrow schema and ingestion schema
version `0.1.0`. Reads revalidate its schema, Pydantic rows, frame ordering and
canonical timestamps. Writes are immutable. Runtime throughput is returned as
non-persisted `IngestionPerformance`, keeping repeated persisted results deterministic.

The four-panel plot shows timestamp against frame index, inter-frame interval
distribution, brightness over time, and Laplacian variance over time. A contact
sheet helper accepts only explicitly selected decoded frames.

## Contract compatibility decision

No core contract field or schema version changed:

- `VideoAsset` already has source/acquisition metadata for observed FPS and file or
  backend details.
- `Frame` continues to provide the stable canonical frame/timestamp reference used
  by future pose rows.
- Nullable/raw timestamps, dimensions, numerical diagnostics and repair provenance
  live in a separate validated sidecar.
- `PoseObservation` and raw/filtered/corrected storage semantics are untouched.

This resolves the legitimate duplicate/missing/negative PTS case without broadening
every downstream frame reference to nullable or non-monotonic time. A future contract
revision could add timestamp provenance directly to `Frame`, but only with an
explicit migration; it is not necessary for this ingestion slice.

## Observed real-video performance

On the development host, the existing local benchmark clip
`Reference_Swing_DTL.mp4` (10,575,446 bytes, H.264, 734×1080, 465 frames, 15.5 s)
decoded and produced grayscale diagnostics in approximately 3.5 s, about 130
frames/s across the retained notebook run.
All 465 frames decoded; nominal and observed rates were both 30 FPS, with no missing,
duplicate, non-monotonic, or irregular timestamps and no decoder error. This is one
descriptive run, not a controlled cross-machine performance guarantee.

The smaller local `test_swing.mp4` (MPEG-4, 640×480, 150 frames) ran at approximately
586 frames/s. The large difference illustrates why codec, resolution, storage,
hardware, warm-up and process state must be controlled before comparing backends.

## Limitations

- Only the first non-attached video stream is ingested.
- Right-angle display rotation is supported; arbitrary-angle display matrices are
  rejected.
- Container-declared frame counts may be absent or inaccurate and are treated as
  advisory.
- A decoder exception identifies a failed decode attempt, not necessarily one exact
  missing source frame.
- Quality metrics are full-frame technical signals; they do not locate the golfer or
  assess camera-view suitability.
- Audio, colour calibration, HDR interpretation, interlacing diagnostics, privacy
  controls and concurrent write locking are outside this task.

The executed [video-ingestion notebook](../../notebooks/analysis/02_video_ingestion.ipynb)
demonstrates CFR, VFR, local real-video ingestion, diagnostic plots and representative
display-oriented frames.
