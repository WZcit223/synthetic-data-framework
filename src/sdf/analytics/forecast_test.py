"""Tests for series construction and the walk-forward backtest."""

from __future__ import annotations

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from .forecast import build_series, compare_models, daily_demand_series


def test_phase2_adapter_and_backtest(sample_csv):
    skus, orders = load_online_retail_csv(sample_csv)
    assert skus and orders
    assert all(o.quantity > 0 for o in orders)  # abs() applied
    series = daily_demand_series(orders)
    assert len(series) > 30
    report = compare_models(series, test_len=21)
    assert report["best_model"] in {"mean", "naive", "ma7", "snaive7"}
    # every model must produce finite, non-negative error metrics
    for r in report["results"]:
        assert r["MAE"] >= 0 and r["RMSE"] >= 0


def test_build_series_accepts_a_generator(sample_csv):
    _, orders = load_online_retail_csv(sample_csv)
    from_list = build_series(orders)
    from_generator = build_series(o for o in orders)
    assert from_generator == from_list
    assert from_generator[0]
