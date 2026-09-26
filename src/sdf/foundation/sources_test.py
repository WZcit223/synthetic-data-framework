from __future__ import annotations

import io
import threading
from pathlib import Path

import pytest

from .sources import (
    BUNDLED,
    DATE_FORMATS,
    ColumnSpec,
    Roles,
    SourceConflict,
    SourceLimits,
    SourceSchema,
    SourceStore,
    SourceTooLarge,
    check,
    data_dir,
    dataset_info,
    default_store,
    infer_schema,
)

REPO_DATA = Path(__file__).resolve().parents[3] / "data"


def _csv(tmp_path: Path, text: str, name: str = "in.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _store(tmp_path: Path, **limits: int) -> SourceStore:
    return SourceStore(tmp_path / "sources", limits=SourceLimits(**limits))


def _lines(n: int, start: int = 0) -> str:
    return "".join(
        f"2024-01-{1 + (i % 28):02d},SKU{i % 3},{i % 5 + 1},{1.5 + i % 4}\n" for i in range(start, start + n)
    )


SALES = "OrderDate,Sku,Units,UnitPrice\n" + _lines(40)


# -- inference ---------------------------------------------------------------------------------------


def test_inference_reads_the_bundled_extract_as_its_declaration():
    schema = infer_schema(REPO_DATA / BUNDLED["retail-10k"].file, name="copy")
    kinds = {c.name: c.kind for c in schema.columns}
    declared = {c.name: c.kind for c in BUNDLED["retail-10k"].schema.columns}
    assert kinds == declared
    assert schema.roles == BUNDLED["retail-10k"].schema.roles
    # every sampled day of December 2010 is at most 12, so day-first also fits: flagged, not guessed
    time = schema.column("InvoiceDate")
    assert time.ambiguous and time.formats == ("%m/%d/%y %H:%M", "%d/%m/%y %H:%M")
    assert schema.problems and "InvoiceDate" in schema.problems[0]


def test_inference_rules_run_in_order(tmp_path):
    rows = "".join(
        f"{i:06d},C{i},2024-02-{1 + i % 28:02d},{i * 1.37 + 0.01:.2f},{i % 7},A label {i % 3},{'long ' * 12}{i}\n"
        for i in range(60)
    )
    path = _csv(tmp_path, "Order No,Code,OrderDate,Amount,Units,Store Name,Notes\n" + rows)
    kinds = {c.name: c.kind for c in infer_schema(path, name="x").columns}
    assert kinds == {
        "Order No": "id",  # a name word, even though the values look like numbers
        "Code": "id",  # a name word
        "OrderDate": "time",  # a date is a time before any name rule
        "Amount": "real",  # unique amounts stay numbers: real values are never ids by distinctness
        "Units": "integer",
        "Store Name": "category",  # spaces, but only three labels
        "Notes": "text",  # long values
    }


def test_inference_ignores_blanks_and_falls_back_to_category(tmp_path):
    rows = "".join(f"{'' if i % 4 == 0 else i % 3},{'x' if i % 2 else ''},\n" for i in range(30))
    path = _csv(tmp_path, "Units,Flag,Empty\n" + rows)
    kinds = {c.name: c.kind for c in infer_schema(path, name="x").columns}
    assert kinds == {"Units": "integer", "Flag": "category", "Empty": "category"}


def test_distinct_codes_are_ids_but_numeric_measures_are_not(tmp_path):
    rows = "".join(f"K-{i},{i},{i % 4}\n" for i in range(50))
    kinds = {c.name: c.kind for c in infer_schema(_csv(tmp_path, "Ref,Seq,Units\n" + rows), name="x").columns}
    assert kinds == {"Ref": "id", "Seq": "id", "Units": "integer"}  # whole numbers all distinct: a sequence


def test_semicolons_mean_decimal_commas(tmp_path):
    path = _csv(
        tmp_path,
        "Datum;Artikel;Menge;Preis\n" + "".join(f"2024-03-0{1 + i % 9};A{i % 2};{i};3,{i}\n" for i in range(9)),
    )
    schema = infer_schema(path, name="de")
    assert (schema.delimiter, schema.decimal) == (";", ",")
    assert schema.column("Preis").kind == "real"
    report = check(path, schema)
    assert report.rows_kept == 9 and not report.unreadable


def test_day_first_dates_are_flagged_when_both_orders_fit(tmp_path):
    path = _csv(tmp_path, "Date,Units\n03/04/2024,1\n05/06/2024,2\n")
    column = infer_schema(path, name="x").column("Date")
    assert column.ambiguous and column.formats == ("%m/%d/%Y", "%d/%m/%Y")
    # a day over 12 settles it
    path = _csv(tmp_path, "Date,Units\n03/04/2024,1\n25/06/2024,2\n")
    column = infer_schema(path, name="x").column("Date")
    assert not column.ambiguous and column.formats == ("%d/%m/%Y",)


def test_roles_are_guessed_from_names_and_kinds(tmp_path):
    schema = infer_schema(_csv(tmp_path, SALES), name="x")
    assert schema.roles == Roles(time="OrderDate", item="Sku", quantity="Units", price="UnitPrice")
    assert schema.has_demand


# -- schema ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roles, problem",
    [
        (Roles(quantity="When"), "must be integer or real"),
        (Roles(time="Units"), "must be time"),
        (Roles(item="Nope"), "not a column"),
        (Roles(quantity="Units", price="Units"), "both quantity and price"),
    ],
)
def test_a_role_must_name_a_column_of_a_fitting_kind(roles, problem):
    columns = (ColumnSpec("When", "time"), ColumnSpec("Units", "integer"))
    with pytest.raises(ValueError, match=problem):
        SourceSchema("x", "x", columns, roles=roles)


