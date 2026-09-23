# Architecture / 架构设计

## 1. Design principle: framework ⟂ algorithm

The single most important decision in this project is the **clean separation of
the engineering framework from the algorithm research**.

- **Framework (this repo, phase 1):** proves the *end-to-end flow* and the *user-facing
  effect*. It runs on a small numerical core (numpy, scipy, scikit-learn), uses
  deterministic rule-based stand-ins, and does **not** validate data quality or
  model accuracy. Heavier backends (SDV, LightGBM, the pywhy causal stack) stay
  optional extras.
- **Algorithm (phase 2+):** replaces each stand-in with a real model trained on
  real/open reference data, and introduces statistical validation.

Every place an algorithm eventually plugs in is marked in code with
`# ALGORITHM-HOOK`; every place real data plugs in is marked `# DATA-HOOK`.
The full list is in [`ALGORITHM_AND_DATA_CHECKLIST.md`](./ALGORITHM_AND_DATA_CHECKLIST.md).

This lets a coding agent build the framework fast and credibly now, while the
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
requirements*) into a full dataset. In the framework this is a seeded stdlib sampler.
In the real system the same spec drives a fitted generative model (SDV / CTGAN /
TimeGAN) or an LLM code-generation step, plus a real quality/validation stage.

Every synthesis algorithm satisfies one contract (`synthesis/api.py`): a
`SynthesizerInfo` class attribute plus `fit(data)` and `sample(n, *, seed)`.
Every algorithm is a plug-in, ours included: `synthesis/registry.py` mounts
the `sdf.synthesizers` entry-point group, where this package declares its
built-ins — `warehouse-spec` (the spec-driven world generator),
`seasonal-profile` (a series fitted on real demand), `bootstrap-table` (a
per-column table bootstrap) and, with the `synthesis` extra, `gaussian-copula`.
Another installed package adds its own algorithm by declaring it in the same
group. Callers choose one by name, for example
`uv run sdf tstr --synthesizer seasonal-profile`; the contract is in
[`refactor/structure/interfaces.md`](refactor/structure/interfaces.md) §2.

### Application Layer
The AI Warehouse-Management demo. It consumes whatever the registry overlays and
produces four capability families that generalise to other industrial domains:
**data management, knowledge organisation, decision support, insight**. Each
"AI" function is a transparent rule-based stand-in today.

One module per concern: `kpi.py` (KPIs, ABC mix, top movers),
`replenishment.py`, `anomaly_rules.py`, `vision.py` and `narrative.py`.
`intelligence.py` is only a facade: `WarehouseIntelligence` holds the registry
and delegates to those modules, so the API, CLI and agent keep one stable object.

### Simulation layer
`src/sdf/simulation` sits between validation and the application layer, so it
can run without the facade (from a notebook, a workflow step or a future causal
module). It has four parts: a `World` (an immutable dataset), `Intervention`s
that change it, `Policy`s that make replenishment decisions on it, and
`Outcome`s that measure the result. An `Experiment` runs every
intervention × policy combination and returns tidy `OutcomeRow`s, one per
metric. The (s,S) plan, the economics counterfactual and the scenario runner
all run through it. The contract is in
[`refactor/structure/interfaces.md`](refactor/structure/interfaces.md) §1.

## 3. Why warehouse management is the first validation scenario
- Real internal business demand exists (fast feedback, real stakeholders).
- It exercises all four core capabilities, so it is representative of the wider
  industrial-AI framework — validating it validates the framework.
- It reuses prior multimodal/vision work (the `SensorReading.vision_occupancy`
  hook) rather than starting cold.

## 4. Data flow (one call)
`GenerationSpec` → the `warehouse-spec` synthesizer (`WarehouseGenerator`) → `SyntheticWarehouse`
→ registered into `DataSourceRegistry` → `WarehouseIntelligence` reads streams →
KPIs / suggestions / insights. See `cmd_demo` in `src/sdf/cli.py` (`uv run sdf demo`).
