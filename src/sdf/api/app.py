"""The versioned JSON API (``/api/v1``); its OpenAPI schema is the contract with any UI.

    uv sync --extra api
    (cd ui && npm ci && npm run build)
    SDF_UI_DIR=ui/dist uv run uvicorn sdf.api.app:app --reload
    # open http://127.0.0.1:8000 (the dashboard from ui/dist) or /api/v1/docs

``create_app()`` builds an app with its own ``WorldStore`` (``app.state.store``),
dataset catalogue (``app.state.datasets``) and synthesizer registry
(``app.state.synthesizers``);
the module-level ``app`` reads ``SDF_UI_DIR`` (mount a UI directory at "/") and
``SDF_CORS_ORIGINS`` (comma-separated origins allowed to call the API). Every
endpoint reads ``store.current`` once, so a request never mixes two worlds.
"""

# No ``from __future__ import annotations`` here: FastAPI resolves the request body
# type of POST /world from a model built inside create_app(), which a string
# annotation cannot reach.
import csv
import dataclasses
import io
import json
import os
import time
from pathlib import Path

try:
    from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
    from fastapi.concurrency import run_in_threadpool
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pydantic import ConfigDict, Field, create_model
    from starlette.requests import ClientDisconnect
except ImportError as exc:  # pragma: no cover
    raise ImportError("FastAPI is optional. Install it with: uv sync --extra api") from exc

from sdf import __version__
from sdf.analytics.causal import (
    MAX_ESTIMATE_SECONDS,
    CausalQuestion,
    EstimatorRegistry,
    check_confidence,
    check_question,
    default_estimators,
    score,
)
from sdf.analytics.demand import DemandTable
from sdf.analytics.detectors import MAX_DETECTORS, DetectorRegistry, default_detectors
from sdf.analytics.forecast import build_series, compare_models, models_for
from sdf.analytics.forecasters import (
    MAX_BACKTEST_SECONDS,
    MAX_FORECASTERS,
    MAX_HORIZON,
    MAX_ORIGINS,
    MAX_QUANTILES,
    MIN_HISTORY,
    ForecasterRegistry,
    backtest as forecast_backtest,
    default_forecasters,
)
from sdf.application.agent import WarehouseAgent
from sdf.application.datasets import DatasetCatalog, Datasets, ReadDeadline, default_datasets
from sdf.application.economics import financial_impact
from sdf.application.knowledge import KnowledgeQA
from sdf.application.replenishment import sku_forecast
from sdf.application.scenarios import run_scenarios
from sdf.foundation.sources import (
    PREVIEW_ROWS,
    SourceConflict,
    SourceSchema,
    SourceStore,
    SourceTooLarge,
    default_store,
)
from sdf.foundation.tables import Field as TableField, csv_cell
from sdf.simulation import catalog
from sdf.simulation.benchmark import (
    ANOMALY_KINDS,
    QUESTION as BENCHMARK_QUESTION,
    AnomalyBenchmark,
    DemandBenchmark,
    PromotionBenchmark,
)
from sdf.simulation.effects import MAX_EFFECT_WORK, MAX_REPLICATES, EffectStudy
from sdf.simulation.experiment import OUTCOME_FIELDS, Experiment
from sdf.simulation.signals import SIGNALS, signal_frame
from sdf.synthesis.materialise import WarehouseRefused
from sdf.synthesis.registry import SynthesizerRegistry, default_registry
from sdf.synthesis.spec import GenerationSpec
from sdf.validation.evaluation import RunFailed, evaluate
from sdf.validation.quality import structural_quality_check
from sdf.workflow import warehouse_pipeline
from . import schemas as s
from .state import MIN_HORIZON_DAYS, MIN_SKUS, GenerateLimits, GenerationBusy, WorldStore

