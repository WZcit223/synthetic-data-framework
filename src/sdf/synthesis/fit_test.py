"""Tests for the fitted seasonal synthesizer."""

from __future__ import annotations

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from .fit import FittedHourlyDemand


def test_fitted_hourly_demand_reproduces_series_length(sample_csv):
    _skus, orders = load_online_retail_csv(sample_csv)
    model = FittedHourlyDemand().fit(orders)
    synth = model.generate()
    assert len(synth) == len(model.real_series)
    assert len(model.profile) == model.ppd
