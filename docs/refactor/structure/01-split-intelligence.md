# PR 1 — Split the analysis class into one module per concern

Interface contract: [`interfaces.md`](interfaces.md) (this PR adds no new public
interface; the facade keeps every public method).

## Goal

`WarehouseIntelligence` stops being one ~400-line class. Each concern lives in
its own module that takes only the data it needs, and the class becomes a thin
facade, so the web API, CLI and agent keep working unchanged.

## Scope

- New modules under `src/sdf/application/`, each a set of functions over the
  registry streams or a `DemandTable`:
  - `kpi.py` — `kpis`, `abc_distribution`, `top_movers`;
  - `replenishment.py` — the rule-based suggestions and their simulation, the
    (s,S) policy table, the service-level z lookup;
  - `anomaly_rules.py` — stockout / dead-stock rules and the demand-anomaly
    wrapper;
  - `vision.py` — shelf occupancy grid and stocktake discrepancies;
  - `narrative.py` — `insights`.
- `intelligence.py` keeps `KPISummary` and `WarehouseIntelligence`, whose
  methods delegate to those functions. Public method names, parameters and
  return values stay identical; private helpers move with their callers.
- `economics.py` and `knowledge.py` call the public facade or the new module
  functions, never a private member.
- Colocated tests move or are added so each new module has its own
  `<module>_test.py`.

## Non-goals

- No behaviour change, no removed method (the rule-based policy goes in PR 3).
- No simulation layer yet (PR 2).

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # golden_test and layering_test unchanged
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf demo | diff <capture-from-main> -           # byte-identical
wc -l src/sdf/application/intelligence.py              # facade only (well under 150 lines)
```

## Version

`Version: MINOR 0.8.0 → 0.9.0` — new application modules and import paths; no
behaviour change.
