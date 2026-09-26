# Algorithm phase — interface contract

This is the **authoritative contract** for this sequence
([`00-overview.md`](00-overview.md)). PR plans link here and do not redefine
names, parameters or return types. If an implementation must change an
interface, the same PR updates this file, the affected plans and every caller.

Every example is labelled:

- **Current**: runs on `main` today.
- **Target (after PR n)**: becomes runnable when PR n merges; not supported before.

Values shown as `…` depend on data. Numbers come from spikes on the default
world (`GenerationSpec()`, seed 42) or on the demand benchmark's defaults and
are marked as such; the implementing PR checks its own numbers in its tests
and replaces these.

Tables follow the exploration contract
([`../explore/interfaces.md`](../explore/interfaces.md) §1): `Field`,
`DatasetInfo` and `Table` from `sdf.foundation.tables`, served as
`{"fields": [...], "rows": [[...], ...]}`. Plug-in catalogues follow the
shared loader (`sdf.foundation.plugins.PluginRegistry`,
[`../causal/interfaces.md`](../causal/interfaces.md) §2): an entry-point
group, `info.requires` for optional modules, and unavailable plug-ins listed
with their reason.

---

## 1. Forecasters

### 1.1 Current: one-step callables on one series

```python
from sdf.analytics.forecast import build_series, compare_models, models_for
from sdf.simulation.world import World
from sdf.synthesis.spec import GenerationSpec

world = World.generate(GenerationSpec())
series, granularity, period = build_series(world.stream("OutboundOrder"))  # the world's total, daily
report = compare_models(series, test_len=2 * period, models=models_for(period))
report["best_model"]    # 'snaive7'
report["results"][0]    # {'model': 'snaive7', 'MAE': 174.071, 'WAPE_pct': 23.29, ...}
```

A model is `Callable[[list[float]], float]`: history in, next value out. There
is no per-SKU forecast, no horizon beyond one step and no interval. This path
stays as it is: `/api/v1/backtest`, `sdf backtest` and the numbers in
`docs/VALIDATION.md` keep using it.

### 1.2 Target (after PR 1): `sdf.analytics.forecasters`

```python
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Protocol, Self

import numpy as np

from sdf.analytics.demand import DemandTable


@dataclass(frozen=True)
class ForecasterInfo:
    name: str  # lower-case words joined by dashes
    description: str
    requires: tuple[str, ...] = ()  # modules; missing ones list the forecaster as unavailable
    global_model: bool = False  # True: one model fitted over all SKUs; False: one per SKU


@dataclass(frozen=True)
class Forecast:
    forecaster: str
    origin: date  # the first forecast day: the day after the history's last day
    sku_ids: tuple[str, ...]  # the history's SKUs, in its order
    mean: np.ndarray  # float, SKUs × horizon, >= 0
    quantiles: dict[float, np.ndarray]  # level -> SKUs × horizon, >= 0, non-decreasing in level
    method: str = ""  # how the intervals were made; the guard appends what it repaired

    @property
    def horizon(self) -> int: ...


class Forecaster(Protocol):
    info: ClassVar[ForecasterInfo]

    def fit(self, history: DemandTable) -> Self: ...

    def forecast(self, history: DemandTable, *, horizon: int, quantiles: Sequence[float]) -> Forecast: ...
```

- `fit` learns from `history`; `forecast` predicts the `horizon` days after
  `history`'s last day, using no day after it. The two take a history each, so
  the backtest can fit once and forecast from several origins (§2.1), and a
  global model can be fitted on one set of SKUs and asked about another.
- Parameters are constructor keywords, read and published as `Param`s the way
  synthesizers' are, with an optional `param_bounds` class attribute. PR 1
  moved the reader down to the foundation, as
  `sdf.foundation.params.constructor_params` (with `Param` and `ParamType`),
  because `analytics` may not import `synthesis`; `sdf.synthesis.api.Param`
  and `sdf.synthesis.registry.synthesizer_params` stay importable where they
  were, unchanged.
- `quantiles` are levels strictly between 0 and 1, at most 9, sorted and
  distinct (`check_quantiles`, which raises `ValueError` naming the problem).

New on `DemandTable` (PR 1), so a history can be cut at an origin:

```python
class DemandTable:  # the two additions only
    def until(self, day: date) -> "DemandTable": ...  # the days before `day`, same SKUs; ValueError if none is left
    def window(self, start: date, days: int) -> "DemandTable": ...  # `days` days from `start`, for scoring
```

**The registry's guard** (in `ForecasterRegistry.forecast`, which the backtest
and every endpoint use; a forecaster is never called directly by them):

