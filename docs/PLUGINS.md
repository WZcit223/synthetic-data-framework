# Plug-ins: your own synthesizer or dataset

The framework has two plug-in points. Both are found through Python entry
points, so a plug-in is an ordinary installed package; nothing in this
repository changes when you add one.

| Plug-in | Entry-point group | Where it shows up |
|---|---|---|
| A **synthesizer** (an algorithm that generates a series, a table or a whole warehouse world) | `sdf.synthesizers` | `GET /api/v1/synthesizers`, the Synthesizers page, `sdf synth` / `sdf privacy` / `sdf tstr --synthesizer NAME`, and the dashboard's Generator choice for a warehouse generator |
| A **dataset provider** (a table computed from the current world, for the Explore page) | `sdf.datasets` | `GET /api/v1/datasets`, the Explore page's source list |

The built-ins are declared the same way, in this repository's `pyproject.toml`.
The contracts behind this guide are in
[`refactor/structure/interfaces.md`](refactor/structure/interfaces.md) §2
(synthesizers) and [`refactor/explore/interfaces.md`](refactor/explore/interfaces.md)
§1 and §4 (datasets, parameters, runs).

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

**Parameters.** Every constructor argument needs a default, so the registry
can create the synthesizer by name. Keyword arguments typed `int`, `float`,
`str` or `bool` (or one of those or `None`) are its *parameters*. The catalogue
publishes them with their defaults, and the run form on the Synthesizers page
is built from them. Two optional refinements:

- A class attribute `param_bounds = {"name": (min, max)}` narrows a numeric
  parameter; either end may be `None`. The registry refuses bounds that are not
  a (min, max) pair of finite numbers, bounds with min above max, and a default
  outside its own bounds.
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

## Declaring and installing a plug-in

Put the class in a package and declare it in that package's `pyproject.toml`.
The entry-point name must equal `info.name`:

```toml
[project.entry-points."sdf.synthesizers"]
moving-average = "my_plugins.series:MovingAverageSeries"

[project.entry-points."sdf.datasets"]
stock-by-zone = "my_plugins.tables:StockByZone"
```

Then add the package to the environment that runs the API or the CLI, for
example `uv add my-plugins` (or `uv add --editable ../my-plugins` while
developing it). There is nothing to install from the UI. The next time the
API or the CLI starts, the plug-in is mounted.

For a quick experiment without packaging, register the class at runtime:

```python
from sdf.api.app import create_app
from sdf.application.datasets import default_datasets
from sdf.synthesis.registry import default_registry

synthesizers = default_registry()
synthesizers.register(MovingAverageSeries)
datasets = default_datasets()
datasets.register(StockByZone)
app = create_app(synthesizers=synthesizers, datasets=datasets)   # serve it with uvicorn
```

## When a plug-in does not load

A broken plug-in installed through an entry point never breaks the registry,
the catalogue or the API. It is left out and listed with the reason:

- `default_registry().unavailable()` and `default_datasets().unavailable()`;
- `"unavailable"` in `GET /api/v1/synthesizers` and `GET /api/v1/datasets`;
- the Synthesizers page, under **Unavailable**.

The usual reasons:

- a module in `requires` is not installed ("needs …");
- the entry-point name differs from `info.name`;
- the name is already taken, for example by a built-in;
- a constructor argument has no default;
- `rows` does not take the world;
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
- **In Python:**

  ```python
  from sdf.validation.evaluation import evaluate

  run = evaluate("moving-average", source="sample", params={"window": 7}, registry=synthesizers)
  run.metrics["fidelity_score"], run.params        # the scores, and every parameter used
  ```
