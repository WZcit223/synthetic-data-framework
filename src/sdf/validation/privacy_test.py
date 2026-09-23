"""Tests for the synthetic-data privacy metrics."""

from __future__ import annotations

from .privacy import bootstrap_synthesize, privacy_report


def test_privacy_metrics():
    real = [(float(i % 7), float(i % 5) + 0.5, float(i % 24), float(i % 7)) for i in range(300)]
    synth = bootstrap_synthesize(real, seed=3)
    rep = privacy_report(real, synth)
    assert 0.0 <= rep["clone_risk_pct"] <= 100.0
    assert rep["dcr_median"] >= 0.0 and "verdict" in rep
