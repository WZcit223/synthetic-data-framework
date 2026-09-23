"""Characterisation tests: the golden numbers from ``docs/REFACTOR_PREP.md`` §2.5.

These lock the behaviour of the default world and the two bundled CSVs so the
pure-move refactor PRs can be verified mechanically. Integers match exactly;
floats match to ±0.5 %. A change that moves any of these values must update
this file and the dossier in the same PR and say why.
"""

from __future__ import annotations

import pytest

from .application.agent import WarehouseAgent
from .application.economics import financial_impact
from .application.scenarios import run_scenarios
from .foundation.adapters.retail_csv import load_online_retail_csv
from .synthesis.fidelity import fidelity_report
from .synthesis.fit import FittedHourlyDemand
from .synthesis.forecast import build_series, compare_models, models_for
from .synthesis.privacy import bootstrap_synthesize, privacy_report, read_retail_feature_table
from .synthesis.quality import structural_quality_check
from .synthesis.spec import GenerationSpec
from .synthesis.tstr import tstr_report

REL = 5e-3


def approx(value):
    return pytest.approx(value, rel=REL)


# -- default world ------------------------------------------------------------


def test_registry_counts(default_world):
    _, reg, _ = default_world
    assert reg.summary()["by_entity"] == {
        "SKU": 200,
        "Location": 120,
        "InventorySnapshot": 200,
        "InboundOrder": 180,
        "OutboundOrder": 28897,
        "SensorReading": 624,
    }


def test_structural_quality(default_world):
    wh, _, _ = default_world
    report = structural_quality_check(wh).to_dict()
    assert report["passed"] is True
    assert report["metrics"] == {
        "sku_count": 200.0,
        "location_count": 120.0,
        "outbound_lines": 28897.0,
        "sku_coverage": 1.0,
    }


def test_kpis(default_world):
    _, _, intel = default_world
    k = intel.kpis()
    assert (k.total_skus, k.total_on_hand, k.outbound_lines) == (200, 25719, 28897)
    assert k.inventory_value == approx(4612609.6)
    assert k.cancel_rate == approx(0.0298)
    assert k.express_rate == approx(0.2525)


def test_abc_distribution(default_world):
    _, _, intel = default_world
    assert intel.abc_distribution() == {"A": 39, "B": 55, "C": 106}


def test_rule_replenishment(default_world):
    _, _, intel = default_world
    assert len(intel.replenishment_suggestions(9999)) == 7
    top = intel.replenishment_suggestions(3)
    assert [(s["sku_id"], s["suggested_order_qty"]) for s in top] == [
        ("SKU-00176", 66),
        ("SKU-00114", 19),
        ("SKU-00093", 186),
    ]


def test_replenishment_simulation(default_world):
    _, _, intel = default_world
    sim = intel.replenishment_simulation()
    assert (sim["skus_total"], sim["skus_flagged"], sim["stockouts_before"], sim["stockouts_after"]) == (200, 7, 2, 0)
    assert sim["service_level_before"] == approx(0.965)
    assert sim["service_level_after"] == approx(1.0)


@pytest.mark.parametrize(
    ("service_level", "z", "needing_order", "safety_stock"),
    [(0.90, 1.282, 32, 2952.0), (0.95, 1.645, 38, 3788.0), (0.99, 2.326, 47, 5357.0)],
)
def test_ss_policy(default_world, service_level, z, needing_order, safety_stock):
    _, _, intel = default_world
    policy = intel.replenishment_ss_policy(service_level=service_level)
    assert policy["z"] == approx(z)
    assert policy["skus_needing_order"] == needing_order
    assert policy["total_safety_stock_units"] == approx(safety_stock)


def test_rule_anomalies(default_world):
    _, _, intel = default_world
    found = intel.anomalies()
    assert sum(1 for a in found if a["type"] == "stockout") == 2
    assert sum(1 for a in found if a["type"] == "dead_stock") == 0


def test_demand_anomalies(default_world):
    _, _, intel = default_world
    a = intel.demand_anomalies()
    assert (a["granularity"], a["seasonal_period"], a["series_len"], a["count"]) == ("daily", 7, 90, 3)
    top = a["anomalies"][0]
    assert (top["index"], top["direction"]) == (37, "spike")
    assert top["value"] == approx(2416.0)
    assert top["expected"] == approx(739.0)
    assert top["robust_z"] == approx(35.35)


def test_vision_stocktake(default_world):
    _, _, intel = default_world
    st = intel.stocktake_discrepancies()
    assert (st["locations_scanned"], st["matched"], st["flagged"], st["net_unit_variance"]) == (40, 32, 8, -923)
    assert st["match_rate"] == approx(0.8)


