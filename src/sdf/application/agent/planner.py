"""Planners turn a question into tool calls; the executor decides what may run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

ORDER_WORDS = ("reorder", "replenish", "place order", "补货", "下单", "order")
MONEY_WORDS = ("impact", "save", "saving", "money", "roi", "cost", "钱", "节省", "价值")


@dataclass(frozen=True)
class PlannedCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


class Planner(Protocol):
    def plan(self, query: str) -> list[PlannedCall]: ...


class KeywordPlanner:
    """Keyword rules: an order question checks replenishment and its value, a money question the value,
    anything else goes to the knowledge Q&A."""

    def plan(self, query: str) -> list[PlannedCall]:
        ql = (query or "").lower()
        if any(k in ql for k in ORDER_WORDS):
            return [PlannedCall("replenishment", {"top_n": 5}), PlannedCall("financial_impact")]
        if any(k in ql for k in MONEY_WORDS):
            return [PlannedCall("financial_impact")]
        return [PlannedCall("ask_knowledge", {"q": query})]
