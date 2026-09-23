"""Tests for the counterfactual economics."""

from __future__ import annotations

from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from .economics import financial_impact
from .warehouse_demo import WarehouseIntelligence


def test_economics_impact():
    _, reg = build_registry(GenerationSpec(n_skus=80, horizon_days=60))
    rep = financial_impact(WarehouseIntelligence(reg))
    assert rep["unmet_units"]["ours"] <= rep["unmet_units"]["naive"]
    assert "annualised_net_saving" in rep
    assert rep["skus_considered"] > 0
