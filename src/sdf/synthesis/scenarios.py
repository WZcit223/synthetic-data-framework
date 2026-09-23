"""Scenario / what-if simulation (turns the generator into a simulation engine).

A single dataset answers "what is"; industry planning needs "what if". This
module transforms a base `GenerationSpec` into a **family of scenarios** (promo
spike, supply disruption, seasonal shift, demand downturn), generates each world,
and compares the resulting KPIs and inventory stress so planners can see how the
warehouse behaves under stress — before it happens.

This is the step from "data generator" toward the "仿真引擎" named to management.
ALGORITHM-HOOK: for a true digital twin, replace the parametric spec transforms
with a discrete-event simulator or an agent-based model of the facility.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List

SCENARIOS = {
    "baseline": {},
    "promo_spike": {"daily_orders_per_a_sku_mult": 2.2, "express_ratio": 0.45},
    "supply_disruption": {"stockout_pressure": 0.35},
    "seasonal_downturn": {"daily_orders_per_a_sku_mult": 0.55},
    "high_variability": {"daily_orders_per_a_sku_mult": 1.4, "stockout_pressure": 0.2},
}


def _apply(spec, tweaks: Dict):
    kw = {}
    if "daily_orders_per_a_sku_mult" in tweaks:
        kw["daily_orders_per_a_sku"] = round(spec.daily_orders_per_a_sku * tweaks["daily_orders_per_a_sku_mult"], 3)
    if "stockout_pressure" in tweaks:
        kw["stockout_pressure"] = tweaks["stockout_pressure"]
    if "express_ratio" in tweaks:
        kw["express_ratio"] = tweaks["express_ratio"]
    return replace(spec, **kw)


def run_scenarios(base_spec=None, names: List[str] = None, service_level: float = 0.95) -> Dict:
    """Generate each scenario world and compare KPIs + inventory stress."""
    from sdf.application.warehouse_demo import WarehouseIntelligence
    from sdf.cli import build_registry
    from sdf.synthesis.warehouse import GenerationSpec

    base = base_spec or GenerationSpec()
    names = names or list(SCENARIOS)
    rows: List[Dict] = []
    for name in names:
        spec = _apply(base, SCENARIOS.get(name, {}))
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
