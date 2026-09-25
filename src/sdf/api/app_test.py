"""HTTP contract tests for ``/api/v1``: every field the UI reads, the world limits, snapshot consistency,
the experiment endpoint, the UI boundary and CORS.

Needs the ``api`` extra (FastAPI) and the dev dependency ``httpx2``; skipped otherwise.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import ClassVar

import pytest

from sdf.foundation.tables import DatasetInfo, Field
from sdf.synthesis.spec import GenerationSpec

pytest.importorskip("fastapi")
pytest.importorskip("httpx2")  # the transport starlette.testclient uses

from fastapi.testclient import TestClient  # noqa: E402

from .app import create_app  # noqa: E402
from .state import GenerateLimits  # noqa: E402

V1 = "/api/v1"
ROOT = Path(__file__).resolve().parents[3]
UI_DIR = ROOT / "ui"
UI_SRC = UI_DIR / "src"
UI_DIST = UI_DIR / "dist"  # built by `npm run build` in ui/; CI builds it before the tests


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
    """Every script and component under ui/src (the tests aside), by path relative to ui/src."""
    return {
        p.relative_to(UI_SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(UI_SRC.rglob("*"))
        if p.suffix in (".js", ".svelte") and not p.name.endswith(".test.js")
    }


def ui_paths() -> set[str]:
    """Every path a ui/src script passes to api(), without its query string; ``${…}`` reads as ``{}``."""
    paths = set()
    for js in ui_scripts().values():
        for m in re.findall(r"""api\(\s*["'`](/[^"'`]*)""", js):
            paths.add(re.sub(r"\$\{[^}]*\}", "{}", m.split("?")[0]))
    return paths


PAGES = ("index.html", "explore.html", "synthesizers.html", "effects.html")


def test_every_ui_path_is_in_the_openapi_schema(client):
    schema_paths = {re.sub(r"\{[^}]*\}", "{}", p.removeprefix(V1)) for p in get(client, "/openapi.json")["paths"]}
    used = ui_paths()
    assert len(used) >= 19, used
    assert {"/datasets", "/datasets/{}", "/experiments/catalog", "/experiments"} <= used
    assert {"/synthesizers", "/synthesis/sources", "/synthesis/runs", "/world"} <= used
    assert {"/effects", "/estimators", "/causal/estimates"} <= used
    assert used <= schema_paths, used - schema_paths
    assert "/export?entity=" in ui_scripts()["pages/dashboard/Controls.svelte"]
    assert "/export" in schema_paths  # the export links are built from API + "/export"


def test_ui_reaches_the_backend_only_through_api():
    scripts = ui_scripts()
    assert sum(js.count("fetch(") for js in scripts.values()) == 1  # the one inside api(), in lib/api.js
    assert "fetch(" in scripts["lib/api.js"]
    assert 'export const API = globalThis.SDF_API_BASE ?? "/api/v1";' in scripts["lib/api.js"]


def test_ui_has_no_inline_event_handler():
    """The pages are ES modules, whose functions are not globals: every handler is registered in a script."""
    shipped = [
        p for p in sorted(UI_SRC.rglob("*.js")) if not p.name.endswith(".test.js")
    ]  # tests hold hostile input on purpose
    for path in sorted(UI_DIR.glob("*.html")) + shipped:
        text = path.read_text(encoding="utf-8")
        assert not re.findall(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", text), path.name
    nav = (UI_SRC / "components" / "Nav.svelte").read_text(encoding="utf-8")
    for page in PAGES:
        html = (UI_DIR / page).read_text(encoding="utf-8")
        assert re.search(r'<script type="module" src="src/pages/[a-z]+\.js">', html), page
        assert '<div id="app"></div>' in html, page  # every page mounts its component, under Nav.svelte
    for link in PAGES:
        assert f'"{link}"' in nav, link


def test_ui_writes_no_html_from_data():
    """Svelte, Chart.js and Tabulator write every label as text; no page builds markup itself."""
    for name, js in ui_scripts().items():
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "{@html"):
            assert sink not in js, (name, sink)


def built_ui() -> Path:
    """The built UI; its tests skip, saying why, when it was not built."""
    if not (UI_DIST / "index.html").is_file():
        pytest.skip("ui/dist is not built: run `npm ci && npm run build` in ui/")
    return UI_DIST


def test_built_ui_has_no_inline_script_or_handler():
    for path in sorted(built_ui().glob("*.html")):
        html = path.read_text(encoding="utf-8")
        assert not re.findall(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", html), path.name
        for attrs in re.findall(r"<script\b([^>]*)>", html):
            assert "src=" in attrs, (path.name, attrs)  # every script is a file, none inline


def test_the_python_package_contains_no_html():
    package = Path(__file__).resolve().parents[1]
    assert not list(package.rglob("*.html"))


def test_openapi_describes_the_fields(client):
    schemas = get(client, "/openapi.json")["components"]["schemas"]
    assert {"sku_id", "order_qty", "reorder_point_s"} <= set(schemas["ReplenishmentRow"]["properties"])
    assert {"n_skus", "horizon_days"} <= set(schemas["WorldRequest"]["properties"])
    assert {"interventions", "policies", "outcomes"} <= set(schemas["ExperimentRequest"]["properties"])
    assert {"proposed_action", "status", "sku_id", "quantity"} <= set(schemas["ProposedAction"]["properties"])


def test_built_ui_is_mounted_for_hosting():
    client = TestClient(create_app(ui_dir=built_ui()))
    page = client.get("/")
    assert page.status_code == 200 and re.search(
        r'<script type="module" crossorigin src="\./assets/index-[^"]+\.js">', page.text
    )
    for url in ("/", *(f"/{page}" for page in PAGES[1:])):
        html = client.get(url).text
        for asset in re.findall(r'(?:href|src)="(?:\./)?([^":#]+)"', html):  # every local file the page loads or links
            assert client.get("/" + asset).status_code == 200, (url, asset)
        for js in re.findall(r'src="\./(assets/[^"]+\.js)"', html):  # and every chunk those scripts import
            for chunk in re.findall(r'from\s*"\./([^"]+\.js)"', client.get("/" + js).text):
                assert client.get("/assets/" + chunk).status_code == 200, (js, chunk)
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

    from sdf.foundation import plugins as plugins_module
    from sdf.synthesis.registry import default_registry

    real_entry_points = plugins_module.entry_points
    extra = EntryPoint(
        name="needs-absent-child", value="sdf.synthesis.registry_test:NeedsAbsentChild", group="sdf.synthesizers"
    )
    monkeypatch.setattr(plugins_module, "entry_points", lambda group: [*real_entry_points(group=group), extra])
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


# -- causal estimates -------------------------------------------------------------------------------

BUILT_INS = ["difference-in-means", "regression-adjustment", "ipw"]
EXPRESS = {"treatment": "priority", "treated_value": "express", "outcome": "line_value", "covariates": ["category"]}


def estimates(client, **body):
    return client.post(V1 + "/causal/estimates", json=body)


def test_the_estimator_catalogue_publishes_limits_and_the_benchmark(client):
    from sdf.simulation.benchmark import QUESTION, PromotionBenchmark

    body = get(client, "/estimators")
    names = [e["name"] for e in body["estimators"]]
    assert set(BUILT_INS) <= set(names)
    for name in ("dowhy-backdoor", "econml-dml"):
        assert name in names or body["unavailable"][name].startswith("needs ")
    naive = next(e for e in body["estimators"] if e["name"] == "difference-in-means")
    assert naive["origin"] == "builtin" and naive["uses_covariates"] is False
    assert body["limits"] == {"max_rows": 40_000, "max_estimators": 6, "max_seconds": 30}
    assert body["benchmark"]["params"] == [p.to_dict() for p in PromotionBenchmark.params()]
    assert body["benchmark"]["question"] == QUESTION.to_dict()


def test_the_benchmark_s_scores_equal_score_on_the_same_draw(client):
    from sdf.analytics.causal import default_estimators, score
    from sdf.simulation.benchmark import PromotionBenchmark
    from sdf.simulation.world import World

    res = estimates(client, estimators=BUILT_INS, benchmark={"confounding": 1.0}, confidence=0.9)
    assert res.status_code == 200, res.text
    body = res.json()
    draw = PromotionBenchmark(confounding=1.0).draw(
        World.generate(GenerationSpec())
    )  # the app's first world, as the CLI's
    expected = score(
        draw.table, draw.question, default_estimators(), names=BUILT_INS, true_effect=draw.true_effect, confidence=0.9
    )
    assert [r[:10] + r[11:] for r in body["rows"]] == [list(r[:10] + r[11:]) for r in expected.rows]  # all but seconds
    assert body["true_effect"] == draw.true_effect and body["source"] == "promotion-benchmark"
    assert [f["name"] for f in body["fields"]][:2] == ["estimator", "effect"]
    assert body["data"]["rows"] == [list(r) for r in draw.table.rows]  # the observed table, for Explore
    assert body["question"]["covariates"] == ["log_demand", "abc_class", "log_price"]


def test_a_dataset_question_has_no_truth(client):
    res = estimates(client, estimators=["regression-adjustment"], dataset="order-lines", question=EXPRESS)
    assert res.status_code == 200, res.text
    body = res.json()
    (row,) = body["rows"]
    assert row[0] == "regression-adjustment" and row[1] is not None
    assert row[4:8] == [None, None, None, None]  # true_effect, bias, relative_bias, covers
    assert body["true_effect"] is None and body["data"] is None and body["source"] == "order-lines"


def test_the_benchmark_question_may_only_drop_covariates(client):
    q = {"treatment": "promoted", "outcome": "weekly_units", "covariates": ["abc_class"]}
    res = estimates(client, estimators=["regression-adjustment"], benchmark={}, question=q)
    assert res.status_code == 200 and res.json()["question"]["covariates"] == ["abc_class"]
    other = estimates(client, estimators=["ipw"], benchmark={}, question={**q, "outcome": "log_price"})
    assert other.status_code == 422 and "only its covariates may be dropped" in other.json()["detail"]
    extra = estimates(client, estimators=["ipw"], benchmark={}, question={**q, "covariates": ["sku_id"]})
    assert extra.status_code == 422 and "sku_id is not one of them" in extra.json()["detail"]


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"estimators": ["nope"], "benchmark": {}}, "unknown estimator 'nope'"),
        ({"estimators": ["ipw"]}, "give exactly one of benchmark and dataset"),
        ({"estimators": ["ipw"], "benchmark": {}, "dataset": "skus"}, "give exactly one of benchmark and dataset"),
        (
            {"estimators": ["ipw"], "benchmark": {"confounding": 9}},
            "benchmark: confounding must be from 0.0 to 3.0, got 9",
        ),
        ({"estimators": ["ipw"], "benchmark": {}, "confidence": 1}, "confidence must be above 0.5 and below 1, got 1"),
        ({"estimators": ["ipw"], "dataset": "nope", "question": EXPRESS}, "unknown dataset 'nope'"),
        ({"estimators": ["ipw"], "dataset": "order-lines"}, "a question is needed for dataset order-lines"),
        (
            {"estimators": ["ipw"], "dataset": "order-lines", "question": {**EXPRESS, "treated_value": 1}},
            "priority has values ['express', 'standard']; set treated_value to one of them",
        ),
        (
            {"estimators": ["ipw"], "dataset": "order-lines", "question": {**EXPRESS, "outcome": "nope"}},
            "unknown field 'nope'",
        ),
    ],
)
def test_an_invalid_estimation_request_is_a_422_that_says_why(client, body, detail):
    res = estimates(client, **body)
    assert res.status_code == 422 and detail in res.json()["detail"], res.text


