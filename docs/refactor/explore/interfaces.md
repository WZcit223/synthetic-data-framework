# Data exploration and synthesizer choice — interface contract

This is the **authoritative contract** for this sequence
([`00-overview.md`](00-overview.md)). PR plans link here and do not redefine
names, parameters or return types. If an implementation must change an
interface, the same PR updates this file, the affected plans and every caller.

Every example is labelled:

- **Current**: runs on `main` today.
- **Target (after PR n)**: becomes runnable when PR n merges; not supported before.
- **Later**: named here so the shape is fixed, but delivered by the causal
  modelling or the algorithm-phase sequence, not by this one.

Values shown as `…` depend on data; numbers are from the default world
(`GenerationSpec()`, seed 42) and are checked by the implementing PR's tests.

---

## 1. Tables: typed fields plus rows

### 1.1 Target (after PR 1): the table types

`sdf.foundation.tables` holds the shape every table shares. It is in the
foundation layer so any layer can return a table.

```python
from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["dimension", "time", "measure"]
Aggregate = Literal["sum", "mean", "min", "max"]


@dataclass(frozen=True)
class Field:
    name: str                 # column key, lower_snake_case
    label: str                # what a person reads
    kind: Kind                # dimension: group by it; time: an ISO date 'YYYY-MM-DD'; measure: a number
    unit: str | None = None   # measures only, for example 'units' or 'currency'
    aggregate: Aggregate | None = None   # measures only: the aggregation the pivot page selects first


@dataclass(frozen=True)
class DatasetInfo:
    name: str                 # catalogue key, lower-case, dash-separated
    label: str
    description: str
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class Table:
    info: DatasetInfo
    rows: list[tuple[Any, ...]]   # one value per field, in field order
```

`Field` rejects an unknown kind, a unit or aggregate on a non-measure, and a name
that is not `lower_snake_case`. A measure without an aggregate gets `"sum"`, so
`Field("channel", "Channel", "dimension")` and `Field("lines", "Lines",
"measure")` are both valid and the second one's `aggregate` is `"sum"`. `DatasetInfo` rejects duplicate field names.
`Table` checks that every row has exactly one value per field.

### 1.2 Target (after PR 1): the dataset catalogue

```python
from sdf.application.datasets import default_datasets
from sdf.simulation.world import World
from sdf.synthesis.spec import GenerationSpec

world = World.generate(GenerationSpec())
cat = default_datasets()
cat.names()              # ['inventory', 'order-lines', 'replenishment-plan', 'skus']
info = cat.info("order-lines")
[f.name for f in info.fields]
# ['date', 'sku_id', 'category', 'abc_class', 'channel', 'priority', 'status', 'quantity', 'line_value']
info.fields[-1]          # Field(name='line_value', label='Line value', kind='measure', unit='currency', aggregate='sum')

table = cat.build("order-lines", world)
len(table.rows)          # 28897 (every line, cancelled ones included; status is a field)
table.rows[0]            # ('2025-01-01', 'SKU-…', '…', 'A', 'ecommerce', 'standard', 'shipped', 1, …)
cat.origin("order-lines")   # 'builtin'
cat.unavailable()           # {} (declared providers that could not be mounted, with the reason)
```

The built-in datasets:

| name | one row per | fields |
|---|---|---|
| `order-lines` | outbound order line | `date` (time), `sku_id`, `category`, `abc_class`, `channel`, `priority`, `status`, `quantity` (units), `line_value` (currency: quantity × unit price) |
| `inventory` | inventory snapshot | `sku_id`, `category`, `abc_class`, `location_id`, `zone`, `on_hand`, `reserved`, `available`, `in_transit` (units), `stock_value` (currency: on hand × unit cost) |
| `skus` | SKU | `sku_id`, `name`, `category`, `abc_class`, `unit_cost`, `unit_price` (currency, aggregate `mean`), `shelf_life_days` (aggregate `mean`) |
| `replenishment-plan` | SKU | `sku_id`, `category`, `abc_class`, `demand_profile`, `needs_order` (dimension, `yes`/`no`), `safety_stock`, `reorder_point`, `order_up_to`, `available`, `order_qty` (units), under `ServiceLevelPolicy(service_level=0.95)` |

A provider is any class with this shape, the same way a synthesizer is:

```python
from collections.abc import Iterable
from typing import Any, ClassVar, Protocol

from sdf.foundation.tables import DatasetInfo
from sdf.simulation.world import World


class DatasetProvider(Protocol):
    info: ClassVar[DatasetInfo]

    def rows(self, world: World) -> Iterable[tuple[Any, ...]]: ...
```

Minimal provider (runnable after PR 1):

