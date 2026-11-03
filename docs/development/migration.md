# Migration record

Migration date: 2026-11-03

Source repository: `golf-balance` at commit
`2fdd711ccbf9b460cdd94b4831ea81c1b012ea5e` (short form `2fdd711`).

Destination: <https://github.com/ThomasHSimm/open-swing-analysis>

## History method

The destination repository was empty. Its `main` branch was based directly on the
source `golf-balance` `main` tip, preserving all four existing commits as ancestors.
The reorganized benchmark and the source working tree's relevant uncommitted files
are added in a subsequent migration commit. No source history was rewritten and the
original checkout was not modified.

## Path mapping

| Source | Destination |
|---|---|
| `notebooks/*.ipynb` | `notebooks/benchmarks/*.ipynb` |
| `docs/package-review.md` | `docs/research/benchmarks/package-review.md` |
| `docs/reuse-map.md` | `docs/research/benchmarks/reuse-map.md` |
| `data/*manifest.yaml` | `data/manifests/` |
| `background/` | `docs/research/background/` |
| `literature/` | `docs/research/literature/` |
| `experiment/` | `docs/research/study-design/` |
| non-video `outputs/` | `outputs/` |
| benchmark Python utilities | `scripts/` |

The original benchmark README is retained at
`docs/research/benchmarks/golf-balance-benchmark-readme.md` for its environment and
sample-retrieval instructions.

## Deliberate exclusions

- `envs/`, caches, and bytecode: local, reproducible environments rather than source;
- `data/golftracker_samples/`: downloaded third-party videos, JSON, and pickles;
- generated MP4/MOV files: large reproducible outputs;
- model weights/checkpoints: licensing, size, and provenance require an explicit gate;
- `_site/` and the old GitHub Pages workflow: generated/obsolete Quarto deployment;
- no private or personal recording was discovered in the source tree.

Public source URLs, file hashes, repository commits, and licence findings are retained
in `data/manifests/` and the benchmark reports.
