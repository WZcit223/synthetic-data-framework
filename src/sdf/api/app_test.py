"""HTTP contract tests for ``/api/v1``: every field the UI reads, the world limits, snapshot consistency,
the experiment endpoint, the UI boundary and CORS.

Needs the ``api`` extra (FastAPI) and the dev dependency ``httpx2``; skipped otherwise.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx2")  # the transport starlette.testclient uses

from fastapi.testclient import TestClient  # noqa: E402

from .app import create_app  # noqa: E402
from .state import GenerateLimits  # noqa: E402

V1 = "/api/v1"
ROOT = Path(__file__).resolve().parents[3]
UI_DIR = ROOT / "ui"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def fields(obj, *paths: str) -> None:
    """Assert each dotted path exists; ``[]`` descends into the first list element."""
    for path in paths:
        node = obj
        for part in path.split("."):
            if part.endswith("[]"):
                node = node[part[:-2]] if part[:-2] else node
                assert isinstance(node, list) and node, f"{path}: empty or not a list"
                node = node[0]
            else:
                assert part in node, f"{path}: missing {part!r}"
                node = node[part]


def get(client, url):
    res = client.get(V1 + url)
    assert res.status_code == 200, (url, res.status_code, res.text[:200])
    return res.json()


def post_world(client, **body):
    return client.post(V1 + "/world", json=body)


# -- the fields the UI reads ----------------------------------------------------------------------


def test_overview(client):
    body = get(client, "/overview")
    fields(body, "abc", "insights[]", *(f"kpis.{k}" for k in ("total_skus", "total_on_hand", "inventory_value")))
    fields(body, *(f"kpis.{k}" for k in ("outbound_lines", "cancel_rate", "express_rate")))


def test_replenishment_comparison(client):
    body = get(client, "/replenishment/comparison?service_level=0.95")
    fields(body, "service_level", "horizon_days")
    for key in ("policy", "skus_needing_order", "safety_stock_units", "unmet_units", "fill_rate", "holding_cost"):
        fields(body, f"policies[].{key}")
    fields(body, "policies[].order_cost")
    assert [p["policy"] for p in body["policies"]] == ["naive", "service-level-95"]


def test_replenishment(client):
    body = get(client, "/replenishment?service_level=0.95&top_n=5")
    fields(body, "z", "lead_time_days", "review_days", "skus_needing_order", "total_safety_stock_units")
    for key in ("sku_id", "avg_daily_demand", "demand_std", "safety_stock", "reorder_point_s", "order_up_to_S"):
        fields(body, f"rows[].{key}")
    fields(body, "rows[].order_qty")
    assert len(body["rows"]) == 5


@pytest.mark.parametrize(
    "query",
    [
        "/replenishment?service_level=0",
        "/replenishment?service_level=1",
        "/replenishment?top_n=-1",
        "/replenishment?lead_time_days=0",
        "/replenishment/comparison?service_level=0.2",
    ],
)
def test_replenishment_rejects_invalid_parameters(client, query):
    assert client.get(V1 + query).status_code == 422


def test_top_movers_and_demand_series(client):
    movers = get(client, "/top-movers?n=8")
    fields({"m": movers}, "m[].sku_id", "m[].name", "m[].abc_class")
    series = get(client, f"/demand-series?sku_id={movers[0]['sku_id']}")
    fields(series, "history[].date", "history[].qty", "forecast_avg_daily", "forecast_total", "forecast_horizon_days")


def test_vision(client):
    grid = get(client, "/shelf-occupancy")
    for key in ("location_id", "occupancy", "book_units", "est_units"):
        fields({"g": grid}, f"g[].aisles[].cells[].{key}")
    fields({"g": grid}, "g[].zone")
    stock = get(client, "/stocktake")
    fields(stock, "match_rate", "flagged", "locations_scanned", "net_unit_variance")
    for key in ("location_id", "book_units", "vision_units", "diff", "direction"):
        fields(stock, f"discrepancies[].{key}")


def test_backtest(client):
    body = get(client, "/backtest")
    fields(body, "granularity", "series_len", "series_mean", "best_model")
    for key in ("model", "MAE", "RMSE", "MAPE_pct", "bias"):
        fields(body, f"results[].{key}")


def test_ask_and_anomalies(client):
    fields(get(client, "/ask?q=inventory%20value"), "intent", "answer")
    body = get(client, "/demand-anomalies")
    fields(body, "count", "series_len", "granularity", "seasonal_period")
    for key in ("index", "direction", "value", "expected", "robust_z"):
        fields(body, f"anomalies[].{key}")


def test_agent(client):
    body = get(client, "/agent/ask?q=should%20I%20reorder%20and%20what%20is%20the%20money%20impact%3F")
    fields(body, "plan[]", "answer", "proposed_actions[].sku_id", "proposed_actions[].quantity")
    fields(body, "proposed_actions[].status", "trace[].seq", "trace[].name", "trace[].status", "trace[].duration_ms")
    assert body["proposed_actions"][0]["status"] == "PENDING_APPROVAL"


def test_economics_workflow_scenarios(client):
    eco = get(client, "/economics")
    fields(eco, "annualised_net_saving", "stockout_units_avoided", "unmet_units.naive", "unmet_units.ours")
    fields(eco, "horizon_days", "assumptions.holding_cost_annual_rate", "period")
    wf = get(client, "/workflow/run")
    fields(wf, "trace[].seq", "trace[].name", "trace[].status", "trace[].duration_ms")
    fields(wf, "run.run_id", "run.steps", "run.total_ms", "run.errors")
    sc = get(client, "/scenarios")
    for key in (
        "scenario",
        "outbound_lines",
        "skus_needing_order",
        "safety_stock_units",
        "safety_stock_vs_baseline_pct",
    ):
        fields(sc, f"scenarios[].{key}")


def test_other_endpoints_answer(client):
    assert get(client, "/health") == {"status": "ok"}
    fields(get(client, "/world"), "by_entity.SKU")
    fields(get(client, "/quality"), "passed")
    fields(get(client, "/agent/tools"), "tools[].name")
    assert client.get(V1 + "/export?entity=skus").text.startswith("sku_id,")
    assert client.get(V1 + "/export?entity=nope").status_code == 404


def test_json_only_and_old_paths_are_gone(client):
    assert client.get("/").status_code == 404  # no HTML route unless a ui_dir is mounted
    for old in ("/health", "/application/overview", "/foundation/summary", "/economics/impact"):
        assert client.get(old).status_code == 404, old
    assert client.post("/generate").status_code == 404


def test_scenarios_and_workflow_use_the_current_world(client, monkeypatch):
    """Before structure PR 6 both endpoints regenerated their own world from the last spec."""
    import sdf.simulation.world as world_module
    import sdf.workflow.pipeline as pipeline_module

    generated = []
    real_generate = world_module.World.generate.__func__

    def counting_generate(cls, spec, *, label=None):
        generated.append(label)
        return real_generate(cls, spec, label=label)

    monkeypatch.setattr(world_module.World, "generate", classmethod(counting_generate))
    monkeypatch.setattr(pipeline_module, "build_registry", lambda spec: pytest.fail("workflow regenerated the world"))
    store = client.app.state.store
    wf = get(client, "/workflow/run")
    assert wf["run"]["errors"] == 0 and [t["status"] for t in wf["trace"]] == ["ok"] * 5  # ingest never regenerated
    sc = get(client, "/scenarios")
    base = next(r for r in sc["scenarios"] if r["scenario"] == "baseline")
    assert base["outbound_lines"] == len(store.current.world.stream("OutboundOrder"))
    assert "baseline" not in generated and len(generated) == len(sc["scenarios"]) - 1  # only the what-if worlds


# -- POST /world ----------------------------------------------------------------------------------


def test_limits_endpoint(client):
    assert get(client, "/world/limits") == {
        "n_skus": {"min": 10, "max": 500},
        "horizon_days": {"min": 14, "max": 180},
    }


def test_each_app_has_its_own_world():
    first, second = TestClient(create_app()), TestClient(create_app())
    assert first.app.state.store is not second.app.state.store
    assert post_world(first, n_skus=30, horizon_days=14).status_code == 200
    assert get(first, "/overview")["kpis"]["total_skus"] == 30
    assert get(second, "/overview")["kpis"]["total_skus"] == 200  # untouched by the other app


def test_generate_swaps_the_world_and_reports_timing():
    client = TestClient(create_app())
    res = post_world(client, n_skus=40, horizon_days=30, seed=5)
    assert res.status_code == 200
    body = res.json()
    assert body["spec"]["n_skus"] == 40 and body["spec"]["horizon_days"] == 30 and body["generated_ms"] >= 0
    assert get(client, "/overview")["kpis"]["total_skus"] == 40


@pytest.mark.parametrize(
    "body",
    [
        {"n_skus": 501},
        {"horizon_days": 181},
        {"n_skus": 5},
        {"horizon_days": 7},
        {"daily_orders_per_a_sku": 50},
        {"stockout_pressure": 0.9},
        {"unknown": 1},
    ],
)
def test_generate_rejects_invalid_bodies(client, body):
    before = client.app.state.store.current
    assert post_world(client, **body).status_code == 422
    assert client.app.state.store.current is before


def test_limits_are_configurable():
    client = TestClient(create_app(limits=GenerateLimits(max_skus=50, max_horizon_days=40)))
    assert post_world(client, n_skus=60).status_code == 422
    assert post_world(client, n_skus=50, horizon_days=40).status_code == 200
    assert get(client, "/world/limits")["n_skus"]["max"] == 50


def test_defaults_stay_inside_the_smallest_limits():
    client = TestClient(create_app(limits=GenerateLimits(max_skus=10, max_horizon_days=14)))
    res = client.post(V1 + "/world", json={})
    assert res.status_code == 200 and (res.json()["spec"]["n_skus"], res.json()["spec"]["horizon_days"]) == (10, 14)


@pytest.mark.parametrize(
    ("kwargs", "message"), [({"max_skus": 5}, "max_skus"), ({"max_horizon_days": 7}, "max_horizon_days")]
)
def test_limits_below_the_minimum_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        GenerateLimits(**kwargs)


def test_a_second_generation_is_refused_while_one_runs(client):
    store = client.app.state.store
    assert store._lock.acquire(blocking=False)
    try:
        res = post_world(client, n_skus=20, horizon_days=14)
        assert res.status_code == 409 and "another generation" in res.json()["detail"]
    finally:
        store._lock.release()


def test_reads_never_see_a_mixed_world():
    client = TestClient(create_app())
    stop = threading.Event()
    errors: list[BaseException] = []

    def regenerate():
        sizes = [20, 30]
        i = 0
        while not stop.is_set():
            res = post_world(client, n_skus=sizes[i % 2], horizon_days=14, seed=i)
            if res.status_code not in (200, 409):
                errors.append(AssertionError(res.text))
            i += 1

    worker = threading.Thread(target=regenerate)
    worker.start()
    try:
        for _ in range(25):
            body = get(client, "/overview")
            # KPIs and the registry summary in one response must come from the same world.
            assert body["kpis"]["total_skus"] == body["foundation"]["by_entity"]["SKU"]
            assert body["kpis"]["outbound_lines"] == body["foundation"]["by_entity"]["OutboundOrder"]
    finally:
        stop.set()
        worker.join()
    assert not errors


# -- the UI boundary --------------------------------------------------------------------------------


def ui_paths() -> set[str]:
    """Every path ui/app.js passes to api(), without its query string."""
    js = (UI_DIR / "app.js").read_text(encoding="utf-8")
    return {m.split("?")[0] for m in re.findall(r"""api\(\s*["'`](/[^"'`]*)""", js)}


def test_every_ui_path_is_in_the_openapi_schema(client):
    schema_paths = {p.removeprefix(V1) for p in get(client, "/openapi.json")["paths"]}
    used = ui_paths()
    assert len(used) >= 15, used
    assert used <= schema_paths, used - schema_paths
    assert re.findall(r'data-export="([a-z]+)"', (UI_DIR / "index.html").read_text(encoding="utf-8"))
    assert "/export" in schema_paths  # the export links are built from API + "/export"


def test_ui_reaches_the_backend_only_through_api():
    js = (UI_DIR / "app.js").read_text(encoding="utf-8")
    assert js.count("fetch(") == 1  # the one inside api()
    assert 'const API = window.SDF_API_BASE ?? "/api/v1";' in js


def test_the_python_package_contains_no_html():
    package = Path(__file__).resolve().parents[1]
    assert not list(package.rglob("*.html"))


def test_openapi_describes_the_fields(client):
    schemas = get(client, "/openapi.json")["components"]["schemas"]
    assert {"sku_id", "order_qty", "reorder_point_s"} <= set(schemas["ReplenishmentRow"]["properties"])
    assert {"n_skus", "horizon_days"} <= set(schemas["WorldRequest"]["properties"])
    assert {"interventions", "policies", "outcomes"} <= set(schemas["ExperimentRequest"]["properties"])
    assert {"proposed_action", "status", "sku_id", "quantity"} <= set(schemas["ProposedAction"]["properties"])


def test_ui_dir_is_mounted_for_development_hosting():
    client = TestClient(create_app(ui_dir=UI_DIR))
    page = client.get("/")
    assert page.status_code == 200 and '<script src="app.js">' in page.text
    for asset in re.findall(r'(?:href|src)="([^":]+)"', page.text):  # every local file the page loads
        assert client.get("/" + asset).status_code == 200, asset
    assert 'rel="icon" href="favicon.svg"' in page.text
    assert client.get(V1 + "/health").json() == {"status": "ok"}  # API routes still win


def test_ui_dir_without_index_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="no index.html"):
        create_app(ui_dir=tmp_path)


def test_cors_origins():
    client = TestClient(create_app(cors_origins=["http://ui.example"]))
    res = client.get(V1 + "/health", headers={"Origin": "http://ui.example"})
    assert res.headers["access-control-allow-origin"] == "http://ui.example"
    other = client.get(V1 + "/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


# -- POST /experiments ------------------------------------------------------------------------------


def test_experiment_endpoint_returns_the_rows_of_experiment_run(client):
    from sdf.simulation.catalog import intervention, outcome, policy
    from sdf.simulation.experiment import Experiment

    body = {
        "interventions": ["baseline", "promo_spike"],
        "policies": [{"kind": "naive"}, {"kind": "service-level", "service_level": 0.95}],
        "outcomes": ["replenishment_need", "simulated_cost"],
    }
    res = client.post(V1 + "/experiments", json=body)
    assert res.status_code == 200
    expected = Experiment(
        client.app.state.store.current.world,
        [intervention("baseline"), intervention("promo_spike")],
        [policy("naive"), policy("service-level", service_level=0.95)],
        [outcome("replenishment_need"), outcome("simulated_cost")],
    ).run()
    assert res.json()["rows"] == [r.__dict__ for r in expected]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            {"interventions": ["nope"], "policies": [{"kind": "naive"}], "outcomes": ["active_stockouts"]},
            "unknown intervention",
        ),
        ({"policies": [{"kind": "naive"}], "outcomes": ["nope"]}, "unknown outcome"),
        (
            {"policies": [{"kind": "naive"}, {"kind": "naive"}], "outcomes": ["active_stockouts"]},
            "each policy may appear once",
        ),
    ],
)
def test_experiment_endpoint_rejects_unknown_or_duplicate_names(client, body, message):
    res = client.post(V1 + "/experiments", json=body)
    assert res.status_code == 422 and message in res.json()["detail"]


def test_experiment_response_passes_extra_fields_through():
    from .schemas import ExperimentResult

    row = {"intervention": "baseline", "policy": "naive", "metric": "m", "value": 1.0, "unit": "units"}
    dumped = ExperimentResult.model_validate({"rows": [row], "world": "w"}).model_dump()
    assert dumped == {"rows": [row], "world": "w"}


def test_experiment_endpoint_validates_the_body(client):
    assert (
        client.post(V1 + "/experiments", json={"policies": [{"kind": "magic"}], "outcomes": ["x"]}).status_code == 422
    )
    assert client.post(V1 + "/experiments", json={"policies": [], "outcomes": ["active_stockouts"]}).status_code == 422
