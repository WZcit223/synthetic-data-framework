# Plug-ins: your own synthesizer, dataset, estimator, forecaster or detector

The framework has five plug-in points. All five are found through Python entry
points, so a plug-in is an ordinary installed package; nothing in this
repository changes when you add one.

| Plug-in | Entry-point group | Where it shows up |
|---|---|---|
| A **synthesizer** (an algorithm that generates a series, a table or a whole warehouse world) | `sdf.synthesizers` | `GET /api/v1/synthesizers`, the Synthesizers page, `sdf synth` / `sdf privacy` / `sdf tstr --synthesizer NAME`, and the dashboard's Generator choice for a warehouse generator |
| A **dataset provider** (a table computed from the current world, for the Explore page) | `sdf.datasets` | `GET /api/v1/datasets`, the Explore page's source list |
| An **estimator** (a method that estimates an average treatment effect from observed rows) | `sdf.estimators` | `GET /api/v1/estimators`, the Effects page's "Estimate from data" view, `sdf estimate --estimator NAME` |
| A **forecaster** (a method that forecasts every SKU's daily demand, with quantiles) | `sdf.forecasters` | `GET /api/v1/forecasters`, `POST /api/v1/forecasts/backtest`, `sdf forecast -f NAME` |
| A **detector** (a method that finds anomalous SKU-days in the daily demand, stock and receipts) | `sdf.detectors` | `GET /api/v1/detectors`, `GET /api/v1/anomalies?detector=NAME`, `sdf anomalies -d NAME` |

The built-ins are declared the same way, in this repository's `pyproject.toml`.
The contracts behind this guide are in
[`refactor/structure/interfaces.md`](refactor/structure/interfaces.md) §2
(synthesizers), [`refactor/explore/interfaces.md`](refactor/explore/interfaces.md)
§1 and §4 (datasets, parameters, runs) and
[`refactor/causal/interfaces.md`](refactor/causal/interfaces.md) §3 (estimators) and
[`refactor/algorithms/interfaces.md`](refactor/algorithms/interfaces.md) §1 to §3
(forecasters, the backtest and the demand benchmark) and §6 (detectors and the
anomaly benchmark).

## A synthesizer

A synthesizer is a class with an `info` class attribute and two methods:

- `info = SynthesizerInfo(name, produces, needs_fit, description, requires=())`:
  - `name` is lower-case words joined by dashes, and is how everyone chooses it.
  - `produces` is `"series"`, `"table"` or `"warehouse"`.
  - `requires` names modules it needs. When one is missing, the synthesizer is
    listed as unavailable with the reason instead of failing.
- `fit(data)` learns from the data and returns `self`. A series synthesizer
  receives a `SeriesData(values, period)`, a table synthesizer a
  `TableData(rows, columns)`, and a warehouse generator nothing.
- `sample(n=None, *, seed=None)` returns:
  - for a series, a list of numbers (`n` of them, or as many as were fitted);
  - for a table, a list of tuples in the fitted column order;
  - for a warehouse, a `SyntheticWarehouse`.

  `seed` pins one draw; without it, each call continues the instance's own
  random stream.

**Column kinds (table synthesizers).** `TableData.kinds` says, per column,
whether it is `"real"`, `"integer"` or `"category"` (`None`: all real). Pass
your sampled rows through `apply_kinds(rows, data)` from `sdf.synthesis.api`,
with the `TableData` you were fitted on: an integer column is rounded and
kept within its observed range, and a category column takes only observed
values (the nearest one). The built-in table synthesizers do. A synthesizer that ignores the
kinds still works, but every table evaluation runs the detection test, and
decimals in a whole-number column give its rows away: its `detection_auc`
shows it.

```python
from sdf.synthesis.api import TableData, apply_kinds

def sample(self, n=None, *, seed=None):
    rows = ...  # your model's rows, in self._data.columns order
    return apply_kinds(rows, self._data)  # self._data: the TableData given to fit()
```

**Parameters.** Every constructor argument needs a default, so the registry
can create the synthesizer by name. Keyword arguments typed `int`, `float`,
`str` or `bool` (or one of those or `None`) are its *parameters*. The catalogue
publishes them with their defaults, and the run form on the Synthesizers page
is built from them. Two optional refinements:

- A class attribute `param_bounds = {"name": (min, max)}` narrows a numeric
  parameter; either end may be `None`. The registry refuses bounds that are not
  a (min, max) pair of finite numbers, bounds with min above max, and a default
  outside its own bounds.
- A seed given to `numpy.random.default_rng` must not be negative: declare
  `param_bounds = {"seed": (0, None)}`, so a negative seed is refused as a bad
  request instead of failing the run.
- A parameter named `seed` makes runs **repeatable**: a run that leaves it out
  uses its declared default, and a nullable seed that is `None` (by default or
  set so) becomes 7. The run reports every parameter it used, so it can be
  reopened in Explore and gives the same table again.

A warehouse generator takes `spec: GenerationSpec | None = None`.
`World.generate` passes the spec of the world being built, so the dashboard's
size and seed controls apply to it too.

An effect study (`sdf effects`, `POST /api/v1/effects`) compares worlds
generated from the same seed, so a warehouse generator must keep three rules:

- **Deterministic in its spec.** The same spec gives the same world: take all
  randomness from `spec.seed`, and none from global or remembered state.
- **Independent across seeds.** Different seeds give independent worlds. The
  intervals assume it, and it cannot be checked from a few draws.
- **No reuse of returned rows.** Never change a world you already returned;
  build new row objects on every call.

The study checks the first and the third rules and refuses a generator that
breaks them, naming it. The second is the generator's promise.
`warehouse-spec` keeps all three.

This example is a series synthesizer: a moving average of the fitted series,
plus residuals drawn from the same position in the cycle (the same hour of the
day) on a random day, so the daily shape is kept. The test suite runs it exactly as written.

```python
# plugins-example: synthesizer
import random
from typing import ClassVar

from sdf.synthesis.api import SeriesData, SynthesizerInfo


class MovingAverageSeries:
    """A smoothed copy of the fitted series, with residuals drawn from the same position in the cycle."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="moving-average",
        produces="series",
        needs_fit=True,
        description="Moving average of the fitted series + residuals resampled per position in the cycle",
    )
    param_bounds: ClassVar[dict] = {"window": (1, 48)}

    def __init__(self, *, seed: int = 7, window: int = 5) -> None:
        self.window = window
        self._rng = random.Random(seed)
        self._level: list[float] = []
        self._residuals: dict[int, list[float]] = {}
        self._period = 1

    def fit(self, data: SeriesData) -> "MovingAverageSeries":
        values = list(data.values)
        self._period = max(1, data.period)
        half = self.window // 2
        self._level = []
        for i in range(len(values)):
            around = values[max(0, i - half) : i + half + 1]
            self._level.append(sum(around) / len(around))
        self._residuals = {}
        for i, (v, m) in enumerate(zip(values, self._level)):
            self._residuals.setdefault(i % self._period, []).append(v - m)
        return self

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[float]:
        rng = random.Random(seed) if seed is not None else self._rng
        n = len(self._level) if n is None else n
        if not self._level:
            return [0.0] * n
        out = []
        for i in range(n):
            residuals = self._residuals.get(i % self._period) or [0.0]
            out.append(max(0.0, self._level[i % len(self._level)] + rng.choice(residuals)))
        return out
```

**A table synthesizer, worked in full.** `bayesian-network`
(`src/sdf/synthesis/bayes_net.py`) is written as a plug-in and shipped as a
built-in. It imports nothing from the framework but `sdf.synthesis.api`, and
a test keeps it that way. It is declared in the `sdf.synthesizers`
entry-point group, and it honours `seed`, `param_bounds` and the column kinds.
Nothing else in the repository names it: the catalogue,
`sdf privacy --synthesizer`, `POST /api/v1/synthesis/runs`, the Synthesizers
page, Explore and the detection test all pick it up from the group. Being
declared by this package, it is listed as a built-in, and its name is taken;
an installed package is mounted by the same code, as `plugin`.

**What a synthesizer reaches today, and what it does not.** A synthesizer
installed in the `sdf.synthesizers` group is listed, has its parameters
published and checked, and runs through the API, the Synthesizers page and
Explore, and through `sdf privacy`, `sdf synth` and `sdf tstr`. The limits:

- **The evaluation data is fixed.** A table synthesizer is evaluated on one
  table, the retail feature table (`qty`, `price`, `hour`, `weekday`), with
  column kinds the framework declares. A series synthesizer is evaluated on
  the hourly or daily demand series. Both are read from a CSV in the Online
  Retail II layout. The command line takes such a CSV by path; the API and
  the pages take only the bundled sources. The retail table is also written
  into the run table's fields, Explore's presets for a synthesis run and the
  Synthesizers page's score tiles.
- **The command line runs defaults only.** `sdf privacy`, `sdf synth` and
  `sdf tstr` take no parameters; set them through the API, the pages or
  Python.
- **A synthesizer added with `register()` at run time** reaches only what you
  hand the registry to: `evaluate(..., registry=)` and
  `create_app(synthesizers=)`. The command line reads the entry-point group
  when it starts, the served `sdf.api.app:app` uses the default registry, and
  `tstr_report` builds its own.
- **Recorded numbers cover the built-ins they name.** `sdf validate` records
  `seasonal-profile` and `bootstrap-table` only.
- **A warehouse generator is not evaluated.** It is chosen for the world
  instead.

To use a synthesizer on a table of your own, call it and the checks from
Python: `fit(TableData(rows, columns, kinds))`, `sample()`, then
`sdf.validation.detection.detection_report` and
`sdf.validation.privacy.privacy_report`.

## A dataset provider

A dataset provider publishes a table computed from the current world, one row
per record, for the Explore page to pivot:

- `info = DatasetInfo(name, label, description, fields)`. Each `Field(name,
  label, kind, unit=None, aggregate=None)` has one of three kinds:
  - `"dimension"` is text to group by;
  - `"time"` is an ISO date `YYYY-MM-DD`;
  - `"measure"` is a number, optionally with a `unit` and the `aggregate` a
    pivot starts with (`sum` by default, or `mean`, `min`, `max`).
- `rows(world)` yields one tuple per row, in field order. `world.stream(entity)`
  reads the world's entities (`"SKU"`, `"Location"`, `"InventorySnapshot"`,
  `"InboundOrder"`, `"OutboundOrder"`, `"SensorReading"`).

