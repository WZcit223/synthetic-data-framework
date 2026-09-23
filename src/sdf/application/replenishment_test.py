"""Tests for the replenishment module."""

from __future__ import annotations

from .replenishment import demand_series, rule_simulation, rule_suggestions, ss_policy


def test_policies_on_the_default_world(default_world):
    _, reg, _ = default_world
    assert len(rule_suggestions(reg, 9999)) == 7
    assert rule_simulation(reg)["stockouts_before"] == 2
    policy = ss_policy(reg, service_level=0.95)
    assert policy["skus_needing_order"] == 62
    assert all(r["reorder_point_s"] >= r["safety_stock"] >= 0 for r in policy["rows"])


def test_demand_series_shape(default_world):
    _, reg, intel = default_world
    sku = intel.top_movers(1)[0]["sku_id"]
    res = demand_series(reg, sku)
    assert res["history"] and res["forecast_total"] == round(res["forecast_avg_daily"] * 14, 1)
