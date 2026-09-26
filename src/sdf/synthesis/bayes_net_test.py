"""The tree-shaped Bayesian network synthesizer, written against the public plug-in contract only."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from .api import TableData
from .bayes_net import BayesianNetworkTable, _chow_liu
from .bootstrap import BootstrapTable


def linked(n: int = 600, seed: int = 0) -> TableData:
    """``size`` sets ``price`` exactly (3 sizes, 3 prices); ``hour`` is independent of both."""
    rng = np.random.default_rng(seed)
    size = rng.integers(0, 3, n)
    price = np.array([1.25, 2.5, 4.95])[size]
    hour = rng.integers(8, 18, n)
    rows = [(float(s), float(p), float(h)) for s, p, h in zip(size, price, hour)]
    return TableData(rows=rows, columns=("size", "price", "hour"), kinds=("category", "category", "integer"))


def test_it_imports_only_the_public_contract_and_numpy():
    tree = ast.parse(Path(__file__).with_name("bayes_net.py").read_text(encoding="utf-8"))
    imported = {
        ("." * node.level) + (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert imported == {"__future__", "typing", "numpy", ".api"}


def test_it_keeps_the_pairs_that_occur_together_where_a_per_column_bootstrap_breaks_them():
    data = linked()
    real_pairs = {(r[0], r[1]) for r in data.rows}
    rows = BayesianNetworkTable(seed=3).fit(data).sample()
    assert len(rows) == len(data.rows)
    kept = sum((r[0], r[1]) in real_pairs for r in rows) / len(rows)
    assert kept > 0.98  # each size with its own price, bar the small chance smoothing leaves an unseen pair
    boot = BootstrapTable(seed=3).fit(data).sample()
    assert sum((r[0], r[1]) in real_pairs for r in boot) / len(boot) < 0.5  # the bootstrap pairs them at random


def test_the_tree_links_the_dependent_columns():
    rng = np.random.default_rng(1)
    a = rng.integers(0, 4, 500)
    b = (a + (rng.random(500) < 0.1)) % 4  # b follows a, mostly
    c = rng.integers(0, 4, 500)  # c is on its own
    parent, order = _chow_liu([(a, 4), (c, 4), (b, 4)])
    assert parent[2] == 0 and order[0] == 0 and order.index(2) > order.index(0)


def test_a_seed_repeats_the_rows_and_the_stream_continues_without_one():
    data = linked()
    model = BayesianNetworkTable(seed=5).fit(data)
    first, second = model.sample(50), model.sample(50)
    assert first != second  # the instance's stream continues
    assert BayesianNetworkTable(seed=5).fit(data).sample(50) == first
    assert model.sample(50, seed=2) == model.sample(50, seed=2) != first


def test_values_are_real_values_and_follow_the_column_kinds():
    rng = np.random.default_rng(2)
    rows = [
        (float(q), round(float(p), 2), float(h))
        for q, p, h in zip(rng.integers(1, 40, 800), rng.gamma(2.0, 3.0, 800), rng.integers(7, 20, 800))
    ]
    data = TableData(rows=rows, columns=("qty", "price", "hour"), kinds=("integer", "real", "category"))
    synth = BayesianNetworkTable(seed=1, bins=8).fit(data).sample()
    for j in range(3):  # a binned column draws the real values of each bin: every value was observed
        assert {r[j] for r in synth} <= {r[j] for r in rows}
    assert all(r[0] == int(r[0]) for r in synth)


def test_edge_cases_are_plain():
    empty = BayesianNetworkTable().fit(TableData(rows=[], columns=("a",)))
    assert empty.sample() == [] and empty.sample(5) == []
    assert BayesianNetworkTable().fit(linked(50)).sample(0) == []
    assert len(BayesianNetworkTable().fit(linked(50)).sample(7)) == 7
    constant = BayesianNetworkTable().fit(TableData(rows=[(1.0, 2.0)] * 20, columns=("a", "b")))
    assert constant.sample(3) == [(1.0, 2.0)] * 3
    with pytest.raises(RuntimeError, match="call fit"):
        BayesianNetworkTable().sample()
    with pytest.raises(ValueError, match="has a nan"):
        BayesianNetworkTable().fit(TableData(rows=[(1.0,), (float("nan"),)], columns=("a",)))
