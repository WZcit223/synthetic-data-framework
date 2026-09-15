# Engineer onboarding

A 10-minute path from clone to running the framework, its API, its tests and its
demos. For architecture see [`ARCHITECTURE.md`](ARCHITECTURE.md); for what a full
implementation still needs see
[`ALGORITHM_AND_DATA_CHECKLIST.md`](ALGORITHM_AND_DATA_CHECKLIST.md).

## 1. Requirements

- Python **3.9+** (CI runs 3.9 and 3.11). The core framework is **stdlib-only** —
  no install is required to run it.
- Optional extras (API server, statistical fidelity, deep synthesis) are declared
  in `pyproject.toml` and installed on demand.

## 2. Clone and sanity-check

```bash
git clone https://github.com/WZcit223/synthetic-data-framework.git
cd synthetic-data-framework

# End-to-end demo — generates a synthetic warehouse and prints a report.
python demo/run_demo.py
```

## 3. The CLI

All entry points go through `sdf.cli` (run with `PYTHONPATH=src`):

```bash
PYTHONPATH=src python -m sdf.cli demo                 # end-to-end demo report
PYTHONPATH=src python -m sdf.cli export out/          # write synthetic CSVs to out/
PYTHONPATH=src python -m sdf.cli backtest [csv]       # walk-forward forecast backtest
PYTHONPATH=src python -m sdf.cli synth [csv]          # fitted synthesis + fidelity
PYTHONPATH=src python -m sdf.cli tstr [csv]           # train-on-synthetic / test-on-real
PYTHONPATH=src python -m sdf.cli agent "should I reorder?"   # trusted agent + audit trace
PYTHONPATH=src python -m sdf.cli pipeline             # DAG workflow run record
PYTHONPATH=src python -m sdf.cli impact               # counterfactual £ economics
PYTHONPATH=src python -m sdf.cli scenarios            # what-if scenario family
PYTHONPATH=src python -m sdf.cli privacy [csv]        # DCR / NNDR / clone-risk
```

`[csv]` defaults to `data/sample_online_retail_ii.csv`.

## 4. The API + dashboard

```bash
pip install ".[api]"
PYTHONPATH=src uvicorn sdf.api.app:app --reload
# open http://127.0.0.1:8000  → the live dashboard (src/sdf/api/static/dashboard.html)
```

The API is stateful: `POST /generate` re-drives the synthetic world; the other
endpoints (`/application/*`, `/validation/*`, `/agent/*`, `/economics/*`,
`/workflow/*`, `/scenarios`) read from it.

## 5. Tests and linting

```bash
pip install -e ".[dev]"     # pytest + ruff
ruff check .                # lint (config in pyproject.toml)
pytest                      # structural + validation tests
```

CI (`.github/workflows/ci.yml`) runs exactly these on every PR into `main`.

## 6. Optional statistical extras

```bash
pip install ".[synthesis]"        # copulas + sdmetrics (Gaussian-copula fidelity, SDMetrics)
pip install ".[synthesis-deep]"   # sdv + faker (CTGAN/TVAE; pulls torch)
pip install ".[app]"              # scikit-learn + lightgbm
```

These are lazy-imported; tests that need them **skip** cleanly when they are absent.

## 7. Making a change

Read [`../CONTRIBUTING.md`](../CONTRIBUTING.md). In short: branch from `main` as
`feature/<name>`, keep `ruff` and `pytest` green, open a PR. Implementation PRs
may auto-merge on green CI; architecture-level changes need CTO sign-off first.
