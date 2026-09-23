"""Portfolio KPIs, ABC mix and top movers (Application Layer)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sdf.analytics.demand import DemandTable
from sdf.foundation.registry import DataSourceRegistry


@dataclass
class KPISummary:
    total_skus: int
    total_on_hand: int
    inventory_value: float
    outbound_lines: int
    cancel_rate: float
    express_rate: float


def kpis(reg: DataSourceRegistry) -> KPISummary:
    skus = {s.sku_id: s for s in reg.stream("SKU")}
    inv = reg.stream("InventorySnapshot")
    out = reg.stream("OutboundOrder")

    on_hand = sum(s.on_hand for s in inv)
    value = sum(s.on_hand * skus[s.sku_id].unit_cost for s in inv if s.sku_id in skus)
    cancels = sum(1 for o in out if o.status == "cancelled")
    express = sum(1 for o in out if o.priority == "express")
    n_out = max(1, len(out))
    return KPISummary(
        total_skus=len(skus),
        total_on_hand=on_hand,
        inventory_value=round(value, 2),
        outbound_lines=len(out),
        cancel_rate=round(cancels / n_out, 4),
        express_rate=round(express / n_out, 4),
    )


def abc_distribution(reg: DataSourceRegistry) -> dict[str, int]:
    dist: dict[str, int] = defaultdict(int)
    for s in reg.stream("SKU"):
        dist[s.abc_class] += 1
    return dict(sorted(dist.items()))


def top_movers(reg: DataSourceRegistry, n: int = 8) -> list[dict]:
    """Highest-demand SKUs — entry points for the deep-dive view."""
    demand = DemandTable.from_orders(reg.stream("OutboundOrder")).daily_rates()
    skus = {s.sku_id: s for s in reg.stream("SKU")}
    ranked = sorted(demand.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [
        {
            "sku_id": sid,
            "name": skus[sid].name if sid in skus else "?",
            "abc_class": skus[sid].abc_class if sid in skus else "?",
            "avg_daily_demand": round(d, 2),
        }
        for sid, d in ranked
    ]
