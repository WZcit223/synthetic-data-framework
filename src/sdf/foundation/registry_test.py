"""Tests for the multi-source data registry."""

from __future__ import annotations

import pytest

from .registry import DataSourceRegistry


def test_duplicate_name_raises_unless_replace():
    reg = DataSourceRegistry()
    reg.register("orders", "OutboundOrder", [1, 2])
    with pytest.raises(ValueError, match="'orders' is already registered"):
        reg.register("orders", "OutboundOrder", [3])
    assert reg.stream("OutboundOrder") == [1, 2]
    reg.register("orders", "OutboundOrder", [3], replace=True)
    assert reg.stream("OutboundOrder") == [3]
