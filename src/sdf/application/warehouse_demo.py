"""AI Warehouse-Management demo logic (Application Layer).

This is the *application shell*: it consumes whatever the DataSourceRegistry
overlays (synthetic today, real later) and produces the four capability
families the framework claims to cover — data management, knowledge
organisation, decision support, and insight. Each "AI" function here is a
transparent rule-based stand-in; the real model that replaces it is named at
its ``# ALGORITHM-HOOK``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from sdf.foundation.registry import DataSourceRegistry


@dataclass
class KPISummary:
    total_skus: int
    total_on_hand: int
    inventory_value: float
    outbound_lines: int
    cancel_rate: float
    express_rate: float


class WarehouseIntelligence:
    """Reads the overlaid data streams and emits KPIs, actions and insights."""

    def __init__(self, registry: DataSourceRegistry) -> None:
        self.reg = registry

    # -- capability 1: data management / KPIs ------------------------------

    def kpis(self) -> KPISummary:
        skus = {s.sku_id: s for s in self.reg.stream("SKU")}
        inv = self.reg.stream("InventorySnapshot")
        out = self.reg.stream("OutboundOrder")

        on_hand = sum(s.on_hand for s in inv)
        value = sum(
            s.on_hand * skus[s.sku_id].unit_cost
            for s in inv if s.sku_id in skus
        )
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

    # -- capability 2: decision support / replenishment --------------------

    def replenishment_suggestions(self, top_n: int = 10) -> List[Dict]:
        """Rule-based reorder-point flags.

        ALGORITHM-HOOK: replace the fixed safety-stock rule with a fitted
        demand-forecast + (s,S) / newsvendor optimiser learned from real
        order history.
        """
        skus = {s.sku_id: s for s in self.reg.stream("SKU")}
        inv = self.reg.stream("InventorySnapshot")
        demand = self._daily_demand()

        suggestions: List[Dict] = []
        for snap in inv:
            d = demand.get(snap.sku_id, 0.0)
            lead = 7  # placeholder average lead time
            safety = d * 3
            reorder_point = d * lead + safety
            if snap.available <= reorder_point:
                target = d * (lead + 14) + safety  # cover to next cycle
                qty = max(0, int(round(target - snap.available)))
                if qty > 0:
                    suggestions.append({
                        "sku_id": snap.sku_id,
                        "name": skus.get(snap.sku_id).name if snap.sku_id in skus else "?",
                        "on_hand": snap.on_hand,
                        "available": snap.available,
                        "avg_daily_demand": round(d, 2),
                        "reorder_point": round(reorder_point, 1),
                        "suggested_order_qty": qty,
                        "urgency": round(reorder_point - snap.available, 1),
                    })
        suggestions.sort(key=lambda x: x["urgency"], reverse=True)
        return suggestions[:top_n]

    # -- capability 3: insight / anomaly & ABC -----------------------------

    def anomalies(self) -> List[Dict]:
        """Flag stockouts and dead stock.

        ALGORITHM-HOOK: replace threshold rules with an anomaly-detection model
        (isolation forest / autoencoder) over the multivariate inventory series.
        """
        inv = self.reg.stream("InventorySnapshot")
        demand = self._daily_demand()
        out: List[Dict] = []
        for snap in inv:
            if snap.available == 0:
                out.append({"type": "stockout", "sku_id": snap.sku_id,
                            "location_id": snap.location_id})
            elif demand.get(snap.sku_id, 0.0) == 0.0 and snap.on_hand > 100:
                out.append({"type": "dead_stock", "sku_id": snap.sku_id,
                            "on_hand": snap.on_hand})
        return out

    def abc_distribution(self) -> Dict[str, int]:
        dist: Dict[str, int] = defaultdict(int)
        for s in self.reg.stream("SKU"):
            dist[s.abc_class] += 1
        return dict(sorted(dist.items()))

    # -- capability 4: knowledge organisation ------------------------------

    def insights(self) -> List[str]:
        """Natural-language-ish findings.

        ALGORITHM-HOOK: replace this with an LLM + knowledge-graph layer
        (retrieval over the entity graph -> grounded narrative).
        """
        k = self.kpis()
        anomalies = self.anomalies()
        stockouts = sum(1 for a in anomalies if a["type"] == "stockout")
        dead = sum(1 for a in anomalies if a["type"] == "dead_stock")
        lines = [
            f"Managing {k.total_skus} SKUs, {k.total_on_hand:,} units on hand, "
            f"inventory value ≈ {k.inventory_value:,.0f}.",
            f"Order cancel rate {k.cancel_rate:.1%}, express share {k.express_rate:.1%}.",
            f"{stockouts} active stockouts and {dead} dead-stock SKUs detected.",
            f"{len(self.replenishment_suggestions(999))} SKUs are at/below reorder point.",
        ]
        return lines

    # -- internals ---------------------------------------------------------

    def _daily_demand(self) -> Dict[str, float]:
        out = self.reg.stream("OutboundOrder",
                              where=lambda o: o.status != "cancelled")
        totals: Dict[str, int] = defaultdict(int)
        days = set()
        for o in out:
            totals[o.sku_id] += o.quantity
            days.add(o.ts.date())
        horizon = max(1, len(days))
        return {sku: qty / horizon for sku, qty in totals.items()}
