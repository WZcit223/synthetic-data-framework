# PR 2 — Data contracts: validated records, typed workflow state

## Goal

The canonical entities reject values no warehouse can have, and the workflow's
steps share their data through a typed object instead of underscore keys.

## Scope

- `foundation/schema.py`: each entity validates its fields in `__post_init__`
  and raises `ValueError` naming the entity and field. Rules:
  - identifiers are non-empty strings;
  - quantities, capacities, costs, prices, weights and volumes are finite and
    not negative; order quantities are positive;
  - `SKU.abc_class` ∈ {A, B, C}; `shelf_life_days` is `None` or positive;
  - `OutboundOrder.channel`, `.priority`, `.status`, `InboundOrder.status` and
    `SensorReading.modality` are in the sets the schema documents;
  - `SensorReading.value` is finite.
  The allowed sets become module constants that the generator and the docs use.
- The synthetic generator and the retail CSV adapter produce only valid records;
  a CSV row that cannot become a valid record is counted in `LoadReport.skipped`
  under `invalid_record`.
- `workflow/pipeline.py`: `warehouse_pipeline` keeps its step outputs keyed by
  step name, as before, but shares the registry, the warehouse and the analysis
  facade through a `WarehouseRun` dataclass instead of `ctx["registry"]`,
  `ctx["_warehouse"]`, `ctx["_intel"]`. `Pipeline.run` refuses an initial context
  key that collides with a step name.
- Tests: one invalid value per rule is rejected with its field named; every
  record of the default world and of both bundled CSVs validates; the workflow
  run record is unchanged.

## Non-goals

- No schema registry or external validation library (checklist D3 stays the
  production answer).
- No change to which rows the adapter keeps on the bundled CSVs.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                                          # golden_test unchanged
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf demo | diff <main's output> -               # byte-identical
```

## Version

`Version: MINOR 1.1.0 → 1.2.0` — entity records reject invalid values and the
workflow's shared state changes shape.
