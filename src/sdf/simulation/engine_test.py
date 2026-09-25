"""Tests for the inventory replay."""

from __future__ import annotations

from .engine import InventoryTrace, simulate_inventory
from .policy import Levels


def test_contract_example_traced_by_hand():
    # day 0: 12-5=7 · day 1: 7 · day 2: 9 wanted, 7 served, order 12 due day 4 · day 3: 4 unmet
    trace = simulate_inventory([5.0, 0.0, 9.0, 4.0], Levels(reorder_point=6.0, order_up_to=12.0), lead_time_days=2)
    assert trace == InventoryTrace(unmet_units=6.0, holding_unit_days=14.0, orders=1, total_demand=18.0)
    assert trace.fill_rate == 1 - 6 / 18


def test_orders_arrive_after_the_lead_time():
    trace = simulate_inventory([6.0, 6.0, 6.0, 6.0], Levels(reorder_point=6.0, order_up_to=12.0), lead_time_days=1)
    # day 0: 6 left → order 6 (due day 1) · day 1: 6+6-6=6 → order 6 · days 2–3 repeat; never short
    assert (trace.unmet_units, trace.orders) == (0.0, 4)


def test_no_demand_means_full_fill_rate():
    trace = simulate_inventory([], Levels(reorder_point=1.0, order_up_to=2.0), lead_time_days=1)
    assert (trace.fill_rate, trace.orders) == (1.0, 0)


def test_many_pairs_replay_exactly_as_one_pair_does():
    import random

    import numpy as np

    from .engine import simulate_candidates

    rng = random.Random(3)
    for _ in range(200):
        days, lead = rng.randint(1, 60), rng.randint(1, 12)
        demand = [float(rng.choice([0, 0, 1, 2, 3, 5, 8, 13, 40])) for _ in range(days)]
        s = np.array([rng.uniform(0, 60) for _ in range(5)])
        big_s = s + np.array([rng.choice([0.0, rng.uniform(0, 50)]) for _ in range(5)])
        unmet, holding, orders = simulate_candidates(demand, s, big_s, lead_time_days=lead)
        for i in range(5):
            one = simulate_inventory(demand, Levels(reorder_point=s[i], order_up_to=big_s[i]), lead_time_days=lead)
            assert (one.unmet_units, one.holding_unit_days, one.orders) == (unmet[i], holding[i], orders[i])
