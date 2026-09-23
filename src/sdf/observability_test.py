"""Tests for the run logger."""

from __future__ import annotations

from .observability import RunLogger


def test_observability_runlogger():
    log = RunLogger("test")
    with log.step("step", "a", inputs={"x": 1}) as box:
        box["output"] = {"ok": True}
    log.record("tool", "b", {"y": 2}, "done")
    d = log.to_dict()
    assert d["steps"] == 2 and d["ok"] == 2
    assert d["trace"][0]["name"] == "a"