Every value is checked against its field. A wrong one fails the request with
the dataset, row and field named, and a failing provider answers 500 with its
name; it never looks like an unknown dataset.

This example is a dataset of units on hand per category and zone, run by the
test suite as written:

```python
# plugins-example: dataset
from collections import defaultdict
from typing import ClassVar

from sdf.foundation.tables import DatasetInfo, Field


class StockByZone:
    """Units on hand per SKU category and warehouse zone."""

    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="stock-by-zone",
        label="Stock by zone",
        description="Units on hand per SKU category and warehouse zone",
        fields=(
            Field("category", "Category", "dimension"),
            Field("zone", "Zone", "dimension"),
            Field("on_hand", "On hand", "measure", unit="units"),
        ),
    )

    def rows(self, world):
        category = {s.sku_id: s.category for s in world.stream("SKU")}
        zone = {loc.location_id: loc.zone for loc in world.stream("Location")}
        totals = defaultdict(int)
        for snap in world.stream("InventorySnapshot"):
            totals[(category.get(snap.sku_id, "unknown"), zone.get(snap.location_id, "unknown"))] += snap.on_hand
        for (cat, z), units in sorted(totals.items()):
            yield cat, z, units
```

Yield the rows rather than returning a built list: the estimation endpoint reads
at most its row limit plus one and stops, so a provider that yields stays within
the limit's memory and time, while one that returns a list has built it whole
first.

