"""Evaluation on a data source's own columns and demand (docs/refactor/userdata/interfaces.md §2)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import ClassVar

import pytest

from sdf.foundation.sources import BUNDLED, SourceStore, data_dir
from sdf.synthesis.api import SynthesizerInfo, TableData
from sdf.synthesis.registry import default_registry
from .evaluation import MAX_TABLE_ROWS, NoUsableRows, RunFailed, evaluate

SALES = "Day,Store,Units,Price,Note\n" + "".join(
    f"2024-01-{1 + i % 28:02d} {9 + i % 8:02d}:15:00,{['north', 'south', 'east'][i % 7 % 3]},{1 + i % 4},"
    f"{2.5 + i % 3},{'x' * 50}\n"
    for i in range(200)
)


@pytest.fixture
def store(tmp_path):
    bundled = {n: (data_dir() / b.file, b.schema) for n, b in BUNDLED.items()}
    s = SourceStore(tmp_path / "sources", bundled=bundled)
    s.add(io.BytesIO(SALES.encode()), name="sales")
    return s


def run(store, synthesizer="bootstrap-table", **kw):
    return evaluate(synthesizer, source="sales", store=store, params={"seed": 3}, **kw)


def test_a_table_run_reads_the_source_columns_and_kinds(store):
    r = run(store)
    assert r.columns == ("Store", "Units", "Price") and r.rows == "sample"  # the text column is left out
    assert [f.name for f in r.table.info.fields] == ["origin", "store", "units", "price"]
    assert [f.kind for f in r.table.info.fields] == ["dimension", "dimension", "measure", "measure"]
    real = [row for row in r.table.rows if row[0] == "real"]
    synth = [row for row in r.table.rows if row[0] == "synthetic"]
    assert len(real) == 200 and synth and {row[1] for row in synth} <= {"north", "south", "east"}  # decoded labels
    assert {"clone_risk_pct", "detection_auc"} <= set(r.metrics)
    assert r.notes and r.notes[0].startswith("Store: its 3 labels are coded 0 to 2")
    assert run(store).table.rows == r.table.rows  # the same seed, the same run


def test_categories_are_coded_by_frequency_then_first_seen(store, monkeypatch):
    seen = {}

    class Spy:
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("spy", "table", True, "keeps what it is given")

        def fit(self, data: TableData):
            seen["data"] = data
            return self

        def sample(self, n=None):
            return [(0.4, 1.0, 3.0), (7.0, 2.0, 2.5), (1.5, 1.0, 2.5)]  # rounded, out of range, a half

    reg = default_registry()
    reg.register(Spy)
    r = evaluate("spy", source="sales", store=store, registry=reg, columns=["Store", "Units", "Price"])
    data = seen["data"]
    assert data.kinds == ("category", "integer", "real")
    # i % 7 % 3 over 200 rows: north (0) most often, then south (1), then east (2)
    assert sorted({row[0] for row in data.rows}) == [0.0, 1.0, 2.0]
    synth = [row[1:] for row in r.table.rows if row[0] == "synthetic"]
    assert synth == [("north", 1.0, 3.0), ("east", 2.0, 2.5), ("east", 1.0, 2.5)]  # rounded, clipped, halves up


def test_derived_hour_and_weekday_and_the_first_rows(store):
    r = run(store, columns=["Units", "Day.hour", "Day.weekday"], rows="first")
    assert [f.name for f in r.table.info.fields] == ["origin", "units", "day_hour", "day_weekday"]
    first = next(row for row in r.table.rows if row[0] == "real")
    assert first == ("real", 1.0, 9.0, "Monday")  # 2024-01-01 09:15 was a Monday
    assert r.rows == "first"


def test_rows_with_a_missing_value_or_no_positive_quantity_are_left_out(tmp_path):
    store = SourceStore(tmp_path / "s")
    text = "Units,Price,Kind\n1,2.0,a\n-1,2.0,a\n2,0,a\n3,,a\n4,1.5,\n5,1.0,b\n"
    store.add(io.BytesIO(text.encode()), name="t")
    r = evaluate("bootstrap-table", source="t", store=store)
    assert sorted(row[1:] for row in r.table.rows if row[0] == "real") == [(1.0, 2.0, "a"), (5.0, 1.0, "b")]


def test_the_sample_is_uniform_over_the_whole_file(tmp_path):
    store = SourceStore(tmp_path / "s")
    n = MAX_TABLE_ROWS * 3
    # a real-valued position (reals are never inferred as ids) tells which rows were read
    store.add(io.BytesIO(("Position,Price\n" + "".join(f"{i}.5,1.0\n" for i in range(n))).encode()), name="big")
    real = [row[1] for row in evaluate("bootstrap-table", source="big", store=store).table.rows if row[0] == "real"]
    assert len(real) == MAX_TABLE_ROWS and max(real) > 2 * MAX_TABLE_ROWS  # not the first rows
    first = evaluate("bootstrap-table", source="big", store=store, rows="first").table.rows
    assert max(row[1] for row in first if row[0] == "real") == MAX_TABLE_ROWS - 0.5


@pytest.mark.parametrize(
    "kw, message",
    [
        ({"columns": ["Nope"]}, r"has no column 'Nope'.*Day.hour"),
        ({"columns": ["Note"]}, "column Note is text"),
        ({"columns": ["Day"]}, "column Day is time"),
        ({"columns": ["Units", "Units"]}, "named twice"),
        ({"rows": "all"}, "rows is 'sample' or 'first'"),
    ],
)
def test_a_bad_choice_is_the_request_s_fault(store, kw, message):
    with pytest.raises(ValueError, match=message):
        run(store, **kw)


def test_a_series_run_reads_the_source_demand(store):
    r = evaluate("seasonal-profile", source="sales", store=store, params={"seed": 1})
    assert r.kind == "series" and r.metrics["fidelity_score"] is not None and r.load is None
    with pytest.raises(ValueError, match="columns and rows are for tables"):
        evaluate("seasonal-profile", source="sales", store=store, columns=["Units"])


def test_a_series_needs_hourly_demand(tmp_path):
    store = SourceStore(tmp_path / "s")
    store.add(io.BytesIO(b"Day,Units\n2024-01-01,1\n2024-01-02,2\n"), name="daily")
    store.add(io.BytesIO(b"Colour,Units\nred,1\n"), name="flat")
    with pytest.raises(ValueError, match="dates without times of day"):
        evaluate("seasonal-profile", source="daily", store=store)
    with pytest.raises(ValueError, match="has no demand"):
        evaluate("seasonal-profile", source="flat", store=store)


def test_a_bundled_source_without_a_choice_reads_as_it_always_did(store):
    today = evaluate("bootstrap-table", source="sample", params={"seed": 7})
    same = evaluate("bootstrap-table", source="sample", params={"seed": 7}, store=store)
    assert same.table.rows == today.table.rows and same.columns == () and same.rows is None
    chosen = evaluate("bootstrap-table", source="sample", store=store, columns=["Quantity", "Price"])
    assert chosen.columns == ("Quantity", "Price")


def test_a_path_takes_no_choice_and_an_unknown_source_is_named(store, tmp_path):
    path = Path(tmp_path / "x.csv")
    path.write_text("a\n1\n")
    with pytest.raises(ValueError, match="needs a source"):
        evaluate("bootstrap-table", source=str(path), store=store, columns=["a"])
    with pytest.raises(ValueError, match=r"unknown source 'nope'; choose from \['sample', 'retail-10k', 'sales'\]"):
        evaluate("bootstrap-table", source="nope", store=store)


def test_no_usable_row_and_a_synthesizer_giving_the_wrong_width(tmp_path):
    store = SourceStore(tmp_path / "s")
    store.add(io.BytesIO(b"Units,Price\n-1,2\n0,1\n"), name="returns")
    with pytest.raises(NoUsableRows, match="no row has every chosen column"):
        evaluate("bootstrap-table", source="returns", store=store)

    class Narrow:
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("narrow", "table", True, "one value short")

        def fit(self, data):
            return self

        def sample(self, n=None):
            return [(1.0,)]

    reg = default_registry()
    reg.register(Narrow)
    store.add(io.BytesIO(b"Units,Price\n1,2\n2,3\n"), name="ok")
    with pytest.raises(RunFailed, match=r"a row of 1 values, not one per column \['Units', 'Price'\]"):
        evaluate("narrow", source="ok", store=store, registry=reg)


# -- the independent review's cases --------------------------------------------------------------------


@pytest.mark.parametrize("name", default_registry().names())
def test_every_mounted_synthesizer_runs_on_a_user_source(store, name):
    info = default_registry().info(name)
    if info.produces == "warehouse":
        pytest.skip("a warehouse generator is chosen for the world, not evaluated")
    r = evaluate(name, source="sales", store=store)
    assert r.kind == info.produces
    assert ("fidelity_score" if r.kind == "series" else "detection_auc") in r.metrics


def test_the_seeded_sample_repeats_and_another_seed_draws_other_rows(tmp_path):
    store = SourceStore(tmp_path / "s")
    rows = "".join(f"{i}.5,1.0\n" for i in range(MAX_TABLE_ROWS * 3))
    store.add(io.BytesIO(("Position,Price\n" + rows).encode()), name="big")

    def real(seed):
        table = evaluate("bootstrap-table", source="big", store=store, params={"seed": seed}).table
        return [row for row in table.rows if row[0] == "real"]

    assert real(1) == real(1) and real(1) != real(2)


def test_a_date_only_time_offers_its_weekday_but_not_its_hour(tmp_path):
    store = SourceStore(tmp_path / "s")
    store.add(io.BytesIO(b"Day,Units\n2024-01-01,1\n2024-01-02,2\n2024-01-06,3\n"), name="daily")
    from .evaluation import derived_columns

    assert derived_columns(store.get("daily")) == ["Day.weekday"]
    r = evaluate("bootstrap-table", source="daily", store=store, columns=["Units", "Day.weekday"])
    assert [row[2] for row in r.table.rows if row[0] == "real"] == ["Monday", "Tuesday", "Saturday"]
    with pytest.raises(ValueError, match="holds dates without times of day"):
        evaluate("bootstrap-table", source="daily", store=store, columns=["Day.hour"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "x", None])
def test_a_synthesizer_giving_no_finite_number_is_its_own_failure(store, bad):
    class Bad:
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("bad", "table", True, "one bad value")

        def fit(self, data):
            return self

        def sample(self, n=None):
            return [(2.0, bad)]

    reg = default_registry()
    reg.register(Bad)
    with pytest.raises(RunFailed, match="Price = .*not a finite number"):
        evaluate("bad", source="sales", store=store, registry=reg, columns=["Units", "Price"])


def test_a_series_run_checks_the_source_before_creating_the_synthesizer(tmp_path):
    class Fragile:
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("fragile", "series", True, "fails when created")

        def __init__(self):
            raise RuntimeError("never created")

        def fit(self, data):
            return self

        def sample(self, n=None):
            return []

    store = SourceStore(tmp_path / "s")
    store.add(io.BytesIO(b"Colour,Units\nred,1\n"), name="flat")
    reg = default_registry()
    reg.register(Fragile)
    with pytest.raises(ValueError, match="has no demand"):  # the request's fault, before the plug-in's
        evaluate("fragile", source="flat", store=store, registry=reg)
