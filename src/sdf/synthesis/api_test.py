"""Tests for the parameter shape every catalogue publishes."""

from __future__ import annotations

import math

import pytest

from .api import Param


def test_to_dict_is_the_published_shape():
    assert Param("seed", "int", None, nullable=True).to_dict() == {
        "name": "seed",
        "type": "int",
        "default": None,
        "min": None,
        "max": None,
        "exclusive": False,
        "nullable": True,
    }


@pytest.mark.parametrize(
    ("param", "value"),
    [
        (Param("seed", "int", 7), 3),
        (Param("seed", "int", 7), 10**400),  # an unbounded int of any size
        (Param("seed", "int", None, nullable=True), None),
        (Param("jitter", "float", 0.05, min=0.0, max=1.0), 0),  # an int is a valid float
        (Param("jitter", "float", 0.05, min=0.0, max=1.0), 1.0),  # inclusive bounds
        (Param("level", "float", 0.95, min=0.5, max=1.0, exclusive=True), 0.99),
        (Param("label", "str", "x"), ""),
        (Param("flag", "bool", False), True),
    ],
)
def test_check_accepts(param, value):
    assert param.check(value) is None


@pytest.mark.parametrize(
    ("param", "value", "message"),
    [
        (Param("seed", "int", 7), None, "must not be null"),
        (Param("seed", "int", 7), 1.5, "must be a whole number"),
        (Param("seed", "int", 7), True, "must be a number"),  # a bool is not a number here
        (Param("seed", "int", 7), "7", "must be a number"),
        (Param("jitter", "float", 0.05), math.inf, "must be finite"),
        (Param("seed", "int", 7, max=100), 10**400, "must be from -inf to 100"),  # a huge int, no overflow
        (Param("jitter", "float", 0.05, min=0.0, max=1.0), 1.5, "must be from 0.0 to 1.0, got 1.5"),
        (Param("jitter", "float", 0.05, min=0.0), -1, "must be from 0.0 to inf"),
        (Param("level", "float", 0.95, min=0.5, max=1.0, exclusive=True), 1.0, "between 0.5 and 1.0, both excluded"),
        (Param("label", "str", "x"), 3, "must be text"),
        (Param("flag", "bool", False), 1, "must be true or false"),
    ],
)
def test_check_refuses_with_a_reason(param, value, message):
    assert message in param.check(value)


def test_apply_kinds_rounds_integers_and_keeps_categories_to_observed_values():
    from .api import TableData, apply_kinds

    data = TableData(
        rows=[(1.0, 2.5, 3.0, 0.1), (4.0, 7.0, 9.0, 0.2)],
        columns=("qty", "price", "hour", "x"),
        kinds=("integer", "category", "category", "real"),
    )
    sampled = [(2.6, 4.75, 5.9, 0.123), (-3.0, 100.0, 6.1, 5.0), (9.4, 2.4, 3.0, 0.2)]
    assert apply_kinds(sampled, data) == [
        (3.0, 2.5, 3.0, 0.123),  # 4.75 is as near 2.5 as 7.0: the lower value
        (1.0, 7.0, 9.0, 5.0),  # clipped to the observed range; the nearest observed value
        (4.0, 2.5, 3.0, 0.2),
    ]
    assert apply_kinds(sampled, TableData(data.rows, data.columns)) is sampled  # no kinds: unchanged
    assert apply_kinds(sampled, TableData([], data.columns, data.kinds)) is sampled


def test_table_data_refuses_kinds_that_do_not_fit_its_columns():
    from .api import TableData

    with pytest.raises(ValueError, match="1 kinds for 2 columns"):
        TableData(rows=[], columns=("a", "b"), kinds=("real",))
    with pytest.raises(ValueError, match=r"unknown column kinds \['text'\]"):
        TableData(rows=[], columns=("a",), kinds=("text",))
