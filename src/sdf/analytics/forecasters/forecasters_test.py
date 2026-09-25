"""The forecaster contract (docs/refactor/algorithms/interfaces.md §1 and §2): guard, built-ins, backtest."""

from __future__ import annotations

from datetime import date, timedelta
from typing import ClassVar

import numpy as np
import pytest

from sdf.analytics.demand import DemandTable
from . import (
    MIN_HISTORY,
    TRUE_DISTRIBUTION,
    Forecast,
    ForecasterInfo,
    ForecasterRegistry,
    backtest,
    check_quantiles,
    default_forecasters,
    quantile_field,
)
from .backtest import _metrics
from .builtin import MeanForecaster, MovingAverage, NaiveForecaster, SeasonalLinear, SeasonalNaive

START = date(2025, 1, 1)
LEVELS = (0.1, 0.5, 0.9)


def table(*series: list[float], start: date = START) -> DemandTable:
    n = len(series[0])
    days = tuple(start + timedelta(days=i) for i in range(n))
    return DemandTable(days=days, series={f"S{i}": tuple(float(v) for v in s) for i, s in enumerate(series)})


def weekly(n: int, pattern=(1, 2, 3, 4, 5, 6, 7), level: float = 0.0) -> list[float]:
    return [level + pattern[i % len(pattern)] for i in range(n)]


# -- the table ----------------------------------------------------------------------------------------


def test_until_and_window_cut_the_day_axis():
    t = table(list(range(10)), list(range(10, 20)))
    past = t.until(START + timedelta(days=4))
    assert past.days == t.days[:4] and past.series["S1"] == (10.0, 11.0, 12.0, 13.0)
    w = t.window(START + timedelta(days=3), 2)
    assert w.days == t.days[3:5] and w.series["S0"] == (3.0, 4.0)
    with pytest.raises(ValueError, match="no day before 2025-01-01"):
        t.until(START)
    with pytest.raises(ValueError, match="the table has 2 days from 2025-01-09, not 3"):
        t.window(START + timedelta(days=8), 3)
    with pytest.raises(ValueError, match="is not a day of the table"):
        t.window(START - timedelta(days=1), 1)


# -- the catalogue and the guard ----------------------------------------------------------------------


def test_the_five_built_ins_are_mounted_with_their_parameters():
    reg = default_forecasters()
    assert {"mean", "naive", "moving-average", "seasonal-naive", "seasonal-linear"} <= set(reg.names())
    assert all(reg.origin(n) == "builtin" for n in ("mean", "seasonal-linear"))
    (window,) = reg.params("moving-average")
    assert (window.name, window.type, window.default, window.min, window.max) == ("window", "int", 7, 1, 365)
    assert reg.params("mean") == ()
    with pytest.raises(ValueError, match="window must be from 1 to 365, got 0"):
        reg.create("moving-average", window=0)
    with pytest.raises(ValueError, match=r"takes no parameter \['span'\]"):
        reg.create("moving-average", span=3)
    with pytest.raises(KeyError, match="unknown forecaster 'nope'"):
        reg.create("nope")


def test_check_quantiles_names_each_problem():
    assert check_quantiles([0.1, 0.9]) == (0.1, 0.9)
    for bad, match in (
        ([], "at least one"),
        ([0.0, 0.5], "strictly between 0 and 1"),
        ([0.5, True], "strictly between 0 and 1"),
        ([0.5, 0.5], "distinct"),
        ([0.9, 0.1], "sorted"),
        ([i / 20 for i in range(1, 11)], "at most 9"),
    ):
        with pytest.raises(ValueError, match=match):
            check_quantiles(bad)


class Scripted:
    """A forecaster whose result a test writes; ``make`` gets the history and the horizon."""

    info: ClassVar[ForecasterInfo] = ForecasterInfo("scripted", "A result the test decides")
    make: ClassVar = None

    def fit(self, history):
        return self

    def forecast(self, history, *, horizon, quantiles):
        return type(self).make(history, horizon, quantiles)


def scripted(make) -> tuple[ForecasterRegistry, Scripted]:
    cls = type("S", (Scripted,), {"make": staticmethod(make)})
    reg = ForecasterRegistry()
    reg.register(cls)
    return reg, cls()


