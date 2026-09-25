"""Replenishment: the (s,S) service-level plan, the policy comparison and the demand deep dive.

The (s,S) service-level policy is the only replenishment policy; its sizing rule
lives in ``sdf.simulation.policy``. This module formats its results for the
dashboard, the agent and the reports.
"""

from __future__ import annotations

from datetime import timedelta

from sdf.analytics.demand import DemandProfile, DemandTable
from sdf.analytics.forecasters import Forecast
from sdf.foundation.registry import DataSourceRegistry
from sdf.simulation.experiment import Experiment
from sdf.simulation.intervention import Baseline
from sdf.simulation.outcome import MIN_FIT_DAYS, CostModel, ReplenishmentNeed, SimulatedCost
from sdf.simulation.policy import CostBasedPolicy, NaivePolicy, ServiceLevelPolicy, plan_orders
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


HOLDOUT_DAYS = 30  # the comparison's out-of-sample replay: levels from the days before, cost on these


def policy_comparison(reg: DataSourceRegistry, *, service_level: float = 0.95) -> dict:
    """Replay the demand history under a no-safety-stock policy, the (s,S) policy and the cost-based policy.

    One ``Experiment`` with ``NaivePolicy``, ``ServiceLevelPolicy`` and ``CostBasedPolicy``
    measured by ``ReplenishmentNeed`` and ``SimulatedCost`` (default ``CostModel``), both
    over every SKU with demand, in sample; and, when the history leaves enough days to
    fit on, out of sample: levels from all but the last ``HOLDOUT_DAYS`` days, the cost
    of those days (``holdout_*``). Each entry of ``policies`` holds one policy's metrics,
    so the dashboard can show what the safety stock buys (fewer unmet units for more
    units held) and what choosing the levels on cost saves on days they were not fitted on.
    """
    world = World(registry=reg, label="policy_comparison")
    every_sku = len(world.demand().series)  # same scope as ReplenishmentNeed, unlike the economics cap
    policies = [NaivePolicy(), ServiceLevelPolicy(service_level=service_level), CostBasedPolicy()]
    outcomes = [ReplenishmentNeed(), SimulatedCost(CostModel(), max_skus=every_sku)]
    if len(world.demand().days) - HOLDOUT_DAYS >= MIN_FIT_DAYS:
        outcomes.append(SimulatedCost(CostModel(), max_skus=every_sku, holdout_days=HOLDOUT_DAYS, name="holdout"))
    rows = Experiment(world=world, interventions=[Baseline()], policies=policies, outcomes=outcomes).run()
    by_policy: dict[str, dict] = {p.name: {"policy": p.name} for p in policies}
    for r in rows:
        by_policy[r.policy][r.metric] = round(r.value, 4) if r.metric.endswith("fill_rate") else round(r.value)
    return {
        "service_level": service_level,
        "horizon_days": len(world.demand().days),
        "holdout_days": HOLDOUT_DAYS if len(outcomes) == 3 else None,
        "policies": list(by_policy.values()),
    }


def demand_series(reg: DataSourceRegistry, sku_id: str, forecast_days: int = 14) -> dict:
    """Daily demand history for one SKU, and its trailing mean as a daily rate.

    ``history`` lists the days on which the SKU shipped (what the chart
    plots). ``forecast_avg_daily`` is the mean over the last 14 *calendar* days
    of the table, zero days included, like every other daily rate in the
    package; the API keeps it for older clients, and adds the fitted forecast
    of ``sku_forecast`` beside it.
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


def sku_forecast(fc: Forecast, sku_id: str, level: float) -> dict:
    """One SKU's rows of a forecast of every SKU: each day's mean and its central ``level`` interval.

    ``fc`` holds the two quantiles of that interval; a SKU it does not cover has no day.
    """
    days = []
    if sku_id in fc.sku_ids:
        i = fc.sku_ids.index(sku_id)
        low, high = (fc.quantiles[lv][i] for lv in sorted(fc.quantiles))
        for k in range(fc.horizon):
            days.append(
                {
                    "date": (fc.origin + timedelta(days=k)).isoformat(),
                    "mean": round(float(fc.mean[i, k]), 2),
                    "low": round(float(low[k]), 2),
                    "high": round(float(high[k]), 2),
                }
            )
    return {"forecaster": fc.forecaster, "level": level, "days": days}
