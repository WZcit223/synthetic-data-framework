# PR 3 — Error metrics: one implementation, correct MAPE, WAPE, safe edge cases

> Status: implemented (correctness sequence PR 3). Deviations found during
> implementation: (1) the anomaly scale also has a floor (`min_scale`, 1 demand
> unit), because the mean-absolute-deviation fallback alone still flags a single
> unit sold on an otherwise empty series; (2) the rank flag is reported by
> `tstr_report` (`rank_deficient`), since the forecaster callables have no place
> for a note; (3) removing the old `1e-6` ridge term moves the hourly
> `seas_linear11` MAE (1787.337 → 1787.347) and the hourly TSTR MAEs in the
> fourth or fifth significant digit, with the TSTR ratio unchanged. Default-world
> MAPE values did not move (no zero-demand day).

## Goal

Forecast error is computed once, with a documented convention, and edge cases
(zero actuals, flat series, collinear features) produce correct or explicitly
flagged results.

## Scope

- New `src/sdf/analytics/metrics.py` with `mae`, `rmse`, `bias`, `mape`
  (mean of `|error| / actual` over days with a positive actual) and `wape`
  (`Σ|error| / Σactual`). `mape` and `wape` return `float | None`: `None`
  when there is no positive actual (respectively a zero total), so the value
  serialises to JSON `null` in `sdf validate` and the API, never to `NaN`.
  `backtest` and `validation.tstr` use it; the local MAE helper in `tstr.py`
  goes away.
- `backtest` reports `MAE`, `RMSE`, `MAPE_pct` (corrected), `WAPE_pct` (new)
  and `bias`. `compare_models` still ranks by MAE.
- `seasonal_residual_anomalies`: when the median absolute deviation is 0, fall
  back to the mean absolute deviation; when that is also 0 the series is flat
  and the function returns no anomalies. `demand_anomalies` reports a `note`
  in that case.
- `analytics/models.py`: build the existing design rows into a matrix `X`
  and target `y` and call `numpy.linalg.lstsq(X, y, rcond=None)` directly,
  instead of forming the normal equations `XᵀX` first (which squares the
  condition number and hides the rank). The returned rank tells whether the
  design was rank deficient (`fit_weights` returns the weights; a new
  `fit_weights_with_rank` exposes the flag, used by the model wrapper for its
  `note`). On full-rank data the weights match the current solver to floating
  precision.
- Regenerate `docs/VALIDATION.md` with `sdf validate --update-doc`; add a
  one-time table "MAPE before / after the convention fix" for the bundled
  CSVs and the default world, and state the convention next to every MAPE
  column.
- Update `golden_test.py` literals that move and list each one in the PR
  description (old → new, cause).

## Expected moved numbers

- Every `MAPE_pct` (default-world backtest table, `sample` 20.57, `10k`
  99.04).
- `seas_linear*` MAE may change in the last digit only (solver change); any
  larger change is a bug and blocks the PR.
- No other recorded number is expected to move.

## Non-goals

- No change to which model wins (still lowest MAE).
- No new forecasting or anomaly model.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest                     # metrics_test passes; golden_test updated only for the listed numbers
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run python -c "from sdf.analytics.forecast import backtest, m_mean; print(backtest([0,10]*30, m_mean, test_len=20)['MAPE_pct'])"   # 51.01
```

## Version

`Version: MINOR 0.6.0 → 0.7.0` — new `sdf.analytics.metrics` module, a new
`WAPE_pct` output field and corrected MAPE values.
