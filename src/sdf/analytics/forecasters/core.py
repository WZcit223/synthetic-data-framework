"""The forecaster contract: fit on a history, forecast every SKU's next days with quantiles.

A forecaster sees a ``DemandTable`` (per-SKU daily demand on a dense day axis)
and returns, for each SKU and each of the ``horizon`` days after the history's
last day, a mean and the requested quantiles. It never sees a day after the
history it is given. The contract is ``docs/refactor/algorithms/interfaces.md`` §1.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Protocol, Self

import numpy as np

from sdf.analytics.demand import DemandTable

MAX_QUANTILES = 9


@dataclass(frozen=True)
class ForecasterInfo:
    name: str  # lower-case words joined by dashes
    description: str
    requires: tuple[str, ...] = ()  # modules; missing ones list the forecaster as unavailable
    global_model: bool = False  # True: one model fitted over all SKUs; False: one per SKU


@dataclass(frozen=True)
class Forecast:
    forecaster: str
    origin: date  # the first forecast day: the day after the history's last day
    sku_ids: tuple[str, ...]  # the history's SKUs, in its order
    mean: np.ndarray  # float, SKUs × horizon, >= 0
    quantiles: dict[float, np.ndarray]  # level -> SKUs × horizon, >= 0, non-decreasing in level
    method: str = ""  # how the intervals were made, and what the registry's guard repaired

    @property
    def horizon(self) -> int:
        return int(self.mean.shape[1]) if self.mean.ndim == 2 else 0


class Forecaster(Protocol):
    info: ClassVar[ForecasterInfo]

    def fit(self, history: DemandTable) -> Self: ...

    def forecast(self, history: DemandTable, *, horizon: int, quantiles: Sequence[float]) -> Forecast: ...


class TrueDistribution(Protocol):
    """The exact distribution of demand a benchmark drew from (``sdf.simulation.benchmark.TrueDemand``)."""

    def mean(self, day: date) -> np.ndarray: ...  # over the benchmark's SKUs, in its order

    def quantiles(self, day: date, levels: Sequence[float]) -> dict[float, np.ndarray]: ...


def check_quantiles(quantiles: Sequence[float]) -> tuple[float, ...]:
    """The levels as a sorted tuple; ``ValueError`` naming the problem otherwise."""
    levels = tuple(quantiles)
    if not levels:
        raise ValueError("quantiles must name at least one level")
    if len(levels) > MAX_QUANTILES:
        raise ValueError(f"at most {MAX_QUANTILES} quantiles, got {len(levels)}")
    for q in levels:
        if isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(q) or not 0 < q < 1:
            raise ValueError(f"quantile levels must be numbers strictly between 0 and 1, got {q!r}")
    if len(set(levels)) != len(levels):
        raise ValueError(f"quantile levels must be distinct, got {list(levels)}")
    if list(levels) != sorted(levels):
        raise ValueError(f"quantile levels must be sorted, got {list(levels)}")
    return tuple(float(q) for q in levels)


def matrix(history: DemandTable) -> np.ndarray:
    """The history as a float array, SKUs × days, in the table's SKU order."""
    if not history.series:
        return np.empty((0, len(history.days)))
    return np.array([history.series[k] for k in history.series], dtype=float)