- the shape of `mean` and of every quantile array must be `(len(sku_ids),
  horizon)`, the `sku_ids` must be the history's, and every value finite;
  otherwise the result is refused with a `ValueError` naming the forecaster
  and the problem;
- a negative value becomes 0, and quantiles that cross are sorted per point
  (monotone rearrangement); both are counted and reported in the scores'
  `method` field, never silent;
- a result labelled with another forecaster's name is refused, as for
  estimators, and so is an `origin` other than the day after the history's
  last day;
- every forecaster is built once, before any runs: a `ValueError` from its
  constructor (a value outside its published bounds, or a combination it
  refuses) is the request's problem, a 422; any other exception is the
  forecaster's own failure, its error row, and the others still run.

### 1.3 Target (after PR 1): the registry and the built-ins

```python
from sdf.analytics.forecasters import ENTRY_POINT_GROUP, ForecasterRegistry, default_forecasters

ENTRY_POINT_GROUP  # 'sdf.forecasters'
reg = default_forecasters()
reg.names()        # ['mean', 'moving-average', 'naive', 'seasonal-linear', 'seasonal-naive', …]
reg.params("moving-average")  # (Param(name='window', type='int', default=7, min=1, max=365), )
model = reg.create("seasonal-naive", period=7).fit(history)
fc = reg.forecast(model, history, horizon=14, quantiles=(0.1, 0.5, 0.9))
fc.quantiles[0.9].shape   # (200, 14) on the default world
```

The built-ins wrap the models of §1.1, per SKU, under dashed names:

| Name | Point forecast | Parameters |
|---|---|---|
| `mean` | the history's mean | none |
| `naive` | the last day | none |
| `moving-average` | the mean of the last `window` days | `window` (1 to 365, default 7) |
| `seasonal-naive` | the same day `period` days earlier | `period` (1 to 365, default 7) |
| `seasonal-linear` | the AR + seasonal OLS of `sdf.analytics.models` | `period` (2 to 365, default 7) |

Each is repeated over the horizon the way the model implies (a seasonal naive
repeats the last cycle; the others hold their value, except `seasonal-linear`,
which feeds its own predictions forward). **Intervals for the built-ins** come
from their own errors, computed at forecast time from the history given (so
nothing needs to be kept from `fit`): from each of the last 56 days of that
history (fewer if it is shorter), each SKU's one-step to `horizon`-step
forecasts are compared with what followed, and the empirical quantiles of the
errors at each step are added to the point forecast and floored at 0. All SKUs
share the day axis, so they have the same number of errors at a step; when a
step has fewer than 14, every SKU borrows the errors of all SKUs, each scaled by
its SKU's mean. The `method` field says so. Every error comes from a forecast
that used only the days before its origin: `seasonal-linear` refits its
weights every 7 origins of the error window (and at the last one), and each
origin uses the latest fit made at or before it.

PR 2 adds `gradient-boosting` and, with the `app` extra, `lightgbm` (§4).

---

## 2. The probabilistic backtest

### 2.1 Target (after PR 1): `backtest`

```python
from sdf.analytics.forecasters import BacktestResult, backtest

result = backtest(
    ["seasonal-naive", "moving-average"],
    world.demand(),
    horizon=14,          # days forecast from each origin, 1 to 56
    origins=4,           # rolling origins, 1 to 12, `step` days apart; the last leaves exactly `horizon` days
    step=7,
    quantiles=(0.1, 0.5, 0.9),
    params={"moving-average": {"window": 28}},
    refit="each-origin", # or "once": fit on the history before the first origin only
    truth=None,          # a TrueDemand (§3) adds the true distribution as a reference row
    deadline=None,       # a time.monotonic() instant; forecasters not started by then are "not run" rows
)
result.scores       # Table: one row per forecaster (§2.2)
result.by_horizon   # Table: one row per forecaster × days ahead
result.forecasts    # Table: SKU × day × forecaster, the last origin only, for charts
```

Each forecaster runs through the registry's guard; one that raises, times out
or is refused becomes an error row, as `score` does for estimators. The
history must hold at least `horizon + (origins - 1) * step + 28` days, or
`backtest` raises `ValueError` saying how many it has and needs.

### 2.2 The tables

`forecast-scores` (one row per forecaster):

