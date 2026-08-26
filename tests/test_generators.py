"""Framework-mode tests: determinism + structural integrity (no stat validation)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sdf.synthesis.warehouse import WarehouseGenerator, GenerationSpec
from sdf.synthesis.quality import structural_quality_check
from sdf.cli import build_registry
from sdf.application.warehouse_demo import WarehouseIntelligence


def test_deterministic_seed():
    a = WarehouseGenerator(GenerationSpec(seed=7, n_skus=50)).generate()
    b = WarehouseGenerator(GenerationSpec(seed=7, n_skus=50)).generate()
    assert [s.sku_id for s in a.skus] == [s.sku_id for s in b.skus]
    assert len(a.outbound) == len(b.outbound)


def test_structural_quality_passes():
    wh = WarehouseGenerator(GenerationSpec(n_skus=80)).generate()
    report = structural_quality_check(wh)
    assert report.passed, report.to_dict()


def test_counts_match_spec():
    spec = GenerationSpec(n_skus=123, n_locations=45)
    wh = WarehouseGenerator(spec).generate()
    assert len(wh.skus) == 123
    assert len(wh.locations) == 45


def test_application_layer_runs():
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=30))
    intel = WarehouseIntelligence(reg)
    k = intel.kpis()
    assert k.total_skus == 60
    assert isinstance(intel.replenishment_suggestions(5), list)
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


def test_phase2_adapter_and_backtest():
    import os
    from sdf.foundation.adapters.retail_csv import load_online_retail_csv
    from sdf.synthesis.forecast import daily_demand_series, compare_models
    path = os.path.join(os.path.dirname(__file__), "..",
                        "data", "sample_online_retail_ii.csv")
    skus, orders = load_online_retail_csv(path)
    assert skus and orders
    assert all(o.quantity > 0 for o in orders)          # abs() applied
    series = daily_demand_series(orders)
    assert len(series) > 30
    report = compare_models(series, test_len=21)
    assert report["best_model"] in {"mean", "naive", "ma7", "snaive7"}
    # every model must produce finite, non-negative error metrics
    for r in report["results"]:
        assert r["MAE"] >= 0 and r["RMSE"] >= 0


def test_phase2_fitted_synthesis_fidelity():
    import os
    from sdf.foundation.adapters.retail_csv import load_online_retail_csv
    from sdf.synthesis.fit import FittedHourlyDemand
    from sdf.synthesis.fidelity import fidelity_report, ks_2samp, pearson
    assert ks_2samp([1, 2, 3], [1, 2, 3]) == 0.0
    assert pearson([1, 2, 3], [2, 4, 6]) == 1.0
    path = os.path.join(os.path.dirname(__file__), "..",
                        "data", "sample_online_retail_ii.csv")
    _skus, orders = load_online_retail_csv(path)
    model = FittedHourlyDemand().fit(orders)
    synth = model.generate()
    rep = fidelity_report(model.real_series, synth, model.ppd)
    assert 0.0 <= rep["ks_statistic"] <= 1.0
    assert -1.0 <= rep["profile_corr"] <= 1.0
    assert 0.0 <= rep["fidelity_score"] <= 100.0


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


def test_phase3_anomaly_c3():
    from sdf.synthesis.anomaly import seasonal_residual_anomalies
    series = [100 + [10, 12, 9, 11, 13, 8, 3][i % 7] for i in range(84)]
    series[40] = 900  # injected spike
    found = seasonal_residual_anomalies(series, 7, k=3.5)
    assert any(a["index"] == 40 and a["direction"] == "spike" for a in found)
    # Application wiring finds the injected generator shocks.
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=90))
    intel = WarehouseIntelligence(reg)
    a = intel.demand_anomalies()
    assert a["count"] >= 1


def test_phase4_knowledge_qa_c6():
    from sdf.application.knowledge import KnowledgeQA
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=45))
    qa = KnowledgeQA(WarehouseIntelligence(reg))
    assert qa.ask("which SKUs are stockout?")["intent"] == "stockouts"
    assert qa.ask("safety stock at 95%?")["intent"] == "safety_stock"
    assert qa.ask("any demand anomalies?")["intent"] == "anomaly"
    assert qa.ask("how good is the forecast?")["intent"] == "forecast"
    # Unknown question falls back to help, still grounded (no crash).
    assert "answer" in qa.ask("tell me a joke")


def test_phase21_sdv_optional():
    """Gaussian-copula + SDMetrics; skipped when optional libs are absent."""
    import os
    try:
        from sdf.synthesis.sdv_synth import gaussian_copula_fidelity
        path = os.path.join(os.path.dirname(__file__), "..",
                            "data", "online_retail_ii_2010_10k.csv")
        rep = gaussian_copula_fidelity(path, max_rows=400)
    except ImportError:
        print("SKIP test_phase21_sdv_optional (copulas/sdmetrics not installed)")
        return
    assert 0.0 <= rep["sdmetrics_overall"] <= 1.0
    assert set(rep["column_shape_ks"]) == {"Quantity", "Price", "hour", "weekday"}


def test_phase3_model_and_tstr():
    import os
    from sdf.synthesis.models import seasonal_linear
    from sdf.synthesis.forecast import backtest, seasonal_naive
    from sdf.foundation.adapters.retail_csv import load_online_retail_csv
    from sdf.synthesis.tstr import tstr_report
    # Model beats seasonal-naive on a clean trend+season series.
    vals = [10 + 0.8 * i + [10, 12, 9, 11, 13, 8, 3][i % 7] for i in range(120)]
    assert backtest(vals, seasonal_linear(7), 21)["MAE"] < \
        backtest(vals, seasonal_naive(7), 21)["MAE"]
    # TSTR ratio is finite and reasonable on the sample.
    path = os.path.join(os.path.dirname(__file__), "..",
                        "data", "sample_online_retail_ii.csv")
    _skus, orders = load_online_retail_csv(path)
    r = tstr_report(orders)
    assert r["ratio_tstr_over_trtr"] is not None
    assert 0.3 <= r["ratio_tstr_over_trtr"] <= 3.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
