"""Tests for the keyword planner."""

from __future__ import annotations

from .planner import KeywordPlanner, PlannedCall


def test_order_question():
    assert KeywordPlanner().plan("should I reorder and what is the money impact?") == [
        PlannedCall("replenishment", {"top_n": 5}),
        PlannedCall("financial_impact"),
    ]


def test_money_question():
    assert KeywordPlanner().plan("what is the ROI?") == [PlannedCall("financial_impact")]


def test_anything_else_goes_to_knowledge():
    assert KeywordPlanner().plan("which SKUs are stockout?") == [
        PlannedCall("ask_knowledge", {"q": "which SKUs are stockout?"})
    ]
    assert KeywordPlanner().plan(None) == [PlannedCall("ask_knowledge", {"q": None})]  # type: ignore[arg-type]