@pytest.mark.parametrize("name", ["", "My-Sales", "a_b", "-a", "../etc", "x" * 41])
def test_names_are_checked_so_no_path_is_built_from_user_text(name):
    with pytest.raises(ValueError, match="source name"):
        SourceSchema(name, "x", (ColumnSpec("a", "id"),))


def test_a_schema_round_trips_through_json():
    schema = BUNDLED["sample"].schema
    assert SourceSchema.from_dict(schema.to_dict()) == schema
    with pytest.raises(ValueError, match="not a source schema"):
        SourceSchema.from_dict({"name": "x"})
    with pytest.raises(ValueError, match="only a time column takes formats"):
        ColumnSpec("a", "integer", formats=("%Y",))


# -- checks ------------------------------------------------------------------------------------------


def test_a_quantity_unreadable_on_more_than_5_percent_of_rows_is_refused(tmp_path):
    schema = infer_schema(_csv(tmp_path, SALES), name="x")
    bad = "OrderDate,Sku,Units,UnitPrice\n" + _lines(47) + "2024-01-01,SKU1,lots,1.0\n" * 3
    with pytest.raises(ValueError, match=r"column Units: 3 of 50 values cannot be read as integer \(e.g. 'lots'"):
        check(_csv(tmp_path, bad, "bad.csv"), schema)
    fine = "OrderDate,Sku,Units,UnitPrice\n" + _lines(49) + "2024-01-01,SKU1,lots,1.0\n"
    report = check(_csv(tmp_path, fine, "fine.csv"), schema)
    assert report.rows_kept == 49 and report.unreadable == {"Units": 1} and report.examples == {"Units": ["lots"]}
    assert report.skipped == {"rows without a readable time or quantity": 1}


def test_blank_cells_are_counted_apart_and_short_rows_skipped(tmp_path):
    schema = infer_schema(_csv(tmp_path, SALES), name="x")
    text = "OrderDate,Sku,Units,UnitPrice\n" + _lines(10) + "2024-01-02,SKU1,3,\n2024-01-02,SKU1\n"
    report = check(_csv(tmp_path, text, "b.csv"), schema)
    assert report.rows_kept == 11 and report.blank == {"UnitPrice": 1} and report.skipped == {"malformed rows": 1}
    assert (report.first_date, report.last_date, report.times_of_day) == ("2024-01-01", "2024-01-10", [])


def test_the_header_must_be_the_schema_columns(tmp_path):
    schema = infer_schema(_csv(tmp_path, SALES), name="x")
    with pytest.raises(ValueError, match="are not the schema's"):
        check(_csv(tmp_path, "OrderDate,Sku,Units\n2024-01-01,a,1\n", "c.csv"), schema)