## An estimator

An estimator answers one question about a table: the average effect of a
treatment on an outcome, adjusting for a declared set of covariates. It is a
class with an `info` class attribute and one method:

- `info = EstimatorInfo(name, description, requires=(), uses_covariates=True)`.
  Set `uses_covariates=False` for a method that ignores the covariates (like
  `difference-in-means`), so redundant covariates never refuse it.
- `estimate(table, question, *, confidence=0.95, seed=7)` returns an
  `Estimate(estimator, effect, ci_low, ci_high, n_treated, n_control, method)`:
  - `estimator` is `self.info.name`: a result under another name is refused;
  - both bounds are numbers, or both are `None` for a method without an
    interval;
  - `seed` is for a method that resamples, so every estimate is repeatable.

Start from `design(table, question)`, the shared preparation. It drops the rows
with a missing value, one-hot encodes dimension covariates, and refuses every
question the table cannot answer, with the reason. It returns the arrays
`treated` (bool), `outcome` and `covariates` (2-D, one column per encoded
covariate, named in `columns`). Before calling your estimator, the registry has
also checked that the design identifies the effect: the intercept, the treatment
and, unless `uses_covariates` is `False`, every encoded covariate must be
linearly independent, with more rows than columns. An estimator that fails this
is an error row ("not identified: …"), and the others still run.

