"""The world's daily signals per SKU, for the anomaly detectors: demand, and the stock of a replayed policy.

The world holds one stock snapshot and a few inbound orders, not a daily stock
record, so ``on_hand`` and ``receipts`` come from replaying each SKU's demand under
a policy (``simulate_inventory(record=True)``), as the simulated cost does. A SKU
without demand is not replayed: its stock and receipts are unknown (``nan``). The
contract is ``docs/refactor/algorithms/interfaces.md`` §6.2.
"""

from __future__ import annotations

import numpy as np

from sdf.analytics.detectors import SignalFrame
from .engine import simulate_inventory
from .policy import Policy, ServiceLevelPolicy, levels_for, policy_input
from .world import World


def signal_frame(world: World, policy: Policy | None = None) -> SignalFrame:
    """``demand``, ``on_hand`` and ``receipts`` for every SKU of the world's demand table and every day of it."""
    policy = policy if policy is not None else ServiceLevelPolicy()
    table = world.demand()
    skus = {s.sku_id: s for s in world.stream("SKU")}
    sku_ids = tuple(table.series)
    shape = (len(sku_ids), len(table.days))
    demand = np.array([table.series[k] for k in sku_ids], dtype=float).reshape(shape)
    on_hand = np.full(shape, np.nan)
    receipts = np.full(shape, np.nan)
    for i, sku in enumerate(sku_ids):
        profile = table.profile(sku)
        if profile.mean <= 0:
            continue  # nothing to replay: no policy is asked about a SKU without demand
        levels = levels_for(policy, policy_input(sku, table.series[sku], skus, profile))
        trace = simulate_inventory(table.series[sku], levels, lead_time_days=policy.lead_time_days, record=True)
        on_hand[i] = trace.on_hand
        receipts[i] = trace.receipts
    return SignalFrame(
        days=table.days, sku_ids=sku_ids, signals={"demand": demand, "on_hand": on_hand, "receipts": receipts}
    )
