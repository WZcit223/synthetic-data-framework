"""Tests for the replenishment module."""

from __future__ import annotations

from .replenishment import demand_series, policy_comparison, ss_policy


def test_policies_on_the_default_world(default_world):
    _, reg, _ = default_world
    policy = ss_policy(reg, service_level=0.95)
    assert policy["skus_needing_order"] == 62
    assert all(r["reorder_point_s"] >= r["safety_stock"] >= 0 for r in policy["rows"])


def test_policy_comparison_on_the_default_world(default_world):
    _, reg, _ = default_world
    res = policy_comparison(reg, service_level=0.95)
    naive, ours = res["policies"]
    assert (naive["policy"], ours["policy"], res["horizon_days"]) == ("naive", "service-level-95", 90)
    assert (naive["unmet_units"], ours["unmet_units"]) == (5269, 0)
    assert (naive["safety_stock_units"], ours["safety_stock_units"]) == (0, 4541)
    assert ours["skus_needing_order"] == 62
    assert naive["fill_rate"] < ours["fill_rate"] == 1.0
    assert ours["holding_cost"] > naive["holding_cost"]


def test_demand_series_shape(default_world):
    _, reg, intel = default_world
    sku = intel.top_movers(1)[0]["sku_id"]
    res = demand_series(reg, sku)
    assert res["history"] and res["forecast_total"] == round(res["forecast_avg_daily"] * 14, 1)
