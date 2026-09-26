"""HTTP contract tests for the data sources (``/api/v1/sources``) and sources as datasets.

Needs the ``api`` extra (FastAPI) and the dev dependency ``httpx2``; skipped otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdf.foundation.sources import BUNDLED, SourceLimits, SourceStore

pytest.importorskip("fastapi")
pytest.importorskip("httpx2")  # the transport starlette.testclient uses

from fastapi.testclient import TestClient  # noqa: E402

from .app import create_app  # noqa: E402

V1 = "/api/v1"
DATA = Path(__file__).resolve().parents[3] / "data"
SALES = "OrderDate,Sku,Units,UnitPrice,Store Name\n" + "".join(
    f"2024-01-{1 + i % 28:02d} {8 + i % 9:02d}:00:00,SKU{i % 3},{i % 5 + 1},{1.5 + i % 4},=cmd|{i % 2}\n"
    for i in range(40)
)


@pytest.fixture
def store(tmp_path):
    bundled = {n: (DATA / b.file, b.schema) for n, b in BUNDLED.items()}
    return SourceStore(tmp_path / "sources", bundled=bundled, limits=SourceLimits(max_bytes=5_000, max_sources=2))


@pytest.fixture
def client(store):
    return TestClient(create_app(sources=store))


def upload(client, name: str, body: str = SALES):
    return client.post(
        f"{V1}/sources", params={"name": name}, content=body.encode(), headers={"content-type": "text/csv"}
    )


def test_bundled_sources_are_listed_with_the_limits(client):
    res = client.get(f"{V1}/sources").json()
    assert [s["name"] for s in res["sources"]] == ["sample", "retail-10k"]  # in their declared order
    assert res["limits"] == {"max_bytes": 5_000, "max_rows": 2_000_000, "max_columns": 64, "max_sources": 2}
    sample = res["sources"][0]
    assert sample["origin"] == "bundled" and sample["rows"] == 3428 and sample["demand"] and sample["ready"]
    assert sample["schema"]["roles"]["item"] == "StockCode"


def test_upload_infer_fix_and_remove(client):
    res = upload(client, "my-sales")
    assert res.status_code == 201, res.text
    entry = res.json()
    assert entry["origin"] == "user" and entry["rows"] == 40 and entry["ready"]
    assert entry["schema"]["roles"] == {
        "time": "OrderDate",
        "item": "Sku",
        "quantity": "Units",
        "price": "UnitPrice",
        "cost": None,
    }
    detail = client.get(f"{V1}/sources/my-sales").json()
    assert detail["preview"]["header"][0] == "OrderDate" and len(detail["preview"]["rows"]) == 40
    # change a kind through the schema: every row is checked again
    schema = entry["schema"]
    schema["columns"][2]["kind"] = "real"
    res = client.put(f"{V1}/sources/my-sales/schema", json=schema)
    assert res.status_code == 200, res.text
    assert res.json()["schema"]["columns"][2]["kind"] == "real"
    assert client.delete(f"{V1}/sources/my-sales").status_code == 204
    assert client.get(f"{V1}/sources/my-sales").status_code == 404


def test_refusals_carry_their_status(client):
    assert upload(client, "Bad Name").status_code == 422
    assert upload(client, "sample").status_code == 409  # a bundled name
    assert upload(client, "big", SALES * 10).status_code == 413  # over max_bytes
    assert upload(client, "empty", "").status_code == 422
    assert upload(client, "a").status_code == 201
    assert upload(client, "a").status_code == 409  # taken
    assert upload(client, "b").status_code == 201
    res = upload(client, "c")
    assert res.status_code == 409 and "holds 2 user sources" in res.json()["detail"]  # the store is full
    assert client.delete(f"{V1}/sources/sample").status_code == 409
    assert client.delete(f"{V1}/sources/nope").status_code == 404
    schema = client.get(f"{V1}/sources/a").json()["schema"]
    schema["roles"]["quantity"] = "OrderDate"
    res = client.put(f"{V1}/sources/a/schema", json=schema)
    assert res.status_code == 422 and "quantity column 'OrderDate' must be integer or real" in res.json()["detail"]
    schema["roles"]["quantity"] = "Units"
    schema["columns"][0]["formats"] = ["%d/%m/%Y"]  # the time role no longer reads
    res = client.put(f"{V1}/sources/a/schema", json=schema)
    assert res.status_code == 422 and "cannot be read as time" in res.json()["detail"]
    assert client.put(f"{V1}/sources/sample/schema", json=schema | {"name": "sample"}).status_code == 409


def test_an_upload_over_the_limit_without_a_length_is_refused(client, store):
    def chunks():
        for _ in range(20):
            yield SALES.encode()

    res = client.post(
        f"{V1}/sources", params={"name": "stream"}, content=chunks(), headers={"content-type": "text/csv"}
    )
    assert res.status_code == 413
    assert [p.name for p in store.root.iterdir()] == []  # nothing left behind


def test_a_source_is_a_dataset_and_an_estimation_dataset(client):
    upload(client, "my-sales")
    listed = {d["name"]: d for d in client.get(f"{V1}/datasets").json()["datasets"]}
    assert {"source-my-sales", "source-sample", "source-retail-10k", "order-lines"} <= set(listed)
    fields = [f["name"] for f in listed["source-my-sales"]["fields"]]
    assert fields == ["order_date", "order_date_hour", "sku", "units", "unit_price", "store_name"]
    assert listed["source-my-sales"]["origin"] == "source"
    table = client.get(f"{V1}/datasets/source-my-sales").json()
    assert table["total_rows"] == 40 and not table["truncated"] and not table["sampled"] and table["world"] == ""
    assert table["rows"][0] == ["2024-01-01", "08", "SKU0", 1, 1.5, "=cmd|0"]
    part = client.get(f"{V1}/datasets/source-my-sales", params={"limit": 5}).json()
    assert part["truncated"] and part["sampled"] and len(part["rows"]) == 5
    res = client.post(
        f"{V1}/causal/estimates",
        json={
            "dataset": "source-my-sales",
            "estimators": ["difference-in-means"],
            "question": {"treatment": "store_name", "outcome": "units", "covariates": [], "treated_value": "=cmd|1"},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "source-my-sales"


def test_an_ambiguous_source_is_not_a_dataset_until_settled(client):
    upload(client, "uk", "Date,Units\n03/04/2024,1\n05/06/2024,2\n")
    entry = client.get(f"{V1}/sources/uk").json()
    assert not entry["ready"] and "choose one" in entry["problems"][0]
    assert "source-uk" not in {d["name"] for d in client.get(f"{V1}/datasets").json()["datasets"]}
    assert client.get(f"{V1}/datasets/source-uk").status_code == 404
    schema = entry["schema"]
    schema["columns"][0] = {"name": "Date", "kind": "time", "formats": ["%d/%m/%Y"], "ambiguous": False}
    assert client.put(f"{V1}/sources/uk/schema", json=schema).json()["ready"]
    assert client.get(f"{V1}/datasets/source-uk").json()["rows"][0] == ["2024-04-03", 1]


def test_a_wide_source_answers_fewer_rows(client, monkeypatch):
    from . import app as app_module

    monkeypatch.setattr(app_module, "MAX_DATASET_CELLS", 60)  # 6 fields: 10 rows at most
    upload(client, "my-sales")
    table = client.get(f"{V1}/datasets/source-my-sales").json()
    assert len(table["rows"]) == 10 and table["sampled"]


def test_exports_guard_text_that_a_spreadsheet_would_run(client, monkeypatch):
    world = client.app.state.store.current.world
    sku = world.warehouse.skus[0]
    monkeypatch.setattr(sku, "name", "=HYPERLINK(1)")
    text = client.get(f"{V1}/export", params={"entity": "skus"}).text
    assert "'=HYPERLINK(1)" in text


def test_a_failed_upload_leaves_nothing_behind(client, store):
    res = client.post(f"{V1}/sources", params={"name": "bad"}, content=b"\xff\xfe,b\n1,2\n")
    assert res.status_code == 422 and "not UTF-8" in res.json()["detail"]
    res = client.post(
        f"{V1}/sources", params={"name": "bad"}, content=b"When\n2024-01-01\n", headers={"content-type": "text/csv"}
    )
    assert res.status_code == 201
    assert sorted(p.name for p in store.root.iterdir()) == ["bad"]  # no .upload-* folder from the failed one


def test_an_unreadable_folder_is_listed_as_unavailable(client, store):
    upload(client, "ok")
    upload(client, "broken")
    (store.root / "broken" / "source.json").write_text("[]", encoding="utf-8")
    res = client.get(f"{V1}/sources").json()
    assert [s["name"] for s in res["sources"]][-1] == "ok" and "broken" in res["unavailable"]
    assert client.get(f"{V1}/sources/broken").status_code == 500
    assert client.delete(f"{V1}/sources/broken").status_code == 204


# -- evaluation on a source (U2, interfaces §2) ------------------------------------------------------


def test_every_ready_source_can_be_fitted_on(client):
    upload(client, "my-sales")
    listed = {s["id"]: s for s in client.get(f"{V1}/synthesis/sources").json()["sources"]}
    assert list(listed) == ["sample", "retail-10k", "my-sales"]
    mine = listed["my-sales"]
    assert mine["origin"] == "user" and mine["series"]
    assert mine["columns"] == ["Sku", "Units", "UnitPrice", "Store Name", "OrderDate.hour", "OrderDate.weekday"]


def test_a_run_on_a_source_takes_its_columns_and_row_choice(client):
    upload(client, "my-sales")
    body = {"synthesizer": "bootstrap-table", "source": "my-sales", "params": {"seed": 1}}
    res = client.post(f"{V1}/synthesis/runs", json=body | {"columns": ["Units", "OrderDate.hour"], "rows": "first"})
    assert res.status_code == 200, res.text
    run = res.json()
    assert (run["columns"], run["row_choice"]) == (["Units", "OrderDate.hour"], "first")
    assert [f["name"] for f in run["fields"]] == ["origin", "units", "order_date_hour"]
    default = client.post(f"{V1}/synthesis/runs", json=body).json()
    assert default["columns"] == ["Sku", "Units", "UnitPrice", "Store Name"]
    assert [n.split(":")[0] for n in default["notes"]] == ["Sku"]  # three labels; Store Name has two
    bad = client.post(f"{V1}/synthesis/runs", json=body | {"columns": ["Nope"]})
    assert bad.status_code == 422 and "has no column 'Nope'" in bad.json()["detail"]
    series = client.post(f"{V1}/synthesis/runs", json=body | {"synthesizer": "seasonal-profile"})
    assert series.status_code == 200 and series.json()["kind"] == "series"
    bundled = client.post(f"{V1}/synthesis/runs", json=body | {"source": "sample"}).json()
    assert bundled["columns"] is None and [f["name"] for f in bundled["fields"]][1] == "qty"  # as today


def test_a_path_is_never_a_source_over_http(client):
    res = client.post(
        f"{V1}/synthesis/runs", json={"synthesizer": "bootstrap-table", "source": "data/sample_online_retail_ii.csv"}
    )
    assert res.status_code == 422 and "unknown source" in res.json()["detail"]
