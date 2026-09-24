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

    def counting_generate(cls, spec, *, label=None, **generator):
        generated.append(label)
        return real_generate(cls, spec, label=label, **generator)

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


def ui_scripts() -> dict[str, str]:
    """Every page script in ui/ (the Node tests aside), by file name."""
    return {
        p.name: p.read_text(encoding="utf-8") for p in sorted(UI_DIR.glob("*.js")) if not p.name.endswith(".test.js")
    }


def ui_paths() -> set[str]:
    """Every path a ui/*.js script passes to api(), without its query string; ``${…}`` reads as ``{}``."""
    paths = set()
    for js in ui_scripts().values():
        for m in re.findall(r"""api\(\s*["'`](/[^"'`]*)""", js):
            paths.add(re.sub(r"\$\{[^}]*\}", "{}", m.split("?")[0]))
    return paths


def test_every_ui_path_is_in_the_openapi_schema(client):
    schema_paths = {re.sub(r"\{[^}]*\}", "{}", p.removeprefix(V1)) for p in get(client, "/openapi.json")["paths"]}
    used = ui_paths()
    assert len(used) >= 19, used
    assert {"/datasets", "/datasets/{}", "/experiments/catalog", "/experiments"} <= used
    assert {"/synthesizers", "/synthesis/sources", "/synthesis/runs", "/world"} <= used
    assert used <= schema_paths, used - schema_paths
    assert re.findall(r'data-export="([a-z]+)"', (UI_DIR / "index.html").read_text(encoding="utf-8"))
    assert "/export" in schema_paths  # the export links are built from API + "/export"


def test_ui_reaches_the_backend_only_through_api():
    scripts = ui_scripts()
    assert sum(js.count("fetch(") for js in scripts.values()) == 1  # the one inside api(), in common.js
    assert "fetch(" in scripts["common.js"]
    assert 'export const API = globalThis.SDF_API_BASE ?? "/api/v1";' in scripts["common.js"]


def test_ui_has_no_inline_event_handler():
    """The pages are ES modules, whose functions are not globals: every handler is registered in a script."""
    for path in sorted(UI_DIR.glob("*.html")) + sorted(UI_DIR.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert not re.findall(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", text), path.name
    for page in ("index.html", "explore.html", "synthesizers.html"):
        html = (UI_DIR / page).read_text(encoding="utf-8")
        assert re.search(r'<script type="module" src="[a-z]+\.js">', html), page
        for link in ("index.html", "explore.html", "synthesizers.html"):  # the navigation bar
            assert f'href="{link}"' in html, (page, link)


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
    assert page.status_code == 200 and '<script type="module" src="app.js">' in page.text
    for url in ("/", "/explore.html", "/synthesizers.html"):
        html = client.get(url).text
        for asset in re.findall(r'(?:href|src)="([^":#]+)"', html):  # every local file the page loads or links
            assert client.get("/" + asset).status_code == 200, (url, asset)
        for js in re.findall(r'src="([^"]+\.js)"', html):  # and every module those scripts import
            for module in re.findall(r'from "\./([^"]+)"', client.get("/" + js).text):
                assert client.get("/" + module).status_code == 200, (js, module)
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
    field = {"name": "value", "label": "Value", "kind": "measure", "unit": None, "aggregate": "mean"}
    dumped = ExperimentResult.model_validate({"rows": [row], "fields": [field], "world": "w"}).model_dump()
    assert dumped == {"rows": [row], "fields": [field], "world": "w"}


def test_experiment_endpoint_validates_the_body(client):
    assert (
        client.post(V1 + "/experiments", json={"policies": [{"kind": "magic"}], "outcomes": ["x"]}).status_code == 422
    )
    assert client.post(V1 + "/experiments", json={"policies": [], "outcomes": ["active_stockouts"]}).status_code == 422


# -- POST /effects (docs/refactor/causal/interfaces.md §1.5) ------------------------------------


@pytest.fixture(scope="module")
def small_client():
    c = TestClient(create_app())
    assert post_world(c, n_skus=30, horizon_days=30).status_code == 200
    return c


def test_effects_answer_the_study_on_the_current_world(small_client):
    from sdf.simulation.catalog import intervention, outcome, policy
    from sdf.simulation.effects import EffectStudy

    body = {"interventions": ["promo_spike"], "outcomes": ["simulated_cost"], "replicates": 3}
    res = small_client.post(V1 + "/effects", json=body)
    assert res.status_code == 200, res.text
    out = res.json()
    world = small_client.app.state.store.current.world
    expected = EffectStudy(
        world.spec,
        [intervention("promo_spike")],
        [policy("service-level", service_level=0.95)],
        [outcome("simulated_cost")],
        replicates=3,
        baseline=world,
    ).run()
    assert out["rows"] == [list(r) for r in expected.effects.rows]
    assert out["replicates"]["rows"] == [list(r) for r in expected.replicates.rows]
    assert [f["name"] for f in out["fields"]][:3] == ["intervention", "policy", "metric"]
    assert out["spec"]["n_skus"] == 30 and out["spec"]["seed"] == world.spec.seed
    assert out["synthesizer"] == "warehouse-spec" and out["elapsed_ms"] >= 0


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"interventions": ["nope"]}, "unknown intervention 'nope'"),
        ({"interventions": ["baseline"]}, "baseline is what every intervention is compared with"),
        ({"interventions": ["promo_spike", "promo_spike"]}, "each may appear once"),
        ({"interventions": ["promo_spike"], "outcomes": ["nope"]}, "unknown outcome"),
        ({"interventions": ["promo_spike"], "replicates": 1}, "greater than or equal to 2"),
        ({"interventions": ["promo_spike"], "confidence": 1}, "less than 1"),
        ({"interventions": ["promo_spike"], "extra": 1}, "Extra inputs are not permitted"),
    ],
)
def test_effects_refuse_an_invalid_request(small_client, body, message):
    res = small_client.post(V1 + "/effects", json=body)
    assert res.status_code == 422 and message in str(res.json()["detail"])


