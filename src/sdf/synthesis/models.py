"""Phase 3 forecasting model: seasonal linear regression (dependency-free).

A genuine model (not a baseline): it fits demand as

    y_i = w0 + w_trend·i + Σ_d w_d · [ (i mod period) == d ]

by ordinary least squares (normal equations solved with Gaussian elimination in
pure Python). It captures **trend + seasonality** together, which is what lets it
beat the naive/seasonal-naive baselines when both signals are present.

It plugs into the same `backtest`/`compare_models` harness as the baselines, and
into TSTR validation (`synthesis/tstr.py`). ALGORITHM-HOOK: DeepAR / TFT / LightGBM
are the next rung — same harness scores them.
"""

from __future__ import annotations

from typing import Callable, List


def _solve(A: List[List[float]], b: List[float]) -> List[float]:
    """Solve A x = b via Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            continue
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        M[col] = [v / pv for v in M[col]]
        for r in range(n):
            if r != col and abs(M[r][col]) > 1e-12:
                f = M[r][col]
                M[r] = [a - f * b_ for a, b_ in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]


def _design_row(i: int, period: int, lag1: float, lagp: float) -> List[float]:
    """Features: intercept, trend, day-of-cycle dummies, lag-1, lag-period."""
    d = i % period
    return ([1.0, float(i)]
            + [1.0 if d == k else 0.0 for k in range(1, period)]
            + [lag1, lagp])


def _fit(values: List[float], period: int) -> List[float]:
    p = period + 3                      # intercept + trend + (period-1) dummies + 2 lags
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for i in range(period, len(values)):
        row = _design_row(i, period, values[i - 1], values[i - period])
        for a in range(p):
            xty[a] += row[a] * values[i]
            for b in range(p):
                xtx[a][b] += row[a] * row[b]
    # Ridge nudge keeps the system solvable on short/degenerate windows.
    for a in range(p):
        xtx[a][a] += 1e-6
    return _solve(xtx, xty)


def fit_weights(values: List[float], period: int) -> List[float]:
    """Public: fit the AR+seasonal OLS weights on a series (for TSTR)."""
    return _fit(values, period)


def predict_at(weights: List[float], i: int, period: int,
               lag1: float, lagp: float) -> float:
    """Public: predict index ``i`` given fitted weights and the two lag values."""
    row = _design_row(i, period, lag1, lagp)
    return max(0.0, sum(a * b for a, b in zip(row, weights)))


def seasonal_linear(period: int = 7) -> Callable[[List[float]], float]:
    """History→next-value autoregressive-seasonal forecaster."""
    def f(h: List[float]) -> float:
        n = len(h)
        if n < 2 * period + 2:
            return h[-1] if h else 0.0
        w = _fit(h, period)
        row = _design_row(n, period, h[n - 1], h[n - period])
        return max(0.0, sum(a * b for a, b in zip(row, w)))
    f.__name__ = f"seasonal_linear{period}"
    return f
