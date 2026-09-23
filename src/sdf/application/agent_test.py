"""Tests for the tool-using warehouse agent."""

from __future__ import annotations

from sdf.application.agent import WarehouseAgent
from sdf.application.warehouse_demo import WarehouseIntelligence
from sdf.cli import build_registry
from sdf.synthesis.warehouse import GenerationSpec


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
