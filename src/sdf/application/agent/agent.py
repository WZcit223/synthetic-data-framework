"""``WarehouseAgent``: plan, execute through the executor, compose a grounded answer.

Guardrails:
  - every tool runs through ``Executor``, which never runs a state-changing or
    approval-gated tool without an explicit approval;
  - every answer is composed from tool results (nothing invented), branching on
    ``ToolResult.ok``;
  - the full call chain is logged for audit.
"""

from __future__ import annotations

from typing import Any

from sdf.application.economics import financial_impact
from sdf.application.knowledge import KnowledgeQA
from sdf.observability import RunLogger
from sdf.simulation.outcome import CostModel
from .executor import Executor
from .planner import KeywordPlanner, Planner
from .tools import Tool, ToolError, ToolResult


def _checked(result: dict) -> dict:
    """Turn an ``{"error": ...}`` result of an application function into a tool failure."""
    if "error" in result:
        raise ToolError(result["error"])
    return result


class WarehouseAgent:
    """A minimal, auditable tool-using assistant over WarehouseIntelligence."""

    def __init__(self, intel, sink_path: str | None = None, planner: Planner | None = None) -> None:
        self.intel = intel
        self.qa = KnowledgeQA(intel)
        self.sink_path = sink_path
        self.planner = planner if planner is not None else KeywordPlanner()
        self.executor = Executor()
        self._register_default_tools()

    @property
    def tools(self) -> dict[str, Tool]:
        return self.executor.tools

    def register(self, tool: Tool) -> None:
        self.executor.register(tool)

    def _register_default_tools(self) -> None:
        i = self.intel
        self.register(Tool("get_kpis", "portfolio KPIs", lambda: i.kpis().__dict__))
        self.register(
            Tool(
                "replenishment",
                "SKUs needing an order under the 95% service-level (s,S) policy",
                lambda top_n=5: i.replenishment_ss_policy(service_level=0.95, top_n=top_n),
            )
        )
        self.register(
            Tool(
                "ss_policy",
                "(s,S) safety-stock policy",
                lambda service_level=0.95: i.replenishment_ss_policy(service_level=service_level),
            )
        )
        self.register(Tool("anomalies", "demand anomalies (robust-z)", lambda: i.demand_anomalies()))
        self.register(Tool("stocktake", "vision vs book reconciliation", lambda: i.stocktake_discrepancies()))
        self.register(Tool("financial_impact", "counterfactual £ savings", lambda: _checked(financial_impact(i))))
        self.register(Tool("ask_knowledge", "grounded NL answer", lambda q="": self.qa.ask(q)))
        # state-changing action: the executor never runs it without approval
        self.register(
            Tool(
                "place_order",
                "place a replenishment order (ACTION)",
                self._place_order,
                read_only=False,
                requires_approval=True,
            )
        )

    def _place_order(self, sku_id: str = "", quantity: int = 0) -> dict:
        # DATA-HOOK: submit to the client's ordering system; none is connected in the framework.
        return {"action": "place_order", "sku_id": sku_id, "quantity": quantity, "status": "APPROVED_NOT_SUBMITTED"}

    def handle(self, query: str, cost_model: CostModel | None = None) -> dict:
        """Plan the query, execute the plan, propose any follow-up action; return answer + trace."""
        log = RunLogger("agent", sink_path=self.sink_path)
        calls = self.planner.plan(query)
        executed = [(c, self.executor.call(log, c.tool, **c.args)) for c in calls]
        results: dict[str, ToolResult] = {}
        for c, r in executed:
            results.setdefault(c.tool, r)  # the answer templates read the first call of each tool
        # every planned call the executor held back is surfaced for approval
        proposed = [_proposal(r) for _, r in executed if r.status == "pending_approval"]

        if "replenishment" in results:
            repl = results["replenishment"]
            n = repl.data["skus_needing_order"] if repl.ok else 0
            rows = repl.data["rows"] if repl.ok else []
            top = rows[0] if n and rows else None  # rows are sorted by order_qty, largest first
            if top:
                pending = self.executor.call(log, "place_order", sku_id=top["sku_id"], quantity=top["order_qty"])
                if pending.status == "pending_approval":
                    proposed.append(_proposal(pending))
            ans = (
                (
                    f"{n} SKUs need an order under the 95% service-level (s,S) policy. "
                    if repl.ok
                    else f"Cannot check replenishment: {repl.error}. "
                )
                + (
                    f"Largest order: {top['sku_id']} — propose ordering "
                    f"{top['order_qty']} units (pending your approval). "
                    if top
                    else ""
                )
                + _saving_sentence(results.get("financial_impact"))
            )
        elif "financial_impact" in results:
            impact = results["financial_impact"]
            if not impact.ok:
                ans = f"Cannot estimate the saving: {impact.error}."
            else:
                d = impact.data
                ans = (
                    f"Estimated annualised net saving ≈ {d['annualised_net_saving']:,} "
                    f"(assumptions: {d['assumptions']['holding_cost_annual_rate']:.0%} holding, "
                    f"95% service). {d['stockout_units_avoided']:,} stockout-units avoided "
                    f"over {d['horizon_days']} days."
                )
        elif "ask_knowledge" in results:
            res = results["ask_knowledge"]
            ans = res.data["answer"] if res.ok else f"Cannot answer: {res.error}."
        elif proposed:
            ans = (
                f"{len(proposed)} action(s) pending your approval: "
                + ", ".join(p["proposed_action"] for p in proposed)
                + "."
            )
        else:
            ans = "Cannot answer: the plan called " + (", ".join(c.tool for c in calls) or "no tool") + "."

        return {
            "query": query,
            "answer": ans,
            "plan": [c.tool for c in calls],
            "proposed_actions": proposed,
            "requires_approval": bool(proposed),
            "run": log.summary(),
            "trace": [e.to_dict() for e in log.entries],
        }

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "read_only": t.read_only,
                "requires_approval": t.requires_approval,
            }
            for t in self.tools.values()
        ]


def _proposal(pending: ToolResult) -> dict[str, Any]:
    """A pending call in the shape reported to the user: the action, its arguments and its status."""
    return {"proposed_action": pending.data["tool"], **pending.data["args"], "status": "PENDING_APPROVAL"}


def _saving_sentence(impact: ToolResult | None) -> str:
    if impact is None:
        return ""
    if not impact.ok:
        return f"Cannot estimate the saving: {impact.error}."
    return (
        f"Estimated annualised saving from disciplined replenishment: "
        f"≈ {impact.data['annualised_net_saving']:,} "
        f"({impact.data['stockout_units_avoided']:,} stockout-units avoided)."
    )
