"""Tests for the counterfactual economics."""

from __future__ import annotations

import pytest

from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from .economics import CostModel, financial_impact
from .intelligence import WarehouseIntelligence


def test_economics_impact():
    _, reg = build_registry(GenerationSpec(n_skus=80, horizon_days=60))
    rep = financial_impact(WarehouseIntelligence(reg))
    assert rep["unmet_units"]["ours"] <= rep["unmet_units"]["naive"]
    assert "annualised_net_saving" in rep
    assert rep["skus_considered"] > 0


def test_cost_model_defaults_validate():
    CostModel()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("holding_cost_annual_rate", 1.5),
        ("stockout_penalty_mult", -0.1),
        ("order_fixed_cost", -1.0),
        ("lead_time_days", 0),
        ("review_days", 0),
        ("working_days_per_year", 0),
        ("service_z", 0.0),
        ("service_z", float("nan")),
        ("order_fixed_cost", float("nan")),
        ("lead_time_days", float("nan")),
        ("holding_cost_annual_rate", float("inf")),
    ],
)
def test_cost_model_invalid_field_raises_value_error_naming_the_field(field, value):
    with pytest.raises(ValueError, match=field):
        CostModel(**{field: value})
