"""Tests for what-if scenario simulation."""

from __future__ import annotations

from sdf.synthesis.spec import GenerationSpec
from .scenarios import run_scenarios


def test_scenarios_whatif():
    rep = run_scenarios(GenerationSpec(n_skus=50, horizon_days=45), names=["baseline", "promo_spike"])
    by = {r["scenario"]: r for r in rep["scenarios"]}
    # a promo spike should not require less safety stock than baseline
    assert by["promo_spike"]["safety_stock_units"] >= by["baseline"]["safety_stock_units"]