```python
from typing import ClassVar

from sdf.application.datasets import default_datasets
from sdf.foundation.tables import DatasetInfo, Field


class ChannelMix:
    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="channel-mix",
        label="Channel mix",
        description="Order lines per channel",
        fields=(Field("channel", "Channel", "dimension"), Field("lines", "Lines", "measure", unit="lines")),
    )

    def rows(self, world):
        counts = {}
        for o in world.stream("OutboundOrder"):
            counts[o.channel] = counts.get(o.channel, 0) + 1
        return sorted(counts.items())


cat = default_datasets()
cat.register(ChannelMix)
cat.build("channel-mix", world).rows     # [('ecommerce', …), ('store', …), ('wholesale', …)]
```

`DatasetCatalog` mirrors `SynthesizerRegistry`: `register(cls, *, replace=False)`,
`load_entry_points(group="sdf.datasets")`, `names(*, origin=None)`, `info(name)`,
`origin(name)` (`"builtin"`, `"plugin"` or `"runtime"`), `unavailable()`, and
`build(name, world)` (raises `KeyError` listing the valid names). The built-ins
are declared in this package's `pyproject.toml`:

```toml
[project.entry-points."sdf.datasets"]
inventory = "sdf.application.datasets:InventoryDataset"
order-lines = "sdf.application.datasets:OrderLinesDataset"
replenishment-plan = "sdf.application.datasets:ReplenishmentPlanDataset"
skus = "sdf.application.datasets:SkuDataset"
```

A plug-in that declares a built-in's name, or fails to load, is not mounted and
is reported by `unavailable()`; it never breaks the catalogue or the API.

The API holds one catalogue for its lifetime, so a provider registered at run
time is served by every later request:

```python
from sdf.api.app import create_app

datasets = default_datasets()
datasets.register(ChannelMix)
app = create_app(datasets=datasets)       # default: default_datasets(), built once
app.state.datasets is datasets            # True; GET /datasets lists 'channel-mix'
```

---

## 2. HTTP

Every endpoint is under `/api/v1`; its OpenAPI schema is the contract with the UI.
A table travels as `{"fields": [Field…], "rows": [[…], …]}`: a field is
`{"name", "label", "kind", "unit", "aggregate"}` (`unit` and `aggregate` are
`null` on dimensions and time fields) and a row is an array in field order. The
one exception is the experiment result, whose rows were objects before this
sequence and stay objects keyed by field name, so its existing clients keep
working; `toTable` (§3) accepts both forms.

### 2.1 Target (after PR 1)

```bash
curl -s localhost:8000/api/v1/datasets
# {"datasets": [{"name": "inventory", "label": "Inventory", "description": "…", "origin": "builtin",
#                "fields": [{"name": "sku_id", "label": "SKU", "kind": "dimension", "unit": null, "aggregate": null}, …]},
#               …],
#  "unavailable": {}}

curl -s 'localhost:8000/api/v1/datasets/order-lines'
# {"name": "order-lines", "label": "Outbound order lines", "world": "GenerationSpec(seed=42)",
#  "fields": [...], "rows": [["2025-01-01", "SKU-…", …], …], "total_rows": 28897, "truncated": false}

curl -s 'localhost:8000/api/v1/datasets/order-lines?limit=100'     # "truncated": true, 100 rows
curl -s localhost:8000/api/v1/datasets/nope                        # 404 {"detail": "unknown dataset 'nope'; choose from [...]"}
```

A response holds at most `MAX_DATASET_ROWS = 250_000` rows (and at most `limit`
when given); `truncated` says whether rows were left out.

```bash
curl -s localhost:8000/api/v1/experiments/catalog
# {"interventions": ["baseline", "promo_spike", "supply_disruption", "seasonal_downturn", "high_variability"],
#  "policies": [{"kind": "naive",
#                "params": [{"name": "lead_time_days", "type": "int", "default": 7, "min": 1, "max": 90},
#                           {"name": "review_days", "type": "int", "default": 7, "min": 1, "max": 90}]},
#               {"kind": "service-level",
#                "params": [{"name": "service_level", "type": "float", "default": 0.95, "min": 0.5, "max": 1.0,
#                            "exclusive": true},
#                           {"name": "lead_time_days", …}, {"name": "review_days", …}]}],
#  "outcomes": ["replenishment_need", "active_stockouts", "simulated_cost"],
#  "max_per_list": 6}
```

A parameter is always described by this one JSON shape, here and for
synthesizers (§4): `{"name", "type", "default", "min", "max", "exclusive"}`, where
`type` is `int`, `float`, `str` or `bool`, `min` and `max` are `null` when
unbounded, and `exclusive: true` means the bounds themselves are not allowed.
The catalogue's bounds are the ones `POST /experiments` enforces, so a form built
from it cannot send a request the endpoint rejects.

