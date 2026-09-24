"""Tests for the hook markers and the code index in the checklist."""

from __future__ import annotations

from pathlib import Path

import pytest

from . import hooks

CHECKLIST = Path(__file__).resolve().parents[2] / "docs" / "ALGORITHM_AND_DATA_CHECKLIST.md"


@pytest.fixture(scope="module")
def checklist_text() -> str:
    return CHECKLIST.read_text(encoding="utf-8")


def test_every_marker_names_a_checklist_row(checklist_text):
    found = hooks.scan()
    assert len(found) >= 30  # the framework's stand-ins are marked
    assert hooks.problems(found, hooks.checklist_ids(checklist_text)) == []


def test_checklist_index_is_current(checklist_text):
    """If this fails, run ``uv run sdf hooks --update-doc docs/ALGORITHM_AND_DATA_CHECKLIST.md``."""
    expected = hooks.render_index(hooks.scan(), hooks.checklist_ids(checklist_text))
    assert hooks.doc_block(checklist_text) == expected


def test_checklist_ids_ignore_the_generated_block(checklist_text):
    ids = hooks.checklist_ids(checklist_text)
    assert {"A1", "B3", "C2", "C7", "D5"} <= set(ids)
    assert ids["C2"] == "Replenishment"


def _package(tmp_path: Path, source: str) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "mod.py").write_text(source, encoding="utf-8")
    (pkg / "mod_test.py").write_text("# ALGORITHM-HOOK: tests are not scanned\n", encoding="utf-8")
    return pkg


def test_scan_reads_ids_and_enclosing_symbols(tmp_path):
    pkg = _package(
        tmp_path,
        '"""Module. ALGORITHM-HOOK[C1]: forecast model."""\n'
        "class Planner:\n"
        "    def plan(self):\n"
        "        # DATA-HOOK[C7]: real action logs\n"
        "        return 1\n"
        "# ``ALGORITHM-HOOK`` names the convention and is not a marker\n",
    )
    found = hooks.scan(pkg)
    assert [(h.kind, h.id, h.line, h.location) for h in found] == [
        ("ALGORITHM", "C1", 1, "pkg/mod.py"),
        ("DATA", "C7", 4, "pkg/mod.py::Planner.plan"),
    ]


def test_bare_and_unknown_markers_are_problems(tmp_path):
    pkg = _package(tmp_path, "# ALGORITHM-HOOK: no id\n# DATA-HOOK[Z9]: unknown row\n")
    assert hooks.problems(hooks.scan(pkg), {"C1": "Demand forecast"}) == [
        "pkg/mod.py:1: ALGORITHM-HOOK without a checklist ID",
        "pkg/mod.py:2: DATA-HOOK[Z9] names no checklist row",
    ]


def test_render_index_lists_every_row(tmp_path):
    pkg = _package(tmp_path, "def f():\n    # ALGORITHM-HOOK[C1]: x\n    pass\n")
    index = hooks.render_index(hooks.scan(pkg), {"C1": "Demand forecast", "C4": "Slotting"})
    assert "| C1 | Demand forecast | `pkg/mod.py::f` | — |" in index
    assert "| C4 | Slotting | — | — |" in index


def test_replace_doc_block_needs_the_markers():
    with pytest.raises(ValueError, match="sdf-hooks"):
        hooks.replace_doc_block("no markers here", "x")
    text = f"a\n{hooks.DOC_BEGIN}\nold\n{hooks.DOC_END}\nb"
    assert hooks.doc_block(hooks.replace_doc_block(text, "new\n")) == "new\n"