# -- the store ---------------------------------------------------------------------------------------


def test_add_list_rows_and_remove(tmp_path):
    store = _store(tmp_path)
    entry = store.add(_csv(tmp_path, SALES), name="my-sales")
    assert entry.origin == "user" and entry.report.rows_kept == 40 and entry.to_dict()["ready"]
    assert [e.name for e in store.list()] == ["my-sales"]
    table = store.rows("my-sales")
    assert [f.name for f in table.info.fields] == ["order_date", "sku", "units", "unit_price"]
    assert table.info.name == "source-my-sales" and table.rows[0] == ("2024-01-01", "SKU0", 1, 1.5)
    assert store.rows("my-sales", limit=5).rows == table.rows[:5]
    sample = store.rows("my-sales", limit=5, seed=3)
    assert len(sample.rows) == 5 and sample.rows == store.rows("my-sales", limit=5, seed=3).rows
    assert set(sample.rows) <= set(table.rows)
    assert store.rows("my-sales", columns=["Units"]).rows[0] == (1,)
    store.remove("my-sales")
    assert store.list() == [] and not (tmp_path / "sources" / "my-sales").exists()
    with pytest.raises(KeyError, match="no source 'my-sales'"):
        store.get("my-sales")


def test_orders_follow_the_retail_adapter_rules(tmp_path):
    text = "Day,Item,Qty,Price,Cost\n2024-01-01,a,2,4.0,1.0\n2024-01-02,a,-1,6.0,\n2024-01-02,b,0,1.0,\n2024-01-03,b,2.6,-1,\n"
    store = _store(tmp_path)
    store.add(_csv(tmp_path, text), name="lines")
    skus, orders = store.orders("lines")
    assert [(o.sku_id, o.quantity, o.status) for o in orders] == [
        ("a", 2, "shipped"),
        ("a", 1, "cancelled"),
        ("b", 3, "shipped"),
    ]
    by_id = {s.sku_id: s for s in skus}
    assert (by_id["a"].unit_price, by_id["a"].unit_cost) == (5.0, 1.0)
    assert (by_id["b"].unit_price, by_id["b"].unit_cost) == (0.0, 0.0)  # no positive price: none known


def test_a_source_without_item_is_one_series_and_one_without_demand_has_no_orders(tmp_path):
    store = _store(tmp_path)
    store.add(_csv(tmp_path, "Date,Units\n2024-01-01,3\n2024-01-02,4\n"), name="total")
    skus, orders = store.orders("total")
    assert [s.sku_id for s in skus] == ["all"] and len(orders) == 2
    store.add(_csv(tmp_path, "Colour,Size\nred,1\n", "b.csv"), name="flat")
    with pytest.raises(ValueError, match="has no demand"):
        store.orders("flat")


def test_an_ambiguous_source_is_stored_but_not_read_until_settled(tmp_path):
    store = _store(tmp_path)
    entry = store.add(_csv(tmp_path, "Date,Units\n03/04/2024,1\n05/06/2024,2\n"), name="uk")
    assert not entry.to_dict()["ready"]
    with pytest.raises(ValueError, match="cannot be read yet"):
        store.rows("uk")
    settled = SourceSchema(
        "uk",
        "uk",
        (ColumnSpec("Date", "time", formats=("%d/%m/%Y",)), ColumnSpec("Units", "integer")),
        roles=Roles(time="Date", quantity="Units"),
    )
    entry = store.update_schema("uk", settled)
    assert entry.to_dict()["ready"] and entry.report.first_date == "2024-04-03"
    assert store.rows("uk").rows[0] == ("2024-04-03", 1)


def test_each_limit_is_refused_with_its_name(tmp_path):
    with pytest.raises(SourceTooLarge, match="larger than 100 bytes"):
        _store(tmp_path, max_bytes=100).add(_csv(tmp_path, SALES), name="big")
    assert list((tmp_path / "sources").iterdir()) == []  # the temporary folder is gone
    with pytest.raises(SourceTooLarge, match="more than 10 rows"):
        _store(tmp_path, max_rows=10).add(_csv(tmp_path, SALES), name="long")
    with pytest.raises(SourceTooLarge, match="4 columns; at most 3"):
        _store(tmp_path, max_columns=3).add(_csv(tmp_path, SALES), name="wide")
    store = _store(tmp_path, max_sources=1)
    store.add(_csv(tmp_path, SALES), name="one")
    with pytest.raises(SourceConflict, match="holds 1 user sources"):
        store.add(_csv(tmp_path, SALES), name="two")


