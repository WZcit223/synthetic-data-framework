"""Tests for seasonal-residual anomaly detection."""

from __future__ import annotations

from sdf.application.warehouse_demo import WarehouseIntelligence
from .anomaly import seasonal_residual_anomalies
from .materialise import build_registry
from .spec import GenerationSpec


def test_phase3_anomaly_c3():
    series = [100 + [10, 12, 9, 11, 13, 8, 3][i % 7] for i in range(84)]
    series[40] = 900  # injected spike
    found = seasonal_residual_anomalies(series, 7, k=3.5)
    assert any(a["index"] == 40 and a["direction"] == "spike" for a in found)
    # Application wiring finds the injected generator shocks.
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=90))
    intel = WarehouseIntelligence(reg)
    a = intel.demand_anomalies()
    assert a["count"] >= 1
