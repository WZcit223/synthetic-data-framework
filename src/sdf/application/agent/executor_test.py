"""Tests for the executor's approval and failure handling."""

from __future__ import annotations

import pytest

from sdf.observability import RunLogger
from .executor import Executor
from .tools import Tool, ToolResult


@pytest.fixture
def setup():
    calls: list[dict] = []
    ex = Executor()
    ex.register(Tool("read", "read-only", lambda x=1: {"x": x}))
    ex.register(Tool("act", "state-changing", lambda **kw: calls.append(kw) or "done", read_only=False))
    ex.register(Tool("gated", "approval", lambda **kw: calls.append(kw) or "done", requires_approval=True))
    return ex, calls


def test_read_only_tool_runs(setup):
    ex, _ = setup
    log = RunLogger("t")
    assert ex.call(log, "read", x=3) == ToolResult(ok=True, status="done", data={"x": 3})
    assert log.entries[0].status == "ok"


@pytest.mark.parametrize("name", ["act", "gated"])
def test_gated_tool_is_not_called_without_approval(setup, name):
    ex, calls = setup
    log = RunLogger("t")
    res = ex.call(log, name, sku_id="S", quantity=5)
    assert res == ToolResult(
        ok=True, status="pending_approval", data={"tool": name, "args": {"sku_id": "S", "quantity": 5}}
    )
    assert calls == []
    assert "requires human approval" in log.entries[0].note


@pytest.mark.parametrize("name", ["act", "gated"])
def test_gated_tool_runs_only_with_approval(setup, name):
    ex, calls = setup
    res = ex.call(RunLogger("t"), name, approved=True, sku_id="S", quantity=5)
    assert (res.ok, res.status, res.data) == (True, "done", "done")
    assert calls == [{"sku_id": "S", "quantity": 5}]


def test_failing_tool_becomes_failed_result():
    ex = Executor()
    ex.register(Tool("bad", "raises", lambda: 1 / 0))
    log = RunLogger("t")
    res = ex.call(log, "bad")
    assert (res.ok, res.status, res.error) == (False, "failed", "division by zero")
    assert log.entries[0].status == "error"


def test_unknown_tool_is_a_failed_result():
    res = Executor().call(RunLogger("t"), "nope")
    assert (res.ok, res.status, res.error) == (False, "failed", "unknown tool 'nope'")


def test_financial_impact_on_an_empty_registry_fails_cleanly():
    from sdf.application.intelligence import WarehouseIntelligence
    from sdf.foundation.registry import DataSourceRegistry
    from .agent import WarehouseAgent

    agent = WarehouseAgent(WarehouseIntelligence(DataSourceRegistry()))
    res = agent.executor.call(RunLogger("t"), "financial_impact")
    assert res == ToolResult(ok=False, status="failed", error="no demand")
