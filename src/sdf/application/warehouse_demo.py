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

    # -- deep dive: replenishment closed loop ------------------------------

    def demand_series(self, sku_id: str, forecast_days: int = 14) -> Dict:
        """Daily demand history for one SKU + a naive trailing-average forecast.

        ALGORITHM-HOOK: the forecast here is a trailing mean. Replace with a
        fitted model (DeepAR / TFT / LightGBM) to get real predictive intervals.
        """
        out = self.reg.stream(
            "OutboundOrder",
            where=lambda o: o.sku_id == sku_id and o.status != "cancelled",
        )
        by_day: Dict = defaultdict(int)
        for o in out:
            by_day[o.ts.date()] += o.quantity
        days = sorted(by_day)
        history = [{"date": d.isoformat(), "qty": by_day[d]} for d in days]
        recent = [by_day[d] for d in days[-14:]] or [0]
        forecast_avg = round(sum(recent) / len(recent), 2)
        return {
            "sku_id": sku_id,
            "history": history,
            "forecast_avg_daily": forecast_avg,
            "forecast_horizon_days": forecast_days,
            "forecast_total": round(forecast_avg * forecast_days, 1),
        }

    def replenishment_simulation(self) -> Dict:
        """Compare service level before vs. after applying the suggestions.

        This is the 'closed loop' story: forecast -> reorder point -> suggested
        order -> projected effect. ALGORITHM-HOOK: a real sim would roll demand
        forward stochastically over lead time; here we apply a one-step top-up.
        """
        inv = self.reg.stream("InventorySnapshot")
        suggestions = {s["sku_id"]: s for s in self.replenishment_suggestions(9999)}
        total = max(1, len(inv))
        at_risk_before = sum(1 for s in inv if s.sku_id in suggestions)
        stockouts_before = sum(1 for s in inv if s.available == 0)
        # After top-up, flagged SKUs are lifted above their reorder point.
        stockouts_after = sum(
            1 for s in inv
            if s.available == 0 and s.sku_id not in suggestions
        )
        return {
            "skus_total": len(inv),
            "skus_flagged": at_risk_before,
            "stockouts_before": stockouts_before,
            "stockouts_after": stockouts_after,
            "service_level_before": round(1 - at_risk_before / total, 4),
            "service_level_after": round(1 - stockouts_after / total, 4),
        }

    def top_movers(self, n: int = 8) -> List[Dict]:
        """Highest-demand SKUs — entry points for the deep-dive view."""
        demand = self._daily_demand()
        skus = {s.sku_id: s for s in self.reg.stream("SKU")}
        ranked = sorted(demand.items(), key=lambda kv: kv[1], reverse=True)[:n]
        return [
            {"sku_id": sid,
             "name": skus[sid].name if sid in skus else "?",
             "abc_class": skus[sid].abc_class if sid in skus else "?",
             "avg_daily_demand": round(d, 2)}
            for sid, d in ranked
        ]

    # -- capability 5: vision stocktake (multimodal) -----------------------

    def _latest_vision(self) -> Dict:
        """Latest vision_occupancy reading per location."""
        readings = self.reg.stream(
            "SensorReading", where=lambda r: r.modality == "vision_occupancy")
        latest: Dict = {}
        for r in readings:
            cur = latest.get(r.location_id)
            if cur is None or r.ts >= cur.ts:
                latest[r.location_id] = r
        return latest

    def shelf_occupancy_grid(self) -> List[Dict]:
        """Zone → aisle → cells, each cell an occupancy ratio for a heatmap.

        DATA-HOOK: occupancy is a synthetic CV estimate. Replace with real
        shelf-occupancy from the vision pipeline (camera frames / defect model).
        """
        locs = {l.location_id: l for l in self.reg.stream("Location")}
        latest = self._latest_vision()
        zones: Dict = defaultdict(lambda: defaultdict(list))
        for loc_id, r in latest.items():
            loc = locs.get(loc_id)
            if not loc:
                continue
            zones[loc.zone][loc.aisle].append({
                "location_id": loc_id,
                "occupancy": r.value,
                "book_units": r.meta.get("book_units"),
                "est_units": r.meta.get("est_units"),
                "capacity": r.meta.get("capacity"),
            })
        out: List[Dict] = []
        for zone in sorted(zones):
            aisles = [
                {"aisle": a, "cells": sorted(zones[zone][a],
                                             key=lambda c: c["location_id"])}
                for a in sorted(zones[zone])
            ]
            out.append({"zone": zone, "aisles": aisles})
        return out

    def stocktake_discrepancies(self, rel_threshold: float = 0.25,
                                min_abs: int = 15) -> Dict:
        """Compare vision-estimated units vs book-of-record; flag mismatches.

        This is the 'AI stocktake' story: the camera mostly confirms the books,
        but flags locations where physical ≠ system (miscount / misplacement /
        shrinkage). ALGORITHM-HOOK: the real unit estimate comes from a trained
        counting/detection model, not occupancy × capacity.
        """
        latest = self._latest_vision()
        flagged: List[Dict] = []
        matched = 0
        for loc_id, r in latest.items():
            book = r.meta.get("book_units", 0)
            est = r.meta.get("est_units", 0)
            diff = est - book
            rel = abs(diff) / max(1, book)
            if abs(diff) >= min_abs and rel >= rel_threshold:
                flagged.append({
                    "location_id": loc_id, "book_units": book,
                    "vision_units": est, "diff": diff,
                    "direction": "shortage" if diff < 0 else "surplus",
                    "rel": round(rel, 2), "occupancy": r.value,
                })
            else:
                matched += 1
        flagged.sort(key=lambda x: abs(x["diff"]), reverse=True)
        total = len(latest)
        return {
            "locations_scanned": total,
            "matched": matched,
            "flagged": len(flagged),
            "match_rate": round(matched / max(1, total), 4),
            "net_unit_variance": sum(f["diff"] for f in flagged),
            "discrepancies": flagged[:20],
        }

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
