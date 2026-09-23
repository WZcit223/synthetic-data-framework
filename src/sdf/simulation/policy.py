"""Replenishment policies: how much stock to hold, given a SKU's demand profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sdf.analytics.demand import DemandProfile
from .world import World

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
        return f"service-level-z{self.z}" if self.z is not None else f"service-level-{round(self.service_level * 100)}"

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
        lv = policy.levels(profile)
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
