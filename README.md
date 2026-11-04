# Open Swing Analysis

Open Swing Analysis is a research-led Python project for measuring movement in
ordinary golf-swing video. Its central question is:

> Can ordinary video quantify an individual golfer's swing variability,
> identify anomalous movements, and determine which variations are associated
> with labelled shot outcomes?

The repository is currently at the **V0.1 video-ingestion implemented** stage. It
preserves executed evaluations of eight existing golf and movement-analysis projects
and now provides versioned local storage plus deterministic streaming decode and
capture diagnostics. It does not yet provide pose inference, swing measurement,
coaching, anomaly detection, or outcome prediction.

## Current contents

Implemented repository infrastructure:

- an installable `open_swing_analysis` project scaffold;
- the `open-swing` status/version command;
- strict Pydantic contracts and validated JSON metadata;
- PyArrow/Parquet frame and long-form pose tables with immutable revision layers;
- deterministic synthetic fixtures and an executed data-contract notebook;
- PyAV streaming ingestion with original timestamp and rotation provenance;
- brightness, contrast, blur-proxy and timestamp diagnostic outputs;
- ten executed benchmark notebooks;
- benchmark scripts, derived evidence, manifests, and licence notes;
- architecture and staged-development documentation;
- research and study-design material migrated from `golf-balance`.

Proposed capabilities—not yet implemented—are video ingestion, 33-landmark pose
extraction, validated swing-event detection, personal consistency analysis, anomaly
detection, outcome association, and club tracking.

## Evidence from the benchmark

The benchmark found that MediaPipe is the best observed V0.1 pose starting point,
but no reviewed event detector or automatic golf-club tracker is production-ready.
The most useful existing ideas are full frame-aligned landmark storage, manual
club/event provenance, transparent wrist-trajectory baselines, confidence gating,
camera-view constraints, and state-machine hysteresis.

Read the full [package review](docs/research/benchmarks/package-review.md), the
[reuse map](docs/research/benchmarks/reuse-map.md), or the executed
[combined comparison notebook](notebooks/benchmarks/09_repository_comparison.ipynb).

## Architecture

The proposed data flow is:

```text
video/session provenance
        -> timestamped frames and capture QC
        -> raw pose observations with confidence
        -> manual/heuristic events with provenance
        -> separately filtered trajectories
        -> view-appropriate 2-D features
        -> phase-aligned personal baselines
        -> variability/anomaly summaries
        -> manually labelled shot outcomes
```

Raw observations, filtered coordinates, events, features, and interpretations are
separate layers. See the [architecture overview](docs/architecture/overview.md).

## Installation

Python 3.11 or newer is recommended for repository development:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,analysis]'
open-swing status
pytest
```

No pose-inference dependency is installed yet. The runtime uses PyAV and NumPy for
streaming decode/diagnostics plus Pydantic and PyArrow for contracts and storage;
Jupyter and Matplotlib are optional analysis dependencies. See the
[data-contract reference](docs/architecture/data-contracts.md) and
[video-ingestion decision](docs/architecture/video-ingestion.md).
The benchmark packages require separate environments; their exact commands are in
the [benchmark reproduction guide](docs/research/benchmarks/golf-balance-benchmark-readme.md).

## Benchmark notebooks

Executed notebooks are under [`notebooks/benchmarks`](notebooks/benchmarks). Their
saved outputs can be reviewed without installing the third-party projects. Large
source videos, pickles, environments, checkpoints, and generated videos are not
versioned.

To rebuild the notebook sources after creating the documented benchmark environment:

```bash
python scripts/build_notebooks.py
python scripts/build_repository_notebooks.py
```

Rebuilding clears saved execution output; only do it when intentionally updating the
benchmark. Data provenance and download hashes are under [`data/manifests`](data/manifests).

## Development roadmap

- **V0.1 — Movement measurement:** ingestion, MediaPipe landmarks, continuous
  storage, validated event baselines, overlays, and diagnostics.
- **V0.2 — Personal consistency:** phase alignment, normalized trajectories,
  personal baselines, variability, anomalies, and manual outcome labels.
- **V0.3 — Club tracking:** evaluate golf-specific models, retain confidence and
  provenance, and support manual correction.
- **V0.4 — Advanced analysis:** outcome association, statistical modelling,
  reference comparisons, and evidence-based explanations.

Each stage has validation gates and acceptance criteria in the
[development roadmap](docs/development/roadmap.md).

## Limitations

- Ordinary monocular video does not directly measure 3-D biomechanics, force,
  pressure, or true club/ball state.
- Existing event algorithms are heuristic and not yet validated for this project.
- Pose confidence and camera suitability must be retained; missing observations must
  not be silently interpolated into false precision.
- The repository contains research evidence, not medical, injury-prevention, or
  automated coaching advice.

## Provenance and licence

The migration preserves the original `golf-balance` Git commits as ancestry and
records the working-tree migration in
[`docs/development/migration.md`](docs/development/migration.md). Third-party code,
data, and model licensing remains governed by their respective projects and is
documented in the benchmark reports.

Open Swing Analysis's own source and documentation are licensed under the MIT
License. See [LICENSE](LICENSE).
