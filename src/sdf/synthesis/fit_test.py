"""Tests for the fitted seasonal synthesizer."""

from __future__ import annotations

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from .fit import FittedHourlyDemand


def test_fitted_hourly_demand_reproduces_series_length(sample_csv):
    _skus, orders, _load = load_online_retail_csv(sample_csv)
    model = FittedHourlyDemand().fit(orders)
    synth = model.generate()
    assert len(synth) == len(model.real_series)
    assert len(model.profile) == model.ppd


def test_repeated_generation_differs_and_a_seed_pins_it():
    from .fit import FittedSeasonalDemand

    series = [10.0 + (i % 7) + (i * 37 % 11) for i in range(42)]  # weekly shape plus noise
    model = FittedSeasonalDemand(seed=7).fit(series, 7)
    assert model.generate(20) != model.generate(20)
    assert model.generate(20, seed=1) == model.generate(20, seed=1)
    assert FittedSeasonalDemand(seed=7).fit(model.reference, 7).generate(20) == (
        FittedSeasonalDemand(seed=7).fit(model.reference, 7).generate(20)
    )
