"""The API's current world: an immutable snapshot, swapped in one assignment.

Requests read ``WorldStore.current`` once and use only that snapshot, so a
concurrent ``/generate`` can never show them a half-replaced world. One
generation runs at a time; a second one is refused rather than queued, so a
burst of requests cannot tie up the server.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from sdf.application.intelligence import WarehouseIntelligence
from sdf.simulation.world import World
from sdf.synthesis.spec import GenerationSpec


@dataclass(frozen=True)
class GenerateLimits:
    """Upper bounds for ``/generate`` (project lead, 2026-09-23)."""

    max_skus: int = 500
    max_horizon_days: int = 180


@dataclass(frozen=True)
class Snapshot:
    world: World
    intel: WarehouseIntelligence
    generated_ms: int


class GenerationBusy(RuntimeError):
    """Another generation is running; the caller should retry later."""


def build_snapshot(spec: GenerationSpec) -> Snapshot:
    t0 = time.perf_counter()
    world = World.generate(spec)
    intel = WarehouseIntelligence(world.registry)
    return Snapshot(world=world, intel=intel, generated_ms=int((time.perf_counter() - t0) * 1000))


class WorldStore:
    def __init__(self, spec: GenerationSpec | None = None) -> None:
        self._lock = threading.Lock()
        self._current = build_snapshot(spec or GenerationSpec())

    @property
    def current(self) -> Snapshot:
        return self._current

    def regenerate(self, spec: GenerationSpec) -> Snapshot:
        """Build a new snapshot and make it current in one assignment; raise ``GenerationBusy`` if one is running."""
        if not self._lock.acquire(blocking=False):
            raise GenerationBusy("another generation is running; retry when it finishes")
        try:
            snapshot = build_snapshot(spec)
            self._current = snapshot
            return snapshot
        finally:
            self._lock.release()
