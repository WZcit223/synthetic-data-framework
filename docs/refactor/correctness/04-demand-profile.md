# PR 4 — Demand profile: variability that fits the demand shape

## Goal

Safety stock uses a variability measure that reflects how an SKU actually
sells, and every daily demand rate in the package uses the same day count.

## Scope

- `analytics/demand.py`:
  - `DemandTable.zero_ratio(sku_id)` — share of days with no demand.
  - `DemandProfile` (frozen dataclass: `mean`, `std`, `zero_ratio`) with
    `is_intermittent` (`zero_ratio > 0.5`) and `variability`
    (`std` for smooth SKUs, `max(std, mean / (1 − zero_ratio))` for
    intermittent ones — see the overview, decision 2).
  - `DemandTable.profile(sku_id) -> DemandProfile`.
- `WarehouseIntelligence.demand_profiles() -> dict[str, DemandProfile]`
  replaces `sku_daily_stats()` (no alias). `replenishment_ss_policy` sizes
  safety stock with `profile.variability` and reports how many flagged SKUs
  are intermittent.
- `economics.financial_impact` sizes its "ours" policy with the same
  `profile.variability`, so the counterfactual matches the policy the
  dashboard shows.
- **One daily-rate convention.** Daily demand rates divide by the number of
  calendar days in the table (`len(table.days)`), everywhere:
  `_daily_demand` and `financial_impact.horizon_days` stop using
  `active_days`. On the default world both counts are 90, so the rule-based
  numbers do not move; on sparse data they become calendar-day rates.
  `DemandTable.active_days` stays for reporting.
- An `ALGORITHM-HOOK[C2]` comment at the variability rule points to
  Croston/TSB as the model-based replacement.
- Regenerate `docs/VALIDATION.md`; explain in the C2 section why the (s,S)
  numbers changed (intermittent SKUs now buffered for their typical order
  size).
- Update the moved `golden_test.py` literals and list each one in the PR
  description.

## Expected moved numbers

- (s,S) at 90/95/99 %: SKUs needing an order and total safety stock.
- Economics: unmet units for "ours", units avoided, annualised saving.
- Scenario table: SKUs needing an order, safety stock and the percentage
  versus baseline.
- Rule-based replenishment, KPIs, anomalies, backtests, fidelity, TSTR and
  privacy do not move.

## Non-goals

- No Croston/TSB forecast, no change to the rule-based suggestions' formula.
- No `ReplenishmentPolicy` interface (structural sequence).

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                     # demand_test covers profile/variability; golden_test updated only for the listed numbers
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf demo                   # only lines derived from (s,S) may differ; the demo prints none today
```

## Version

`Version: MINOR 0.7.0 → 0.8.0` — `sku_daily_stats` is replaced by
`demand_profiles`, `DemandProfile` is added, and safety-stock results change.
