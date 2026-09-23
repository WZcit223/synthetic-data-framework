"""Text insights over the computed facts (Application Layer)."""

from __future__ import annotations

from sdf.foundation.registry import DataSourceRegistry
from .anomaly_rules import rule_anomalies
from .kpi import kpis
from .replenishment import rule_suggestions


def insights(reg: DataSourceRegistry) -> list[str]:
    """Natural-language-ish findings.

    ALGORITHM-HOOK: replace this with an LLM + knowledge-graph layer
    (retrieval over the entity graph -> grounded narrative).
    """
    k = kpis(reg)
    anomalies = rule_anomalies(reg)
    stockouts = sum(1 for a in anomalies if a["type"] == "stockout")
    dead = sum(1 for a in anomalies if a["type"] == "dead_stock")
    return [
        f"Managing {k.total_skus} SKUs, {k.total_on_hand:,} units on hand, inventory value ≈ {k.inventory_value:,.0f}.",
        f"Order cancel rate {k.cancel_rate:.1%}, express share {k.express_rate:.1%}.",
        f"{stockouts} active stockouts and {dead} dead-stock SKUs detected.",
        f"{len(rule_suggestions(reg, 999))} SKUs are at/below reorder point.",
    ]
