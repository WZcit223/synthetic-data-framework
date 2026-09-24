"""Run every intervention × policy × outcome combination on one world."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sdf.foundation.tables import Field
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


# The fields of an experiment's rows, so a client can pivot them like any table. A metric's value is
# averaged when rows are combined: rates such as fill_rate cannot be summed across policies.
OUTCOME_FIELDS = (
    Field("intervention", "Intervention", "dimension"),
    Field("policy", "Policy", "dimension"),
    Field("metric", "Metric", "dimension"),
    Field("value", "Value", "measure", aggregate="mean"),
)


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
