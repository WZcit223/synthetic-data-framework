"""Tests for the counterfactual economics."""

from __future__ import annotations

from sdf.application.economics import financial_impact
from sdf.application.warehouse_demo import WarehouseIntelligence
from sdf.cli import build_registry
from sdf.synthesis.warehouse import GenerationSpec


def test_economics_impact():
    _, reg = build_registry(GenerationSpec(n_skus=80, horizon_days=60))
    rep = financial_impact(WarehouseIntelligence(reg))
    assert rep["unmet_units"]["ours"] <= rep["unmet_units"]["naive"]
    assert "annualised_net_saving" in rep
    assert rep["skus_considered"] > 0