def test_effects_check_only_answers_the_budget_without_generating(small_client, monkeypatch):
    from sdf.simulation import effects

    monkeypatch.setattr(effects.EffectStudy, "run", lambda self: pytest.fail("check_only ran the study"))
    body = {"interventions": ["promo_spike", "supply_disruption"], "check_only": True}
    budget = small_client.post(V1 + "/effects", json=body).json()
    assert budget == {
        "work": effects.effect_work(10, 2, 1, 1, 30, 30),
        "max_work": effects.MAX_EFFECT_WORK,
        "within_budget": True,
        "size": "10 replicates × 3 arms × 1 policy × 1 outcome × 30 SKUs × 30 days",
    }
    bad = small_client.post(V1 + "/effects", json={"interventions": ["baseline"], "check_only": True})
    assert bad.status_code == 422  # the same refusal as a real run


def test_effects_over_budget_agree_between_check_only_and_a_run():
    c = TestClient(create_app())
    assert post_world(c, n_skus=500, horizon_days=180).status_code == 200
    body = {"interventions": ["promo_spike", "supply_disruption"], "replicates": 20}
    budget = c.post(V1 + "/effects", json={**body, "check_only": True}).json()
    assert budget["within_budget"] is False and budget["work"] > budget["max_work"]
    res = c.post(V1 + "/effects", json=body)
    assert res.status_code == 422 and "exceeds MAX_EFFECT_WORK" in res.json()["detail"]


def test_the_experiment_catalog_publishes_the_replicate_bound(client):
    assert get(client, "/experiments/catalog")["effects"] == {"max_replicates": 20}


def test_effects_study_a_runtime_generator_through_the_worlds_own_registry():
    from sdf.simulation.world_test import MyWarehouseGenerator
    from sdf.synthesis.registry import default_registry

    synthesizers = default_registry()
    synthesizers.register(MyWarehouseGenerator)
    c = TestClient(create_app(synthesizers=synthesizers))
    assert post_world(c, synthesizer="my-warehouse", n_skus=30, horizon_days=30).status_code == 200
    res = c.post(V1 + "/effects", json={"interventions": ["promo_spike"], "replicates": 2})
    assert res.status_code == 200, res.text
    assert res.json()["synthesizer"] == "my-warehouse"


def test_effects_refuse_a_generator_whose_first_world_differs_from_its_later_ones():
    from typing import ClassVar

    from sdf.synthesis.api import SynthesizerInfo
    from sdf.synthesis.registry import default_registry
    from sdf.synthesis.warehouse import WarehouseGenerator, WarehouseSpecSynthesizer

    class FirstDiffers(WarehouseSpecSynthesizer):
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("first-differs", "warehouse", False, "stateful")
        calls: ClassVar[list] = []

        def sample(self, n=None, *, seed=None):
            FirstDiffers.calls.append(1)
            wh = WarehouseGenerator(self.spec).generate()
            if len(FirstDiffers.calls) == 1:
                wh.skus[0].name += " (first call)"  # only an unmeasured field differs
            return wh

    synthesizers = default_registry()
    synthesizers.register(FirstDiffers)
    c = TestClient(create_app(synthesizers=synthesizers))
    assert post_world(c, synthesizer="first-differs", n_skus=30, horizon_days=30).status_code == 200
    res = c.post(V1 + "/effects", json={"interventions": ["promo_spike"], "replicates": 2})
    assert res.status_code == 422 and "not deterministic in its spec" in res.json()["detail"]


