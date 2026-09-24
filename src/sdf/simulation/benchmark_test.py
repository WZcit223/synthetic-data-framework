"""The promotion benchmark: its table, the exact truth, the mechanism's edge cases and its bounds."""

from __future__ import annotations

import importlib.util
import math
import statistics
from dataclasses import replace

import numpy as np
import pytest

from sdf.analytics.causal import default_estimators, score
from sdf.synthesis.spec import GenerationSpec
from .benchmark import BENCHMARK_INFO, QUESTION, PromotionBenchmark
from .world import World


@pytest.fixture(scope="module")
def world():
    return World.generate(GenerationSpec())


def column(draw, name):
    i = [f.name for f in draw.table.info.fields].index(name)
    return [r[i] for r in draw.table.rows]


def test_the_table_s_fields_and_question():
    assert [(f.name, f.kind, f.unit, f.aggregate) for f in BENCHMARK_INFO.fields] == [
        ("sku_id", "dimension", None, None),
        ("abc_class", "dimension", None, None),
        ("log_demand", "measure", None, "mean"),
        ("log_price", "measure", None, "mean"),
        ("promoted", "measure", None, "mean"),
        ("weekly_units", "measure", "units", "mean"),
    ]
    assert QUESTION.to_dict() == {
        "treatment": "promoted",
        "outcome": "weekly_units",
        "covariates": ["log_demand", "abc_class", "log_price"],
        "treated_value": 1,
    }


def test_the_truth_is_exact_and_the_table_shows_the_observed_outcome(world):
    draw = PromotionBenchmark(uplift=0.3, noise=0.0).draw(world)  # without noise, y(0) = 7 × mean daily demand
    y0 = [7 * math.exp(v) for v in column(draw, "log_demand")]
    assert draw.true_effect == pytest.approx(0.3 * statistics.fmean(y0))
    for promoted, observed, base in zip(column(draw, "promoted"), column(draw, "weekly_units"), y0):
        assert observed == pytest.approx(base * (1.3 if promoted else 1.0))
    assert set(column(draw, "promoted")) == {0, 1}
    assert len(draw.table.rows) == sum(1 for s in world.stream("SKU") if world.demand().series.get(s.sku_id))
    assert PromotionBenchmark(seed=3).draw(world) == PromotionBenchmark(seed=3).draw(world)  # repeatable


def test_confounding_zero_promotes_at_random(world):
    draw = PromotionBenchmark(confounding=0.0, seed=11).draw(world)
    n = len(draw.table.rows)
    p = 1 / (1 + math.exp(0.5))  # the same probability for every SKU, whatever its demand
    expected = (np.random.default_rng(11).random(n) < p).astype(int).tolist()
    assert column(draw, "promoted") == expected


def test_one_shared_demand_gives_z_zero_instead_of_a_division_by_zero(world):
    orders = world.stream("OutboundOrder")
    first = next(o for o in orders if o.status != "cancelled")
    skus = world.stream("SKU")[:12]
    flat = world.with_stream(
        "OutboundOrder",
        [replace(first, order_id=f"O{i}", sku_id=s.sku_id, quantity=5) for i, s in enumerate(skus)],
        label="flat",
    )
    for confounding in (0.0, 3.0):  # with sd 0 promotion is random: the confounding changes nothing
        draw = PromotionBenchmark(confounding=confounding, seed=5).draw(flat)
        assert len(draw.table.rows) == 12 and len(set(column(draw, "log_demand"))) == 1
        expected = (np.random.default_rng(5).random(12) < 1 / (1 + math.exp(0.5))).astype(int).tolist()
        assert column(draw, "promoted") == expected


