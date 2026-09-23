"""Tests for the vision stocktake module."""

from __future__ import annotations

from .vision import shelf_occupancy_grid, stocktake_discrepancies


def test_grid_and_stocktake(default_world):
    _, reg, _ = default_world
    grid = shelf_occupancy_grid(reg)
    assert grid and all("zone" in z and "aisles" in z for z in grid)
    st = stocktake_discrepancies(reg)
    assert (st["locations_scanned"], st["matched"], st["flagged"]) == (40, 32, 8)
    assert stocktake_discrepancies(reg, rel_threshold=10.0)["flagged"] == 0
