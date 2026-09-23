# PR 4 — Contracts: config validation, typed public functions, built-in generics

## Goal

Bring the code under `implementation-and-tests.instructions.md`: configuration
dataclasses validate themselves, public functions declare what they accept,
and type hints use the Python 3.12 built-in generics.

## Scope

- `GenerationSpec.__post_init__`: `n_skus >= 1`, `n_locations >= 1`,
  `horizon_days >= 1`, `abc_split` has three non-negative entries summing to
  1 (±1e-9), `0 <= express_ratio <= 1`, `0 <= stockout_pressure <= 1`,
  `daily_orders_per_a_sku > 0`; raise `ValueError` with the field name.
  `api/app.py` keeps its clamping (it is a UI convenience) but now relies on
  the spec for the invariant.
- `CostModel.__post_init__`: rates in `[0, 1]`, days `>= 1`, `service_z > 0`.
- `Step.__post_init__`: `name` non-empty and no self-dependency.
- Type the six duck-typed public parameters: `structural_quality_check(warehouse: SyntheticWarehouse)`,
  `financial_impact(intel: WarehouseIntelligence, cost_model: CostModel | None = None, ...)`,
  `daily_demand_series(orders: Iterable[OutboundOrder], ...)`,
  `hourly_business_series(orders: Iterable[OutboundOrder], ...)`,
  `build_series(orders: Iterable[OutboundOrder], ...)`,
  `tstr_report(orders: Iterable[OutboundOrder], ...)`.
- Replace `typing.List/Dict/Tuple/Optional` with `list/dict/tuple/X | None`
  across `src/sdf/` (21 files); `from __future__ import annotations` stays.
- Colocated tests for each new validation: one `pytest.mark.parametrize`
  per field with an invalid value asserting `ValueError` and the field name in
  the message, plus one test that the defaults validate.

## Non-goals

- No new configuration fields or options.
- No change to accepted default values, so every golden number stays.
- No `build_*_config()` normaliser yet: nothing in the repository constructs
  these dataclasses from mappings; add one when the first YAML/TOML caller
  appears.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                     # new validation tests pass; golden_test unchanged
uv run python -c "from sdf.synthesis.spec import GenerationSpec; GenerationSpec(n_skus=0)"   # ValueError naming n_skus
uv run sdf demo                   # output identical to the capture
```

## Version

`Version: PATCH 0.4.0 → 0.4.1` — stricter validation of inputs that were
already invalid, type annotations and generics; no capability change.