def test_an_upload_without_a_length_is_cut_off_as_it_passes_the_limit(tmp_path):
    store = _store(tmp_path, max_bytes=1000)
    upload = store.begin("stream")
    upload.write(b"x" * 1000)
    with pytest.raises(SourceTooLarge):
        upload.write(b"x")
    upload.discard()
    assert list((tmp_path / "sources").iterdir()) == []


def test_names_are_taken_once_and_bundled_names_are_reserved(tmp_path):
    store = SourceStore(
        tmp_path / "sources", bundled={"sample": (REPO_DATA / BUNDLED["sample"].file, BUNDLED["sample"].schema)}
    )
    store.add(_csv(tmp_path, SALES), name="dup")
    with pytest.raises(SourceConflict, match="already exists"):
        store.add(_csv(tmp_path, SALES), name="dup")
    for name in ("sample", "retail-10k"):
        with pytest.raises(SourceConflict, match="bundled"):
            store.add(_csv(tmp_path, SALES), name=name)
    with pytest.raises(SourceConflict, match="cannot be removed"):
        store.remove("sample")
    with pytest.raises(SourceConflict, match="cannot be changed"):
        store.update_schema("sample", BUNDLED["sample"].schema)


def test_two_uploads_of_one_name_leave_one_source(tmp_path):
    store = _store(tmp_path)
    first, second = store.begin("race"), store.begin("race")  # both pass the early check
    for upload in (first, second):
        upload.write(SALES.encode())
    first.commit()
    with pytest.raises(SourceConflict, match="already exists"):
        second.commit()
    second.discard()
    assert [p.name for p in (tmp_path / "sources").iterdir()] == ["race"]


def test_concurrent_adds_respect_the_source_limit(tmp_path):
    store = _store(tmp_path, max_sources=3)
    errors: list[Exception] = []

    def add(i: int) -> None:
        try:
            store.add(io.BytesIO(SALES.encode()), name=f"s{i}")
        except SourceConflict as exc:
            errors.append(exc)

    threads = [threading.Thread(target=add, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.list()) == 3 and len(errors) == 3


def test_empty_and_non_utf8_files_are_refused(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        store.add(io.BytesIO(b""), name="empty")
    with pytest.raises(ValueError, match="not UTF-8"):
        store.add(io.BytesIO("Größe,Units\nä,1\n".encode("latin-1")), name="latin")


def test_the_dataset_view_maps_names_and_splits_the_hour(tmp_path):
    text = (
        "InvoiceDate,Customer ID,customer_id,Price,Note\n2024-01-01 08:30:00,7,8,2.5,"
        + "a long free-text note " * 3
        + "\n"
    )
    store = _store(tmp_path)
    entry = store.add(_csv(tmp_path, text), name="map")
    info = dataset_info(entry)
    assert [(f.name, f.kind) for f in info.fields] == [
        ("invoice_date", "time"),
        ("invoice_date_hour", "dimension"),
        ("customer_id", "dimension"),
        ("customer_id_2", "dimension"),
        ("price", "measure"),
    ]
    assert store.rows("map").rows == [("2024-01-01", "08", "7", "8", 2.5)]


def test_the_bundled_files_are_sources_with_declared_schemas(monkeypatch):
    monkeypatch.setenv("SDF_DATA_DIR", str(REPO_DATA))
    store = default_store()
    assert data_dir() == REPO_DATA and [e.name for e in store.list()] == ["retail-10k", "sample"]
    entry = store.get("retail-10k")
    assert entry.origin == "bundled" and entry.report.rows_kept == 10_000
    assert (entry.report.first_date, entry.report.last_date) == ("2010-12-01", "2010-12-05")
    assert BUNDLED["retail-10k"].schema.column("InvoiceDate").formats == DATE_FORMATS
