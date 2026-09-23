"""Replay a demand history under (s, S) levels, one SKU at a time."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from .policy import Levels


@dataclass(frozen=True)
class InventoryTrace:
    unmet_units: float
    holding_unit_days: float
    orders: int
    total_demand: float

    @property
    def fill_rate(self) -> float:
        """Share of demand served from stock (1.0 when there was no demand)."""
        return 1.0 - self.unmet_units / self.total_demand if self.total_demand > 0 else 1.0


def simulate_inventory(demand: Sequence[float], levels: Levels, *, lead_time_days: int) -> InventoryTrace:
    """Start at S, serve each day's demand, reorder up to S when stock + inbound ≤ s.

    Orders arrive ``lead_time_days`` later; unmet demand is lost, not back-ordered.
    """
    s, S = levels.reorder_point, levels.order_up_to
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
                pipeline[t + lead_time_days] += qty
                orders += 1
    return InventoryTrace(
        unmet_units=unmet, holding_unit_days=holding_unit_days, orders=orders, total_demand=sum(demand)
    )
