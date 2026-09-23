"""Tests for seasonal-residual anomaly detection."""

from __future__ import annotations

from sdf.application.intelligence import WarehouseIntelligence
from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from .anomaly import seasonal_residual_anomalies


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


def test_sparse_and_flat_series_have_no_false_anomalies():
    from .anomaly import residual_scale

    assert seasonal_residual_anomalies([0.0] * 40 + [1.0], 7) == []  # one unit sold is not an anomaly
    assert seasonal_residual_anomalies([5.0] * 30, 7) == []
    assert residual_scale([0.0] * 40 + [1.0]) == (1.0, "floor")
    assert residual_scale([0.0] * 20 + [50.0] * 5 + [-50.0] * 5)[1] == "mean_abs_dev"
    assert residual_scale([float(i % 13) * 10 for i in range(40)])[1] == "mad"


def test_a_large_spike_on_a_sparse_series_is_still_found():
    series = [0.0, 0.0, 2.0, 0.0, 1.0, 0.0, 0.0] * 6
    series[30] = 40.0
    found = seasonal_residual_anomalies(series, 7)
    assert [a["index"] for a in found] == [30]
