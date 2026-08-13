# Roadmap / 路线图

Phased plan aligning the management update (framework + AI-warehouse demo) with a
clean shell-first, algorithm-second delivery.

## Phase 0 — Shell foundation ✅ (this repo)
- Three-layer architecture wired end-to-end.
- Warehouse synthetic generator (stdlib, deterministic, zero-dep).
- Application demo: KPIs, replenishment, anomaly, ABC, insights.
- Structural quality check (no statistical validation — by design).
- Docs: architecture, algorithm/data checklist, datasets, this roadmap.
- **Deliverable:** runnable demo + client checklist.

## Phase 1 — Presentable shell (client-facing demo)
- Front-end dashboard (Streamlit or React) over the FastAPI endpoints.
- Scenario controls: sliders for `GenerationSpec` (SKU count, demand, stockout).
- Export to CSV/Parquet; "what-if" replenishment view.
- **Deliverable:** the "像样的壳" — a polished, demoable product shell.

## Phase 2 — Introduce real/open data + real synthesis
- Ingest one open dataset (see `DATASETS.md`) through the registry.
- Swap generator internals for **SDV** (CTGAN/TVAE) fitted on the reference set.
- Add **SDMetrics** report → first real B1 fidelity numbers.
- **Deliverable:** synthetic data that is statistically validated, not just structural.

## Phase 3 — Real application algorithms
- Demand forecast (C1), (s,S) replenishment (C2), anomaly model (C3).
- TSTR validation (B2): prove models trained on synthetic transfer to real.
- Reuse vision pipeline for C5.
- **Deliverable:** core technical-capability validation results + report.

## Phase 4 — Framework hardening & reuse
- Knowledge graph + LLM insight layer (C6); trusted agent actions (C7).
- MLOps: feature store, model registry, experiment tracking (D1–D4).
- Prove portability: instantiate the framework for a second industrial scenario.
- **Deliverable:** reusable industrial-AI framework prototype + technical docs.

---

## Mapping to the committed deliverables (管理层交付物)
| Committed deliverable | Delivered in |
|-----------------------|--------------|
| 合成数据工业AI应用框架原型 | Phase 0 → hardened Phase 4 |
| AI + 仓库管理 Demo | Phase 1 (shell) → Phase 3 (validated) |
| 合成数据验证环境 | Phase 2 |
| 核心技术验证成果 + 技术文档 + 阶段报告 | Phase 3–4 (docs seeded from Phase 0) |

## Personal growth track (个人能力积累)
- **Framework/engineering:** Phase 0–1 (layered design, interfaces, MLOps seams).
- **Algorithms:** Phase 2–3 (generative models, forecasting, validation metrics).
- Keep the two tracks separable so each can be studied and demonstrated on its own.
