# Causal modelling — interface contract

This is the **authoritative contract** for this sequence
([`00-overview.md`](00-overview.md)). PR plans link here and do not redefine
names, parameters or return types. If an implementation must change an
interface, the same PR updates this file, the affected plans and every caller.

Every example is labelled:

- **Current**: runs on `main` today.
- **Target (after PR n)**: becomes runnable when PR n merges; not supported before.

Values shown as `…` depend on data. The numbers shown come from spikes on the
default world (`GenerationSpec()`, seed 42) and are marked as such; the
implementing PR checks its own numbers in its tests and replaces these.

Tables follow the exploration contract
([`../explore/interfaces.md`](../explore/interfaces.md) §1): `Field`,
`DatasetInfo` and `Table` from `sdf.foundation.tables`, served as
`{"fields": [...], "rows": [[...], ...]}`.

---

## 1. Effect study: the simulator's answer

### 1.1 Current: one experiment, one seed

```python
from sdf.simulation import catalog
from sdf.simulation.experiment import Experiment
from sdf.simulation.world import World
from sdf.synthesis.spec import GenerationSpec

world = World.generate(GenerationSpec())
rows = Experiment(
    world,
    [catalog.intervention("baseline"), catalog.intervention("promo_spike")],
    [catalog.policy("service-level", service_level=0.95)],
    [catalog.outcome("simulated_cost")],
).run()
rows[0]   # OutcomeRow(intervention='baseline', policy='service-level-95', metric='unmet_units', value=…)
```

Each arm is measured once. The rows hold levels, not effects, and say nothing
about how much a level would move on another draw of the same world.

### 1.2 Target (after PR 1): `sdf.simulation.effects`

```python
from collections.abc import Sequence
from dataclasses import dataclass

from sdf.foundation.tables import Table
from sdf.synthesis.registry import SynthesizerRegistry
from sdf.synthesis.spec import GenerationSpec
from .intervention import Intervention
from .outcome import Outcome
from .policy import Policy
from .world import World

MAX_REPLICATES = 20


@dataclass(frozen=True)
class EffectStudy:
    """Each intervention against the baseline, on ``replicates`` paired worlds."""

    spec: GenerationSpec
    interventions: Sequence[Intervention]     # compared with Baseline(); "baseline" itself is refused here
    policies: Sequence[Policy]
    outcomes: Sequence[Outcome]
    replicates: int = 10                      # 2 to MAX_REPLICATES
    confidence: float = 0.95                  # of the interval; above 0.5, below 1
    synthesizer: str = "warehouse-spec"       # the world generator, as World.generate takes it
    synthesizers: SynthesizerRegistry | None = None
    baseline: World | None = None             # replicate 0's baseline, when the caller already holds it (the API's current world)

    def run(self) -> "EffectResult": ...


@dataclass(frozen=True)
class EffectResult:
    effects: Table       # dataset "effects", one row per intervention × policy × metric (§1.3)
    replicates: Table    # dataset "effect-replicates", one row per replicate × arm × policy × metric (§1.4)
```

Rules the implementation keeps:

- **Replicate r generates the world from `replace(spec, seed=spec.seed + r)`,**
  for r = 0 … R − 1. Replicate 0 is therefore the world `POST /experiments`
  measures, and its rows equal that experiment's rows.
- **Paired by seed.** Within one replicate, the baseline and every intervention
  come from that replicate's seed: `Baseline()` measures the world as
  generated, and a `SpecIntervention` regenerates from it with the same seed
  (it already does). The effect is the mean of the R paired differences
  `treated − baseline`.
- **Pairing needs a deterministic generator.** A warehouse generator is called
  as today, `reg.create(name, spec=spec).sample()`. Pairing holds only if that
  call returns the same world for the same spec, which means the generator
  takes its randomness from `spec.seed`. `warehouse-spec` does. The
  synthesizer contract does not yet require it of a plug-in, so:
  - PR 1 adds that requirement to the warehouse generator's contract and to
    the plug-in guide;
  - the study checks it before any replicate runs, against a reference world
    for replicate 0's spec. The reference is `baseline` when given; the API
    passes the snapshot's current world, the very world `POST /experiments`
    measures. Without `baseline` (the CLI), the reference is one generation
    of that spec. The study generates the spec once more and compares the
    two worlds' data, not only their measurements. Every source in
    `world.registry.sources()` must match by name, entity type and rows, in
    order, with rows compared by their dataclass equality. Every policy ×
    outcome value must match too. So a stateful generator that changes SKUs,
    inventory or any other rows, measured or not, is caught. If anything
    differs, it refuses
    with `ValueError`: "generator X is not deterministic in its spec; paired
    effects need the same world for the same seed" (422 through the API).

  The reference is kept as replicate 0's baseline. In the API, replicate 0 is
  therefore the held world itself, not a regeneration that might differ from
  it. A generator whose output changed since the world was built (stateful
  across calls) is refused by the comparison, not trusted.
