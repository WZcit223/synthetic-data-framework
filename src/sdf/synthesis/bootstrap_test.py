"""Tests for the bootstrap table synthesizer."""

from __future__ import annotations

import random
import statistics

from .api import TableData
from .bootstrap import BootstrapTable

ROWS = [(float(i % 7), float(i % 5) + 0.5, float(i % 24)) for i in range(50)]


def test_first_sample_matches_the_per_column_bootstrap():
    # Reference: resample each column, then add N(0, 0.05 × column std), in column order per row.
    rng = random.Random(7)
    cols = list(zip(*ROWS))
    stds = [statistics.pstdev(c) or 1.0 for c in cols]
    expected = [tuple(rng.choice(c) + rng.gauss(0, 0.05 * s) for c, s in zip(cols, stds)) for _ in ROWS]
    assert BootstrapTable(seed=7).fit(TableData(rows=ROWS, columns=("a", "b", "c"))).sample() == expected


def test_stream_continues_and_a_seed_pins_it():
    model = BootstrapTable(seed=7).fit(TableData(rows=ROWS, columns=("a", "b", "c")))
    assert model.sample(5) != model.sample(5)
    assert model.sample(5, seed=1) == model.sample(5, seed=1)


def test_no_rows_samples_nothing():
    assert BootstrapTable().fit(TableData(rows=[], columns=("a",))).sample() == []


def test_rows_follow_the_table_s_column_kinds():
    data = TableData(rows=ROWS, columns=("a", "b", "c"), kinds=("integer", "category", "real"))
    rows = BootstrapTable(seed=7, jitter=0.3).fit(data).sample()
    observed_b = {r[1] for r in ROWS}
    assert all(r[0] == int(r[0]) and 0 <= r[0] <= 6 for r in rows)
    assert {r[1] for r in rows} <= observed_b
    assert any(r[2] != int(r[2]) for r in rows)  # a real column keeps its jitter
