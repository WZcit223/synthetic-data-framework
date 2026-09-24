"""Effect studies: paired replicates, the interval, the checks that keep pairing honest, and the limits."""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, replace
from typing import ClassVar

import pytest
from scipy import stats

from sdf.synthesis.api import SynthesizerInfo
from sdf.synthesis.registry import default_registry
from sdf.synthesis.spec import GenerationSpec
from sdf.synthesis.warehouse import WarehouseGenerator, WarehouseSpecSynthesizer
from . import catalog, effects as fx
from .effects import MAX_EFFECT_WORK, EffectStudy, effect_work, snapshot
from .experiment import Experiment
from .world import World

SMALL = GenerationSpec(n_skus=30, horizon_days=30)
PROMO = catalog.intervention("promo_spike")
SERVICE = catalog.policy("service-level", service_level=0.95)
COST = catalog.outcome("simulated_cost")


def study(**kw) -> EffectStudy:
    args = dict(spec=SMALL, interventions=[PROMO], policies=[SERVICE], outcomes=[COST], replicates=3)
    args.update(kw)
    return EffectStudy(**args)


@pytest.fixture(scope="module")
def result():
    return study(outcomes=[COST, catalog.outcome("active_stockouts")]).run()


def rows_as_dicts(table):
    names = [f.name for f in table.info.fields]
    return [dict(zip(names, r)) for r in table.rows]


# -- the tables -----------------------------------------------------------------------------------


def test_replicate_zero_equals_the_experiment_on_the_same_world(result):
    world = World.generate(SMALL)
    expected = Experiment(
        world, [catalog.intervention("baseline"), PROMO], [SERVICE], [COST, catalog.outcome("active_stockouts")]
    ).run()
    got = [(r["intervention"], r["policy"], r["metric"], r["value"]) for r in rows_as_dicts(result.replicates)]
    replicate0 = [g for g, r in zip(got, rows_as_dicts(result.replicates)) if r["replicate"] == "0"]
    assert replicate0 == [(e.intervention, e.policy, e.metric, e.value) for e in expected]


def test_replicates_are_paired_by_seed_and_carry_the_difference(result):
    rows = rows_as_dicts(result.replicates)
    assert {r["seed"] for r in rows} == {"42", "43", "44"}
    base = {(r["replicate"], r["policy"], r["metric"]): r["value"] for r in rows if r["intervention"] == "baseline"}
    for r in rows:
        if r["intervention"] == "baseline":
            assert r["difference"] is None
        else:
            assert r["difference"] == pytest.approx(r["value"] - base[(r["replicate"], r["policy"], r["metric"])])
    effects = {(e["policy"], e["metric"]): e for e in rows_as_dicts(result.effects)}
    for (policy, metric), e in effects.items():
        diffs = [r["difference"] for r in rows if r["intervention"] == "promo_spike" and r["metric"] == metric]
        assert e["effect"] == pytest.approx(sum(diffs) / len(diffs))
        assert e["replicates"] == 3 and e["method"] == "paired t, 95 %"


def test_the_fields_are_those_of_the_contract(result):
    assert [f.name for f in result.effects.info.fields] == [
        "intervention", "policy", "metric", "baseline", "treated", "effect",
        "ci_low", "ci_high", "relative_effect", "replicates", "method",
    ]  # fmt: skip
    assert [f.name for f in result.replicates.info.fields] == [
        "replicate", "seed", "intervention", "policy", "metric", "value", "difference",
    ]  # fmt: skip


@dataclass(frozen=True)
class SeedOutcome:
    """Seed × 2 on a promo world, seed on the baseline: the differences are the seeds (42, 43, 44)."""

    name: str = "seed_outcome"

    def measure(self, world, policy):
        promo = world.spec.daily_orders_per_a_sku > SMALL.daily_orders_per_a_sku
        return {"v": float(world.spec.seed * (2 if promo else 1))}


