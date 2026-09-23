"""Tests for the tool-using warehouse agent."""

from __future__ import annotations

from sdf.application.intelligence import WarehouseIntelligence
from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from .agent import WarehouseAgent
from .tools import Tool


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


def test_reorder_without_plan_rows_proposes_nothing():
    _, reg = build_registry(GenerationSpec(n_skus=40, horizon_days=30))
    agent = WarehouseAgent(WarehouseIntelligence(reg))
    # A count without rows (e.g. the tool asked for top_n=0) must not index an empty list.
    agent.register(Tool("replenishment", "stub", lambda top_n=5: {"skus_needing_order": 3, "rows": []}))
    r = agent.handle("should I reorder?")
    assert r["proposed_actions"] == [] and r["answer"].startswith("3 SKUs need an order")


def test_the_proposed_order_is_never_executed():
    _, reg = build_registry(GenerationSpec(n_skus=40, horizon_days=30))
    agent = WarehouseAgent(WarehouseIntelligence(reg))
    calls = []
    agent.register(Tool("place_order", "spy", lambda **kw: calls.append(kw), read_only=False, requires_approval=True))
    r = agent.handle("should I reorder?")
    assert calls == [] and r["proposed_actions"] and r["proposed_actions"][0]["status"] == "PENDING_APPROVAL"
    assert any("requires human approval" in e["note"] for e in r["trace"])


def test_a_failing_tool_is_reported_not_raised():
    _, reg = build_registry(GenerationSpec(n_skus=40, horizon_days=30))
    agent = WarehouseAgent(WarehouseIntelligence(reg))

    def boom(**_):
        raise RuntimeError("backend down")

    agent.register(Tool("financial_impact", "broken", boom))
    r = agent.handle("what is the money impact?")
    assert r["answer"] == "Cannot estimate the saving: backend down."
    assert r["trace"][-1]["status"] == "error" and r["run"]["errors"] == 1


def test_a_custom_planner_is_used():
    from .planner import PlannedCall

    class KpiPlanner:
        def plan(self, query):
            return [PlannedCall("ask_knowledge", {"q": "inventory value?"})]

    _, reg = build_registry(GenerationSpec(n_skus=40, horizon_days=30))
    r = WarehouseAgent(WarehouseIntelligence(reg), planner=KpiPlanner()).handle("anything")
    assert r["plan"] == ["ask_knowledge"] and "inventory" in r["answer"].lower()


def test_a_gated_call_from_any_planner_is_proposed_not_run():
    from .planner import PlannedCall

    class OrderPlanner:
        def plan(self, query):
            return [
                PlannedCall("place_order", {"sku_id": "S1", "quantity": 4}),
                PlannedCall("place_order", {"sku_id": "S2", "quantity": 1}),
            ]

    _, reg = build_registry(GenerationSpec(n_skus=40, horizon_days=30))
    agent = WarehouseAgent(WarehouseIntelligence(reg), planner=OrderPlanner())
    calls = []
    agent.register(Tool("place_order", "spy", lambda **kw: calls.append(kw), read_only=False, requires_approval=True))
    r = agent.handle("order two things")
    assert calls == [] and r["requires_approval"] is True
    assert r["proposed_actions"] == [
        {"proposed_action": "place_order", "sku_id": "S1", "quantity": 4, "status": "PENDING_APPROVAL"},
        {"proposed_action": "place_order", "sku_id": "S2", "quantity": 1, "status": "PENDING_APPROVAL"},
    ]
    assert r["answer"] == "2 action(s) pending your approval: place_order, place_order."


def test_a_falsy_planner_is_still_used():
    from .planner import PlannedCall

    class EmptyButValid:
        def __len__(self):
            return 0

        def plan(self, query):
            return [PlannedCall("get_kpis")]

    _, reg = build_registry(GenerationSpec(n_skus=40, horizon_days=30))
    r = WarehouseAgent(WarehouseIntelligence(reg), planner=EmptyButValid()).handle("x")
    assert r["plan"] == ["get_kpis"] and r["answer"] == "Cannot answer: the plan called get_kpis."
