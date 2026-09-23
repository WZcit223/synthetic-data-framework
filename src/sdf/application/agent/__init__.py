"""Warehouse assistant agent: plan tool calls, execute them under guardrails, answer with an audit trail.

- ``tools`` — ``Tool`` and ``ToolResult``;
- ``executor`` — ``Executor``, the one place that runs tools and enforces approval;
- ``planner`` — ``PlannedCall``, the ``Planner`` protocol and ``KeywordPlanner``;
- ``agent`` — ``WarehouseAgent``, which plans, executes and composes the answer.

ALGORITHM-HOOK: replace ``KeywordPlanner`` with an LLM tool-use planner; the
tools, the executor's guardrails and the audit log stay identical.
"""

from .agent import WarehouseAgent

__all__ = ["WarehouseAgent"]