| Field | Label | Kind | Unit | Aggregate |
|---|---|---|---|---|
| `forecaster` | Forecaster | dimension | | |
| `wape` | WAPE | measure | share | mean |
| `relative_wape` | WAPE relative to seasonal naive | measure | share | mean |
| `bias` | Bias | measure | share | mean |
| `mae` | Mean absolute error | measure | units | mean |
| `pinball` | Pinball loss | measure | units | mean |
| `coverage_open` | Coverage, bounds excluded | measure | share | mean |
| `coverage_closed` | Coverage, bounds included | measure | share | mean |
| `nominal` | Nominal coverage | measure | share | mean |
| `width` | Interval width | measure | units | mean |
| `seconds` | Run time | measure | s | sum |
| `method` | Method | dimension | | |
| `error` | Error | dimension | | |

`by-horizon` has `forecaster`, `days_ahead` (measure, days) and the same
metric fields. `forecasts` has `sku_id`, `date` (time), `forecaster`,
`actual`, `mean`, and one `q<level>` field per quantile (`q10`, `q50`, `q90`).

With `truth`, a row named `true-distribution` gives the same metrics for the
exact distribution (§3). No forecaster beats its pinball loss on average; its
WAPE is a floor only for a mean forecast (a median forecast can have a lower
WAPE), so the pinball loss is the score to compare with it.

### 2.3 Definitions

Over every SKU, origin and day ahead with actual `y`:

- **Point forecast** is `mean`. `wape = Σ|y − mean| / Σy`;
  `bias = Σ(mean − y) / Σy` (positive: over-forecast), the sign convention of
  `sdf.analytics.metrics.bias`; `mae` is the mean of `|y − mean|`.
- `relative_wape` is `wape` divided by the `wape` of `seasonal-naive` (period
  7) on the same points; it is computed even if `seasonal-naive` was not
  requested, and is below 1 when a forecaster beats it. When that
  denominator is 0 (seasonal naive is exact on every point, for example on a
  constant series) or empty (every actual is 0), `relative_wape` is empty
  (`None`), never a non-finite number.
- **`pinball`** is the mean, over points and levels τ, of
  `max(τ(y − q_τ), (τ − 1)(y − q_τ))`.
- **Coverage** is for the central interval between the lowest and highest
  requested level (with the default, 10 % to 90 %; `nominal` = 0.8).
  Demand comes in whole units, so an outcome often equals a bound, and one
  coverage number misleads: the true distribution's own 10 % to 90 % interval
  covers 89.7 % of the benchmark's outcomes with the bounds included and
  47.9 % with them excluded (spike). Both are reported: `coverage_closed`
  counts `q_low ≤ y ≤ q_high`, `coverage_open` counts `q_low < y < q_high`.
  For a calibrated forecaster the nominal level lies between the two
  (`coverage_open ≤ nominal ≤ coverage_closed`, up to sampling noise); the
  spike's gradient-boosted forecaster gives 53.4 % and 89.8 %. `width` is
  the mean of `q_high − q_low`.
- A day with `Σy = 0` over all SKUs is kept; `wape` and `bias` are empty
  (`None`) only if every scored actual is 0.

### 2.4 Target (after PR 1): API and CLI

`GET /api/v1/forecasters`:

```json
{
  "forecasters": [{"name": "seasonal-naive", "description": "…", "global_model": false,
                   "params": [{"name": "period", "type": "int", "default": 7, "min": 1, "max": 365}],
                   "origin": "built-in"}],
  "unavailable": {"lightgbm": "needs lightgbm"},
  "limits": {"max_forecasters": 6, "max_horizon": 56, "max_origins": 12, "max_quantiles": 9,
             "max_skus": 400, "max_seconds": 30},
  "benchmark": {"params": [{"name": "n_skus", "type": "int", "default": 200, "min": 10, "max": 400}, "…"]}
}
```

`POST /api/v1/forecasts/backtest`:

```json
{
  "forecasters": ["seasonal-naive", "moving-average"],
  "params": {"moving-average": {"window": 28}},
  "source": {"world": {}},
  "horizon": 14, "origins": 4, "step": 7, "quantiles": [0.1, 0.5, 0.9], "refit": "each-origin"
}
```

`source` is `{"world": {}}` (the current world's demand, the first
`max_skus` SKUs in first-appearance order) or `{"benchmark": {…params}}` (§3,
which adds the `true-distribution` row). The answer holds the `scores`,
`by_horizon` and `forecasts` tables, the `source`, and `elapsed_ms`. A bad
request is a 422 naming the field; a forecaster's own failure is its error
row in a 200. One world snapshot per request, as for estimates.

CLI:

```
uv run sdf forecast                      # the world, the built-ins, default horizon/origins
uv run sdf forecast --benchmark --seed 3 # the benchmark, with the true-distribution row
uv run sdf forecast -f seasonal-naive -f gradient-boosting --horizon 28 --csv out/scores.csv
```

