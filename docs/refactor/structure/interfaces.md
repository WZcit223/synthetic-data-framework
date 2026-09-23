# Structure refactor — interface contract

This is the **authoritative contract** for the structure sequence
([`00-overview.md`](00-overview.md)). PR plans link here and do not redefine
names, parameters or return types. If an implementation must change an
interface, the same PR updates this file, the affected plans and every caller.

Every example is labelled:

- **Current** — runs on `main` today.
- **Target (after PR n)** — becomes runnable when PR n merges; not supported before.
- **Later (F1/F2/F3)** — named here so the shape is fixed, but not delivered in this
  sequence.

Values shown as `…` depend on data; values shown as numbers are from the default
world (`GenerationSpec()`, seed 42) and are verified by the implementing PR's tests.

---

## 1. Simulation layer (`sdf.simulation`) — F2

**Idea.** One dataset (`World`) can be changed by `Intervention`s and managed by
`Policy`s. `Outcome`s measure the result. An `Experiment` runs every
intervention × policy combination and returns tidy rows, one per
(intervention, policy, metric). A causal model later treats interventions as
`do()` operations and the tidy rows as its treatment/outcome table.

### 1.1 Current (for comparison)

```python
from sdf.application.intelligence import WarehouseIntelligence
from sdf.application.economics import financial_impact
from sdf.application.scenarios import run_scenarios
from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec

_wh, reg = build_registry(GenerationSpec())
intel = WarehouseIntelligence(reg)
intel.replenishment_ss_policy(service_level=0.95)["skus_needing_order"]   # 62
financial_impact(intel)["annualised_net_saving"]                           # 1858631
run_scenarios(GenerationSpec())["scenarios"][1]["scenario"]                # 'promo_spike'
```

Three unrelated entry points; none can be combined with another.

### 1.2 Target (after PR 2): world, policies, levels, plans

```python
from sdf.simulation.world import World
from sdf.simulation.policy import Levels, NaivePolicy, ServiceLevelPolicy, plan_orders
from sdf.synthesis.spec import GenerationSpec

world = World.generate(GenerationSpec())       # immutable: registry + spec + label
world.label                                    # 'GenerationSpec(seed=42)'
len(world.stream("OutboundOrder"))             # 28897

policy = ServiceLevelPolicy(service_level=0.95)            # lead_time_days=7, review_days=7
policy.name                                                # 'service-level-95'
profile = world.demand().profile("SKU-00001")              # sdf.analytics.demand.DemandProfile
policy.levels(profile)                                     # Levels(reorder_point=…, order_up_to=…, safety_stock=…)
ServiceLevelPolicy(z=1.645).name                           # 'service-level-z1.645' (explicit z, no table lookup)

plan = plan_orders(world, policy)                          # list[PlanRow], sorted by order_qty desc
plan[0]                                                    # PlanRow(sku_id=…, name=…, profile=…, safety_stock=…,
                                                           #         reorder_point=…, order_up_to=…, available=…, order_qty=…)
sum(1 for r in plan if r.order_qty > 0)                    # 62  (same as today's skus_needing_order)

NaivePolicy().levels(profile)                              # no safety stock: s = μ·L, S = μ·(L+R)
```

`Levels.safety_stock` (default `0.0`) is the part of the reorder point held
against variability; reports sum it. `ServiceLevelPolicy` takes the service
level, or an explicit `z` that overrides the table (the economics counterfactual
passes `CostModel.service_z`). `z_for` and `Z_FOR_SERVICE_LEVEL` live in
`sdf.simulation.policy`.

`Policy` is a protocol; any object with these members is a policy:

```python
from typing import Protocol

from sdf.analytics.demand import DemandProfile
from sdf.simulation.policy import Levels


class Policy(Protocol):
    name: str
    lead_time_days: int

    def levels(self, profile: DemandProfile) -> Levels: ...
```

Minimal extension (runnable after PR 2), a policy that always covers ten days:

```python
from dataclasses import dataclass

from sdf.simulation.policy import Levels


@dataclass(frozen=True)
class FixedCoverPolicy:
    days: int = 10
    lead_time_days: int = 7
    name: str = "cover-10d"

    def levels(self, profile):
        s = profile.mean * self.days
        return Levels(reorder_point=s, order_up_to=s)
```

