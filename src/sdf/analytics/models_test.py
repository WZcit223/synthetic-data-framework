"""Tests for the AR + seasonal OLS forecaster."""

from __future__ import annotations

from .forecast import backtest, seasonal_naive
from .models import seasonal_linear


def test_model_beats_seasonal_naive_on_trend_plus_season():
    # Model beats seasonal-naive on a clean trend+season series.
    vals = [10 + 0.8 * i + [10, 12, 9, 11, 13, 8, 3][i % 7] for i in range(120)]
    assert backtest(vals, seasonal_linear(7), 21)["MAE"] < backtest(vals, seasonal_naive(7), 21)["MAE"]