# -- datasets (docs/refactor/explore/interfaces.md §1–2) ---------------------------------------


def test_datasets_are_listed_with_their_fields(client):
    body = get(client, "/datasets")
    assert [d["name"] for d in body["datasets"]] == ["inventory", "order-lines", "replenishment-plan", "skus"]
    assert body["unavailable"] == {}
    lines = next(d for d in body["datasets"] if d["name"] == "order-lines")
    assert lines["origin"] == "builtin" and lines["label"] == "Outbound order lines"
    assert lines["fields"][0] == {
        "name": "date",
        "label": "Order date",
        "kind": "time",
        "unit": None,
        "aggregate": None,
    }
    assert lines["fields"][-1]["unit"] == "currency" and lines["fields"][-1]["aggregate"] == "sum"


def test_a_dataset_is_served_as_rows_in_field_order(client):
    body = get(client, "/datasets/order-lines")
    assert body["world"] == "GenerationSpec(seed=42)"
    assert (body["total_rows"], body["truncated"], len(body["rows"])) == (28897, False, 28897)
    assert len(body["rows"][0]) == len(body["fields"]) and body["rows"][0][0] == "2025-01-01"
    few = get(client, "/datasets/order-lines?limit=100")
    assert (len(few["rows"]), few["total_rows"], few["truncated"]) == (100, 28897, True)
    assert few["rows"] == body["rows"][:100]


def test_an_unknown_dataset_or_a_bad_limit_is_rejected(client):
    res = client.get(V1 + "/datasets/nope")
    assert res.status_code == 404 and "unknown dataset 'nope'" in res.json()["detail"]
    assert client.get(V1 + "/datasets/skus?limit=0").status_code == 422


def test_the_app_serves_a_provider_registered_on_its_catalogue():
    from sdf.application.datasets import default_datasets
    from sdf.application.datasets_test import ChannelMix

    datasets = default_datasets()
    app = create_app(datasets=datasets)
    assert app.state.datasets is datasets
    datasets.register(ChannelMix)  # after the app was built: later requests still see it
    c = TestClient(app)
    assert "channel-mix" in [d["name"] for d in get(c, "/datasets")["datasets"]]
    rows = get(c, "/datasets/channel-mix")["rows"]
    assert [r[0] for r in rows] == ["ecommerce", "store", "wholesale"]


def test_a_failing_provider_is_a_500_that_names_it_not_an_unknown_dataset():
    from typing import ClassVar

    from sdf.application.datasets import DatasetCatalog
    from sdf.foundation.tables import DatasetInfo, Field

    class Broken:
        info: ClassVar[DatasetInfo] = DatasetInfo("broken", "Broken", "x", (Field("n", "N", "measure"),))

        def rows(self, world):
            return [{}["missing"]]

    datasets = DatasetCatalog()
    datasets.register(Broken)
    res = TestClient(create_app(datasets=datasets), raise_server_exceptions=False).get(V1 + "/datasets/broken")
    assert res.status_code == 500 and res.json()["detail"] == "dataset broken could not be built: 'missing'"


def test_the_row_limit_applies_while_a_provider_is_read():
    from sdf.application.datasets import DatasetCatalog
    from sdf.application.datasets_test import Counter

    datasets = DatasetCatalog()
    datasets.register(Counter)  # its last row is invalid: a capped response never stores or checks it
    body = get(TestClient(create_app(datasets=datasets)), "/datasets/counter?limit=5")
    assert (body["rows"], body["total_rows"], body["truncated"]) == ([[0], [1], [2], [3], [4]], 100_000, True)


def test_the_experiment_catalogue_lists_names_and_parameter_bounds(client):
    body = get(client, "/experiments/catalog")
    assert body["interventions"][0] == "baseline" and "promo_spike" in body["interventions"]
    assert body["outcomes"] == ["replenishment_need", "active_stockouts", "simulated_cost"]
    assert body["max_per_list"] == 6
    kinds = {p["kind"]: p["params"] for p in body["policies"]}
    assert [p["name"] for p in kinds["naive"]] == ["lead_time_days", "review_days"]
    assert kinds["service-level"][0] == {
        "name": "service_level",
        "type": "float",
        "default": 0.95,
        "min": 0.5,
        "max": 1.0,
        "exclusive": True,
        "nullable": False,
    }
    assert kinds["naive"][0] == {
        "name": "lead_time_days",
        "type": "int",
        "default": 7,
        "min": 1,
        "max": 90,
        "exclusive": False,
        "nullable": False,
    }


