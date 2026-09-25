# Synthetic Data System — Industrial AI Application Framework
# 合成数据工业 AI 框架（工程可复用框架）

[![CI](https://github.com/WZcit223/synthetic-data-framework/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/WZcit223/synthetic-data-framework/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.12--3.14-blue)

A three-layer industrial-AI framework that uses **synthetic data** to build and
demonstrate applications before real data is available. The first validation
scenario is **AI Warehouse Management**.

> **Framework-first philosophy.** This repo is the *engineering framework*: it proves the
> end-to-end flow and the user-facing effect with zero heavy dependencies and
> rule-based stand-ins. Where a full implementation needs real algorithms or data,
> the seam is marked `ALGORITHM-HOOK[<#>]` / `DATA-HOOK[<#>]` in code, where `<#>`
> is a row of [`docs/ALGORITHM_AND_DATA_CHECKLIST.md`](docs/ALGORITHM_AND_DATA_CHECKLIST.md);
> the checklist's generated index (`uv run sdf hooks`) shows where each row plugs in.

## Quickstart

The project is managed with [uv](https://docs.astral.sh/uv/); `uv sync` creates the
environment (Python 3.14 by default, numpy / scipy / scikit-learn core) and locks it to `uv.lock`:

```bash
uv sync
uv run sdf demo                      # end-to-end demo, prints report
uv run sdf export out/               # write synthetic CSVs
uv run sdf backtest                  # real-data forecast backtest
uv run sdf agent "reorder & impact?" # tool-using agent + audit trace
uv run sdf effects --intervention promo_spike   # an action's effect, with its interval
uv run sdf estimate --confounding 1   # causal estimators scored against a known effect
uv run sdf forecast --benchmark      # per-SKU forecasts with intervals, against the true distribution
```

The full command list is in [`docs/ONBOARDING.md`](docs/ONBOARDING.md).

Web dashboard: a UI in `ui/` over the versioned JSON API (`/api/v1`,
FastAPI; built with Svelte, Chart.js and Tabulator, and it works offline, as
the build bundles every asset). Building it needs Node 22:

```bash
uv sync --extra api
(cd ui && npm ci && npm run build)   # writes ui/dist
SDF_UI_DIR=ui/dist uv run uvicorn sdf.api.app:app --reload
# open http://127.0.0.1:8000 (dashboard), http://127.0.0.1:8000/explore.html (Explore),
# http://127.0.0.1:8000/effects.html (Effects)
# or http://127.0.0.1:8000/api/v1/docs (API)
```

The data behind the dashboard is also served as typed tables for exploration:
`GET /api/v1/datasets` lists them (order lines, inventory, SKUs, the
replenishment plan) with their fields, and `GET /api/v1/datasets/{name}` returns
one. Another package can add a table through the `sdf.datasets` entry-point
group.

The synthesis algorithms are served the same way: `GET /api/v1/synthesizers`
lists them with the parameters each takes, `GET /api/v1/synthesis/sources` the
sample data they can be fitted on, and `POST /api/v1/synthesis/runs` fits one and
returns its quality scores (fidelity for a series, privacy for a table) with the
real and synthetic data side by side. `POST /api/v1/world` accepts a
`synthesizer` that produces a warehouse, to build the world with it.

The **Synthesizers** page lists them, runs any series or table synthesizer on
the sample data with the parameters you choose, and shows its scores with real
and synthetic data charted together; "Open in Explore" pivots the same run. The
dashboard's **Generator** choice picks the synthesizer that builds the world.

The **Effects** page answers "what happens if we take this action": it runs an
effect study (`POST /api/v1/effects`) on the dashboard's current world, with the
interventions, policies, outcomes and replicates you choose, and draws each
effect with its confidence interval, one chart per metric. An interval that
covers 0 is greyed and labelled "not distinguishable from 0". The work budget is
the server's answer while you edit, the page address keeps the study, and "Open
in Explore" pivots the effects or every replicate's paired difference.

Its **Estimate from data** view scores causal estimators (`GET /api/v1/estimators`,
`POST /api/v1/causal/estimates`) on the promotion benchmark, whose true effect is
known: each estimator's estimate and interval against the truth, the adjustment
set to edit (drop `log_demand` and `abc_class` and the naive bias returns), and a
sweep of the bias as confounding grows. An estimator is a plug-in like a
synthesizer; [`docs/PLUGINS.md`](docs/PLUGINS.md) shows how to write, mount and
score one.

Forecasters are plug-ins too (`GET /api/v1/forecasters`,
`POST /api/v1/forecasts/backtest`, `sdf forecast`). Each forecasts every SKU's
next days with a mean and quantiles, and one backtest scores them all from the
same rolling origins: WAPE, bias, pinball loss, both interval coverages and
the ratio to seasonal naive. On the demand benchmark, whose process is
declared, a `true-distribution` row gives the same scores for the exact
distribution the data came from.
Writing your own synthesizer or dataset is described in
[`docs/PLUGINS.md`](docs/PLUGINS.md).

The **Explore** page pivots any of these tables, or the result of a policy
experiment: drag fields onto Rows, Columns, Values and Filters; choose the
aggregation (sum, count, distinct count, mean, median, min, max), the time grain
(day to year, or weekday) and how values show (as they are, or as a share of the
grand, row or column total); read the result as a table (subtotals, totals,
heatmap shading, sorting by any column) or as a chart; export it as CSV. The
whole view is kept in the page address, so a copied link reopens it.

The dashboard has two views: a **framework capability overview** (for management)
and a **replenishment deep dive**
(demand → demand profile → (s,S) levels at a service level → order → replayed fill rate
versus a no-safety-stock policy).
Sliders re-drive the `GenerationSpec` to regenerate the synthetic world live.

## Layers

```
Foundation  (src/sdf/foundation)  canonical entities + multi-source registry
Synthesis   (src/sdf/synthesis)   GenerationSpec → generators → quality report
Application (src/sdf/application)  AI warehouse demo: KPIs, replenishment, insight
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## What is a framework vs. what is an algorithm?

| In this repo (framework) | Deferred to algorithm phase |
|----------------------|-----------------------------|
| Seeded rule-based generators | Fitted generative models (SDV/CTGAN/TimeGAN) |
| Structural quality checks | Statistical fidelity / privacy / ML-utility validation |
| Trailing-average forecast, normal-approximation (s,S) replenishment | DeepAR / TFT forecasting + cost-based newsvendor |
| Templated insights | LLM + knowledge-graph reasoning |

## Development

`main` is the protected, always-releasable default branch; all work happens on
`feature/*` branches and merges via Pull Request. Before opening a PR:

```bash
uv sync                                                      # environment + pytest + ruff
uv run ruff check && uv run ruff format --check && uv run pytest   # CI runs the same on Python 3.12, 3.13 and 3.14
```

- **New engineers:** start with [`docs/ONBOARDING.md`](docs/ONBOARDING.md).
- **Coding agents and contributors:** [`AGENTS.md`](AGENTS.md) lists the repository rules
  (`.github/instructions/`) that every change must follow.
- **Contribution & PR policy:** [`CONTRIBUTING.md`](CONTRIBUTING.md) (implementation
  PRs may auto-merge on green CI; architecture changes need a short written plan,
  approved by the project lead, first).

## Documentation
- [Onboarding / 上手指南](docs/ONBOARDING.md)
- [Architecture / 架构](docs/ARCHITECTURE.md)
- [Algorithm & Data Checklist / 算法与数据清单](docs/ALGORITHM_AND_DATA_CHECKLIST.md)
- [Validation Results / 验证结果](docs/VALIDATION.md)
- [Reference & Open Datasets / 数据集](docs/DATASETS.md)
- [Plug-ins: your own synthesizer or dataset / 插件](docs/PLUGINS.md)
- [Roadmap / 路线图](docs/ROADMAP.md)
- [Refactor Preparation / 重构准备](docs/REFACTOR_PREP.md)