def test_the_request_shape_is_checked(client):
    assert estimates(client, estimators=[], benchmark={}).status_code == 422
    assert estimates(client, estimators=["ipw"] * 7, benchmark={}).status_code == 422  # at most 6
    assert estimates(client, estimators=["ipw"], benchmark={"nope": 1}).status_code == 422  # extra keys are refused


def test_a_failing_estimator_is_a_row_in_a_200():
    from sdf.analytics.causal import default_estimators
    from sdf.analytics.causal.causal_test import Raises

    reg = default_estimators()
    reg.register(Raises)
    res = estimates(
        TestClient(create_app(estimators=reg)), estimators=["raises", "regression-adjustment"], benchmark={}
    )
    assert res.status_code == 200
    failed, ok = res.json()["rows"]
    assert failed[0] == "raises" and failed[1] is None and failed[11] == "RuntimeError: library error"
    assert ok[1] is not None


def test_rows_that_cannot_be_built_are_a_500_that_names_the_source(monkeypatch):
    from sdf.application.datasets import DatasetCatalog
    from sdf.simulation.benchmark import PromotionBenchmark

    datasets = DatasetCatalog()
    datasets.register(FailsMidway)
    c = TestClient(create_app(datasets=datasets), raise_server_exceptions=False)
    q = {"treatment": "t", "outcome": "y"}
    res = estimates(c, estimators=["ipw"], dataset="fails-midway", question=q)
    assert res.status_code == 500 and res.json()["detail"] == "dataset fails-midway could not be built: provider broke"
    monkeypatch.setattr(PromotionBenchmark, "draw", lambda self, world: (_ for _ in ()).throw(RuntimeError("no SKUs")))
    res = estimates(c, estimators=["ipw"], benchmark={})
    assert res.status_code == 500 and res.json()["detail"] == "the benchmark draw failed: no SKUs"