---

## 3. The demand benchmark

### 3.1 Target (after PR 1): `sdf.simulation.benchmark.DemandBenchmark`

```python
from sdf.simulation.benchmark import DemandBenchmark, DEMAND_BENCHMARK_INFO

bench = DemandBenchmark(n_skus=200, days=365, intermittent_share=0.3,
                        promo_rate=0.03, promo_uplift=0.6, dispersion=2.0, seed=7)
draw = bench.draw()
draw.table                     # DemandTable: the drawn daily demand, days from 2025-01-01
draw.truth                     # TrueDemand
draw.truth.mean(day)           # np.ndarray over SKUs: the expected demand a forecaster can know
draw.truth.quantiles(day, (0.1, 0.5, 0.9))  # dict level -> np.ndarray over SKUs
draw.truth.cdf(day, np.arange(10))  # SKUs × counts: P(demand <= x)
draw.observed()                # Table "demand-benchmark": sku_id, date, units, true_mean
```

The process, per SKU `i` and day `t`, is declared in the class docstring and
tested:

- level `ℓᵢ = exp(N(1, 1))`, a weekday profile shared by all SKUs (Monday to
  Sunday 1.0, 1.05, 1.1, 1.1, 1.25, 0.8, 0.7) and a small trend
  `exp(βᵢ t)`, `βᵢ ~ N(0, 0.001)`;
- promotions: on each SKU-day with probability `promo_rate`, the mean is
  multiplied by `1 + promo_uplift`. Promotions are **unannounced**: no
  forecaster sees them in advance, so the truth a forecaster is scored
  against is the mixture over "promotion or not";
- intermittency: a share `intermittent_share` of SKUs have a zero-day
  probability `πᵢ ~ U(0.4, 0.8)`; others have `πᵢ = 0`;
- demand is `0` with probability `πᵢ`, else negative binomial with mean
  `μᵢₜ / (1 − πᵢ)` and dispersion `dispersion`, so the mean over both is
  `μᵢₜ`.

`TrueDemand.quantiles` is exact (the CDF of the zero-inflated mixture,
inverted per SKU-day), not simulated. Parameters are `Param`s with bounds
published by `GET /forecasters` and checked by the class, as for
`PromotionBenchmark`:

| Parameter | Range | Default |
|---|---|---|
| `n_skus` | 10 to 400 | 200 |
| `days` | 84 to 730 | 365 |
| `intermittent_share` | 0 to 0.9 | 0.3 |
| `promo_rate` | 0 to 0.2 | 0.03 |
| `promo_uplift` | 0 to 3 | 0.6 |
| `dispersion` | 0.5 to 50 | 2.0 |
| `seed` | integer ≥ 0, or empty for 7 | empty |

---

## 4. Gradient-boosted forecasters

### 4.1 Target (after PR 2): `gradient-boosting`

One model over all SKUs (`global_model = True`), scikit-learn's
`HistGradientBoostingRegressor`:

- **Features**, from the history before the origin only: the last 1, 7 and
  14 days, the means of the last 7 and 28 days, the share of zero days in the
  last 28, the weekday of the target day, and the days ahead (1 to
  `horizon`). One model covers all horizons ("direct" forecasting: the days
  ahead are a feature, so errors are not fed back).
- **Targets**: one model with Poisson loss for the mean, one with quantile
  loss per requested level. The quantile models are fitted when `forecast`
  first sees a set of levels and cached per set.
- **Parameters**: `max_iter` (10 to 1000, default 200), `learning_rate`
  (0.01 to 1, default 0.1), `max_leaf_nodes` (2 to 255, default 31),
  `min_history` (28 to 365, default 28; SKUs with less history get the
  `moving-average` forecast and are counted in `method`), `seed`.
- Spike, one-step, last 28 days: WAPE 84.5 % on the benchmark against 83.5 %
  for the true mean; 60.6 % on the default world's SKUs against 80.6 % for
  seasonal naive.

`lightgbm` is the same design on LightGBM (`requires = ("lightgbm",)`, the
`app` extra), for data too large for scikit-learn's model.

### 4.2 Target (after PR 2): the SKU forecast on the dashboard

`GET /api/v1/demand-series?sku_id=…` keeps every current field and adds:

```json
"forecast": {
  "forecaster": "gradient-boosting",
  "level": 0.8,
  "days": [{"date": "2025-04-01", "mean": 3.4, "low": 0.0, "high": 7.0}, "…"]
}
```

