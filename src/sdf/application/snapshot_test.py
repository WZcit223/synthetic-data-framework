"""Tests for the ``sdf validate`` snapshot and its documentation block."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .snapshot import DOC_BEGIN, DOC_END, _backtest, doc_block, render_markdown, replace_doc_block

VALIDATION_MD = Path(__file__).resolve().parents[3] / "docs" / "VALIDATION.md"


def test_snapshot_is_plain_json(full_snapshot):
    assert json.loads(json.dumps(full_snapshot)) == full_snapshot


def test_validation_doc_matches_the_code(full_snapshot):
    """docs/VALIDATION.md embeds exactly what the code computes today.

    If this fails, run ``uv run sdf validate --update-doc docs/VALIDATION.md``
    and explain the changed numbers in the PR.
    """
    assert doc_block(VALIDATION_MD.read_text(encoding="utf-8")) == render_markdown(full_snapshot)


def test_replace_doc_block_only_touches_the_marked_block():
    text = f"# Title\n\nbefore\n{DOC_BEGIN}\nold\n{DOC_END}\nafter\n"
    updated = replace_doc_block(text, "new line\n")
    assert updated == f"# Title\n\nbefore\n{DOC_BEGIN}\nnew line\n{DOC_END}\nafter\n"
    assert doc_block(updated) == "new line\n"
    assert replace_doc_block(updated, "new line\n") == updated


def test_replace_doc_block_requires_markers():
    with pytest.raises(ValueError, match="sdf-validate"):
        replace_doc_block("# no markers\n", "x\n")


def test_backtest_of_no_orders_reports_an_empty_series():
    bt = _backtest([])
    assert (bt["series_len"], bt["series_mean"], bt["test_len"], bt["results"]) == (0, 0.0, 0, [])
