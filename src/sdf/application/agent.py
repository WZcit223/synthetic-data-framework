"""Warehouse assistant agent — tool calls + audit trail (dependency-free).

Closes the reported gap "Agent 调用与日志记录". It wraps the existing warehouse
capabilities as named **tools**, runs a small rule-based **planner** that decides
which tools to call for a query, and records every call as an auditable trace via
`RunLogger`. High-impact actions (placing an order) are **not executed** — they
are returned as *proposed actions requiring human approval* (human-in-the-loop).

Guardrails enforced here:
  - read-only tools run freely; state-changing actions require approval;
  - every answer is grounded in a tool result (nothing invented);
  - the full call chain + decision is logged for audit.

ALGORITHM-HOOK: replace the rule-based planner with an LLM tool-use planner; the
tool registry, guardrails, and audit log stay identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from sdf.observability import RunLogger
from .economics import CostModel, financial_impact
from .knowledge import KnowledgeQA


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    read_only: bool = True
    requires_approval: bool = False


class WarehouseAgent:
    """A minimal, auditable tool-using assistant over WarehouseIntelligence."""

    def __init__(self, intel, sink_path: Optional[str] = None) -> None:
        self.intel = intel
        self.qa = KnowledgeQA(intel)
        self.sink_path = sink_path
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()

    # -- tool registry -----------------------------------------------------

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def _register_default_tools(self) -> None:
        i = self.intel
        self.register(Tool("get_kpis", "portfolio KPIs", lambda: i.kpis().__dict__))
        self.register(
            Tool("replenishment", "SKUs at/below reorder point", lambda top_n=5: i.replenishment_suggestions(top_n))
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
        self.register(Tool("financial_impact", "counterfactual £ savings", lambda: financial_impact(i)))
        self.register(Tool("ask_knowledge", "grounded NL answer", lambda q="": self.qa.ask(q)))
        # state-changing action — never auto-executed
        self.register(
            Tool(
                "place_order",
                "place a replenishment order (ACTION)",
                self._propose_order,
                read_only=False,
                requires_approval=True,
            )
        )

    def _propose_order(self, sku_id: str = "", quantity: int = 0) -> Dict:
        # Guardrail: do not execute; return a proposal for human approval.
        return {"proposed_action": "place_order", "sku_id": sku_id, "quantity": quantity, "status": "PENDING_APPROVAL"}

    # -- execution with logging -------------------------------------------

    def call(self, log: RunLogger, name: str, **args) -> Any:
        tool = self.tools[name]
        with log.step("tool", name, inputs=args) as box:
            if tool.requires_approval:
                box["note"] = "requires human approval — not executed"
            box["output"] = tool.fn(**args)
            return box["output"]

    # -- planner -----------------------------------------------------------

    def handle(self, query: str, cost_model: CostModel = None) -> Dict:
        """Route a query to a small plan of tool calls; return answer + trace."""
        log = RunLogger("agent", sink_path=self.sink_path)
        ql = (query or "").lower()
        plan: List[str] = []
        proposed: List[Dict] = []

        wants_order = any(k in ql for k in ("reorder", "replenish", "place order", "补货", "下单", "order"))
        wants_money = any(k in ql for k in ("impact", "save", "saving", "money", "roi", "cost", "钱", "节省", "价值"))

        if wants_order:
            plan = ["replenishment", "financial_impact"]
            sugg = self.call(log, "replenishment", top_n=5)
            impact = self.call(log, "financial_impact")
            top = sugg[0] if sugg else None
            if top:
                # propose the action, gated by approval
                action = self.call(log, "place_order", sku_id=top["sku_id"], quantity=top["suggested_order_qty"])
                proposed.append(action)
            n = len(self.intel.replenishment_suggestions(9999))
            ans = (
                f"{n} SKUs are at/below reorder point. "
                + (
                    f"Most urgent: {top['sku_id']} — propose ordering "
                    f"{top['suggested_order_qty']} units (pending your approval). "
                    if top
                    else ""
                )
                + f"Estimated annualised saving from disciplined replenishment: "
                f"≈ {impact.get('annualised_net_saving', 0):,} "
                f"({impact.get('stockout_units_avoided', 0):,} stockout-units avoided)."
            )
        elif wants_money:
            plan = ["financial_impact"]
            impact = self.call(log, "financial_impact")
            ans = (
                f"Estimated annualised net saving ≈ {impact.get('annualised_net_saving', 0):,} "
                f"(assumptions: {impact['assumptions']['holding_cost_annual_rate']:.0%} holding, "
                f"95% service). {impact.get('stockout_units_avoided', 0):,} stockout-units avoided "
                f"over {impact.get('horizon_days', 0)} days."
            )
        else:
            plan = ["ask_knowledge"]
            res = self.call(log, "ask_knowledge", q=query)
            ans = res["answer"]

        return {
            "query": query,
            "answer": ans,
            "plan": plan,
            "proposed_actions": proposed,
            "requires_approval": bool(proposed),
            "run": log.summary(),
            "trace": [e.to_dict() for e in log.entries],
        }

    def list_tools(self) -> List[Dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "read_only": t.read_only,
                "requires_approval": t.requires_approval,
            }
            for t in self.tools.values()
        ]
