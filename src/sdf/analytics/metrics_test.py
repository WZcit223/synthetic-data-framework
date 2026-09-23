"""Tests for the shared forecast error metrics."""

from __future__ import annotations

import json

import pytest

from .metrics import bias, mae, mape, pct, rmse, wape


def test_basic_metrics():
    actuals, preds = [10.0, 20.0, 30.0], [12.0, 18.0, 33.0]
    assert mae(actuals, preds) == pytest.approx(7 / 3)
    assert rmse(actuals, preds) == pytest.approx(((4 + 4 + 9) / 3) ** 0.5)
    assert bias(actuals, preds) == pytest.approx(1.0)
    assert mape(actuals, preds) == pytest.approx((0.2 + 0.1 + 0.1) / 3)
    assert wape(actuals, preds) == pytest.approx(7 / 60)


def test_mape_counts_only_days_with_a_positive_actual():
    """The old backtest divided by all days; zero days must leave the count too."""
    actuals = [0.0, 10.0, 0.0, 10.0]
    preds = [5.0, 5.0, 5.0, 5.0]
    assert mape(actuals, preds) == pytest.approx(0.5)  # not 0.25
    assert wape(actuals, preds) == pytest.approx(20 / 20)


def test_undefined_percentages_are_none_and_json_safe():
    assert mape([0.0, 0.0], [1.0, 2.0]) is None
    assert wape([0.0, 0.0], [1.0, 2.0]) is None
    assert pct(None) is None and pct(0.12345) == 12.35
    assert json.dumps({"mape": pct(mape([0.0], [1.0]))}) == '{"mape": null}'


def test_mismatched_or_empty_input_raises():
    with pytest.raises(ValueError, match="differ in length"):
        mae([1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="at least one point"):
        mae([], [])
