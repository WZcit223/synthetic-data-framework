"""Effects of interventions against the baseline, over paired replicate worlds.

An effect study answers "what happens if we take this action" with the
simulator itself: each intervention and the baseline run on R replicate
worlds, every arm of one replicate generated from that replicate's seed, and
the effect is the mean of the R paired differences with a Student-t interval.
The contract is ``docs/refactor/causal/interfaces.md`` §1 and §5.
"""

from __future__ import annotations

import dataclasses
import math
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from scipy import stats

from sdf.foundation.tables import DatasetInfo, Field, Table
from sdf.synthesis.materialise import DEFAULT_WAREHOUSE_SYNTHESIZER
from sdf.synthesis.registry import SynthesizerRegistry, default_registry
from sdf.synthesis.spec import GenerationSpec
from .intervention import Baseline, Intervention, SpecIntervention
from .outcome import Outcome
from .policy import Policy
from .world import World

MAX_REPLICATES = 20
MAX_EFFECT_SECONDS = 30.0
# One policy × outcome measurement, in units of one world generation: measured on the default
# world (generation ~110 ms, simulated_cost under a service-level policy ~24 ms, the heaviest).
MEASURE_WEIGHT = 0.25
# The largest work (formula in effect_work) a request may ask for. Measured: 3 to 14 µs per unit,
# the slowest for the largest world the API allows (500 SKUs × 180 days), where generation
# dominates. 1.2 M units is about 17 s at that pace, leaving room for a slower machine within 30 s.
MAX_EFFECT_WORK = 1_200_000

EFFECTS_INFO = DatasetInfo(
    name="effects",
    label="Effects",
    description="Each intervention against the baseline: mean paired difference with its interval",
    fields=(
        Field("intervention", "Intervention", "dimension"),
        Field("policy", "Policy", "dimension"),
        Field("metric", "Metric", "dimension"),
        Field("baseline", "Baseline mean", "measure", aggregate="mean"),
        Field("treated", "Treated mean", "measure", aggregate="mean"),
        Field("effect", "Effect", "measure", aggregate="mean"),
        Field("ci_low", "Interval low", "measure", aggregate="mean"),
        Field("ci_high", "Interval high", "measure", aggregate="mean"),
        Field("relative_effect", "Relative effect", "measure", unit="share", aggregate="mean"),
        Field("replicates", "Replicates", "measure", aggregate="min"),
        Field("method", "Method", "dimension"),
    ),
)

REPLICATES_INFO = DatasetInfo(
    name="effect-replicates",
    label="Effect replicates",
    description="Every replicate's measured value per arm, with its paired difference from the baseline",
    fields=(
        Field("replicate", "Replicate", "dimension"),
        Field("seed", "Seed", "dimension"),
        Field("intervention", "Intervention", "dimension"),
        Field("policy", "Policy", "dimension"),
        Field("metric", "Metric", "dimension"),
        Field("value", "Value", "measure", aggregate="mean"),
        Field("difference", "Difference from baseline", "measure", aggregate="mean"),
    ),
)

Snapshot = tuple[tuple[str, str, tuple[tuple[Any, ...], ...]], ...]
Values = dict[tuple[str, str], float]  # (policy, metric) -> value


def effect_work(
    replicates: int, interventions: int, policies: int, outcomes: int, n_skus: int, horizon_days: int
) -> int:
    """The work of a study: generations (plus one for the check) weighted by the measurements each arm runs."""
    arms = 1 + interventions
    return round((replicates * arms + 1) * (1 + MEASURE_WEIGHT * policies * outcomes) * n_skus * horizon_days)


def size_text(replicates: int, interventions: int, policies: int, outcomes: int, spec: GenerationSpec) -> str:
    """The request's size in words, as the budget answer shows it."""

    def n(k: int, one: str, many: str) -> str:
        return f"{k} {one if k == 1 else many}"

    return " × ".join(
        (
            n(replicates, "replicate", "replicates"),
            n(1 + interventions, "arm", "arms"),
            n(policies, "policy", "policies"),
            n(outcomes, "outcome", "outcomes"),
            f"{spec.n_skus} SKUs",
            f"{spec.horizon_days} days",
        )
    )


