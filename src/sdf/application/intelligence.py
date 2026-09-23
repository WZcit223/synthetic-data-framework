"""AI Warehouse-Management facade (Application Layer).

``WarehouseIntelligence`` keeps one stable object for the web API, the CLI and
the agent. It holds the registry and delegates every capability to the module
that implements it:

- ``kpi`` — KPIs, ABC mix, top movers;
- ``replenishment`` — replenishment policies and the demand deep dive;
- ``anomaly_rules`` — rule anomalies and statistical demand anomalies;
- ``vision`` — shelf occupancy and the vision stocktake;
- ``narrative`` — text insights.

Each "AI" function is a transparent stand-in; the real model that replaces it
is named at its ``# ALGORITHM-HOOK`` in those modules.
"""

from __future__ import annotations

from sdf.analytics.demand import DemandProfile, DemandTable
from sdf.foundation.registry import DataSourceRegistry
from . import anomaly_rules, kpi, narrative, replenishment, vision
from .kpi import KPISummary


class WarehouseIntelligence:
    """Reads the overlaid data streams and emits KPIs, actions and insights."""

    def __init__(self, registry: DataSourceRegistry) -> None:
        self.reg = registry

    def kpis(self) -> KPISummary:
        return kpi.kpis(self.reg)

    def abc_distribution(self) -> dict[str, int]:
        return kpi.abc_distribution(self.reg)

    def top_movers(self, n: int = 8) -> list[dict]:
        return kpi.top_movers(self.reg, n)

    def demand_table(self) -> DemandTable:
        return replenishment.demand_table(self.reg)

    def demand_profiles(self) -> dict[str, DemandProfile]:
        return replenishment.demand_profiles(self.reg)

    def replenishment_suggestions(self, top_n: int = 10) -> list[dict]:
        return replenishment.rule_suggestions(self.reg, top_n)

    def replenishment_simulation(self) -> dict:
        return replenishment.rule_simulation(self.reg)

    def replenishment_ss_policy(
        self, *, lead_time_days: int = 7, review_days: int = 7, service_level: float = 0.95, top_n: int = 12
    ) -> dict:
        return replenishment.ss_policy(
            self.reg, lead_time_days=lead_time_days, review_days=review_days, service_level=service_level, top_n=top_n
        )

    def demand_series(self, sku_id: str, forecast_days: int = 14) -> dict:
        return replenishment.demand_series(self.reg, sku_id, forecast_days)

    def anomalies(self) -> list[dict]:
        return anomaly_rules.rule_anomalies(self.reg)

    def demand_anomalies(self, k: float = 3.5) -> dict:
        return anomaly_rules.demand_anomalies(self.reg, k)

    def shelf_occupancy_grid(self) -> list[dict]:
        return vision.shelf_occupancy_grid(self.reg)

    def stocktake_discrepancies(self, *, rel_threshold: float = 0.25, min_abs: int = 15) -> dict:
        return vision.stocktake_discrepancies(self.reg, rel_threshold=rel_threshold, min_abs=min_abs)

    def insights(self) -> list[str]:
        return narrative.insights(self.reg)
