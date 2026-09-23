"""Tests for the AR + seasonal OLS forecaster."""

from __future__ import annotations

from .forecast import backtest, seasonal_naive
from .models import seasonal_linear


def test_model_beats_seasonal_naive_on_trend_plus_season():
    # Model beats seasonal-naive on a clean trend+season series.
    vals = [10 + 0.8 * i + [10, 12, 9, 11, 13, 8, 3][i % 7] for i in range(120)]
    assert (
        backtest(vals, seasonal_linear(7), test_len=21)["MAE"] < backtest(vals, seasonal_naive(7), test_len=21)["MAE"]
    )


def test_rank_deficiency_is_reported():
    from .models import fit_weights_with_rank

    trend = [10.0 + 0.5 * i + [0, 3, 1, 4, 2, 6, 5][i % 7] + (i * 7 % 5) for i in range(60)]
    _, deficient = fit_weights_with_rank(trend, 7)
    assert deficient is False
    weights, deficient = fit_weights_with_rank([4.0] * 30, 7)  # constant: lags duplicate the intercept
    assert deficient is True and len(weights) == 7 + 3
