# Architecture / 架构设计

## 1. Design principle: shell ⟂ algorithm

The single most important decision in this project is the **clean separation of
the engineering shell from the algorithm research**.

- **Shell (this repo, phase 1):** proves the *end-to-end flow* and the *user-facing
  effect*. It runs with zero heavy dependencies, uses deterministic rule-based
  stand-ins, and does **not** validate data quality or model accuracy.
- **Algorithm (phase 2+):** replaces each stand-in with a real model trained on
  real/open reference data, and introduces statistical validation.

Every place an algorithm eventually plugs in is marked in code with
`# ALGORITHM-HOOK`; every place real data plugs in is marked `# DATA-HOOK`.
The full list is in [`ALGORITHM_AND_DATA_CHECKLIST.md`](./ALGORITHM_AND_DATA_CHECKLIST.md).

This lets a coding agent build the shell fast and credibly now, while the
algorithm team works independently against a stable interface.

## 2. Three-layer platform

```
┌─────────────────────────────────────────────────────────────────┐
│  Operation / Application Layer   (src/sdf/application)           │
│  AI Warehouse Management demo:                                    │
│  KPIs · replenishment · anomaly · ABC · knowledge/insights        │
└───────────────▲──────────────────────────────────────────────────┘
                │  reads overlaid streams by entity type
┌───────────────┴──────────────────────────────────────────────────┐
│  Synthesis / Prediction Layer    (src/sdf/synthesis)             │
│  GenerationSpec (reference dataset + requirements)                 │
│  → generators → SyntheticWarehouse → quality report               │
└───────────────▲──────────────────────────────────────────────────┘
                │  materialises into canonical entities
┌───────────────┴──────────────────────────────────────────────────┐
│  Foundation Layer                (src/sdf/foundation)            │
│  Canonical entities (schema) + DataSourceRegistry                 │
│  overlay of many sources: synthetic | real | open-dataset         │
└───────────────────────────────────────────────────────────────────┘
```

### Foundation Layer
Defines the canonical entities (`SKU`, `Location`, `InventorySnapshot`,
`InboundOrder`, `OutboundOrder`, `SensorReading`) and a `DataSourceRegistry`.
The registry is the **multi-source overlay** seam: synthetic and real feeds are
interchangeable because both must satisfy the same schema. Swapping the
in-memory backing store for SQL / object storage / a feature store does not
change the interface the upper layers use.

### Synthesis / Prediction Layer
Turns a declarative `GenerationSpec` (the *reference dataset + generation
requirements*) into a full dataset. In the shell this is a seeded stdlib sampler.
In the real system the same spec drives a fitted generative model (SDV / CTGAN /
TimeGAN) or an LLM code-generation step, plus a real quality/validation stage.

### Application Layer
The AI Warehouse-Management demo. It consumes whatever the registry overlays and
produces four capability families that generalise to other industrial domains:
**data management, knowledge organisation, decision support, insight**. Each
"AI" function is a transparent rule-based stand-in today.

## 3. Why warehouse management is the first validation scenario
- Real internal business demand exists (fast feedback, real stakeholders).
- It exercises all four core capabilities, so it is representative of the wider
  industrial-AI framework — validating it validates the framework.
- It reuses prior multimodal/vision work (the `SensorReading.vision_occupancy`
  hook) rather than starting cold.

## 4. Data flow (one call)
`GenerationSpec` → `WarehouseGenerator.generate()` → `SyntheticWarehouse`
→ registered into `DataSourceRegistry` → `WarehouseIntelligence` reads streams →
KPIs / suggestions / insights. See `demo/run_demo.py`.
