"""The benchmarks: the promotion benchmark (table, exact truth, edge cases, bounds) and the demand benchmark."""

from __future__ import annotations

import importlib.util
import math
import statistics
from dataclasses import replace
from datetime import date

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


# -- the demand benchmark ---------------------------------------------------------------------------


def test_the_demand_draw_averages_to_the_true_mean():
    from sdf.simulation.benchmark import DemandBenchmark

    d = DemandBenchmark(n_skus=400, days=365).draw()
    drawn = np.mean([d.table.series[s] for s in d.table.series])
    truth = np.mean([d.truth.mean(day) for day in d.table.days])
    assert abs(drawn / truth - 1) < 0.02
    assert d.table.days[0] == date(2025, 1, 1) and len(d.table.days) == 365
    assert list(d.table.series) == list(d.truth.sku_ids) and d.truth.sku_ids[0] == "B-0000"


def test_the_exact_quantiles_match_the_simulated_mixture():
    from sdf.simulation.benchmark import DemandBenchmark

    d = DemandBenchmark(n_skus=12, days=84, intermittent_share=0.5, promo_rate=0.2, promo_uplift=1.0, seed=3).draw()
    t = d.truth
    day = d.table.days[10]
    exact = t.quantiles(day, (0.1, 0.5, 0.9))
    rng = np.random.default_rng(0)
    c = t.component[:, 10][:, None]
    lifted = np.where(rng.random((12, 40_000)) < t.promo_rate, 1 + t.promo_uplift, 1.0)
    k = t.dispersion
    sims = rng.negative_binomial(k, k / (k + c * lifted)) * (rng.random((12, 40_000)) >= t.zero[:, None])
    for lv in (0.1, 0.5, 0.9):
        simulated = np.quantile(sims, lv, axis=1, method="inverted_cdf")
        assert np.abs(exact[lv] - simulated).max() <= 1, lv  # counts: at most one unit apart from sampling noise
    assert np.allclose(t.mean(day), sims.mean(axis=1), rtol=0.05)
    cdf = t.cdf(day, np.array([-2, -1, 0, 10_000]))
    assert (cdf[:, :2] == 0).all() and np.allclose(cdf[:, 3], 1.0)
    assert np.allclose(cdf[:, 2], (sims == 0).mean(axis=1), atol=0.02)  # P(0) includes the structural zero


def test_without_promotions_or_zeros_the_quantiles_are_the_negative_binomial_s():
    from scipy import stats

    from sdf.simulation.benchmark import DemandBenchmark

    d = DemandBenchmark(n_skus=10, days=84, intermittent_share=0.0, promo_rate=0.0, dispersion=4.0).draw()
    day = d.table.days[5]
    c = d.truth.component[:, 5]
    for lv, got in d.truth.quantiles(day, (0.25, 0.75)).items():
        assert np.array_equal(got, stats.nbinom.ppf(lv, 4.0, 4.0 / (4.0 + c)))
    assert np.allclose(d.truth.mean(day), c)


def test_the_demand_benchmark_refuses_values_outside_its_bounds():
    from sdf.simulation.benchmark import DemandBenchmark

    names = [p.name for p in DemandBenchmark.params()]
    assert names == ["n_skus", "days", "intermittent_share", "promo_rate", "promo_uplift", "dispersion", "seed"]
    for kwargs, match in (
        ({"n_skus": 9}, "n_skus must be from 10 to 400"),
        ({"days": 800}, "days must be from 84 to 730"),
        ({"promo_rate": 0.5}, "promo_rate must be from 0.0 to 0.2"),
        ({"seed": -1}, "seed must be from 0 to inf"),
    ):
        with pytest.raises(ValueError, match=match):
            DemandBenchmark(**kwargs)
    assert DemandBenchmark().draw().table.series == DemandBenchmark(seed=7).draw().table.series


def test_the_true_distribution_s_coverages_bracket_the_nominal_level():
    from sdf.analytics.forecasters import TRUE_DISTRIBUTION, backtest
    from sdf.simulation.benchmark import DemandBenchmark

    d = DemandBenchmark().draw()
    result = backtest(["seasonal-naive"], d.table, horizon=14, origins=4, truth=d.truth)
    row = next(r for r in result.scores.rows if r[0] == TRUE_DISTRIBUTION)
    cov_open, cov_closed, nominal = row[6], row[7], row[8]
    assert cov_open <= nominal <= cov_closed
    snaive = result.scores.rows[0]
    assert row[5] < snaive[5]  # the exact distribution's pinball loss is below seasonal naive's
    observed = d.observed()
    assert len(observed.rows) == 200 * 365 and observed.info.name == "demand-benchmark"
