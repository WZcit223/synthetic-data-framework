"""The single place where tools run: approval is enforced here, for every planner."""

from __future__ import annotations

import time
from typing import Any

from sdf.observability import RunLogger
from .planner import PlannedCall
from .tools import Tool, ToolResult

APPROVAL_NOTE = "requires human approval — not executed"


class Executor:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def call(self, log: RunLogger, name: str, *, approved: bool = False, **args: Any) -> ToolResult:
        """Run tool ``name`` and log the step.

        A gated tool (state-changing or marked ``requires_approval``) is not
        called unless ``approved`` is true; the result is ``pending_approval``
        with the intended call as data. Any exception from the tool becomes a
        ``failed`` result. An unknown name is a ``failed`` result too, so a
        planner that invents a tool cannot crash the run.
        """
        return self._run(log, name, args, approved=approved)

    def run_planned(self, log: RunLogger, call: PlannedCall) -> ToolResult:
        """Run a planner's call. A plan can never approve itself: ``approved`` is not accepted as an argument."""
        if "approved" in call.args:
            result = ToolResult(ok=False, status="failed", error="a planned call may not set 'approved'")
            log.record("tool", call.tool, call.args, {"error": result.error}, status="error")
            return result
        return self._run(log, call.tool, dict(call.args), approved=False)

    def _run(self, log: RunLogger, name: str, args: dict[str, Any], *, approved: bool) -> ToolResult:
        # Tool arguments travel as a dict, so names such as "log" or "name" cannot collide with a signature.
        tool = self.tools.get(name)
        if tool is None:
            result = ToolResult(ok=False, status="failed", error=f"unknown tool {name!r}")
            log.record("tool", name, args, {"error": result.error}, status="error")
            return result
        if tool.gated and not approved:
            result = ToolResult(ok=True, status="pending_approval", data={"tool": name, "args": dict(args)})
            log.record("tool", name, args, result.data, note=APPROVAL_NOTE)
            return result
        t0 = time.perf_counter()
        try:
            data = tool.fn(**args)
        except Exception as exc:  # a tool failure is a result, not a crash
            ms = int((time.perf_counter() - t0) * 1000)
            log.record("tool", name, args, {"error": str(exc)}, status="error", duration_ms=ms)
            return ToolResult(ok=False, status="failed", error=str(exc))
        ms = int((time.perf_counter() - t0) * 1000)
        log.record("tool", name, args, data, duration_ms=ms, note="approved" if tool.gated else "")
        return ToolResult(ok=True, status="done", data=data)
