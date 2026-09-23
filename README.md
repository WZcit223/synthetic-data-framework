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
> the seam is marked `# ALGORITHM-HOOK` / `# DATA-HOOK` in code and catalogued in
> [`docs/ALGORITHM_AND_DATA_CHECKLIST.md`](docs/ALGORITHM_AND_DATA_CHECKLIST.md).

## Quickstart

Install once (`pip install -e .`; the numerical core needs numpy, scipy and scikit-learn), then:

```bash
python demo/run_demo.py                          # end-to-end demo, prints report
PYTHONPATH=src python -m sdf.cli export out/     # write synthetic CSVs
PYTHONPATH=src python -m sdf.cli backtest        # real-data forecast backtest
PYTHONPATH=src python -m sdf.cli agent "reorder & impact?"  # tool-using agent + audit trace
```

The full command list is in [`docs/ONBOARDING.md`](docs/ONBOARDING.md).

Web dashboard (FastAPI + a dependency-free HTML page, works offline):

```bash
pip install ".[api]"
PYTHONPATH=src uvicorn sdf.api.app:app --reload
# open http://127.0.0.1:8000
```

The dashboard has two views: a **framework capability overview** (for management)
and a **replenishment closed-loop deep dive**
(demand → forecast → reorder point → suggested order → projected service level).
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
| Rule-based forecast & replenishment | DeepAR / TFT forecasting + (s,S) optimisation |
| Templated insights | LLM + knowledge-graph reasoning |

## Development

`main` is the protected, always-releasable default branch; all work happens on
`feature/*` branches and merges via Pull Request. Before opening a PR:

```bash
pip install -e ".[dev]"     # pytest + ruff
ruff check . && ruff format --check . && pytest   # CI runs the same on Python 3.12, 3.13 and 3.14
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
- [Roadmap / 路线图](docs/ROADMAP.md)
- [Refactor Preparation / 重构准备](docs/REFACTOR_PREP.md)