def test_a_sku_with_unit_price_zero_has_log_price_zero(world):
    free = world.with_stream("SKU", [replace(s, unit_price=0.0) for s in world.stream("SKU")], label="free")
    assert set(column(PromotionBenchmark().draw(free), "log_price")) == {0.0}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"uplift": -1.0}, "uplift must be from -0.9 to 3.0, got -1.0"),
        ({"uplift": float("nan")}, "uplift must be finite, got nan"),
        ({"confounding": 3.5}, "confounding must be from 0.0 to 3.0, got 3.5"),
        ({"noise": -0.1}, "noise must be from 0.0 to 1.0, got -0.1"),
        ({"seed": 1.5}, "seed must be a whole number, got 1.5"),
        ({"seed": -1}, "seed must be from 0 to inf, got -1"),
        ({"noise": "high"}, "noise must be a number, got 'high'"),
    ],
)
def test_the_bounds_are_refused_by_the_benchmark_itself(kwargs, message):
    with pytest.raises(ValueError, match=f"^{message}$".replace("(", r"\(").replace(")", r"\)")):
        PromotionBenchmark(**kwargs)


def test_any_seed_the_bounds_allow_draws(world):
    for seed in (0, 2**64 + 5):  # numpy's generator takes any non-negative integer
        assert PromotionBenchmark(seed=seed).draw(world).table.rows


def test_the_published_params_are_the_bounds_it_checks():
    assert [p.to_dict() for p in PromotionBenchmark.params()] == [
        {
            "name": "uplift",
            "type": "float",
            "default": 0.3,
            "min": -0.9,
            "max": 3.0,
            "exclusive": False,
            "nullable": False,
        },
        {
            "name": "confounding",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 3.0,
            "exclusive": False,
            "nullable": False,
        },
        {
            "name": "noise",
            "type": "float",
            "default": 0.25,
            "min": 0.0,
            "max": 1.0,
            "exclusive": False,
            "nullable": False,
        },
        {"name": "seed", "type": "int", "default": 7, "min": 0, "max": None, "exclusive": False, "nullable": False},
    ]


def test_over_50_seeds_adjustment_recovers_the_truth_and_the_naive_difference_does_not(world):
    """The plan's acceptance measure (interfaces.md §3.3): the mean effect over 50 draws at confounding 1."""
    reg = default_estimators()
    truths, naive, adjusted = [], [], []
    for s in range(50):
        d = PromotionBenchmark(confounding=1.0, seed=s).draw(world)
        rows = score(d.table, d.question, reg, names=["difference-in-means", "regression-adjustment"]).rows
        truths.append(d.true_effect)
        naive.append(rows[0][1])
        adjusted.append(rows[1][1])
    truth = statistics.fmean(truths)
    assert abs(statistics.fmean(adjusted) - truth) < 0.15 * truth
    assert statistics.fmean(naive) > 3 * truth


def test_the_contract_example_runs_as_written(world):
    # docs/refactor/causal/interfaces.md §3.3
    reg = default_estimators()
    draw = PromotionBenchmark(confounding=1.0).draw(world)
    scores = score(
        draw.table,
        draw.question,
        reg,
        names=["difference-in-means", "regression-adjustment", "ipw"],
        true_effect=draw.true_effect,
    )
    naive, adjusted, ipw = scores.rows
    assert naive[7] == "no" and adjusted[7] == "yes" and ipw[7] == "yes"
    assert naive[1] > 3 * draw.true_effect


@pytest.mark.skipif(
    importlib.util.find_spec("dowhy") is None or importlib.util.find_spec("econml") is None,
    reason="needs the causal extra (Python 3.13)",
)
def test_the_pywhy_estimators_land_near_the_adjusted_built_ins(world):
    draw = PromotionBenchmark(confounding=1.0).draw(world)
    names = ["regression-adjustment", "ipw", "dowhy-backdoor", "econml-dml"]
    rows = {
        r[0]: r
        for r in score(draw.table, draw.question, default_estimators(), names=names, true_effect=draw.true_effect).rows
    }
    for name in ("dowhy-backdoor", "econml-dml"):
        assert rows[name][1] is not None, rows[name][11]
        assert abs(rows[name][1] - rows["regression-adjustment"][1]) < 0.25 * draw.true_effect
        assert rows[name][7] == "yes"