- **What the interval assumes.** The Student-t interval is valid when the R
  replicate differences are independent draws. That holds when different
  seeds give independent worlds, which is a requirement of the warehouse
  generator's contract. PR 1 adds it next to the determinism requirement,
  and the plug-in guide states both. It cannot be checked from a few draws,
  so the effects are exactly as trustworthy as that requirement:
  - `warehouse-spec` meets it: every draw comes from `random.Random(seed)`.
  - A plug-in that correlates its seeds gives intervals that are too narrow.
    The contract says so rather than claiming validity for any generator.
- **Pairing buys precision.** Given independent replicates, a generator that
  shares its random stream between the baseline and an intervention's changed
  spec gives narrower intervals. One that does not gives wider, still correct
  ones. PR 1 tests `warehouse-spec`'s sharing directly: the baseline and
  `promo_spike` share their SKU, location and inventory tables for the same
  seed.
- **The interval** is Student's t on the paired differences, with R − 1
  degrees of freedom (`scipy.stats.t`). When every difference is equal, the
  interval collapses to the point (zero width), which is correct for a metric
  the intervention does not move.
- **The relative effect** is `effect / baseline mean`, or `None` when the
  baseline mean is 0.
- The study never mutates the API's current world. In the API, the snapshot's
  world is passed as `baseline` and read as replicate 0's baseline and the
  determinism check's reference (§1.2), never changed. Every other world the
  study generates itself from `spec`, with the given generator. In the CLI,
  with no `baseline`, it generates the reference too.
- It refuses `replicates` outside 2 … `MAX_REPLICATES`, `confidence` outside
  (0.5, 1), an empty list, and an intervention named `baseline`, with messages
  that name the field.

### 1.3 Target (after PR 1): the effects table

| Field | Label | Kind | Unit | Aggregate |
|---|---|---|---|---|
| `intervention` | Intervention | dimension | | |
| `policy` | Policy | dimension | | |
| `metric` | Metric | dimension | | |
| `baseline` | Baseline mean | measure | | mean |
| `treated` | Treated mean | measure | | mean |
| `effect` | Effect | measure | | mean |
| `ci_low` | Interval low | measure | | mean |
| `ci_high` | Interval high | measure | | mean |
| `relative_effect` | Relative effect | measure | share | mean |
| `replicates` | Replicates | measure | | min |
| `method` | Method | dimension | | |

`method` is `f"paired t, {confidence * 100:g} %"`, built from the study's own
`confidence`: `"paired t, 95 %"` at the default, `"paired t, 80 %"` at 0.8. Metrics keep
their own units, so a table mixes units across rows. That is why every measure
aggregates with `mean`, and why the Effects page draws one chart per metric
(PR 2).

Spike on the default world, `promo_spike` against the baseline under
`service-level-95`, 10 replicates, `simulated_cost` (about 4 s):

```python
from sdf.simulation.effects import EffectStudy

result = EffectStudy(
    GenerationSpec(),
    [catalog.intervention("promo_spike")],
    [catalog.policy("service-level", service_level=0.95)],
    [catalog.outcome("simulated_cost")],
    replicates=10,
).run()
[r for r in result.effects.rows if r[2] == "holding_cost"]
# [('promo_spike', 'service-level-95', 'holding_cost', 137600.0, 217400.0, 79790.0, 72250.0, 87330.0, 0.58, 10, 'paired t, 95 %')]   (spike, rounded)
[r for r in result.effects.rows if r[2] == "unmet_units"]
# effect -0.26, interval -1.39 to 0.87: the interval covers 0, so the promotion's effect on unmet units is not shown
```

### 1.4 Target (after PR 1): the replicate table

| Field | Label | Kind | Unit | Aggregate |
|---|---|---|---|---|
| `replicate` | Replicate | dimension | | |
| `seed` | Seed | dimension | | |
| `intervention` | Intervention | dimension | | |
| `policy` | Policy | dimension | | |
| `metric` | Metric | dimension | | |
| `value` | Value | measure | | mean |
| `difference` | Difference from baseline | measure | | mean |

`replicate` and `seed` are dimensions, so they hold text (`"0"`, `"42"`), as
every dimension does. The baseline appears here as the arm `baseline`, so a
pivot of `intervention` against `replicate` shows each paired draw.
`difference` is `value` minus the same replicate's baseline value for that
policy and metric, computed by the study: the paired difference the interval
is built from, so the page never subtracts. It is empty on the baseline's own
rows.

### 1.5 Target (after PR 1): HTTP and CLI

```text
POST /api/v1/effects
{
  "interventions": ["promo_spike", "supply_disruption"],       // 1 to 6 names, "baseline" refused
  "policies": [{"kind": "service-level", "service_level": 0.95}],   // PolicyChoice, 1 to 6
  "outcomes": ["simulated_cost"],                               // 1 to 6
  "replicates": 10,                                             // 2 to 20, default 10
  "confidence": 0.95                                            // above 0.5, below 1, default 0.95
}
→ 200
{
  "fields": [...],            // §1.3
  "rows": [[...], ...],
  "replicates": {"fields": [...], "rows": [[...], ...]},       // §1.4
  "spec": {"n_skus": 200, "horizon_days": 90, "seed": 42, ...},  // the spec replicate 0 used
  "synthesizer": "warehouse-spec",
  "elapsed_ms": 3900
}
```