# The providers below are module level, so a catalogue can mount them.
TY_INFO = DatasetInfo(
    "ty-rows", "T and Y", "a treatment and an outcome", (Field("t", "T", "measure"), Field("y", "Y", "measure"))
)


class FailsMidway:
    info: ClassVar[DatasetInfo] = DatasetInfo("fails-midway", "Fails", "x", TY_INFO.fields)

    def rows(self, world):
        yield (1, 1.0)
        raise RuntimeError("provider broke")


class Endless:
    info: ClassVar[DatasetInfo] = DatasetInfo("endless", "Endless", "x", TY_INFO.fields)
    served: ClassVar[list[int]] = []

    def rows(self, world):
        i = 0
        while True:
            Endless.served.append(i)
            yield (i % 2, float(i))
            i += 1


class SlowRows:
    info: ClassVar[DatasetInfo] = DatasetInfo("slow-rows", "Slow", "x", TY_INFO.fields)

    def rows(self, world):
        for i in range(1000):
            time.sleep(0.05)
            yield (i % 2, float(i))


def test_the_row_limit_reads_one_probe_row_and_nothing_further(monkeypatch):
    from sdf.api import app as app_module
    from sdf.application.datasets import DatasetCatalog

    monkeypatch.setattr(app_module, "MAX_ESTIMATE_ROWS", 5)
    datasets = DatasetCatalog()
    datasets.register(Endless)
    Endless.served.clear()
    res = estimates(
        TestClient(create_app(datasets=datasets)),
        estimators=["ipw"],
        dataset="endless",
        question={"treatment": "t", "outcome": "y"},
    )
    assert res.status_code == 422 and res.json()["detail"] == "dataset endless has more than MAX_ESTIMATE_ROWS (5) rows"
    assert Endless.served == [0, 1, 2, 3, 4, 5]  # five kept, one probe


