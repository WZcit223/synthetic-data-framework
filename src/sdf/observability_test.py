"""Tests for the run logger."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime

import pytest

from .observability import RunLogger, _json_safe


def test_observability_runlogger():
    log = RunLogger("test")
    with log.step("step", "a", inputs={"x": 1}) as box:
        box["output"] = {"ok": True}
    log.record("tool", "b", {"y": 2}, "done")
    d = log.to_dict()
    assert d["steps"] == 2 and d["ok"] == 2
    assert d["trace"][0]["name"] == "a"


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_the_sink_gets_values_whole_while_the_trace_stays_short(tmp_path):
    sink = tmp_path / "audit.jsonl"
    rows = list(range(10))
    text = "x" * 500
    with RunLogger("test", sink_path=str(sink)) as log:
        log.record("tool", "a", {"rows": rows}, {"text": text, "rows": rows})
    trace = log.to_dict()["trace"][0]
    assert trace["inputs"]["rows"] == {"type": "list", "len": 10, "head": [0, 1, 2]}
    assert len(trace["output"]["text"]) < 100

    entry, summary = _lines(sink)
    assert entry["record"] == "entry" and entry["run_id"] == log.run_id
    assert entry["inputs"] == {"rows": rows}
    assert entry["output"] == {"text": text, "rows": rows}
    assert summary["record"] == "summary"
    assert {k: summary[k] for k in ("run_id", "steps", "ok", "errors")} == {
        "run_id": log.run_id,
        "steps": 1,
        "ok": 1,
        "errors": 0,
    }


def test_the_summary_closes_the_run_even_when_a_step_fails(tmp_path):
    sink = tmp_path / "audit.jsonl"
    with pytest.raises(RuntimeError), RunLogger("test", sink_path=str(sink)) as log:
        with log.step("step", "boom"):
            raise RuntimeError("no")
    log.close()  # a second close writes nothing
    entry, summary = _lines(sink)
    assert entry["status"] == "error" and entry["output"] == {"error": "no"}
    assert summary["record"] == "summary" and summary["errors"] == 1


def test_json_safe_converts_what_json_cannot_hold():
    @dataclass
    class Row:
        when: datetime
        qty: int

    safe = _json_safe({1: Row(datetime(2025, 1, 2, 3, 4), 5), "n": [math.nan, (1, 2)], "o": object})
    assert safe == {"1": {"when": "2025-01-02T03:04:00", "qty": 5}, "n": ["nan", [1, 2]], "o": str(object)}
    json.dumps(safe, allow_nan=False)


def test_json_safe_keeps_keys_that_would_collide():
    assert _json_safe({1: "a", "2": "b"}) == {"1": "a", "2": "b"}
    assert _json_safe({1: "a", "1": "b"}) == [[1, "a"], ["1", "b"]]


def test_a_closed_run_takes_no_more_entries(tmp_path):
    sink = tmp_path / "audit.jsonl"
    with RunLogger("test", sink_path=str(sink)) as log:
        log.record("tool", "a", {}, 1)
    with pytest.raises(RuntimeError, match="closed"):
        log.record("tool", "late", {}, 2)
    assert [line["record"] for line in _lines(sink)] == ["entry", "summary"]