def test_the_interval_is_students_t_on_the_paired_differences():
    (row,) = study(outcomes=[SeedOutcome()]).run().effects.rows
    half = stats.t.ppf(0.975, 2) * 1.0 / math.sqrt(3)  # differences 42, 43, 44: mean 43, sd 1
    assert row[5] == pytest.approx(43)
    assert (row[6], row[7]) == pytest.approx((43 - half, 43 + half))
    assert row[6] == pytest.approx(43 - 2.4841, abs=1e-4)
    low80 = study(outcomes=[SeedOutcome()], confidence=0.8).run().effects.rows[0]
    assert low80[10] == "paired t, 80 %" and low80[6] > row[6]  # a lower confidence, a narrower interval


def test_an_unmoved_metric_has_a_zero_width_interval(result):
    stockouts = [e for e in rows_as_dicts(result.effects) if e["metric"] == "active_stockouts"]
    assert stockouts and all(e["ci_low"] == e["effect"] == e["ci_high"] for e in stockouts)


@dataclass(frozen=True)
class ZeroBaseline:
    name: str = "zero_baseline"

    def measure(self, world, policy):
        return {"v": 1.0 if world.spec.daily_orders_per_a_sku > SMALL.daily_orders_per_a_sku else 0.0}


def test_the_relative_effect_is_empty_on_a_zero_baseline():
    (row,) = study(outcomes=[ZeroBaseline()]).run().effects.rows
    assert row[3] == 0 and row[5] == 1 and row[8] is None


def test_warehouse_spec_shares_its_tables_between_the_arms_of_one_seed():
    base = World.generate(SMALL)
    promo = PROMO.apply(base)
    for entity in ("SKU", "Location", "InventorySnapshot"):
        assert base.stream(entity) == promo.stream(entity)
    assert base.stream("OutboundOrder") != promo.stream("OutboundOrder")


# -- refusals ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "message"),
    [
        ({"replicates": 1}, "replicates must be from 2 to 20, got 1"),
        ({"replicates": 21}, "replicates must be from 2 to 20, got 21"),
        ({"replicates": True}, "replicates must be a whole number"),
        ({"confidence": 0.5}, "confidence must be above 0.5 and below 1"),
        ({"confidence": 1.0}, "confidence must be above 0.5 and below 1"),
        ({"confidence": float("nan")}, "confidence must be above 0.5 and below 1"),
        ({"interventions": []}, "interventions must name at least one"),
        ({"policies": []}, "policies must name at least one"),
        ({"outcomes": []}, "outcomes must name at least one"),
        ({"interventions": [catalog.intervention("baseline")]}, "baseline is what every intervention is compared with"),
        ({"interventions": [PROMO, PROMO]}, r"interventions: each may appear once, repeated \['promo_spike'\]"),
        ({"policies": [SERVICE, SERVICE]}, "policies: each may appear once"),
    ],
)
def test_an_invalid_study_is_refused_naming_the_field(kw, message):
    with pytest.raises(ValueError, match=message):
        study(**kw)


def test_a_study_over_budget_is_refused_before_any_work(monkeypatch):
    big = study(spec=GenerationSpec(n_skus=500, horizon_days=180), replicates=20)
    assert big.work() > MAX_EFFECT_WORK
    monkeypatch.setattr(fx.World, "generate", lambda *a, **k: pytest.fail("generated despite the budget"))
    with pytest.raises(ValueError, match=r"work 4,612,500 exceeds MAX_EFFECT_WORK 1,200,000 \(20 replicates"):
        big.run()


def test_the_work_formula():
    assert effect_work(10, 2, 2, 1, 200, 90) == 837_000  # the contract's check_only example
    assert study().size() == "3 replicates × 2 arms × 1 policy × 1 outcome × 30 SKUs × 30 days"


def test_the_study_leaves_its_baseline_world_unchanged():
    held = World.generate(SMALL)
    before = snapshot(held)
    study(baseline=held).run()
    assert snapshot(held) == before


# -- generators and interventions that would break pairing ----------------------------------------


def registry_with(cls):
    reg = default_registry()
    reg.register(cls)
    return reg


