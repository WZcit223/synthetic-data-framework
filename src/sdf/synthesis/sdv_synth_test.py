"""Tests for the Gaussian-copula + SDMetrics path (optional ``synthesis`` extra)."""

from __future__ import annotations

import pytest


def test_phase21_sdv_optional(retail_10k_csv):
    """Gaussian-copula + SDMetrics; skipped when the optional libs are absent."""
    pytest.importorskip("copulas")
    pytest.importorskip("sdmetrics")
    from sdf.synthesis.sdv_synth import gaussian_copula_fidelity

    rep = gaussian_copula_fidelity(retail_10k_csv, max_rows=400)
    assert 0.0 <= rep["sdmetrics_overall"] <= 1.0
    assert set(rep["column_shape_ks"]) == {"Quantity", "Price", "hour", "weekday"}