PREFIX = "/api/v1"
_EXPORT_TABLES = ("skus", "locations", "inventory", "inbound", "outbound", "sensors")
MAX_DATASET_ROWS = 250_000  # the most rows one dataset response carries
MAX_DATASET_CELLS = 2_000_000  # the most cells one data source's dataset response carries, so a wide one has fewer rows
# The most dataset rows one estimation reads. Measured: ipw (the slowest built-in, 200 bootstrap fits)
# takes 4 s on order-lines' 28 897 rows and about 5.5 s at 40 000; the three built-ins together about
# 6 s, and with the causal extra's two about 12 s, well within MAX_ESTIMATE_SECONDS.
MAX_ESTIMATE_ROWS = 40_000
SKU_LEVEL = 0.8  # the central interval of the dashboard's SKU forecast
ANOMALY_FIELDS = (
    TableField("sku_id", "SKU", "dimension"),
    TableField("date", "Date", "time"),
    TableField("score", "Score", "measure", aggregate="max"),
    TableField("direction", "Direction", "dimension"),
    TableField("signals", "Signals", "dimension"),
)


def _spec_dict(spec: GenerationSpec) -> dict:
    """A spec as JSON: its fields, the start date as ISO text."""
    out = dataclasses.asdict(spec)
    out["start"] = spec.start.isoformat()
    return out


def _policy_params(kind: str) -> list[dict]:
    """The form parameters of a policy kind, with the bounds ``POST /experiments`` enforces."""
    names = (
        ("service_level", "lead_time_days", "review_days")
        if kind == "service-level"
        else ("lead_time_days", "review_days")
    )
    params = []
    for name in names:
        info = s.PolicyChoice.model_fields[name]
        bounds = {type(m).__name__: m for m in info.metadata}
        lower, upper = bounds.get("Gt") or bounds.get("Ge"), bounds.get("Lt") or bounds.get("Le")
        params.append(
            {
                "name": name,
                "type": info.annotation.__name__,
                "default": info.default,
                "min": getattr(lower, "gt", getattr(lower, "ge", None)),
                "max": getattr(upper, "lt", getattr(upper, "le", None)),
                "exclusive": "Gt" in bounds or "Lt" in bounds,
                "nullable": False,
            }
        )
    return params


def _question(q: s.QuestionModel) -> CausalQuestion:
    return CausalQuestion(q.treatment, q.outcome, tuple(q.covariates), q.treated_value)


def _check_benchmark_question(q: CausalQuestion) -> None:
    """With the benchmark, a question may only drop covariates from the benchmark's own."""
    b = BENCHMARK_QUESTION
    if (q.treatment, q.outcome, q.treated_value) != (b.treatment, b.outcome, b.treated_value):
        raise HTTPException(
            status_code=422,
            detail=f"with the benchmark the question is {b.treatment} → {b.outcome}; only its covariates may be dropped",
        )
    extra = [c for c in q.covariates if c not in b.covariates]
    if extra:
        raise HTTPException(
            status_code=422,
            detail=f"the benchmark's covariates are {list(b.covariates)}; {extra[0]} is not one of them",
        )


