"""Lightweight DAG pipeline (Data Intelligence Workflow), dependency-free.

Closes the reported gap "数据智能工作流验证". It makes the implicit
ingest → generate → validate → application → report flow an *explicit* object
with steps, declared dependencies, per-step artifacts, and a logged run record —
without pulling in Airflow/Dagster/Prefect.

Each `Step` names its dependencies; the pipeline runs them in topological order,
passing a shared context dict, timing and logging each via `RunLogger`, and
storing each step's artifact under its name.

ALGORITHM-HOOK: swap the in-process runner for Airflow/Dagster/Prefect; the Step
contract (name, deps, run(ctx)->artifact) is intentionally the same shape.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sdf.application.economics import financial_impact
from sdf.application.intelligence import WarehouseIntelligence
from sdf.foundation.adapters.retail_csv import register_online_retail
from sdf.foundation.registry import DataSourceRegistry
from sdf.observability import RunLogger
from sdf.simulation.world import World
from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from sdf.validation.quality import structural_quality_check


@dataclass
class Step:
    name: str
    run: Callable[[dict[str, Any]], Any]  # run(ctx) -> artifact
    depends_on: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be non-empty")
        if self.name in self.depends_on:
            raise ValueError(f"name {self.name!r} must not appear in its own depends_on")


class Pipeline:
    def __init__(self, steps: list[Step], name: str = "diw") -> None:
        self.name = name
        self.steps = {s.name: s for s in steps}
        self._order = self._toposort(steps)

    def _toposort(self, steps: list[Step]) -> list[str]:
        order, seen, temp = [], set(), set()
        by_name = {s.name: s for s in steps}

        def visit(n: str):
            if n in seen:
                return
            if n in temp:
                raise ValueError(f"cycle at {n}")
            temp.add(n)
            for dep in by_name[n].depends_on:
                if dep not in by_name:
                    raise ValueError(f"{n} depends on unknown step {dep}")
                visit(dep)
            temp.discard(n)
            seen.add(n)
            order.append(n)

        for s in steps:
            visit(s.name)
        return order

    def run(self, ctx: dict[str, Any] | None = None, sink_path: str | None = None) -> dict[str, Any]:
        ctx = dict(ctx or {})
        log = RunLogger(self.name, sink_path=sink_path)
        artifacts: dict[str, Any] = {}
        for name in self._order:
            step = self.steps[name]
            with log.step("step", name, inputs={"depends_on": step.depends_on}) as box:
                art = step.run(ctx)
                artifacts[name] = art
                ctx[name] = art
                box["output"] = art
        return {
            "pipeline": self.name,
            "order": self._order,
            "run": log.summary(),
            "trace": [e.to_dict() for e in log.entries],
            "artifacts": artifacts,
        }


def _economics_summary(economics: dict) -> dict:
    """Keep why economics was skipped (or failed); otherwise report the saving."""
    for key in ("skipped", "error"):
        if key in economics:
            return {key: economics[key]}
    return {"annual_saving": economics.get("annualised_net_saving")}


def warehouse_pipeline(
    spec: GenerationSpec | None = None,
    real_csv: str | None = None,
    *,
    date_format: str | None = None,
    world: World | None = None,
) -> Pipeline:
    """The warehouse Data Intelligence Workflow as an explicit DAG.

    ingest → validate → application → economics → report
    (ingest generates the synthetic world, loads a real CSV via the adapter, or
    uses ``world`` when one is given, e.g. the API's current world).
    """

    def ingest(ctx):
        if real_csv:
            reg = DataSourceRegistry()
            load = register_online_retail(reg, real_csv, date_format=date_format)
            ctx["registry"] = reg
            ctx["_warehouse"] = None
            return {
                "origin": "real",
                "source": real_csv,
                "skus": load.skus,
                "orders": load.orders,
                "load": load.to_dict(),
            }
        if world is not None:
            ctx["registry"] = world.registry
            ctx["_warehouse"] = world.warehouse
            return {"origin": "synthetic" if world.warehouse is not None else "world", **world.registry.summary()}
        wh, reg = build_registry(spec or GenerationSpec())
        ctx["registry"] = reg
        ctx["_warehouse"] = wh
        return {"origin": "synthetic", **reg.summary()}

    def validate(ctx):
        wh = ctx.get("_warehouse")
        if wh is None:
            return {"skipped": "structural checks apply to the synthetic world only"}
        return structural_quality_check(wh).to_dict()

    def application(ctx):
        intel = WarehouseIntelligence(ctx["registry"])
        ctx["_intel"] = intel
        return {
            "kpis": intel.kpis().__dict__,
            "replenishment_flagged": intel.replenishment_ss_policy(service_level=0.95, top_n=0)["skus_needing_order"],
            "anomalies": intel.demand_anomalies().get("count", 0),
        }

    def economics(ctx):
        intel = ctx.get("_intel")
        if intel is None or ctx.get("_warehouse") is None:
            return {"skipped": "economics runs on the synthetic world in this demo"}
        return financial_impact(intel)

    def report(ctx):
        return {
            "validate": ctx.get("validate"),
            "application": ctx.get("application"),
            "economics": _economics_summary(ctx.get("economics") or {}),
        }

    return Pipeline(
        [
            Step("ingest", ingest),
            Step("validate", validate, depends_on=["ingest"]),
            Step("application", application, depends_on=["ingest"]),
            Step("economics", economics, depends_on=["application"]),
            Step("report", report, depends_on=["validate", "application", "economics"]),
        ],
        name="warehouse-diw",
    )