@dataclass(frozen=True)
class EffectResult:
    effects: Table  # dataset "effects", one row per intervention × policy × metric
    replicates: Table  # dataset "effect-replicates", one row per replicate × arm × policy × metric


@dataclass(frozen=True)
class EffectStudy:
    """Each intervention against the baseline, on ``replicates`` paired worlds."""

    spec: GenerationSpec
    interventions: Sequence[Intervention]  # compared with Baseline(); "baseline" itself is refused here
    policies: Sequence[Policy]
    outcomes: Sequence[Outcome]
    replicates: int = 10  # 2 to MAX_REPLICATES
    confidence: float = 0.95  # of the interval; above 0.5, below 1
    synthesizer: str = DEFAULT_WAREHOUSE_SYNTHESIZER
    synthesizers: SynthesizerRegistry | None = None
    baseline: World | None = None  # replicate 0's baseline, when the caller already holds it (the API's world)

    def __post_init__(self) -> None:
        """Refuse a study that cannot run; every message names the field."""
        if isinstance(self.replicates, bool) or not isinstance(self.replicates, int):
            raise ValueError(f"replicates must be a whole number, got {self.replicates!r}")
        if not 2 <= self.replicates <= MAX_REPLICATES:
            raise ValueError(f"replicates must be from 2 to {MAX_REPLICATES}, got {self.replicates}")
        if not (math.isfinite(self.confidence) and 0.5 < self.confidence < 1):
            raise ValueError(f"confidence must be above 0.5 and below 1, got {self.confidence!r}")
        for name in ("interventions", "policies", "outcomes"):
            if not getattr(self, name):
                raise ValueError(f"{name} must name at least one")
        names = [i.name for i in self.interventions]
        if "baseline" in names:
            raise ValueError("interventions: baseline is what every intervention is compared with; leave it out")
        for label, values in (
            ("interventions", names),
            ("policies", [p.name for p in self.policies]),
            ("outcomes", [o.name for o in self.outcomes]),
        ):
            duplicates = sorted({v for v in values if values.count(v) > 1})
            if duplicates:
                raise ValueError(f"{label}: each may appear once, repeated {duplicates}")

    def work(self) -> int:
        return effect_work(
            self.replicates,
            len(self.interventions),
            len(self.policies),
            len(self.outcomes),
            self.spec.n_skus,
            self.spec.horizon_days,
        )

    def size(self) -> str:
        return size_text(self.replicates, len(self.interventions), len(self.policies), len(self.outcomes), self.spec)

    def method(self) -> str:
        return f"paired t, {self.confidence * 100:g} %"

    def run(self) -> EffectResult:
        """Run the study; ``ValueError`` for a request over budget or time, or a generator or intervention that breaks pairing."""
        if self.work() > MAX_EFFECT_WORK:
            raise ValueError(
                f"the study is over its budget: work {self.work():,} exceeds MAX_EFFECT_WORK {MAX_EFFECT_WORK:,}"
                f" ({self.size()}); lower the replicates or the lists"
            )
        return _Run(self).run()


