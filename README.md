# Synthetic Data System — Industrial AI Application Framework
# 合成数据工业 AI 框架（工程可复用框架）

A three-layer industrial-AI framework prototype that uses **synthetic data** to
build and demonstrate applications before real data is available. The first
validation scenario is **AI Warehouse Management**.

> **Framework-first philosophy.** This repo is the *engineering framework*: it proves the
> end-to-end flow and the user-facing effect with zero heavy dependencies and
> rule-based stand-ins. It intentionally does **no** data/algorithm validation.
> What a full implementation additionally requires (algorithms + data) is
> catalogued in [`docs/ALGORITHM_AND_DATA_CHECKLIST.md`](docs/ALGORITHM_AND_DATA_CHECKLIST.md).

## Quickstart

No install required (pure Python 3.9+ stdlib):

```bash
python demo/run_demo.py            # end-to-end demo, prints report
PYTHONPATH=src python -m sdf.cli export out/     # write synthetic CSVs
PYTHONPATH=src python -m sdf.cli backtest        # Phase 2: real-data forecast backtest
PYTHONPATH=src python -m sdf.cli synth           # Phase 2.1: fitted synthesis + fidelity
PYTHONPATH=src python -m sdf.cli tstr            # Phase 3: train-on-synthetic, test-on-real
PYTHONPATH=src python -m sdf.cli sdv <csv>       # Phase 2.1 full: Gaussian-copula + SDMetrics
python tests/test_generators.py    # run framework tests
```

Web dashboard (FastAPI + a dependency-free HTML page, works offline):

```bash
pip install fastapi uvicorn
PYTHONPATH=src uvicorn sdf.api.app:app --reload
# open http://127.0.0.1:8000
```

The dashboard has two views: a **framework capability overview** (for
management) and a **replenishment closed-loop deep dive**
(demand → forecast → reorder point → suggested order → projected service level).
Sliders re-drive the `GenerationSpec` to regenerate the synthetic world live.

## Layers

```
Foundation  (src/sdf/foundation)  canonical entities + multi-source registry
Synthesis   (src/sdf/synthesis)   GenerationSpec → generators → quality report
Application (src/sdf/application)  AI warehouse demo: KPIs, replenishment, insight
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design and
[`docs/ROADMAP.md`](docs/ROADMAP.md) for the phased plan.

## What is a framework vs. what is an algorithm?

| In this repo (framework) | Deferred to algorithm phase |
|----------------------|-----------------------------|
| Seeded rule-based generators | Fitted generative models (SDV/CTGAN/TimeGAN) |
| Structural quality checks | Statistical fidelity / privacy / ML-utility validation |
| Rule-based forecast & replenishment | DeepAR / TFT forecasting + (s,S) optimisation |
| Templated insights | LLM + knowledge-graph reasoning |

Every deferred item is marked `# ALGORITHM-HOOK` / `# DATA-HOOK` in code and
listed in the checklist.

## Documentation
- [Architecture / 架构](docs/ARCHITECTURE.md)
- [Algorithm & Data Checklist / 算法与数据清单](docs/ALGORITHM_AND_DATA_CHECKLIST.md)
- [Validation Results / 验证结果](docs/VALIDATION.md)
- [Demo Script / 演示讲稿](docs/DEMO_SCRIPT.md)
- [Reference & Open Datasets / 数据集](docs/DATASETS.md)
- [Roadmap / 路线图](docs/ROADMAP.md)