What your estimator returns is checked once more: an effect or bound that is not
a finite number becomes an error row naming the value, and so does an exception.
Neither ever hides the other estimators' results.

This example is a median difference with a seeded bootstrap interval, run by the
test suite as written:

```python
# plugins-example: estimator
from typing import ClassVar

import numpy as np

from sdf.analytics.causal import CausalQuestion, Estimate, EstimatorInfo, design


class MedianDifference:
    """Treated median minus control median, ignoring the covariates; a percentile bootstrap interval."""

    info: ClassVar[EstimatorInfo] = EstimatorInfo(
        "median-difference",
        "Difference of the groups' medians, with a bootstrap interval",
        uses_covariates=False,
    )

    def estimate(self, table, question: CausalQuestion, *, confidence=0.95, seed=7) -> Estimate:
        d = design(table, question)
        y1, y0 = d.outcome[d.treated], d.outcome[~d.treated]
        effect = float(np.median(y1) - np.median(y0))
        rng = np.random.default_rng(seed)
        draws = [
            np.median(rng.choice(y1, len(y1))) - np.median(rng.choice(y0, len(y0))) for _ in range(200)
        ]
        alpha = (1 - confidence) / 2
        low, high = (float(q) for q in np.quantile(draws, [alpha, 1 - alpha]))
        method = f"median difference, 200 bootstrap resamples, {confidence * 100:g} %"
        return Estimate(self.info.name, effect, low, high, len(y1), len(y0), method)
```

**Keep it fast.** A request runs its estimators one after another within 30 s,
and the budget is checked only between estimators, so one slow estimator delays
its whole request. Aim for a few seconds at the published row limit
(`GET /api/v1/estimators` → `limits.max_rows`). The Effects page shows each
estimator's run time.

**Score it** on the promotion benchmark, whose true effect is known:

```python
from sdf.analytics.causal import default_estimators, score
from sdf.simulation.benchmark import PromotionBenchmark
from sdf.simulation.world import World
from sdf.synthesis.spec import GenerationSpec

estimators = default_estimators()
estimators.register(MedianDifference)
draw = PromotionBenchmark(confounding=1.0).draw(World.generate(GenerationSpec()))
scores = score(draw.table, draw.question, estimators,
               names=["median-difference", "regression-adjustment"], true_effect=draw.true_effect)
```

## A forecaster

A forecaster forecasts every SKU's daily demand for the next days, with a mean
and quantiles. It is a class with an `info` class attribute and two methods:

- `info = ForecasterInfo(name, description, requires=(), global_model=False)`.
  Set `global_model=True` for one model over all SKUs. The built-in
  `gradient-boosting` and `lightgbm` (`sdf/analytics/forecasters/boosted.py`)
  are examples: one model learns from every SKU's history, and a SKU with too
  little history of its own falls back to a simpler forecaster.
