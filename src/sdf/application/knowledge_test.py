"""Tests for grounded knowledge Q&A."""

from __future__ import annotations

from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from .intelligence import WarehouseIntelligence
from .knowledge import KnowledgeQA


def test_phase4_knowledge_qa_c6():
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=45))
    qa = KnowledgeQA(WarehouseIntelligence(reg))
    assert qa.ask("which SKUs are stockout?")["intent"] == "stockouts"
    assert qa.ask("safety stock at 95%?")["intent"] == "safety_stock"
    assert qa.ask("any demand anomalies?")["intent"] == "anomaly"
    assert qa.ask("how good is the forecast?")["intent"] == "forecast"
    # Unknown question falls back to help, still grounded (no crash).
    assert "answer" in qa.ask("tell me a joke")


def test_forecast_question_on_an_empty_registry_says_so():
    from sdf.foundation.registry import DataSourceRegistry

    res = KnowledgeQA(WarehouseIntelligence(DataSourceRegistry())).ask("forecast accuracy?")
    assert res["intent"] == "forecast"
    assert "not enough demand history" in res["answer"]


def test_undefined_percentages_read_as_not_available():
    from .knowledge import _pct_text

    assert _pct_text(None) == "n/a" and _pct_text(21.2) == "21.2%"
