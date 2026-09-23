# PR 2 — Simulation layer: world, policies, interventions, outcomes, experiments

Interface contract: [`interfaces.md` §1](interfaces.md#1-simulation-layer-sdfsimulation--f2).

## Goal

Introduce `sdf.simulation` as its own layer and run every existing simulation
through it, so one dataset can be combined with any set of interventions,
policies and outcomes. Numbers do not change.

## Scope

- New package `src/sdf/simulation/` exactly as in the contract:
  - `world.py` — `World` (immutable registry + spec + label), `World.generate`,
    `stream`, `demand`, `with_stream`;
  - `policy.py` — `Levels`, `Policy` protocol, `ServiceLevelPolicy`,
    `NaivePolicy`, `PlanRow`, `plan_orders`; the z lookup moves here;
  - `engine.py` — `simulate_inventory`, `InventoryTrace` (extracted from
    `economics._simulate`, cost arithmetic removed);
  - `intervention.py` — `Intervention` protocol, `Baseline`,
    `SpecIntervention` (with `named()` over `synthesis.scenarios.SCENARIOS`);
  - `outcome.py` — `Outcome` protocol, `CostModel` (moved from
    `application/economics.py`), `ReplenishmentNeed`, `ActiveStockouts`,
    `SimulatedCost`, `OutboundVolume`;
  - `experiment.py` — `Experiment`, `OutcomeRow`.
- Migrations, with signatures and return values unchanged:
  - `WarehouseIntelligence.replenishment_ss_policy` builds its table from
    `plan_orders(world, ServiceLevelPolicy(...))`;
  - `economics.financial_impact` is computed from an `Experiment` with
    `NaivePolicy` versus `ServiceLevelPolicy` and `SimulatedCost`;
  - `application.scenarios.run_scenarios` is an `Experiment` over
    `SpecIntervention`s.
- `layering_test.py` ranks `simulation` between `validation` and `application`
  (`… validation 3 · simulation 4 · application 5 · workflow 6 · api 7 · cli 7`)
  and checks that importing `sdf.simulation.experiment` does not load
  `sdf.application`.
- Tests: `world_test`, `policy_test` (including the contract's `FixedCoverPolicy`
  example), `engine_test` (same trace as the old `_simulate` on fixed inputs),
  `intervention_test` (including `DropExpressOrders`), `experiment_test` (row
  shape; the contract's §1.5 example runs).

## Non-goals

- No change to which callers use the rule-based suggestions (PR 3).
- No causal estimator, no new intervention or policy beyond the contract.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # golden_test unchanged; contract examples run as tests
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf demo | diff <capture-from-main> -           # byte-identical
```

## Version

`Version: MINOR 0.9.0 → 0.10.0` — new `sdf.simulation` layer; `CostModel`
changes import path.
