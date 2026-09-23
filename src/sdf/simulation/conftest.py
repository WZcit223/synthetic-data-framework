"""Fixtures shared by the simulation tests."""

from __future__ import annotations

import pytest

from sdf.synthesis.spec import GenerationSpec
from .world import World


@pytest.fixture(scope="session")
def small_world() -> World:
    """A fast world for shape tests; golden values use the default world."""
    return World.generate(GenerationSpec(n_skus=40, horizon_days=30))


@pytest.fixture(scope="session")
def world(default_world) -> World:
    """The default world wrapped as a ``World`` (shares the session registry)."""
    wh, reg, _ = default_world
    return World(registry=reg, spec=GenerationSpec(), label="GenerationSpec(seed=42)", warehouse=wh)
