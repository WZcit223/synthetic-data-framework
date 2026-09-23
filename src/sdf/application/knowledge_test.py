"""Tests for grounded knowledge Q&A."""

from __future__ import annotations

from sdf.application.knowledge import KnowledgeQA
from sdf.application.warehouse_demo import WarehouseIntelligence
from sdf.cli import build_registry
from sdf.synthesis.warehouse import GenerationSpec


def test_phase4_knowledge_qa_c6():
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=45))
    qa = KnowledgeQA(WarehouseIntelligence(reg))
    assert qa.ask("which SKUs are stockout?")["intent"] == "stockouts"
    assert qa.ask("safety stock at 95%?")["intent"] == "safety_stock"
    assert qa.ask("any demand anomalies?")["intent"] == "anomaly"
    assert qa.ask("how good is the forecast?")["intent"] == "forecast"
    # Unknown question falls back to help, still grounded (no crash).
    assert "answer" in qa.ask("tell me a joke")
