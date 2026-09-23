"""Interventions: changes applied to a world before policies and outcomes run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sdf.synthesis.scenarios import SCENARIOS, apply_scenario
from .world import World


class Intervention(Protocol):
    name: str

    def apply(self, world: World) -> World: ...


@dataclass(frozen=True)
class Baseline:
    """No change."""

    name: str = "baseline"

    def apply(self, world: World) -> World:
        return world


@dataclass(frozen=True)
class SpecIntervention:
    """Regenerate the world from its spec with one scenario's tweaks applied.

    ALGORITHM-HOOK: for a true digital twin, replace the parametric spec
    transforms with a discrete-event simulator or an agent-based model.
    """

    name: str
    tweaks: dict = field(default_factory=dict, hash=False)

    @classmethod
    def named(cls, name: str) -> SpecIntervention:
        if name not in SCENARIOS:
            raise KeyError(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}")
        return cls(name=name, tweaks=SCENARIOS[name])

    def apply(self, world: World) -> World:
        if world.spec is None:
            raise ValueError(f"{self.name}: the world has no GenerationSpec to regenerate from")
        return World.generate(apply_scenario(world.spec, self.tweaks), label=self.name)