@pytest.mark.parametrize(
    ("policy", "status"),
    [
        ({"kind": "service-level", "service_level": 1.0}, 422),  # exclusive bound
        ({"kind": "service-level", "service_level": 0.99}, 200),
        ({"kind": "naive", "lead_time_days": 90}, 200),  # inclusive bound
        ({"kind": "naive", "lead_time_days": 91}, 422),
    ],
)
def test_the_catalogue_bounds_are_the_ones_the_experiment_endpoint_enforces(client, policy, status):
    body = {"interventions": ["baseline"], "policies": [policy], "outcomes": ["replenishment_need"]}
    assert client.post(V1 + "/experiments", json=body).status_code == status


def test_the_experiment_result_carries_its_fields(client):
    body = {"interventions": ["baseline"], "policies": [{"kind": "naive"}], "outcomes": ["replenishment_need"]}
    res = client.post(V1 + "/experiments", json=body).json()
    assert [f["name"] for f in res["fields"]] == ["intervention", "policy", "metric", "value"]
    assert res["fields"][-1]["kind"] == "measure" and res["fields"][-1]["aggregate"] == "mean"
    assert set(res["rows"][0]) == {"intervention", "policy", "metric", "value"}  # rows stay objects


# -- synthesizers and runs ----------------------------------------------------------------------


def run(client, **body):
    return client.post(V1 + "/synthesis/runs", json=body)


def test_the_synthesizer_catalogue_lists_parameters_and_unavailable_ones(client):
    body = get(client, "/synthesizers")
    by_name = {e["name"]: e for e in body["synthesizers"]}
    assert {"bootstrap-table", "seasonal-profile", "warehouse-spec"} <= set(by_name)
    assert by_name["bootstrap-table"]["params"] == [
        {"name": "seed", "type": "int", "default": 7, "min": None, "max": None, "exclusive": False, "nullable": False},
        {
            "name": "jitter",
            "type": "float",
            "default": 0.05,
            "min": 0.0,
            "max": 1.0,
            "exclusive": False,
            "nullable": False,
        },
    ]
    assert by_name["warehouse-spec"]["params"] == [] and by_name["warehouse-spec"]["produces"] == "warehouse"
    assert by_name["seasonal-profile"]["origin"] == "builtin" and by_name["seasonal-profile"]["requires"] == []
    assert isinstance(body["unavailable"], dict)


def test_the_sources_are_ids_and_file_names(client, monkeypatch, tmp_path):
    assert get(client, "/synthesis/sources")["sources"] == [
        {"id": "sample", "label": "sample_online_retail_ii.csv"},
        {"id": "retail-10k", "label": "online_retail_ii_2010_10k.csv"},
    ]
    monkeypatch.setenv("SDF_DATA_DIR", str(tmp_path))
    assert get(client, "/synthesis/sources")["sources"] == []


def test_a_series_run_returns_its_params_scores_and_table(client):
    res = run(client, synthesizer="seasonal-profile", source="sample", params={"seed": 7})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["kind"], body["params"], body["repeatable"]) == ("series", {"seed": 7}, True)
    assert {"ks_statistic", "profile_corr", "mean_delta_pct", "std_delta_pct", "fidelity_score"} <= set(body["metrics"])
    assert [f["name"] for f in body["fields"]] == ["step", "origin", "value"]
    assert {r[1] for r in body["rows"]} == {"real", "synthetic"}


def test_a_table_run_leaving_the_seed_out_is_repeatable(client):
    first = run(client, synthesizer="bootstrap-table", source="sample").json()
    assert first["params"] == {"seed": 7, "jitter": 0.05} and first["repeatable"]
    assert first["metrics"]["verdict"] and first["fields"][0]["name"] == "origin"
    again = run(client, synthesizer="bootstrap-table", source="sample", params=first["params"]).json()
    assert again["rows"] == first["rows"]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"synthesizer": "nope", "source": "sample"}, "unknown synthesizer 'nope'"),
        ({"synthesizer": "seasonal-profile", "source": "sample", "params": {"jitter": 1}}, "takes no parameter"),
        ({"synthesizer": "seasonal-profile", "source": "sample", "params": {"seed": "7"}}, "seed must be a number"),
        (
            {"synthesizer": "bootstrap-table", "source": "sample", "params": {"jitter": 5}},
            "jitter must be from 0.0 to 1.0",
        ),
        ({"synthesizer": "seasonal-profile", "source": "elsewhere"}, "unknown source 'elsewhere'"),
        (
            {"synthesizer": "seasonal-profile", "source": "data/sample_online_retail_ii.csv"},
            "unknown source",
        ),  # never a path
        ({"synthesizer": "warehouse-spec", "source": "sample"}, "produces a warehouse"),
    ],
)
def test_a_run_that_cannot_happen_is_a_422_with_the_reason(client, body, message):
    res = run(client, **body)
    assert res.status_code == 422 and message in res.json()["detail"], res.text


