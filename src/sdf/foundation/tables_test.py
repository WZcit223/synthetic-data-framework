"""Tests for the table types."""

from __future__ import annotations

import math
from datetime import date

import pytest

from .tables import DatasetInfo, Field, Table


def _info(*fields: Field) -> DatasetInfo:
    return DatasetInfo(name="demo", label="Demo", description="A test table", fields=fields)


def test_a_measure_defaults_to_sum_and_a_dimension_has_no_aggregate():
    assert Field("lines", "Lines", "measure").aggregate == "sum"
    assert Field("price", "Price", "measure", unit="currency", aggregate="mean").aggregate == "mean"
    channel = Field("channel", "Channel", "dimension")
    assert (channel.unit, channel.aggregate) == (None, None)
    assert channel.to_dict() == {
        "name": "channel",
        "label": "Channel",
        "kind": "dimension",
        "unit": None,
        "aggregate": None,
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "Channel", "label": "x", "kind": "dimension"}, "lower_snake_case"),
        ({"name": "channel\n", "label": "x", "kind": "dimension"}, "lower_snake_case"),
        ({"name": "channel", "label": "x", "kind": "category"}, "kind must be one of"),
        ({"name": "channel", "label": "x", "kind": "dimension", "unit": "units"}, "only a measure"),
        ({"name": "day", "label": "x", "kind": "time", "aggregate": "sum"}, "only a measure"),
        ({"name": "qty", "label": "x", "kind": "measure", "aggregate": "median"}, "aggregate must be one of"),
    ],
)
def test_field_rejects_what_it_cannot_describe(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Field(**kwargs)


def test_dataset_info_rejects_a_bad_name_and_duplicate_fields():
    with pytest.raises(ValueError, match="dashes"):
        DatasetInfo(name="Order_Lines", label="x", description="x", fields=())
    with pytest.raises(ValueError, match="dashes"):
        DatasetInfo(name="order-lines\n", label="x", description="x", fields=())
    with pytest.raises(ValueError, match=r"duplicate field names \['qty'\]"):
        _info(Field("qty", "Qty", "measure"), Field("qty", "Qty again", "measure"))
    with pytest.raises(TypeError, match="tuple of Field"):
        DatasetInfo(name="demo", label="x", description="x", fields=[Field("qty", "Qty", "measure")])


def test_table_accepts_values_that_match_their_fields():
    info = _info(Field("day", "Day", "time"), Field("channel", "Channel", "dimension"), Field("qty", "Qty", "measure"))
    table = Table(info, [("2025-01-02", "store", 3), ("2025-01-03", None, 1.5), (None, "web", None)])
    assert len(table.rows) == 3


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("2025-01-02", "store"), "has 2 values for 3 fields"),
        ((date(2025, 1, 2), "store", 1), "field day: a time field holds an ISO date"),
        (("2025-13-01", "store", 1), "field day: a time field holds an ISO date"),
        (("2025-W01-1", "store", 1), "field day: a time field holds an ISO date"),
        (("２０２５-01-01", "store", 1), "field day: a time field holds an ISO date"),
        (("2025-01-02", 7, 1), "field channel: a dimension holds text, got int"),
        (("2025-01-02", "store", "3"), "field qty: a measure holds a number, got str"),
        (("2025-01-02", "store", True), "field qty: a measure holds a number, got bool"),
        (("2025-01-02", "store", math.nan), "field qty: a measure must be finite"),
    ],
)
def test_table_names_the_dataset_row_and_field_of_a_bad_value(row, message):
    info = _info(Field("day", "Day", "time"), Field("channel", "Channel", "dimension"), Field("qty", "Qty", "measure"))
    with pytest.raises(ValueError, match=rf"^dataset demo: row 0.*{message}"):
        Table(info, [row])