def test_backtest_on_default_world(default_world):
    _, reg, _ = default_world
    series, freq, period = build_series(reg.stream("OutboundOrder"))
    assert (freq, period, len(series)) == ("daily", 7, 90)
    report = compare_models(series, test_len=2 * period, models=models_for(period))
    got = [(r["model"], r["MAE"], r["MAPE_pct"]) for r in report["results"]]
    expected = [
        ("snaive7", 174.071, 14.69),
        ("seas_linear7", 200.903, 18.58),
        ("mean", 226.21, 26.35),
        ("ma7", 277.184, 35.44),
        ("naive", 337.786, 40.99),
    ]
    assert [g[0] for g in got] == [e[0] for e in expected]
    for (_, mae, mape), (_, e_mae, e_mape) in zip(got, expected):
        assert mae == approx(e_mae)
        assert mape == approx(e_mape)


def test_economics(default_world):
    _, _, intel = default_world
    rep = financial_impact(intel)
    assert (rep["skus_considered"], rep["horizon_days"]) == (200, 90)
    assert rep["unmet_units"] == {"naive": 5269, "ours": 17}
    assert rep["stockout_units_avoided"] == 5252
    assert rep["annualised_net_saving"] == approx(1887834)


def test_agent_reorder_and_impact(default_world):
    _, _, intel = default_world
    res = WarehouseAgent(intel).handle("should I reorder and what is the money impact?")
    assert res["plan"] == ["replenishment", "financial_impact"]
    assert res["run"]["steps"] == 3
    assert res["proposed_actions"] == [
        {"proposed_action": "place_order", "sku_id": "SKU-00176", "quantity": 66, "status": "PENDING_APPROVAL"}
    ]


def test_scenarios():
    rows = {r["scenario"]: r for r in run_scenarios(GenerationSpec())["scenarios"]}
    expected = {
        "baseline": (38, 3788.0, 0.0),
        "promo_spike": (66, 5374.0, 41.9),
        "supply_disruption": (50, 3818.0, 0.8),
        "seasonal_downturn": (35, 3275.0, -13.5),
        "high_variability": (52, 4399.0, 16.1),
    }
    assert list(rows) == list(expected)
    for name, (needing, safety, pct) in expected.items():
        assert rows[name]["skus_needing_order"] == needing
        assert rows[name]["safety_stock_units"] == approx(safety)
        assert rows[name]["safety_stock_vs_baseline_pct"] == approx(pct)


# -- bundled CSVs ------------------------------------------------------------


def _csv_metrics(path: str):
    skus, orders = load_online_retail_csv(path)
    series, freq, period = build_series(orders)
    backtest = compare_models(series, test_len=2 * period, models=models_for(period))
    model = FittedHourlyDemand().fit(orders)
    fidelity = fidelity_report(model.real_series, model.generate(), model.ppd)
    tstr = tstr_report(orders)
    real = read_retail_feature_table(path)
    privacy = privacy_report(real, bootstrap_synthesize(real))
    return len(skus), len(orders), freq, period, len(series), backtest, fidelity, tstr, privacy


def test_sample_csv(sample_csv):
    n_skus, n_orders, freq, period, n, backtest, fidelity, tstr, privacy = _csv_metrics(sample_csv)
    assert (n_skus, n_orders, freq, period, n) == (12, 3428, "daily", 7, 139)
    assert [r["model"] for r in backtest["results"]] == ["snaive7", "seas_linear7", "mean", "ma7", "naive"]
    assert backtest["results"][0]["MAE"] == approx(32.786)
    assert backtest["results"][0]["MAPE_pct"] == approx(20.57)
    assert fidelity["ks_statistic"] == approx(0.0197)
    assert fidelity["profile_corr"] == approx(0.9732)
    assert fidelity["fidelity_score"] == approx(95.4)
    assert tstr["TRTR_mae"] == approx(53.634)
    assert tstr["TSTR_mae"] == approx(48.538)
    assert tstr["ratio_tstr_over_trtr"] == approx(0.905)
    assert privacy["dcr_median"] == approx(0.0915)
    assert privacy["dcr_p05"] == approx(0.0205)
    assert privacy["clone_risk_pct"] == approx(4.38)
    assert privacy["verdict"] == "low leakage risk"


def test_real_10k_csv(retail_10k_csv):
    n_skus, n_orders, freq, period, n, backtest, fidelity, tstr, privacy = _csv_metrics(retail_10k_csv)
    assert (n_skus, n_orders, freq, period, n) == (2015, 10000, "hourly", 11, 44)
    assert [r["model"] for r in backtest["results"]] == ["naive", "ma11", "snaive11", "mean", "seas_linear11"]
    assert backtest["results"][0]["MAE"] == approx(950.786)
    assert backtest["results"][0]["MAPE_pct"] == approx(99.04)
    assert fidelity["ks_statistic"] == approx(0.1364)
    assert fidelity["profile_corr"] == approx(0.9036)
    assert fidelity["fidelity_score"] == approx(78.0)
    assert tstr["TRTR_mae"] == approx(2628.928)
    assert tstr["TSTR_mae"] == approx(2635.385)
    assert tstr["ratio_tstr_over_trtr"] == approx(1.002)
    assert privacy["dcr_median"] == approx(0.1086)
    assert privacy["dcr_p05"] == approx(0.0151)
    assert privacy["clone_risk_pct"] == approx(7.62)
    assert privacy["verdict"].startswith("review")
