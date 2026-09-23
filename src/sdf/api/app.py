"""The versioned JSON API (``/api/v1``); its OpenAPI schema is the contract with any UI.

    uv sync --extra api
    SDF_UI_DIR=ui uv run uvicorn sdf.api.app:app --reload
    # open http://127.0.0.1:8000 (the dashboard from ui/) or /api/v1/docs

``create_app()`` builds an app with its own ``WorldStore`` (``app.state.store``);
the module-level ``app`` reads ``SDF_UI_DIR`` (mount a UI directory at "/") and
``SDF_CORS_ORIGINS`` (comma-separated origins allowed to call the API). Every
endpoint reads ``store.current`` once, so a request never mixes two worlds.
"""

# No ``from __future__ import annotations`` here: FastAPI resolves the request body
# type of POST /world from a model built inside create_app(), which a string
# annotation cannot reach.
import csv
import io
import json
import os
from pathlib import Path

try:
    from fastapi import APIRouter, FastAPI, HTTPException, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pydantic import ConfigDict, Field, create_model
except ImportError as exc:  # pragma: no cover
    raise ImportError("FastAPI is optional. Install it with: uv sync --extra api") from exc

from sdf import __version__
from sdf.analytics.forecast import build_series, compare_models, models_for
from sdf.application.agent import WarehouseAgent
from sdf.application.economics import financial_impact
from sdf.application.knowledge import KnowledgeQA
from sdf.application.scenarios import run_scenarios
from sdf.simulation import catalog
from sdf.simulation.experiment import Experiment
from sdf.synthesis.spec import GenerationSpec
from sdf.validation.quality import structural_quality_check
from sdf.workflow import warehouse_pipeline
from . import schemas as s
from .state import MIN_HORIZON_DAYS, MIN_SKUS, GenerateLimits, GenerationBusy, WorldStore

PREFIX = "/api/v1"
_EXPORT_TABLES = ("skus", "locations", "inventory", "inbound", "outbound", "sensors")


