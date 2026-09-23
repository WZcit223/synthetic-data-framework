"""An immutable dataset that simulations run on."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from sdf.analytics.demand import DemandTable
from sdf.foundation.registry import DataSourceRegistry
from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from sdf.synthesis.warehouse import SyntheticWarehouse


@dataclass(frozen=True)
class World:
    """A registry of entity streams plus where it came from.

    ``spec`` is set when the data was generated from a ``GenerationSpec`` and
    still matches it; a data-level intervention (``with_stream``) clears it,
    because the data no longer follows the spec. ``warehouse`` keeps the
    generated bundle for structural checks when there is one.
    """

    registry: DataSourceRegistry
    spec: GenerationSpec | None = None
    label: str = ""
    warehouse: SyntheticWarehouse | None = field(default=None, repr=False, compare=False)

    @classmethod
    def generate(cls, spec: GenerationSpec, *, label: str | None = None) -> World:
        """Generate the world described by ``spec``."""
        warehouse, registry = build_registry(spec)
        return cls(
            registry=registry, spec=spec, label=label or f"GenerationSpec(seed={spec.seed})", warehouse=warehouse
        )

    def stream(self, entity_type: str) -> list[Any]:
        return self.registry.stream(entity_type)

    @cached_property
    def _demand(self) -> DemandTable:
        return DemandTable.from_orders(self.stream("OutboundOrder"))

    def demand(self) -> DemandTable:
        """Per-SKU daily demand of the world's non-cancelled orders (computed once)."""
        return self._demand

    def with_stream(self, entity_type: str, rows: Iterable[Any], *, label: str) -> World:
        """A new world whose ``entity_type`` stream is replaced by ``rows``; this world is unchanged."""
        registry = DataSourceRegistry()
        for src in self.registry.sources():
            if src.entity_type != entity_type:
                registry.register(src.name, src.entity_type, src.rows(), origin=src.origin)
        registry.register(f"{label}:{entity_type}", entity_type, list(rows), origin="intervention")
        return World(registry=registry, spec=None, label=label)