class _Run:
    """One execution of a study, with its deadline and step accounting."""

    def __init__(self, study: EffectStudy) -> None:
        self.study = study
        self.reg = study.synthesizers if study.synthesizers is not None else default_registry()
        self.start = time.monotonic()
        self.deadline = self.start + MAX_EFFECT_SECONDS
        self.replicates_done = 0
        self.arms = [Baseline(), *study.interventions]

    # -- steps ------------------------------------------------------------------------------------

    def _step(self, what: str) -> None:
        """The cooperative deadline (§5): checked before every generation and measurement."""
        if time.monotonic() > self.deadline:
            raise ValueError(
                f"the study passed its {MAX_EFFECT_SECONDS:g} s limit at {what}, after"
                f" {self.replicates_done} of {self.study.replicates} replicates"
            )

    def _generate(self, seed: int) -> World:
        self._step(f"generating the world for seed {seed}")
        return World.generate(
            replace(self.study.spec, seed=seed), synthesizer=self.study.synthesizer, synthesizers=self.reg
        )

    def _apply(self, intervention: Intervention, world: World, replicate: int) -> World:
        if type(intervention) is Baseline:
            return world
        self._step(f"applying {intervention.name} in replicate {replicate}")
        if _built_in(intervention):
            return intervention.apply(world)  # only builds a new world
        before = snapshot(world)  # a custom intervention: its input must come out unchanged, every time
        out = intervention.apply(world)
        if snapshot(world) != before:
            raise ValueError(f"intervention {intervention.name} modified its input world")
        return out

    def _measure(self, world: World, arm: str, replicate: int) -> Values:
        values: Values = {}
        source: dict[tuple[str, str], str] = {}  # (policy, metric) -> the outcome that reported it
        for policy in self.study.policies:
            for outcome in self.study.outcomes:
                self._step(f"measuring {outcome.name} under {policy.name} for {arm} in replicate {replicate}")
                for metric, value in outcome.measure(world, policy).items():
                    key = (policy.name, metric)
                    if key in source:
                        raise ValueError(
                            f"outcomes {source[key]} and {outcome.name} both report metric {metric};"
                            " each metric may come from one outcome"
                        )
                    source[key] = outcome.name
                    values[key] = value
        return values

    # -- the study --------------------------------------------------------------------------------

    def run(self) -> EffectResult:
        study = self.study
        seed0 = study.spec.seed
        # Replicate 0's baseline is the held world when there is one, else one generation of its spec.
        timed = time.monotonic()
        reference = study.baseline if study.baseline is not None else self._generate(seed0)
        reference_seconds = time.monotonic() - timed if study.baseline is None else None
        reference_snapshot = snapshot(reference)

        timed = time.monotonic()
        check = self._generate(seed0)
        world_seconds = time.monotonic() - timed
        if reference_seconds is not None:
            world_seconds = (world_seconds + reference_seconds) / 2
        if snapshot(reference) != reference_snapshot:  # the second call changed the first world's rows
            raise ValueError("the generator modified an earlier world; regenerate the world")
        check_snapshot = snapshot(check)

        # Paced on the fresh check world: the held world may already have its demand cached.
        timed = time.monotonic()
        check_values = self._measure(check, "baseline", 0)
        measure_seconds = (time.monotonic() - timed) / (len(study.policies) * len(study.outcomes))
        reference_values = self._measure(reference, "baseline", 0)
        if check_snapshot != reference_snapshot or not _same(check_values, reference_values):
            raise ValueError(
                f"generator {study.synthesizer} is not deterministic in its spec; paired effects need the same"
                " world for the same seed"
            )
        del check, check_snapshot

        self._project(world_seconds, measure_seconds)

        # Every world is measured as soon as it exists and never read again, except a replicate's
        # base, which custom interventions read: with any of those, the base is snapshot and rechecked.
        custom = any(not _built_in(i) for i in study.interventions)
        per_replicate: list[dict[str, Values]] = []
        for r in range(study.replicates):
            seed = seed0 + r
            base = reference if r == 0 else self._generate(seed)
            base_snapshot = (reference_snapshot if r == 0 else snapshot(base)) if custom else None
            measured: dict[str, Values] = {
                "baseline": reference_values if r == 0 else self._measure(base, "baseline", r)
            }
            for intervention in study.interventions:
                if _built_in(intervention):
                    world = self._apply(intervention, base, r)
                else:
                    world = self._apply_custom(intervention, base, base_snapshot, r)
                measured[intervention.name] = self._measure(world, intervention.name, r)
            per_replicate.append(measured)
            self.replicates_done = r + 1

        if snapshot(reference) != reference_snapshot:
            raise ValueError("the generator modified an earlier world; regenerate the world")
        return _tables(study, per_replicate)

    def _project(self, world_seconds: float, measure_seconds: float) -> None:
        """Refuse up front when the measured pace says the study cannot finish in time (§1.5)."""
        study = self.study
        arms = len(self.arms)
        pairs = len(study.policies) * len(study.outcomes)
        custom = sum(1 for i in study.interventions if not _built_in(i))
        spent = time.monotonic() - self.start
        per_arm = world_seconds + pairs * measure_seconds
        # Replicate 0's baseline is measured; its other arms, then R - 1 full replicates, remain,
        # plus the second application of each custom intervention in every replicate (its check).
        remaining = (
            (arms - 1) * per_arm + (study.replicates - 1) * arms * per_arm + custom * study.replicates * world_seconds
        )
        if spent + remaining <= MAX_EFFECT_SECONDS:
            return
        # The largest R whose projection fits: R - 1 full replicates, each with its custom re-applications.
        per_replicate = arms * per_arm + custom * world_seconds
        first = (arms - 1) * per_arm + custom * world_seconds
        fits = 1 + math.floor((MAX_EFFECT_SECONDS - spent - first) / per_replicate)
        advice = (
            f"at most {fits} replicates would fit"
            if fits >= 2
            else "not even 2 replicates would fit; shorten the lists or the world"
        )
        raise ValueError(
            f"the study would take about {spent + remaining:.0f} s, over its {MAX_EFFECT_SECONDS:g} s limit:"
            f" generator {study.synthesizer} takes {world_seconds:.2f} s per world; {advice}"
        )

    def _apply_custom(self, intervention: Intervention, base: World, base_snapshot: Snapshot, replicate: int) -> World:
        """Apply a custom intervention twice to an unchanged base: the same world, the input left alone."""
        if snapshot(base) != base_snapshot:
            raise ValueError("the generator modified an earlier world; regenerate the world")
        once = self._apply(intervention, base, replicate)  # _apply refuses one that changes its input
        once_snapshot = snapshot(once)
        twice = self._apply(intervention, base, replicate)
        if snapshot(twice) != once_snapshot:
            raise ValueError(
                f"intervention {intervention.name} is not deterministic; paired effects need the same world"
                " from the same input"
            )
        return once