def create_app(
    *,
    limits: GenerateLimits = GenerateLimits(),
    ui_dir: str | Path | None = None,
    cors_origins: list[str] | None = None,
    datasets: DatasetCatalog | None = None,
    synthesizers: SynthesizerRegistry | None = None,
    estimators: EstimatorRegistry | None = None,
    forecasters: ForecasterRegistry | None = None,
    forecaster: str = "gradient-boosting",
    detectors: DetectorRegistry | None = None,
    sources: SourceStore | None = None,
) -> FastAPI:
    """A new app with its own world store, dataset catalogue and synthesizer registry.

    ``datasets`` is the catalogue the app serves for its lifetime (default:
    ``default_datasets()``, built once), so a provider registered on it later is
    served by later requests. ``synthesizers`` is likewise the one registry every
    synthesizer comes from (default: ``default_registry()``, built once): the
    catalogue, runs, the initial world, ``POST /world`` and scenario regeneration. ``estimators``
    is the estimator catalogue (default: ``default_estimators()``) and ``forecasters`` the forecaster
    catalogue (default: ``default_forecasters()``); ``forecaster`` names the one that draws the
    dashboard's SKU forecast (``demand-series``), fitted once per world. ``POST /api/v1/world`` rejects parameters outside
    ``limits``. ``ui_dir``
    mounts a static UI at "/" for development hosting; ``cors_origins`` lets a
    UI hosted elsewhere call the API. ``sources`` is the data source store (default:
    ``default_store()``: the bundled files and ``$SDF_DATA_DIR/sources``); its ``limits``
    bound every upload.
    """
    app = FastAPI(
        title="Synthetic Data Framework — AI Warehouse API",
        version=__version__,
        openapi_url=f"{PREFIX}/openapi.json",
        docs_url=f"{PREFIX}/docs",
        redoc_url=None,
    )
    registry = synthesizers if synthesizers is not None else default_registry()
    app.state.synthesizers = registry
    store = WorldStore(synthesizers=registry)
    app.state.store = store
    app.state.limits = limits
    catalogue = datasets if datasets is not None else default_datasets()
    app.state.datasets = catalogue
    source_store = sources if sources is not None else default_store()
    app.state.sources = source_store
    view = Datasets(catalogue, source_store)
    estimator_reg = estimators if estimators is not None else default_estimators()
    forecaster_reg = forecasters if forecasters is not None else default_forecasters()
    app.state.estimators = estimator_reg
    app.state.forecasters = forecaster_reg
    if forecaster not in forecaster_reg.names():
        raise ValueError(f"forecaster {forecaster!r} is not mounted; mounted: {forecaster_reg.names()}")
    app.state.forecaster = forecaster
    detector_reg = detectors if detectors is not None else default_detectors()
    app.state.detectors = detector_reg
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
        # the warehouse generator; left out, the current world's generator builds the new one
        synthesizer=(str | None, None),
    )

    @api.get("/health", response_model=s.Health)
    def health():
        return {"status": "ok"}

    @api.get("/world", response_model=s.CurrentWorld)
    def world_summary():
        world = store.current.world
        return {**world.registry.summary(), "synthesizer": world.synthesizer}

    @api.post(
        "/world",
        response_model=s.WorldGenerated,
        responses={409: {"description": "a generation is running"}, 422: {"description": "not a warehouse generator"}},
    )
    def generate(body: WorldRequest):  # type: ignore[valid-type]
        values = body.model_dump()
        name = values.pop("synthesizer")
        if name is not None:
            _warehouse_synthesizer(name)
        spec = GenerationSpec(**values)
        try:
            snap = store.regenerate(spec, synthesizer=name)
        except GenerationBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WarehouseRefused as exc:  # it claims a warehouse but returned something else; the world is unchanged
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True, "spec": values, "generated_ms": snap.generated_ms, "synthesizer": snap.world.synthesizer}

    def _warehouse_synthesizer(name: str) -> None:
        """422 unless ``name`` is a mounted synthesizer that produces a warehouse."""
        try:
            produces = registry.info(name).produces
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=exc.args[0]) from exc
        if produces != "warehouse":
            raise HTTPException(status_code=422, detail=f"{name} produces a {produces}, not a warehouse")

    @api.get("/world/limits", response_model=s.WorldLimits)
    def world_limits():
        """The accepted ranges of the generation parameters, so a UI can size its controls."""
        return {
            "n_skus": {"min": MIN_SKUS, "max": limits.max_skus},
            "horizon_days": {"min": MIN_HORIZON_DAYS, "max": limits.max_horizon_days},
        }

    @api.get("/datasets", response_model=s.DatasetList)
    def datasets_list():
        """Every dataset the catalogue serves, with its fields; and the declared ones that could not be mounted."""
        entries = []
        for name in view.names():
            info = view.info(name)
            entries.append(
                {
                    "name": info.name,
                    "label": info.label,
                    "description": info.description,
                    "origin": view.origin(name),
                    "fields": [f.to_dict() for f in info.fields],
                }
            )
        return {"datasets": entries, "unavailable": view.unavailable()}

    @api.get(
        "/datasets/{name}",
        response_model=s.DatasetTable,
        responses={404: {"description": "unknown dataset"}, 500: {"description": "the provider failed"}},
    )
    def dataset(name: str, limit: int | None = Query(None, ge=1, le=MAX_DATASET_ROWS)):
        """One dataset over the current world, or a data source's rows; rows are arrays in field order."""
        world = store.current.world
        try:
            info = view.info(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc
        rows = min(limit or MAX_DATASET_ROWS, MAX_DATASET_ROWS)
        if view.origin(name) == "source":
            rows = max(1, min(rows, MAX_DATASET_CELLS // max(1, len(info.fields))))
        try:
            table, total, sampled = view.head(name, world, rows)
        except Exception as exc:  # a provider's own failure, a KeyError included, is not an unknown dataset
            raise HTTPException(status_code=500, detail=f"dataset {name} could not be built: {exc}") from exc
        return {
            "name": table.info.name,
            "label": table.info.label,
            "world": "" if view.origin(name) == "source" else world.label,  # a source's rows are not the world's
            "fields": [f.to_dict() for f in table.info.fields],
            "rows": [list(r) for r in table.rows],
            "total_rows": total,
            "truncated": total > len(table.rows),
            "sampled": sampled,
        }

    @api.get("/sources", response_model=s.SourceList)
    def sources_list():
        """Every data source, bundled first, with its schema, its last check and the limits an upload must keep."""
        entries, broken = source_store.scan()
        return {
            "sources": [e.to_dict() for e in entries],
            "limits": source_store.limits.to_dict(),
            "unavailable": broken,
        }

    @api.get("/sources/{name}", response_model=s.SourceDetail, responses={404: {"description": "unknown source"}})
    def source_detail(name: str):
        """One source, with its first rows as the file holds them."""
        try:
            entry = source_store.get(name)
            header = [c.name for c in entry.schema.columns]
            return {**entry.to_dict(), "preview": {"header": header, "rows": source_store.preview(name, PREVIEW_ROWS)}}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc
        except (ValueError, OSError) as exc:  # its folder cannot be read
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @api.post(
        "/sources",
        status_code=201,
        response_model=s.SourceEntryModel,
        openapi_extra={"requestBody": {"required": True, "content": {"text/csv": {"schema": {"type": "string"}}}}},
        responses={
            409: {"description": "the name is taken or reserved, or the store is full"},
            413: {"description": "over a size limit"},
            422: {"description": "the name or the file cannot be read"},
        },
    )
    async def source_add(request: Request, name: str = Query(..., description="lower-case words joined by dashes")):
        """Add the CSV in the body as a source; its schema is inferred, to be confirmed with ``PUT …/schema``.

        The body is streamed to disk and refused as soon as it passes the byte limit.
        """
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > source_store.limits.max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"the file is larger than {source_store.limits.max_bytes:,} bytes, the most accepted",
            )
        try:
            upload = await run_in_threadpool(source_store.begin, name)
        except SourceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            async for chunk in request.stream():
                await run_in_threadpool(upload.write, chunk)  # a disk write: off the event loop
            entry = await run_in_threadpool(upload.commit)
        except ClientDisconnect as exc:  # the client went away mid-upload; nothing is kept
            raise HTTPException(status_code=400, detail="the upload was cut off before it ended") from exc
        except SourceTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except SourceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            await run_in_threadpool(upload.discard)  # a folder removal: off the event loop too
        return entry.to_dict()

    @api.put(
        "/sources/{name}/schema",
        response_model=s.SourceEntryModel,
        responses={
            404: {"description": "unknown source"},
            409: {"description": "a bundled source"},
            422: {"description": "the schema does not fit the file"},
        },
    )
    def source_schema(name: str, body: s.SourceSchemaModel):
        """Replace a user source's schema; every row is checked again under it."""
        try:
            schema = SourceSchema.from_dict(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return source_store.update_schema(name, schema).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc
        except SourceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:  # SourceTooLarge included: the limits did not change, but the check says so
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.delete(
        "/sources/{name}",
        status_code=204,
        response_class=Response,
        responses={404: {"description": "unknown source"}, 409: {"description": "a bundled source"}},
    )
    def source_remove(name: str):
        """Delete a user source and its file."""
        try:
            source_store.remove(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc
        except SourceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=204)

    @api.get("/synthesizers", response_model=s.SynthesizerList)
    def synthesizers_list():
        """Every mounted synthesizer with the parameters a run may set; and the declared ones that are unavailable."""
        entries = []
        for name in registry.names():
            info = registry.info(name)
            entries.append(
                {
                    "name": name,
                    "produces": info.produces,
                    "needs_fit": info.needs_fit,
                    "origin": registry.origin(name),
                    "description": info.description,
                    "requires": list(info.requires),
                    "params": [p.to_dict() for p in registry.params(name)],
                }
            )
        return {"synthesizers": entries, "unavailable": registry.unavailable()}

    @api.get("/synthesis/sources", response_model=s.SynthesisSources)
    def synthesis_sources():
        """The data sources a run may be fitted on, by name (the server's own; a client never sends a path).

        Each says whether it has hourly demand, which a series synthesizer needs, and the columns a
        table synthesizer may be fitted on (``<time>.hour`` and ``<time>.weekday`` included).
        """
        return {"sources": [_synthesis_source(e) for e in source_store.list() if not e.schema.problems]}

    def _synthesis_source(entry) -> dict:
        schema = entry.schema
        columns = [c.name for c in schema.columns if c.kind in ("integer", "real", "category")]
        time = schema.roles.time
        if time is not None and time in entry.report.times_of_day:
            columns += [f"{time}.hour", f"{time}.weekday"]
        return {
            "id": entry.name,
            "label": entry.schema.label,
            "origin": entry.origin,
            "series": schema.has_demand and time in entry.report.times_of_day,
            "columns": columns,
        }

    @api.post(
        "/synthesis/runs",
        response_model=s.SynthesisRunResult,
        responses={422: {"description": "not runnable"}, 500: {"description": "the synthesizer failed"}},
    )
    def synthesis_run(body: s.SynthesisRunRequest):
        """Fit one synthesizer on one source and score it; the parameters are checked before it is created."""
        listed = [e.name for e in source_store.list() if not e.schema.problems]
        if body.source not in listed:  # a name, never a path
            raise HTTPException(status_code=422, detail=f"unknown source {body.source!r}; choose from {listed}")
        try:
            run = evaluate(
                body.synthesizer,
                source=body.source,
                params=body.params,
                registry=registry,
                store=source_store,
                columns=body.columns,
                rows=body.rows,
            )
        except RunFailed as exc:  # the plug-in's own code failed: not the request's fault
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except KeyError as exc:  # unknown or unavailable synthesizer
            raise HTTPException(status_code=422, detail=exc.args[0]) from exc
        except ValueError as exc:  # a warehouse generator, a parameter it refuses, a source with no usable row
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "synthesizer": run.synthesizer,
            "source": run.source,
            "kind": run.kind,
            "params": run.params,
            "repeatable": run.repeatable,
            "metrics": run.metrics,
            "columns": list(run.columns) or None,
            "row_choice": run.rows,
            "notes": list(run.notes),
            "fields": [f.to_dict() for f in run.table.info.fields],
            "rows": [list(r) for r in run.table.rows],
        }

    @api.get("/experiments/catalog", response_model=s.ExperimentCatalog)
    def experiments_catalog():
        """The interventions, policies (with their parameters and bounds) and outcomes an experiment may name."""
        return {
            "interventions": catalog.intervention_names(),
            "policies": [{"kind": k, "params": _policy_params(k)} for k in catalog.POLICY_KINDS],
            "outcomes": list(catalog.OUTCOMES),
            "max_per_list": s.MAX_PER_LIST,
            "effects": {"max_replicates": MAX_REPLICATES},
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
    def replenishment(
        service_level: float = Query(0.95, gt=0.5, lt=1.0),
        top_n: int = Query(12, ge=0, le=1000),
        lead_time_days: int = Query(7, ge=1, le=90),
    ):
        return store.current.intel.replenishment_ss_policy(
            service_level=service_level, top_n=top_n, lead_time_days=lead_time_days
        )

    @api.get("/replenishment/comparison", response_model=s.ReplenishmentComparison)
    def replenishment_comparison(service_level: float = Query(0.95, gt=0.5, lt=1.0)):
        return store.current.intel.replenishment_comparison(service_level=service_level)

    @api.get("/top-movers", response_model=list[s.TopMover])
    def top_movers(n: int = 8):
        return store.current.intel.top_movers(n=n)

    @api.get("/demand-series", response_model=s.DemandSeries)
    def demand_series(sku_id: str):
        snapshot = store.current
        series = snapshot.intel.demand_series(sku_id)
        fc = snapshot.forecast(forecaster_reg, forecaster, horizon=series["forecast_horizon_days"], level=SKU_LEVEL)
        return series | {"forecast": sku_forecast(fc, sku_id, SKU_LEVEL)}

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
        try:
            rows = Experiment(store.current.world, interventions, policies, outcomes).run()
        except ValueError as exc:  # an outcome the world cannot measure (a history too short to hold out)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"rows": [r.__dict__ for r in rows], "fields": [f.to_dict() for f in OUTCOME_FIELDS]}

    @api.post("/effects", response_model=s.EffectsResult | s.EffectsBudget)
    def effects(body: s.EffectsRequest):
        """Each intervention against the baseline over paired replicate worlds of the current world's spec.

        ``check_only`` answers the work budget without generating anything; a real run
        answers the effects and every replicate's rows. 422 for an invalid request, a
        request over budget or time, or a generator or intervention that breaks pairing.
        """
        snap = store.current  # one snapshot: its world, spec, generator and registry together
        world = snap.world
        if world.spec is None:
            raise HTTPException(status_code=422, detail="the current world has no GenerationSpec to replicate")
        try:
            study = EffectStudy(
                world.spec,
                [catalog.intervention(n) for n in body.interventions],
                [catalog.policy(p.kind, **p.model_dump(exclude={"kind"})) for p in body.policies],
                [catalog.outcome(n) for n in body.outcomes],
                replicates=body.replicates,
                confidence=body.confidence,
                synthesizer=world.synthesizer,
                synthesizers=world.synthesizers,
                baseline=world,
            )
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=exc.args[0]) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if body.check_only:
            return {
                "work": study.work(),
                "max_work": MAX_EFFECT_WORK,
                "within_budget": study.work() <= MAX_EFFECT_WORK,
                "size": study.size(),
            }
        started = time.monotonic()
        try:
            result = study.run()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "fields": [f.to_dict() for f in result.effects.info.fields],
            "rows": [list(r) for r in result.effects.rows],
            "replicates": {
                "fields": [f.to_dict() for f in result.replicates.info.fields],
                "rows": [list(r) for r in result.replicates.rows],
            },
            "spec": _spec_dict(world.spec),
            "synthesizer": world.synthesizer,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

    @api.get("/estimators", response_model=s.EstimatorList)
    def estimators_list():
        """Every mounted estimator, the unavailable ones with the reason, the request limits and the benchmark."""
        entries = []
        for name in estimator_reg.names():
            info = estimator_reg.info(name)
            entries.append(
                {
                    "name": name,
                    "description": info.description,
                    "origin": estimator_reg.origin(name),
                    "requires": list(info.requires),
                    "uses_covariates": info.uses_covariates,
                }
            )
        return {
            "estimators": entries,
            "unavailable": estimator_reg.unavailable(),
            "limits": {
                "max_rows": MAX_ESTIMATE_ROWS,
                "max_estimators": s.MAX_ESTIMATORS,
                "max_seconds": MAX_ESTIMATE_SECONDS,
            },
            "benchmark": {
                "params": [p.to_dict() for p in PromotionBenchmark.params()],
                "question": BENCHMARK_QUESTION.to_dict(),
            },
        }

    @api.post(
        "/causal/estimates",
        response_model=s.EstimatesResult,
        responses={
            422: {"description": "an invalid request, question or benchmark value, or too many rows"},
            500: {"description": "the benchmark draw or the dataset could not be built"},
        },
    )
    def estimates(body: s.EstimatesRequest):
        """Each chosen estimator on the same rows: the promotion benchmark, or a catalogue dataset.

        A failing estimator is a row with its error in ``method``, not a failed request.
        """
        started = time.monotonic()
        deadline = started + MAX_ESTIMATE_SECONDS
        world = store.current.world  # one snapshot for the draw, the dataset rows and the metadata
        if (body.benchmark is None) == (body.dataset is None):
            raise HTTPException(status_code=422, detail="give exactly one of benchmark and dataset")
        try:
            check_confidence(body.confidence)  # a request problem: refused before any draw or read
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        for name in body.estimators:
            try:
                estimator_reg.info(name)
            except KeyError as exc:
                raise HTTPException(status_code=422, detail=exc.args[0]) from exc
        data = None
        if body.benchmark is not None:
            try:
                bench = PromotionBenchmark(**body.benchmark.model_dump())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"benchmark: {exc}") from exc
            question = BENCHMARK_QUESTION if body.question is None else _question(body.question)
            _check_benchmark_question(question)
            try:
                draw = bench.draw(world)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"the benchmark draw failed: {exc}") from exc
            table, truth, source = draw.table, draw.true_effect, "promotion-benchmark"
            data = {"fields": [f.to_dict() for f in table.info.fields], "rows": [list(r) for r in table.rows]}
        else:
            if body.question is None:
                raise HTTPException(status_code=422, detail=f"a question is needed for dataset {body.dataset}")
            question = _question(body.question)
            try:
                check_question(view.info(body.dataset), question)  # before reading: no data needed
            except KeyError as exc:
                raise HTTPException(status_code=422, detail=exc.args[0]) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            try:
                table, more = view.read(body.dataset, world, limit=MAX_ESTIMATE_ROWS, deadline=deadline)
            except ReadDeadline as exc:  # the request's deadline; a provider's own TimeoutError is its failure (500)
                detail = f"dataset {body.dataset} did not deliver its rows within {MAX_ESTIMATE_SECONDS:g} s"
                raise HTTPException(status_code=422, detail=detail) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"dataset {body.dataset} could not be built: {exc}"
                ) from exc
            if more:
                raise HTTPException(
                    status_code=422,
                    detail=f"dataset {body.dataset} has more than MAX_ESTIMATE_ROWS ({MAX_ESTIMATE_ROWS:,}) rows",
                )
            truth, source = None, body.dataset
        try:
            scores = score(
                table,
                question,
                estimator_reg,
                names=body.estimators,
                true_effect=truth,
                confidence=body.confidence,
                deadline=deadline,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=exc.args[0] if isinstance(exc, KeyError) else str(exc)) from exc
        return {
            "fields": [f.to_dict() for f in scores.info.fields],
            "rows": [list(r) for r in scores.rows],
            "question": question.to_dict(),
            "true_effect": truth,
            "data": data,
            "source": source,
            "world": world.label,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

    @api.get("/forecasters", response_model=s.ForecasterList)
    def forecasters_list():
        """Every mounted forecaster with its parameters, the unavailable ones with the reason, the limits and the benchmark."""
        entries = []
        for name in forecaster_reg.names():
            info = forecaster_reg.info(name)
            entries.append(
                {
                    "name": name,
                    "description": info.description,
                    "origin": forecaster_reg.origin(name),
                    "requires": list(info.requires),
                    "global_model": info.global_model,
                    "params": [p.to_dict() for p in forecaster_reg.params(name)],
                }
            )
        return {
            "forecasters": entries,
            "unavailable": forecaster_reg.unavailable(),
            "limits": {
                "max_forecasters": MAX_FORECASTERS,
                "max_horizon": MAX_HORIZON,
                "max_origins": MAX_ORIGINS,
                "max_quantiles": MAX_QUANTILES,
                "max_skus": s.MAX_FORECAST_SKUS,
                "max_seconds": MAX_BACKTEST_SECONDS,
                "min_history": MIN_HISTORY,
            },
            "benchmark": {"params": [p.to_dict() for p in DemandBenchmark.params()]},
        }

    @api.get("/detectors", response_model=s.DetectorList)
    def detectors_list():
        """Every mounted detector with its parameters, the unavailable ones with the reason, and the benchmark."""
        entries = [
            {
                "name": name,
                "description": detector_reg.info(name).description,
                "origin": detector_reg.origin(name),
                "requires": list(detector_reg.info(name).requires),
                "signals": list(detector_reg.info(name).signals),
                "params": [p.to_dict() for p in detector_reg.params(name)],
            }
            for name in detector_reg.names()
        ]
        return {
            "detectors": entries,
            "unavailable": detector_reg.unavailable(),
            "limits": {"max_detectors": MAX_DETECTORS},
            "signals": list(SIGNALS),
            "benchmark": {"params": [p.to_dict() for p in AnomalyBenchmark.params()], "kinds": list(ANOMALY_KINDS)},
        }

    @api.get(
        "/anomalies",
        response_model=s.AnomaliesResult,
        responses={
            422: {"description": "an unknown detector, or a result the registry refused"},
            500: {"description": "the detector itself failed"},
        },
    )
    def anomalies(detector: str = "seasonal-residual"):
        """One detector's detections on the current world's daily signals per SKU (demand, and the stock and
        receipts of the service-level policy replayed), highest score first."""
        started = time.monotonic()
        world = store.current.world
        try:
            model = detector_reg.create(detector)
        except KeyError as exc:  # unknown or unavailable
            raise HTTPException(status_code=422, detail=exc.args[0]) from exc
        try:
            _, found = detector_reg.run(model, signal_frame(world))
        except ValueError as exc:  # the guard refused its result
            raise HTTPException(status_code=422, detail=f"{detector}: {exc}") from exc
        except Exception as exc:  # the detector's own failure, a KeyError included, is not an unknown detector
            raise HTTPException(
                status_code=500, detail=f"detector {detector} failed: {type(exc).__name__}: {exc}"
            ) from exc
        found.sort(key=lambda d: (-d.score, d.sku_id, d.day))
        return {
            "detector": detector,
            "world": world.label,
            "fields": [f.to_dict() for f in ANOMALY_FIELDS],
            "rows": [
                [d.sku_id, d.day.isoformat(), round(d.score, 4), d.direction, ", ".join(d.signals)] for d in found
            ],
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

    @api.post(
        "/forecasts/backtest",
        response_model=s.ForecastBacktestResult,
        responses={
            422: {"description": "an invalid request, parameter or benchmark value, or a history too short"},
            500: {"description": "the benchmark draw failed"},
        },
    )
    def forecasts_backtest(body: s.ForecastBacktestRequest):
        """Each chosen forecaster from the same rolling origins: the current world's demand, or the demand benchmark.

        A failing forecaster is a row with its error, not a failed request.
        """
        started = time.monotonic()
        source = body.source
        if (source.world is None) == (source.benchmark is None):
            raise HTTPException(status_code=422, detail="source: give exactly one of world and benchmark")
        truth = None
        world_label = None
        if source.benchmark is not None:
            try:
                bench = DemandBenchmark(**source.benchmark.model_dump())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"benchmark: {exc}") from exc
            try:
                draw = bench.draw()
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"the benchmark draw failed: {exc}") from exc
            history, truth, label = draw.table, draw.truth, "demand-benchmark"
        else:
            world = store.current.world  # one snapshot for the demand and the label
            demand = world.demand()
            keep = list(demand.series)[: s.MAX_FORECAST_SKUS]
            history = DemandTable(days=demand.days, series={k: demand.series[k] for k in keep})
            label, world_label = "world", world.label
        try:
            result = forecast_backtest(
                body.forecasters,
                history,
                horizon=body.horizon,
                origins=body.origins,
                step=body.step,
                quantiles=body.quantiles,
                params=body.params,
                refit=body.refit,
                truth=truth,
                deadline=started + MAX_BACKTEST_SECONDS,
                registry=forecaster_reg,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=exc.args[0] if isinstance(exc, KeyError) else str(exc)) from exc

        def table(t):
            return {"fields": [f.to_dict() for f in t.info.fields], "rows": [list(r) for r in t.rows]}

        return {
            "scores": table(result.scores),
            "by_horizon": table(result.by_horizon),
            "forecasts": table(result.forecasts),
            "origins": [d.isoformat() for d in result.origins],
            "source": label,
            "world": world_label,
            "skus": len(history.series),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

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
            w.writerow({k: csv_cell(json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()})
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{entity}.csv"'},
        )

    app.include_router(api)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
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
