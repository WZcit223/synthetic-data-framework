"""The probabilistic backtest: every forecaster, from the same rolling origins, scored on the same days.

From each origin a forecaster sees only the days before it and forecasts the next
``horizon`` days of every SKU; the forecasts are scored against what happened
(WAPE, bias, pinball loss, both interval coverages, width) and against seasonal
naive on the same points. With a benchmark's exact distribution, a
``true-distribution`` row gives the same scores for the best forecast there is.
The contract is ``docs/refactor/algorithms/interfaces.md`` §2.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from sdf.analytics.demand import DemandTable
from sdf.foundation.tables import DatasetInfo, Field, Table
from .builtin import SeasonalNaive
from .core import TrueDistribution, check_quantiles, matrix
from .registry import ForecasterRegistry, default_forecasters

MIN_HISTORY = 28  # days of history before the first origin
MAX_HORIZON = 56
MAX_ORIGINS = 12
MAX_FORECASTERS = 6
MAX_BACKTEST_SECONDS = 30.0  # a request's budget: forecasters not started (or finished) by then are "not run" rows
TRUE_DISTRIBUTION = "true-distribution"
REFITS = ("each-origin", "once")

_METRICS = (
    Field("wape", "WAPE", "measure", unit="share", aggregate="mean"),
    Field("relative_wape", "WAPE relative to seasonal naive", "measure", unit="share", aggregate="mean"),
    Field("bias", "Bias", "measure", unit="share", aggregate="mean"),
    Field("mae", "Mean absolute error", "measure", unit="units", aggregate="mean"),
    Field("pinball", "Pinball loss", "measure", unit="units", aggregate="mean"),
    Field("coverage_open", "Coverage, bounds excluded", "measure", unit="share", aggregate="mean"),
    Field("coverage_closed", "Coverage, bounds included", "measure", unit="share", aggregate="mean"),
    Field("nominal", "Nominal coverage", "measure", unit="share", aggregate="mean"),
    Field("width", "Interval width", "measure", unit="units", aggregate="mean"),
)

SCORES_INFO = DatasetInfo(
    name="forecast-scores",
    label="Forecast scores",
    description="Each forecaster's errors over every SKU, origin and day ahead, against seasonal naive",
    fields=(
        Field("forecaster", "Forecaster", "dimension"),
        *_METRICS,
        Field("seconds", "Run time", "measure", unit="s", aggregate="sum"),
        Field("method", "Method", "dimension"),
        Field("error", "Error", "dimension"),
    ),
)

BY_HORIZON_INFO = DatasetInfo(
    name="by-horizon",
    label="Forecast scores by days ahead",
    description="Each forecaster's errors at each number of days ahead, over every SKU and origin",
    fields=(
        Field("forecaster", "Forecaster", "dimension"),
        Field("days_ahead", "Days ahead", "measure", unit="days", aggregate="min"),
        *_METRICS,
    ),
)


def quantile_field(level: float) -> str:
    """The field holding one quantile: 0.1 -> "q10", 0.025 -> "q2_5"."""
    return "q" + f"{level * 100:g}".replace(".", "_")


def forecasts_info(levels: Sequence[float]) -> DatasetInfo:
    """The ``forecasts`` table: every SKU and day of the last origin, per forecaster, with its quantiles."""
    return DatasetInfo(
        name="forecasts",
        label="Forecasts at the last origin",
        description="Each forecaster's mean and quantiles for every SKU and day after the last origin, with the actual",
        fields=(
            Field("sku_id", "SKU", "dimension"),
            Field("date", "Date", "time"),
            Field("forecaster", "Forecaster", "dimension"),
            Field("actual", "Actual", "measure", unit="units", aggregate="sum"),
            Field("mean", "Mean forecast", "measure", unit="units", aggregate="sum"),
            *(
                Field(quantile_field(lv), f"Quantile {lv * 100:g} %", "measure", unit="units", aggregate="sum")
                for lv in levels
            ),
        ),
    )


@dataclass(frozen=True)
class BacktestResult:
    scores: Table  # "forecast-scores": one row per forecaster, then the true distribution when known
    by_horizon: Table  # "by-horizon": one row per forecaster and day ahead
    forecasts: Table  # "forecasts": the last origin only, for charts
    origins: tuple[date, ...]  # the first forecast day of each origin


def backtest(
    forecasters: Sequence[str],
    history: DemandTable,
    *,
    horizon: int = 14,
    origins: int = 4,
    step: int = 7,
    quantiles: Sequence[float] = (0.1, 0.5, 0.9),
    params: Mapping[str, Mapping[str, Any]] | None = None,
    refit: str = "each-origin",
    truth: TrueDistribution | None = None,
    deadline: float | None = None,
    registry: ForecasterRegistry | None = None,
) -> BacktestResult:
    """Score ``forecasters`` on ``history`` from ``origins`` rolling origins ``step`` days apart.

    Raises ``KeyError`` for an unknown or unavailable forecaster and ``ValueError`` for a
    request that cannot run (a bad parameter, horizon, origin count or quantile, or a
    history too short); both before any forecaster runs. A forecaster that raises or
    returns what the guard refuses becomes an error row. ``deadline`` (a
    ``time.monotonic()`` instant) is checked before each forecaster and each origin.
    """
    reg = registry if registry is not None else default_forecasters()
    names, levels, params = _checked_request(reg, forecasters, horizon, origins, step, quantiles, params, refit)
    y = matrix(history)
    n = len(history.days)
    need = horizon + (origins - 1) * step + MIN_HISTORY
    if n < need:
        raise ValueError(
            f"the history has {n} days; horizon {horizon}, {origins} origins {step} days apart and "
            f"{MIN_HISTORY} days before the first need {need}"
        )
    if not history.series:
        raise ValueError("the history has no SKU")
    starts = [n - horizon - (origins - 1 - j) * step for j in range(origins)]
    actual = np.stack([y[:, o : o + horizon] for o in starts])  # origins × SKUs × horizon
    reference = SeasonalNaive(7)
    ref_mean = np.stack(
        [reference.forecast(history.until(history.days[o]), horizon=horizon, quantiles=levels).mean for o in starts]
    )
    ref_abs = np.abs(actual - ref_mean)

    score_rows: list[tuple[Any, ...]] = []
    horizon_rows: list[tuple[Any, ...]] = []
    last_rows: list[tuple[Any, ...]] = []
    days_last = history.days[starts[-1] : starts[-1] + horizon]
    skus = tuple(history.series)
    for name in names:
        started = time.monotonic()
        try:
            means, qs, method = _run(reg, name, params.get(name, {}), history, starts, horizon, levels, refit, deadline)
        except _NotRun as exc:
            score_rows.append(_error_row(name, str(exc), None if exc.started is None else time.monotonic() - started))
            continue
        except Exception as exc:  # one broken forecaster must not hide the others
            score_rows.append(_error_row(name, _reason(exc), time.monotonic() - started))
            continue
        seconds = time.monotonic() - started
        score_rows.append((name, *_metrics(actual, means, qs, levels, ref_abs), round(seconds, 4), method, None))
        horizon_rows += _by_horizon(name, actual, means, qs, levels, ref_abs)
        last_rows += _forecast_rows(name, skus, days_last, actual[-1], means[-1], {lv: q[-1] for lv, q in qs.items()})
    if truth is not None:
        means, qs = _truth(truth, history, starts, horizon, levels)
        method = "the exact distribution the benchmark drew from"
        score_rows.append((TRUE_DISTRIBUTION, *_metrics(actual, means, qs, levels, ref_abs), None, method, None))
        horizon_rows += _by_horizon(TRUE_DISTRIBUTION, actual, means, qs, levels, ref_abs)
        last_rows += _forecast_rows(
            TRUE_DISTRIBUTION, skus, days_last, actual[-1], means[-1], {lv: q[-1] for lv, q in qs.items()}
        )
    return BacktestResult(
        scores=Table(SCORES_INFO, score_rows),
        by_horizon=Table(BY_HORIZON_INFO, horizon_rows),
        forecasts=Table(forecasts_info(levels), last_rows),
        origins=tuple(history.days[o] for o in starts),
    )


class _NotRun(Exception):
    def __init__(self, message: str, started: float | None) -> None:
        super().__init__(message)
        self.started = started


def _checked_request(reg, forecasters, horizon, origins, step, quantiles, params, refit):
    names = list(forecasters)
    if not names:
        raise ValueError("forecasters must name at least one")
    if len(names) > MAX_FORECASTERS:
        raise ValueError(f"at most {MAX_FORECASTERS} forecasters, got {len(names)}")
    repeated = sorted({f for f in names if names.count(f) > 1})
    if repeated:
        raise ValueError(f"forecasters: each may appear once, repeated {repeated}")
    for name in names:
        reg.info(name)  # KeyError, with the unavailable reason, before any run
    for label, value, top in (
        ("horizon", horizon, MAX_HORIZON),
        ("origins", origins, MAX_ORIGINS),
        ("step", step, None),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or (top is not None and value > top):
            bound = f"from 1 to {top}" if top is not None else "at least 1"
            raise ValueError(f"{label} must be a whole number {bound}, got {value!r}")
    if refit not in REFITS:
        raise ValueError(f"refit must be one of {list(REFITS)}, got {refit!r}")
    levels = check_quantiles(quantiles)
    given = {k: dict(v) for k, v in (params or {}).items()}
    stray = sorted(set(given) - set(names))
    if stray:
        raise ValueError(f"params names forecasters not requested: {stray}")
    for name in names:
        reg.create(name, **given.get(name, {}))  # a bad parameter is the request's problem: refused now
    return names, levels, given


def _run(reg, name, params, history, starts, horizon, levels, refit, deadline):
    means, qs = [], {lv: [] for lv in levels}
    methods: list[str] = []
    model = None
    for j, o in enumerate(starts):
        if deadline is not None and time.monotonic() > deadline:
            word = "not run" if j == 0 else "not finished"
            raise _NotRun(f"{word}: the request's {MAX_BACKTEST_SECONDS:g} s were used", None if j == 0 else 0.0)
        past = history.until(history.days[o])
        if model is None or refit == "each-origin":
            model = reg.create(name, **params).fit(past)
        fc = reg.forecast(model, past, horizon=horizon, quantiles=levels)
        means.append(fc.mean)
        for lv in levels:
            qs[lv].append(fc.quantiles[lv])
        if fc.method and fc.method not in methods:
            methods.append(fc.method)
    return np.stack(means), {lv: np.stack(v) for lv, v in qs.items()}, "; ".join(methods)


def _truth(truth, history, starts, horizon, levels):
    means, qs = [], {lv: [] for lv in levels}
    cache: dict[date, tuple[np.ndarray, dict[float, np.ndarray]]] = {}  # overlapping origins share days
    for o in starts:
        days = history.days[o : o + horizon]
        for d in days:
            if d not in cache:
                cache[d] = (truth.mean(d), truth.quantiles(d, levels))
        means.append(np.stack([cache[d][0] for d in days], axis=1))
        per_day = [cache[d][1] for d in days]
        for lv in levels:
            qs[lv].append(np.stack([q[lv] for q in per_day], axis=1))
    return np.stack(means), {lv: np.stack(v) for lv, v in qs.items()}


def _metrics(actual, mean, qs, levels, ref_abs) -> tuple[Any, ...]:
    """The metric fields of §2.3 over every point of the arrays given (any shape, all alike)."""
    total = float(actual.sum())
    abs_err = np.abs(actual - mean)
    wape = float(abs_err.sum()) / total if total > 0 else None
    ref = float(ref_abs.sum())
    relative = float(abs_err.sum()) / ref if ref > 0 else None
    bias = float((mean - actual).sum()) / total if total > 0 else None
    mae = float(abs_err.mean())
    pinball = float(np.mean([np.maximum(lv * (actual - qs[lv]), (lv - 1) * (actual - qs[lv])).mean() for lv in levels]))
    cov_open = cov_closed = nominal = width = None
    if len(levels) >= 2:
        lo, hi = qs[levels[0]], qs[levels[-1]]
        cov_open = float(((actual > lo) & (actual < hi)).mean())
        cov_closed = float(((actual >= lo) & (actual <= hi)).mean())
        nominal = levels[-1] - levels[0]
        width = float((hi - lo).mean())
    return tuple(
        None if v is None else round(v, 4)
        for v in (wape, relative, bias, mae, pinball, cov_open, cov_closed, nominal, width)
    )


def _by_horizon(name, actual, means, qs, levels, ref_abs) -> list[tuple[Any, ...]]:
    return [
        (
            name,
            k + 1,
            *_metrics(actual[..., k], means[..., k], {lv: q[..., k] for lv, q in qs.items()}, levels, ref_abs[..., k]),
        )
        for k in range(actual.shape[-1])
    ]


def _forecast_rows(name, skus, days, actual, mean, qs) -> list[tuple[Any, ...]]:
    levels = sorted(qs)
    return [
        (
            sku,
            d.isoformat(),
            name,
            float(actual[i, k]),
            round(float(mean[i, k]), 4),
            *(round(float(qs[lv][i, k]), 4) for lv in levels),
        )
        for i, sku in enumerate(skus)
        for k, d in enumerate(days)
    ]


def _error_row(name: str, reason: str, seconds: float | None) -> tuple[Any, ...]:
    return (name, *(None,) * len(_METRICS), None if seconds is None else round(seconds, 4), None, reason)


def _reason(exc: Exception) -> str:
    text = str(exc) or type(exc).__name__
    return text if isinstance(exc, ValueError) else f"{type(exc).__name__}: {text}"
