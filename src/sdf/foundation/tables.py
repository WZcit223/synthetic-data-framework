"""Tables: typed fields plus rows, the shape every layer publishes data in.

A table is what the dataset catalogue builds, what an experiment returns and
what a synthesizer run produces. Each field says whether it is a *dimension*
(group by it), a *time* (an ISO date) or a *measure* (a number), so a client
can group, filter and aggregate any table without knowing its meaning.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, get_args

Kind = Literal["dimension", "time", "measure"]
Aggregate = Literal["sum", "mean", "min", "max"]

_FIELD_NAME = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
_DATASET_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")  # the calendar form only: fromisoformat also takes "2025-W01-1"


@dataclass(frozen=True)
class Field:
    """One column: its key, the label a person reads, and what kind of value it holds."""

    name: str
    label: str
    kind: Kind
    unit: str | None = None  # measures only, for example "units" or "currency"
    aggregate: Aggregate | None = None  # measures only: the aggregation a pivot selects first

    def __post_init__(self) -> None:
        if not _FIELD_NAME.fullmatch(self.name):
            raise ValueError(f"field name {self.name!r} must be lower_snake_case")
        if self.kind not in get_args(Kind):
            raise ValueError(f"field {self.name}: kind must be one of {list(get_args(Kind))}, got {self.kind!r}")
        if self.kind != "measure":
            if self.unit is not None or self.aggregate is not None:
                raise ValueError(f"field {self.name}: only a measure takes a unit or an aggregate")
            return
        if self.aggregate is None:
            object.__setattr__(self, "aggregate", "sum")
        elif self.aggregate not in get_args(Aggregate):
            raise ValueError(
                f"field {self.name}: aggregate must be one of {list(get_args(Aggregate))}, got {self.aggregate!r}"
            )

    def check(self, value: Any) -> str | None:
        """Why ``value`` cannot be held by this field, or ``None`` when it can."""
        if value is None:
            return None
        if self.kind == "dimension":
            return None if isinstance(value, str) else f"a dimension holds text, got {type(value).__name__}"
        if self.kind == "time":
            if isinstance(value, str) and _is_iso_date(value):
                return None
            return f"a time field holds an ISO date 'YYYY-MM-DD', got {value!r}"
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"a measure holds a number, got {type(value).__name__}"
        return None if isinstance(value, int) or math.isfinite(value) else f"a measure must be finite, got {value!r}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "unit": self.unit,
            "aggregate": self.aggregate,
        }


@dataclass(frozen=True)
class DatasetInfo:
    """What a dataset is: its catalogue key, a label, a description and its fields."""

    name: str
    label: str
    description: str
    fields: tuple[Field, ...]

    def __post_init__(self) -> None:
        if not _DATASET_NAME.fullmatch(self.name):
            raise ValueError(f"dataset name {self.name!r} must be lower-case words joined by dashes")
        if not isinstance(self.fields, tuple) or not all(isinstance(f, Field) for f in self.fields):
            raise TypeError(f"dataset {self.name}: fields must be a tuple of Field")
        names = [f.name for f in self.fields]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"dataset {self.name}: duplicate field names {duplicates}")


@dataclass(frozen=True)
class Table:
    """Rows of one dataset, one value per field in field order, every value checked against its field."""

    info: DatasetInfo
    rows: list[tuple[Any, ...]]

    def __post_init__(self) -> None:
        fields = self.info.fields
        for i, row in enumerate(self.rows):
            if len(row) != len(fields):
                raise ValueError(f"dataset {self.info.name}: row {i} has {len(row)} values for {len(fields)} fields")
            for field, value in zip(fields, row, strict=True):
                problem = field.check(value)
                if problem:
                    raise ValueError(f"dataset {self.info.name}: row {i}, field {field.name}: {problem}")


def csv_cell(value: Any) -> Any:
    """``value`` for a CSV cell: text that a spreadsheet would run as a formula gets a leading ``'``.

    Text starting with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return is guarded, as the
    pages' ``csvCell`` does; numbers and everything else are returned unchanged.
    """
    return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _is_iso_date(text: str) -> bool:
    if not _ISO_DATE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True
