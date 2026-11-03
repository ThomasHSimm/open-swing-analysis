# Migrated golf-swing package benchmark

This is the reproduction guide migrated from `golf-balance`. Paths have been
updated for Open Swing Analysis; the original Git version remains available in
repository history.

Preliminary research and experiment design for a study of balance-focused
training applied to golf swing weight transfer.

This repository also contains a source-level benchmark of three PyPI packages
and five GitHub repositories. The benchmark deliberately does not implement a
new golf-analysis pipeline.

## Benchmark deliverables

- `notebooks/benchmarks/01_swing_analyzer.ipynb` — installed source, real pose run,
  phase/metric diagnostics, key frames, and package comparison mode.
- `notebooks/benchmarks/02_golftracker.ipynb` — installed source, packaging failures,
  live MediaPipe path, supplied pickle/JSON, and body/club trajectories.
- `notebooks/benchmarks/03_golftrainer.ipynb` — installed source, expected schema,
  DataFrame outputs, compatibility failures, and coordinate diagnostics.
- `notebooks/benchmarks/04_greggjuri_golf_swing_analyzer.ipynb` — event and club
  component execution, test failures, GUI integration, and label-error audit.
- `notebooks/benchmarks/05_pose2par.ipynb` — reproducibility, hardware, OpenSim metric,
  event, and validation-claim audit.
- `notebooks/benchmarks/06_golfposepro.ipynb` — exact wrist/phase functions on two clips
  and normalized phase diagnostics.
- `notebooks/benchmarks/07_heleena_golf_swing_analysis.ipynb` — exact end-to-end run on
  the included reference clip.
- `notebooks/benchmarks/08_squat_ai.ipynb` — strength-comparison source audit and a
  separately labelled current-YOLO backend probe.
- `notebooks/benchmarks/09_repository_comparison.ipynb` — combined eight-project decision
  record and direct answers to the benchmark questions.
- `notebooks/benchmarks/10_pypi_package_comparison.ipynb` — original three-package
  comparison.
- `docs/research/benchmarks/package-review.md` — full architecture/algorithm/licence review and a
  proposed V0.1 architecture (design only).
- `docs/research/benchmarks/reuse-map.md` — component-level reuse/adapt/replace/defer decisions.
- `data/manifests/manifest.yaml` — provenance, Drive file IDs, sizes, and SHA-256 hashes.
- `data/manifests/repository-manifest.yaml` — exact repository commits and licence-file
  status.
- `scripts/inspect_packages.py` — read-only installed-source inventory.

All ten notebooks are committed with executed outputs. The large downloaded
videos/pickles and generated videos are ignored by Git.

## Key benchmark conclusion

MediaPipe is the strongest observed pose default for this project. GolfPosePro
is a useful executable phase-normalization seed, while `swing-analyzer` remains
the simplest transparent event baseline. `golftracker` has the most useful
continuous-data and manual club-label concept. No automatic club tracker passed
the label audit, and no automatic event detector is adequately validated.

No reviewed project supports robust club/shaft/ball tracking, validated swing events,
multi-session personal consistency, anomaly detection, or outcome linkage.

## Recreate the benchmark environments

The host default Python 3.13 cannot install `swing-analyzer`; use isolated
environments. The commands below mirror the tested setup from the repository
root. Environment directories are ignored by Git.

### swing-analyzer

```bash
conda create -p ./envs/swing-analyzer python=3.11 pip -y
./envs/swing-analyzer/bin/python -m pip install \
  swing-analyzer==0.1.2 pandas matplotlib nbformat nbconvert ipykernel
```

Tested key versions were Python 3.11.18, MediaPipe 0.10.14, OpenCV 5.0.0,
NumPy 2.4.6, and SciPy 1.17.1. The package pins MediaPipe 0.10.14 and declares
Python `>=3.9,<3.13`.

### golftrainer

```bash
conda create -p ./envs/golftrainer python=3.11 pip -y
./envs/golftrainer/bin/python -m pip install \
  golftrainer==1.0.2 matplotlib nbformat nbconvert ipykernel
```

Tested key versions were Python 3.11.18, pandas 3.1.0, and NumPy 2.4.6.

### golftracker: reproduce the failure and diagnostic environment

The declared installation is expected to fail: MediaPipe 0.8.10 is unavailable
for the tested index/platform, one console entry point is malformed, and the
wheel omits the `scripts` package used by every CLI.

