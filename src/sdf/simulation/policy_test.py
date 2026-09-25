"""Tests for the replenishment policies and ``plan_orders``."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import pytest

from sdf.analytics.demand import DemandProfile
from .engine import simulate_inventory
from .outcome import CostModel, SimulatedCost
from .policy import (
    CostBasedPolicy,
    Levels,
    NaivePolicy,
    PolicyInput,
    ServiceLevelPolicy,
    levels_for,
    plan_orders,
    z_for,
)


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


def test_name_keeps_a_fractional_service_level():
    assert ServiceLevelPolicy(service_level=0.975).name == "service-level-97.5"
    assert ServiceLevelPolicy(service_level=0.9).name == "service-level-90"


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


# -- the SKU a policy sees, and the cost-based policy (interfaces.md §5.2, §5.3) -----------------------

HISTORY = (4.0, 0.0, 9.0, 3.0, 0.0, 12.0, 5.0, 2.0, 0.0, 7.0, 6.0, 0.0, 15.0, 3.0) * 4


def item(history=HISTORY, unit_cost=2.0, unit_price=5.0) -> PolicyInput:
    return PolicyInput("S", DemandProfile.of(history), tuple(history), unit_cost, unit_price)


def test_levels_for_uses_the_policy_s_own_method_or_its_profile_levels():
    it = item()
    sl = ServiceLevelPolicy(0.95)
    assert levels_for(sl, it) == sl.levels(it.profile)  # no levels_for: the profile's levels, as before
    assert levels_for(FixedCoverPolicy(), it) == FixedCoverPolicy().levels(it.profile)
    with pytest.raises(TypeError, match="needs a SKU's costs and history"):
        CostBasedPolicy().levels(it.profile)


def _brute_force(policy: CostBasedPolicy, it: PolicyInput):
    cm = policy.cost_model
    protect = policy.lead_time_days + policy.review_days
    daily_holding = it.unit_cost * cm.holding_cost_annual_rate / cm.working_days_per_year
    q = policy.order_quantity(it)
    best = None
    for z, m in itertools.product(policy.Z_GRID, policy.LOT_GRID):  # s ascending, then the order size
        s = it.profile.mean * protect + z * it.profile.variability * math.sqrt(protect)
        tr = simulate_inventory(it.history, Levels(s, s + m * q), lead_time_days=policy.lead_time_days)
        cost = (
            tr.holding_unit_days * daily_holding
            + tr.orders * cm.order_fixed_cost
            + tr.unmet_units * (it.unit_price - it.unit_cost) * cm.stockout_penalty_mult
        )
        if best is None or cost < best[0]:
            best = (cost, s, s + m * q)
    return best


@pytest.mark.parametrize("costs", [(2.0, 5.0), (10.0, 11.0), (0.5, 40.0)])
def test_the_search_finds_what_a_brute_force_over_the_same_grid_finds(costs):
    it = item(unit_cost=costs[0], unit_price=costs[1])
    policy = CostBasedPolicy()
    lv = levels_for(policy, it)
    _, s, big_s = _brute_force(policy, it)
    assert (lv.reorder_point, lv.order_up_to) == (s, big_s)


def test_the_grid_is_the_contract_s():
    assert CostBasedPolicy.Z_GRID == (0.0, 0.5, 1.0, 1.28, 1.645, 2.0, 2.5, 3.0)
    assert CostBasedPolicy.LOT_GRID == (0.5, 1.0, 1.5, 2.0, 3.0)
    assert (CostBasedPolicy().name, CostBasedPolicy().lead_time_days, CostBasedPolicy().review_days) == (
        "cost-based",
        7,
        7,
    )


def test_ties_go_to_the_smaller_reorder_point_then_the_smaller_order():
    # no margin and free holding: only orders cost. From 1.5 times one order for the whole history, the
    # stock never falls to s, so every such candidate costs 0 at every z; smaller orders reorder.
    it = item(unit_cost=3.0, unit_price=3.0)
    policy = CostBasedPolicy(cost_model=CostModel(holding_cost_annual_rate=0.0))
    q = policy.order_quantity(it)
    assert q == it.profile.mean * len(it.history) and it.profile.variability > 0
    lv = policy.levels_for(it)
    s0 = it.profile.mean * 14  # z = 0: the smallest reorder point
    assert (lv.reorder_point, lv.order_up_to) == (s0, s0 + 1.5 * q)  # of the 24 zero-cost ties, the first


def test_the_levels_come_from_the_item_alone():
    it = item()
    assert levels_for(CostBasedPolicy(), it) == levels_for(
        CostBasedPolicy(), PolicyInput("other", it.profile, it.history, 2.0, 5.0)
    )
    longer = PolicyInput("S", DemandProfile.of(HISTORY + (100.0,) * 7), HISTORY + (100.0,) * 7, 2.0, 5.0)
    assert levels_for(CostBasedPolicy(), longer) != levels_for(CostBasedPolicy(), it)  # the history is what it reads


def test_free_ordering_orders_up_to_s_and_free_holding_orders_once():
    it = item()
    free_orders = CostBasedPolicy(cost_model=CostModel(order_fixed_cost=0.0))
    assert free_orders.order_quantity(it) == 0.0
    lv = free_orders.levels_for(it)
    assert lv.order_up_to == lv.reorder_point
    for cm in (CostModel(holding_cost_annual_rate=0.0), CostModel()):
        policy = CostBasedPolicy(cost_model=cm)
        cheap = PolicyInput("S", it.profile, it.history, 0.0, 5.0) if cm.holding_cost_annual_rate else it
        assert policy.order_quantity(cheap) == it.profile.mean * len(it.history)  # one order for the history
        policy.levels_for(cheap)  # no division by zero


def test_with_no_margin_there_is_no_safety_stock():
    lv = CostBasedPolicy().levels_for(item(unit_cost=3.0, unit_price=3.0))
    assert lv.safety_stock == 0.0 and lv.reorder_point == item().profile.mean * 14


def test_plan_orders_asks_levels_for_with_the_sku_s_costs(world):
    rows = {r.sku_id: r for r in plan_orders(world, CostBasedPolicy())}
    skus = {s.sku_id: s for s in world.stream("SKU")}
    sku = next(iter(rows))
    table = world.demand()
    expected = CostBasedPolicy().levels_for(
        PolicyInput(sku, table.profile(sku), table.series[sku], skus[sku].unit_cost, skus[sku].unit_price)
    )
    assert (rows[sku].reorder_point, rows[sku].order_up_to) == (expected.reorder_point, expected.order_up_to)
    # the existing policies plan exactly as before
    before = {r.sku_id: r.reorder_point for r in plan_orders(world, ServiceLevelPolicy(0.95))}
    assert before == {s: ServiceLevelPolicy(0.95).levels(table.profile(s)).reorder_point for s in before}


def test_the_holdout_replay_fits_on_the_days_before_and_scores_the_last_ones(world):
    in_sample = SimulatedCost(CostModel()).measure(world, ServiceLevelPolicy(0.95))
    assert set(in_sample) == {"unmet_units", "fill_rate", "holding_cost", "order_cost", "lost_margin"}
    out = SimulatedCost(CostModel(), holdout_days=30).measure(world, ServiceLevelPolicy(0.95))
    assert set(out) == {f"holdout_{k}" for k in (*in_sample, "total_cost")}
    assert (
        out["holdout_total_cost"]
        == out["holdout_holding_cost"] + out["holdout_order_cost"] + out["holdout_lost_margin"]
    )
    days = len(world.demand().days)
    with pytest.raises(ValueError, match=f"holdout_days {days} is not shorter than the history's {days} days"):
        SimulatedCost(CostModel(), holdout_days=days).measure(world, ServiceLevelPolicy(0.95))
    with pytest.raises(ValueError, match=f"holdout_days {days - 10} leaves 10 of the history's {days} days to fit on"):
        SimulatedCost(CostModel(), holdout_days=days - 10).measure(world, ServiceLevelPolicy(0.95))
    with pytest.raises(ValueError, match="holdout_days must be a whole number of days"):
        SimulatedCost(CostModel(), holdout_days=0)


def test_on_the_default_world_the_cost_based_policy_costs_far_less_out_of_sample(world):
    outcome = SimulatedCost(CostModel(), holdout_days=30)
    sl = outcome.measure(world, ServiceLevelPolicy(0.95))
    cb = outcome.measure(world, CostBasedPolicy())
    assert cb["holdout_total_cost"] <= 0.7 * sl["holdout_total_cost"]  # at least 30 % less
    assert cb["holdout_fill_rate"] >= 0.99


@dataclass(frozen=True)
class SeesWhatItGets:
    """Records what levels_for is given."""

    seen: list
    lead_time_days: int = 7
    name: str = "spy"

    def levels(self, profile):
        raise AssertionError("levels_for is asked, not levels")

    def levels_for(self, item):
        self.seen.append(item)
        return ServiceLevelPolicy(0.95).levels(item.profile)


def test_the_holdout_levels_see_only_the_days_before_the_held_out_ones(world):
    seen = []
    SimulatedCost(CostModel(), holdout_days=30).measure(world, SeesWhatItGets(seen))
    table = world.demand()
    for it in seen:
        fit = table.series[it.sku_id][:-30]
        assert it.history == tuple(fit) and it.profile == DemandProfile.of(fit)
    assert seen and all(len(it.history) == len(table.days) - 30 for it in seen)
