"""Optional FastAPI surface for the shell (requires `pip install fastapi uvicorn`).

    uvicorn sdf.api.app:app --reload

Endpoints mirror the CLI so a front-end dashboard can render the same demo.
Keeping this optional preserves the zero-dependency guarantee of the core.
"""

from __future__ import annotations

try:
    from fastapi import FastAPI
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "FastAPI is optional. Install it with: pip install fastapi uvicorn"
    ) from exc

from sdf.cli import build_registry
from sdf.synthesis.warehouse import GenerationSpec
from sdf.synthesis.quality import structural_quality_check
from sdf.application.warehouse_demo import WarehouseIntelligence

app = FastAPI(title="Synthetic Data Framework — Warehouse Shell", version="0.1.0")

# Generate once at startup; a real deployment would regenerate per-request/spec.
_wh, _reg = build_registry(GenerationSpec())
_intel = WarehouseIntelligence(_reg)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/foundation/summary")
def foundation_summary():
    return _reg.summary()


@app.get("/synthesis/quality")
def synthesis_quality():
    return structural_quality_check(_wh).to_dict()


@app.get("/application/kpis")
def application_kpis():
    return _intel.kpis().__dict__


@app.get("/application/replenishment")
def application_replenishment(top_n: int = 10):
    return _intel.replenishment_suggestions(top_n=top_n)


@app.get("/application/insights")
def application_insights():
    return {"insights": _intel.insights(),
            "abc": _intel.abc_distribution(),
            "anomalies": _intel.anomalies()[:50]}
