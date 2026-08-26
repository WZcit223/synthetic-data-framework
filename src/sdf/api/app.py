"""FastAPI surface + web dashboard for the shell.

    pip install fastapi uvicorn
    PYTHONPATH=src uvicorn sdf.api.app:app --reload
    # open http://127.0.0.1:8000

The dashboard (served at "/") is a single dependency-free HTML file with inline
SVG charts, so it runs fully offline. Endpoints mirror the CLI and add a
stateful `/generate` so the front-end sliders can re-drive the GenerationSpec.
"""

from __future__ import annotations

import os

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "FastAPI is optional. Install it with: pip install fastapi uvicorn"
    ) from exc

from sdf.cli import build_registry
from sdf.synthesis.warehouse import GenerationSpec
from sdf.synthesis.quality import structural_quality_check
from sdf.application.warehouse_demo import WarehouseIntelligence

app = FastAPI(title="Synthetic Data Framework — Warehouse Shell", version="0.1.0")

_STATIC = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")


class _State:
    """Holds the currently generated world so sliders can regenerate it."""

    def __init__(self) -> None:
        self.regenerate(GenerationSpec())

    def regenerate(self, spec: GenerationSpec) -> None:
        self.spec = spec
        self.wh, self.reg = build_registry(spec)
        self.intel = WarehouseIntelligence(self.reg)


_state = _State()


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    with open(_STATIC, encoding="utf-8") as fh:
        return fh.read()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate")
def generate(n_skus: int = 200, horizon_days: int = 90,
             daily_orders_per_a_sku: float = 6.0,
             stockout_pressure: float = 0.08, seed: int = 42):
    spec = GenerationSpec(
        n_skus=max(10, min(2000, n_skus)),
        horizon_days=max(14, min(365, horizon_days)),
        daily_orders_per_a_sku=max(0.5, min(20.0, daily_orders_per_a_sku)),
        stockout_pressure=max(0.0, min(0.5, stockout_pressure)),
        seed=seed,
    )
    _state.regenerate(spec)
    return {"ok": True, "spec": {
        "n_skus": spec.n_skus, "horizon_days": spec.horizon_days,
        "daily_orders_per_a_sku": spec.daily_orders_per_a_sku,
        "stockout_pressure": spec.stockout_pressure, "seed": spec.seed}}


@app.get("/foundation/summary")
def foundation_summary():
    return _state.reg.summary()


@app.get("/synthesis/quality")
def synthesis_quality():
    return structural_quality_check(_state.wh).to_dict()


@app.get("/application/kpis")
def application_kpis():
    return _state.intel.kpis().__dict__


@app.get("/application/overview")
def application_overview():
    intel = _state.intel
    return {
        "kpis": intel.kpis().__dict__,
        "abc": intel.abc_distribution(),
        "insights": intel.insights(),
        "anomalies_sample": intel.anomalies()[:20],
        "foundation": _state.reg.summary(),
        "quality": structural_quality_check(_state.wh).to_dict(),
    }


@app.get("/application/replenishment")
def application_replenishment(top_n: int = 10):
    return _state.intel.replenishment_suggestions(top_n=top_n)


@app.get("/application/replenishment/simulate")
def application_replenishment_sim():
    return _state.intel.replenishment_simulation()


@app.get("/application/top_movers")
def application_top_movers(n: int = 8):
    return _state.intel.top_movers(n=n)


@app.get("/application/demand_series")
def application_demand_series(sku_id: str):
    return _state.intel.demand_series(sku_id)