### 1.3 Target (after PR 2): the inventory engine

```python
from sdf.simulation.engine import InventoryTrace, simulate_inventory
from sdf.simulation.policy import Levels

trace = simulate_inventory([5.0, 0.0, 9.0, 4.0], Levels(reorder_point=6.0, order_up_to=12.0), lead_time_days=2)
trace                                   # InventoryTrace(unmet_units=…, holding_unit_days=…, orders=…, total_demand=…)
trace.fill_rate                         # 1 − unmet_units / total_demand
```

This is today's `economics._simulate` without the cost arithmetic, which moves
into an `Outcome`. With the same inputs it returns the same unmet units, holding
unit-days and order count.

### 1.4 Target (after PR 2): interventions

```python
from sdf.simulation.intervention import Baseline, SpecIntervention

Baseline().apply(world) is world                                  # True
promo = SpecIntervention.named("promo_spike")                     # from sdf.synthesis.scenarios.SCENARIOS
promo.apply(world).label                                          # 'promo_spike'
SpecIntervention.named("nope")                                    # KeyError: unknown scenario 'nope'; choose from [...]
```

```python
from typing import Protocol

from sdf.simulation.world import World


class Intervention(Protocol):
    name: str

    def apply(self, world: World) -> World: ...
```

Minimal extension (runnable after PR 2): an intervention that edits the data
itself rather than the generator. This is the shape a causal `do()` will take:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DropExpressOrders:
    name: str = "no_express"

    def apply(self, world):
        orders = [o for o in world.stream("OutboundOrder") if o.priority != "express"]
        return world.with_stream("OutboundOrder", orders, label=self.name)
```

`World.with_stream(entity_type, rows, *, label)` returns a new `World` whose
registry has that entity stream replaced; the original world is unchanged.

### 1.5 Target (after PR 2): outcomes and experiments

```python
from sdf.simulation.experiment import Experiment, OutcomeRow
from sdf.simulation.outcome import ActiveStockouts, CostModel, ReplenishmentNeed, SimulatedCost

exp = Experiment(
    world=world,
    interventions=[Baseline(), SpecIntervention.named("promo_spike")],
    policies=[NaivePolicy(), ServiceLevelPolicy(service_level=0.95)],
    outcomes=[ReplenishmentNeed(), ActiveStockouts(), SimulatedCost(CostModel())],
)
rows = exp.run()                         # list[OutcomeRow], tidy
rows[0]                                  # OutcomeRow(intervention='baseline', policy='naive',
                                         #            metric='skus_needing_order', value=…)
{r.metric for r in rows}                 # {'skus_needing_order', 'safety_stock_units', 'intermittent_needing_order',
                                         #  'active_stockouts', 'unmet_units', 'fill_rate', 'holding_cost',
                                         #  'order_cost', 'lost_margin'}
```

```python
from typing import Protocol

from sdf.simulation.world import World


class Outcome(Protocol):
    name: str

    def measure(self, world: World, policy: "Policy") -> dict[str, float]: ...
```

`SimulatedCost` replays each SKU's demand history under the policy with
`simulate_inventory` and reports `unmet_units`, `fill_rate` (1 − unmet units /
total demand), `holding_cost`, `order_cost` and `lost_margin`.

`CostModel` moves from `application/economics.py` to `sdf.simulation.outcome`
in PR 2, because the simulation layer cannot import the application layer.
Every caller imports it from the new module; no alias stays behind.

After PR 2, `financial_impact` and `run_scenarios` are thin wrappers over
`Experiment`, keep their current signatures and return values, and every golden
number stays identical.

**Later (F2).** A causal module consumes `exp.run()` rows directly: the
intervention column is the treatment, the metric columns are outcomes. New
intervention types (demand shocks, lead-time changes, `do(variable=value)` on a
structural model) only need the `Intervention` protocol.

---

## 2. Synthesizer contract (`sdf.synthesis.api`, `sdf.synthesis.registry`) — F1

### 2.1 Current (for comparison)

```python
from sdf.synthesis.fit import FittedSeasonalDemand
from sdf.synthesis.warehouse import WarehouseGenerator
from sdf.validation.privacy import bootstrap_synthesize

