# Algorithm & Data Checklist / 算法与数据清单

> **Purpose.** The framework in this repo demonstrates the full flow and effect with
> rule-based stand-ins. This document is the promised client deliverable: it
> states exactly **what algorithms and what data** are required to turn each
> stand-in into production capability. It is the contract between the
> *engineering framework* and the *algorithm research* track.
>
> 本文件即交付给客户的清单：说明将"可复用框架"升级为完整功能所需的**算法**与**数据**。

Legend — each row maps to a `# ALGORITHM-HOOK` / `# DATA-HOOK` marker in code.

---

## What the framework already demonstrates (v2)

So the "gap" is unambiguous, here is what the current framework shows working vs.
what each still needs. Everything in the "framework shows" column is visible in the
web dashboard (`sdf.api.app`) or the CLI.

| Capability in the demo | Framework shows | Still needs (see rows below) |
|------------------------|-------------|------------------------------|
| Synthetic warehouse world | full, seeded, live-regenerated | A1–A3 fitted models; B1–B4 validation |
| Real-data ingestion | UCI Online Retail II via adapter, end-to-end | full 2-year dataset for daily/weekly models |
| Demand forecast | baseline **+ real-data backtest** + **AR/seasonal model** (C1) + **forecaster plug-ins with intervals, backtested per SKU** against the exact distribution of a demand benchmark + **a gradient-boosted global forecaster with intervals** (on the dashboard's SKU chart) | DeepAR/TFT; full dataset to beat `snaive` |
| Synthesis fidelity (B1) | **measured**: baseline 78/100 **+ Gaussian-copula/SDMetrics 0.92** | CTGAN/TVAE for complex joints; DCR + detection (B3–B4) |
| Synthetic utility (B2) | **measured** TSTR ratio 0.90–1.00 (as useful as real) | rerun on full dataset + learned models |
| Replenishment (C2) | **(s,S) policy** + service-level selector + replayed comparison with a no-safety-stock policy | cost-based newsvendor + fitted lead-time demand |
| Vision stocktake | synthetic shelf-occupancy heatmap + vision-vs-book discrepancy | C5 counting/detection model; labelled shelf images |
| Anomaly detection (C3) | **seasonal-residual + robust-z** on demand, live | Isolation Forest / autoencoder over multivariate state |
| Knowledge Q&A (C6) | **grounded NL Q&A** over computed facts, live | LLM + knowledge graph (same grounding contract) |
| Trusted agent (C7) | **tool-using agent + audit trace + human-in-loop** | LLM tool-use planner (same tools/guardrails/log) |
| Causal effects (C8) | **simulated effects with intervals** (paired replicates) + **estimators scored against a known effect** (promotion benchmark) | DML / causal forests + sensitivity analysis; real promotion history |
| Data Intelligence Workflow | **explicit DAG** (ingest→validate→application→economics→report) + run record | Airflow/Dagster/Prefect runner (same Step contract) |
| Business economics | **counterfactual £** savings vs naive policy (stated assumptions) | client real unit costs + current policy |
| Synthetic-data privacy (B3) | **DCR / NNDR / clone-risk** metrics | full membership-inference + differential privacy |
| Scenario simulation | **what-if family** (promo/disruption/downturn), safety-stock re-sized | discrete-event / digital-twin simulator |
| Insights / KPIs | templated narrative + portfolio KPIs | richer LLM narratives |

> **Measured results** (B1 fidelity, B2 TSTR, C1 forecast) live in
> [`VALIDATION.md`](./VALIDATION.md). Run `synth`, `tstr`, `backtest` to reproduce.

---

## A. Synthetic data generation (Synthesis Layer)

| # | Capability | Framework stand-in (now) | Algorithm needed | Data needed |
|---|------------|----------------------|------------------|-------------|
| A1 | Tabular synthesis (SKU / inventory) | seeded stdlib sampler | **CTGAN / TVAE / Gaussian Copula (SDV)**, or Bayesian network | a real product + inventory table to fit distributions |
| A2 | Demand time series (outbound) | class-scaled Poisson draw | **TimeGAN / DoppelGANger / DeepAR**; intermittent demand: **Croston / TSB** | ≥1–2 yrs of dated order history |
| A3 | Multi-table consistency | independent per-entity gen | **SDV HMA / relational synthesizer** (keeps FKs & cross-table correlations) | linked orders↔inventory↔SKU tables |
| A4 | Multimodal (vision/IoT) synthesis | random scalar stub | **diffusion / GAN image synthesis**; sim engines (e.g. warehouse digital twin) | seed images + sensor logs |
| A5 | LLM script generation | `GenerationSpec` is hand-written | **LLM codegen** (spec → fitted generator code) + eval harness | few-shot examples of good generators |

## B. Synthetic data validation (Synthesis Layer)

> Deliberately **absent** in the framework (agreed: framework needs no validation).
> This is the algorithm-phase gate before any result is trusted.

| # | Validation dimension | Method | Data needed |
|---|----------------------|--------|-------------|
| B1 | Statistical fidelity | KS / Chi², correlation-matrix delta, **SDMetrics** report | real holdout set |
| B2 | ML utility | **TSTR** (train-on-synthetic, test-on-real) AUC/RMSE gap | labelled real task set |
| B3 | Privacy / leakage | **DCR**, nearest-neighbour distance, membership-inference | real training set |
| B4 | Detection test | "synthetic-vs-real" classifier AUC → 0.5 is ideal | mixed real+synthetic |

## C. AI Warehouse application (Application Layer)

| # | Function | Framework stand-in (now) | Algorithm needed | Data needed |
|---|----------|----------------------|------------------|-------------|
| C1 | Demand forecast | a gradient-boosted global forecaster with intervals (scikit-learn, or LightGBM with the `app` extra), beside per-SKU baselines with empirical-error intervals, all scored by a probabilistic backtest | **DeepAR / Temporal Fusion Transformer** on the full dataset | dated order history + calendar/promo features |
| C2 | Replenishment | (s,S) service-level policy, normal approximation | **cost-based (s,S) / newsvendor optimisation** on forecast + lead-time dist. | supplier lead times, holding/stockout costs |
| C3 | Anomaly detection | threshold rules | **Isolation Forest / autoencoder** over multivariate series | historical normal-operations data |
| C4 | Slotting / layout | random location assign | **assignment / bin-packing optimisation**, RL | pick paths, location geometry, order affinity |
| C5 | Vision (shelf/defect) | `vision_occupancy` stub | **CV detection/segmentation** (reuse fabric-defect pipeline) | labelled shelf/product images |
| C6 | Knowledge / insight | templated strings | **LLM + knowledge graph / RAG** over the entity graph | domain ontology + document corpus |
| C7 | Trusted agent actions | none | **tool-use agent + guardrails/verification** | action logs, business rules |
| C8 | Causal effect estimation | regression adjustment and IPW on a declared adjustment set, scored on a promotion benchmark with a known effect | **double machine learning with flexible learners, causal forests, sensitivity analysis for unobserved confounding** | real promotion or intervention history with its assignment rules |

## D. Platform / MLOps (cross-cutting)

| # | Concern | Framework | Production need |
|---|---------|-------|-----------------|
| D1 | Storage | in-memory lists | SQL / object store / **feature store** connectors behind the registry |
| D2 | Serving | CLI + optional FastAPI | model registry, batch + online inference |
| D3 | Data contracts | dataclasses with field checks | schema registry + validation (e.g. Great Expectations / Pandera) |
| D4 | Reproducibility | fixed seed | experiment tracking (MLflow/W&B), data & model versioning (DVC) |
| D5 | Front-end | JSON endpoints | dashboard (React/Streamlit) for the client demo |

## Where each item plugs into the code

Every place a real algorithm or real data plugs in is marked in the code as
``ALGORITHM-HOOK[<#>]`` or ``DATA-HOOK[<#>]`` with the row's number from the
tables above. The table below is generated from those markers, so it always
shows the current code; `src/sdf/hooks_test.py` fails when a marker names no
row or the table is stale. A row with no marker has no stand-in in the code yet.

<!-- sdf-hooks:begin -->
_Generated by `uv run sdf hooks --update-doc docs/ALGORITHM_AND_DATA_CHECKLIST.md`; do not edit by hand._

| # | Item | Algorithm hooks | Data hooks |
|---|---|---|---|
| A1 | Tabular synthesis (SKU / inventory) | `sdf/synthesis/bootstrap.py::BootstrapTable`<br>`sdf/synthesis/sdv_synth.py`<br>`sdf/synthesis/warehouse.py::WarehouseGenerator._gen_inventory` | — |
| A2 | Demand time series (outbound) | `sdf/synthesis/fit.py`<br>`sdf/synthesis/warehouse.py::WarehouseGenerator._gen_outbound` | — |
| A3 | Multi-table consistency | — | — |
| A4 | Multimodal (vision/IoT) synthesis | `sdf/simulation/intervention.py::SpecIntervention`<br>`sdf/synthesis/scenarios.py` | — |
| A5 | LLM script generation | — | — |
| B1 | Statistical fidelity | `sdf/cli.py::cmd_synth`<br>`sdf/validation/fidelity.py`<br>`sdf/validation/quality.py::structural_quality_check` | — |
| B2 | ML utility | `sdf/validation/quality.py::structural_quality_check`<br>`sdf/validation/tstr.py` | — |
| B3 | Privacy / leakage | `sdf/cli.py::cmd_privacy`<br>`sdf/validation/privacy.py`<br>`sdf/validation/quality.py::structural_quality_check` | — |
| B4 | Detection test | — | — |
| C1 | Demand forecast | `sdf/analytics/forecast.py`<br>`sdf/analytics/forecasters/boosted.py`<br>`sdf/analytics/forecasters/builtin.py`<br>`sdf/analytics/models.py`<br>`sdf/cli.py::cmd_backtest` | `sdf/simulation/benchmark.py::DemandBenchmark` |
| C2 | Replenishment | `sdf/analytics/demand.py::DemandProfile.variability`<br>`sdf/application/economics.py::financial_impact`<br>`sdf/simulation/outcome.py::SimulatedCost`<br>`sdf/simulation/policy.py::ServiceLevelPolicy` | `sdf/application/economics.py`<br>`sdf/application/economics.py::financial_impact`<br>`sdf/cli.py::cmd_impact`<br>`sdf/simulation/outcome.py::CostModel` |
| C3 | Anomaly detection | `sdf/analytics/anomaly.py`<br>`sdf/application/anomaly_rules.py::rule_anomalies` | — |
| C4 | Slotting / layout | — | — |
| C5 | Vision (shelf/defect) | `sdf/application/vision.py::stocktake_discrepancies` | `sdf/application/vision.py::shelf_occupancy_grid`<br>`sdf/synthesis/warehouse.py::WarehouseGenerator._gen_sensors` |
| C6 | Knowledge / insight | `sdf/application/knowledge.py`<br>`sdf/application/narrative.py::insights` | — |
| C7 | Trusted agent actions | `sdf/application/agent/__init__.py` | `sdf/application/agent/agent.py::WarehouseAgent._place_order` |
| C8 | Causal effect estimation | `sdf/analytics/causal/builtin.py::DifferenceInMeans`<br>`sdf/analytics/causal/builtin.py::Ipw`<br>`sdf/analytics/causal/builtin.py::RegressionAdjustment` | `sdf/simulation/benchmark.py::PromotionBenchmark` |
| D1 | Storage | — | — |
| D2 | Serving | `sdf/workflow/pipeline.py` | — |
| D3 | Data contracts | — | `sdf/foundation/schema.py` |
| D4 | Reproducibility | `sdf/observability.py` | — |
| D5 | Front-end | — | — |
<!-- sdf-hooks:end -->

---

## Minimum data to move from framework → credible algorithm demo

Ranked by leverage (see [`DATASETS.md`](./DATASETS.md) for concrete open sources):

1. **One real order history** (dated, per-SKU) — unlocks A2, B1–B4, C1, C2.
2. **A product/inventory master table** — unlocks A1, A3.
3. **Supplier lead-time records** — unlocks C2.
4. **A small labelled image set** (shelf or defect) — unlocks C5, reusing prior work.
5. **A domain glossary / SOP documents** — unlocks C6.

If none of the above is available internally yet, start with the open datasets
in `DATASETS.md`; they are sufficient to fit A1–A2 and validate B1–B4 end-to-end.
