"""HTTP contract tests: every field the dashboard reads, the /generate limits and snapshot consistency.

Needs the ``api`` extra (FastAPI) and the dev dependency ``httpx``; skipped otherwise.
"""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from .app import create_app  # noqa: E402
from .state import GenerateLimits  # noqa: E402


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
    res = client.get(url)
    assert res.status_code == 200, (url, res.status_code, res.text[:200])
    return res.json()


# -- the fields the dashboard reads (REFACTOR_PREP.md §2.2, after structure PR 3) ----------


def test_overview(client):
    body = get(client, "/application/overview")
    fields(body, "abc", "insights[]", *(f"kpis.{k}" for k in ("total_skus", "total_on_hand", "inventory_value")))
    fields(body, *(f"kpis.{k}" for k in ("outbound_lines", "cancel_rate", "express_rate")))


def test_replenishment_comparison(client):
    body = get(client, "/application/replenishment/comparison?service_level=0.95")
    fields(body, "service_level", "horizon_days")
    for key in ("policy", "skus_needing_order", "safety_stock_units", "unmet_units", "fill_rate", "holding_cost"):
        fields(body, f"policies[].{key}")
    assert [p["policy"] for p in body["policies"]] == ["naive", "service-level-95"]


def test_replenishment_ss(client):
    body = get(client, "/application/replenishment/ss?service_level=0.95")
    fields(body, "z", "lead_time_days", "review_days", "skus_needing_order", "total_safety_stock_units")
    for key in ("sku_id", "avg_daily_demand", "demand_std", "safety_stock", "reorder_point_s", "order_up_to_S"):
        fields(body, f"rows[].{key}")
    fields(body, "rows[].order_qty")


def test_top_movers_and_demand_series(client):
    movers = get(client, "/application/top_movers?n=8")
    fields({"m": movers}, "m[].sku_id", "m[].name", "m[].abc_class")
    series = get(client, f"/application/demand_series?sku_id={movers[0]['sku_id']}")
    fields(series, "history[].date", "history[].qty", "forecast_avg_daily", "forecast_total", "forecast_horizon_days")


def test_vision(client):
    grid = get(client, "/application/shelf_occupancy")
    for key in ("location_id", "occupancy", "book_units", "est_units"):
        fields({"g": grid}, f"g[].aisles[].cells[].{key}")
    fields({"g": grid}, "g[].zone")
    stock = get(client, "/application/stocktake")
    fields(stock, "match_rate", "flagged", "locations_scanned", "net_unit_variance")
    for key in ("location_id", "book_units", "vision_units", "diff", "direction"):
        fields(stock, f"discrepancies[].{key}")


def test_backtest(client):
    body = get(client, "/validation/backtest")
    fields(body, "granularity", "series_len", "series_mean", "best_model")
    for key in ("model", "MAE", "RMSE", "MAPE_pct", "bias"):
        fields(body, f"results[].{key}")


def test_ask_and_anomalies(client):
    fields(get(client, "/application/ask?q=inventory%20value"), "intent", "answer")
    body = get(client, "/application/demand_anomalies")
    fields(body, "count", "series_len", "granularity", "seasonal_period")
    for key in ("index", "direction", "value", "expected", "robust_z"):
        fields(body, f"anomalies[].{key}")


def test_agent(client):
    body = get(client, "/agent/ask?q=should%20I%20reorder%20and%20what%20is%20the%20money%20impact%3F")
    fields(body, "plan[]", "answer", "proposed_actions[].sku_id", "proposed_actions[].quantity")
    fields(body, "proposed_actions[].status", "trace[].seq", "trace[].name", "trace[].status", "trace[].duration_ms")
    assert body["proposed_actions"][0]["status"] == "PENDING_APPROVAL"


def test_economics_workflow_scenarios(client):
    eco = get(client, "/economics/impact")
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
    fields(get(client, "/foundation/summary"), "by_entity.SKU")
    fields(get(client, "/synthesis/quality"), "passed")
    fields(get(client, "/application/kpis"), "total_skus")
    fields(get(client, "/agent/tools"), "tools[].name")
    assert client.get("/export?entity=skus").text.startswith("sku_id,")
    assert client.get("/export?entity=nope").status_code == 404
    assert "<html" in client.get("/").text.lower()


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


def test_limits_endpoint(client):
    assert get(client, "/generate/limits") == {
        "n_skus": {"min": 10, "max": 500},
        "horizon_days": {"min": 14, "max": 180},
    }


# -- /generate ----------------------------------------------------------------------------


def test_generate_swaps_the_world_and_reports_timing():
    client = TestClient(create_app())
    res = client.post("/generate?n_skus=40&horizon_days=30&seed=5")
    assert res.status_code == 200
    body = res.json()
    assert body["spec"]["n_skus"] == 40 and body["spec"]["horizon_days"] == 30 and body["generated_ms"] >= 0
    assert get(client, "/application/kpis")["total_skus"] == 40


@pytest.mark.parametrize(
    "query",
    [
        "n_skus=501",
        "horizon_days=181",
        "n_skus=5",
        "horizon_days=7",
        "daily_orders_per_a_sku=50",
        "stockout_pressure=0.9",
    ],
)
def test_generate_rejects_out_of_range_parameters(client, query):
    before = client.app.state.store.current
    res = client.post("/generate?" + query)
    assert res.status_code == 422
    assert client.app.state.store.current is before


def test_limits_are_configurable():
    client = TestClient(create_app(limits=GenerateLimits(max_skus=50, max_horizon_days=40)))
    assert client.post("/generate?n_skus=60").status_code == 422
    assert client.post("/generate?n_skus=50&horizon_days=40").status_code == 200
    assert get(client, "/generate/limits")["n_skus"]["max"] == 50


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
        res = client.post("/generate?n_skus=20&horizon_days=14")
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
            res = client.post(f"/generate?n_skus={sizes[i % 2]}&horizon_days=14&seed={i}")
            if res.status_code not in (200, 409):
                errors.append(AssertionError(res.text))
            i += 1

    worker = threading.Thread(target=regenerate)
    worker.start()
    try:
        for _ in range(25):
            body = get(client, "/application/overview")
            # KPIs and the registry summary in one response must come from the same world.
            assert body["kpis"]["total_skus"] == body["foundation"]["by_entity"]["SKU"]
            assert body["kpis"]["outbound_lines"] == body["foundation"]["by_entity"]["OutboundOrder"]
    finally:
        stop.set()
        worker.join()
    assert not errors
