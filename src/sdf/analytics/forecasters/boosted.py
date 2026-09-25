"""Gradient-boosted global forecasters: one model over every SKU, with an interval from quantile models.

The features of a SKU at an origin come from the days before the origin only: the
demand on the last day and on the 7th and 14th last, the means of the last 7 and
28 days, the share of zero days in the last 28, the weekday of the target day and
the days ahead. One model covers every day of the horizon ("direct" forecasting:
the days ahead are a feature, so no forecast is fed back as an input). The mean
comes from a model with Poisson loss, each quantile from a model with quantile
loss. The models are fitted, for a horizon and a set of levels, the first time
``forecast`` is asked for them, and kept until the next ``fit``. A SKU with less
than ``min_history`` days since its first sale gets the ``moving-average``
forecast instead, and the forecast's ``method`` counts them. The contract is
``docs/refactor/algorithms/interfaces.md`` §4.1.

ALGORITHM-HOOK[C1]: a deep global model (DeepAR, Temporal Fusion Transformer)
trained on the full dataset plugs in beside this one, on the same backtest.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any, ClassVar, Self

import numpy as np

from sdf.analytics.demand import DemandTable
from .builtin import MovingAverage
from .core import Forecast, ForecasterInfo, check_quantiles, matrix

WINDOW = 28  # the days of history the features read: the first origin a SKU is modelled from
MAX_ROWS = 60_000  # training rows (SKU, origin, days ahead) drawn at most; more cost time and add little
FEATURES = ("last_1", "last_7", "last_14", "mean_7", "mean_28", "zero_share_28", "weekday", "days_ahead")


def features(y: np.ndarray, weekday0: int, sku: np.ndarray, origin: np.ndarray, ahead: np.ndarray) -> np.ndarray:
    """The feature rows for SKU indices ``sku`` forecast from ``origin`` (the first day not seen) ``ahead`` days out.

    ``y`` is SKUs × days; ``weekday0`` the weekday of its first day (Monday 0). Every
    value is read from ``y[:, :origin]``: an origin needs at least ``WINDOW`` days before it.
    """
    cs = np.concatenate([np.zeros((len(y), 1)), np.cumsum(y, axis=1)], axis=1)
    zeros = np.concatenate([np.zeros((len(y), 1)), np.cumsum(y == 0, axis=1)], axis=1)
    return np.column_stack(
        [
            y[sku, origin - 1],
            y[sku, origin - 7],
            y[sku, origin - 14],
            (cs[sku, origin] - cs[sku, origin - 7]) / 7,
            (cs[sku, origin] - cs[sku, origin - 28]) / 28,
            (zeros[sku, origin] - zeros[sku, origin - 28]) / 28,
            (weekday0 + origin + ahead - 1) % 7,
            ahead,
        ]
    ).astype(float)


def first_sale(y: np.ndarray) -> np.ndarray:
    """Each SKU's first day with demand; the number of days for a SKU that never sold."""
    sold = y > 0
    return np.where(sold.any(axis=1), sold.argmax(axis=1), y.shape[1])


