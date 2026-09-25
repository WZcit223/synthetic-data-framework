"""The gradient-boosted forecasters (docs/refactor/algorithms/interfaces.md §4.1)."""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta

import numpy as np
import pytest

from sdf.analytics.demand import DemandTable
from sdf.simulation.benchmark import DemandBenchmark
from . import backtest, boosted, default_forecasters
from .boosted import FEATURES, WINDOW, GradientBoosting, features, first_sale
from .builtin import MovingAverage
from .core import matrix

START = date(2025, 1, 6)  # a Monday
HAS_LIGHTGBM = importlib.util.find_spec("lightgbm") is not None


def table(rows: list[list[float]], start: date = START) -> DemandTable:
    days = tuple(start + timedelta(days=i) for i in range(len(rows[0])))
    return DemandTable(days=days, series={f"S{i}": tuple(float(v) for v in r) for i, r in enumerate(rows)})


def weekly_table(n_days: int, n_skus: int = 12) -> DemandTable:
    pattern = np.array([1, 2, 3, 4, 5, 8, 6], dtype=float)
    return table([list((1 + s / 3) * pattern[np.arange(n_days) % 7]) for s in range(n_skus)])


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.abs(actual - forecast).sum() / actual.sum())


def test_it_is_mounted_as_a_global_model_with_its_published_parameters():
    reg = default_forecasters()
    assert "gradient-boosting" in reg.names() and reg.info("gradient-boosting").global_model
    params = {p.name: (p.default, p.min, p.max) for p in reg.params("gradient-boosting")}
    assert params == {
        "max_iter": (200, 10, 1000),
        "learning_rate": (0.1, 0.01, 1.0),
        "max_leaf_nodes": (31, 2, 255),
        "min_history": (28, 28, 365),
        "seed": (0, 0, None),
    }
    with pytest.raises(ValueError, match="min_history must be from 28 to 365, got 7"):
        reg.create("gradient-boosting", min_history=7)


def test_a_known_weekly_pattern_without_noise_is_recovered():
    full = weekly_table(140)
    history = full.until(full.days[126])
    fc = GradientBoosting().fit(history).forecast(history, horizon=14, quantiles=(0.1, 0.9))
    actual = matrix(full)[:, 126:]
    assert wape(actual, fc.mean) < 0.05
    assert fc.origin == full.days[126] and fc.horizon == 14


def test_the_features_read_no_day_at_or_after_the_origin():
    y = matrix(weekly_table(60))
    rng = np.random.default_rng(1)
    sku = np.repeat(np.arange(len(y)), 5)
    origin = rng.integers(WINDOW, 60, len(sku))
    ahead = rng.integers(1, 15, len(sku))
    x = features(y, 0, sku, origin, ahead)
    assert x.shape == (len(sku), len(FEATURES))
    for i, (s, o) in enumerate(zip(sku, origin)):
        poisoned = y.copy()
        poisoned[:, o:] = 1e9  # every day from the row's origin on, for every SKU
        row = features(poisoned, 0, sku[i : i + 1], origin[i : i + 1], ahead[i : i + 1])
        assert np.array_equal(row[0], x[i]), (s, o)
    # the weekday is the target day's: origin + ahead - 1 days after a Monday
    assert np.array_equal(x[:, FEATURES.index("weekday")], (origin + ahead - 1) % 7)


def test_the_models_are_cached_per_horizon_and_set_of_levels_and_repeatable_with_a_seed():
    history = weekly_table(70, n_skus=6)
    model = GradientBoosting(max_iter=20).fit(history)
    first = model.forecast(history, horizon=7, quantiles=(0.1, 0.9))
    assert model.fits == 3  # the mean and two quantiles
    again = model.forecast(history, horizon=7, quantiles=(0.1, 0.9))
    assert model.fits == 3 and np.array_equal(again.mean, first.mean)
    model.forecast(history, horizon=7, quantiles=(0.1, 0.5, 0.9))
    assert model.fits == 4  # only the new level is fitted
    model.forecast(history, horizon=14, quantiles=(0.1, 0.9))
    assert model.fits == 7  # a new horizon: its own rows, so its own models
    model.fit(history)
    model.forecast(history, horizon=7, quantiles=(0.1, 0.9))
    assert model.fits == 10  # a new fit forgets the models
    other = GradientBoosting(max_iter=20).fit(history).forecast(history, horizon=7, quantiles=(0.1, 0.9))
    assert np.array_equal(other.mean, first.mean) and np.array_equal(other.quantiles[0.9], first.quantiles[0.9])