- `fit(history)` learns from a `DemandTable` (`days`, and `series`: one daily
  series per SKU) and returns `self`.
- `forecast(history, *, horizon, quantiles)` returns a
  `Forecast(forecaster, origin, sku_ids, mean, quantiles, method="")`:
  - `forecaster` is `self.info.name`, `origin` the day after the history's
    last day, and `sku_ids` the history's SKUs in its order;
  - `mean` and each `quantiles[level]` are arrays of SKUs × horizon, for the
    levels asked for;
  - use only the history you are given: the backtest cuts it at each origin.

Parameters are constructor keywords, published and checked like a
synthesizer's (`int`, `float`, `str` or `bool`, bounded by `param_bounds`).

The registry checks every forecast before it is scored: a wrong shape, other
SKUs, a missing level, a non-finite value, another name or an origin other
than the day after the history is refused, and that
forecaster becomes an error row while the others still run. Negative values are
set to 0, and quantiles that cross are sorted; both are counted in the row's
`method`, never silent.

This example forecasts each day as the mean of the same weekday over the last
few weeks, and takes the quantiles from those same days. The test suite runs it
as written:

```python
# plugins-example: forecaster
from datetime import timedelta
from typing import ClassVar

import numpy as np

from sdf.analytics.forecasters import Forecast, ForecasterInfo


class WeekdayMean:
    """Each day: the mean of the same weekday over the last `weeks` weeks; those days' spread gives the quantiles."""

    info: ClassVar[ForecasterInfo] = ForecasterInfo(
        "weekday-mean", "Mean of the same weekday over the last weeks, with its quantiles"
    )
    param_bounds: ClassVar[dict] = {"weeks": (1, 52)}

    def __init__(self, weeks: int = 4):
        self.weeks = weeks

    def fit(self, history):
        return self  # nothing to learn beyond the history each forecast gets

    def forecast(self, history, *, horizon, quantiles) -> Forecast:
        y = np.array([history.series[s] for s in history.series], dtype=float)
        n = y.shape[1]
        mean = np.zeros((len(y), horizon))
        qs = {q: np.zeros((len(y), horizon)) for q in quantiles}
        for k in range(horizon):
            same = np.arange(n + k - 7 * (k // 7 + 1), -1, -7)[: self.weeks]  # the same weekday, before the origin
            days = y[:, same] if len(same) else y[:, -1:]
            mean[:, k] = days.mean(axis=1)
            for q, value in zip(quantiles, np.quantile(days, quantiles, axis=1)):
                qs[q][:, k] = value
        origin = history.days[-1] + timedelta(days=1)
        method = f"the same weekday over the last {self.weeks} weeks"
        return Forecast(self.info.name, origin, tuple(history.series), mean, qs, method)
```

**Keep it fast.** A backtest runs its forecasters one after another, each from
every origin, within 30 s, and the budget is checked between origins. Aim for
about a second per origin on the published SKU limit
(`GET /api/v1/forecasters` → `limits.max_skus`); `sdf forecast` prints each
forecaster's run time.

**Score it** on the demand benchmark, whose true distribution is known, next to
the built-ins:

```python
from sdf.analytics.forecasters import backtest, default_forecasters
from sdf.simulation.benchmark import DemandBenchmark

forecasters = default_forecasters()
forecasters.register(WeekdayMean)
draw = DemandBenchmark().draw()
result = backtest(["weekday-mean", "seasonal-naive"], draw.table, truth=draw.truth, registry=forecasters)
```

`result.scores` has a row per forecaster and a `true-distribution` row: the
exact distribution the benchmark drew from, whose pinball loss no forecaster
beats on average. A `relative_wape` below 1 means your forecaster beats
seasonal naive on the same points.

## A detector

