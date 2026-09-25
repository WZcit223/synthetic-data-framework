"""Replenishment policies: how much stock to hold, given a SKU's demand profile, or its costs and history.

A policy's ``levels(profile)`` sees the demand profile only; a policy that also needs
the SKU's history and costs defines ``levels_for(item)``. Callers ask ``levels_for``,
which uses whichever the policy has. The contract is
``docs/refactor/algorithms/interfaces.md`` §5.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import numpy as np

from sdf.analytics.demand import DemandProfile
from .world import World

if TYPE_CHECKING:
    from .outcome import CostModel

# What a SKU missing from the SKU stream costs and sells for: the values SimulatedCost has always assumed.
DEFAULT_UNIT_COST = 1.0
DEFAULT_UNIT_PRICE = 1.3

Z_FOR_SERVICE_LEVEL = {0.80: 0.842, 0.85: 1.036, 0.90: 1.282, 0.95: 1.645, 0.975: 1.960, 0.99: 2.326}


def z_for(service_level: float) -> float:
    """Standard-normal z of the nearest tabulated service level."""
    key = min(Z_FOR_SERVICE_LEVEL, key=lambda k: abs(k - service_level))
    return Z_FOR_SERVICE_LEVEL[key]


@dataclass(frozen=True)
class Levels:
    """Reorder point ``s``, order-up-to level ``S`` and the safety stock inside ``s``."""

    reorder_point: float
    order_up_to: float
    safety_stock: float = 0.0


class Policy(Protocol):
    name: str
    lead_time_days: int

    def levels(self, profile: DemandProfile) -> Levels: ...


@dataclass(frozen=True)
class PolicyInput:
    """What a policy may know of one SKU: its demand profile, the daily history it came from, its costs."""

    sku_id: str
    profile: DemandProfile  # of ``history``
    history: tuple[float, ...]  # daily demand the levels may use, oldest first
    unit_cost: float
    unit_price: float


def levels_for(policy: Policy, item: PolicyInput) -> Levels:
    """``policy.levels_for(item)`` when the policy defines it, else ``policy.levels(item.profile)``."""
    own = getattr(policy, "levels_for", None)
    return own(item) if callable(own) else policy.levels(item.profile)


@dataclass(frozen=True)
class ServiceLevelPolicy:
    """Classic (s, S): s = μ·(L+R) + z·σ·√(L+R), S = s.

    μ is the mean daily demand over calendar days; σ is
    ``DemandProfile.variability`` (the day-to-day std for smooth SKUs, at least
    the average selling-day quantity for intermittent ones). ``z`` defaults to
    the tabulated value for ``service_level``.
    ALGORITHM-HOOK[C2]: this is a normal-demand approximation; a real system fits
    the lead-time demand distribution and solves a cost-based newsvendor objective.
    """

    service_level: float = 0.95
    z: float | None = None
    lead_time_days: int = 7
    review_days: int = 7

    @property
    def name(self) -> str:
        if self.z is not None:
            return f"service-level-z{self.z}"
        return f"service-level-{round(self.service_level * 100, 2):g}"  # 0.95 -> 95, 0.975 -> 97.5

    @property
    def effective_z(self) -> float:
        return self.z if self.z is not None else z_for(self.service_level)

    def levels(self, profile: DemandProfile) -> Levels:
        protect = self.lead_time_days + self.review_days
        ss = self.effective_z * profile.variability * (protect**0.5)
        s = profile.mean * protect + ss
        return Levels(reorder_point=s, order_up_to=s, safety_stock=ss)


@dataclass(frozen=True)
class NaivePolicy:
    """No safety stock: reorder at mean lead-time demand, fill to one review cycle."""

    lead_time_days: int = 7
    review_days: int = 7
    name: str = "naive"

    def levels(self, profile: DemandProfile) -> Levels:
        return Levels(
            reorder_point=profile.mean * self.lead_time_days,
            order_up_to=profile.mean * (self.lead_time_days + self.review_days),
        )


def _cost_model() -> CostModel:
    from .outcome import CostModel  # outcome imports this module

    return CostModel()


@dataclass(frozen=True)
class CostBasedPolicy:
    """(s, S) with both levels chosen per SKU on the cost of replaying its own history.

    Candidates: ``s = μ(L+R) + z·σ·√(L+R)`` for every ``z`` of ``Z_GRID`` (μ, σ from the
    profile; σ its ``variability``), and an order size ``S − s = m·Q`` for every ``m`` of
    ``LOT_GRID``, with ``Q`` the economic order quantity ``√(2·K·μ / h)`` (K the order's fixed
    cost, h the daily holding cost of a unit), at most one order for the whole history. The
    pair whose replay of ``item.history`` costs least (holding + ordering + lost margin, as
    ``SimulatedCost`` prices them) wins; ties go to the smaller ``s``, then the smaller order.
    The grid is fixed, so the levels are reproducible; nothing beyond ``item.history`` is read.
    The policy prices with its own ``cost_model``: an outcome scoring it under other costs
    scores levels tuned for these.
    ALGORITHM-HOOK[C2]: lead times are fixed and demand is replayed as it happened; stochastic
    lead times and a fitted lead-time demand distribution replace the replay.
    """

    cost_model: CostModel = field(default_factory=_cost_model, hash=False)
    lead_time_days: int = 7
    review_days: int = 7
    name: str = "cost-based"

    Z_GRID = (0.0, 0.5, 1.0, 1.28, 1.645, 2.0, 2.5, 3.0)
    LOT_GRID = (0.5, 1.0, 1.5, 2.0, 3.0)

    def levels(self, profile: DemandProfile) -> Levels:
        raise TypeError("cost-based needs a SKU's costs and history: call levels_for(policy, PolicyInput(...))")

    def order_quantity(self, item: PolicyInput) -> float:
        """``Q``: the economic order quantity, at most one order for the whole history; 0 when ordering is
        free (which wins when holding is free too), the cap when only holding is free."""
        cm = self.cost_model
        mu = item.profile.mean
        cap = mu * len(item.history)
        if cm.order_fixed_cost == 0:
            return 0.0  # ordering is free: order up to s at every review
        daily_holding = item.unit_cost * cm.holding_cost_annual_rate / cm.working_days_per_year
        if daily_holding == 0:
            return cap  # holding is free: one order for the whole history
        return min(math.sqrt(2 * cm.order_fixed_cost * mu / daily_holding), cap)

    def levels_for(self, item: PolicyInput) -> Levels:
        from .engine import simulate_candidates

        cm = self.cost_model
        protect = self.lead_time_days + self.review_days
        sigma = item.profile.variability
        zs = np.repeat(np.array(self.Z_GRID), len(self.LOT_GRID))  # s-major, so the first minimum is the tie-break
        lots = np.tile(np.array(self.LOT_GRID), len(self.Z_GRID)) * self.order_quantity(item)
        s = item.profile.mean * protect + zs * sigma * math.sqrt(protect)
        unmet, holding, orders = simulate_candidates(item.history, s, s + lots, lead_time_days=self.lead_time_days)
        daily_holding = item.unit_cost * cm.holding_cost_annual_rate / cm.working_days_per_year
        margin = item.unit_price - item.unit_cost
        cost = holding * daily_holding + orders * cm.order_fixed_cost + unmet * margin * cm.stockout_penalty_mult
        best = int(np.argmin(cost))  # the first of equal costs: the smaller s, then the smaller order
        return Levels(
            reorder_point=float(s[best]),
            order_up_to=float(s[best] + lots[best]),
            safety_stock=float(zs[best] * sigma * math.sqrt(protect)),
        )


def policy_input(
    sku_id: str, history: Sequence[float], skus: dict, profile: DemandProfile | None = None
) -> PolicyInput:
    """The ``PolicyInput`` of ``sku_id`` from its history and the SKU stream (``skus``: sku_id -> SKU)."""
    sku = skus.get(sku_id)
    return PolicyInput(
        sku_id=sku_id,
        profile=profile if profile is not None else DemandProfile.of(history),
        history=tuple(history),
        unit_cost=sku.unit_cost if sku is not None else DEFAULT_UNIT_COST,
        unit_price=sku.unit_price if sku is not None else DEFAULT_UNIT_PRICE,
    )


@dataclass(frozen=True)
class PlanRow:
    sku_id: str
    name: str
    profile: DemandProfile
    safety_stock: float
    reorder_point: float
    order_up_to: float
    available: int
    order_qty: int


def plan_orders(world: World, policy: Policy) -> list[PlanRow]:
    """Apply ``policy`` to every SKU with demand; rows sorted by order quantity, largest first."""
    table = world.demand()
    skus = {s.sku_id: s for s in world.stream("SKU")}
    avail: dict[str, int] = {}
    for snap in world.stream("InventorySnapshot"):
        avail[snap.sku_id] = avail.get(snap.sku_id, 0) + snap.available
    rows: list[PlanRow] = []
    for sku in table.series:
        profile = table.profile(sku)
        if profile.mean <= 0:
            continue  # no demand in the window: nothing to protect
        lv = levels_for(policy, policy_input(sku, table.series[sku], skus, profile))
        on_hand = avail.get(sku, 0)
        order = max(0, round(lv.order_up_to - on_hand)) if on_hand <= lv.reorder_point else 0
        rows.append(
            PlanRow(
                sku_id=sku,
                name=skus[sku].name if sku in skus else "?",
                profile=profile,
                safety_stock=lv.safety_stock,
                reorder_point=lv.reorder_point,
                order_up_to=lv.order_up_to,
                available=on_hand,
                order_qty=order,
            )
        )
    rows.sort(key=lambda r: r.order_qty, reverse=True)
    return rows
