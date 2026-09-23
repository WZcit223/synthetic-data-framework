"""Tests for the KPI module."""

from __future__ import annotations

from .kpi import abc_distribution, kpis, top_movers


def test_kpis_abc_and_top_movers(default_world):
    _, reg, _ = default_world
    k = kpis(reg)
    assert (k.total_skus, k.total_on_hand, k.outbound_lines) == (200, 25719, 28897)
    assert sum(abc_distribution(reg).values()) == 200
    movers = top_movers(reg, 3)
    assert len(movers) == 3
    assert movers[0]["avg_daily_demand"] >= movers[-1]["avg_daily_demand"]
