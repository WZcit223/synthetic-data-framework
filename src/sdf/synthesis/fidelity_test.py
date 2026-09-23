"""Tests for the dependency-free fidelity metrics."""

from __future__ import annotations

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from sdf.synthesis.fidelity import fidelity_report, ks_2samp, pearson
from sdf.synthesis.fit import FittedHourlyDemand


def test_phase2_fitted_synthesis_fidelity(sample_csv):
    assert ks_2samp([1, 2, 3], [1, 2, 3]) == 0.0
    assert pearson([1, 2, 3], [2, 4, 6]) == 1.0
    _skus, orders = load_online_retail_csv(sample_csv)
    model = FittedHourlyDemand().fit(orders)
    synth = model.generate()
    rep = fidelity_report(model.real_series, synth, model.ppd)
    assert 0.0 <= rep["ks_statistic"] <= 1.0
    assert -1.0 <= rep["profile_corr"] <= 1.0
    assert 0.0 <= rep["fidelity_score"] <= 100.0