WarehouseGenerator(spec).generate()                      # SyntheticWarehouse
FittedSeasonalDemand(seed=7).fit(series, 7).generate(42) # list[float]
bootstrap_synthesize(rows, seed=7)                       # list[tuple[float, ...]]  (lives in validation/)
```

Four calling conventions; there is no way to list or choose them by name.

### 2.2 Target (after PR 4)

```python
from sdf.synthesis.api import SeriesData, TableData
from sdf.synthesis.registry import default_registry
from sdf.synthesis.spec import GenerationSpec

reg = default_registry()
reg.names()          # ['bootstrap-table', 'seasonal-profile', 'warehouse-spec']
                     # (+ 'gaussian-copula' when the `synthesis` extra is installed)
reg.info("seasonal-profile")
# SynthesizerInfo(name='seasonal-profile', produces='series', needs_fit=True,
#                 description='Per-cycle mean profile × resampled multiplicative residuals')

series_model = reg.create("seasonal-profile", seed=7).fit(SeriesData(values=series, period=7))
series_model.sample(42)                         # list[float], 42 points
series_model.sample(42, seed=1)                 # pinned: equal for equal seeds

table_model = reg.create("bootstrap-table", seed=7).fit(TableData(rows=rows, columns=("qty", "price", "hour", "weekday")))
table_model.sample()                            # list[tuple[float, ...]], len(rows) rows

world_gen = reg.create("warehouse-spec", spec=GenerationSpec(n_skus=50))
world_gen.sample()                              # SyntheticWarehouse (seed from the spec); needs no fit()
```

The contract:

```python
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol, Self

Produces = Literal["warehouse", "series", "table"]


@dataclass(frozen=True)
class SynthesizerInfo:
    name: str          # registry key, lower-case, dash-separated
    produces: Produces
    needs_fit: bool    # False: configured entirely by constructor arguments
    description: str
    requires: tuple[str, ...] = ()   # importable modules it needs; missing ones make it unavailable


@dataclass(frozen=True)
class SeriesData:
    values: tuple[float, ...] | list[float]
    period: int


@dataclass(frozen=True)
class TableData:
    rows: list[tuple[float, ...]]
    columns: tuple[str, ...]


class Synthesizer(Protocol):
    info: ClassVar[SynthesizerInfo]

    def fit(self, data: Any) -> Self: ...                                   # SeriesData | TableData | None
    def sample(self, n: int | None = None, *, seed: int | None = None) -> Any: ...
```

`SynthesizerRegistry` methods: `register(cls, *, replace=False)` (validates the
metadata and raises on a duplicate name), `load_entry_points(group="sdf.synthesizers")`,
`create(name, **config)` (raises `KeyError` listing the valid names),
`names(*, origin=None)`, `info(name)`, `origin(name)` (`"builtin"`, `"plugin"` or
`"runtime"`) and `unavailable()` (declared but not mounted, with the reason).
`SynthesizerInfo` also carries `requires: tuple[str, ...] = ()`, the importable
modules a synthesizer needs.

**Every synthesizer is a plug-in, ours included** (project lead, 2026-09-23).
The built-ins are declared in this package's own `pyproject.toml`, in the same
entry-point group a third-party package uses, and `default_registry()` mounts the
whole group. "Built-in" only means "declared by `synthetic-data-framework`":

```toml
[project.entry-points."sdf.synthesizers"]
bootstrap-table = "sdf.synthesis.bootstrap:BootstrapTable"
gaussian-copula = "sdf.synthesis.sdv_synth:GaussianCopulaTable"   # needs the synthesis extra
seasonal-profile = "sdf.synthesis.fit:FittedSeasonalDemand"
warehouse-spec = "sdf.synthesis.warehouse:WarehouseSpecSynthesizer"
```

A declared synthesizer whose `requires` are missing, or that fails to load, is
skipped and reported by `unavailable()`; it never breaks the registry or the CLI.

Minimal plug-in (runnable after PR 4):

```python
import random
from typing import ClassVar