def test_a_provider_that_does_not_deliver_in_time_is_stopped(monkeypatch):
    from sdf.api import app as app_module
    from sdf.application.datasets import DatasetCatalog

    monkeypatch.setattr(app_module, "MAX_ESTIMATE_SECONDS", 0.3)
    datasets = DatasetCatalog()
    datasets.register(SlowRows)
    started = time.monotonic()
    res = estimates(
        TestClient(create_app(datasets=datasets)),
        estimators=["ipw"],
        dataset="slow-rows",
        question={"treatment": "t", "outcome": "y"},
    )
    assert res.status_code == 422 and res.json()["detail"] == "dataset slow-rows did not deliver its rows within 0.3 s"
    assert time.monotonic() - started < 2  # stopped at the next row, not after all of them


class EagerAndSlow:
    """Builds its whole list before returning it, taking longer than the budget."""

    info: ClassVar[DatasetInfo] = DatasetInfo("eager-and-slow", "Eager", "x", TY_INFO.fields)

    def rows(self, world):
        time.sleep(0.5)
        return [(i % 2, float(i)) for i in range(10)]


class SlowToFinish:
    """Yields its rows at once, then takes longer than the budget before it ends."""

    info: ClassVar[DatasetInfo] = DatasetInfo("slow-to-finish", "Slow to finish", "x", TY_INFO.fields)

    def rows(self, world):
        yield from [(i % 2, float(i)) for i in range(10)]
        time.sleep(0.5)


