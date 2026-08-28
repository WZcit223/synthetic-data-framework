# Roadmap / 路线图

Phased plan aligning the management update (framework + AI-warehouse demo) with a
clean framework-first, algorithm-second delivery.

## Phase 0 — Framework foundation ✅ (this repo)
- Three-layer architecture wired end-to-end.
- Warehouse synthetic generator (stdlib, deterministic, zero-dep).
- Application demo: KPIs, replenishment, anomaly, ABC, insights.
- Structural quality check (no statistical validation — by design).
- Docs: architecture, algorithm/data checklist, datasets, this roadmap.
- **Deliverable:** runnable demo + client checklist.

## Phase 1 — Presentable framework (client-facing demo) ✅
- Web dashboard (FastAPI + dependency-free HTML, inline SVG charts, offline).
- Two views: framework capability overview (management) + replenishment
  closed-loop deep dive (demand → forecast → reorder point → order → service level).
- Scenario controls: live sliders for `GenerationSpec` (SKU count, demand, stockout, seed).
- Vision stocktake view: synthetic shelf-occupancy heatmap + vision-vs-book
  discrepancy detection (DATA-HOOK for real images).
- CSV export of every synthetic entity.
- **Deliverable:** the "像样的可复用框架" — a polished, demoable product framework.

## Phase 2 — Introduce real/open data + real synthesis  🟡 started (2.0)
- ✅ Ingest an open dataset (UCI *Online Retail II* schema) via
  `foundation/adapters/retail_csv.py`; a runnable sample ships in `data/`.
- ✅ Real-data forecast **backtest** harness (MAE/RMSE/MAPE/bias, walk-forward);
  first measured numbers in [`VALIDATION.md`](./VALIDATION.md).
- ✅ Fitted synthesizer on real data (`synthesis/fit.py`) + dependency-free
  **fidelity** metrics: KS 0.14, profile-corr 0.90, score 78/100 (B1).
- ✅ **Gaussian copula** (SDV engine) + real **SDMetrics** (`synthesis/sdv_synth.py`):
  overall quality **0.916** on the real extract (see `VALIDATION.md`, B1 full).
- ⬜ CTGAN/TVAE (adds torch) for complex joints; privacy (DCR) + detection AUC (B3–B4).
- **Deliverable:** synthetic data that is statistically validated, not just structural.

## Phase 3 — Real application algorithms  🟡 started
- ✅ Real forecasting model (C1): AR + seasonal OLS (`synthesis/models.py`),
  verified to beat baselines on trend/noise data; in the backtest harness + dashboard.
- ✅ **TSTR** validation (B2): synthetic-trained ≈ real-trained, ratio 0.90–1.00
  (`synthesis/tstr.py`, `VALIDATION.md`).
- ✅ (s,S) replenishment optimisation (C2): safety stock from demand variability +
  service level; live service-level selector in the dashboard (see `VALIDATION.md`).
- ✅ Anomaly detection (C3): seasonal-residual + robust-z on the demand series;
  live in the dashboard. DeepAR/TFT for C1 and Isolation-Forest for C3 remain hooks.
- ✅ Full 13-month real dataset run: model wins by 26%, fidelity 88/0.92, TSTR 1.04
  (see `VALIDATION.md` headline).
- ⬜ Reuse vision pipeline for C5 (real images).
- **Deliverable:** core technical-capability validation results + report.

## Phase 4 — Framework hardening & reuse
- ✅ Grounded knowledge Q&A (C6): NL questions → computed facts (dependency-free);
  live "Ask the warehouse". ⬜ upgrade to LLM + knowledge graph; trusted agent actions (C7).
- MLOps: feature store, model registry, experiment tracking (D1–D4).
- Prove portability: instantiate the framework for a second industrial scenario.
- **Deliverable:** reusable industrial-AI framework prototype + technical docs.

---

## Deliverables 
| Committed deliverable | Delivered in |
|-----------------------|--------------|
| 合成数据工业AI应用框架原型 | Phase 0 → hardened Phase 4 |
| AI + 仓库管理 Demo | Phase 1 (framework) → Phase 3 (validated) |
| 合成数据验证环境 | Phase 2 |
| 核心技术验证成果 + 技术文档 + 阶段报告 | Phase 3–4 (docs seeded from Phase 0) |