- The study runs on the **current world's spec and generator**, the ones the
  dashboard's world was built from. The handler reads `store.current` once and
  takes all three from that one snapshot: `snapshot.world.spec`,
  `snapshot.world.synthesizer` and `snapshot.world.synthesizers`. They go to
  `EffectStudy(spec=…, synthesizer=…, synthesizers=…, baseline=snapshot.world)`,
  so the held world is replicate 0's baseline and a generator mounted
  at runtime or from a plug-in resolves exactly as it did for the current
  world. The store replaces its snapshot atomically, so
  a concurrent `POST /world` cannot mix two worlds. The
  response echoes them (`spec`, `synthesizer`), since `GET /world` does not
  publish the spec. An effect therefore answers the same question as the
  dashboard's experiment, over replicates.
- **422** for an unknown name, `baseline` among the interventions, a duplicate,
  or a value out of range. **422** when the work is over budget (see next
  bullet), naming the limit and the request's size.
- **The budget** counts both the world generations and the measurements, since
  every arm measures every policy × outcome pair:

  ```text
  work = (replicates × (1 + len(interventions)) + 1) × (1 + MEASURE_WEIGHT × len(policies) × len(outcomes)) × n_skus × horizon_days
  ```

  `work` must not exceed `MAX_EFFECT_WORK`. Spike on the default world:
  - generating a world takes 110 ms;
  - one measurement takes 0 ms (`active_stockouts`), 2 to 3 ms
    (`replenishment_need`) or 11 to 24 ms (`simulated_cost`, the heaviest).

  So `MEASURE_WEIGHT = 0.25` charges each pair at the cost of the heaviest
  measurement. PR 1 re-measures both costs, sets `MEASURE_WEIGHT` and
  `MAX_EFFECT_WORK` so that a request at the limit stays under 30 s whatever
  its mix (6 policies × 6 outcomes of `simulated_cost` included), and tests
  that case.
- **The budget covers the built-in generator; a timing check covers the
  others.** The work formula is calibrated on `warehouse-spec`. A plug-in
  generator can be much slower per world, so the study also times the
  determinism check's generation. It projects the whole
  study as:

  ```text
  projected = time already spent (the check's generations and their measurements)
            + measured seconds per world × (replicates × arms − 1)
            + measured seconds per measurement × the measurements still to run
  ```

  The reference is kept as replicate 0's baseline, so the study generates
  `replicates × arms` worlds in the API (the held world replaces one
  generation, the check adds one) and `replicates × arms + 1` in the CLI. The
  `+ 1` in the work formula above is that upper bound. If the projection exceeds
  `MAX_EFFECT_SECONDS = 30`, the study refuses before generating further
  (422), naming the generator, its measured time per world, and the most
  replicates that would fit, with the check's own cost counted. What this
  guarantees, and what it does not, is set out once for both endpoints in
  §5, "Time limits".
- **Explore links** replay this request. The source shape is added to the
  exploration contract ([`../explore/interfaces.md`](../explore/interfaces.md)
  §3.2) by PR 2: `{ effects: { request: {...}, table: "effects" | "replicates" } }`,
  where `request` is the body above.
- **The server is the only authority on the budget.** The body accepts
  `"check_only": true`. The study then validates the request and computes
  its work, without generating anything, and answers 200:

  ```text
  {"work": 1_458_000, "max_work": …, "within_budget": true,
   "size": "10 replicates × 3 arms × 2 policies × 1 outcome × 200 SKUs × 90 days"}
  ```

  An invalid request gets the same 422 as a real run. The page asks this
  while the user edits the form, and shows the answer. It computes no part of
  the formula itself. `GET /api/v1/experiments/catalog` gains
  `"effects": {"max_replicates": 20}` for the form's input bounds only. The
  timing projection for plug-in generators needs a real generation, so it is
  known only to a real run, which refuses with 422 as above.
- The response models follow the existing rule: declared fields plus
  pass-through.

```text
$ uv run sdf effects --intervention promo_spike --outcome simulated_cost --replicates 10
promo_spike vs baseline, service-level-95, 10 paired replicates, 95 % intervals
metric          baseline    treated     effect   interval
holding_cost    137 600     217 400    +79 790   +72 250 … +87 330
order_cost      240 600     242 000     +1 388      +487 … +2 288
unmet_units        0.596      0.333     −0.263    −1.39 … +0.866   (covers 0)
…
```

Options: `--intervention NAME` (repeatable, required), `--policy
naive|service-level[:LEVEL]` (repeatable, default `service-level:0.95`),
`--outcome NAME` (repeatable, default `simulated_cost`), `--replicates N`,
`--confidence C`, and `--csv PATH` to write the effects table.

---

## 2. One plug-in loader

### 2.1 Current: two copies

`SynthesizerRegistry` (`sdf.synthesis.registry`) and `DatasetCatalog`
(`sdf.application.datasets`) each implement entry-point loading:

