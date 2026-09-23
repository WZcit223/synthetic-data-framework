"""Tests for the tool-using warehouse agent."""

from __future__ import annotations

from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from .agent import WarehouseAgent
from .intelligence import WarehouseIntelligence


def test_agent_trace_and_guardrail():
    _, reg = build_registry(GenerationSpec(n_skus=80, horizon_days=60))
    agent = WarehouseAgent(WarehouseIntelligence(reg))
    r = agent.handle("should I reorder and what is the money impact?")
    assert r["plan"] == ["replenishment", "financial_impact"]
    assert r["trace"] and all("seq" in e for e in r["trace"])
    # state-changing action must be gated, never auto-executed
    if r["proposed_actions"]:
        assert r["proposed_actions"][0]["status"] == "PENDING_APPROVAL"
        assert r["requires_approval"] is True
    # a knowledge query still returns a grounded answer
    assert agent.handle("which SKUs are stockout?")["answer"]


def test_cost_question_on_an_empty_registry_says_so():
    from sdf.foundation.registry import DataSourceRegistry

    agent = WarehouseAgent(WarehouseIntelligence(DataSourceRegistry()))
    assert agent.handle("what is the cost?")["answer"] == "Cannot estimate the saving: no demand."
    assert "Cannot estimate the saving: no demand." in agent.handle("should I reorder?")["answer"]
