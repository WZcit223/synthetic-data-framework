# PR 3 — Module layout: `analytics/`, `validation/`, `intelligence.py`, one demand aggregation

> Status: implemented (layout sequence PR 3). Acceptance commands below pass;
> golden numbers and `sdf demo` output unchanged. Two deviations from the text
> below, found during implementation: (1) `analytics` ranks *below* `synthesis`
> in `layering_test.py`, because `synthesis/fit.py` consumes
> `analytics.forecast.hourly_business_series` while nothing in `analytics`
> needs a generator — the order that matches the code is
> `foundation < analytics < synthesis < validation < application < entry points`;
> (2) `intelligence.demand_series` keeps listing only the days on which the SKU
> shipped (filtered from the dense table), because zipping the dense axis would
> change the history and the trailing-14-day forecast of the `/demand` endpoint.

## Goal

Put each module in a package whose name says what it is, and replace the five
copies of "per-SKU daily demand aggregation" with one implementation that the
others call.

## Scope

### Moves (pure, `git mv`, call sites updated in the same PR)

| From | To |
|---|---|
| `synthesis/forecast.py` | `analytics/forecast.py` |
| `synthesis/models.py` | `analytics/models.py` |
| `synthesis/anomaly.py` | `analytics/anomaly.py` |
| `synthesis/quality.py` | `validation/quality.py` |
| `synthesis/fidelity.py` | `validation/fidelity.py` |
| `synthesis/tstr.py` | `validation/tstr.py` |
| `synthesis/privacy.py` | `validation/privacy.py` |
| `application/warehouse_demo.py` | `application/intelligence.py` |

Colocated tests move with their modules. `synthesis/__init__.py`,
`analytics/__init__.py` and `validation/__init__.py` export nothing beyond a
docstring (no re-exports, so the layering test sees real edges).
`layering_test.py` gains the ranking
`foundation < analytics < synthesis < validation < application < entry points`
(see the status note above for why `analytics` sits below `synthesis`).

### One demand aggregation

New `analytics/demand.py`, the only place that turns `OutboundOrder` rows into
per-SKU daily series:

```python
@dataclass(frozen=True)
class DemandTable:
    days: tuple[date, ...]                       # sorted, dense from first to last order day
    series: dict[str, tuple[float, ...]]          # sku_id -> quantity per day, len == len(days)

    @classmethod
    def from_orders(cls, orders: Iterable[OutboundOrder], *, include_cancelled: bool = False) -> "DemandTable": ...
    def total(self) -> tuple[float, ...]: ...      # sum over SKUs per day
    def mean(self, sku_id: str) -> float: ...      # over all days (zeros included)
    def std(self, sku_id: str) -> float: ...       # population std over all days
```

Callers replaced by it, with their **current** semantics preserved exactly
(so golden numbers do not move):

- `intelligence._daily_demand` → `{sku: table.mean(sku)}` (it already divides
  by the number of distinct order days, which equals `len(table.days)` only
  when every day has at least one order; where the two differ, keep the
  current divisor by exposing `DemandTable.active_days` and using it here).
- `intelligence.sku_daily_stats` → `(table.mean(sku), table.std(sku))`.
- `intelligence.demand_series` → `table.series[sku]` zipped with `table.days`.
- `economics.financial_impact` → `table.series[sku]` for the per-SKU
  simulation; its `[:max_skus]` truncation keeps first-appearance order.
- `analytics.forecast.daily_demand_series` → `table.total()`.

Any place where the five copies genuinely disagree is listed in the PR
description with the golden number it would move if unified; the PR keeps the
current value and leaves the unification of semantics to the step-3 numerics
PR in `REFACTOR_PREP.md` §5.

## Non-goals

- No split of `WarehouseIntelligence` into services.
- No change to `hourly_business_series` / `build_series` beyond the move.
- No numpy port.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                     # golden_test unchanged; layering_test with the extended ranking
git diff --stat main -- src       # every moved file shows as a rename (similarity ≥ 90 %)
uv run sdf demo                   # output identical to the capture
```

## Version

`Version: MINOR 0.3.0 → 0.4.0` — module paths change for eight modules and a
new `analytics.demand` module is added; no documented public interface changes.
