"""Outcomes: named metrics measured on a world under a policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from .engine import simulate_inventory
from .policy import Policy, plan_orders
from .world import World


class Outcome(Protocol):
    name: str

    def measure(self, world: World, policy: Policy) -> dict[str, float]: ...


@dataclass
class CostModel:
    """Explicit, client-overridable cost assumptions. DATA-HOOK: real unit costs."""

    holding_cost_annual_rate: float = 0.25  # 25%/yr of unit cost to hold
    stockout_penalty_mult: float = 1.0  # penalty = this × unit margin per lost unit
    order_fixed_cost: float = 25.0  # per replenishment order
    lead_time_days: int = 7
    review_days: int = 7
    service_z: float = 1.645  # 95% service level for the "good" policy
    working_days_per_year: int = 313

    def __post_init__(self) -> None:
        """Reject cost assumptions the simulation cannot price; every message names the field."""
        for name in ("holding_cost_annual_rate", "stockout_penalty_mult"):
            v = getattr(self, name)
            if not (math.isfinite(v) and 0.0 <= v <= 1.0):
                raise ValueError(f"{name} must be a finite number in [0, 1], got {v!r}")
        if not (math.isfinite(self.order_fixed_cost) and self.order_fixed_cost >= 0):
            raise ValueError(f"order_fixed_cost must be a finite number >= 0, got {self.order_fixed_cost!r}")
        for name in ("lead_time_days", "review_days", "working_days_per_year"):
            v = getattr(self, name)
            if not (math.isfinite(v) and v >= 1):
                raise ValueError(f"{name} must be a finite number >= 1, got {v!r}")
        if not (math.isfinite(self.service_z) and self.service_z > 0):
            raise ValueError(f"service_z must be a finite number > 0, got {self.service_z!r}")


@dataclass(frozen=True)
class ReplenishmentNeed:
    """SKUs the policy would order now, and the safety stock it holds."""

    name: str = "replenishment_need"

    def measure(self, world: World, policy: Policy) -> dict[str, float]:
        plan = plan_orders(world, policy)
        ordering = [r for r in plan if r.order_qty > 0]
        return {
            "skus_needing_order": len(ordering),
            "safety_stock_units": round(sum(r.safety_stock for r in plan), 0),
            "intermittent_needing_order": sum(1 for r in ordering if r.profile.is_intermittent),
        }


@dataclass(frozen=True)
class ActiveStockouts:
    """Inventory positions with nothing available right now."""

    name: str = "active_stockouts"

    def measure(self, world: World, policy: Policy) -> dict[str, float]:
        return {"active_stockouts": sum(1 for s in world.stream("InventorySnapshot") if s.available == 0)}


@dataclass(frozen=True)
class SimulatedCost:
    """Replay each SKU's demand history under the policy and price the result.

    Covers the first ``max_skus`` SKUs with demand in first-appearance order.
    ALGORITHM-HOOK: the replay is deterministic on history; a stochastic
    lead-time and demand model gives distributions instead of one number.
    """

    cost_model: CostModel
    max_skus: int = 400
    name: str = "simulated_cost"

    def measure(self, world: World, policy: Policy) -> dict[str, float]:
        cm = self.cost_model
        table = world.demand()
        skus = {s.sku_id: s for s in world.stream("SKU")}
        unmet = holding = order_cost = lost_margin = total_demand = 0.0
        for sku in list(table.series)[: self.max_skus]:
            profile = table.profile(sku)
            if profile.mean <= 0:
                continue
            uc = skus[sku].unit_cost if sku in skus else 1.0
            margin = (skus[sku].unit_price - uc) if sku in skus else uc * 0.3
            trace = simulate_inventory(table.series[sku], policy.levels(profile), lead_time_days=policy.lead_time_days)
            daily_holding = uc * cm.holding_cost_annual_rate / cm.working_days_per_year
            unmet += trace.unmet_units
            holding += trace.holding_unit_days * daily_holding
            order_cost += trace.orders * cm.order_fixed_cost
            lost_margin += trace.unmet_units * margin * cm.stockout_penalty_mult
            total_demand += trace.total_demand
        return {
            "unmet_units": unmet,
            "fill_rate": 1.0 - unmet / total_demand if total_demand > 0 else 1.0,
            "holding_cost": holding,
            "order_cost": order_cost,
            "lost_margin": lost_margin,
        }