from sdf.synthesis.api import SeriesData, SynthesizerInfo
from sdf.synthesis.registry import default_registry


class ShuffleSeries:
    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="shuffle-series", produces="series", needs_fit=True, description="Random permutation of the fitted series"
    )

    def __init__(self, *, seed: int = 0) -> None:
        self._rng = random.Random(seed)
        self._values: list[float] = []

    def fit(self, data: SeriesData) -> "ShuffleSeries":
        self._values = list(data.values)
        return self

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[float]:
        rng = random.Random(seed) if seed is not None else self._rng
        values = self._values[:]
        rng.shuffle(values)
        return values if n is None else values[:n]   # n=0 returns an empty sample


reg = default_registry()
reg.register(ShuffleSeries)
reg.create("shuffle-series", seed=3).fit(SeriesData(values=[1.0, 2.0, 3.0], period=1)).sample()
```

The built-ins after PR 4: `FittedSeasonalDemand` (`sdf.synthesis.fit`) is
`seasonal-profile`; `BootstrapTable` (`sdf.synthesis.bootstrap`) is
`bootstrap-table` and replaces `bootstrap_synthesize`; `WarehouseSpecSynthesizer`
(`sdf.synthesis.warehouse`) is `warehouse-spec`; `GaussianCopulaTable`
(`sdf.synthesis.sdv_synth`) is `gaussian-copula`. `FittedHourlyDemand(model=None,
*, seed=7)` fits any series synthesizer on the hourly series derived from orders.
The privacy feature table's columns are `sdf.validation.privacy.FEATURE_COLUMNS`.

Consumers choose a synthesizer by name (after PR 4):

```python
from sdf.validation.tstr import tstr_report

tstr_report(orders, synthesizer="seasonal-profile")        # default, same numbers as today
```

```bash
uv run sdf synth data/sample_online_retail_ii.csv --synthesizer seasonal-profile
uv run sdf privacy data/sample_online_retail_ii.csv --synthesizer bootstrap-table
```

A third-party package mounts its own synthesizer the same way (after PR 4):

```toml
[project.entry-points."sdf.synthesizers"]
shuffle-series = "my_package.synth:ShuffleSeries"
```

**Later (F1).** Choosing and configuring plug-ins from the UI, and documented
guidance for writing one, build on this without changing the contract.

---

## 3. Agent executor (`sdf.application.agent`)

### 3.1 Current

```python
agent.call(log, "place_order", sku_id="SKU-00176", quantity=66)
# runs the tool function and only notes "requires human approval" in the log
```

### 3.2 Target (after PR 5)

```python
from sdf.application.agent import WarehouseAgent
from sdf.application.agent.executor import Executor
from sdf.application.agent.planner import KeywordPlanner, PlannedCall, Planner
from sdf.application.agent.tools import Tool, ToolResult

res = agent.executor.call(log, "place_order", sku_id="SKU-00176", quantity=66)
res   # ToolResult(ok=True, status='pending_approval', data={'tool': 'place_order', 'args': {...}}, error=None)
      # the tool function was NOT called

agent.executor.call(log, "place_order", approved=True, sku_id="SKU-00176", quantity=66)
      # ToolResult(ok=True, status='done', data=…)  — only an explicit approval runs it

agent.executor.call(log, "financial_impact")
      # ToolResult(ok=False, status='failed', error='no demand')  on an empty registry

KeywordPlanner().plan("should I reorder and what is the money impact?")
      # [PlannedCall(tool='replenishment', args={}), PlannedCall(tool='financial_impact', args={}),
      #  PlannedCall(tool='place_order', args=…)]
```

```python
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    status: Literal["done", "pending_approval", "failed"]
    data: Any = None
    error: str | None = None


@dataclass(frozen=True)
class PlannedCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


class Planner(Protocol):
    def plan(self, query: str) -> list[PlannedCall]: ...
