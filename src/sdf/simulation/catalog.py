"""Built-in interventions, policies and outcomes by name, for callers that only have strings (an HTTP body, a UI)."""

from __future__ import annotations

from collections.abc import Callable

from sdf.synthesis.scenarios import SCENARIOS
from .intervention import Baseline, Intervention, SpecIntervention
from .outcome import ActiveStockouts, CostModel, Outcome, ReplenishmentNeed, SimulatedCost
from .policy import NaivePolicy, Policy, ServiceLevelPolicy

OUTCOMES: dict[str, Callable[[], Outcome]] = {
    "replenishment_need": ReplenishmentNeed,
    "active_stockouts": ActiveStockouts,
    "simulated_cost": lambda: SimulatedCost(CostModel()),
}
POLICY_KINDS = ("naive", "service-level")


def intervention_names() -> list[str]:
    return ["baseline", *(n for n in SCENARIOS if n != "baseline")]


def intervention(name: str) -> Intervention:
    """``baseline`` is the world unchanged; any other name is a generator scenario."""
    if name == "baseline":
        return Baseline()
    if name not in SCENARIOS:
        raise KeyError(f"unknown intervention {name!r}; choose from {intervention_names()}")
    return SpecIntervention.named(name)


def policy(kind: str, *, service_level: float = 0.95, lead_time_days: int = 7, review_days: int = 7) -> Policy:
    if kind == "naive":
        return NaivePolicy(lead_time_days=lead_time_days, review_days=review_days)
    if kind == "service-level":
        return ServiceLevelPolicy(service_level=service_level, lead_time_days=lead_time_days, review_days=review_days)
    raise KeyError(f"unknown policy kind {kind!r}; choose from {list(POLICY_KINDS)}")


def outcome(name: str) -> Outcome:
    if name not in OUTCOMES:
        raise KeyError(f"unknown outcome {name!r}; choose from {sorted(OUTCOMES)}")
    return OUTCOMES[name]()
