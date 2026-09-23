"""Tests for the fitted seasonal synthesizer."""

from __future__ import annotations

import pytest

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from .api import SeriesData
from .bootstrap import BootstrapTable
from .fit import FittedHourlyDemand, FittedSeasonalDemand


def test_fitted_hourly_demand_reproduces_series_length(sample_csv):
    _skus, orders, _load = load_online_retail_csv(sample_csv)
    model = FittedHourlyDemand().fit(orders)
    synth = model.generate()
    assert len(synth) == len(model.real_series)
    assert len(model.model.profile) == model.ppd


def test_repeated_generation_differs_and_a_seed_pins_it():
    series = SeriesData(values=[10.0 + (i % 7) + (i * 37 % 11) for i in range(42)], period=7)  # weekly + noise
    model = FittedSeasonalDemand(seed=7).fit(series)
    assert model.sample(20) != model.sample(20)
    assert model.sample(20, seed=1) == model.sample(20, seed=1)
    assert FittedSeasonalDemand(seed=7).fit(series).sample(20) == FittedSeasonalDemand(seed=7).fit(series).sample(20)
    assert len(model.sample()) == 42 and model.sample(0) == []


def test_hourly_wrapper_rejects_a_table_synthesizer():
    with pytest.raises(ValueError, match="not a series"):
        FittedHourlyDemand(BootstrapTable())