A detector finds anomalous SKU-days in a `SignalFrame`: `days`, `sku_ids`, and
`signals`, a dict of arrays of SKUs × days. The world's frame
(`sdf.simulation.signals.signal_frame`) has `demand`, and the `on_hand` and
`receipts` of the service-level policy replayed on it. A detector is a class
with an `info` class attribute and two methods:

- `info = DetectorInfo(name, description, requires=(), signals=("demand",))`:
  `signals` names the frame's columns it reads.
- `scores(frame)` rates every SKU-day: an array of the frame's shape, finite,
  larger meaning more anomalous. The benchmark ranks detectors by it, apart
  from their threshold.
- `detect(frame)` returns the points it would alarm on, as
  `Detection(sku_id, day, score, direction, signals)`, `direction` being
  `spike`, `drop` or `other`.

The registry refuses scores of the wrong shape or with a non-finite value, a
detection outside the frame and a frame without the signals the detector
reads; in the benchmark, that detector becomes an error row.

This example is a stock-balance rule: a day whose stock fell by more than its
demand explains, with no receipt, has lost stock. It finds the benchmark's
`shrinkage` exactly, which no demand-only detector can see. The test suite runs
it as written:

```python
# plugins-example: detector
from typing import ClassVar

import numpy as np

from sdf.analytics.detectors import Detection, DetectorInfo


class StockBalance:
    """Stock that went missing: today's stock below yesterday's plus receipts minus demand."""

    info: ClassVar[DetectorInfo] = DetectorInfo(
        "stock-balance", "Stock lost with no demand or receipt to explain it", signals=("demand", "on_hand", "receipts")
    )
    param_bounds: ClassVar[dict] = {"tolerance": (0.0, None)}

    def __init__(self, tolerance: float = 1e-6):
        self.tolerance = tolerance

    def scores(self, frame):
        on_hand = np.nan_to_num(frame.signals["on_hand"])
        change = np.diff(on_hand, axis=1, prepend=on_hand[:, :1])
        missing = -(change - np.nan_to_num(frame.signals["receipts"]) + np.nan_to_num(frame.signals["demand"]))
        missing[:, 0] = 0.0
        return np.maximum(missing, 0.0)

    def detect(self, frame):
        lost = self.scores(frame)
        return [
            Detection(frame.sku_ids[i], frame.days[t], float(lost[i, t]), "drop", ("on_hand",))
            for i, t in zip(*np.nonzero(lost > self.tolerance))
        ]
```

**Score it** on the anomaly benchmark, next to the built-ins:

```python
from sdf.analytics.detectors import default_detectors, score_detectors
from sdf.simulation.benchmark import AnomalyBenchmark
from sdf.simulation.signals import signal_frame
from sdf.simulation.world import World
from sdf.synthesis.spec import GenerationSpec

detectors = default_detectors()
detectors.register(StockBalance)
bench = AnomalyBenchmark()
frame, injected = bench.inject(signal_frame(World.generate(GenerationSpec())))
scores = score_detectors(["stock-balance", "isolation-forest"], frame, injected, kinds=bench.kinds, registry=detectors)
```

`scores` has, per detector, anomaly kind (and `all`) and cut, the precision,
the recall and the F1. `threshold` keeps what `detect` reports; `top-k` keeps
as many SKU-days as were injected, ranked by `scores`.

## Declaring and installing a plug-in

Put the class in a package and declare it in that package's `pyproject.toml`.
The entry-point name must equal `info.name`:

```toml
[project.entry-points."sdf.synthesizers"]
moving-average = "my_plugins.series:MovingAverageSeries"

[project.entry-points."sdf.datasets"]
stock-by-zone = "my_plugins.tables:StockByZone"

[project.entry-points."sdf.estimators"]
median-difference = "my_plugins.causal:MedianDifference"

[project.entry-points."sdf.forecasters"]
weekday-mean = "my_plugins.forecast:WeekdayMean"

[project.entry-points."sdf.detectors"]
stock-balance = "my_plugins.detect:StockBalance"
```