class _Boosted:
    """The design both back ends share; a subclass supplies ``_model(loss, quantile)``."""

    info: ClassVar[ForecasterInfo]
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {
        "max_iter": (10, 1000),
        "learning_rate": (0.01, 1.0),
        "max_leaf_nodes": (2, 255),
        "min_history": (28, 365),
        "seed": (0, None),
    }

    def __init__(
        self,
        max_iter: int = 200,
        learning_rate: float = 0.1,
        max_leaf_nodes: int = 31,
        min_history: int = 28,
        seed: int = 0,
    ) -> None:
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.max_leaf_nodes = max_leaf_nodes
        self.min_history = min_history
        self.seed = seed
        self._history: DemandTable | None = None
        self._models: dict[Any, Any] = {}  # (horizon, None) -> the mean model; (horizon, level) -> a quantile model
        self.fits = 0  # models fitted since construction: what the cache saved is observable

    def fit(self, history: DemandTable) -> Self:
        """Keep ``history`` to train on; the models are fitted when ``forecast`` first needs them."""
        self._history = history
        self._models = {}
        return self

    def forecast(self, history: DemandTable, *, horizon: int, quantiles: Sequence[float]) -> Forecast:
        levels = check_quantiles(quantiles)
        if horizon < 1:
            raise ValueError(f"horizon must be at least 1, got {horizon}")
        if not history.days:
            raise ValueError("the history has no day to forecast from")
        if self._history is None:
            self.fit(history)
        y = matrix(history)
        n_skus, n = y.shape
        modelled = (n - first_sale(y) >= self.min_history) & (n >= WINDOW)
        short = int((~modelled).sum())
        fallback = None
        if short:
            fallback = MovingAverage().forecast(history, horizon=horizon, quantiles=levels)
        mean = np.zeros((n_skus, horizon))
        q = {lv: np.zeros((n_skus, horizon)) for lv in levels}
        trained = self._train(horizon, levels) if modelled.any() else None
        if trained is None:
            modelled[:] = False
            short = n_skus
            fallback = fallback or MovingAverage().forecast(history, horizon=horizon, quantiles=levels)
        else:
            sku = np.repeat(np.flatnonzero(modelled), horizon)
            ahead = np.tile(np.arange(1, horizon + 1), int(modelled.sum()))
            x = features(y, history.days[0].weekday(), sku, np.full(len(sku), n), ahead)
            mean[modelled] = trained[None].predict(x).reshape(-1, horizon)
            for lv in levels:
                q[lv][modelled] = trained[lv].predict(x).reshape(-1, horizon)
        if fallback is not None:
            mean[~modelled] = fallback.mean[~modelled]
            for lv in levels:
                q[lv][~modelled] = fallback.quantiles[lv][~modelled]
        method = f"one {self.info.name} model over {n_skus - short} SKU(s), quantile loss per level"
        if short:
            method += f"; {short} SKU(s) with less than {self.min_history} days since their first sale: moving-average"
        return Forecast(
            forecaster=self.info.name,
            origin=history.days[-1] + timedelta(days=1),
            sku_ids=tuple(history.series),
            mean=np.maximum(mean, 0.0),
            quantiles={lv: np.maximum(arr, 0.0) for lv, arr in q.items()},
            method=method,
        )

    def _train(self, horizon: int, levels: tuple[float, ...]) -> dict[Any, Any] | None:
        """The mean model and one model per level for ``horizon``, fitted on the kept history once each; None
        when the history holds no training row."""
        missing = [lv for lv in (None, *levels) if (horizon, lv) not in self._models]
        if missing:
            data = self._rows(horizon)
            if data is None:
                return None
            x, target = data
            for lv in missing:
                model = self._model("poisson" if lv is None else "quantile", lv)
                model.fit(x, target)
                self._models[horizon, lv] = model
                self.fits += 1
        return {lv: self._models[horizon, lv] for lv in (None, *levels)}

    def _rows(self, horizon: int) -> tuple[np.ndarray, np.ndarray] | None:
        """Training rows from the kept history: every (SKU, origin, days ahead) whose features and target
        lie inside a modelled SKU's selling life, at most ``MAX_ROWS`` of them, drawn with ``seed``."""
        history = self._history
        y = matrix(history)
        n_skus, n = y.shape
        first = first_sale(y)
        eligible = np.flatnonzero(n - first >= self.min_history)
        sku, origin, ahead = [], [], []
        for s in eligible:
            origins = np.arange(max(WINDOW, first[s] + WINDOW), n)
            for h in range(1, horizon + 1):
                o = origins[origins + h - 1 < n]
                sku.append(np.full(len(o), s))
                origin.append(o)
                ahead.append(np.full(len(o), h))
        if not sku or not sum(len(o) for o in origin):
            return None
        sku, origin, ahead = np.concatenate(sku), np.concatenate(origin), np.concatenate(ahead)
        if len(sku) > MAX_ROWS:
            pick = np.sort(np.random.default_rng(self.seed).choice(len(sku), MAX_ROWS, replace=False))
            sku, origin, ahead = sku[pick], origin[pick], ahead[pick]
        x = features(y, history.days[0].weekday(), sku, origin, ahead)
        return x, y[sku, origin + ahead - 1]

    def _model(self, loss: str, quantile: float | None) -> Any:
        raise NotImplementedError


class GradientBoosting(_Boosted):
    info: ClassVar[ForecasterInfo] = ForecasterInfo(
        "gradient-boosting",
        "One gradient-boosted model over all SKUs (scikit-learn): recent demand, weekday and days ahead;"
        " Poisson loss for the mean, quantile loss for the interval",
        global_model=True,
    )

    def _model(self, loss: str, quantile: float | None) -> Any:
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(
            loss=loss,
            quantile=quantile,
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_leaf_nodes=self.max_leaf_nodes,
            early_stopping=False,
            random_state=self.seed,
        )


class LightGBM(_Boosted):
    info: ClassVar[ForecasterInfo] = ForecasterInfo(
        "lightgbm",
        "The gradient-boosting design on LightGBM, for data too large for scikit-learn's model",
        requires=("lightgbm",),
        global_model=True,
    )

    def _model(self, loss: str, quantile: float | None) -> Any:
        import lightgbm

        return lightgbm.LGBMRegressor(
            objective=loss,
            alpha=quantile if quantile is not None else 0.9,
            n_estimators=self.max_iter,
            learning_rate=self.learning_rate,
            num_leaves=self.max_leaf_nodes,
            random_state=self.seed,
            deterministic=True,
            n_jobs=1,
            verbose=-1,
        )
