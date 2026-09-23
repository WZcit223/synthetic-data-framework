"""Tests for WarehouseIntelligence."""

from __future__ import annotations

from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from .intelligence import WarehouseIntelligence


def test_application_layer_runs():
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=30))
    intel = WarehouseIntelligence(reg)
    k = intel.kpis()
    assert k.total_skus == 60
    assert [p["policy"] for p in intel.replenishment_comparison()["policies"]] == ["naive", "service-level-95"]
    assert len(intel.insights()) >= 3


def test_vision_stocktake():
    _, reg = build_registry(GenerationSpec(n_skus=120, horizon_days=45))
    intel = WarehouseIntelligence(reg)
    grid = intel.shelf_occupancy_grid()
    assert grid and all("zone" in z and "aisles" in z for z in grid)
    stock = intel.stocktake_discrepancies()
    # Most locations should match; some flagged. Sanity, not a fidelity claim.
    assert stock["locations_scanned"] > 0
    assert stock["matched"] + stock["flagged"] == stock["locations_scanned"]
    assert 0.0 <= stock["match_rate"] <= 1.0


def test_phase3_ss_policy():
    _, reg = build_registry(GenerationSpec(n_skus=80, horizon_days=45))
    intel = WarehouseIntelligence(reg)
    lo = intel.replenishment_ss_policy(service_level=0.90)
    hi = intel.replenishment_ss_policy(service_level=0.99)
    # Higher service level => more safety stock (monotone in z).
    assert hi["total_safety_stock_units"] >= lo["total_safety_stock_units"]
    assert hi["z"] > lo["z"]
    for r in lo["rows"]:
        assert r["reorder_point_s"] >= r["safety_stock"] >= 0


def test_numeric_options_are_keyword_only(default_world):
    import pytest

    _, _, intel = default_world
    with pytest.raises(TypeError):
        intel.replenishment_ss_policy(0.95)  # would silently mean lead_time_days=0.95
    with pytest.raises(TypeError):
        intel.stocktake_discrepancies(0.3)
    with pytest.raises(TypeError):
        intel.replenishment_comparison(0.95)


def test_demand_series_forecast_is_a_calendar_day_rate():
    from datetime import datetime

    from sdf.foundation.registry import DataSourceRegistry
    from sdf.foundation.schema import OutboundOrder

    def order(day, qty):
        return OutboundOrder(
            order_id=f"o{day}",
            ts=datetime(2025, 1, day, 9),
            sku_id="S",
            quantity=qty,
            channel="store",
            priority="standard",
            status="shipped",
        )

    reg = DataSourceRegistry()
    reg.register("orders", "OutboundOrder", [order(1, 1), order(5, 20), order(10, 1)])
    res = WarehouseIntelligence(reg).demand_series("S")
    assert [h["qty"] for h in res["history"]] == [1, 20, 1]  # selling days only, for the chart
    assert res["forecast_avg_daily"] == 2.2  # 22 units over 10 calendar days, not 22 / 3
