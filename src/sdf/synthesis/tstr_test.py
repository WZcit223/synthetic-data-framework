"""Tests for train-on-synthetic, test-on-real."""

from __future__ import annotations

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from sdf.synthesis.tstr import tstr_report


def test_tstr_ratio_is_finite_and_reasonable(sample_csv):
    # TSTR ratio is finite and reasonable on the sample.
    _skus, orders = load_online_retail_csv(sample_csv)
    r = tstr_report(orders)
    assert r["ratio_tstr_over_trtr"] is not None
    assert 0.3 <= r["ratio_tstr_over_trtr"] <= 3.0
