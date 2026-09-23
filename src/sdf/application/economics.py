"""Business-outcome economics — translate metrics into money (dependency-free).

The decisive step from "technical demo" to "commercial proposal": show, by
counterfactual simulation on the demand history, how much a good policy would
have saved versus a naive one. An ``Experiment`` replays each SKU's daily demand
under both policies (``sdf.simulation``) and this module prices the difference
in stockouts and holding.

All unit costs are explicit ASSUMPTIONS (a ``CostModel``) — in a real engagement
they come from the client's finance team. Every number here is therefore an
estimate with stated assumptions, not a claim. # DATA-HOOK: real unit costs.
"""

from __future__ import annotations

from sdf.simulation.experiment import Experiment
from sdf.simulation.intervention import Baseline
from sdf.simulation.outcome import CostModel, SimulatedCost
from sdf.simulation.policy import NaivePolicy, ServiceLevelPolicy
from sdf.simulation.world import World
from .intelligence import WarehouseIntelligence


def financial_impact(intel: WarehouseIntelligence, *, cost_model: CostModel | None = None, max_skus: int = 400) -> dict:
    """Counterfactual £: our (s,S) policy vs a naive no-safety-stock policy.

    ALGORITHM-HOOK: the naive baseline stands in for "current practice"; plug in
    the client's real current policy for a true before/after.
    """
    cm = cost_model or CostModel()
    world = World(registry=intel.reg, label="financial_impact")
    table = world.demand()
    if not table.days:
        return {"error": "no demand"}
    naive = NaivePolicy(lead_time_days=cm.lead_time_days, review_days=cm.review_days)
    ours = ServiceLevelPolicy(z=cm.service_z, lead_time_days=cm.lead_time_days, review_days=cm.review_days)
    rows = Experiment(
        world=world, interventions=[Baseline()], policies=[naive, ours], outcomes=[SimulatedCost(cm, max_skus=max_skus)]
    ).run()
    tot = {(r.policy, r.metric): r.value for r in rows}
    n, o = naive.name, ours.name

    considered = sum(1 for sku in list(table.series)[:max_skus] if table.profile(sku).mean > 0)
    horizon_days = max(1, len(table.days))
    scale = cm.working_days_per_year / horizon_days  # annualise
    # value of a served-vs-lost unit = margin × penalty
    stockout_saving = tot[n, "lost_margin"] - tot[o, "lost_margin"]
    holding_delta = tot[o, "holding_cost"] - tot[n, "holding_cost"]  # +ve = we hold more
    order_delta = tot[o, "order_cost"] - tot[n, "order_cost"]
    net_period = stockout_saving - holding_delta - order_delta
    return {
        "assumptions": cm.__dict__,
        "skus_considered": considered,
        "horizon_days": horizon_days,
        "unmet_units": {"naive": round(tot[n, "unmet_units"]), "ours": round(tot[o, "unmet_units"])},
        "stockout_units_avoided": round(tot[n, "unmet_units"] - tot[o, "unmet_units"]),
        "period": {
            "stockout_cost_saved": round(stockout_saving),
            "extra_holding_cost": round(holding_delta),
            "extra_order_cost": round(order_delta),
            "net_saving": round(net_period),
        },
        "annualised_net_saving": round(net_period * scale),
        "note": "Estimate on synthetic demand with assumed unit costs (CostModel). "
        "DATA-HOOK: real costs + real current policy give the true figure.",
    }