- the origin (`builtin`, `plugin`, `runtime`);
- the reserved built-in names;
- idempotent re-loading;
- the unavailable reasons;
- the check that the entry-point name equals `info.name`;
- the check that every constructor argument has a default.

### 2.2 Target (after PR 3): `sdf.foundation.plugins`

```python
from typing import Generic, Literal, TypeVar

Origin = Literal["builtin", "plugin", "runtime"]
T = TypeVar("T")


class PluginRegistry(Generic[T]):
    """Classes with an ``info`` class attribute, by ``info.name``; mounted from one entry-point group."""

    kind: str                  # "synthesizer", "dataset", "estimator": used in every message
    info_type: type            # SynthesizerInfo, DatasetInfo, EstimatorInfo
    group: str                 # "sdf.synthesizers", "sdf.datasets", "sdf.estimators"

    def register(self, cls: type[T], *, replace: bool = False, origin: Origin = "runtime") -> None: ...
    def load_entry_points(self, group: str | None = None) -> list[str]: ...
    def names(self, *, origin: Origin | None = None) -> list[str]: ...
    def info(self, name: str): ...
    def origin(self, name: str) -> Origin: ...
    def unavailable(self) -> dict[str, str]: ...

    def check(self, cls: type[T]) -> None:
        """Kind-specific checks, called by register(); raise TypeError or ValueError. Subclasses override."""
```

`register` runs the shared checks: an `info` of `info_type`, a lower-case
dashed name, constructor defaults, the `requires` modules when `info` has
`requires`, and the duplicate name. It then calls `check`.
`SynthesizerRegistry` and `DatasetCatalog` become subclasses: `check` holds
what is theirs (`produces` and `param_bounds`; `rows(world)`), and `create`,
`params`, `build` and `head` stay where they are. Their public names,
signatures and messages do not change, except that the dataset catalogue's
name-clash message gains the holder, as the synthesizer one already has.

---

## 3. Estimators: the answer from observational rows

### 3.1 Target (after PR 4): `sdf.analytics.causal`

```python
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

from sdf.foundation.tables import Table


@dataclass(frozen=True)
class CausalQuestion:
    treatment: str                         # a field: a dimension, or a measure holding 0 and 1
    outcome: str                           # a measure field
    covariates: tuple[str, ...] = ()       # the adjustment set: the user's claim, not discovered
    treated_value: Any = 1                 # the treatment value that counts as treated; every other value is control


@dataclass(frozen=True)
class EstimatorInfo:
    name: str                              # lower-case words joined by dashes
    description: str
    requires: tuple[str, ...] = ()         # modules; missing ones list the estimator as unavailable
    uses_covariates: bool = True           # False for an estimator that ignores them, e.g. difference-in-means


@dataclass(frozen=True)
class Estimate:
    estimator: str
    effect: float                          # average treatment effect, in the outcome's unit
    ci_low: float | None
    ci_high: float | None
    n_treated: int
    n_control: int
    method: str                            # how the interval was made, e.g. "OLS, HC1 errors, 95 %"


class Estimator(Protocol):
    info: ClassVar[EstimatorInfo]

    def estimate(self, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7) -> Estimate: ...
```

- **Rows the estimate cannot use.** Before calling the estimator, the registry
  drops rows with a missing treatment, outcome or covariate, and refuses:
  - a question naming an unknown field;
  - a treatment that is neither a dimension nor a measure holding only 0 and 1
    (a time field, or a measure with any other value, is refused, naming the
    field and its kind);
  - an outcome that is not a measure, or a covariate that is a time field;
  - a covariate that is the treatment or the outcome itself, or a duplicate
    covariate name. Adjusting for the outcome would leak it into the
    estimate. Whether a covariate is measured before the treatment cannot be
    read from a table, so that stays the user's claim, as the whole
    adjustment set is;
  - a `confidence` outside (0.5, 1), as for `EffectStudy`;
  - a table with fewer than two treated or two control rows;
  - a design that cannot identify the effect. The design matrix X is the
    full matrix the estimator fits: an intercept column, the treatment
    column, and the encoded covariate columns it uses. The design is refused
    when `rank(X) < columns(X)` (collinear) or when
    `kept_rows <= columns(X)` (no residual degree of freedom). It is kept
    exactly when `rank(X) == columns(X)` and `kept_rows > columns(X)`. The
    check uses the columns the estimator uses: for one with
    `info.uses_covariates = False` (`difference-in-means`), only the
    intercept and the treatment, so redundant covariates never refuse the
    naive estimate. `score` runs the check once per estimator on the same
    kept rows. Rank is
    `numpy.linalg.matrix_rank` of that matrix on the kept rows, so a covariate
    that is constant within one group but varies in the other is kept. The
    message names the encoded columns of a dependency, for example
    "log_price equals log_price_copy", or "log_demand is 2 × log_units"
    for any exact linear combination. The first level dropped by the
    encoding is the first level present among the kept rows, so a level
    absent from them never produces a column.

  Every refusal above except the last concerns the question itself, whatever
  the estimator. It is a request problem: `design` raises `ValueError`, and
  the API answers 422. The last, identification, depends on which columns an
  estimator uses, so it is decided per estimator:
  - `EstimatorRegistry.estimate` on one estimator raises `ValueError`;
  - `score`, and therefore the API, record that estimator as an error row
    ("not identified: …", with the columns named) and still run the others.

  With duplicate covariates, `difference-in-means` gives a number while
  `regression-adjustment` gives an error row, in one 200 answer. PR 4 tests
  that mixed case.
