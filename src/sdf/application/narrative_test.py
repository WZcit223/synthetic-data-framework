"""Tests for the text insights."""

from __future__ import annotations

from .narrative import insights


def test_insights_quote_the_computed_facts(default_world):
    _, reg, intel = default_world
    lines = insights(reg)
    assert len(lines) == 4
    assert f"Managing {intel.kpis().total_skus} SKUs" in lines[0]
