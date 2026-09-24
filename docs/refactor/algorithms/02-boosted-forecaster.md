# PR 2 — A gradient-boosted forecaster, and intervals on the dashboard

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §4.

## Goal

The first real forecaster replaces the trailing mean: one model over all
SKUs, with intervals, scored by PR 1's backtest against the stand-ins and
against the true distribution. The dashboard's SKU chart shows its forecast
and interval.

## Scope

- **`gradient-boosting`** in `sdf.analytics.forecasters.boosted`, as in §4.1:
  the features, the Poisson model for the mean, a quantile model per level
  (cached per set of levels), the parameters with their bounds, and the
  fallback to `moving-average` for SKUs with less than `min_history` days.
- **`lightgbm`**, the same design on LightGBM, `requires = ("lightgbm",)`.
  Listed as unavailable with the reason when the `app` extra is not
  installed. The CI job with the optional extras installs `app` and runs its
  test.
- **`demand-series`'s `forecast` block** (§4.2), from the app's default
  forecaster, fitted once per world and cached with it;
  `create_app(forecaster=…)`. The schema marks `forecast_avg_daily` and
  `forecast_total` as deprecated in their description only.
- **Hook markers.** `demand_series` loses its `ALGORITHM-HOOK[C1]` (the
  trailing mean is no longer the forecast); `gradient-boosting` carries one
  (DeepAR or Temporal Fusion Transformer on the full dataset). The code index
  is regenerated.
- **Docs:** the "Per-SKU probabilistic backtest" section of
  `docs/VALIDATION.md` gains the new rows; checklist row C1 ("framework
  shows": a gradient-boosted global forecaster with intervals); the plug-in
  guide mentions both as examples of global models.

## Tests

- On a series with a known weekly pattern and no noise, the forecaster
  recovers it (WAPE under 5 %).
- Features use no day at or after the origin (a history whose later days are
  poisoned changes nothing).
- Quantile models are cached per set of levels and refitted for a new set;
  the results are repeatable with the same `seed`.
- The short-history fallback is used and counted.
- `lightgbm` is listed as unavailable without the extra, and, with it,
  scores within 5 % of `gradient-boosting`'s WAPE on the benchmark.
- `demand-series` keeps every current field and adds `forecast`; the
  forecast is fitted once per world (a second request does not refit).

## Non-goals

- No page (PR 6); the dashboard change is the interval on the existing chart.
- No hyperparameter search. The defaults are fixed in this PR and recorded.
- No exogenous features.

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main`.
- On the benchmark's defaults, `gradient-boosting`'s WAPE is within 3 %
  (relative) of the `true-distribution` row's, and its `relative_wape` is
  below 0.85; on the default world, below 0.85 too. Both coverages bracket
  the nominal level. The PR records the numbers, and if a target is missed,
  says so and why instead of changing the target.
- The whole default-world backtest (all built-ins and `gradient-boosting`,
  horizon 14, 4 origins) finishes within the 30 s budget.

## Version

`Version: MINOR 1.9.0 → 1.10.0` — new forecasters and a new field in the
`demand-series` answer.