class OwnTimeout:
    """Fails with a TimeoutError of its own: a provider failure, not the request's deadline."""

    info: ClassVar[DatasetInfo] = DatasetInfo("own-timeout", "Own timeout", "x", TY_INFO.fields)

    def rows(self, world):
        raise TimeoutError("upstream database timed out")


def test_an_eager_provider_past_the_deadline_is_stopped_and_its_own_timeout_is_a_500(monkeypatch):
    from sdf.api import app as app_module
    from sdf.application.datasets import DatasetCatalog

    monkeypatch.setattr(app_module, "MAX_ESTIMATE_SECONDS", 0.3)
    datasets = DatasetCatalog()
    datasets.register(EagerAndSlow)
    datasets.register(SlowToFinish)
    datasets.register(OwnTimeout)
    c = TestClient(create_app(datasets=datasets), raise_server_exceptions=False)
    q = {"treatment": "t", "outcome": "y"}
    res = estimates(c, estimators=["ipw"], dataset="eager-and-slow", question=q)
    assert (
        res.status_code == 422
        and res.json()["detail"] == "dataset eager-and-slow did not deliver its rows within 0.3 s"
    )
    res = estimates(c, estimators=["ipw"], dataset="slow-to-finish", question=q)
    assert res.status_code == 422 and "slow-to-finish did not deliver its rows within 0.3 s" in res.json()["detail"]
    # a confidence out of range, or a question that names the wrong fields, is refused before any row is read
    bad = estimates(c, estimators=["ipw"], dataset="eager-and-slow", question=q, confidence=1.5)
    assert bad.status_code == 422 and bad.json()["detail"] == "confidence must be above 0.5 and below 1, got 1.5"
    wrong = estimates(c, estimators=["ipw"], dataset="eager-and-slow", question={"treatment": "t", "outcome": "nope"})
    assert wrong.status_code == 422 and wrong.json()["detail"].startswith("unknown field 'nope'")
    res = estimates(c, estimators=["ipw"], dataset="own-timeout", question=q)
    assert (
        res.status_code == 500
        and res.json()["detail"] == "dataset own-timeout could not be built: upstream database timed out"
    )


class RegeneratesMidway:
    """While the estimation reads it, the app's world is replaced; the rows stay the first world's."""

    info: ClassVar[DatasetInfo] = DatasetInfo(
        "regenerates", "Regenerates", "x", (*TY_INFO.fields, Field("world", "World", "dimension"))
    )
    store: ClassVar[object] = None

    def rows(self, world):
        for i in range(8):
            if i == 4:
                RegeneratesMidway.store.regenerate(GenerationSpec(n_skus=30, horizon_days=30, seed=99))
            yield (i % 2, float(i), world.label)


def test_one_world_serves_the_whole_estimation():
    from sdf.application.datasets import DatasetCatalog

    datasets = DatasetCatalog()
    datasets.register(RegeneratesMidway)
    app = create_app(datasets=datasets)
    RegeneratesMidway.store = app.state.store
    first = app.state.store.current.world.label
    res = estimates(
        TestClient(app),
        estimators=["difference-in-means"],
        dataset="regenerates",
        question={"treatment": "t", "outcome": "y"},
    )
    assert res.status_code == 200 and res.json()["world"] == first
    assert app.state.store.current.world.label != first  # the store moved on; this answer did not