- **What can still fail inside an estimator** is data the checks above cannot
  rule out: a covariate that perfectly separates treated from control (no
  overlap, for `ipw`), a computation that divides zero by zero, or a library
  error. The rule is one test on the result, applied the same way to every
  estimator:
  - an estimator that raises is handled as `score` handles it, as an error row;
  - an `Estimate` whose effect or interval bound is not a finite number (NaN,
    infinite) is replaced by an error row naming the estimator and the value;
  - every finite result stays.

  So a constant outcome is not an error in itself. When treated and control
  share one constant value, the effect is 0 with a finite zero-width interval,
  and that row stays. If an estimator's own formula divides 0 by 0 on such
  data, the NaN it returns becomes an error row. No table ever holds an
  infinite or undefined estimate, and the tests cover both cases.
- **Covariates.** Dimension covariates are one-hot encoded, dropping the first
  level. Measure covariates are used as they are.
- **Seeds.** `seed` is used only by estimators that resample (the `ipw`
  bootstrap), so every estimate is repeatable.

A minimal plug-in:

```python
import numpy as np
from typing import ClassVar

from sdf.analytics.causal import CausalQuestion, Estimate, EstimatorInfo, design


class MedianDifference:
    info: ClassVar[EstimatorInfo] = EstimatorInfo("median-difference", "Difference of the groups' medians, no interval")

    def estimate(self, table, question: CausalQuestion, *, confidence=0.95, seed=7) -> Estimate:
        d = design(table, question)          # arrays: d.treated (bool), d.outcome, d.covariates (2-D)
        effect = float(np.median(d.outcome[d.treated]) - np.median(d.outcome[~d.treated]))
        return Estimate(self.info.name, effect, None, None, int(d.treated.sum()), int((~d.treated).sum()), "medians")
```

`design` is the shared preparation (the missing-value rule, the refusals and
the encoding above), so no estimator re-implements it:

```python
import numpy as np


@dataclass(frozen=True)
class Design:
    treated: np.ndarray            # bool, one per kept row
    outcome: np.ndarray            # float, one per kept row
    covariates: np.ndarray         # float, 2-D: kept rows × encoded columns (0 columns without covariates)
    columns: tuple[str, ...]       # the encoded columns' names, e.g. ("log_demand", "abc_class=B", "abc_class=C")
    dropped: int                   # rows left out for a missing value


def design(table: Table, question: CausalQuestion) -> Design:
    """Raises ValueError for every refusal listed above, naming the field or covariate."""
```

### 3.2 Target (after PR 4): the built-ins and the `causal` extra

| Name | Method | Interval | Needs |
|---|---|---|---|
| `difference-in-means` | treated mean − control mean; ignores the covariates | Welch t | core |
| `regression-adjustment` | least squares of the outcome on the treatment and the covariates; the treatment coefficient | HC1 robust errors, t | core |
| `ipw` | Hajek inverse propensity weighting; logistic propensity on the covariates, clipped to 0.01 to 0.99 after an overlap check (below) | 200 bootstrap resamples with `seed`, percentile | core (scikit-learn) |
| `dowhy-backdoor` | DoWhy, back-door criterion over the declared covariates, linear regression | DoWhy's interval | `dowhy` (`causal` extra, Python 3.13) |
| `econml-dml` | EconML `LinearDML` with the covariates as controls | EconML's interval | `econml` (`causal` extra) |

The five are declared in the `sdf.estimators` group of `pyproject.toml`.

**`ipw`'s overlap check comes before clipping.** Clipping keeps the weights
finite, but on its own it would turn a design with no overlap into a plausible
number. So `ipw` first counts the rows whose fitted, unclipped propensity lies
outside [0.01, 0.99]:
- **More than 10 % of the rows:** there is too little overlap to weight
  across. `ipw` raises, and the registry records an error row: "no overlap: N
  of M rows have a propensity outside [0.01, 0.99]". Perfect separation always
  lands here.
- **10 % or fewer:** those rows are clipped, and `method` reports how many
  ("… , 12 rows clipped"), so the reader sees it.

The registry is a `PluginRegistry` (§2.2) with `kind = "estimator"`,
`info_type = EstimatorInfo` and `group = "sdf.estimators"`, plus one method:

```python
class EstimatorRegistry(PluginRegistry[Estimator]):
    def estimate(self, name: str, table: Table, question: CausalQuestion, *,
                 confidence: float = 0.95, seed: int = 7) -> Estimate:
        """Check the question against the table, then run ``name`` on it.

        Raises KeyError for an unknown or unavailable estimator, ValueError for a
        question the table cannot answer or a confidence outside (0.5, 1)
        (§3.1), and lets the estimator's own
        exception through (``score`` turns that into a row).
        """


def default_estimators() -> EstimatorRegistry:
    """A registry with the ``sdf.estimators`` group mounted, like default_registry()."""
```

