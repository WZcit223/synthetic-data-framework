"""The built-in forecasters: the one-step models of ``sdf.analytics.forecast``, per SKU, with intervals.

Each built-in turns its point model into a path over the horizon the way the model
implies: ``seasonal-naive`` repeats the last cycle, ``seasonal-linear`` feeds its
own predictions forward, and the others hold their value. The intervals come from
the model's own errors: for every SKU, the model forecasts from each of the last
56 days of the history it is given and is compared with what followed, step by
step. The empirical quantiles of those errors, added to the point forecast and
floored at 0, are the forecast's quantiles. When a step has fewer than 14 errors
(a short history), every SKU borrows the errors of all SKUs, each scaled by its
own SKU's mean demand. All SKUs share one day axis, so every step is computed for
all SKUs at once. The contract is ``docs/refactor/algorithms/interfaces.md`` §1.3.

ALGORITHM-HOOK[C1]: these are the reference points a real forecaster must beat on
the same backtest (``backtest``); a gradient-boosted or deep model plugs in beside them.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import ClassVar, Self

import numpy as np

from sdf.analytics.demand import DemandTable
from .core import Forecast, ForecasterInfo, check_quantiles, matrix

ERROR_WINDOW = 56  # the last days of the history whose forecasts size the intervals
MIN_ERRORS = 14  # fewer errors at a step: every SKU borrows the pooled, scaled errors of all SKUs


class _PointModel:
    """A per-SKU point model with empirical-error intervals; a subclass supplies ``_paths``."""

    info: ClassVar[ForecasterInfo]
    min_origin: int = 1  # the fewest days of history a path can start from

    def fit(self, history: DemandTable) -> Self:
        return self  # the built-ins learn from the history they forecast from; nothing to keep

    def forecast(self, history: DemandTable, *, horizon: int, quantiles: Sequence[float]) -> Forecast:
        levels = check_quantiles(quantiles)
        if horizon < 1:
            raise ValueError(f"horizon must be at least 1, got {horizon}")
        if not history.days:
            raise ValueError("the history has no day to forecast from")
        y = matrix(history)
        n_skus, n = y.shape
        err_origins = np.arange(max(self.min_origin, n - ERROR_WINDOW), n)
        paths = self._paths(y, np.append(err_origins, n), horizon)  # SKUs × origins × horizon
        point = paths[:, -1, :]
        scale = np.maximum(y.mean(axis=1), 1e-9)
        q = {lv: point.copy() for lv in levels}
        pooled = empty = False
        for k in range(horizon):
            usable = err_origins + k < n
            errors = y[:, err_origins[usable] + k] - paths[:, : len(err_origins), k][:, usable]  # SKUs × errors
            if errors.shape[1] >= MIN_ERRORS:
                offsets = np.quantile(errors, levels, axis=1)  # levels × SKUs
            elif errors.size:
                pooled = True
                offsets = np.quantile((errors / scale[:, None]).ravel(), levels)[:, None] * scale[None, :]
            else:
                empty = True
                continue
            for j, lv in enumerate(levels):
                q[lv][:, k] += offsets[j]
        method = f"empirical errors of the last {ERROR_WINDOW} days"
        if pooled:
            method += f"; fewer than {MIN_ERRORS} errors at some days ahead, so all SKUs' scaled errors were pooled"
        if empty:
            method += "; no error to size some intervals, which have zero width"
        return Forecast(
            forecaster=self.info.name,
            origin=history.days[-1] + timedelta(days=1),
            sku_ids=tuple(history.series),
            mean=np.maximum(point, 0.0),
            quantiles={lv: np.maximum(arr, 0.0) for lv, arr in q.items()},
            method=method,
        )

    def _paths(self, y: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
        """Point paths, SKUs × origins × horizon: the forecast of days ``o .. o+horizon-1`` from ``y[:, :o]``."""
        raise NotImplementedError


def _hold(level: np.ndarray, horizon: int) -> np.ndarray:
    """A level per SKU and origin, held over the horizon."""
    return np.repeat(level[:, :, None], horizon, axis=2)


class MeanForecaster(_PointModel):
    info: ClassVar[ForecasterInfo] = ForecasterInfo("mean", "The mean of the whole history, held over the horizon")

    def _paths(self, y: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
        cs = np.cumsum(y, axis=1)
        return _hold(cs[:, origins - 1] / origins, horizon)


class NaiveForecaster(_PointModel):
    info: ClassVar[ForecasterInfo] = ForecasterInfo("naive", "The last day's demand, held over the horizon")

    def _paths(self, y: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
        return _hold(y[:, origins - 1], horizon)


class MovingAverage(_PointModel):
    info: ClassVar[ForecasterInfo] = ForecasterInfo(
        "moving-average", "The mean of the last `window` days, held over the horizon"
    )
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {"window": (1, 365)}

    def __init__(self, window: int = 7) -> None:
        self.window = window

    def _paths(self, y: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
        cs = np.concatenate([np.zeros((len(y), 1)), np.cumsum(y, axis=1)], axis=1)
        start = np.maximum(origins - self.window, 0)
        return _hold((cs[:, origins] - cs[:, start]) / (origins - start), horizon)


class SeasonalNaive(_PointModel):
    info: ClassVar[ForecasterInfo] = ForecasterInfo(
        "seasonal-naive", "The same day one `period` earlier: the last cycle, repeated"
    )
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {"period": (1, 365)}

    def __init__(self, period: int = 7) -> None:
        self.period = period

    def _paths(self, y: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
        k = np.arange(horizon)
        idx = origins[:, None] - self.period + (k[None, :] % self.period)
        short = origins < self.period  # less than one cycle: hold the last day, as seasonal naive does
        idx = np.where(short[:, None], (origins - 1)[:, None], idx)
        return y[:, idx]


class SeasonalLinear(_PointModel):
    """``sdf.analytics.models.seasonal_linear`` per SKU, fitted once on the history and fed forward.

    The features are those of ``models._design_row``: an intercept, the day index,
    one dummy per day of the cycle but the first, and the lags 1 and ``period``.
    """

    info: ClassVar[ForecasterInfo] = ForecasterInfo(
        "seasonal-linear",
        "Least squares on trend, day of the cycle and the lags 1 and `period`, fed forward over the horizon",
    )
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {"period": (2, 365)}

    def __init__(self, period: int = 7) -> None:
        self.period = period

    @property
    def min_origin(self) -> int:  # type: ignore[override]
        return self.period

    def _paths(self, y: np.ndarray, origins: np.ndarray, horizon: int) -> np.ndarray:
        p = self.period
        n = int(origins.max())
        if n < 2 * p + 2:  # too short to fit: hold the last day, as the one-step model does
            return _hold(y[:, origins - 1], horizon)
        w = self._weights(y[:, :n])  # SKUs × (p + 3)
        dummies = np.concatenate([np.zeros((len(y), 1)), w[:, 2 : p + 1]], axis=1)  # SKUs × p
        buf = np.zeros((len(y), len(origins), p + horizon))
        buf[:, :, :p] = y[:, origins[:, None] - p + np.arange(p)[None, :]]
        for k in range(horizon):
            i = origins + k
            pred = (
                w[:, 0:1]
                + w[:, 1:2] * i[None, :]
                + dummies[:, i % p]
                + w[:, p + 1 : p + 2] * buf[:, :, p + k - 1]
                + w[:, p + 2 : p + 3] * buf[:, :, k]
            )
            buf[:, :, p + k] = np.maximum(pred, 0.0)
        return buf[:, :, p:]

    def _weights(self, y: np.ndarray) -> np.ndarray:
        """Least squares per SKU on ``models._design_row``'s features; the minimum-norm solution when rank deficient."""
        p = self.period
        n = y.shape[1]
        i = np.arange(p, n)
        base = np.column_stack([np.ones(len(i)), i, (i[:, None] % p == np.arange(1, p)[None, :]).astype(float)])
        out = np.zeros((len(y), p + 3))
        for s, v in enumerate(y):
            x = np.column_stack([base, v[i - 1], v[i - p]])
            out[s] = np.linalg.lstsq(x, v[p:], rcond=None)[0]
        return out
