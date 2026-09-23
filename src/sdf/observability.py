"""Run logging / audit trail (cross-cutting, dependency-free).

A single structured logger reused by the Agent (tool-call trace) and the Workflow
(step trace). Every recorded entry is a small, serialisable dict — an auditable
record of *what ran, with what inputs, producing what, and whether it succeeded*.
Persist to JSONL for a durable audit log, or keep in memory for a demo.

This is the observability substrate an industrial deployment needs (audit,
debugging, compliance). ALGORITHM-HOOK: swap the JSONL sink for OpenTelemetry /
a real tracing backend without changing callers.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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


@dataclass
class LogEntry:
    seq: int
    ts: str
    kind: str  # "tool" | "step"
    name: str
    status: str  # "ok" | "error"
    duration_ms: int
    inputs: Dict[str, Any] = field(default_factory=dict)
    output: Any = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
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
    """Collects an ordered, serialisable trace of a run."""

    def __init__(self, run_kind: str = "run", sink_path: Optional[str] = None) -> None:
        self.run_id = run_kind + "-" + uuid.uuid4().hex[:8]
        self.run_kind = run_kind
        self.started = _now()
        self.entries: List[LogEntry] = []
        self._sink_path = sink_path

    def record(
        self,
        kind: str,
        name: str,
        inputs: Dict[str, Any],
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
        self.entries.append(e)
        if self._sink_path:
            with open(self._sink_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"run_id": self.run_id, **e.to_dict()}) + "\n")
        return e

    @contextmanager
    def step(self, kind: str, name: str, inputs: Optional[Dict[str, Any]] = None):
        """Time a block; record ok/error automatically. Yields a dict you fill
        with the step's output under key 'output'."""
        box: Dict[str, Any] = {"output": None, "note": ""}
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

    def summary(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
        return {**self.summary(), "trace": [e.to_dict() for e in self.entries]}
