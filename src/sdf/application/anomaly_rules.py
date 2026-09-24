"""Anomalies: stockout / dead-stock rules and statistical demand anomalies (Application Layer)."""

from __future__ import annotations

import statistics

from sdf.analytics.anomaly import residual_scale, seasonal_residual_anomalies
from sdf.analytics.demand import DemandTable
from sdf.analytics.forecast import build_series
from sdf.foundation.registry import DataSourceRegistry


def rule_anomalies(reg: DataSourceRegistry) -> list[dict]:
    """Flag stockouts and dead stock.

    ALGORITHM-HOOK[C3]: replace threshold rules with an anomaly-detection model
    (isolation forest / autoencoder) over the multivariate inventory series.
    """
    inv = reg.stream("InventorySnapshot")
    demand = DemandTable.from_orders(reg.stream("OutboundOrder")).daily_rates()
    out: list[dict] = []
    for snap in inv:
        if snap.available == 0:
            out.append({"type": "stockout", "sku_id": snap.sku_id, "location_id": snap.location_id})
        elif demand.get(snap.sku_id, 0.0) == 0.0 and snap.on_hand > 100:
            out.append({"type": "dead_stock", "sku_id": snap.sku_id, "on_hand": snap.on_hand})
    return out


def demand_anomalies(reg: DataSourceRegistry, k: float = 3.5) -> dict:
    """Seasonal-residual + robust-z anomalies on the demand series (C3)."""
    orders = reg.stream("OutboundOrder")
    series, freq, period = build_series(orders)
    found = seasonal_residual_anomalies(series, period, k=k)
    out = {
        "granularity": freq,
        "seasonal_period": period,
        "series_len": len(series),
        "count": len(found),
        "anomalies": found[:20],
    }
    if len(series) >= max(2 * period, 8):
        profile = [statistics.median(series[j::period]) for j in range(period)]
        _scale, method = residual_scale([v - profile[i % period] for i, v in enumerate(series)])
        if method != "mad":
            out["note"] = f"residual spread too small for MAD; scale from {method.replace('_', ' ')}"
    return out