class Unseeded(WarehouseSpecSynthesizer):
    """Draws a different world on every call: its randomness does not come from the spec."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("unseeded", "warehouse", False, "ignores spec.seed")
    calls = itertools.count()

    def sample(self, n=None, *, seed=None):
        return WarehouseGenerator(replace(self.spec, seed=self.spec.seed + 1000 * next(self.calls))).generate()


def test_a_generator_that_ignores_the_seed_is_refused():
    with pytest.raises(ValueError, match="generator unseeded is not deterministic in its spec"):
        study(synthesizer="unseeded", synthesizers=registry_with(Unseeded)).run()
    study(synthesizer="warehouse-spec").run()  # the built-in passes


class ReusesRows(WarehouseSpecSynthesizer):
    """Deterministic output, but each call renames the SKU objects the previous call returned."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("reuses-rows", "warehouse", False, "mutates old rows")
    previous: ClassVar[list] = []

    def sample(self, n=None, *, seed=None):
        for sku in ReusesRows.previous:
            sku.name += " (changed)"
        wh = WarehouseGenerator(self.spec).generate()
        ReusesRows.previous = list(wh.skus)
        return wh


def test_a_generator_that_mutates_an_earlier_world_is_refused():
    reg = registry_with(ReusesRows)
    with pytest.raises(ValueError, match="the generator modified an earlier world; regenerate the world"):
        study(synthesizer="reuses-rows", synthesizers=reg).run()


@dataclass(frozen=True)
class RandomDrop:
    """Drops a different SKU on every call: state of its own, so two applications always differ."""

    name: str = "random_drop"
    calls = itertools.count()

    def apply(self, world):
        skus = world.stream("SKU")
        drop = skus[next(self.calls) % len(skus)]
        return world.with_stream("SKU", [s for s in skus if s is not drop], label=self.name)


@dataclass(frozen=True)
class Appends:
    """Deterministic, but appends to its input world's rows."""

    name: str = "appends"

    def apply(self, world):
        source = world.registry.sources()[0]
        source._rows.append(source._rows[0])
        return world.with_stream("SKU", world.stream("SKU"), label=self.name)


@dataclass(frozen=True)
class AppendsLater:
    """Leaves replicate 0's world alone, then appends to the rows of every later replicate's world."""

    name: str = "appends_later"

    def apply(self, world):
        if world.spec.seed != SMALL.seed:
            source = world.registry.sources()[0]
            source._rows.append(source._rows[0])
        return world.with_stream("SKU", world.stream("SKU"), label=self.name)


class ChangesLater:
    """Deterministic on replicate 0, then answers differently on the second call for any later base."""

    name = "changes_later"
    calls = itertools.count()

    def apply(self, world):
        skus = world.stream("SKU")
        if world.spec.seed != SMALL.seed and next(self.calls) % 2:
            skus = skus[1:]
        return world.with_stream("SKU", skus, label=self.name)


