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
from sdf.synthesis.materialise import DEFAULT_WAREHOUSE_SYNTHESIZER
from sdf.synthesis.registry import SynthesizerRegistry, default_registry
from sdf.synthesis.spec import GenerationSpec

MIN_SKUS = 10
MIN_HORIZON_DAYS = 14


@dataclass(frozen=True)
class GenerateLimits:
    """Upper bounds for ``/generate`` (project lead, 2026-09-23); the lower bounds are fixed."""

    max_skus: int = 500
    max_horizon_days: int = 180

    def __post_init__(self) -> None:
        # A maximum below the fixed minimum would make /generate reject every request.
        if self.max_skus < MIN_SKUS:
            raise ValueError(f"max_skus must be at least {MIN_SKUS}, got {self.max_skus}")
        if self.max_horizon_days < MIN_HORIZON_DAYS:
            raise ValueError(f"max_horizon_days must be at least {MIN_HORIZON_DAYS}, got {self.max_horizon_days}")


@dataclass(frozen=True)
class Snapshot:
    world: World
    intel: WarehouseIntelligence
    generated_ms: int


class GenerationBusy(RuntimeError):
    """Another generation is running; the caller should retry later."""


def build_snapshot(
    spec: GenerationSpec,
    *,
    synthesizer: str = DEFAULT_WAREHOUSE_SYNTHESIZER,
    synthesizers: SynthesizerRegistry | None = None,
) -> Snapshot:
    t0 = time.perf_counter()
    world = World.generate(spec, synthesizer=synthesizer, synthesizers=synthesizers)
    intel = WarehouseIntelligence(world.registry)
    return Snapshot(world=world, intel=intel, generated_ms=int((time.perf_counter() - t0) * 1000))


class WorldStore:
    """The current snapshot; every world it builds comes from ``synthesizers`` (default: ``default_registry()``)."""

    def __init__(self, spec: GenerationSpec | None = None, *, synthesizers: SynthesizerRegistry | None = None) -> None:
        self._lock = threading.Lock()
        self.synthesizers = synthesizers if synthesizers is not None else default_registry()
        self._current = build_snapshot(spec or GenerationSpec(), synthesizers=self.synthesizers)

    @property
    def current(self) -> Snapshot:
        return self._current

    def regenerate(self, spec: GenerationSpec, *, synthesizer: str | None = None) -> Snapshot:
        """Build a new snapshot and make it current in one assignment; raise ``GenerationBusy`` if one is running.

        ``synthesizer`` names the warehouse generator; ``None`` keeps the current world's.
        """
        if not self._lock.acquire(blocking=False):
            raise GenerationBusy("another generation is running; retry when it finishes")
        try:
            name = synthesizer if synthesizer is not None else self._current.world.synthesizer
            snapshot = build_snapshot(spec, synthesizer=name, synthesizers=self.synthesizers)
            self._current = snapshot
            return snapshot
        finally:
            self._lock.release()