def good(history, horizon, levels, **change):
    n = len(history.series)
    fields = dict(
        forecaster="scripted",
        origin=history.days[-1] + timedelta(days=1),
        sku_ids=tuple(history.series),
        mean=np.ones((n, horizon)),
        quantiles={q: np.full((n, horizon), q) for q in levels},
    )
    fields.update(change)
    return Forecast(**fields)


@pytest.mark.parametrize(
    "change, match",
    [
        ({"forecaster": "other"}, "labelled 'other'"),
        ({"sku_ids": ("S0",)}, "other SKUs than the history's"),
        ({"mean": np.ones((2, 2))}, r"mean of shape \(2, 2\), not \(2, 3\)"),
        ({"mean": np.full((2, 3), np.nan)}, "non-finite mean"),
        ({"quantiles": {0.5: np.ones((2, 3))}}, r"returned the levels \[0.5\]"),
        ({"origin": START}, r"forecast from 2025-01-01, not 2025-01-31 \(the day after the history\)"),
    ],
)
def test_the_guard_refuses_what_cannot_be_scored(change, match):
    reg, model = scripted(lambda h, k, q: good(h, k, q, **change))
    with pytest.raises(ValueError, match=match):
        reg.forecast(model, table([1] * 30, [2] * 30), horizon=3, quantiles=LEVELS)


def test_the_guard_repairs_negatives_and_crossed_quantiles_and_says_so():
    def make(h, k, q):
        crossed = {0.1: np.full((2, k), 5.0), 0.5: np.full((2, k), 1.0), 0.9: np.full((2, k), -1.0)}
        return good(h, k, q, mean=np.full((2, k), -2.0), quantiles=crossed)

    reg, model = scripted(make)
    fc = reg.forecast(model, table([1] * 30, [2] * 30), horizon=3, quantiles=LEVELS)
    assert (fc.mean == 0).all()
    assert (fc.quantiles[0.1] == 0).all() and (fc.quantiles[0.5] == 1).all() and (fc.quantiles[0.9] == 5).all()
    assert "12 negative value(s) set to 0" in fc.method and "crossed quantiles sorted at 6 point(s)" in fc.method


# -- the built-ins ----------------------------------------------------------------------------------------


def run(model, history, horizon=7):
    reg = ForecasterRegistry()
    reg.register(type(model))
    return reg.forecast(model, history, horizon=horizon, quantiles=LEVELS)


def test_a_constant_series_gives_that_constant_and_a_zero_width_interval():
    for model in (MeanForecaster(), NaiveForecaster(), MovingAverage(), SeasonalNaive(), SeasonalLinear()):
        fc = run(model, table([4.0] * 60))
        assert np.allclose(fc.mean, 4.0), model.info.name
        for lv in LEVELS:
            assert np.allclose(fc.quantiles[lv], 4.0), (model.info.name, lv)
        assert fc.origin == START + timedelta(days=60)


def test_seasonal_naive_repeats_the_last_cycle_and_linear_recovers_a_clean_week():
    history = table(weekly(63))
    snaive = run(SeasonalNaive(7), history, horizon=10)
    assert snaive.mean[0].tolist() == weekly(73)[63:]
    linear = run(SeasonalLinear(7), history, horizon=10)
    assert np.allclose(linear.mean[0], weekly(73)[63:], atol=1e-6)


@pytest.mark.parametrize(
    "model", [MeanForecaster(), NaiveForecaster(), MovingAverage(5), SeasonalNaive(7), SeasonalLinear(7)]
)
def test_a_path_from_an_origin_depends_only_on_the_days_before_it(model):
    rng = np.random.default_rng(4)
    y = rng.poisson(6, (3, 90)).astype(float)
    origins = np.append(np.arange(34, 90), 90)
    paths = model._paths(y, origins, 5)
    for j, o in enumerate(origins[:-1]):
        changed = y.copy()
        changed[:, o:] = 1_000.0  # the future, poisoned
        again = model._paths(changed, origins, 5)
        assert np.array_equal(again[:, j], paths[:, j]), (model.info.name, int(o))