`check` (the kind-specific hook of §2.2) refuses a class without a callable
`estimate`. An estimator is created with no argument, so, as for datasets,
every constructor argument needs a default.

```python
from sdf.analytics.causal import default_estimators

reg = default_estimators()
reg.names()          # ['difference-in-means', 'ipw', 'regression-adjustment', ...]
reg.unavailable()    # {'dowhy-backdoor': 'needs dowhy', 'econml-dml': 'needs econml'} without the extra
est = reg.estimate("regression-adjustment", table, CausalQuestion("promoted", "weekly_units", ("log_demand", "abc_class", "log_price")))
```

### 3.3 Target (after PR 4): the promotion benchmark (`sdf.simulation.benchmark`)

```python
@dataclass(frozen=True)
class PromotionBenchmark:
    """The world's SKUs as units, with a declared promotion mechanism on top, so the true effect is known."""

    uplift: float = 0.3          # promoted weekly units = (1 + uplift) × unpromoted; -0.9 to 3
    confounding: float = 1.0     # how strongly high-demand SKUs are promoted; 0 (random) to 3
    noise: float = 0.25          # lognormal sigma of weekly units; 0 to 1
    seed: int = 7

    # The bounds, declared once, in the shape synthesizers use (§4.1 of the exploration contract).
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {
        "uplift": (-0.9, 3.0),
        "confounding": (0.0, 3.0),
        "noise": (0.0, 1.0),
    }

    @classmethod
    def params(cls) -> tuple[Param, ...]:
        """The four fields as Params: synthesizer_params(cls), the reader the synthesizer registry uses."""

    def __post_init__(self) -> None:
        """Run each value through its Param's check(), raising ValueError that names the field."""

    def draw(self, world: World) -> "BenchmarkDraw": ...


@dataclass(frozen=True)
class BenchmarkDraw:
    table: Table                 # dataset "promotion-benchmark": what an analyst would observe (below)
    question: CausalQuestion     # promoted → weekly_units, adjusting for log_demand, abc_class, log_price
    true_effect: float           # the mean over SKUs of y(1) − y(0): exact, because both are generated
```

`params()` is the single source of the bounds:
- `__post_init__` checks against it;
- `GET /estimators` publishes it as `benchmark.params`
  (`[p.to_dict() for p in PromotionBenchmark.params()]`);
- the API's `Param.check` and the page's `readParam` apply it.

So a direct Python caller, the API and the form refuse exactly the same
values. `Param` and `synthesizer_params` come from `sdf.synthesis`, a lower
layer than `sdf.simulation`.

- **Units.** SKUs with demand in the world.
- **Observed fields**, in this order:

  | Field | Label | Kind | Unit | Aggregate |
  |---|---|---|---|---|
  | `sku_id` | SKU | dimension | | |
  | `abc_class` | ABC class | dimension | | |
  | `log_demand` | Log mean daily demand | measure | | mean |
  | `log_price` | Log (1 + unit price) | measure | | mean |
  | `promoted` | Promoted | measure (0 or 1) | | mean |
  | `weekly_units` | Weekly units | measure | units | mean |

  `promoted` is a 0/1 measure, not a dimension. That makes it a valid
  treatment (§3.1), and its mean in a pivot is the promoted share.
  - `log_demand` is `log(mean daily demand)`, always finite because the units
    are the SKUs with demand.
  - `log_price` is `log(1 + unit price)`, so a SKU with a unit price of 0
    (valid in the schema) gives 0 instead of an infinite value.
- **The mechanism.** The standardised log demand is z. The probability of
  promotion is `1 / (1 + exp(0.5 − confounding × z))`.
  - Unpromoted units are `y(0) = 7 × mean daily demand × e`, with `e` lognormal
    (0, noise).
  - Promoted units are `y(1) = (1 + uplift) × y(0)`.
  - The table shows `y(promoted)` only.

```python
def score(
    table: Table,
    question: CausalQuestion,
    registry: EstimatorRegistry,
    *,
    names: Sequence[str],
    true_effect: float | None = None,
    confidence: float = 0.95,
    seed: int = 7,
) -> Table:
    """Run every estimator in ``names`` on the same rows; one row each, in ``names`` order.

    Raises ValueError, as ``design`` does, when the question cannot be answered
    at all (that is a request problem), and KeyError for an unknown name. An
    estimator that raises, or returns a non-finite value, becomes an error row.
    """
```

```python
from sdf.analytics.causal import score

draw = PromotionBenchmark(confounding=1.0).draw(world)
scores = score(draw.table, draw.question, reg,
               names=["difference-in-means", "regression-adjustment", "ipw"], true_effect=draw.true_effect)
# spike means over 50 draws, confounding 1: truth 7.2; difference-in-means 38.1, regression-adjustment 7.7, ipw 8.1
```

The `estimator-scores` table, one row per estimator in `names` order, with
these fields in this order:

| Field | Label | Kind | Unit | Aggregate |
|---|---|---|---|---|
| `estimator` | Estimator | dimension | | |
| `effect` | Estimated effect | measure | the outcome's unit | mean |
| `ci_low` | Interval low | measure | the outcome's unit | mean |
| `ci_high` | Interval high | measure | the outcome's unit | mean |
| `true_effect` | True effect | measure | the outcome's unit | mean |
| `bias` | Bias | measure | the outcome's unit | mean |
| `relative_bias` | Relative bias | measure | share | mean |
| `covers` | Interval covers the truth | dimension | | |
| `n_treated` | Treated rows | measure | rows | sum |
| `n_control` | Control rows | measure | rows | sum |
| `seconds` | Run time | measure | s | sum |
| `method` | Method | dimension | | |

Notes:
- **Units.** "The outcome's unit" is the outcome field's own `unit` (`units`
  for the benchmark; none when the field has none).
- **`covers`** is `"yes"`, `"no"`, or empty without a truth.
- **Error rows.** An error row keeps `estimator` and `method` (the error) and
  leaves every other field empty. `seconds` is the only exception: it is
  filled when the estimator ran and empty when it was not run.
- **`n_treated` and `n_control`** come from the `Estimate`.
- **`bias`** is `effect − true_effect`, and **`relative_bias`** is
  `bias / true_effect`. Both are empty without a truth, and `relative_bias`
  is also empty for a zero truth.

- **`score` lives in the analytics layer.** It therefore takes the table, the
  question and the truth, never a `BenchmarkDraw` from the simulation layer
  above it.
- **Every estimator runs on the same rows.**
- **A failing estimator.** It is recorded as a row with the error in `method`
  and empty numbers, so one broken plug-in does not hide the others.
- **Without a truth** (`true_effect=None`), `true_effect`, `bias`,
  `relative_bias` and `covers` are empty.
- **With a zero truth** (`uplift=0`, which the benchmark allows), `bias` and
  `covers` are filled and `relative_bias` is empty: a bias relative to 0 is not
  defined. The tests cover it.

### 3.4 Target (after PR 4): HTTP and CLI

```text
GET /api/v1/estimators
→ {
    "estimators": [{"name", "description", "origin", "requires"}],
    "unavailable": {"name": "reason"},
    "limits": {"max_rows": …, "max_estimators": 6, "max_seconds": 30},   // MAX_ESTIMATE_ROWS, the estimator cap and the time budget (below, §5)
    "benchmark": {
      "params": [Param, ...],        // uplift, confounding, noise, seed: the synthesizer Param shape (name, type, default, min, max, exclusive, nullable)
      "question": {...}              // the benchmark's CausalQuestion: treatment, outcome, the covariates a client may drop
    }
  }

POST /api/v1/causal/estimates
{
  "estimators": ["difference-in-means", "regression-adjustment", "ipw"],   // 1 to 6
  "benchmark": {"uplift": 0.3, "confounding": 1.0, "noise": 0.25, "seed": 7},
  "confidence": 0.95
}
→ 200 {"fields": [...], "rows": [[...]], "question": {...}, "true_effect": 7.2,
       "data": {"fields": [...], "rows": [[...]]}}     // the benchmark's observed table, for Explore

POST /api/v1/causal/estimates
{
  "estimators": ["regression-adjustment"],
  "dataset": "order-lines",                                            // any catalogue dataset instead of the benchmark
  "question": {"treatment": "priority", "treated_value": "express", "outcome": "line_value", "covariates": ["category"]}
}
→ 200 {"fields": [...], "rows": [[...]], "question": {...}, "true_effect": null}   // no truth: bias and covers are null
```

- **422** for an unknown estimator, dataset or field, an invalid question (the
  refusals of §3.1), a `confidence` outside (0.5, 1), neither or both of
  `benchmark` and `dataset`, or a benchmark value outside
  the bounds `GET /estimators` publishes. The server checks each value with the
  same `Param.check` the synthesizer runs use, so the form and the server agree.
- **One world per request.** The handler reads `store.current` once, at the
  start, and uses that snapshot's world for the whole request. The benchmark
  draw, the catalogue dataset's rows, and the response's metadata all come
  from it, as for `POST /effects` (§1.5). A concurrent `POST /world` replaces
  the store's snapshot, not the one this request holds.
- **Limits.** Estimation runs synchronously, so its size is bounded like an
  effect study's:
  - at most `MAX_ESTIMATE_ROWS` rows. A catalogue dataset is read through a
    bounded stream: the handler takes rows from the provider's `rows(world)`
    iterator and stops at `MAX_ESTIMATE_ROWS + 1`, without reading or counting
    the rest. The `+ 1` is only there to detect overflow. A dataset that
    reaches it answers 422: "more than MAX_ESTIMATE_ROWS rows". The cap
    bounds memory: that many rows are held, the same rows
    `GET /datasets/{name}?limit=` already reads. It does not bound time. A
    provider can be slow per row, so the stream also checks the request's
    deadline between rows (§5), and the missing-value rule applies to the
    rows it keeps;
  - at most 6 estimators per request.

  `ipw`'s 200 bootstrap fits dominate. On the largest built-in dataset
  (`order-lines`, 28 897 rows on the default world), PR 4 measures the
  slowest built-in and sets `MAX_ESTIMATE_ROWS` so that six estimators at the
  cap finish under 30 s. The limits are published in `GET /estimators` as
  `"limits": {"max_rows": …, "max_estimators": 6, "max_seconds": 30}`. The page
  shows them and bounds its estimator list to `max_estimators`. The server's
  422 stays the authority: the row count is only known once the server reads
  the dataset.