The forecaster is the app's default forecaster (`create_app(forecaster=…)`,
default `gradient-boosting`), fitted once per world and cached with it. The
existing `forecast_avg_daily` and `forecast_total` stay, and are marked
deprecated in the schema's description; nothing removes them in this
sequence.

---

## 5. Replenishment

### 5.1 Current: levels from a profile

```python
from sdf.simulation.policy import ServiceLevelPolicy
levels = ServiceLevelPolicy(service_level=0.95).levels(world.demand().profile("SKU-00000"))
levels   # Levels(reorder_point=…, order_up_to=…, safety_stock=…), order_up_to == reorder_point
```

`Policy.levels(profile)` sees only the demand profile: no costs, no history.
`SimulatedCost` replays the same history the levels came from.

### 5.2 Target (after PR 3): the policy sees the SKU

```python
from sdf.simulation.policy import PolicyInput, levels_for

@dataclass(frozen=True)
class PolicyInput:
    sku_id: str
    profile: DemandProfile          # of `history`
    history: tuple[float, ...]      # daily demand the levels may use, oldest first
    unit_cost: float
    unit_price: float

def levels_for(policy: Policy, item: PolicyInput) -> Levels: ...
```

`levels_for` calls `policy.levels_for(item)` when the policy defines it, and
`policy.levels(item.profile)` otherwise, so every existing policy works
unchanged. `plan_orders` and `SimulatedCost` call `levels_for`. A SKU
missing from the SKU stream gets `unit_cost` 1.0 and `unit_price` 1.3, the
values `SimulatedCost` assumes today.

### 5.3 Target (after PR 3): `CostBasedPolicy`

```python
from sdf.simulation.policy import CostBasedPolicy
from sdf.simulation.outcome import CostModel

policy = CostBasedPolicy(cost_model=CostModel())
policy.name            # 'cost-based'
levels_for(policy, item)
```

For each SKU it chooses the reorder point `s` and the order size `S − s` that
minimise the cost of replaying `item.history` under the cost model
(holding + ordering + lost margin, the `SimulatedCost` pricing):

- candidate `s = μ(L + R) + z · σ · √(L + R)` for
  `z ∈ {0, 0.5, 1, 1.28, 1.645, 2, 2.5, 3}`, with `μ` and `σ` from
  `item.profile` (`σ` is its `variability`);
- candidate `S − s = m · Q` for `m ∈ {0.5, 1, 1.5, 2, 3}`, with `Q` the
  economic order quantity `√(2 · order_fixed_cost · μ / daily_holding_cost)`,
  where `daily_holding_cost = unit_cost · holding_cost_annual_rate /
  working_days_per_year`. `Q` is capped at `μ · len(item.history)`, one
  order for the whole history; when `daily_holding_cost` is 0 (a zero
  holding rate or a zero unit cost, both allowed today) `Q` is that cap, and
  when `order_fixed_cost` is 0, `Q` is 0 and every candidate order size is 0
  (order up to `s` each review, as `ServiceLevelPolicy` does). `μ > 0`
  always: SKUs without demand are skipped before any policy is asked, as
  today;
- ties go to the smaller `s`, then the smaller order size.

The grid is part of the contract, so results are reproducible; `levels_for`
never looks beyond `item.history`. Planning with a forecaster's output
instead of the history's profile is not part of this contract:
`PolicyInput` carries one SKU's values without the day axis and the other
SKUs a forecaster needs (§1.2). Whether to add it is decided on PR 2's and
PR 3's numbers, in its own contract change. Spike: 60,370 simulated cost against
119,736 for `service-level-95`, out of sample (§5.4).

### 5.4 Target (after PR 3): out-of-sample replay

```python
from sdf.simulation.outcome import SimulatedCost

SimulatedCost(cost_model=CostModel(), holdout_days=30)
```

With `holdout_days`, each SKU's levels come from the days before the last
`holdout_days` and the replay runs on those last days only. The default,
`None`, keeps today's in-sample replay, so every recorded number stays.
`holdout_days` must leave at least 28 fitting days, or `measure` raises
`ValueError`. The catalogue gains the outcome `simulated_cost_holdout`
(`holdout_days=30`) and the policy kind `cost-based`, so experiments and
effect studies can compare it with the others.

---

## 6. Anomaly detectors

### 6.1 Current

```python
from sdf.analytics.anomaly import seasonal_residual_anomalies
seasonal_residual_anomalies(values, period=7, k=3.5)   # [{'index': 41, 'robust_z': 5.2, 'direction': 'spike', …}]
```

One function over one series; `/api/v1/demand-anomalies` runs it on the
world's total.

