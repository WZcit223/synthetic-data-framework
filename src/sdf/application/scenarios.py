"""Scenario / what-if simulation runner (Application Layer).

A single dataset answers "what is"; industry planning needs "what if". This
module generates one world per scenario (the spec transforms live in
``sdf.synthesis.scenarios``) and compares the resulting KPIs and inventory
stress so planners can see how the warehouse behaves under stress — before it
happens.

ALGORITHM-HOOK: for a true digital twin, replace the parametric spec transforms
with a discrete-event simulator or an agent-based model of the facility.
"""

from __future__ import annotations

from sdf.synthesis.materialise import build_registry
from sdf.synthesis.scenarios import SCENARIOS, apply_scenario
from sdf.synthesis.spec import GenerationSpec
from .intelligence import WarehouseIntelligence


def run_scenarios(
    base_spec: GenerationSpec | None = None, names: list[str] | None = None, service_level: float = 0.95
) -> dict:
    """Generate each scenario world and compare KPIs + inventory stress."""
    base = base_spec or GenerationSpec()
    names = names or list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        raise KeyError(f"unknown scenario(s) {unknown}; choose from {sorted(SCENARIOS)}")
    rows: list[dict] = []
    for name in names:
        spec = apply_scenario(base, SCENARIOS[name])
        _wh, reg = build_registry(spec)
        intel = WarehouseIntelligence(reg)
        k = intel.kpis()
        ss = intel.replenishment_ss_policy(service_level=service_level)
        stockouts = sum(1 for a in intel.anomalies() if a["type"] == "stockout")
        rows.append(
            {
                "scenario": name,
                "outbound_lines": k.outbound_lines,
                "inventory_value": k.inventory_value,
                "skus_needing_order": ss["skus_needing_order"],
                "safety_stock_units": ss["total_safety_stock_units"],
                "active_stockouts": stockouts,
            }
        )
    base_row = next((r for r in rows if r["scenario"] == "baseline"), rows[0])
    for r in rows:
        r["safety_stock_vs_baseline_pct"] = round(
            100 * (r["safety_stock_units"] - base_row["safety_stock_units"]) / max(1, base_row["safety_stock_units"]), 1
        )
    return {"service_level": service_level, "scenarios": rows}