class ReusesBaseRows(WarehouseSpecSynthesizer):
    """Renames the previous call's SKUs on each call: from replicate 1 on, the base a custom arm reads changes."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("reuses-base-rows", "warehouse", False, "mutates old rows")
    previous: ClassVar[list] = []

    def sample(self, n=None, *, seed=None):
        for sku in ReusesBaseRows.previous:
            sku.name += " (changed)"
        wh = WarehouseGenerator(self.spec).generate()
        if self.spec.seed != SMALL.seed:
            ReusesBaseRows.previous = list(wh.skus)  # only later worlds are reused, so the reference stays intact
        return wh


def test_later_replicates_are_checked_too():
    with pytest.raises(ValueError, match="intervention changes_later is not deterministic"):
        study(interventions=[ChangesLater()]).run()
    reg = registry_with(ReusesBaseRows)
    # In replicate 1, PROMO regenerates after the base was snapshot, which renames the base's SKUs;
    # the custom arm that reads the base next must refuse it.
    with pytest.raises(ValueError, match="the generator modified an earlier world"):
        study(synthesizer="reuses-base-rows", synthesizers=reg, interventions=[PROMO, Copies()]).run()


@dataclass(frozen=True)
class Copies:
    """Deterministic and non-mutating: a custom intervention that passes."""

    name: str = "copies"

    def apply(self, world):
        return world.with_stream("SKU", world.stream("SKU"), label=self.name)


def test_custom_interventions_must_be_deterministic_and_leave_their_input_alone():
    with pytest.raises(ValueError, match="intervention random_drop is not deterministic"):
        study(interventions=[RandomDrop()]).run()
    with pytest.raises(ValueError, match="intervention appends modified its input world"):
        study(interventions=[Appends()]).run()
    with pytest.raises(ValueError, match="intervention appends_later modified its input world"):
        study(interventions=[AppendsLater(), PROMO]).run()  # caught in replicate 1, before PROMO runs on it
    assert study(interventions=[Copies()]).run().effects.rows


class Slow(WarehouseSpecSynthesizer):
    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("slow", "warehouse", False, "sleeps per world")

    def sample(self, n=None, *, seed=None):
        time.sleep(0.15)
        return super().sample(n, seed=seed)


def test_a_slow_generator_is_refused_up_front_with_what_would_fit(monkeypatch):
    monkeypatch.setattr(fx, "MAX_EFFECT_SECONDS", 1.5)
    reg = registry_with(Slow)
    started = time.monotonic()
    with pytest.raises(
        ValueError, match=r"generator slow takes 0\.1\d s per world; (at most \d+|not even 2) replicate"
    ):
        study(synthesizer="slow", synthesizers=reg, replicates=10).run()
    assert time.monotonic() - started < 1.0  # refused after the check, not after the study


class SlowLater(WarehouseSpecSynthesizer):
    """Fast for the two check generations, slow afterwards: the projection passes, the deadline stops it."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("slow-later", "warehouse", False, "slows down")
    calls = itertools.count()

    def sample(self, n=None, *, seed=None):
        if next(self.calls) >= 2:
            time.sleep(0.4)
        return super().sample(n, seed=seed)


def test_the_deadline_stops_a_generator_that_slows_down(monkeypatch):
    monkeypatch.setattr(fx, "MAX_EFFECT_SECONDS", 1.0)
    reg = registry_with(SlowLater)
    with pytest.raises(ValueError, match=r"passed its 1 s limit at .+, after \d of 4 replicates"):
        study(synthesizer="slow-later", synthesizers=reg, replicates=4).run()


# -- the limit and the contract ---------------------------------------------------------------------


def test_a_request_at_the_budget_finishes_within_its_time():
    policies = [catalog.policy("service-level", service_level=x) for x in (0.8, 0.85, 0.9, 0.95, 0.99)]
    heavy = study(
        spec=GenerationSpec(),
        policies=[*policies, catalog.policy("naive")],
        outcomes=[catalog.outcome(n) for n in ("simulated_cost", "replenishment_need", "active_stockouts")],
        replicates=5,
    )
    assert MAX_EFFECT_WORK * 0.85 < heavy.work() <= MAX_EFFECT_WORK
    started = time.monotonic()
    heavy.run()
    assert time.monotonic() - started < fx.MAX_EFFECT_SECONDS


def test_the_contract_example_runs_as_written():
    # docs/refactor/causal/interfaces.md §1.3
    result = EffectStudy(
        GenerationSpec(),
        [catalog.intervention("promo_spike")],
        [catalog.policy("service-level", service_level=0.95)],
        [catalog.outcome("simulated_cost")],
        replicates=10,
    ).run()
    (holding,) = [r for r in result.effects.rows if r[2] == "holding_cost"]
    assert holding[:3] == ("promo_spike", "service-level-95", "holding_cost")
    assert holding[5] == pytest.approx(79_790, rel=1e-3) and holding[6] > 0  # the interval excludes 0
    (unmet,) = [r for r in result.effects.rows if r[2] == "unmet_units"]
    assert unmet[6] < 0 < unmet[7]  # covers 0
