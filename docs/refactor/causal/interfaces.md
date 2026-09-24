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
- **The interval** is Student's t on the paired differences, with R − 1
  degrees of freedom (`scipy.stats.t`). When every difference is equal, the
  interval collapses to the point (zero width), which is correct for a metric
  the intervention does not move.
- **The relative effect** is `effect / baseline mean`, or `None` when the
  baseline mean is 0.
- The study never touches the API's current world. It generates its own worlds
  from `spec`, with the given generator.
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

`replicate` and `seed` are dimensions, so they hold text (`"0"`, `"42"`), as
every dimension does. The baseline appears here as the arm `baseline`, so a
pivot of `intervention` against `replicate` shows each paired draw.

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

- The study runs on the **current world's spec and generator** (`GET /world`),
  so an effect answers the same question as the dashboard's experiment, over
  replicates.
- **422** for an unknown name, `baseline` among the interventions, a duplicate,
  or a value out of range. **422** when the work is over budget (see next
  bullet), naming the limit and the request's size.
- **The budget** counts both the world generations and the measurements, since
  every arm measures every policy × outcome pair:

  ```text
  work = replicates × (1 + len(interventions)) × (1 + MEASURE_WEIGHT × len(policies) × len(outcomes)) × n_skus × horizon_days
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
- **The limits are published.** `GET /api/v1/experiments/catalog` gains
  `"effects": {"max_replicates": 20, "measure_weight": 0.25, "max_work": …}`,
  so a client checks a request with the server's own numbers.
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
  - a `confidence` outside (0.5, 1), as for `EffectStudy`;
  - a table with fewer than two treated or two control rows.

  So an estimator never sees an interval level that would give a non-finite
  interval or fail inside a library.
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

`design(table, question) -> Design` is the shared preparation (the missing-value
rule and the encoding above), so no estimator re-implements it.

### 3.2 Target (after PR 4): the built-ins and the `causal` extra

| Name | Method | Interval | Needs |
|---|---|---|---|
| `difference-in-means` | treated mean − control mean; ignores the covariates | Welch t | core |
| `regression-adjustment` | least squares of the outcome on the treatment and the covariates; the treatment coefficient | HC1 robust errors, t | core |
| `ipw` | Hajek inverse propensity weighting; logistic propensity on the covariates, clipped to 0.01 to 0.99 | 200 bootstrap resamples with `seed`, percentile | core (scikit-learn) |
| `dowhy-backdoor` | DoWhy, back-door criterion over the declared covariates, linear regression | DoWhy's interval | `dowhy` (`causal` extra, Python 3.13) |
| `econml-dml` | EconML `LinearDML` with the covariates as controls | EconML's interval | `econml` (`causal` extra) |

The five are declared in the `sdf.estimators` group of `pyproject.toml`.

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

    def draw(self, world: World) -> "BenchmarkDraw": ...


@dataclass(frozen=True)
class BenchmarkDraw:
    table: Table                 # dataset "promotion-benchmark": what an analyst would observe (below)
    question: CausalQuestion     # promoted → weekly_units, adjusting for log_demand, abc_class, log_price
    true_effect: float           # the mean over SKUs of y(1) − y(0): exact, because both are generated
```

- **Units.** SKUs with demand in the world.
- **Observed fields.** `sku_id`, `abc_class` (dimension), `log_demand`,
  `log_price`, `promoted` (0 or 1), `weekly_units` (measures).
- **The mechanism.** The standardised log demand is z. The probability of
  promotion is `1 / (1 + exp(0.5 − confounding × z))`.
  - Unpromoted units are `y(0) = 7 × mean daily demand × e`, with `e` lognormal
    (0, noise).
  - Promoted units are `y(1) = (1 + uplift) × y(0)`.
  - The table shows `y(promoted)` only.

```python
from sdf.analytics.causal import score

draw = PromotionBenchmark(confounding=1.0).draw(world)
scores = score(draw.table, draw.question, reg,
               names=["difference-in-means", "regression-adjustment", "ipw"], true_effect=draw.true_effect)
# dataset "estimator-scores":
#   estimator (dimension), effect, ci_low, ci_high, true_effect, bias, relative_bias (measures),
#   covers ("yes", "no", or empty without a truth), method (dimension)
# spike means over 50 draws, confounding 1: truth 7.2; difference-in-means 38.1, regression-adjustment 7.7, ipw 8.1
```

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