```bash
conda create -p ./envs/golftracker python=3.9 pip -y
./envs/golftracker/bin/python -m pip install golftracker==2.0
```

For source/library evaluation only, the benchmark used the unmodified wheel
with a compatible legacy-API MediaPipe stack:

```bash
./envs/golftracker/bin/python -m pip download --no-deps \
  golftracker==2.0 -d /tmp/golftracker-wheel
./envs/golftracker/bin/python -m zipfile -e \
  /tmp/golftracker-wheel/golftracker-2.0-py3-none-any.whl \
  ./envs/golftracker/lib/python3.9/site-packages
./envs/golftracker/bin/python -m pip install \
  'mediapipe==0.10.14' 'protobuf>=4.25.3,<5' 'numpy<2' \
  'opencv-contrib-python<5' 'pandas<3' 'scikit-learn<1.7' \
  'matplotlib<3.10' 'nbformat<6' 'nbconvert<8' 'ipykernel<7'
```

This is explicitly a diagnostic deviation from the package metadata, not a
claim that the normal installation succeeded. Tested key versions were Python
3.9.25, MediaPipe 0.10.14, OpenCV 4.11.0, protobuf 4.25.9, NumPy 1.26.4,
pandas 2.3.3, and scikit-learn 1.6.1.

## Retrieve the supplied samples

```bash
python -m pip install gdown
mkdir -p data/raw/golftracker_samples
python -m gdown --folder \
  'https://drive.google.com/drive/folders/1TDUnGjP1wh1gZeN1EZdJOO4AeYuMLnkO' \
  --output data/raw/golftracker_samples
sha256sum data/raw/golftracker_samples/*
```

Compare the hashes with `data/manifests/manifest.yaml`. All 12 public files downloaded on
2026-11-03. Do not invent substitutes if the folder later becomes inaccessible.

## Inspect installed source

Run the same script with each environment:

```bash
./envs/swing-analyzer/bin/python scripts/inspect_packages.py swing-analyzer
./envs/golftracker/bin/python scripts/inspect_packages.py golftracker
./envs/golftrainer/bin/python scripts/inspect_packages.py golftrainer
```

## Execute the notebooks

Register one kernel per environment:

```bash
./envs/swing-analyzer/bin/python -m ipykernel install --user \
  --name swing-benchmark --display-name 'swing-analyzer benchmark'
./envs/golftracker/bin/python -m ipykernel install --user \
  --name tracker-benchmark --display-name 'golftracker benchmark'
./envs/golftrainer/bin/python -m ipykernel install --user \
  --name trainer-benchmark --display-name 'golftrainer benchmark'
```

Then execute in place:

```bash
./envs/swing-analyzer/bin/jupyter nbconvert --to notebook --execute \
  notebooks/benchmarks/01_swing_analyzer.ipynb --inplace \
  --ExecutePreprocessor.timeout=240 \
  --ExecutePreprocessor.kernel_name=swing-benchmark
./envs/golftracker/bin/jupyter nbconvert --to notebook --execute \
  notebooks/benchmarks/02_golftracker.ipynb --inplace \
  --ExecutePreprocessor.timeout=180 \
  --ExecutePreprocessor.kernel_name=tracker-benchmark
./envs/golftrainer/bin/jupyter nbconvert --to notebook --execute \
  notebooks/benchmarks/03_golftrainer.ipynb --inplace \
  --ExecutePreprocessor.timeout=180 \
  --ExecutePreprocessor.kernel_name=trainer-benchmark
./envs/swing-analyzer/bin/jupyter nbconvert --to notebook --execute \
  notebooks/benchmarks/10_pypi_package_comparison.ipynb --inplace \
  --ExecutePreprocessor.timeout=120 \
  --ExecutePreprocessor.kernel_name=swing-benchmark

# Repository-extension notebooks share the Python 3.11 environment.
for notebook in notebooks/benchmarks/0{4,5,6,7,8,9}_*.ipynb; do
  ./envs/swing-analyzer/bin/jupyter nbconvert --to notebook --execute \
    "$notebook" --inplace --ExecutePreprocessor.timeout=600 \
    --ExecutePreprocessor.kernel_name=python3
done
```

The first notebook probes the package's native H.264 writer failure, then uses
a runtime-only `mp4v` fallback without modifying site-packages. Package
comparison is substantially slower than the single pose pass because it
re-analyzes and rewrites both clips.

The broader literature and study-design documents are now organized under
`docs/research/`; the old Quarto deployment workflow was deliberately not migrated.
