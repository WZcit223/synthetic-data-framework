"""Shared pytest fixtures for the colocated test files under ``src/sdf``."""

from __future__ import annotations

from pathlib import Path

import pytest

from .application.intelligence import WarehouseIntelligence
from .application.snapshot import snapshot
from .synthesis.materialise import build_registry
from .synthesis.spec import GenerationSpec

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"


@pytest.fixture(scope="session")
def default_world():
    """The default ``GenerationSpec()`` world, generated once per session.

    Returns ``(warehouse, registry, intelligence)``. Every golden number in
    ``docs/REFACTOR_PREP.md`` §2.5 is computed on this world.
    """
    wh, reg = build_registry(GenerationSpec())
    return wh, reg, WarehouseIntelligence(reg)


@pytest.fixture(scope="session")
def sample_csv() -> str:
    """Bundled schema-compatible sample (12 SKUs, 139 daily points)."""
    return str(DATA_DIR / "sample_online_retail_ii.csv")


@pytest.fixture(scope="session")
def retail_10k_csv() -> str:
    """Bundled real UCI Online Retail II extract (10k rows, 4 days)."""
    return str(DATA_DIR / "online_retail_ii_2010_10k.csv")


@pytest.fixture(scope="session")
def full_snapshot(sample_csv, retail_10k_csv) -> dict:
    """``sdf validate``'s snapshot of the default world and both bundled CSVs, computed once."""
    return snapshot(sample_csv, retail_10k_csv)
