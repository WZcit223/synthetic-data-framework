# PR 1 — Forecaster plug-ins, a probabilistic backtest and a demand benchmark

> Status: implemented (algorithm phase PR 1).
>
> Measured (horizon 14, 4 origins 7 days apart, 80 % interval):
> - Demand benchmark (seed 7, 200 SKUs × 365 days): the exact distribution's
>   WAPE is 85.6 % and its pinball loss 0.898; the best built-in,
>   `seasonal-linear`, has 86.5 % and 0.955, and seasonal naive 108.8 % and
>   1.306. The exact distribution's 80 % interval covers 45.5 % of outcomes
>   with the bounds excluded and 90.1 % with them included, so the nominal 80 %
>   lies between the two, as the contract predicts (§2.3).
> - Default world: `mean` has WAPE 65.9 % (0.814 of seasonal naive's 81.0 %).
> - The built-ins' intervals are too narrow on the benchmark: 75 % to 80 %
>   covered with the bounds included, against the exact distribution's 90 %.
>   `seasonal-linear` refits its weights every 7 origins of the error window,
>   so each error comes from a fit on days before its origin; fitted once on
>   the whole history, its errors were in sample and its coverage on the
>   default world was 66.9 % instead of 80.6 %.
> - Timing: the five built-ins with the `true-distribution` row take 4.7 s at
>   400 SKUs × 730 days and 15.4 s at the largest request (horizon 56, 12
>   origins).
>
> Beyond the plan: `Param` and the constructor-parameter reader moved down to
> `sdf.foundation.params` (analytics may not import synthesis; the old names
> stay importable); the built-ins compute their intervals at forecast time from
> the history given, for all SKUs at once; `Forecast` carries a `method`;
> `TrueDemand` has `cdf` and `DemandDraw.observed()` gives the draw as a table;
> `GET /forecasters` also publishes `min_history` in its limits; the backtest
> response also has `origins`, `source`, `world`, `skus` and
> `elapsed_ms`; `sdf forecast` takes `--param FORECASTER.NAME=VALUE`.

Contract: [`interfaces.md`](interfaces.md) §1, §2, §3 and §10.

## Goal

Any forecaster can be plugged in and scored per SKU, over several days ahead,
with intervals, on the same rows as every other forecaster. On the benchmark,
the score is set against the exact distribution the data came from.

## Scope

- **New `sdf.analytics.forecasters`**, holding:
  - the types `ForecasterInfo`, `Forecast`, `Forecaster` and
    `check_quantiles`;
  - the registry: `ForecasterRegistry` (a `PluginRegistry` over the new
    `sdf.forecasters` group), `default_forecasters()`, and the guard of §1.2;
  - the five built-ins of §1.3, wrapping the existing models of
    `sdf.analytics.forecast` and `sdf.analytics.models` (not copying them),
    with intervals from their own errors;
  - `backtest`, `BacktestResult` and the `forecast-scores`, `by-horizon` and
    `forecasts` table infos (§2).
- **`DemandTable.until` and `DemandTable.window`** (§1.2).
- **`DemandBenchmark`, `DemandDraw`, `TrueDemand`** in
  `sdf.simulation.benchmark`, with `DEMAND_BENCHMARK_INFO` (§3). The exact
  quantiles invert the mixture's CDF with scipy.
- **API:** `GET /api/v1/forecasters` and `POST /api/v1/forecasts/backtest`
  (§2.4), `create_app(forecasters=…)`, the response models, the limits of §10
  measured and set, and the paths in the UI contract test's allowed list.
- **CLI:** `sdf forecast` (§2.4), with `--csv`.
- **Entry points:** the five built-ins in `pyproject.toml` under
  `[project.entry-points."sdf.forecasters"]`.
- **Docs:** the plug-in guide gains a forecaster section with a runnable
  example (tested like the others in `src/sdf/plugins_guide_test.py`);
  `ARCHITECTURE.md`; the README command list; a new section in
  `docs/VALIDATION.md`, "Per-SKU probabilistic backtest", with the scores of
  the built-ins on the default world and on the benchmark, and the command
  that reproduces them; checklist row C1's "framework shows" cell.

## Tests

- The guard: wrong shape, wrong SKUs, a non-finite value, another
  forecaster's name are refused; negative values and crossed quantiles are
  repaired and counted in `method`.
- Each built-in against a closed-form case: a constant series gives that
  constant and a zero-width interval; `seasonal-naive` repeats the last cycle;
  `moving-average` over a known window; the pooled interval for a SKU with
  too few errors.
- The metrics of §2.3 on hand-computed cases: WAPE, bias sign, pinball
  loss, both coverages on outcomes equal to a bound, `relative_wape`
  computed without `seasonal-naive` requested, and `wape` empty only when
  every actual is 0.
- The backtest never lets a forecaster see a day at or after its origin
  (a forecaster that raises when it does); `refit="once"` fits once.
- The benchmark: the drawn mean over many draws matches `TrueDemand.mean`;
  the exact quantiles match simulated ones; with `promo_rate=0` and
  `intermittent_share=0` the quantiles are the negative binomial's; the
  parameter bounds are refused by the class and by the API alike; the
  `true-distribution` row satisfies `coverage_open ≤ 0.8 ≤ coverage_closed`.
- The API's 422 cases (unknown forecaster, too many, bad parameter, horizon
  or origins over the limit, history too short) and a failing forecaster as
  an error row in a 200; the time budget turns forecasters not started into
  "not run" rows; one world snapshot per request.
- The CLI output, and the contract examples of §1 to §3 run as written.

## Non-goals

- No gradient boosting yet (PR 2), no page (PR 6).
- No change to `/api/v1/backtest`, `sdf backtest`, `compare_models` or any
  recorded number; the existing model names (`snaive7`, `ma7`) stay where
  they are.
- No exogenous features (prices, announced promotions). The history is
  demand only.

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main` and `sdf validate --update-doc docs/VALIDATION.md` giving no diff
  outside the new section.
- `uv run sdf forecast --benchmark` shows every built-in with a
  `relative_wape`, both coverages and the `true-distribution` row; the PR
  records the numbers.
- `POST /api/v1/forecasts/backtest` returns the same scores as the CLI for
  the same request.

## Version

`Version: MINOR 1.8.0 → 1.9.0` — a new capability: forecaster plug-ins, the
probabilistic backtest, the demand benchmark, two endpoints and
`sdf forecast`.
