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

from sdf.analytics.demand import DemandTable
from .intelligence import WarehouseIntelligence


@dataclass
class CostModel:
    """Explicit, client-overridable cost assumptions."""

    holding_cost_annual_rate: float = 0.25  # 25%/yr of unit cost to hold
    stockout_penalty_mult: float = 1.0  # penalty = this × unit margin per lost unit
    order_fixed_cost: float = 25.0  # per replenishment order
    lead_time_days: int = 7
    review_days: int = 7
    service_z: float = 1.645  # 95% service level for the "good" policy
    working_days_per_year: int = 313

    def __post_init__(self) -> None:
        for name in ("holding_cost_annual_rate", "stockout_penalty_mult"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {getattr(self, name)!r}")
        if self.order_fixed_cost < 0:
            raise ValueError(f"order_fixed_cost must be >= 0, got {self.order_fixed_cost!r}")
        for name in ("lead_time_days", "review_days", "working_days_per_year"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1, got {getattr(self, name)!r}")
        if self.service_z <= 0:
            raise ValueError(f"service_z must be > 0, got {self.service_z!r}")


def _simulate(demand: list[float], s: float, S: float, lead: int, unit_cost: float, cm: CostModel) -> dict[str, float]:
    """One-SKU (s,S) simulation. Returns unmet units, holding £-days, #orders."""
    on_hand = S
    pipeline: dict[int, float] = defaultdict(float)  # day -> arriving qty
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
    return {
        "unmet_units": unmet,
        "holding_cost": holding_unit_days * daily_holding,
        "order_cost": orders * cm.order_fixed_cost,
        "orders": orders,
    }


def financial_impact(intel: WarehouseIntelligence, cost_model: CostModel | None = None, max_skus: int = 400) -> dict:
    """Counterfactual £: our (s,S) policy vs a naive no-safety-stock policy.

    ALGORITHM-HOOK: the naive baseline stands in for "current practice"; plug in
    the client's real current policy for a true before/after.
    """
    cm = cost_model or CostModel()
    table = DemandTable.from_orders(intel.reg.stream("OutboundOrder"))
    skus = {s.sku_id: s for s in intel.reg.stream("SKU")}
    if not table.days:
        return {"error": "no demand"}
    protect = cm.lead_time_days + cm.review_days

    tot = {"naive": defaultdict(float), "ours": defaultdict(float)}
    lost_margin = 0.0
    considered = 0
    for sku in list(table.series)[:max_skus]:
        mu, sigma = table.mean(sku), table.std(sku)
        if mu <= 0:
            continue
        considered += 1
        series = list(table.series[sku])
        uc = skus[sku].unit_cost if sku in skus else 1.0
        margin = (skus[sku].unit_price - uc) if sku in skus else uc * 0.3
        # naive: cover mean lead demand only, no safety stock
        s_n = mu * cm.lead_time_days
        S_n = mu * protect
        # ours: safety stock sized to the service level
        ss = cm.service_z * sigma * (protect**0.5)
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

    horizon_days = max(1, table.active_days)
    scale = cm.working_days_per_year / horizon_days  # annualise
    stockout_saving = lost_margin
    holding_delta = tot["ours"]["holding"] - tot["naive"]["holding"]  # +ve = we hold more
    order_delta = tot["ours"]["order"] - tot["naive"]["order"]
    net_period = stockout_saving - holding_delta - order_delta
    return {
        "assumptions": cm.__dict__,
        "skus_considered": considered,
        "horizon_days": horizon_days,
        "unmet_units": {"naive": round(tot["naive"]["unmet"]), "ours": round(tot["ours"]["unmet"])},
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