def test_moving_average_uses_its_window_and_mean_the_whole_history():
    history = table([1.0] * 30 + [10.0] * 5)
    assert np.allclose(run(MovingAverage(5), history).mean, 10.0)
    assert np.allclose(run(MovingAverage(10), history).mean, 5.5)
    assert np.allclose(run(MeanForecaster(), history).mean, 80 / 35)
    assert np.allclose(run(NaiveForecaster(), history).mean, 10.0)


def test_intervals_come_from_the_model_s_own_errors():
    rng = np.random.default_rng(1)
    noisy = list(10 + rng.normal(0, 2, 120))
    fc = run(MeanForecaster(), table(noisy), horizon=3)
    lo, mid, hi = (fc.quantiles[lv][0, 0] for lv in LEVELS)
    assert lo < mid < hi and 3 < hi - lo < 8  # about 2 × 1.28 × σ = 5.1
    assert fc.method == "empirical errors of the last 56 days"


def test_a_sku_with_too_few_errors_borrows_the_pooled_scaled_errors():
    rng = np.random.default_rng(2)
    long_sku = list(10 + rng.normal(0, 2, 60))
    fc = run(NaiveForecaster(), table(long_sku[:10] + [0.0] * 50, long_sku), horizon=2)
    assert "pooled" not in fc.method  # 56 errors at step 1, 55 at step 2
    short = run(NaiveForecaster(), table([5.0, 6.0, 4.0, 5.0, 7.0], [1.0, 2.0, 1.0, 3.0, 2.0]), horizon=2)
    assert "fewer than 14 errors at some days ahead, so all SKUs' scaled errors were pooled" in short.method
    assert (short.quantiles[0.9] >= short.quantiles[0.1]).all()


# -- the metrics ----------------------------------------------------------------------------------------


def test_the_metrics_on_a_hand_computed_case():
    actual = np.array([[2.0, 4.0]])
    mean = np.array([[3.0, 2.0]])
    qs = {0.1: np.array([[2.0, 1.0]]), 0.9: np.array([[3.0, 3.0]])}
    ref_abs = np.array([[2.0, 2.0]])
    wape, rel, bias, mae, pinball, cov_open, cov_closed, nominal, width = _metrics(
        actual, mean, qs, (0.1, 0.9), ref_abs
    )
    assert wape == round(3 / 6, 4) and rel == 0.75 and bias == round(-1 / 6, 4) and mae == 1.5
    # pinball at 0.1: y=2,q=2 -> 0; y=4,q=1 -> 0.3 | at 0.9: y=2,q=3 -> 0.1; y=4,q=3 -> 0.9
    assert pinball == round(((0 + 0.3) / 2 + (0.1 + 0.9) / 2) / 2, 4)
    assert cov_open == 0.0 and cov_closed == 0.5  # 2 sits on the lower bound; 4 is above the upper
    assert nominal == 0.8 and width == 1.5


def test_wape_is_empty_only_when_every_actual_is_zero_and_relative_when_the_reference_is_exact():
    zero = np.zeros((1, 2))
    out = _metrics(zero, np.ones((1, 2)), {0.5: np.ones((1, 2))}, (0.5,), np.zeros((1, 2)))
    assert out[0] is None and out[1] is None and out[2] is None
    assert out[5:] == (None, None, None, None)  # one level: no interval


# -- the backtest ----------------------------------------------------------------------------------------


def test_the_backtest_scores_every_forecaster_on_the_same_points():
    rng = np.random.default_rng(3)
    history = table(*[list(rng.poisson(5 + i, 90).astype(float)) for i in range(4)])
    result = backtest(["mean", "seasonal-naive"], history, horizon=7, origins=3, step=7)
    assert [r[0] for r in result.scores.rows] == ["mean", "seasonal-naive"]
    snaive = result.scores.rows[1]
    assert snaive[2] == 1.0 and snaive[12] is None  # relative to itself
    assert len(result.by_horizon.rows) == 2 * 7 and result.by_horizon.rows[0][1] == 1
    assert len(result.forecasts.rows) == 2 * 4 * 7
    assert [f.name for f in result.forecasts.info.fields][-3:] == ["q10", "q50", "q90"]
    assert result.origins == (history.days[69], history.days[76], history.days[83])


