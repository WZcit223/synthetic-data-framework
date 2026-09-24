"""Run logging / audit trail (cross-cutting, dependency-free).

A single structured logger reused by the Agent (tool-call trace) and the Workflow
(step trace). Every recorded entry is an auditable record of *what ran, with what
inputs, producing what, and whether it succeeded*.

Two views of the same run: the in-memory ``entries`` (and every trace built from
them) keep a shortened form for display, while the JSONL sink, when one is set,
receives each entry's inputs and output whole, converted to JSON-safe values,
and closes the run with a summary record. The sink is the audit log that can be
replayed; the trace is what a person reads.

This is the observability substrate an industrial deployment needs (audit,
debugging, compliance). ALGORITHM-HOOK[D4]: swap the JSONL sink for OpenTelemetry /
a real tracing backend without changing callers.
"""

from __future__ import annotations

import dataclasses
import json
import math
import numbers
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _summarise(value: Any, limit: int = 240) -> Any:
    """Compact a tool/step output so the log stays small and readable."""
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, dict):
        return {k: _summarise(v, 80) for k, v in list(value.items())[:12]}
    if isinstance(value, (list, tuple)):
        return {"type": "list", "len": len(value), "head": [_summarise(v, 80) for v in list(value)[:3]]}
    return str(value)[:limit]


def _json_safe(value: Any) -> Any:
    """``value`` in full as plain JSON: dataclasses as dicts, datetimes as ISO
    strings, a non-finite number or anything else as its string form.

    A dict whose keys are not all strings keeps string forms of its keys unless
    two keys would share one (``1`` and ``"1"``); then it becomes a list of
    ``[key, value]`` pairs, so no member is lost."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        return number if math.isfinite(number) else str(number)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _json_safe(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        keys = [k if isinstance(k, str) else str(k) for k in value]
        if len(set(keys)) < len(keys):
            return [[_json_safe(k), _json_safe(v)] for k, v in value.items()]
        return {key: _json_safe(v) for key, v in zip(keys, value.values(), strict=True)}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    return str(value)


@dataclass
class LogEntry:
    seq: int
    ts: str
    kind: str  # "tool" | "step"
    name: str
    status: str  # "ok" | "error"
    duration_ms: int
    inputs: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "inputs": self.inputs,
            "output": self.output,
            "note": self.note,
        }


class RunLogger:
    """Collects an ordered, serialisable trace of a run.

    With ``sink_path`` every entry is also appended to that JSONL file in full,
    and :meth:`close` (or leaving the ``with`` block) appends the run's summary.
    """

    def __init__(self, run_kind: str = "run", sink_path: str | None = None) -> None:
        self.run_id = run_kind + "-" + uuid.uuid4().hex[:8]
        self.run_kind = run_kind
        self.started = _now()
        self.entries: list[LogEntry] = []
        self._sink_path = sink_path
        self._closed = False

    def record(
        self,
        kind: str,
        name: str,
        inputs: dict[str, Any],
        output: Any,
        status: str = "ok",
        duration_ms: int = 0,
        note: str = "",
    ) -> LogEntry:
        e = LogEntry(
            seq=len(self.entries) + 1,
            ts=_now(),
            kind=kind,
            name=name,
            status=status,
            duration_ms=duration_ms,
            inputs=_summarise(inputs),
            output=_summarise(output),
            note=note,
        )
        if self._closed:
            raise RuntimeError(f"run {self.run_id} is closed; its summary is already written")
        self.entries.append(e)
        if self._sink_path:  # the full conversion is only for the sink
            full = {**e.to_dict(), "inputs": _json_safe(inputs), "output": _json_safe(output)}
            self._write({"record": "entry", "run_id": self.run_id, **full})
        return e

    def _write(self, line: dict[str, Any]) -> None:
        if self._sink_path:
            with open(self._sink_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False, allow_nan=False) + "\n")

    def close(self) -> None:
        """End the run: append its summary record to the sink (once)."""
        if not self._closed:
            self._closed = True
            self._write({"record": "summary", **self.summary(), "finished": _now()})

    def __enter__(self) -> RunLogger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def step(self, kind: str, name: str, inputs: dict[str, Any] | None = None):
        """Time a block; record ok/error automatically. Yields a dict you fill
        with the step's output under key 'output'."""
        box: dict[str, Any] = {"output": None, "note": ""}
        t0 = time.perf_counter()
        try:
            yield box
            ms = int((time.perf_counter() - t0) * 1000)
            self.record(
                kind, name, inputs or {}, box.get("output"), status="ok", duration_ms=ms, note=box.get("note", "")
            )
        except Exception as exc:  # pragma: no cover - defensive
            ms = int((time.perf_counter() - t0) * 1000)
            self.record(kind, name, inputs or {}, {"error": str(exc)}, status="error", duration_ms=ms)
            raise

    def summary(self) -> dict[str, Any]:
        ok = sum(1 for e in self.entries if e.status == "ok")
        return {
            "run_id": self.run_id,
            "run_kind": self.run_kind,
            "started": self.started,
            "steps": len(self.entries),
            "ok": ok,
            "errors": len(self.entries) - ok,
            "total_ms": sum(e.duration_ms for e in self.entries),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.summary(), "trace": [e.to_dict() for e in self.entries]}
