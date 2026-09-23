"""Forecast error metrics, implemented once and shared by the backtest and TSTR.

Conventions (documented in ``docs/VALIDATION.md`` next to every table):

- ``mae``  — mean absolute error.
- ``rmse`` — root mean squared error.
- ``bias`` — mean of ``prediction − actual`` (positive = over-forecast).
- ``mape`` — mean of ``|error| / actual`` over the points whose actual is
  positive; points with a zero actual are left out of *both* the sum and the
  count. ``None`` when no actual is positive.
- ``wape`` — ``Σ|error| / Σactual`` over all points: every point counts, zero
  actuals included, and nothing is divided by zero. ``None`` when the actuals
  sum to zero.

``mape`` and ``wape`` are fractions (0.25 = 25 %). They return ``None`` rather
than ``NaN`` so results serialise to JSON ``null``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _pairs(actuals: Sequence[float], preds: Sequence[float]) -> list[tuple[float, float]]:
    if len(actuals) != len(preds):
        raise ValueError(f"actuals and preds differ in length ({len(actuals)} vs {len(preds)})")
    if not actuals:
        raise ValueError("metrics need at least one point")
    return list(zip(actuals, preds))


def mae(actuals: Sequence[float], preds: Sequence[float]) -> float:
    pairs = _pairs(actuals, preds)
    return sum(abs(p - a) for a, p in pairs) / len(pairs)


def rmse(actuals: Sequence[float], preds: Sequence[float]) -> float:
    pairs = _pairs(actuals, preds)
    return math.sqrt(sum((p - a) ** 2 for a, p in pairs) / len(pairs))


def bias(actuals: Sequence[float], preds: Sequence[float]) -> float:
    pairs = _pairs(actuals, preds)
    return sum(p - a for a, p in pairs) / len(pairs)


def mape(actuals: Sequence[float], preds: Sequence[float]) -> float | None:
    positive = [(a, p) for a, p in _pairs(actuals, preds) if a > 0]
    if not positive:
        return None
    return sum(abs(p - a) / a for a, p in positive) / len(positive)


def wape(actuals: Sequence[float], preds: Sequence[float]) -> float | None:
    pairs = _pairs(actuals, preds)
    total = sum(a for a, _ in pairs)
    if total <= 0:
        return None
    return sum(abs(p - a) for a, p in pairs) / total


def pct(value: float | None, digits: int = 2) -> float | None:
    """A fraction as a rounded percentage, keeping ``None``."""
    return None if value is None else round(100 * value, digits)