def test_a_sku_with_a_short_history_gets_the_moving_average_and_is_counted():
    rows = [list(r) for r in matrix(weekly_table(70, n_skus=5))]
    rows[4] = [0.0] * 55 + [3.0] * 15  # first sold 15 days before the origin
    history = table(rows)
    fc = GradientBoosting(max_iter=20).forecast(history, horizon=7, quantiles=(0.1, 0.9))
    ma = MovingAverage().forecast(history, horizon=7, quantiles=(0.1, 0.9))
    assert np.array_equal(fc.mean[4], ma.mean[4]) and np.array_equal(fc.quantiles[0.9][4], ma.quantiles[0.9][4])
    assert "1 SKU(s) with less than 28 days since their first sale: moving-average" in fc.method
    assert list(first_sale(matrix(history))) == [0, 0, 0, 0, 55]
    # a history too short for any model: every SKU falls back
    short = table([list(r[:20]) for r in rows])
    fc = GradientBoosting().forecast(short, horizon=3, quantiles=(0.5,))
    assert "5 SKU(s) with less than 28 days" in fc.method
    assert np.array_equal(fc.mean, MovingAverage().forecast(short, horizon=3, quantiles=(0.5,)).mean)


def test_the_backtest_scores_it_through_the_registry_guard():
    history = weekly_table(84, n_skus=6)
    result = backtest(
        ["seasonal-naive", "gradient-boosting"],
        history,
        horizon=7,
        origins=2,
        params={"gradient-boosting": {"max_iter": 30}},
    )
    rows = {r[0]: r for r in result.scores.rows}
    assert rows["gradient-boosting"][12] is None  # no error
    assert rows["gradient-boosting"][1] < 0.1  # WAPE on a clean weekly pattern


@pytest.mark.skipif(HAS_LIGHTGBM, reason="lightgbm is installed")
def test_lightgbm_is_listed_as_unavailable_without_the_app_extra():
    reg = default_forecasters()
    assert "lightgbm" not in reg.names()
    assert "lightgbm" in reg.unavailable() and "lightgbm" in reg.unavailable()["lightgbm"]


@pytest.mark.skipif(not HAS_LIGHTGBM, reason="needs the app extra (lightgbm)")
def test_lightgbm_scores_within_five_percent_of_gradient_boosting_on_the_benchmark():
    draw = DemandBenchmark().draw()
    result = backtest(["gradient-boosting", "lightgbm"], draw.table, truth=draw.truth)
    wapes = {r[0]: r[1] for r in result.scores.rows}
    assert abs(wapes["lightgbm"] - wapes["gradient-boosting"]) / wapes["gradient-boosting"] < 0.05


def test_an_origin_without_a_full_window_is_refused_not_wrapped_round():
    y = matrix(weekly_table(40))
    with pytest.raises(ValueError, match="an origin needs 28 days of history before it, got 10"):
        features(y, 0, np.array([0]), np.array([10]), np.array([1]))


def test_every_training_row_lies_inside_the_history_from_an_age_forecast_models(monkeypatch):
    seen = []
    real = boosted.features

    def spy(y, weekday0, sku, origin, ahead):
        seen.append((y.shape[1], weekday0, sku.copy(), origin.copy(), ahead.copy()))
        return real(y, weekday0, sku, origin, ahead)

    monkeypatch.setattr(boosted, "features", spy)
    rows = [list(r) for r in matrix(weekly_table(90, n_skus=4))]
    rows[3] = [0.0] * 20 + rows[3][20:]  # first sold on day 20
    start = date(2025, 1, 8)  # a Wednesday: the weekday of the first day is passed on, not assumed
    history = table(rows, start=start)
    GradientBoosting(max_iter=10, min_history=40).fit(history).forecast(history, horizon=7, quantiles=(0.5,))
    (n, wd_train, sku, origin, ahead), (_, wd_forecast, *_rest) = seen
    assert wd_train == wd_forecast == start.weekday() == 2
    assert (origin + ahead - 1 < n).all()  # every target inside the history
    assert origin[sku == 3].min() >= 20 + 40 and origin[sku != 3].min() >= 40  # from the age min_history


def test_the_rows_are_capped_and_drawn_with_the_seed(monkeypatch):
    monkeypatch.setattr(boosted, "MAX_ROWS", 300)
    history = weekly_table(70, n_skus=6)
    x1, t1 = GradientBoosting(seed=1).fit(history)._rows(7)
    x2, _ = GradientBoosting(seed=1).fit(history)._rows(7)
    x3, _ = GradientBoosting(seed=2).fit(history)._rows(7)
    assert len(x1) == len(t1) == 300
    assert np.array_equal(x1, x2) and not np.array_equal(x1, x3)


def test_a_history_with_no_demand_to_learn_from_falls_back_instead_of_failing():
    rows = [[5.0] + [0.0] * 59, [2.0] + [0.0] * 59]  # sold once, on the first day, then never again
    history = table(rows)
    fc = GradientBoosting(max_iter=10).forecast(history, horizon=7, quantiles=(0.1, 0.9))
    assert fc.method == "2 SKU(s) moving-average: the history holds no demand to train a model on"
    assert np.array_equal(fc.mean, MovingAverage().forecast(history, horizon=7, quantiles=(0.1, 0.9)).mean)


def test_a_model_fitted_once_forecasts_from_later_origins():
    history = weekly_table(98, n_skus=6)
    result = backtest(
        ["gradient-boosting"],
        history,
        horizon=7,
        origins=3,
        refit="once",
        params={"gradient-boosting": {"max_iter": 30}},
    )
    (row,) = result.scores.rows
    assert row[12] is None and row[1] < 0.1
