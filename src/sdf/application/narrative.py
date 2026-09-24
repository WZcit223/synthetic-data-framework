"""Text insights over the computed facts (Application Layer)."""

from __future__ import annotations

from sdf.foundation.registry import DataSourceRegistry
from .anomaly_rules import rule_anomalies
from .kpi import kpis
from .replenishment import ss_policy


def insights(reg: DataSourceRegistry) -> list[str]:
    """Natural-language-ish findings.

    ALGORITHM-HOOK[C6]: replace this with an LLM + knowledge-graph layer
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
        f"{ss_policy(reg, service_level=0.95, top_n=0)['skus_needing_order']} SKUs need an order under the "
        "95% service-level (s,S) policy.",
    ]