The experiment result keeps its rows and gains their fields:

```bash
curl -s -X POST localhost:8000/api/v1/experiments -H 'content-type: application/json' -d '{
  "interventions": ["baseline", "promo_spike"],
  "policies": [{"kind": "naive"}, {"kind": "service-level", "service_level": 0.95}],
  "outcomes": ["replenishment_need"]}'
# {"rows": [{"intervention": "baseline", "policy": "naive", "metric": "skus_needing_order", "value": …}, …],
#  "fields": [{"name": "intervention", "kind": "dimension", …}, {"name": "policy", …},
#             {"name": "metric", …}, {"name": "value", "kind": "measure", …}]}
```

### 2.2 Target (after PR 3)

See §4.2.

---

## 3. The pivot engine (`ui/pivot.js`)

### 3.1 Target (after PR 2)

A pure ES module with no DOM access, so Node's test runner covers it
(`node --test ui/`).

```javascript
import { pivot, toTable } from "./pivot.js";

// toTable accepts a table payload (§2) whose rows are arrays or objects
const table = toTable(await api("/datasets/order-lines"));

const result = pivot(table, {
  rows:    [{ field: "category" }],
  columns: [{ field: "date", grain: "month" }],        // grain: day | week | month | quarter | year | weekday
  values:  [{ field: "line_value", agg: "sum" }],      // agg: sum | count | count_distinct | mean | median | min | max
  filters: { status: { exclude: ["cancelled"] } },     // or { include: [...] }
  showAs:  "value",                                    // value | share_of_total | share_of_row | share_of_column
  sort:    { by: "value", dir: "desc" },               // by: label | value (the first value's row total)
  subtotals: true,
});

result.columns        // [{ key: ["2025-01"] }, { key: ["2025-02"] }, { key: ["2025-03"] }]
result.rows[0]        // { key: ["electronics"], depth: 0, group: false, cells: [[…], […], […]], total: […] }
result.totals         // { columns: [[…], […], […]], grand: […] }  (one entry per value)
result.stats          // { rowsIn: 28897, rowsUsed: 28033, ms: … }
```

Rules the engine keeps:

- A total is aggregated from the underlying rows, never from the cells it
  sums: the mean of a total is the mean of its rows, not the mean of the cell
  means.
- With two or more row fields and `subtotals: true`, each outer group is emitted
  as a `group: true` row carrying its subtotal, before its children, so the page
  can collapse it.
- `count` counts rows; `count_distinct` counts distinct values of the field.
  Every other aggregation ignores a missing value (`null`).
- A week key is its ISO week (`2025-W02`); weekday keys run `Mon` to `Sun`; a
  month key is `2025-01`; a quarter key is `2025-Q1`.
- Blank cells are `null`, never `0`.
- `showAs` shares are fractions (0–1) of the grand, row or column total of the
  same value.

The page keeps the whole view in its address (`explore.html#view=…`, a compact
JSON of the dataset or source and the view above), so a link reproduces it.

---

## 4. Synthesizer catalogue and evaluation

### 4.1 Target (after PR 3): parameters and evaluation

```python
from sdf.synthesis.registry import default_registry

reg = default_registry()
reg.params("bootstrap-table")
# (Param(name='seed', type='int', default=7, min=None, max=None, exclusive=False),
#  Param(name='jitter', type='float', default=0.05, min=None, max=None, exclusive=False))
reg.params("warehouse-spec")   # () : its GenerationSpec comes from the world request, not from a form
```

`Param` (in `sdf.synthesis.api`) is the parameter shape of §2.1:
`Param(name, type, default, min=None, max=None, exclusive=False)`. It covers each
keyword argument whose type is `int`, `float`, `str` or `bool`; other arguments
are supplied by the framework. A synthesizer may narrow its parameters with a
class attribute `param_bounds: ClassVar[dict[str, tuple[float | None, float |
None]]]`, for example `{"jitter": (0.0, 1.0)}`; without it they are unbounded. A
`produces="warehouse"` synthesizer takes `spec: GenerationSpec`.