def _built_in(intervention: Intervention) -> bool:
    """Built-in interventions only build new worlds from the spec, so the generator check covers them.

    The exact types only: a subclass may override ``apply`` and is checked as a custom intervention.
    """
    return type(intervention) in (Baseline, SpecIntervention)


def snapshot(world: World) -> Snapshot:
    """Every source's name, entity type and rows, copied (``dataclasses.astuple``) so later mutation cannot hide."""
    return tuple(
        (src.name, src.entity_type, tuple(dataclasses.astuple(row) for row in src.rows()))
        for src in world.registry.sources()
    )


def _same(a: Values, b: Values) -> bool:
    return a.keys() == b.keys() and all(a[k] == b[k] or (_nan(a[k]) and _nan(b[k])) for k in a)


def _nan(x: float) -> bool:
    return isinstance(x, float) and math.isnan(x)


def _tables(study: EffectStudy, per_replicate: list[dict[str, Values]]) -> EffectResult:
    replicate_rows: list[tuple[Any, ...]] = []
    for r, measured in enumerate(per_replicate):
        base = measured["baseline"]
        for arm, values in measured.items():
            for (policy, metric), value in values.items():
                difference = None if arm == "baseline" else value - base[(policy, metric)]
                replicate_rows.append((str(r), str(study.spec.seed + r), arm, policy, metric, value, difference))

    n = len(per_replicate)
    t = stats.t.ppf((1 + study.confidence) / 2, n - 1)
    effect_rows: list[tuple[Any, ...]] = []
    for intervention in study.interventions:
        for key in per_replicate[0][intervention.name]:
            base = [m["baseline"][key] for m in per_replicate]
            treated = [m[intervention.name][key] for m in per_replicate]
            diffs = [y - x for x, y in zip(base, treated)]
            effect = statistics.fmean(diffs)
            half = 0.0 if len(set(diffs)) == 1 else float(t) * statistics.stdev(diffs) / math.sqrt(n)
            base_mean = statistics.fmean(base)
            effect_rows.append(
                (
                    intervention.name,
                    key[0],
                    key[1],
                    base_mean,
                    statistics.fmean(treated),
                    effect,
                    effect - half,
                    effect + half,
                    effect / base_mean if base_mean != 0 else None,
                    n,
                    study.method(),
                )
            )
    return EffectResult(Table(EFFECTS_INFO, effect_rows), Table(REPLICATES_INFO, replicate_rows))