def test_no_forecaster_sees_a_day_at_or_after_its_origin():
    seen: list[date] = []

    def make(h, k, q):
        seen.append(h.days[-1])
        return good(h, k, q)

    reg, _ = scripted(make)
    history = table([1.0] * 60, [2.0] * 60)
    result = backtest(["scripted"], history, horizon=5, origins=3, step=4, registry=reg)
    assert seen == [o - timedelta(days=1) for o in result.origins]


def test_refit_once_fits_on_the_first_origin_only():
    fits: list[int] = []

    class Counting(MeanForecaster):
        info: ClassVar[ForecasterInfo] = ForecasterInfo("counting", "counts its fits")

        def fit(self, history):
            fits.append(len(history.days))
            return self

    reg = ForecasterRegistry()
    reg.register(Counting)
    history = table([1.0] * 60)
    backtest(["counting"], history, horizon=5, origins=3, step=4, refit="once", registry=reg)
    assert fits == [60 - 5 - 8]
    fits.clear()
    backtest(["counting"], history, horizon=5, origins=3, step=4, registry=reg)
    assert fits == [47, 51, 55]


def test_a_failing_forecaster_is_an_error_row_and_the_others_still_run():
    def make(h, k, q):
        raise RuntimeError("boom")

    reg, _ = scripted(make)
    reg.register(MeanForecaster)
    result = backtest(["scripted", "mean"], table([1.0] * 60), horizon=5, origins=2, registry=reg)
    broken, fine = result.scores.rows
    assert broken[12] == "RuntimeError: boom" and broken[1] is None
    assert fine[12] is None and fine[1] == 0.0


def test_a_constructor_that_fails_is_an_error_row_not_a_failed_request():
    class Fragile(MeanForecaster):
        info: ClassVar[ForecasterInfo] = ForecasterInfo("fragile", "cannot be built")

        def __init__(self) -> None:
            raise RuntimeError("no model file")

    reg = ForecasterRegistry()
    reg.register(Fragile)
    reg.register(MeanForecaster)
    result = backtest(["fragile", "mean"], table([1.0] * 60), horizon=5, origins=2, registry=reg)
    assert [r[12] for r in result.scores.rows] == ["RuntimeError: no model file", None]


def test_the_deadline_turns_forecasters_not_started_into_not_run_rows():
    result = backtest(["mean", "naive"], table([1.0] * 60), horizon=5, origins=2, deadline=0.0)
    assert [r[12] for r in result.scores.rows] == ["not run: the request's 30 s were used"] * 2


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"forecasters": []}, "at least one"),
        ({"forecasters": ["mean", "mean"]}, "repeated"),
        ({"forecasters": ["mean"] * 7}, "at most 6"),
        ({"horizon": 0}, "horizon must be a whole number from 1 to 56"),
        ({"origins": 13}, "origins must be a whole number from 1 to 12"),
        ({"refit": "never"}, "refit must be one of"),
        ({"params": {"naive": {}}}, "params names forecasters not requested"),
        ({"params": {"mean": {"x": 1}}}, "takes no parameter"),
        ({"horizon": 40, "origins": 3}, "the history has 60 days; horizon 40, 3 origins 7 days apart"),
    ],
)
def test_a_request_that_cannot_run_is_refused_before_any_forecaster(kwargs, match):
    args = {"forecasters": ["mean"], "horizon": 5, "origins": 2} | kwargs
    with pytest.raises(ValueError, match=match):
        backtest(args.pop("forecasters"), table([1.0] * 60), **args)
    assert MIN_HISTORY == 28


def test_quantile_fields_are_named_from_their_level():
    assert quantile_field(0.1) == "q10" and quantile_field(0.025) == "q2_5" and quantile_field(0.975) == "q97_5"


def test_the_true_distribution_row_uses_the_truth_given():
    class Exact:
        def mean(self, day):
            return np.array([3.0])

        def quantiles(self, day, levels):
            return {lv: np.array([3.0]) for lv in levels}

    result = backtest(["mean"], table([3.0] * 60), horizon=5, origins=2, truth=Exact())
    truth = result.scores.rows[-1]
    assert truth[0] == TRUE_DISTRIBUTION and truth[1] == 0.0 and truth[10] is None
    assert truth[11] == "the exact distribution the benchmark drew from"
