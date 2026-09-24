# Engineer onboarding

A 10-minute path from clone to running the framework, its API, its tests and its
demos. For architecture see [`ARCHITECTURE.md`](ARCHITECTURE.md); for what a full
implementation still needs see
[`ALGORITHM_AND_DATA_CHECKLIST.md`](ALGORITHM_AND_DATA_CHECKLIST.md).

## 1. Requirements

- [uv](https://docs.astral.sh/uv/) (0.12.10 or newer). It provides Python **3.12 to 3.14**
  (`.python-version` pins 3.14; CI runs 3.12, 3.13 and 3.14) and installs the
  numerical core (numpy, scipy, scikit-learn) from `uv.lock`. pip is not supported.
- Optional extras (API server, statistical fidelity, deep synthesis, gradient
  boosting, causal inference) are declared in `pyproject.toml` and installed on demand.

## 2. Clone and sanity-check

```bash
git clone https://github.com/WZcit223/synthetic-data-framework.git
cd synthetic-data-framework

uv sync                      # environment + dev tools, locked to uv.lock
# End-to-end demo — generates a synthetic warehouse and prints a report.
uv run sdf demo
```

## 3. The CLI

All entry points go through the `sdf` console script (`uv run sdf ...`; `uv run sdf --help` lists them):

```bash
uv run sdf demo                 # end-to-end demo report
uv run sdf export out/          # write synthetic CSVs to out/
uv run sdf backtest [csv]       # walk-forward forecast backtest
uv run sdf synth [csv]          # fitted synthesis + fidelity
uv run sdf tstr [csv]           # train-on-synthetic / test-on-real
uv run sdf agent "should I reorder?"   # trusted agent + audit trace
uv run sdf pipeline             # DAG workflow run record
uv run sdf impact               # counterfactual £ economics
uv run sdf scenarios            # what-if scenario family
uv run sdf privacy [csv]        # DCR / NNDR / clone-risk
uv run sdf hooks                # where each checklist item plugs into the code
```

`[csv]` defaults to `data/sample_online_retail_ii.csv`. `agent` and `pipeline`
take `--audit-log PATH`, which appends the run's full log to a JSONL file: every
input and output whole, then a summary line. The trace they print is shortened
for reading.

## 4. The API + dashboard

```bash
uv sync --extra api
SDF_UI_DIR=ui uv run uvicorn sdf.api.app:app --reload
# open http://127.0.0.1:8000           → the dashboard, served from ui/
#      http://127.0.0.1:8000/api/v1/docs → the API and its OpenAPI schema
```

The backend is a JSON-only API under `/api/v1`; its OpenAPI schema
(`/api/v1/openapi.json`) is the contract with any UI. The UI in `ui/` is plain
HTML/JS (`index.html`, `app.js`, `style.css`) and reaches the backend only
through the `api()` helper in `app.js`. `SDF_UI_DIR=ui` (or
`create_app(ui_dir="ui")`) serves it at `/` for development; it can be hosted
anywhere else by setting `window.SDF_API_BASE` before `app.js` loads and allowing
its origin with `SDF_CORS_ORIGINS=https://ui.example` (comma-separated).

The API is stateful: `POST /api/v1/world` (JSON body: `n_skus`, `horizon_days`,
`daily_orders_per_a_sku`, `stockout_pressure`, `seed`) re-drives the synthetic
world; the other endpoints read from it. The world is an immutable snapshot
swapped in one step, so a request never mixes two worlds. Generation accepts
10–500 SKUs and 14–180 days (HTTP 422 outside those bounds; `GET
/api/v1/world/limits` reports them) and runs one at a time (HTTP 409 while
another runs). `create_app(limits=GenerateLimits(...))` builds an app with other
limits. `POST /api/v1/experiments` runs built-in interventions × policies ×
outcomes on the current world and returns tidy rows. The HTTP contract tests in
`src/sdf/api/app_test.py` need `uv sync --extra api`.

## 5. Tests and linting

```bash
uv run ruff check              # lint (config in pyproject.toml)
uv run ruff format --check     # formatting
uv run pytest                  # structural + validation tests
```

CI (`.github/workflows/ci.yml`) runs these on every PR into `main` with the `api`
extra installed (so the HTTP contract tests run), then `sdf demo`, then the
synthesis and CLI tests again with the `synthesis` extra.

## 6. Optional statistical extras

```bash
uv sync --extra synthesis         # copulas + sdmetrics (Gaussian-copula fidelity, SDMetrics)
uv sync --extra synthesis-deep    # sdv + faker (CTGAN/TVAE; pulls torch)
uv sync --extra app               # lightgbm
uv sync --extra causal            # econml, plus dowhy on Python 3.13 only (dowhy 0.14 does not support 3.14 yet)
```

These are lazy-imported; tests that need them **skip** cleanly when they are absent.

## 7. Making a change

Read [`../CONTRIBUTING.md`](../CONTRIBUTING.md). In short: branch from `main` as
`feature/<name>`, keep `ruff` and `pytest` green, open a PR. Implementation PRs
may auto-merge on green CI; architecture-level changes need a short written plan,
approved by the project lead, first.