```

The executor enforces, for every caller: a tool with `requires_approval=True` or
`read_only=False` is never run without `approved=True`.

---

## 4. Backend state and the HTTP / UI boundary — F3

### 4.1 Current

`sdf.api.app` holds a module-level mutable `_state` that `regenerate()` updates
in three assignments. The API also serves `static/dashboard.html` at `/`, and
the dashboard fetches unversioned paths such as `/application/overview`.

### 4.2 Target (after PR 6): app factory and atomic snapshot

```python
from sdf.api.app import create_app
from sdf.api.state import GenerateLimits, Snapshot, WorldStore

app = create_app(limits=GenerateLimits(max_skus=500, max_horizon_days=180))
store: WorldStore = app.state.store
snap: Snapshot = store.current          # Snapshot(world=World(...), intel=WarehouseIntelligence(...), generated_ms=…)
store.regenerate(GenerationSpec(n_skus=80))   # builds a new Snapshot, then replaces `current` in one assignment
```

`app = create_app()` remains the module-level ASGI object, so
`uv run uvicorn sdf.api.app:app` keeps working. Requests read `store.current`
once and use only that snapshot. `regenerate` takes the store's lock without
waiting (`lock.acquire(blocking=False)`) and raises `GenerationBusy` when another
generation holds it. `/generate` maps that to HTTP 409, and answers 422 when a
parameter exceeds `GenerateLimits`. Endpoint paths are
unchanged in PR 6.

### 4.3 Target (after PR 7): versioned JSON API and a separate UI

The backend serves JSON only, under `/api/v1`. Its OpenAPI schema
(`/api/v1/openapi.json`) is the contract with any UI.

| v1 endpoint | replaces |
|---|---|
| `GET /api/v1/health` | `GET /health` |
| `GET /api/v1/world` | `GET /foundation/summary` |
| `POST /api/v1/world` (JSON body: `n_skus`, `horizon_days`, `daily_orders_per_a_sku`, `stockout_pressure`, `seed`) | `POST /generate?…` |
| `GET /api/v1/overview` | `GET /application/overview` |
| `GET /api/v1/replenishment?service_level=&top_n=` | `GET /application/replenishment/ss` |
| `GET /api/v1/replenishment/comparison` | `GET /application/replenishment/comparison` (added in PR 3) |
| `GET /api/v1/top-movers`, `/demand-series`, `/demand-anomalies`, `/shelf-occupancy`, `/stocktake` | the `/application/...` equivalents |
| `GET /api/v1/quality`, `/backtest`, `/economics`, `/scenarios`, `/workflow/run` | `/synthesis/quality`, `/validation/backtest`, `/economics/impact`, `/scenarios`, `/workflow/run` |
| `GET /api/v1/ask?q=`, `/agent/ask?q=`, `/agent/tools`, `/export?entity=` | same names without the prefix |
| `POST /api/v1/experiments` | new: runs an `Experiment` (§1.5) from built-in names and returns `{"rows": [OutcomeRow...]}` |

```bash
curl -s -X POST localhost:8000/api/v1/experiments -H 'content-type: application/json' -d '{
  "interventions": ["baseline", "promo_spike"],
  "policies": [{"kind": "naive"}, {"kind": "service-level", "service_level": 0.95}],
  "outcomes": ["replenishment_need", "simulated_cost"]
}'
# {"rows": [{"intervention": "baseline", "policy": "naive", "metric": "skus_needing_order", "value": …}, …]}
```

The UI lives in `ui/` (plain HTML/JS, outside the Python package). It reaches
the backend only through one helper, so the base URL is configurable and every
path it uses can be checked against the OpenAPI schema:

```javascript
// ui/app.js
const API = window.SDF_API_BASE ?? "/api/v1";
async function api(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}
const overview = await api("/overview");
```

Development hosting: `create_app(ui_dir=Path("ui"))` also mounts the static UI
at `/`. Setting `SDF_UI_DIR=ui` does the same for `uv run uvicorn sdf.api.app:app`.
The UI can also be hosted anywhere else; allowed origins come from
`SDF_CORS_ORIGINS`.

UI rule: the UI may reshape data it received (sort, filter, group, pivot, chart)
but computes no business number and writes nothing back except user intent
(generation parameters, questions, experiment choices).

**Later (F3).** A pivot view over `/api/v1/experiments` rows, and any richer UI
framework, build on this boundary without backend changes.
