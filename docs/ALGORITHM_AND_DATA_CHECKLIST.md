# Algorithm & Data Checklist / 算法与数据清单

> **Purpose.** The shell in this repo demonstrates the full flow and effect with
> rule-based stand-ins. This document is the promised client deliverable: it
> states exactly **what algorithms and what data** are required to turn each
> stand-in into production capability. It is the contract between the
> *engineering shell* and the *algorithm research* track.
>
> 本文件即交付给客户的清单：说明将"壳"升级为完整功能所需的**算法**与**数据**。

Legend — each row maps to a `# ALGORITHM-HOOK` / `# DATA-HOOK` marker in code.

---

## A. Synthetic data generation (Synthesis Layer)

| # | Capability | Shell stand-in (now) | Algorithm needed | Data needed |
|---|------------|----------------------|------------------|-------------|
| A1 | Tabular synthesis (SKU / inventory) | seeded stdlib sampler | **CTGAN / TVAE / Gaussian Copula (SDV)**, or Bayesian network | a real product + inventory table to fit distributions |
| A2 | Demand time series (outbound) | class-scaled Poisson draw | **TimeGAN / DoppelGANger / DeepAR**; intermittent demand: **Croston / TSB** | ≥1–2 yrs of dated order history |
| A3 | Multi-table consistency | independent per-entity gen | **SDV HMA / relational synthesizer** (keeps FKs & cross-table correlations) | linked orders↔inventory↔SKU tables |
| A4 | Multimodal (vision/IoT) synthesis | random scalar stub | **diffusion / GAN image synthesis**; sim engines (e.g. warehouse digital twin) | seed images + sensor logs |
| A5 | LLM script generation | `GenerationSpec` is hand-written | **LLM codegen** (spec → fitted generator code) + eval harness | few-shot examples of good generators |

## B. Synthetic data validation (Synthesis Layer)

> Deliberately **absent** in the shell (agreed: shell needs no validation).
> This is the algorithm-phase gate before any result is trusted.

| # | Validation dimension | Method | Data needed |
|---|----------------------|--------|-------------|
| B1 | Statistical fidelity | KS / Chi², correlation-matrix delta, **SDMetrics** report | real holdout set |
| B2 | ML utility | **TSTR** (train-on-synthetic, test-on-real) AUC/RMSE gap | labelled real task set |
| B3 | Privacy / leakage | **DCR**, nearest-neighbour distance, membership-inference | real training set |
| B4 | Detection test | "synthetic-vs-real" classifier AUC → 0.5 is ideal | mixed real+synthetic |

## C. AI Warehouse application (Application Layer)

| # | Function | Shell stand-in (now) | Algorithm needed | Data needed |
|---|----------|----------------------|------------------|-------------|
| C1 | Demand forecast | avg daily demand | **DeepAR / Temporal Fusion Transformer / LightGBM** | dated order history + calendar/promo features |
| C2 | Replenishment | fixed safety-stock rule | **(s,S) / newsvendor optimisation** on forecast + lead-time dist. | supplier lead times, holding/stockout costs |
| C3 | Anomaly detection | threshold rules | **Isolation Forest / autoencoder** over multivariate series | historical normal-operations data |
| C4 | Slotting / layout | random location assign | **assignment / bin-packing optimisation**, RL | pick paths, location geometry, order affinity |
| C5 | Vision (shelf/defect) | `vision_occupancy` stub | **CV detection/segmentation** (reuse fabric-defect pipeline) | labelled shelf/product images |
| C6 | Knowledge / insight | templated strings | **LLM + knowledge graph / RAG** over the entity graph | domain ontology + document corpus |
| C7 | Trusted agent actions | none | **tool-use agent + guardrails/verification** | action logs, business rules |

## D. Platform / MLOps (cross-cutting)

| # | Concern | Shell | Production need |
|---|---------|-------|-----------------|
| D1 | Storage | in-memory lists | SQL / object store / **feature store** connectors behind the registry |
| D2 | Serving | CLI + optional FastAPI | model registry, batch + online inference |
| D3 | Data contracts | dataclasses | schema registry + validation (e.g. Great Expectations / Pandera) |
| D4 | Reproducibility | fixed seed | experiment tracking (MLflow/W&B), data & model versioning (DVC) |
| D5 | Front-end | JSON endpoints | dashboard (React/Streamlit) for the client demo |

---

## Minimum data to move from shell → credible algorithm demo

Ranked by leverage (see [`DATASETS.md`](./DATASETS.md) for concrete open sources):

1. **One real order history** (dated, per-SKU) — unlocks A2, B1–B4, C1, C2.
2. **A product/inventory master table** — unlocks A1, A3.
3. **Supplier lead-time records** — unlocks C2.
4. **A small labelled image set** (shelf or defect) — unlocks C5, reusing prior work.
5. **A domain glossary / SOP documents** — unlocks C6.

If none of the above is available internally yet, start with the open datasets
in `DATASETS.md`; they are sufficient to fit A1–A2 and validate B1–B4 end-to-end.
