"""Replay a demand history under (s, S) levels, one SKU at a time."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

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


def simulate_candidates(
    demand: Sequence[float], reorder_points: np.ndarray, order_up_tos: np.ndarray, *, lead_time_days: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``simulate_inventory`` for many (s, S) pairs at once: unmet units, holding unit-days and orders, per pair.

    The same rules, applied to every pair in step, and the same arithmetic in the same
    order (the inbound is summed over the arriving days oldest first, as the one-pair
    replay sums its pipeline), so each pair's numbers equal ``simulate_inventory``'s exactly.
    """
    s = np.asarray(reorder_points, dtype=float)
    big_s = np.asarray(order_up_tos, dtype=float)
    days = len(demand)
    arriving = np.zeros((len(s), days + lead_time_days + 1))  # day -> quantity arriving, per pair
    on_hand = big_s.copy()
    unmet = np.zeros(len(s))
    holding = np.zeros(len(s))
    orders = np.zeros(len(s), dtype=int)
    for t, dmd in enumerate(demand):
        on_hand = on_hand + arriving[:, t]
        fill = np.minimum(on_hand, dmd)
        unmet = unmet + np.maximum(0.0, dmd - fill)
        on_hand = on_hand - fill
        holding = holding + on_hand
        inbound = np.zeros(len(s))
        for k in range(t + 1, t + lead_time_days + 1):
            inbound = inbound + arriving[:, k]
        position = on_hand + inbound
        qty = np.maximum(0.0, big_s - position)
        place = (position <= s) & (qty > 0)
        arriving[place, t + lead_time_days] += qty[place]
        orders = orders + place
    return unmet, holding, orders