- **The 30 s bound (§5) is guaranteed for the built-ins, and enforced between
  estimators for plug-ins.** An estimator runs in the request's own thread,
  and Python cannot interrupt it safely, so:
  - The estimators run one after another. Before starting each one, the
    handler compares the time already spent with `MAX_ESTIMATE_SECONDS = 30`.
    Once the budget is spent, each estimator not yet started becomes an error
    row: "not run: the request's 30 s were used".
  - A single plug-in that runs far longer still delays its own request. The
    plug-in guide (PR 5) states the expectation: an estimator finishes in a
    few seconds at `max_rows`. The page lists the time each estimator took,
    so a slow plug-in is visible.

  The measured guarantee covers the built-ins. For plug-ins it is a bound on
  how many start, not on how long one runs, and the contract says so rather
  than claiming more.
- **Explore links** replay this request, through the source shape PR 5 adds to
  the exploration contract (§3.2): `{ estimates: { request: {...}, table:
  "scores" | "data" } }`, where `request` is the body above. `table: "data"`
  is valid only when `request` holds a `benchmark`, since only that response
  carries the observed rows. With a `dataset`, the rows are the catalogue
  dataset itself, which Explore opens as `{ dataset: name }`. The validator
  refuses `"data"` with a `dataset` request, with that message.
- With `benchmark`, `question` is optional. When it is given, it may only drop
  covariates from the benchmark's own question, so a user can watch the bias
  return.
- **An estimator that raises** does not fail the request. The endpoint answers
  with the `score` table, and that estimator's row carries the error in
  `method` with empty numbers, as in §3.3, so the other estimators' results
  still arrive.
- **500** only when the rows cannot be built: the benchmark draw or the
  catalogue dataset fails, with the message naming which.

```text
$ uv run sdf estimate --confounding 1 --estimator difference-in-means --estimator regression-adjustment --estimator ipw
promotion benchmark: 200 SKUs, uplift 30 %, confounding 1, seed 7; true effect +7.2 units/week
estimator               effect   95 % interval     bias     covers
difference-in-means     +38.1    …                 +30.9    no
regression-adjustment    +7.7    …                  +0.5    yes
ipw                      +8.1    …                  +0.9    yes
```

---

## 4. What the algorithm phase uses

- A real estimator (double machine learning with gradient boosting, a causal
  forest, a Bayesian model) is an `sdf.estimators` plug-in. It is scored by the
  same benchmark and shown by the same page, with no UI change.
- A real simulator of the warehouse (the `ALGORITHM-HOOK[A4]` digital twin)
  plugs in as the world generator, and `EffectStudy` gives its effects with
  intervals unchanged.

---

## 5. Time limits

Both new endpoints run synchronously, so each has one deadline:
`MAX_EFFECT_SECONDS = 30` for an effect study and `MAX_ESTIMATE_SECONDS = 30`
for an estimation, from the start of the request. Python cannot safely
interrupt a call already running in the request's thread. So the deadline is
**cooperative**: it is checked at every step boundary, and never inside a
call.

| Endpoint | Where the deadline is checked | Past it |
|---|---|---|
| `POST /effects` | before each world generation and each measurement | 422 naming the step reached and the replicates done |
| `POST /causal/estimates` | between rows of a catalogue dataset, and before each estimator | reading rows: 422 "dataset X did not deliver its rows within 30 s"; estimators: the ones not started become "not run" rows |

On top of that sit the up-front refusals of §1.5 and §3.4 (the work formula,
the timing projection, the row and estimator caps). They refuse a request
that would clearly overrun before any work starts.

What is guaranteed:

- **Built-in code only.** The warehouse generator `warehouse-spec`, the
  built-in datasets, the benchmark and the built-in estimators are measured
  by PR 1 and PR 4. A request that passes the up-front checks finishes within
  its deadline plus one step, and the tests assert it.
- **Plug-in code is best effort.** A plug-in generator, dataset provider or
  estimator is stopped at the next step boundary after the deadline. One call
  that runs long, or runs longer on another seed or scenario than on the one
  timed, still delays its own request by that call's length.

  The published limits (`GET /experiments/catalog` under `effects`, and
  `GET /estimators` under `limits`) say which guarantee applies. The plug-in
  guide asks a plug-in to keep each call to a few seconds at the published
  sizes.

Making plug-in calls killable needs a worker process per call. That changes
how plug-ins run and what they may share, and is left to a later sequence if
it is ever needed.
