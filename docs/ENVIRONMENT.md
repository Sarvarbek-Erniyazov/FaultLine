# Environment

There is one supported environment: **uv, installing exactly what `uv.lock` records.**
`python -m venv` plus `pip` still works as a fallback, but nothing is promised for it:
it resolves versions fresh on every install, so two machines drift apart.

## Set up

```bash
uv sync --extra dev        # creates .venv from uv.lock; installs the package editable
pre-commit install
uv run faultline --help
uv run pytest -q
```

`uv sync` never re-resolves. It installs the versions in `uv.lock` or fails. To change a
dependency, edit `pyproject.toml`, run `uv lock`, and commit both files together. A lock
that changes without its `pyproject.toml` change, or the reverse, is a review finding.

## Why the lock is committed

`uv.lock` first turned up as a by-product of running uv, not as a decision. It is now
committed on purpose, for the same reason every run config is: a number in a report has
to trace back to a config hash and a git SHA (docs/ROADMAP.md, M1). Once a trained model
exists, the library versions behind it are part of that trace. torch 2.13 and 2.14 differ
in kernels, and pandas 2 and 3 differ in how a missing value survives `astype(str)`; this
repository has already shipped a fix for the second one (`src/faultline/data/telemetry/inspect.py`).

## torch and CUDA

| item | value | where it is recorded |
| --- | --- | --- |
| GPU | NVIDIA GeForce RTX 4060, 8 GB | `nvidia-smi`, 2026-09-10 |
| driver | 616.56, CUDA UMD 13.4 | `nvidia-smi`, 2026-09-10 |
| torch | 2.14.0, CUDA 13.2 build (`+cu132`) | `uv.lock` |
| wheel index | `https://download.pytorch.org/whl/cu132`, used for torch only | `[tool.uv.sources]` in `pyproject.toml` |

A driver runs any CUDA runtime up to its own version. cu132 is the newest CUDA build
published for torch 2.14 and it is at or below the driver's 13.4, so it is the build that
matches this driver. If the driver is downgraded below CUDA 13.2, `torch.cuda.is_available()`
turns `False` without an error message. Check it before blaming a model:

```bash
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

The lock covers Windows and Linux only (`[tool.uv] environments`), because the CUDA index
publishes no macOS wheel. Tests need no GPU and never import torch, so the test suite still
runs under 60 seconds on a CPU-only machine.

## Data root

Set `FAULTLINE_DATA_ROOT` (`.env.example`) to keep the archives off the repository drive.
Nothing under `data/raw`, `data/cleaned`, `data/filtered` or `data/final` is ever committed.
A pre-commit hook blocks it.
