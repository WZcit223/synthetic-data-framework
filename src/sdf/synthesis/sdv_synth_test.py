"""Tests for the Gaussian-copula + SDMetrics path (optional ``synthesis`` extra)."""

from __future__ import annotations

import pytest


def test_phase21_sdv_optional(retail_10k_csv):
    """Gaussian-copula + SDMetrics; skipped when the optional libs are absent."""
    pytest.importorskip("copulas")
    pytest.importorskip("sdmetrics")
    from .sdv_synth import gaussian_copula_fidelity

    rep = gaussian_copula_fidelity(retail_10k_csv, max_rows=400)
    assert 0.0 <= rep["sdmetrics_overall"] <= 1.0
    assert set(rep["column_shape_ks"]) == {"Quantity", "Price", "hour", "weekday"}


def test_gaussian_copula_rows_follow_the_table_s_column_kinds():
    pytest.importorskip("copulas")
    import random

    from .api import TableData
    from .sdv_synth import GaussianCopulaTable

    rng = random.Random(3)
    rows = [(float(rng.randint(1, 12)), rng.choice((0.85, 1.25, 2.95)), float(rng.randint(8, 17))) for _ in range(300)]
    data = TableData(rows=rows, columns=("qty", "price", "hour"), kinds=("integer", "category", "category"))
    synth = GaussianCopulaTable(seed=7).fit(data).sample()
    assert len(synth) == 300
    assert all(q == int(q) and 1 <= q <= 12 for q, _, _ in synth)
    assert {p for _, p, _ in synth} <= {0.85, 1.25, 2.95} and {h for *_, h in synth} <= {r[2] for r in rows}