```python
from sdf.validation.evaluation import evaluate, sources

sources()          # {'sample': 'data/sample_online_retail_ii.csv', 'retail-10k': 'data/online_retail_ii_2010_10k.csv'}
                   # (only files that exist under the data directory, default ./data or $SDF_DATA_DIR)
run = evaluate("seasonal-profile", source="sample", params={"seed": 7})
run.kind           # 'series'
run.metrics        # {'ks_statistic': …, 'profile_corr': …, 'mean_delta_pct': …, 'std_delta_pct': …, 'fidelity_score': …}
                   # the same numbers `sdf synth data/sample_online_retail_ii.csv` prints
run.table          # Table: fields (step: dimension, origin: dimension real|synthetic, value: measure)

run = evaluate("bootstrap-table", source="sample")
run.kind           # 'table'
run.metrics        # {'n_real': …, 'dcr_median': …, 'clone_risk_pct': …, 'verdict': '…', …}  as `sdf privacy` prints
run.table          # Table: fields (origin, qty, price, hour, weekday)

evaluate("warehouse-spec", source="sample")   # ValueError: warehouse-spec produces a warehouse; choose it for the world instead
evaluate("nope", source="sample")             # KeyError listing the synthesizers
```

`sdf synth` and `sdf privacy` call `evaluate` and print the same numbers as today.
`evaluate` takes `registry: SynthesizerRegistry | None = None` (default
`default_registry()`), so a caller with its own registry evaluates its own
plug-ins.

**One registry per application, and a world keeps its generator.** The API
holds one synthesizer registry for its lifetime, and every path that creates a
synthesizer uses it: the catalogue, runs, `POST /world`, and the regeneration
a scenario does. A world remembers which synthesizer built it and from which
registry, so a scenario regenerates it with the same generator instead of
falling back to `warehouse-spec`:

```python
from sdf.api.app import create_app
from sdf.simulation.intervention import SpecIntervention
from sdf.simulation.world import World
from sdf.synthesis.registry import default_registry

synthesizers = default_registry()
synthesizers.register(MyWarehouseGenerator)          # produces="warehouse", takes spec=
app = create_app(synthesizers=synthesizers)          # default: default_registry(), built once
app.state.synthesizers is synthesizers               # True

world = World.generate(spec, synthesizer="my-warehouse", synthesizers=synthesizers)
world.synthesizer                                    # 'my-warehouse'
SpecIntervention.named("promo_spike").apply(world).synthesizer   # 'my-warehouse'
World.generate(spec).synthesizer                     # 'warehouse-spec' (the default, from default_registry())
```

`World.synthesizers` (the registry) is kept with the world but is not part of
its equality or its printed form.

### 4.2 Target (after PR 3): HTTP

```bash
curl -s localhost:8000/api/v1/synthesizers
# {"synthesizers": [{"name": "bootstrap-table", "produces": "table", "needs_fit": true, "origin": "builtin",
#                    "description": "…", "requires": [],
#                    "params": [{"name": "seed", "type": "int", "default": 7, "min": null, "max": null, "exclusive": false}, …]},
#                   …],
#  "unavailable": {"gaussian-copula": "needs copulas, pandas"}}

curl -s localhost:8000/api/v1/synthesis/sources
# {"sources": [{"id": "sample", "label": "sample_online_retail_ii.csv"}, {"id": "retail-10k", "label": "…"}]}

curl -s -X POST localhost:8000/api/v1/synthesis/runs -H 'content-type: application/json' \
     -d '{"synthesizer": "seasonal-profile", "source": "sample", "params": {"seed": 7}}'
# {"synthesizer": "seasonal-profile", "source": "sample", "kind": "series",
#  "metrics": {"fidelity_score": …, …}, "fields": [...], "rows": [...]}

curl -s -X POST localhost:8000/api/v1/world -H 'content-type: application/json' \
     -d '{"synthesizer": "warehouse-spec", "n_skus": 80}'
# as today; a synthesizer that does not produce a warehouse answers 422
```

A run answers 422 for an unknown synthesizer, a parameter it does not take or
of the wrong type, an unknown source, or a synthesizer that is unavailable.

---

## 5. Later

These shapes are fixed now so the next sequences plug in without changing the
pivot page or the table contract.

- **Causal modelling.** Experiment rows (§2.1) are already the treatment and
  outcome table: `intervention` is the treatment, each `metric` an outcome. An
  effect estimator publishes its estimates as a table, for example
  `POST /api/v1/effects` answering `{"fields": [treatment, outcome, estimate,
  ci_low, ci_high, method], "rows": [...]}`, which the pivot page opens like any
  other table. New interventions keep implementing `Intervention` from the
  structure contract.
- **Algorithm phase.** A real algorithm's outputs are published as a dataset
  provider in the `sdf.datasets` group (for example `forecast-backtest`: date,
  model, actual, predicted, absolute error), and a real synthesizer is a plug-in
  whose keyword arguments become its form (§4.1) and whose runs are scored by the
  same evaluation. The `ALGORITHM-HOOK` markers stay where the stand-ins are.
