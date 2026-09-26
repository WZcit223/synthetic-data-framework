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
uv run sdf effects --intervention promo_spike   # effects with intervals over paired replicates
uv run sdf estimate --confounding 1   # estimators scored on the promotion benchmark
uv run sdf forecast [--benchmark]     # forecasters backtested per SKU, with intervals
uv run sdf privacy [csv]        # DCR / NNDR / clone-risk
uv run sdf hooks                # where each checklist item plugs into the code
uv run sdf data add FILE --name NAME [--role time=COL] [--kind COL=KIND] [--time-format COL=FMT]
uv run sdf data list | show NAME | remove NAME   # your own data sources
uv run sdf privacy --source NAME [--columns A,B] [--rows sample|first] [--param k=v]
uv run sdf synth --source NAME [--param k=v]    # also sdf tstr --source NAME
```

`sdf data add` infers the schema of a CSV (comma or semicolon, UTF-8, a header
row) and checks every row. A date column whose day and month order cannot be
told apart (every sampled day is at most 12) is refused with the two
`--time-format` choices to add it again with. Sources are kept in
`$SDF_DATA_DIR/sources` (default `data/sources`, gitignored).

`[csv]` defaults to `data/sample_online_retail_ii.csv`. `agent` and `pipeline`
take `--audit-log PATH`, which appends the run's full log to a JSONL file: every
input and output whole, then a summary line. The trace they print is shortened
for reading.

## 4. The API + dashboard

```bash
uv sync --extra api
(cd ui && npm ci && npm run build)   # Node 22; writes ui/dist
SDF_UI_DIR=ui/dist uv run uvicorn sdf.api.app:app --reload
# open http://127.0.0.1:8000           → the dashboard, served from ui/dist
#      http://127.0.0.1:8000/api/v1/docs → the API and its OpenAPI schema
```

The UI has five pages: the dashboard, Explore (pivot any table), Synthesizers
(run and score a synthesizer), Effects (simulate an action, or estimate one
from data) and Forecasts (backtest forecasters per SKU, with intervals). A
page's address holds its request, so a link reproduces what it shows:
`forecasts.html#backtest=<the request as JSON, URL-encoded>`, for example
`{"forecasters": ["seasonal-naive", "moving-average"], "source": "benchmark",
"horizon": 14, "origins": 4, "level": 0.8}`, runs that backtest when opened.
Effects uses `#request=` and `#estimate=` the same way, and Explore
`#view=`, which each page's "Open in Explore" links write.

The backend is a JSON-only API under `/api/v1`; its OpenAPI schema
(`/api/v1/openapi.json`) is the contract with any UI. The UI in `ui/` is built
with Vite, Svelte, Chart.js and Tabulator (see
[`refactor/frontend/`](refactor/frontend/00-overview.md)) and reaches the
backend only through the `api()` helper in `ui/src/lib/api.js`.
`SDF_UI_DIR=ui/dist` (or `create_app(ui_dir="ui/dist")`) serves the built UI at
`/`; it can be hosted anywhere else by setting `window.SDF_API_BASE` before the
page's script loads and allowing its origin with
`SDF_CORS_ORIGINS=https://ui.example` (comma-separated).

Working on the UI, in `ui/`:

```bash
npm ci              # once, and after package-lock.json changes
npm run dev         # http://127.0.0.1:5173, /api proxied to the API on port 8000
npm test            # unit tests of the pure modules (Vitest)
npm run check       # svelte-check
npm run build       # ui/dist
npm run e2e         # page tests in Chromium; starts the API itself on ui/dist
```

`npm run e2e` needs Playwright's Chromium (`npx playwright install chromium`);
`SDF_E2E_CHROMIUM=/path/to/chrome` uses an installed one instead.

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

Data sources (`docs/refactor/userdata/interfaces.md` §1): `GET /api/v1/sources`
lists them with the upload limits; `POST /api/v1/sources?name=NAME` with a CSV
body (`text/csv`) adds one (201; 409 when the name is taken or reserved, or
the store holds 20 user sources; 413 over 200 MB, refused as the body
arrives, or over 2,000,000 rows or 64 columns, refused when the file is read;
422 when it cannot be read);
`PUT /api/v1/sources/{name}/schema` corrects kinds, formats and roles and
re-checks every row; `DELETE` removes a user source (the bundled ones are
read-only). A ready source is also the dataset `source-<name>`: a source larger
than one answer (250,000 rows or 2,000,000 cells) answers a uniform sample
with `sampled: true`. `create_app(sources=SourceStore(root, limits=...))`
builds an app on another store or with other limits.

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