### 6.2 Target (after PR 4): `sdf.analytics.detectors` and `sdf.simulation.signals`

```python
@dataclass(frozen=True)
class DetectorInfo:
    name: str
    description: str
    requires: tuple[str, ...] = ()
    signals: tuple[str, ...] = ("demand",)   # the columns of a SignalFrame it reads


@dataclass(frozen=True)
class SignalFrame:
    days: tuple[date, ...]
    sku_ids: tuple[str, ...]
    signals: dict[str, np.ndarray]   # name -> SKUs × days, float; np.nan where unknown


@dataclass(frozen=True)
class Detection:
    sku_id: str
    day: date
    score: float        # larger is more anomalous; comparable within one detector only
    direction: str      # 'spike', 'drop' or 'other'
    signals: tuple[str, ...]  # the signals that made it anomalous, when the detector can say


class Detector(Protocol):
    info: ClassVar[DetectorInfo]
    def scores(self, frame: SignalFrame) -> np.ndarray: ...     # SKUs × days, float, finite; larger is more anomalous
    def detect(self, frame: SignalFrame) -> list[Detection]: ...  # the points it reports at its own threshold
```

`scores` rates every SKU-day, not only the reported ones, so a detector can
be ranked apart from its threshold (§6.3's `top-k` cut); `detect` reports the
points it would alarm on. The registry checks that `scores` has the frame's
shape and finite values and that every detection names a SKU and day of the
frame, a direction of `DIRECTIONS`, a finite number as its score (passed on
as a plain `float`) and, as its reasons, a tuple of the frame's signals;
otherwise the detector's result is refused and becomes an error row, as does
a detector that fails in its constructor or its run. In `GET /anomalies` a
refused result is a 422 and a detector's own failure a 500 that names it.

`ENTRY_POINT_GROUP = "sdf.detectors"`, `DetectorRegistry`,
`default_detectors()` and `score_detectors` live in `sdf.analytics.detectors`
and know only `SignalFrame`: `analytics` sits below `simulation` in
`src/sdf/layering_test.py`, so nothing there imports a world or a policy.
The world's frame is built one layer up, by
`sdf.simulation.signals.signal_frame(world, policy=ServiceLevelPolicy()) -> SignalFrame`, with three
signals: `demand` (daily units), and `on_hand` and `receipts`, the end-of-day
stock and the units arriving, from replaying the demand under `policy`. The
world holds one stock snapshot and a few inbound orders, not a daily stock
record, so the stock is the replayed one. For this, `simulate_inventory`
gains `record=True`, which fills two new trace fields, `on_hand` and
`receipts` (tuples per day, empty by default). Built-ins:

- `seasonal-residual`: today's rule per SKU on `demand`, with `k` (2 to 10,
  default 3.5) and `period` (2 to 28, default 7). Its `scores` are the
  absolute robust z of every point, from the same seasonal profile and
  scale (`seasonal_residual_anomalies` gains the internal helper that
  returns them, and keeps its answer); a SKU too short for the rule scores
  0 everywhere;
- `isolation-forest`: scikit-learn's `IsolationForest` over per-SKU scaled
  features of every signal in the frame (the value, its residual from the
  weekday median, from the rolling median, the zero indicator, and the day's
  change in `on_hand` not explained by `demand` and `receipts`), with
  `contamination` (0.001 to 0.2, default 0.01) and `seed`.

`/api/v1/demand-anomalies` keeps its answer. A new
`GET /api/v1/anomalies?detector=…` returns the detections as a table
(`sku_id`, `date`, `score`, `direction`, `signals`).

### 6.3 Target (after PR 4): the anomaly benchmark

```python
from sdf.analytics.detectors import score_detectors
from sdf.simulation.benchmark import AnomalyBenchmark
from sdf.simulation.signals import signal_frame

bench = AnomalyBenchmark(rate=0.01, kinds=("spike", "drop", "shrinkage"), seed=7)
frame, injected = bench.inject(signal_frame(world))   # injected: set of (sku_id, day, kind)
scores = score_detectors(["seasonal-residual", "isolation-forest"], frame, injected, kinds=bench.kinds)
```

- `spike`: demand × U(3, 6) of the SKU's mean added; `drop`: demand set to 0 on
  a selling day; `shrinkage`: `on_hand` falls by 2 to 5 days of mean demand,
  from that day on, with no demand or receipt to explain it. A stock-balance
  rule finds shrinkage exactly; it is in the benchmark to check that a
  detector reads more than one signal, since a demand-only detector cannot
  see it.
