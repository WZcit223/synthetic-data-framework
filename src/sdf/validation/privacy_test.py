"""Tests for the synthetic-data privacy metrics."""

from __future__ import annotations

from sdf.synthesis.api import TableData
from sdf.synthesis.bootstrap import BootstrapTable
from .privacy import FEATURE_COLUMNS, privacy_report


def test_privacy_metrics():
    real = [(float(i % 7), float(i % 5) + 0.5, float(i % 24), float(i % 7)) for i in range(300)]
    synth = BootstrapTable(seed=3).fit(TableData(rows=real, columns=FEATURE_COLUMNS)).sample()
    rep = privacy_report(real, synth)
    assert 0.0 <= rep["clone_risk_pct"] <= 100.0
    assert rep["dcr_median"] >= 0.0 and "verdict" in rep
