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
