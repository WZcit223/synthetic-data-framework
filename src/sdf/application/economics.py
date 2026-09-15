"""Business-outcome economics — translate metrics into money (dependency-free).

The decisive step from "technical demo" to "commercial proposal": show, by
counterfactual simulation on the demand history, how much a good policy would
have saved versus a naive one. We simulate two inventory policies over each SKU's
daily demand and price the difference in stockouts and holding.

All unit costs are explicit ASSUMPTIONS (a `CostModel`) — in a real engagement
they come from the client's finance team. Every number here is therefore an
estimate with stated assumptions, not a claim. # DATA-HOOK: real unit costs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class CostModel:
    """Explicit, client-overridable cost assumptions."""

    holding_cost_annual_rate: float = 0.25      # 25%/yr of unit cost to hold
    stockout_penalty_mult: float = 1.0          # penalty = this × unit margin per lost unit
    order_fixed_cost: float = 25.0              # per replenishment order
    lead_time_days: int = 7
    review_days: int = 7
    service_z: float = 1.645                    # 95% service level for the "good" policy
    working_days_per_year: int = 313


def _simulate(demand: List[float], s: float, S: float, lead: int,
              unit_cost: float, cm: CostModel) -> Dict[str, float]:
    """One-SKU (s,S) simulation. Returns unmet units, holding £-days, #orders."""
    on_hand = S
    pipeline: Dict[int, float] = defaultdict(float)   # day -> arriving qty
    unmet = 0.0
    holding_unit_days = 0.0
    orders = 0
    for t, dmd in enumerate(demand):
        on_hand += pipeline.pop(t, 0.0)
        fill = min(on_hand, dmd)
        unmet += max(0.0, dmd - fill)
        on_hand -= fill
        holding_unit_days += on_hand
        inbound = sum(v for k, v in pipeline.items() if k > t)
        if on_hand + inbound <= s:
            qty = max(0.0, S - (on_hand + inbound))
            if qty > 0:
                pipeline[t + lead] += qty
                orders += 1
    daily_holding = unit_cost * cm.holding_cost_annual_rate / cm.working_days_per_year
    return {"unmet_units": unmet, "holding_cost": holding_unit_days * daily_holding,
            "order_cost": orders * cm.order_fixed_cost, "orders": orders}


def financial_impact(intel, cost_model: CostModel = None, max_skus: int = 400) -> Dict:
    """Counterfactual £: our (s,S) policy vs a naive no-safety-stock policy.

    ALGORITHM-HOOK: the naive baseline stands in for "current practice"; plug in
    the client's real current policy for a true before/after.
    """
    cm = cost_model or CostModel()
    stats = intel._sku_daily_stats()
    skus = {s.sku_id: s for s in intel.reg.stream("SKU")}
    # per-SKU demand series over the horizon
    out = intel.reg.stream("OutboundOrder", where=lambda o: o.status != "cancelled")
    by_sku_day: Dict = defaultdict(lambda: defaultdict(float))
    days = set()
    for o in out:
        by_sku_day[o.sku_id][o.ts.date()] += o.quantity
        days.add(o.ts.date())
    days = sorted(days)
    if not days:
        return {"error": "no demand"}
    protect = cm.lead_time_days + cm.review_days

    tot = {"naive": defaultdict(float), "ours": defaultdict(float)}
    lost_margin = 0.0
    considered = 0
    for sku, (mu, sigma) in list(stats.items())[:max_skus]:
        if mu <= 0:
            continue
        considered += 1
        series = [by_sku_day[sku].get(d, 0.0) for d in days]
        uc = skus[sku].unit_cost if sku in skus else 1.0
        margin = (skus[sku].unit_price - uc) if sku in skus else uc * 0.3
        # naive: cover mean lead demand only, no safety stock
        s_n = mu * cm.lead_time_days
        S_n = mu * protect
        # ours: safety stock sized to the service level
        ss = cm.service_z * sigma * (protect ** 0.5)
        s_o = mu * protect + ss
        S_o = s_o
        rn = _simulate(series, s_n, S_n, cm.lead_time_days, uc, cm)
        ro = _simulate(series, s_o, S_o, cm.lead_time_days, uc, cm)
        for pol, r in (("naive", rn), ("ours", ro)):
            tot[pol]["unmet"] += r["unmet_units"]
            tot[pol]["holding"] += r["holding_cost"]
            tot[pol]["order"] += r["order_cost"]
        # value of a served-vs-lost unit = margin × penalty
        lost_margin += (rn["unmet_units"] - ro["unmet_units"]) * margin * cm.stockout_penalty_mult

    horizon_days = max(1, len(days))
    scale = cm.working_days_per_year / horizon_days      # annualise
    stockout_saving = lost_margin
    holding_delta = tot["ours"]["holding"] - tot["naive"]["holding"]     # +ve = we hold more
    order_delta = tot["ours"]["order"] - tot["naive"]["order"]
    net_period = stockout_saving - holding_delta - order_delta
    return {
        "assumptions": cm.__dict__,
        "skus_considered": considered,
        "horizon_days": horizon_days,
        "unmet_units": {"naive": round(tot["naive"]["unmet"]),
                        "ours": round(tot["ours"]["unmet"])},
        "stockout_units_avoided": round(tot["naive"]["unmet"] - tot["ours"]["unmet"]),
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
