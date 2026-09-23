"""Scenario / what-if simulation runner (Application Layer).

A single dataset answers "what is"; industry planning needs "what if". Each
scenario is a ``SpecIntervention`` (the spec transforms live in
``sdf.synthesis.scenarios``); one ``Experiment`` regenerates the world per
scenario and compares the resulting KPIs and inventory stress so planners can
see how the warehouse behaves under stress — before it happens.
"""

from __future__ import annotations

from dataclasses import dataclass

from sdf.simulation.experiment import Experiment
from sdf.simulation.intervention import Baseline, Intervention, SpecIntervention
from sdf.simulation.outcome import ActiveStockouts, ReplenishmentNeed
from sdf.simulation.policy import Policy, ServiceLevelPolicy
from sdf.simulation.world import World
from sdf.synthesis.scenarios import SCENARIOS
from sdf.synthesis.spec import GenerationSpec
from .kpi import kpis


@dataclass(frozen=True)
class ScenarioKPIs:
    """Outbound volume and inventory value, measured with the dashboard's KPI definitions."""

    name: str = "scenario_kpis"

    def measure(self, world: World, policy: Policy) -> dict[str, float]:
        k = kpis(world.registry)
        return {"outbound_lines": k.outbound_lines, "inventory_value": k.inventory_value}


def run_scenarios(
    base_spec: GenerationSpec | None = None, names: list[str] | None = None, service_level: float = 0.95
) -> dict:
    """Generate each scenario world and compare KPIs + inventory stress."""
    base = base_spec or GenerationSpec()
    names = names or list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        raise KeyError(f"unknown scenario(s) {unknown}; choose from {sorted(SCENARIOS)}")
    # "baseline" has no tweaks, so it reuses the base world instead of regenerating it.
    interventions: list[Intervention] = [Baseline() if n == "baseline" else SpecIntervention.named(n) for n in names]
    result = Experiment(
        world=World.generate(base),
        interventions=interventions,
        policies=[ServiceLevelPolicy(service_level=service_level)],
        outcomes=[ScenarioKPIs(), ReplenishmentNeed(), ActiveStockouts()],
    ).run()
    by_scenario: dict[str, dict[str, float]] = {}
    for r in result:
        by_scenario.setdefault(r.intervention, {})[r.metric] = r.value
    rows = [
        {
            "scenario": name,
            "outbound_lines": m["outbound_lines"],
            "inventory_value": m["inventory_value"],
            "skus_needing_order": m["skus_needing_order"],
            "safety_stock_units": m["safety_stock_units"],
            "active_stockouts": m["active_stockouts"],
        }
        for name in names
        for m in [by_scenario[name]]
    ]
    base_row = next((r for r in rows if r["scenario"] == "baseline"), rows[0])
    for r in rows:
        r["safety_stock_vs_baseline_pct"] = round(
            100 * (r["safety_stock_units"] - base_row["safety_stock_units"]) / max(1, base_row["safety_stock_units"]), 1
        )
    return {"service_level": service_level, "scenarios": rows}
