"""Run every intervention × policy × outcome combination on one world."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .intervention import Intervention
from .outcome import Outcome
from .policy import Policy
from .world import World


@dataclass(frozen=True)
class OutcomeRow:
    """One measured value; a list of these is a tidy table (pivot- and causal-ready)."""

    intervention: str
    policy: str
    metric: str
    value: float


@dataclass(frozen=True)
class Experiment:
    world: World
    interventions: Sequence[Intervention]
    policies: Sequence[Policy]
    outcomes: Sequence[Outcome]

    def run(self) -> list[OutcomeRow]:
        rows: list[OutcomeRow] = []
        for intervention in self.interventions:
            world = intervention.apply(self.world)
            for policy in self.policies:
                for outcome in self.outcomes:
                    for metric, value in outcome.measure(world, policy).items():
                        rows.append(OutcomeRow(intervention.name, policy.name, metric, value))
        return rows
