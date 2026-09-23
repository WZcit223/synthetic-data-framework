"""Grounded knowledge Q&A over the warehouse (checklist C6).

A natural-language interface that answers questions about the current world by
routing intents to the Application Layer's computed facts, then phrasing a
grounded answer with the real numbers. Every answer is backed by data the layers
produced — nothing is invented.

This is the transparent, dependency-free version of the capability. ALGORITHM-HOOK:
replace the intent router + templated phrasing with an **LLM over a knowledge
graph** (retrieval across the entity graph → grounded generation), keeping the
same "answers must be grounded in computed facts" contract.
"""

from __future__ import annotations

from collections.abc import Callable

from sdf.analytics.forecast import build_series, compare_models, models_for


def _pct_text(value: float | None) -> str:
    """A percentage for an answer; ``None`` (undefined, e.g. no sales) reads as n/a."""
    return "n/a" if value is None else f"{value}%"


class KnowledgeQA:
    """Intent-routed Q&A backed by WarehouseIntelligence."""

    def __init__(self, intel) -> None:
        self.intel = intel
        # (keywords, handler) — first keyword hit wins, so order by specificity.
        self._routes: list[tuple[list[str], Callable[[], dict]]] = [
            (["stockout", "out of stock", "缺货"], self._stockouts),
            (["dead stock", "slow moving", "呆滞", "dead"], self._dead_stock),
            (["safety stock", "service level", "s,s", "(s,s)", "安全库存"], self._safety),
            (["reorder", "replenish", "补货", "order"], self._replenish),
            (["forecast", "predict", "model", "accuracy", "预测"], self._forecast),
            (["anomal", "unusual", "spike", "异常"], self._anomaly),
            (["vision", "stocktake", "discrepancy", "盘点", "shelf"], self._stocktake),
            (["abc", "class", "pareto"], self._abc),
            (["value", "worth", "inventory value", "价值"], self._value),
            (["how many sku", "total sku", "number of sku", "多少"], self._counts),
            (["help", "what can", "capabilities", "帮助"], self._help),
        ]

    def ask(self, q: str) -> dict:
        ql = (q or "").lower()
        for keys, handler in self._routes:
            if any(k in ql for k in keys):
                res = handler()
                res["question"] = q
                return res
        # Fallback: a portfolio summary.
        res = self._help()
        res["question"] = q
        res["answer"] = (
            "I can answer about stockouts, dead stock, replenishment, "
            "(s,S) safety stock, forecast accuracy, demand anomalies, "
            "vision stocktake, ABC mix, and inventory value. " + res["answer"]
        )
        return res

    # -- intent handlers ---------------------------------------------------

    def _stockouts(self) -> dict:
        an = self.intel.anomalies()
        outs = [a for a in an if a["type"] == "stockout"]
        ex = ", ".join(a["sku_id"] for a in outs[:5])
        return {
            "intent": "stockouts",
            "data": {"count": len(outs)},
            "answer": f"There are {len(outs)} active stockouts" + (f" (e.g. {ex})." if ex else "."),
        }

    def _dead_stock(self) -> dict:
        an = self.intel.anomalies()
        dead = [a for a in an if a["type"] == "dead_stock"]
        return {
            "intent": "dead_stock",
            "data": {"count": len(dead)},
            "answer": f"{len(dead)} SKUs look like dead stock (high on-hand, no recent demand).",
        }

    def _safety(self) -> dict:
        p = self.intel.replenishment_ss_policy(service_level=0.95)
        return {
            "intent": "safety_stock",
            "data": p,
            "answer": f"At a 95% service level, total safety stock is "
            f"{p['total_safety_stock_units']:.0f} units and "
            f"{p['skus_needing_order']} SKUs need an order now.",
        }

    def _replenish(self) -> dict:
        p = self.intel.replenishment_ss_policy(service_level=0.95, top_n=1)
        n = p["skus_needing_order"]
        top = p["rows"][0] if n and p["rows"] else None
        msg = f"{n} SKUs need an order under the 95% service-level (s,S) policy."
        if top:
            msg += f" Largest order: {top['sku_id']} — order {top['order_qty']} units."
        return {"intent": "replenishment", "data": {"count": n, "policy": "service-level-95"}, "answer": msg}

    def _forecast(self) -> dict:
        orders = self.intel.reg.stream("OutboundOrder")
        series, freq, period = build_series(orders)
        rep = compare_models(series, test_len=2 * period, models=models_for(period))
        if not rep["results"]:
            return {
                "intent": "forecast",
                "data": rep,
                "answer": f"There is not enough demand history to measure forecast accuracy ({rep['error']}).",
            }
        best = rep["results"][0]
        return {
            "intent": "forecast",
            "data": rep,
            "answer": f"On the current demand, the best model is "
            f"'{best['model']}' (MAE {best['MAE']}, WAPE {_pct_text(best['WAPE_pct'])}, "
            f"MAPE {_pct_text(best['MAPE_pct'])}) at {freq} granularity.",
        }

    def _anomaly(self) -> dict:
        a = self.intel.demand_anomalies()
        return {
            "intent": "anomaly",
            "data": a,
            "answer": f"{a['count']} demand anomalies detected "
            f"(seasonal-residual, robust-z) on a {a['series_len']}-point "
            f"{a['granularity']} series.",
        }

    def _stocktake(self) -> dict:
        s = self.intel.stocktake_discrepancies()
        return {
            "intent": "stocktake",
            "data": s,
            "answer": f"Vision stocktake matches the books at "
            f"{s['match_rate'] * 100:.0f}% of {s['locations_scanned']} "
            f"locations; {s['flagged']} flagged (net variance "
            f"{s['net_unit_variance']} units).",
        }

    def _abc(self) -> dict:
        d = self.intel.abc_distribution()
        parts = ", ".join(f"{k}:{v}" for k, v in d.items())
        return {"intent": "abc", "data": d, "answer": f"ABC distribution — {parts}."}

    def _value(self) -> dict:
        k = self.intel.kpis()
        return {
            "intent": "inventory_value",
            "data": {"value": k.inventory_value},
            "answer": f"Total inventory value is ≈ {k.inventory_value:,.0f} "
            f"across {k.total_skus} SKUs ({k.total_on_hand:,} units).",
        }

    def _counts(self) -> dict:
        k = self.intel.kpis()
        return {
            "intent": "counts",
            "data": {"skus": k.total_skus, "on_hand": k.total_on_hand},
            "answer": f"There are {k.total_skus} SKUs, {k.total_on_hand:,} "
            f"units on hand, {k.outbound_lines:,} outbound lines.",
        }

    def _help(self) -> dict:
        return {
            "intent": "help",
            "data": {},
            "answer": "Ask me about stockouts, dead stock, replenishment, "
            "(s,S) safety stock, forecast accuracy, anomalies, "
            "vision stocktake, ABC mix, or inventory value.",
        }
