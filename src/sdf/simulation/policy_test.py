"""Tests for the replenishment policies and ``plan_orders``."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sdf.analytics.demand import DemandProfile
from .policy import Levels, NaivePolicy, ServiceLevelPolicy, plan_orders, z_for


@dataclass(frozen=True)
class FixedCoverPolicy:
    """The contract's minimal extension (interfaces.md §1.2)."""

    days: int = 10
    lead_time_days: int = 7
    name: str = "cover-10d"

    def levels(self, profile):
        s = profile.mean * self.days
        return Levels(reorder_point=s, order_up_to=s)


SMOOTH = DemandProfile(mean=10.0, std=3.0, zero_ratio=0.0)


def test_z_lookup_uses_the_nearest_service_level():
    assert z_for(0.95) == 1.645 and z_for(0.951) == 1.645 and z_for(0.99) == 2.326


def test_service_level_policy_levels_and_name():
    p = ServiceLevelPolicy(service_level=0.95)
    assert (p.name, p.lead_time_days, p.review_days) == ("service-level-95", 7, 7)
    lv = p.levels(SMOOTH)
    ss = 1.645 * 3.0 * 14**0.5
    assert lv.safety_stock == pytest.approx(ss)
    assert lv.reorder_point == pytest.approx(140 + ss) and lv.order_up_to == lv.reorder_point


def test_explicit_z_overrides_the_table():
    p = ServiceLevelPolicy(z=2.0)
    assert (p.name, p.effective_z) == ("service-level-z2.0", 2.0)
    assert p.levels(SMOOTH).safety_stock == pytest.approx(2.0 * 3.0 * 14**0.5)


def test_naive_policy_holds_no_safety_stock():
    assert NaivePolicy().levels(SMOOTH) == Levels(reorder_point=70.0, order_up_to=140.0, safety_stock=0.0)


def test_plan_orders_matches_the_golden_count(world):
    plan = plan_orders(world, ServiceLevelPolicy(service_level=0.95))
    assert [r.order_qty for r in plan] == sorted((r.order_qty for r in plan), reverse=True)
    assert sum(1 for r in plan if r.order_qty > 0) == 62
    assert round(sum(r.safety_stock for r in plan)) == 4541


def test_any_object_with_the_protocol_members_is_a_policy(small_world):
    plan = plan_orders(small_world, FixedCoverPolicy())
    assert plan and all(r.safety_stock == 0.0 for r in plan)
    for r in plan:
        assert r.reorder_point == pytest.approx(r.profile.mean * 10)
        expected = max(0, round(r.order_up_to - r.available)) if r.available <= r.reorder_point else 0
        assert r.order_qty == expected