class AtTheLimit:
    """MAX_ESTIMATE_ROWS rows with a dimension treatment and three covariates."""

    info: ClassVar[DatasetInfo] = DatasetInfo(
        "at-the-limit",
        "At the limit",
        "x",
        (
            Field("priority", "Priority", "dimension"),
            Field("value", "Value", "measure"),
            Field("category", "Category", "dimension"),
            Field("a", "A", "measure"),
            Field("b", "B", "measure"),
        ),
    )

    def rows(self, world):
        import numpy as np

        from sdf.api.app import MAX_ESTIMATE_ROWS

        rng = np.random.default_rng(0)
        a, b = rng.normal(size=MAX_ESTIMATE_ROWS), rng.normal(size=MAX_ESTIMATE_ROWS)
        cats = rng.integers(0, 5, MAX_ESTIMATE_ROWS)
        express = rng.random(MAX_ESTIMATE_ROWS) < 1 / (1 + np.exp(-a))
        value = 10 + 2 * express + a + 0.5 * b + cats + rng.normal(size=MAX_ESTIMATE_ROWS)
        for i in range(MAX_ESTIMATE_ROWS):
            yield ("express" if express[i] else "standard", float(value[i]), f"c{cats[i]}", float(a[i]), float(b[i]))


def test_six_estimators_at_the_row_limit_finish_within_the_budget():
    from sdf.analytics.causal import EstimatorInfo, default_estimators
    from sdf.analytics.causal.builtin import DifferenceInMeans, RegressionAdjustment
    from sdf.application.datasets import DatasetCatalog

    reg = default_estimators()
    for name, base in (
        ("naive-2", DifferenceInMeans),
        ("adjusted-2", RegressionAdjustment),
        ("adjusted-3", RegressionAdjustment),
    ):
        reg.register(
            type(name, (base,), {"info": EstimatorInfo(name, "a copy", uses_covariates=base.info.uses_covariates)})
        )
    datasets = DatasetCatalog()
    datasets.register(AtTheLimit)
    q = {"treatment": "priority", "treated_value": "express", "outcome": "value", "covariates": ["category", "a", "b"]}
    names = [*BUILT_INS, "naive-2", "adjusted-2", "adjusted-3"]
    started = time.monotonic()
    res = estimates(
        TestClient(create_app(datasets=datasets, estimators=reg)), estimators=names, dataset="at-the-limit", question=q
    )
    elapsed = time.monotonic() - started
    assert res.status_code == 200, res.text
    rows = res.json()["rows"]
    assert all(r[1] is not None for r in rows), [r[11] for r in rows]
    assert rows[1][1] == pytest.approx(2, abs=0.1)  # regression adjustment recovers the planted effect
    assert elapsed < 30


# -- forecasting ------------------------------------------------------------------------------------

FORECASTERS = ["mean", "naive", "moving-average", "seasonal-naive", "seasonal-linear"]


def forecast(client, **body):
    return client.post(V1 + "/forecasts/backtest", json=body)


def test_the_forecaster_catalogue_publishes_parameters_limits_and_the_benchmark(client):
    from sdf.simulation.benchmark import DemandBenchmark

    body = get(client, "/forecasters")
    names = [e["name"] for e in body["forecasters"]]
    assert set(FORECASTERS) <= set(names)
    ma = next(e for e in body["forecasters"] if e["name"] == "moving-average")
    assert ma["origin"] == "builtin" and ma["global_model"] is False
    assert ma["params"] == [
        {"name": "window", "type": "int", "default": 7, "min": 1, "max": 365, "exclusive": False, "nullable": False}
    ]
    assert body["unavailable"] == {}
    assert body["limits"] == {
        "max_forecasters": 6,
        "max_horizon": 56,
        "max_origins": 12,
        "max_quantiles": 9,
        "max_skus": 400,
        "max_seconds": 30,
        "min_history": 28,
    }
    assert body["benchmark"]["params"] == [p.to_dict() for p in DemandBenchmark.params()]


