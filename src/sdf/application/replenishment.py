"""Replenishment: the rule-of-thumb suggestions, the (s,S) policy and the demand deep dive.

Both replenishment answers still live here until the rule-of-thumb policy is
removed (structure sequence, PR 3).
"""

from __future__ import annotations

from sdf.analytics.demand import DemandProfile, DemandTable
from sdf.foundation.registry import DataSourceRegistry

Z_FOR_SERVICE_LEVEL = {0.80: 0.842, 0.85: 1.036, 0.90: 1.282, 0.95: 1.645, 0.975: 1.960, 0.99: 2.326}


def z_for(service_level: float) -> float:
    """Standard-normal z of the nearest tabulated service level."""
    key = min(Z_FOR_SERVICE_LEVEL, key=lambda k: abs(k - service_level))
    return Z_FOR_SERVICE_LEVEL[key]


def demand_table(reg: DataSourceRegistry) -> DemandTable:
    """Per-SKU daily demand of non-cancelled orders (the shared aggregation)."""
    return DemandTable.from_orders(reg.stream("OutboundOrder"))


def demand_profiles(reg: DataSourceRegistry) -> dict[str, DemandProfile]:
    """Per-SKU demand shape (mean, std, zero-day share); safety stock uses ``variability``."""
    table = demand_table(reg)
    return {sku: table.profile(sku) for sku in table.series}


def rule_suggestions(reg: DataSourceRegistry, top_n: int = 10) -> list[dict]:
    """Rule-based reorder-point flags.

    ALGORITHM-HOOK: replace the fixed safety-stock rule with a fitted
    demand-forecast + (s,S) / newsvendor optimiser learned from real
    order history.
    """
    skus = {s.sku_id: s for s in reg.stream("SKU")}
    inv = reg.stream("InventorySnapshot")
    demand = demand_table(reg).daily_rates()

    suggestions: list[dict] = []
    for snap in inv:
        d = demand.get(snap.sku_id, 0.0)
        lead = 7  # placeholder average lead time
        safety = d * 3
        reorder_point = d * lead + safety
        if snap.available <= reorder_point:
            target = d * (lead + 14) + safety  # cover to next cycle
            qty = max(0, int(round(target - snap.available)))
            if qty > 0:
                suggestions.append(
                    {
                        "sku_id": snap.sku_id,
                        "name": skus.get(snap.sku_id).name if snap.sku_id in skus else "?",
                        "on_hand": snap.on_hand,
                        "available": snap.available,
                        "avg_daily_demand": round(d, 2),
                        "reorder_point": round(reorder_point, 1),
                        "suggested_order_qty": qty,
                        "urgency": round(reorder_point - snap.available, 1),
                    }
                )
    suggestions.sort(key=lambda x: x["urgency"], reverse=True)
    return suggestions[:top_n]


def rule_simulation(reg: DataSourceRegistry) -> dict:
    """Compare service level before vs. after applying the rule-based suggestions.

    This is the 'closed loop' story: forecast -> reorder point -> suggested
    order -> projected effect. ALGORITHM-HOOK: a real sim would roll demand
    forward stochastically over lead time; here we apply a one-step top-up.
    """
    inv = reg.stream("InventorySnapshot")
    suggestions = {s["sku_id"]: s for s in rule_suggestions(reg, 9999)}
    total = max(1, len(inv))
    at_risk_before = sum(1 for s in inv if s.sku_id in suggestions)
    stockouts_before = sum(1 for s in inv if s.available == 0)
    # After top-up, flagged SKUs are lifted above their reorder point.
    stockouts_after = sum(1 for s in inv if s.available == 0 and s.sku_id not in suggestions)
    return {
        "skus_total": len(inv),
        "skus_flagged": at_risk_before,
        "stockouts_before": stockouts_before,
        "stockouts_after": stockouts_after,
        "service_level_before": round(1 - at_risk_before / total, 4),
        "service_level_after": round(1 - stockouts_after / total, 4),
    }


def ss_policy(
    reg: DataSourceRegistry,
    *,
    lead_time_days: int = 7,
    review_days: int = 7,
    service_level: float = 0.95,
    top_n: int = 12,
) -> dict:
    """Classic (s, S) policy sized from demand variability + a service level.

    s (reorder point) = μ·(L+R) + z·σ·√(L+R);  S (order-up-to) = s,
    where μ is the SKU's mean daily demand over calendar days and σ is
    ``DemandProfile.variability`` (the day-to-day std for smooth SKUs, at
    least the average selling-day quantity for intermittent ones).
    ALGORITHM-HOOK: this uses a normal-demand approximation; a real system
    fits the lead-time demand distribution (incl. intermittent-demand models)
    and solves a cost-based newsvendor objective.
    """
    z = z_for(service_level)
    profiles = demand_profiles(reg)
    skus = {s.sku_id: s for s in reg.stream("SKU")}
    avail = {}
    for snap in reg.stream("InventorySnapshot"):
        avail[snap.sku_id] = avail.get(snap.sku_id, 0) + snap.available

    protect = lead_time_days + review_days
    rows: list[dict] = []
    total_ss_units = 0.0
    intermittent_flagged = 0
    for sku, prof in profiles.items():
        mu = prof.mean
        if mu <= 0:
            continue  # no demand in the window: nothing to protect
        ss = z * prof.variability * (protect**0.5)
        s = mu * protect + ss
        S = s  # order-up-to == reorder point for a single review cycle
        on_hand = avail.get(sku, 0)
        order = max(0, round(S - on_hand)) if on_hand <= s else 0
        total_ss_units += ss
        if order > 0 and prof.is_intermittent:
            intermittent_flagged += 1
        rows.append(
            {
                "sku_id": sku,
                "name": skus[sku].name if sku in skus else "?",
                "avg_daily_demand": round(mu, 2),
                "demand_std": round(prof.std, 2),
                "variability": round(prof.variability, 2),
                "intermittent": prof.is_intermittent,
                "safety_stock": round(ss, 1),
                "reorder_point_s": round(s, 1),
                "order_up_to_S": round(S, 1),
                "available": on_hand,
                "order_qty": order,
            }
        )
    rows.sort(key=lambda r: r["order_qty"], reverse=True)
    return {
        "service_level": service_level,
        "z": z,
        "lead_time_days": lead_time_days,
        "review_days": review_days,
        "skus_needing_order": sum(1 for r in rows if r["order_qty"] > 0),
        "intermittent_needing_order": intermittent_flagged,
        "total_safety_stock_units": round(total_ss_units, 0),
        "rows": rows[:top_n],
    }


def demand_series(reg: DataSourceRegistry, sku_id: str, forecast_days: int = 14) -> dict:
    """Daily demand history for one SKU + a naive trailing-average forecast.

    ``history`` lists the days on which the SKU shipped (what the chart
    plots). The forecast is the mean over the last 14 *calendar* days of the
    table, zero days included, like every other daily rate in the package.
    ALGORITHM-HOOK: the forecast here is a trailing mean. Replace with a
    fitted model (DeepAR / TFT / LightGBM) to get real predictive intervals.
    """
    table = demand_table(reg)
    series = table.series.get(sku_id, ())
    history = [{"date": d.isoformat(), "qty": int(q)} for d, q in zip(table.days, series) if q > 0]
    recent = list(series[-14:]) or [0.0]
    forecast_avg = round(sum(recent) / len(recent), 2)
    return {
        "sku_id": sku_id,
        "history": history,
        "forecast_avg_daily": forecast_avg,
        "forecast_horizon_days": forecast_days,
        "forecast_total": round(forecast_avg * forecast_days, 1),
    }
