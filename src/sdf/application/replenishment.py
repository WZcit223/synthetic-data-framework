"""Replenishment: the (s,S) service-level plan, the policy comparison and the demand deep dive.

The (s,S) service-level policy is the only replenishment policy; its sizing rule
lives in ``sdf.simulation.policy``. This module formats its results for the
dashboard, the agent and the reports.
"""

from __future__ import annotations

from sdf.analytics.demand import DemandProfile, DemandTable
from sdf.foundation.registry import DataSourceRegistry
from sdf.simulation.experiment import Experiment
from sdf.simulation.intervention import Baseline
from sdf.simulation.outcome import CostModel, ReplenishmentNeed, SimulatedCost
from sdf.simulation.policy import NaivePolicy, ServiceLevelPolicy, plan_orders
from sdf.simulation.world import World


def demand_table(reg: DataSourceRegistry) -> DemandTable:
    """Per-SKU daily demand of non-cancelled orders (the shared aggregation)."""
    return DemandTable.from_orders(reg.stream("OutboundOrder"))


def demand_profiles(reg: DataSourceRegistry) -> dict[str, DemandProfile]:
    """Per-SKU demand shape (mean, std, zero-day share); safety stock uses ``variability``."""
    table = demand_table(reg)
    return {sku: table.profile(sku) for sku in table.series}


def ss_policy(
    reg: DataSourceRegistry,
    *,
    lead_time_days: int = 7,
    review_days: int = 7,
    service_level: float = 0.95,
    top_n: int = 12,
) -> dict:
    """The (s, S) service-level policy applied to every SKU with demand.

    The sizing rule lives in ``sdf.simulation.policy.ServiceLevelPolicy``; this
    function formats its plan for the dashboard, the agent and the reports.
    """
    policy = ServiceLevelPolicy(service_level=service_level, lead_time_days=lead_time_days, review_days=review_days)
    plan = plan_orders(World(registry=reg, label="ss_policy"), policy)
    ordering = [r for r in plan if r.order_qty > 0]
    rows = [
        {
            "sku_id": r.sku_id,
            "name": r.name,
            "avg_daily_demand": round(r.profile.mean, 2),
            "demand_std": round(r.profile.std, 2),
            "variability": round(r.profile.variability, 2),
            "intermittent": r.profile.is_intermittent,
            "safety_stock": round(r.safety_stock, 1),
            "reorder_point_s": round(r.reorder_point, 1),
            "order_up_to_S": round(r.order_up_to, 1),
            "available": r.available,
            "order_qty": r.order_qty,
        }
        for r in plan[:top_n]
    ]
    return {
        "service_level": service_level,
        "z": policy.effective_z,
        "lead_time_days": lead_time_days,
        "review_days": review_days,
        "skus_needing_order": len(ordering),
        "intermittent_needing_order": sum(1 for r in ordering if r.profile.is_intermittent),
        "total_safety_stock_units": round(sum(r.safety_stock for r in plan), 0),
        "rows": rows,
    }


def policy_comparison(reg: DataSourceRegistry, *, service_level: float = 0.95) -> dict:
    """Replay the demand history under a no-safety-stock policy and the (s,S) policy.

    One ``Experiment`` with ``NaivePolicy`` and ``ServiceLevelPolicy`` measured by
    ``ReplenishmentNeed`` and ``SimulatedCost`` (default ``CostModel``). Each
    entry of ``policies`` holds one policy's metrics, so the dashboard can show
    what the safety stock buys: fewer unmet units for more units held.
    """
    world = World(registry=reg, label="policy_comparison")
    policies = [NaivePolicy(), ServiceLevelPolicy(service_level=service_level)]
    rows = Experiment(
        world=world,
        interventions=[Baseline()],
        policies=policies,
        outcomes=[ReplenishmentNeed(), SimulatedCost(CostModel())],
    ).run()
    by_policy: dict[str, dict] = {p.name: {"policy": p.name} for p in policies}
    for r in rows:
        by_policy[r.policy][r.metric] = round(r.value, 4) if r.metric == "fill_rate" else round(r.value)
    return {
        "service_level": service_level,
        "horizon_days": len(world.demand().days),
        "policies": list(by_policy.values()),
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