Then add the package to the environment that runs the API or the CLI, for
example `uv add my-plugins` (or `uv add --editable ../my-plugins` while
developing it). There is nothing to install from the UI. The next time the
API or the CLI starts, the plug-in is mounted.

For a quick experiment without packaging, register the class at runtime:

```python
from sdf.analytics.causal import default_estimators
from sdf.analytics.detectors import default_detectors
from sdf.analytics.forecasters import default_forecasters
from sdf.api.app import create_app
from sdf.application.datasets import default_datasets
from sdf.synthesis.registry import default_registry

synthesizers = default_registry()
synthesizers.register(MovingAverageSeries)
datasets = default_datasets()
datasets.register(StockByZone)
estimators = default_estimators()
estimators.register(MedianDifference)
forecasters = default_forecasters()
forecasters.register(WeekdayMean)
detectors = default_detectors()
detectors.register(StockBalance)
app = create_app(synthesizers=synthesizers, datasets=datasets, estimators=estimators,
                 forecasters=forecasters, detectors=detectors)   # serve it with uvicorn
```

## When a plug-in does not load

A broken plug-in installed through an entry point never breaks the registry,
the catalogue or the API. It is left out and listed with the reason:

- `default_registry().unavailable()`, `default_datasets().unavailable()`,
  `default_estimators().unavailable()` and `default_forecasters().unavailable()`;
- `"unavailable"` in `GET /api/v1/synthesizers`, `GET /api/v1/datasets`,
  `GET /api/v1/estimators` and `GET /api/v1/forecasters`;
- the Synthesizers page and the Effects page's estimation form, under
  **Unavailable**. The built-in `dowhy-backdoor` and `econml-dml` are listed
  there ("needs dowhy", "needs econml") until the `causal` extra is installed.

The usual reasons:

- a module in `requires` is not installed ("needs …");
- the entry-point name differs from `info.name`;
- the name is already taken, for example by a built-in (the reason names the
  holder: "name already provided by a builtin dataset (…)");
- a constructor argument has no default;
- `rows` does not take the world, an estimator has no `estimate` method, or a
  forecaster has no `fit` or `forecast` method;
- the parameter bounds are malformed, or a default breaks its own bounds.

A class registered at runtime with `register()` is checked the same way, but
the problem is raised at once as an exception instead of being listed, so a
quick experiment fails where it is set up.

## Checking it

- **Synthesizer, from the CLI** (installed plug-ins only):
  - `uv run sdf synth data/sample_online_retail_ii.csv --synthesizer moving-average` for a series;
  - `uv run sdf privacy data/sample_online_retail_ii.csv --synthesizer NAME` for a table.
- **Synthesizer, from the API or the Synthesizers page:** `GET /api/v1/synthesizers` lists it with its parameters, and a run is
  `POST /api/v1/synthesis/runs` with `{"synthesizer": "moving-average", "source": "sample", "params": {"window": 7}}`.
  The Synthesizers page does the same with a form and charts.
- **Dataset:** `GET /api/v1/datasets/stock-by-zone`, or choose it in the Explore page's source list.
- **Estimator:** `uv run sdf estimate --estimator median-difference --estimator regression-adjustment`
  (installed plug-ins), or `POST /api/v1/causal/estimates` with
  `{"estimators": ["median-difference"], "benchmark": {"confounding": 1.0}}`, or tick it in
  the Effects page's "Estimate from data" view; each shows its score against the true effect.
- **Forecaster:** `uv run sdf forecast --benchmark -f weekday-mean -f seasonal-naive`
  (installed plug-ins; `--param weekday-mean.weeks=8` sets a parameter), or
  `POST /api/v1/forecasts/backtest` with
  `{"forecasters": ["weekday-mean"], "source": {"benchmark": {}}}`; both show its
  scores next to the true distribution's.
- **In Python:**

  ```python
  from sdf.validation.evaluation import evaluate

  run = evaluate("moving-average", source="sample", params={"window": 7}, registry=synthesizers)
  run.metrics["fidelity_score"], run.params        # the scores, and every parameter used
  ```
