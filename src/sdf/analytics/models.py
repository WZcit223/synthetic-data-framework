"""Phase 3 forecasting model: seasonal linear regression.

A genuine model (not a baseline): it fits demand as

    y_i = w0 + w_trend·i + Σ_d w_d · [ (i mod period) == d ]

by ordinary least squares, solved with ``numpy.linalg.lstsq`` on the design
matrix itself (never on the normal equations ``XᵀX``, which square the condition
number and hide the rank). It captures **trend + seasonality** together, which is what lets it
beat the naive/seasonal-naive baselines when both signals are present.

It plugs into the same `backtest`/`compare_models` harness as the baselines, and
into TSTR validation (`validation/tstr.py`). ALGORITHM-HOOK: DeepAR / TFT / LightGBM
are the next rung — same harness scores them.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def _design_row(i: int, period: int, lag1: float, lagp: float) -> list[float]:
    """Features: intercept, trend, day-of-cycle dummies, lag-1, lag-period."""
    d = i % period
    return [1.0, float(i)] + [1.0 if d == k else 0.0 for k in range(1, period)] + [lag1, lagp]


def _design(values: list[float], period: int) -> tuple[np.ndarray, np.ndarray]:
    rows = [_design_row(i, period, values[i - 1], values[i - period]) for i in range(period, len(values))]
    X = np.asarray(rows, dtype=float).reshape(-1, period + 3)  # intercept + trend + (period-1) dummies + 2 lags
    y = np.asarray(values[period:], dtype=float)
    return X, y


def fit_weights_with_rank(values: list[float], period: int) -> tuple[list[float], bool]:
    """Fit the AR+seasonal OLS weights; also say whether the design was rank deficient.

    Rank deficient means some feature is (numerically) a combination of the
    others, e.g. a lag column identical to a dummy on a short window. The
    minimum-norm solution is returned in that case, and the flag lets callers
    report that the model used fewer independent inputs than it has.
    """
    X, y = _design(values, period)
    if X.shape[0] == 0:
        return [0.0] * X.shape[1], True
    w, _residuals, rank, _singular = np.linalg.lstsq(X, y, rcond=None)
    return [float(v) for v in w], int(rank) < X.shape[1]


def fit_weights(values: list[float], period: int) -> list[float]:
    """Public: fit the AR+seasonal OLS weights on a series (for TSTR)."""
    return fit_weights_with_rank(values, period)[0]


def predict_at(weights: list[float], i: int, period: int, lag1: float, lagp: float) -> float:
    """Public: predict index ``i`` given fitted weights and the two lag values."""
    row = _design_row(i, period, lag1, lagp)
    return max(0.0, sum(a * b for a, b in zip(row, weights)))


def seasonal_linear(period: int = 7) -> Callable[[list[float]], float]:
    """History→next-value autoregressive-seasonal forecaster."""

    def f(h: list[float]) -> float:
        n = len(h)
        if n < 2 * period + 2:
            return h[-1] if h else 0.0
        w = fit_weights(h, period)
        row = _design_row(n, period, h[n - 1], h[n - period])
        return max(0.0, sum(a * b for a, b in zip(row, w)))

    f.__name__ = f"seasonal_linear{period}"
    return f
