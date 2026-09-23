"""Characterisation tests: the golden numbers from ``docs/REFACTOR_PREP.md`` §2.5.

Every value is read from the snapshot that ``sdf validate`` prints and
``docs/VALIDATION.md`` embeds (``sdf.application.snapshot``), so the tests, the
command and the document can never disagree. Integers match exactly; floats
match to ±0.5 %. A change that moves any of these values must update this file
and regenerate the document (``uv run sdf validate --update-doc
docs/VALIDATION.md``) in the same PR and say why.
"""

from __future__ import annotations

import pytest

REL = 5e-3


def approx(value):
    return pytest.approx(value, rel=REL)


@pytest.fixture(scope="module")
def world(full_snapshot):
    return full_snapshot["default_world"]


# -- default world ------------------------------------------------------------


def test_registry_counts(world):
    assert world["registry"] == {
        "SKU": 200,
        "Location": 120,
        "InventorySnapshot": 200,
        "InboundOrder": 180,
        "OutboundOrder": 28897,
        "SensorReading": 624,
    }


def test_structural_quality(world):
    assert world["quality"]["passed"] is True
    assert world["quality"]["metrics"] == {
        "sku_count": 200.0,
        "location_count": 120.0,
        "outbound_lines": 28897.0,
        "sku_coverage": 1.0,
    }


def test_kpis(world):
    k = world["kpis"]
    assert (k["total_skus"], k["total_on_hand"], k["outbound_lines"]) == (200, 25719, 28897)
    assert k["inventory_value"] == approx(4612609.6)
    assert k["cancel_rate"] == approx(0.0298)
    assert k["express_rate"] == approx(0.2525)


def test_abc_distribution(world):
    assert world["abc"] == {"A": 39, "B": 55, "C": 106}


def test_rule_replenishment(world):
    rule = world["rule_replenishment"]
    assert rule["skus_flagged"] == 7
    assert [(s["sku_id"], s["suggested_order_qty"]) for s in rule["top"]] == [
        ("SKU-00176", 66),
        ("SKU-00114", 19),
        ("SKU-00093", 186),
    ]


def test_replenishment_simulation(world):
    sim = world["replenishment_simulation"]
    assert (sim["skus_total"], sim["skus_flagged"], sim["stockouts_before"], sim["stockouts_after"]) == (200, 7, 2, 0)
    assert sim["service_level_before"] == approx(0.965)
    assert sim["service_level_after"] == approx(1.0)


@pytest.mark.parametrize(
    ("index", "service_level", "z", "needing_order", "intermittent", "safety_stock"),
    # Before correctness PR 4 (plain std for every SKU): 32/38/47 SKUs, 2952/3788/5357 units.
    [(0, 0.90, 1.282, 44, 24, 3539.0), (1, 0.95, 1.645, 62, 40, 4541.0), (2, 0.99, 2.326, 73, 49, 6421.0)],
)
def test_ss_policy(world, index, service_level, z, needing_order, intermittent, safety_stock):
    policy = world["ss_policy"][index]
    assert policy["service_level"] == approx(service_level)
    assert policy["z"] == approx(z)
    assert policy["skus_needing_order"] == needing_order
    assert policy["intermittent_needing_order"] == intermittent
    assert policy["total_safety_stock_units"] == approx(safety_stock)


def test_rule_anomalies(world):
    assert world["rule_anomalies"] == {"stockout": 2, "dead_stock": 0}


def test_demand_anomalies(world):
    a = world["demand_anomalies"]
    assert (a["granularity"], a["seasonal_period"], a["series_len"], a["count"]) == ("daily", 7, 90, 3)
    top = a["top"]
    assert (top["index"], top["direction"]) == (37, "spike")
    assert top["value"] == approx(2416.0)
    assert top["expected"] == approx(739.0)
    assert top["robust_z"] == approx(35.35)


def test_vision_stocktake(world):
    st = world["stocktake"]
    assert (st["locations_scanned"], st["matched"], st["flagged"], st["net_unit_variance"]) == (40, 32, 8, -923)
    assert st["match_rate"] == approx(0.8)


