"""Demand forecasting + walk-forward backtest (Phase 2).

This is the first place the framework produces a *real number*: given a daily demand
series (from real or synthetic orders), it backtests several baseline models with
a walk-forward split and reports error metrics (MAE / RMSE / MAPE / WAPE / bias;
conventions in ``analytics/metrics.py``).

These baselines (mean, naive, moving average, seasonal-naive) are honest,
dependency-free reference points. ALGORITHM-HOOK: swap in DeepAR / TFT / LightGBM
to beat them — the backtest harness stays the same and gives you the comparison.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable

from sdf.foundation.schema import OutboundOrder
from . import metrics
from .demand import DemandTable
from .models import seasonal_linear  # Phase 3

# -- build a daily series from canonical OutboundOrders ---------------------


def daily_demand_series(orders: Iterable[OutboundOrder], sku_id: str | None = None) -> list[float]:
    """Aggregate shipped orders into a dense daily quantity series.

    With ``sku_id`` the axis spans that SKU's own first-to-last order day.
    """
    if sku_id is not None:
        orders = [o for o in orders if o.sku_id == sku_id]
    return list(DemandTable.from_orders(orders).total())


def hourly_business_series(orders: Iterable[OutboundOrder], *, lo: int = 8, hi: int = 19):
    """Dense per-business-hour demand series. Returns (values, periods_per_day).

    Used when the data spans too few days for a daily model (e.g. a short
    extract). Captures intraday seasonality — the dominant signal at this scale.
    """
    from datetime import datetime

    by: dict = defaultdict(float)
    for o in orders:
        if o.status == "cancelled":
            continue
        by[o.ts.replace(minute=0, second=0, microsecond=0)] += o.quantity
    if not by:
        return [], 0
    days = sorted({k.date() for k in by})
    values = [float(by.get(datetime(d.year, d.month, d.day, h), 0.0)) for d in days for h in range(lo, hi)]
    return values, (hi - lo)


def build_series(orders: Iterable[OutboundOrder], prefer_daily_min_days: int = 14):
    """Pick the finest granularity the data can support.

    Returns (values, granularity_label, seasonal_period).
    """
    orders = list(orders)  # iterated twice below, so a generator must be materialised once
    days = sorted({o.ts.date() for o in orders if o.status != "cancelled"})
    if len(days) >= prefer_daily_min_days:
        return daily_demand_series(orders), "daily", 7
    values, ppd = hourly_business_series(orders)
    return values, "hourly", max(1, ppd)


def models_for(period: int, include_model: bool = True) -> dict:
    """Baselines matched to the granularity, plus the Phase 3 seasonal model."""
    models = {
        "mean": m_mean,
        "naive": m_naive,
        f"ma{period}": moving_average(period),
        f"snaive{period}": seasonal_naive(period),
    }
    if include_model:
        models[f"seas_linear{period}"] = seasonal_linear(period)
    return models


# -- one-step forecast models: history -> next-value prediction -------------


def m_mean(h: list[float]) -> float:
    return sum(h) / len(h) if h else 0.0


def m_naive(h: list[float]) -> float:
    return h[-1] if h else 0.0


def moving_average(k: int = 7) -> Callable[[list[float]], float]:
    def f(h: list[float]) -> float:
        w = h[-k:] if h else []
        return sum(w) / len(w) if w else 0.0

    f.__name__ = f"ma{k}"
    return f


def seasonal_naive(period: int = 7) -> Callable[[list[float]], float]:
    def f(h: list[float]) -> float:
        return h[-period] if len(h) >= period else (h[-1] if h else 0.0)

    f.__name__ = f"snaive{period}"
    return f


DEFAULT_MODELS = {
    "mean": m_mean,
    "naive": m_naive,
    "ma7": moving_average(7),
    "snaive7": seasonal_naive(7),
}


# -- walk-forward backtest ---------------------------------------------------


MIN_BACKTEST_POINTS = 3


def backtest(values: list[float], model: Callable[[list[float]], float], *, test_len: int = 21) -> dict:
    """One-step-ahead walk-forward evaluation over the last ``test_len`` days.

    A series shorter than ``MIN_BACKTEST_POINTS`` cannot be split into history
    and test points; the result is then ``{"error": ...}`` instead of metrics.
    """
    n = len(values)
    if n < MIN_BACKTEST_POINTS:
        return {"error": f"series too short to backtest ({n} points, need >= {MIN_BACKTEST_POINTS})"}
    test_len = min(test_len, max(1, n // 3))
    start = n - test_len
    actuals = values[start:]
    preds = [model(values[:t]) for t in range(start, n)]
    return {
        "model": getattr(model, "__name__", "model"),
        "test_days": test_len,
        "MAE": round(metrics.mae(actuals, preds), 3),
        "RMSE": round(metrics.rmse(actuals, preds), 3),
        "MAPE_pct": metrics.pct(metrics.mape(actuals, preds)),
        "WAPE_pct": metrics.pct(metrics.wape(actuals, preds)),
        "bias": round(metrics.bias(actuals, preds), 3),
    }


def compare_models(values: list[float], *, test_len: int = 21, models: dict[str, Callable] | None = None) -> dict:
    """Backtest every model; return per-model metrics and the MAE winner.

    On a series too short to backtest, ``results`` is empty, ``best_model`` is
    ``None`` and ``error`` says why.
    """
    models = models or DEFAULT_MODELS
    if len(values) < MIN_BACKTEST_POINTS:
        return {
            "series_len": len(values),
            "series_mean": round(sum(values) / len(values), 3) if values else 0.0,
            "results": [],
            "best_model": None,
            "error": f"series too short to backtest ({len(values)} points, need >= {MIN_BACKTEST_POINTS})",
        }
    results = [backtest(values, fn, test_len=test_len) for fn in models.values()]
    for r, name in zip(results, models):
        r["model"] = name
    results.sort(key=lambda r: r["MAE"])
    return {
        "series_len": len(values),
        "series_mean": round(sum(values) / len(values), 3) if values else 0.0,
        "results": results,
        "best_model": results[0]["model"] if results else None,
    }
