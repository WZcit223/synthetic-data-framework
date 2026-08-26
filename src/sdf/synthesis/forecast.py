"""Demand forecasting + walk-forward backtest (Phase 2).

This is the first place the shell produces a *real number*: given a daily demand
series (from real or synthetic orders), it backtests several baseline models with
a walk-forward split and reports error metrics (MAE / RMSE / MAPE / bias).

These baselines (mean, naive, moving average, seasonal-naive) are honest,
dependency-free reference points. ALGORITHM-HOOK: swap in DeepAR / TFT / LightGBM
to beat them — the backtest harness stays the same and gives you the comparison.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Callable, Dict, List, Optional


# -- build a daily series from canonical OutboundOrders ---------------------

def daily_demand_series(orders, sku_id: Optional[str] = None) -> List[float]:
    """Aggregate shipped orders into a dense daily quantity series."""
    by_day: Dict[date, float] = defaultdict(float)
    for o in orders:
        if o.status == "cancelled":
            continue
        if sku_id is not None and o.sku_id != sku_id:
            continue
        by_day[o.ts.date()] += o.quantity
    if not by_day:
        return []
    d0, d1 = min(by_day), max(by_day)
    out, cur = [], d0
    from datetime import timedelta
    while cur <= d1:
        out.append(float(by_day.get(cur, 0.0)))
        cur += timedelta(days=1)
    return out


def hourly_business_series(orders, lo: int = 8, hi: int = 19):
    """Dense per-business-hour demand series. Returns (values, periods_per_day).

    Used when the data spans too few days for a daily model (e.g. a short
    extract). Captures intraday seasonality — the dominant signal at this scale.
    """
    from datetime import datetime
    by: Dict = defaultdict(float)
    for o in orders:
        if o.status == "cancelled":
            continue
        by[o.ts.replace(minute=0, second=0, microsecond=0)] += o.quantity
    if not by:
        return [], 0
    days = sorted({k.date() for k in by})
    values = [float(by.get(datetime(d.year, d.month, d.day, h), 0.0))
              for d in days for h in range(lo, hi)]
    return values, (hi - lo)


def build_series(orders, prefer_daily_min_days: int = 14):
    """Pick the finest granularity the data can support.

    Returns (values, granularity_label, seasonal_period).
    """
    days = sorted({o.ts.date() for o in orders if o.status != "cancelled"})
    if len(days) >= prefer_daily_min_days:
        return daily_demand_series(orders), "daily", 7
    values, ppd = hourly_business_series(orders)
    return values, "hourly", max(1, ppd)


def models_for(period: int) -> Dict:
    """Baseline model set with the seasonal period matched to the granularity."""
    return {
        "mean": m_mean,
        "naive": m_naive,
        f"ma{period}": moving_average(period),
        f"snaive{period}": seasonal_naive(period),
    }


# -- one-step forecast models: history -> next-value prediction -------------

def m_mean(h: List[float]) -> float:
    return sum(h) / len(h) if h else 0.0


def m_naive(h: List[float]) -> float:
    return h[-1] if h else 0.0


def moving_average(k: int = 7) -> Callable[[List[float]], float]:
    def f(h: List[float]) -> float:
        w = h[-k:] if h else []
        return sum(w) / len(w) if w else 0.0
    f.__name__ = f"ma{k}"
    return f


def seasonal_naive(period: int = 7) -> Callable[[List[float]], float]:
    def f(h: List[float]) -> float:
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

def backtest(values: List[float], model: Callable[[List[float]], float],
             test_len: int = 21) -> Dict[str, float]:
    """One-step-ahead walk-forward evaluation over the last ``test_len`` days."""
    n = len(values)
    test_len = min(test_len, max(1, n // 3))
    start = n - test_len
    abs_err, sq_err, ape, bias, cnt = 0.0, 0.0, 0.0, 0.0, 0
    for t in range(start, n):
        pred = model(values[:t])
        actual = values[t]
        err = pred - actual
        abs_err += abs(err)
        sq_err += err * err
        bias += err
        if actual > 0:
            ape += abs(err) / actual
        cnt += 1
    return {
        "model": getattr(model, "__name__", "model"),
        "test_days": cnt,
        "MAE": round(abs_err / cnt, 3),
        "RMSE": round(math.sqrt(sq_err / cnt), 3),
        "MAPE_pct": round(100 * ape / cnt, 2),
        "bias": round(bias / cnt, 3),
    }


def compare_models(values: List[float], test_len: int = 21,
                   models: Optional[Dict[str, Callable]] = None) -> Dict:
    """Backtest every model; return per-model metrics and the MAE winner."""
    models = models or DEFAULT_MODELS
    results = [backtest(values, fn, test_len) for fn in models.values()]
    for r, name in zip(results, models):
        r["model"] = name
    results.sort(key=lambda r: r["MAE"])
    return {
        "series_len": len(values),
        "series_mean": round(sum(values) / len(values), 3) if values else 0.0,
        "results": results,
        "best_model": results[0]["model"] if results else None,
    }
