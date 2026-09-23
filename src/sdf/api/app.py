"""FastAPI surface + web dashboard for the framework.

    uv sync --extra api
    uv run uvicorn sdf.api.app:app --reload
    # open http://127.0.0.1:8000

``create_app()`` builds an app with its own ``WorldStore`` (``app.state.store``);
the module-level ``app`` is ``create_app()`` with the default limits. Every
endpoint reads ``store.current`` once, so a request never mixes two worlds. The
dashboard (served at "/") is a single dependency-free HTML file with inline SVG
charts, so it runs fully offline.
"""

from __future__ import annotations

import csv
import io
import json
import os

try:
    from fastapi import FastAPI, HTTPException, Query, Response
    from fastapi.responses import HTMLResponse
except ImportError as exc:  # pragma: no cover
    raise ImportError("FastAPI is optional. Install it with: uv sync --extra api") from exc

from sdf import __version__
from sdf.analytics.forecast import build_series, compare_models, models_for
from sdf.application.agent import WarehouseAgent
from sdf.application.economics import financial_impact
from sdf.application.knowledge import KnowledgeQA
from sdf.application.scenarios import run_scenarios
from sdf.synthesis.spec import GenerationSpec
from sdf.validation.quality import structural_quality_check
from sdf.workflow import warehouse_pipeline
from .state import GenerateLimits, GenerationBusy, WorldStore

_STATIC = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
_EXPORT_TABLES = ("skus", "locations", "inventory", "inbound", "outbound", "sensors")


def create_app(*, limits: GenerateLimits = GenerateLimits()) -> FastAPI:
    """A new app with its own world store; ``/generate`` rejects parameters above ``limits``."""
    app = FastAPI(title="Synthetic Data Framework — AI Warehouse", version=__version__)
    store = WorldStore()
    app.state.store = store
    app.state.limits = limits

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        with open(_STATIC, encoding="utf-8") as fh:
            return fh.read()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/generate")
    def generate(
        n_skus: int = Query(200, ge=10, le=limits.max_skus),
        horizon_days: int = Query(90, ge=14, le=limits.max_horizon_days),
        daily_orders_per_a_sku: float = Query(6.0, ge=0.5, le=20.0),
        stockout_pressure: float = Query(0.08, ge=0.0, le=0.5),
        seed: int = 42,
    ):
        spec = GenerationSpec(
            n_skus=n_skus,
            horizon_days=horizon_days,
            daily_orders_per_a_sku=daily_orders_per_a_sku,
            stockout_pressure=stockout_pressure,
            seed=seed,
        )
        try:
            snap = store.regenerate(spec)
        except GenerationBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "ok": True,
            "spec": {
                "n_skus": spec.n_skus,
                "horizon_days": spec.horizon_days,
                "daily_orders_per_a_sku": spec.daily_orders_per_a_sku,
                "stockout_pressure": spec.stockout_pressure,
                "seed": spec.seed,
            },
            "generated_ms": snap.generated_ms,
        }

    @app.get("/foundation/summary")
    def foundation_summary():
        return store.current.world.registry.summary()

    @app.get("/synthesis/quality")
    def synthesis_quality():
        return structural_quality_check(store.current.world.warehouse).to_dict()

    @app.get("/application/kpis")
    def application_kpis():
        return store.current.intel.kpis().__dict__

    @app.get("/application/overview")
    def application_overview():
        snap = store.current
        intel = snap.intel
        return {
            "kpis": intel.kpis().__dict__,
            "abc": intel.abc_distribution(),
            "insights": intel.insights(),
            "anomalies_sample": intel.anomalies()[:20],
            "foundation": snap.world.registry.summary(),
            "quality": structural_quality_check(snap.world.warehouse).to_dict(),
        }

    @app.get("/application/replenishment/comparison")
    def application_replenishment_comparison(service_level: float = 0.95):
        return store.current.intel.replenishment_comparison(service_level=service_level)

    @app.get("/application/replenishment/ss")
    def application_replenishment_ss(service_level: float = 0.95, lead_time_days: int = 7):
        return store.current.intel.replenishment_ss_policy(service_level=service_level, lead_time_days=lead_time_days)

    @app.get("/application/top_movers")
    def application_top_movers(n: int = 8):
        return store.current.intel.top_movers(n=n)

    @app.get("/application/demand_series")
    def application_demand_series(sku_id: str):
        return store.current.intel.demand_series(sku_id)

    @app.get("/application/demand_anomalies")
    def application_demand_anomalies():
        return store.current.intel.demand_anomalies()

    @app.get("/application/ask")
    def application_ask(q: str = ""):
        return KnowledgeQA(store.current.intel).ask(q)

    @app.get("/agent/ask")
    def agent_ask(q: str = ""):
        return WarehouseAgent(store.current.intel).handle(q)

    @app.get("/agent/tools")
    def agent_tools():
        return {"tools": WarehouseAgent(store.current.intel).list_tools()}

    @app.get("/economics/impact")
    def economics_impact():
        return financial_impact(store.current.intel)

    @app.get("/workflow/run")
    def workflow_run():
        res = warehouse_pipeline(world=store.current.world).run()
        return {"pipeline": res["pipeline"], "order": res["order"], "run": res["run"], "trace": res["trace"]}

    @app.get("/scenarios")
    def scenarios():
        return run_scenarios(world=store.current.world)

    @app.get("/application/shelf_occupancy")
    def application_shelf_occupancy():
        return store.current.intel.shelf_occupancy_grid()

    @app.get("/application/stocktake")
    def application_stocktake():
        return store.current.intel.stocktake_discrepancies()

    @app.get("/validation/backtest")
    def validation_backtest():
        """Measured forecast backtest on the current world's demand (real number)."""
        orders = store.current.world.stream("OutboundOrder")
        series, freq, period = build_series(orders)
        report = compare_models(series, test_len=2 * period, models=models_for(period))
        report["granularity"] = freq
        report["seasonal_period"] = period
        return report

    @app.get("/export")
    def export(entity: str = "outbound"):
        """Download the current synthetic dataset for one entity as CSV."""
        wh = store.current.world.warehouse
        rows = getattr(wh, entity) if entity in _EXPORT_TABLES and wh is not None else None
        if not rows:
            return Response(content="unknown or empty entity\n", media_type="text/plain", status_code=404)
        keys = list(rows[0].to_dict().keys())
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=keys)
        w.writeheader()
        for r in rows:
            d = r.to_dict()
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()})
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{entity}.csv"'},
        )

    return app


app = create_app()