def test_an_unavailable_synthesizer_is_a_422_that_says_why(monkeypatch):
    from importlib.metadata import EntryPoint

    from sdf.synthesis import registry as registry_module
    from sdf.synthesis.registry import default_registry

    real_entry_points = registry_module.entry_points
    extra = EntryPoint(
        name="needs-absent-child", value="sdf.synthesis.registry_test:NeedsAbsentChild", group="sdf.synthesizers"
    )
    monkeypatch.setattr(registry_module, "entry_points", lambda group: [*real_entry_points(group=group), extra])
    c = TestClient(create_app(synthesizers=default_registry()))
    assert "needs-absent-child" in get(c, "/synthesizers")["unavailable"]
    res = run(c, synthesizer="needs-absent-child", source="sample")
    assert res.status_code == 422 and "needs no_such_parent_pkg.backend" in res.json()["detail"]


def test_the_world_reports_and_keeps_its_generator():
    from sdf.simulation.world_test import MyWarehouseGenerator
    from sdf.synthesis.registry import default_registry

    synthesizers = default_registry()
    synthesizers.register(MyWarehouseGenerator)
    app = create_app(synthesizers=synthesizers)
    assert app.state.synthesizers is synthesizers
    c = TestClient(app)
    assert get(c, "/world")["synthesizer"] == "warehouse-spec"
    assert "my-warehouse" in [e["name"] for e in get(c, "/synthesizers")["synthesizers"]]

    MyWarehouseGenerator.built.clear()
    res = post_world(c, synthesizer="my-warehouse", n_skus=30, horizon_days=20)
    assert res.status_code == 200 and res.json()["synthesizer"] == "my-warehouse"
    assert get(c, "/world")["synthesizer"] == "my-warehouse" and len(MyWarehouseGenerator.built) == 1
    assert post_world(c, n_skus=30, horizon_days=21).json()["synthesizer"] == "my-warehouse"  # left out: kept

    MyWarehouseGenerator.built.clear()
    scenarios = get(c, "/scenarios")["scenarios"]
    assert len(MyWarehouseGenerator.built) == len(scenarios) - 1  # every scenario but the baseline, with my-warehouse
    MyWarehouseGenerator.built.clear()
    body = {"interventions": ["promo_spike"], "policies": [{"kind": "naive"}], "outcomes": ["replenishment_need"]}
    assert c.post(V1 + "/experiments", json=body).status_code == 200
    assert len(MyWarehouseGenerator.built) == 1


@pytest.mark.parametrize(
    ("name", "message"), [("seasonal-profile", "produces a series, not a warehouse"), ("nope", "unknown synthesizer")]
)
def test_the_world_refuses_a_generator_that_is_not_a_warehouse(client, name, message):
    res = post_world(client, synthesizer=name)
    assert res.status_code == 422 and message in res.json()["detail"]


def test_a_generator_that_returns_something_else_is_a_422_and_the_world_is_kept():
    from typing import ClassVar

    from sdf.synthesis.api import SynthesizerInfo
    from sdf.synthesis.registry import default_registry

    class NotAWarehouse:
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("not-a-warehouse", "warehouse", False, "claims a warehouse")

        def __init__(self, *, spec=None) -> None:
            self.spec = spec

        def fit(self, data=None):
            return self

        def sample(self, n=None, *, seed=None):
            return []

    synthesizers = default_registry()
    synthesizers.register(NotAWarehouse)
    c = TestClient(create_app(synthesizers=synthesizers))
    before = get(c, "/world")
    res = post_world(c, synthesizer="not-a-warehouse", n_skus=30)
    assert res.status_code == 422 and "returned list, not a SyntheticWarehouse" in res.json()["detail"]
    assert get(c, "/world") == before


def test_a_synthesizer_that_fails_is_a_500_that_names_it():
    from sdf.synthesis.registry import default_registry
    from sdf.validation.evaluation_test import Broken

    synthesizers = default_registry()
    synthesizers.register(Broken)
    c = TestClient(create_app(synthesizers=synthesizers), raise_server_exceptions=False)
    res = run(c, synthesizer="broken-sample", source="sample")
    assert res.status_code == 500 and "broken-sample failed while fitting and sampling it" in res.json()["detail"]
