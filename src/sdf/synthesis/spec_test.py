"""Tests for ``GenerationSpec`` validation."""

from __future__ import annotations

import pytest

from .spec import GenerationSpec


def test_defaults_validate():
    GenerationSpec()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("n_skus", 0),
        ("n_locations", 0),
        ("horizon_days", 0),
        ("abc_split", (0.5, 0.5)),
        ("abc_split", (0.6, 0.6, -0.2)),
        ("abc_split", (0.5, 0.3, 0.3)),
        ("daily_orders_per_a_sku", 0.0),
        ("daily_orders_per_a_sku", float("nan")),
        ("daily_orders_per_a_sku", float("inf")),
        ("n_skus", float("nan")),
        ("abc_split", (float("nan"), 0.5, 0.5)),
        ("express_ratio", float("nan")),
        ("express_ratio", 1.5),
        ("stockout_pressure", -0.1),
    ],
)
def test_invalid_field_raises_value_error_naming_the_field(field, value):
    with pytest.raises(ValueError, match=field):
        GenerationSpec(**{field: value})