def create_app(
    *,
    limits: GenerateLimits = GenerateLimits(),
    ui_dir: str | Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """A new app with its own world store.

    ``POST /api/v1/world`` rejects parameters outside ``limits``. ``ui_dir``
    mounts a static UI at "/" for development hosting; ``cors_origins`` lets a
    UI hosted elsewhere call the API.
    """
    app = FastAPI(
        title="Synthetic Data Framework — AI Warehouse API",
        version=__version__,
        openapi_url=f"{PREFIX}/openapi.json",
        docs_url=f"{PREFIX}/docs",
        redoc_url=None,
    )
    store = WorldStore()
    app.state.store = store
    app.state.limits = limits
    api = APIRouter(prefix=PREFIX)

    WorldRequest = create_model(  # noqa: N806 - a model class built from this app's limits
        "WorldRequest",
        __config__=ConfigDict(extra="forbid"),
        # defaults stay inside whatever limits this app was built with
        n_skus=(int, Field(min(200, limits.max_skus), ge=MIN_SKUS, le=limits.max_skus)),
        horizon_days=(int, Field(min(90, limits.max_horizon_days), ge=MIN_HORIZON_DAYS, le=limits.max_horizon_days)),
        daily_orders_per_a_sku=(float, Field(6.0, ge=0.5, le=20.0)),
        stockout_pressure=(float, Field(0.08, ge=0.0, le=0.5)),
        seed=(int, 42),
    )

    @api.get("/health", response_model=s.Health)
    def health():
        return {"status": "ok"}

    @api.get("/world", response_model=s.WorldSummary)
    def world_summary():
        return store.current.world.registry.summary()

    @api.post("/world", response_model=s.WorldGenerated, responses={409: {"description": "a generation is running"}})
    def generate(body: WorldRequest):  # type: ignore[valid-type]
        spec = GenerationSpec(**body.model_dump())
        try:
            snap = store.regenerate(spec)
        except GenerationBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "spec": body.model_dump(), "generated_ms": snap.generated_ms}

    @api.get("/world/limits", response_model=s.WorldLimits)
    def world_limits():
        """The accepted ranges of the generation parameters, so a UI can size its controls."""
        return {
            "n_skus": {"min": MIN_SKUS, "max": limits.max_skus},
            "horizon_days": {"min": MIN_HORIZON_DAYS, "max": limits.max_horizon_days},
        }

    @api.get("/quality", response_model=s.Quality)
    def quality():
        return structural_quality_check(store.current.world.warehouse).to_dict()

    @api.get("/overview", response_model=s.Overview)
    def overview():
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

    @api.get("/replenishment", response_model=s.Replenishment)
    def replenishment(service_level: float = 0.95, top_n: int = 12, lead_time_days: int = 7):
        return store.current.intel.replenishment_ss_policy(
            service_level=service_level, top_n=top_n, lead_time_days=lead_time_days
        )

    @api.get("/replenishment/comparison", response_model=s.ReplenishmentComparison)
    def replenishment_comparison(service_level: float = 0.95):
        return store.current.intel.replenishment_comparison(service_level=service_level)

    @api.get("/top-movers", response_model=list[s.TopMover])
    def top_movers(n: int = 8):
        return store.current.intel.top_movers(n=n)

    @api.get("/demand-series", response_model=s.DemandSeries)
    def demand_series(sku_id: str):
        return store.current.intel.demand_series(sku_id)

    @api.get("/demand-anomalies", response_model=s.DemandAnomalies)
    def demand_anomalies():
        return store.current.intel.demand_anomalies()

    @api.get("/shelf-occupancy", response_model=list[s.ShelfZone])
    def shelf_occupancy():
        return store.current.intel.shelf_occupancy_grid()

    @api.get("/stocktake", response_model=s.Stocktake)
    def stocktake():
        return store.current.intel.stocktake_discrepancies()

    @api.get("/backtest", response_model=s.Backtest)
    def backtest():
        """Measured forecast backtest on the current world's demand (real number)."""
        series, freq, period = build_series(store.current.world.stream("OutboundOrder"))
        report = compare_models(series, test_len=2 * period, models=models_for(period))
        return {**report, "granularity": freq, "seasonal_period": period}

    @api.get("/ask", response_model=s.Answer)
    def ask(q: str = ""):
        return KnowledgeQA(store.current.intel).ask(q)

    @api.get("/agent/ask", response_model=s.AgentAnswer)
    def agent_ask(q: str = ""):
        return WarehouseAgent(store.current.intel).handle(q)

    @api.get("/agent/tools", response_model=s.AgentTools)
    def agent_tools():
        return {"tools": WarehouseAgent(store.current.intel).list_tools()}

    @api.get("/economics", response_model=s.Economics)
    def economics():
        return financial_impact(store.current.intel)

    @api.get("/workflow/run", response_model=s.WorkflowRun)
    def workflow_run():
        res = warehouse_pipeline(world=store.current.world).run()
        return {"pipeline": res["pipeline"], "order": res["order"], "run": res["run"], "trace": res["trace"]}

    @api.get("/scenarios", response_model=s.Scenarios)
    def scenarios():
        return run_scenarios(world=store.current.world)

    @api.post("/experiments", response_model=s.ExperimentResult)
    def experiments(body: s.ExperimentRequest):
        """Run built-in interventions × policies × outcomes on the current world; tidy rows, one per metric."""
        try:
            interventions = [catalog.intervention(n) for n in body.interventions]
            policies = [catalog.policy(p.kind, **p.model_dump(exclude={"kind"})) for p in body.policies]
            outcomes = [catalog.outcome(n) for n in body.outcomes]
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=exc.args[0]) from exc
        for label, names in (
            ("intervention", [i.name for i in interventions]),
            ("policy", [p.name for p in policies]),
            ("outcome", [o.name for o in outcomes]),
        ):
            if len(set(names)) != len(names):
                raise HTTPException(status_code=422, detail=f"each {label} may appear once, got {names}")
        rows = Experiment(store.current.world, interventions, policies, outcomes).run()
        return {"rows": [r.__dict__ for r in rows]}

    @api.get("/export", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
    def export(entity: str = "outbound"):
        """Download the current synthetic dataset for one entity as CSV."""
        wh = store.current.world.warehouse
        rows = getattr(wh, entity) if entity in _EXPORT_TABLES and wh is not None else None
        if not rows:
            raise HTTPException(status_code=404, detail=f"unknown or empty entity {entity!r}")
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

    app.include_router(api)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"]
        )
    if ui_dir is not None:
        path = Path(ui_dir)
        if not (path / "index.html").is_file():
            raise ValueError(f"ui_dir {path} has no index.html")
        app.mount("/", StaticFiles(directory=path, html=True), name="ui")  # after the API routes, so they win
    return app


def _cors_origins_from_env() -> list[str]:
    return [o.strip() for o in os.environ.get("SDF_CORS_ORIGINS", "").split(",") if o.strip()]


app = create_app(ui_dir=os.environ.get("SDF_UI_DIR") or None, cors_origins=_cors_origins_from_env())
