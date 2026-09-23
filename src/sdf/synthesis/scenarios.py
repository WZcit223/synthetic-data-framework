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

from .spec import GenerationSpec

SCENARIOS = {
    "baseline": {},
    "promo_spike": {"daily_orders_per_a_sku_mult": 2.2, "express_ratio": 0.45},
    "supply_disruption": {"stockout_pressure": 0.35},
    "seasonal_downturn": {"daily_orders_per_a_sku_mult": 0.55},
    "high_variability": {"daily_orders_per_a_sku_mult": 1.4, "stockout_pressure": 0.2},
}


def apply_scenario(spec: GenerationSpec, tweaks: dict) -> GenerationSpec:
    """Return a copy of ``spec`` with one scenario's tweaks applied (pure)."""
    kw = {}
    if "daily_orders_per_a_sku_mult" in tweaks:
        kw["daily_orders_per_a_sku"] = round(spec.daily_orders_per_a_sku * tweaks["daily_orders_per_a_sku_mult"], 3)
    if "stockout_pressure" in tweaks:
        kw["stockout_pressure"] = tweaks["stockout_pressure"]
    if "express_ratio" in tweaks:
        kw["express_ratio"] = tweaks["express_ratio"]
    return replace(spec, **kw)
