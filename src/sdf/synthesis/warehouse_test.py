"""Tests for the seeded warehouse generator."""

from __future__ import annotations

from .spec import GenerationSpec
from .warehouse import WarehouseGenerator


def test_deterministic_seed():
    a = WarehouseGenerator(GenerationSpec(seed=7, n_skus=50)).generate()
    b = WarehouseGenerator(GenerationSpec(seed=7, n_skus=50)).generate()
    assert [s.sku_id for s in a.skus] == [s.sku_id for s in b.skus]
    assert len(a.outbound) == len(b.outbound)


def test_counts_match_spec():
    spec = GenerationSpec(n_skus=123, n_locations=45)
    wh = WarehouseGenerator(spec).generate()
    assert len(wh.skus) == 123
    assert len(wh.locations) == 45
