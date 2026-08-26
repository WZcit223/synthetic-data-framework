"""Multi-source data registry (Foundation Layer).

The platform must "overlay and analyse multiple data sources". This registry is
the seam that makes that possible: every dataset — synthetic or real — is
registered as a :class:`DataSource`. Downstream layers ask the registry for a
*stream* by entity type and get back rows regardless of origin.

Framework behaviour: sources are in-memory lists. The real system swaps the
``_rows`` backing store for connectors (SQL, object storage, Kafka, a feature
store) without changing the interface the Application Layer depends on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass
class DataSource:
    """A named, typed collection of records from one origin."""

    name: str
    entity_type: str
    origin: str  # "synthetic" | "real" | "external-open-dataset"
    _rows: List[Any] = field(default_factory=list)

    def add(self, rows: Iterable[Any]) -> "DataSource":
        self._rows.extend(rows)
        return self

    def rows(self) -> List[Any]:
        return list(self._rows)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._rows)


class DataSourceRegistry:
    """Central catalogue that lets layers overlay multiple sources by entity."""

    def __init__(self) -> None:
        self._sources: Dict[str, DataSource] = {}

    def register(
        self,
        name: str,
        entity_type: str,
        rows: Iterable[Any],
        origin: str = "synthetic",
    ) -> DataSource:
        src = DataSource(name=name, entity_type=entity_type, origin=origin)
        src.add(rows)
        self._sources[name] = src
        return src

    def sources(self) -> List[DataSource]:
        return list(self._sources.values())

    def stream(
        self,
        entity_type: str,
        where: Optional[Callable[[Any], bool]] = None,
    ) -> List[Any]:
        """Overlay every registered source of ``entity_type`` into one stream."""

        out: List[Any] = []
        for src in self._sources.values():
            if src.entity_type != entity_type:
                continue
            for row in src.rows():
                if where is None or where(row):
                    out.append(row)
        return out

    def summary(self) -> Dict[str, Any]:
        return {
            "source_count": len(self._sources),
            "by_entity": self._count_by("entity_type"),
            "by_origin": self._count_by("origin"),
        }

    def _count_by(self, attr: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for src in self._sources.values():
            key = getattr(src, attr)
            counts[key] = counts.get(key, 0) + len(src)
        return counts