def test_a_world_backtest_equals_the_backtest_on_the_same_demand(client):
    from sdf.analytics.forecasters import backtest

    res = forecast(client, forecasters=["seasonal-naive", "moving-average"], params={"moving-average": {"window": 28}})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "world" and body["world"] and body["skus"] == 200
    direct = backtest(
        ["seasonal-naive", "moving-average"],
        client.app.state.store.current.world.demand(),
        params={"moving-average": {"window": 28}},
    )
    assert [r[:10] for r in body["scores"]["rows"]] == [list(r[:10]) for r in direct.scores.rows]
    assert [f["name"] for f in body["scores"]["fields"]][:3] == ["forecaster", "wape", "relative_wape"]
    assert len(body["by_horizon"]["rows"]) == 2 * 14 and len(body["forecasts"]["rows"]) == 2 * 200 * 14
    assert body["origins"] == [d.isoformat() for d in direct.origins]


def test_the_benchmark_adds_the_true_distribution_row(client):
    res = forecast(client, forecasters=["mean"], source={"benchmark": {"n_skus": 20, "days": 120, "seed": 3}})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "demand-benchmark" and body["world"] is None and body["skus"] == 20
    names = [r[0] for r in body["scores"]["rows"]]
    assert names == ["mean", "true-distribution"]


@pytest.mark.parametrize(
    "body, detail",
    [
        ({"forecasters": ["nope"]}, "unknown forecaster 'nope'"),
        ({"forecasters": FORECASTERS + ["mean", "naive"]}, "at most 6 forecasters"),
        ({"forecasters": ["mean"], "horizon": 57}, "horizon must be a whole number from 1 to 56"),
        ({"forecasters": ["mean"], "quantiles": [0.9, 0.1]}, "sorted"),
        ({"forecasters": ["mean"], "params": {"mean": {"x": 1}}}, "takes no parameter"),
        ({"forecasters": ["mean"], "source": {}}, "exactly one of world and benchmark"),
        ({"forecasters": ["mean"], "source": {"benchmark": {"n_skus": 5}}}, "benchmark: n_skus must be from 10"),
        ({"forecasters": ["mean"], "horizon": 56, "origins": 12}, "the history has 90 days"),
    ],
)
def test_a_backtest_request_that_cannot_run_is_a_422(client, body, detail):
    res = forecast(client, **body)
    assert res.status_code == 422 and detail in res.json()["detail"], res.text


def test_a_constructor_that_refuses_its_configuration_is_a_422():
    from sdf.analytics.forecasters import ForecasterInfo, default_forecasters

    class Picky:
        info: ClassVar[ForecasterInfo] = ForecasterInfo("picky", "refuses a combination")

        def __init__(self, low: int = 1, high: int = 2):
            if low >= high:
                raise ValueError(f"low ({low}) must be below high ({high})")

        def fit(self, history):
            return self

        def forecast(self, history, *, horizon, quantiles):
            raise AssertionError("never reached")

    reg = default_forecasters()
    reg.register(Picky)
    c = TestClient(create_app(forecasters=reg))
    res = c.post(V1 + "/forecasts/backtest", json={"forecasters": ["picky"], "params": {"picky": {"low": 3}}})
    assert res.status_code == 422 and res.json()["detail"] == "low (3) must be below high (2)"


def test_a_failing_forecaster_is_a_row_in_a_200():

    from sdf.analytics.forecasters import ForecasterInfo, default_forecasters

    class Broken:
        info: ClassVar[ForecasterInfo] = ForecasterInfo("broken", "always fails")

        def fit(self, history):
            return self

        def forecast(self, history, *, horizon, quantiles):
            raise RuntimeError("no forecast today")

    reg = default_forecasters()
    reg.register(Broken)
    app = create_app(forecasters=reg)
    assert app.state.forecasters is reg
    c = TestClient(app)
    res = c.post(V1 + "/forecasts/backtest", json={"forecasters": ["broken", "mean"], "horizon": 7, "origins": 2})
    assert res.status_code == 200, res.text
    broken, mean = res.json()["scores"]["rows"]
    assert broken[-1] == "RuntimeError: no forecast today" and mean[-1] is None
