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