def test_backtest_on_default_world(world):
    bt = world["backtest"]
    assert (bt["granularity"], bt["seasonal_period"], bt["series_len"]) == ("daily", 7, 90)
    expected = [
        ("snaive7", 174.071, 14.69),
        ("seas_linear7", 200.903, 18.58),
        ("mean", 226.21, 26.35),
        ("ma7", 277.184, 35.44),
        ("naive", 337.786, 40.99),
    ]
    assert [r["model"] for r in bt["results"]] == [e[0] for e in expected]
    for r, (_, e_mae, e_mape) in zip(bt["results"], expected):
        assert r["MAE"] == approx(e_mae)
        assert r["MAPE_pct"] == approx(e_mape)  # unchanged by the MAPE fix: no zero-demand day
    assert [r["WAPE_pct"] for r in bt["results"]] == [approx(v) for v in (23.29, 26.88, 30.27, 37.08, 45.19)]


def test_economics(world):
    eco = world["economics"]
    assert (eco["skus_considered"], eco["horizon_days"]) == (200, 90)
    # Before correctness PR 4: ours 17 unmet units, 5252 avoided, saving 1887834.
    assert eco["unmet_units"] == {"naive": 5269, "ours": 0}
    assert eco["stockout_units_avoided"] == 5269
    assert eco["annualised_net_saving"] == approx(1858631)


def test_agent_reorder_and_impact(world):
    agent = world["agent"]
    assert agent["plan"] == ["replenishment", "financial_impact"]
    assert agent["steps"] == 3
    assert agent["proposed_actions"] == [
        {"proposed_action": "place_order", "sku_id": "SKU-00176", "quantity": 66, "status": "PENDING_APPROVAL"}
    ]


def test_scenarios(world):
    rows = {r["scenario"]: r for r in world["scenarios"]}
    # Before correctness PR 4: 38/66/50/35/52 SKUs, +41.9/+0.8/-13.5/+16.1 % vs baseline.
    expected = {
        "baseline": (62, 4541.0, 0.0),
        "promo_spike": (83, 6116.0, 34.7),
        "supply_disruption": (67, 4556.0, 0.3),
        "seasonal_downturn": (48, 4029.0, -11.3),
        "high_variability": (72, 5143.0, 13.3),
    }
    assert list(rows) == list(expected)
    for name, (needing, safety, pct) in expected.items():
        assert rows[name]["skus_needing_order"] == needing
        assert rows[name]["safety_stock_units"] == approx(safety)
        assert rows[name]["safety_stock_vs_baseline_pct"] == approx(pct)


# -- bundled CSVs ------------------------------------------------------------


def test_sample_csv(full_snapshot):
    c = full_snapshot["sample_csv"]
    bt, fidelity, tstr, privacy = c["backtest"], c["fidelity"], c["tstr"], c["privacy"]
    assert (c["skus"], c["orders"], bt["granularity"], bt["seasonal_period"], bt["series_len"]) == (
        12,
        3428,
        "daily",
        7,
        139,
    )
    assert [r["model"] for r in bt["results"]] == ["snaive7", "seas_linear7", "mean", "ma7", "naive"]
    assert bt["results"][0]["MAE"] == approx(32.786)
    assert bt["results"][0]["MAPE_pct"] == approx(24.0)  # 20.57 before the MAPE fix (correctness PR 3)
    assert bt["results"][0]["WAPE_pct"] == approx(21.2)
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


def test_real_10k_csv(full_snapshot):
    c = full_snapshot["retail_csv"]
    bt, fidelity, tstr, privacy = c["backtest"], c["fidelity"], c["tstr"], c["privacy"]
    assert (c["skus"], c["orders"], bt["granularity"], bt["seasonal_period"], bt["series_len"]) == (
        2015,
        10000,
        "hourly",
        11,
        44,
    )
    assert [r["model"] for r in bt["results"]] == ["naive", "ma11", "snaive11", "mean", "seas_linear11"]
    assert bt["results"][0]["MAE"] == approx(950.786)
    assert bt["results"][0]["MAPE_pct"] == approx(154.07)  # 99.04 before the MAPE fix (correctness PR 3)
    assert bt["results"][0]["WAPE_pct"] == approx(74.01)
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