- `score_detectors` returns an `anomaly-scores` table with one row per
  detector × kind × cut:

  | Field | Label | Kind | Unit | Aggregate |
  |---|---|---|---|---|
  | `detector` | Detector | dimension | | |
  | `kind` | Anomaly kind (each injected kind, and `all`) | dimension | | |
  | `cut` | Cut (`threshold` or `top-k`) | dimension | | |
  | `precision` | Precision | measure | share | mean |
  | `recall` | Recall | measure | share | mean |
  | `f1` | F1 | measure | share | mean |
  | `flagged` | Flagged | measure | rows | max |
  | `seconds` | Run time | measure | s | sum |
  | `error` | Error | dimension | | |

  `threshold` keeps the detections `detect` reports; `top-k` keeps the
  `len(injected)` SKU-days with the highest `scores`, ties broken by SKU
  order and then day, so the cut is reproducible. Both are reported so a detector is not
  judged by its threshold alone. `precision` is empty when nothing is
  flagged. Per kind, `precision` counts only detections at an injected
  place of that kind or at no injected place, so a false alarm counts in
  every kind's row and `flagged` rows do not add up. Each injected place
  holds one kind; the rows follow `kinds` (the benchmark's order), then
  any other injected kind by name.
- Spike, 400 injected spikes and drops, demand only: `seasonal-residual`
  precision 0.28 and recall 0.72 at its threshold (1,019 flagged);
  `isolation-forest` 0.21 and 0.53 at the same count.

---

## 7. Synthetic data checks

### 7.1 Current

`TableData(rows, columns)` holds floats; the table synthesizers return floats
for every column. An evaluation of a table synthesizer reports privacy
metrics only (`privacy_report`: DCR, NNDR, clone risk).

### 7.2 Target (after PR 5): column kinds

```python
@dataclass(frozen=True)
class TableData:
    rows: list[tuple[float, ...]]
    columns: tuple[str, ...]
    kinds: tuple[str, ...] | None = None   # per column: 'real', 'integer' or 'category'; None: all 'real'
```

- `integer`: the synthesizer's output is rounded to the nearest integer and
  clipped to the column's observed range;
- `category`: the output takes only values observed in the column (nearest
  observed value for a continuous synthesizer);
- the built-ins (`bootstrap-table`, `gaussian-copula`) apply both after
  sampling, through one shared helper `apply_kinds(rows, data)`, which a
  plug-in may call too. A plug-in that ignores `kinds` still works; the
  detection test shows the difference.
- The evaluation's retail feature table declares `qty` integer, `price` real
  (with a note that the sample's catalogue prices make it categorical in
  effect), `hour` and `weekday` category. *As built (PR 5):* `price` is
  declared a category, since as a real number it kept the AUC at 0.96–0.99.

### 7.3 Target (after PR 5): the detection test (B4)

```python
from sdf.validation.detection import detection_report

detection_report(real_rows, synth_rows, folds=5, seed=7)   # folds and seed are keyword-only
# {'auc': 0.68, 'auc_low': 0.66, 'auc_high': 0.70, 'n_real': 3000, 'n_synth': 3000,
#  'model': 'HistGradientBoostingClassifier, 5-fold', 'top_features': ['price', 'qty', 'hour'],
#  'verdict': 'distinguishable'}
```

A classifier learns to tell real from synthetic rows; `auc` is its
cross-validated area under the ROC curve, with the spread over folds.
0.5 means indistinguishable. Verdicts: below 0.6 `hard to distinguish`, 0.6
to 0.8 `distinguishable`, above 0.8 `easily distinguished`. `top_features`
ranks columns by permutation importance. It runs in every table evaluation
(`evaluate`, `POST /api/v1/synthesis/runs`, `sdf privacy`), next to
the privacy metrics, under the metric names `detection_auc`,
`detection_auc_low`, `detection_auc_high` and `detection_verdict`.
Spike (with integer columns rounded): 0.68 for `bootstrap-table` and 0.67 for
`gaussian-copula` on the real extract. *As built (PR 5):* 0.89 and 0.90 on the
extract and 0.55 and 0.62 on the sample, and a new `bayesian-network`
synthesizer (a Chow–Liu tree over binned columns) 0.53 and 0.49; the column names come in as
`columns=`, and a fifth metric, `detection_top_features`, joins them by commas
(`docs/VALIDATION.md`, "Detection test").

---

## 8. Pages (after PR 6)

- **Forecasts page** (`ui/forecasts.html`): choose forecasters and their
  parameters from `GET /forecasters`, the source (world or benchmark with its
  parameters), horizon, origins and interval level; run the backtest; show
  the scores table, WAPE by days ahead (one line per forecaster), and one
  SKU's history with each forecaster's interval band for the last origin; the
  benchmark's `true-distribution` row is drawn as the reference. *As built
  (PR 6):* the SKU's "history" is the demand over the days after the last
  origin, the only demand the backtest's `forecasts` table holds. The
  request is in the address, and "Open in Explore" opens the three tables
  (a new Explore source `forecasts`).
- **Dashboard**: the SKU chart draws the forecast's interval band (§4.2); the
  anomaly panel gains a detector choice.
- **Synthesizers page**: the table evaluation shows the detection AUC with
  its verdict and top features.

---

## 9. Real data (after PR 7, only with decision D1 (a) or (b))

```
uv run sdf prepare-retail online_retail_II_2009-2010.csv online_retail_II_2010-2011.csv \
    --top 200 --out data/online_retail_ii_daily_top200.csv
```

- reads the UCI file as CSV (the workbook's two sheets saved as CSV, or the
  CSV copies that circulate with the same columns), with the existing
  adapter (rows without a `StockCode` skipped, negative quantities as
  cancelled orders) and its new option `drop_non_product=True` (off by
  default, PR 7). The rule is exact, so two implementations give the same
  totals: the `StockCode` is stripped of surrounding whitespace and
  upper-cased; it is a non-product code when it equals one of `POST`,
  `DOT`, `M`, `C2`, `D`, `S`, `B`, `CRUK`, `PADS`, `ADJUST`, `ADJUST2`,
  `AMAZONFEE`, `BANK CHARGES`, or starts with `GIFT_` or `TEST`. The list
  is one constant in the adapter (`NON_PRODUCT_CODES`, `NON_PRODUCT_PREFIXES`).
  Codes that contain no digit and are not on the list are kept, and counted
  by code in the load report, so a code the list misses is visible
  rather than silently kept or dropped. Reading the `.xlsx` directly would need `openpyxl`, which no
  extra installs today; PR 7 adds it to the `synthesis` extra only if the
  project lead prefers that to a one-time conversion;
- writes a wide daily table: one `date` column and one column per SKU (the
  `--top` SKUs by total units), dense over every calendar day, with a header
  comment giving the source, the licence (CC BY 4.0) and the command;
- `DemandTable.from_daily_csv(path)` reads it back, so every backtest, the
  replenishment replay and the anomaly frame run on it unchanged.

---

## 10. Limits

Each new endpoint is synchronous and bounded, as in the causal sequence:

| Endpoint | Limit | Value (set and measured in the PR) |
|---|---|---|
| `POST /forecasts/backtest` | forecasters, horizon, origins, quantiles | 6, 56, 12, 9 |
| | SKUs read from the world or drawn by the benchmark | 400 |
| | time, checked before each forecaster and each origin | 30 s (`MAX_BACKTEST_SECONDS`) |
| `GET /anomalies` | SKUs × days in the frame | measured in PR 4 |

Measured in PR 1: the five built-ins together, with the `true-distribution`
row, take 4.7 s at 400 SKUs × 730 days (horizon 14, 4 origins) and 15.4 s at
the largest request (horizon 56, 12 origins). The built-ins run for all SKUs at
once; the exact quantiles are computed once per day shared by several origins.

The limits are published in `GET /forecasters` (and for detectors in
`GET /detectors`), so the pages check them before sending.

## 11. Compatibility

- No existing name, signature, endpoint answer or entry-point group changes.
  New fields are additive (`demand-series.forecast`, the detection metrics),
  new parameters default to today's behaviour (`holdout_days=None`,
  `kinds=None`, `drop_non_product=False`), and the `Policy` protocol keeps
  `levels(profile)`. Catalogue answers keep the shared shape: `unavailable`
  maps a name to its reason, as for synthesizers and estimators.
- `sdf demo`, `/api/v1/backtest` and `docs/VALIDATION.md`'s recorded numbers
  stay byte-identical, with one stated exception: PR 5 re-records the table
  privacy numbers, because declaring column kinds changes the synthetic rows
  they are measured on (see its plan). New measurements go in new sections of
  `docs/VALIDATION.md`, each with the command that reproduces it.
- Checklist markers move with the code: a replaced stand-in keeps its
  `ALGORITHM-HOOK` until the new algorithm is the default, and each new
  built-in carries the marker of what would replace it in turn (for example,
  `gradient-boosting` carries `ALGORITHM-HOOK[C1]`: DeepAR or Temporal
  Fusion Transformer on the full dataset).
