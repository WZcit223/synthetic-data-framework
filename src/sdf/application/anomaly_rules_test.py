"""Tests for the anomaly rules module."""

from __future__ import annotations

from .anomaly_rules import demand_anomalies, rule_anomalies


def test_rule_and_demand_anomalies(default_world):
    _, reg, _ = default_world
    found = rule_anomalies(reg)
    assert sum(1 for a in found if a["type"] == "stockout") == 2
    a = demand_anomalies(reg)
    assert a["count"] == 3 and a["anomalies"][0]["index"] == 37
