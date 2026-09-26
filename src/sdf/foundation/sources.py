"""Data sources: a CSV file plus a schema that says what each column holds.

A user brings a file; the framework reads it as it is. The **schema** gives each
column a kind (``id``, ``category``, ``integer``, ``real``, ``time``, ``text``)
and optional **roles** that say where the demand is (``time``, ``item``,
``quantity``, ``price``, ``cost``). ``infer_schema`` proposes a schema from the
file, which the user confirms or corrects; ``SourceStore`` keeps each source in
its own folder, checks every row when it arrives, and serves it back as a
checked ``Table`` or as the canonical ``SKU`` and ``OutboundOrder`` entities.

Contract: ``docs/refactor/userdata/interfaces.md`` §1.
"""

from __future__ import annotations

import csv
import io
import json
import os
import random
import re
import shutil
import statistics
import threading
import uuid
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Literal, get_args

from .adapters.retail_csv import DATE_FORMATS
from .schema import SKU, OutboundOrder
from .tables import DatasetInfo, Field, Table

ColumnKind = Literal["id", "category", "integer", "real", "time", "text"]
Origin = Literal["bundled", "user"]
ROLES = ("time", "item", "quantity", "price", "cost")
ROLE_KINDS: dict[str, frozenset[str]] = {
    "time": frozenset({"time"}),
    "item": frozenset({"id", "category"}),
    "quantity": frozenset({"integer", "real"}),
    "price": frozenset({"integer", "real"}),
    "cost": frozenset({"integer", "real"}),
}
DATA_DIR_ENV = "SDF_DATA_DIR"
DATASET_PREFIX = "source-"  # a source's name in the dataset catalogue; reserved for sources
MAX_NAME = 40
INFER_ROWS = 10_000  # rows inference reads
MAX_UNREADABLE = 0.05  # a quantity or time column unreadable on more rows than this refuses the source
PREVIEW_ROWS = 50
# Inference also tries the day-first dates the retail adapter leaves out, so a UK file is flagged, not misread.
INFER_FORMATS = DATE_FORMATS + ("%d/%m/%Y", "%d/%m/%y")
_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_ISO = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}([T ][0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?)?")
_WHOLE = re.compile(r"[-+]?[0-9]+")
_CHUNK = 1 << 20

# Inference: words of a column name that mark an identifier, and the names each role is guessed from.
ID_WORDS = frozenset({"id", "code", "no", "number", "invoice", "customer", "zip", "postcode"})
ROLE_WORDS: dict[str, frozenset[str]] = {
    "time": frozenset({"date", "time", "day", "timestamp", "invoicedate", "orderdate"}),
    "item": frozenset({"sku", "item", "product", "stockcode", "article"}),
    "quantity": frozenset({"quantity", "qty", "units", "sales", "demand"}),
    "price": frozenset({"price", "unitprice"}),
    "cost": frozenset({"cost", "unitcost"}),
}


class SourceTooLarge(ValueError):
    """An upload over a size limit (bytes, rows or columns)."""


class SourceConflict(ValueError):
    """The name is taken or reserved, the store is full, or a bundled source cannot be changed."""


def data_dir() -> Path:
    """Where data files are read from: ``$SDF_DATA_DIR``, default ``./data``."""
    return Path(os.environ.get(DATA_DIR_ENV) or "data")


def check_name(name: str) -> None:
    """``ValueError`` unless ``name`` is lower-case words joined by dashes, at most 40 characters."""
    if not isinstance(name, str) or not _NAME.fullmatch(name) or len(name) > MAX_NAME:
        raise ValueError(
            f"a source name is lower-case letters and digits joined by dashes, at most {MAX_NAME} characters;"
            f" got {name!r}"
        )


@dataclass(frozen=True)
class ColumnSpec:
    """One column: its name in the file's header, its kind, and for a time its formats."""

    name: str
    kind: ColumnKind
    formats: tuple[str, ...] = ()  # time only: strptime formats tried in order; () reads ISO 8601
    ambiguous: bool = False  # time only: day-first and month-first both fit; the user must pick one

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"a column name must be non-empty text, got {self.name!r}")
        if self.kind not in get_args(ColumnKind):
            raise ValueError(f"column {self.name}: kind must be one of {list(get_args(ColumnKind))}, got {self.kind!r}")
        object.__setattr__(self, "formats", tuple(self.formats))
        if self.kind != "time" and (self.formats or self.ambiguous):
            raise ValueError(f"column {self.name}: only a time column takes formats")
        if not all(isinstance(f, str) and "%" in f for f in self.formats):
            raise ValueError(f"column {self.name}: formats are strptime formats such as '%d/%m/%Y'")
        if self.ambiguous and len(self.formats) != 2:
            raise ValueError(f"column {self.name}: an ambiguous time column carries its two candidate formats")


@dataclass(frozen=True)
class Roles:
    """Which column is the time, the item, the quantity, the unit price and the unit cost; all optional."""

    time: str | None = None
    item: str | None = None
    quantity: str | None = None
    price: str | None = None
    cost: str | None = None

    def items(self) -> list[tuple[str, str]]:
        """The declared roles, as ``(role, column)``."""
        return [(r, getattr(self, r)) for r in ROLES if getattr(self, r) is not None]


@dataclass(frozen=True)
class SourceSchema:
    """How to read one CSV: its columns in header order, their roles, and how the file is written."""

    name: str
    label: str
    columns: tuple[ColumnSpec, ...]
    roles: Roles = field(default_factory=Roles)
    provenance: dict[str, str] = field(default_factory=dict)  # url, licence, fetched: free text
    delimiter: str = ","
    decimal: str = "."

    def __post_init__(self) -> None:
        check_name(self.name)
        object.__setattr__(self, "columns", tuple(self.columns))
        if not self.columns or not all(isinstance(c, ColumnSpec) for c in self.columns):
            raise ValueError(f"source {self.name}: columns must be a non-empty sequence of ColumnSpec")
        names = [c.name for c in self.columns]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"source {self.name}: duplicate column names {duplicates}")
        if self.delimiter not in (",", ";"):
            raise ValueError(f"source {self.name}: the delimiter is ',' or ';', got {self.delimiter!r}")
        if self.decimal not in (".", ","):
            raise ValueError(f"source {self.name}: the decimal mark is '.' or ',', got {self.decimal!r}")
        if self.decimal == self.delimiter:
            raise ValueError(f"source {self.name}: the decimal mark cannot be the delimiter")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in self.provenance.items()):
            raise ValueError(f"source {self.name}: provenance maps text to text")
        kinds = {c.name: c.kind for c in self.columns}
        used: dict[str, str] = {}
        for role, column in self.roles.items():
            if column not in kinds:
                raise ValueError(f"source {self.name}: role {role} names {column!r}, which is not a column")
            if kinds[column] not in ROLE_KINDS[role]:
                allowed = " or ".join(sorted(ROLE_KINDS[role]))
                raise ValueError(
                    f"source {self.name}: the {role} column {column!r} must be {allowed}, not {kinds[column]}"
                )
            if column in used:
                raise ValueError(f"source {self.name}: column {column!r} is both {used[column]} and {role}")
            used[column] = role

    def column(self, name: str) -> ColumnSpec:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"source {self.name} has no column {name!r}; its columns: {[c.name for c in self.columns]}")

    @property
    def problems(self) -> list[str]:
        """What must be settled before the source can be read: ambiguous date orders."""
        return [
            f"column {c.name}: day-first ({c.formats[1]}) and month-first ({c.formats[0]}) both fit; choose one"
            for c in self.columns
            if c.ambiguous
        ]

    @property
    def has_demand(self) -> bool:
        return self.roles.time is not None and self.roles.quantity is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "columns": [
                {"name": c.name, "kind": c.kind, "formats": list(c.formats), "ambiguous": c.ambiguous}
                for c in self.columns
            ],
            "roles": {r: getattr(self.roles, r) for r in ROLES},
            "provenance": dict(self.provenance),
            "delimiter": self.delimiter,
            "decimal": self.decimal,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceSchema:
        """The schema a JSON object describes; ``ValueError`` naming what is wrong."""
        try:
            return cls(
                name=data["name"],
                label=data.get("label") or data["name"],
                columns=tuple(ColumnSpec(**c) for c in data["columns"]),
                roles=Roles(**(data.get("roles") or {})),
                provenance=dict(data.get("provenance") or {}),
                delimiter=data.get("delimiter", ","),
                decimal=data.get("decimal", "."),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"not a source schema: {exc}") from exc


@dataclass(frozen=True)
class SourceLimits:
    """What one upload and the store may hold (decision E2)."""

    max_bytes: int = 200_000_000
    max_rows: int = 2_000_000
    max_columns: int = 64
    max_sources: int = 20  # user sources; the bundled ones do not count

    def __post_init__(self) -> None:
        for name in ("max_bytes", "max_rows", "max_columns", "max_sources"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"SourceLimits.{name} must be a positive whole number, got {value!r}")

    def to_dict(self) -> dict[str, int]:
        return {
            "max_bytes": self.max_bytes,
            "max_rows": self.max_rows,
            "max_columns": self.max_columns,
            "max_sources": self.max_sources,
        }


@dataclass
class SourceReport:
    """What reading every row found: rows kept and skipped, and each column's unreadable and blank cells."""

    rows_read: int = 0
    rows_kept: int = 0
    skipped: dict[str, int] = field(default_factory=dict)  # reason -> rows
    unreadable: dict[str, int] = field(default_factory=dict)  # column -> cells that do not parse as its kind
    examples: dict[str, list[str]] = field(default_factory=dict)  # column -> the first three of them
    blank: dict[str, int] = field(default_factory=dict)  # column -> blank cells
    first_date: str | None = None  # the time role's range, ISO dates
    last_date: str | None = None
    times_of_day: list[str] = field(default_factory=list)  # time columns holding a time other than midnight

    def summary(self) -> str:
        text = f"kept {self.rows_kept:,} of {self.rows_read:,} rows"
        if self.skipped:
            text += "; skipped " + ", ".join(f"{n:,} {reason}" for reason, n in sorted(self.skipped.items()))
        for column, n in sorted(self.unreadable.items()):
            text += f"; {column}: {n:,} unreadable (e.g. {', '.join(repr(e) for e in self.examples[column])})"
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_read": self.rows_read,
            "rows_kept": self.rows_kept,
            "skipped": dict(sorted(self.skipped.items())),
            "unreadable": dict(self.unreadable),
            "examples": {k: list(v) for k, v in self.examples.items()},
            "blank": dict(self.blank),
            "first_date": self.first_date,
            "last_date": self.last_date,
            "times_of_day": list(self.times_of_day),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceReport:
        return cls(**data)


@dataclass(frozen=True)
class SourceEntry:
    """A stored source: its schema, the report of its last check, and where its file is."""

    schema: SourceSchema
    report: SourceReport
    origin: Origin
    path: Path
    size_bytes: int

    @property
    def name(self) -> str:
        return self.schema.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.schema.label,
            "origin": self.origin,
            "rows": self.report.rows_kept,
            "columns": len(self.schema.columns),
            "size_bytes": self.size_bytes,
            "first_date": self.report.first_date,
            "last_date": self.report.last_date,
            "demand": self.schema.has_demand,
            "ready": not self.schema.problems,
            "problems": self.schema.problems,
            "schema": self.schema.to_dict(),
            "report": self.report.to_dict(),
            "summary": self.report.summary(),
        }


# -- reading values ----------------------------------------------------------------------------------


def _number(text: str, decimal: str) -> float:
    value = float(text.replace(",", ".") if decimal == "," else text)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{text!r} is not a finite number")
    return value


def _time(text: str, formats: tuple[str, ...]) -> datetime:
    if not formats:
        if not _ISO.fullmatch(text):
            raise ValueError(f"{text!r} is not an ISO 8601 date or time")
        return datetime.fromisoformat(text)
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"{text!r} matches none of {list(formats)}")


def _value(text: str, column: ColumnSpec, decimal: str) -> Any:
    """A cell as its column's kind: ``int``, ``float``, ``datetime`` or text; ``ValueError`` when it does not parse."""
    if column.kind == "integer":
        if _WHOLE.fullmatch(text):
            return int(text)
        value = _number(text, decimal)
        if not value.is_integer():
            raise ValueError(f"{text!r} is not a whole number")
        return int(value)
    if column.kind == "real":
        return _number(text, decimal)
    if column.kind == "time":
        return _time(text, column.formats)
    return text


def _open_rows(path: Path, delimiter: str) -> tuple[list[str], Iterator[list[str]], io.TextIOWrapper]:
    fh = open(path, newline="", encoding="utf-8-sig")
    reader = csv.reader(fh, delimiter=delimiter)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        fh.close()
        raise ValueError("the file is empty: a CSV needs a header row") from None
    except UnicodeDecodeError as exc:
        fh.close()
        raise ValueError(f"the file is not UTF-8 text: {exc.reason} at byte {exc.start}") from None
    return header, reader, fh


def _iter_kept(path: Path, schema: SourceSchema) -> Iterator[list[Any]]:
    """Every kept row, parsed: a value per column, ``None`` for a blank or unreadable cell.

    A row is skipped, as ``check`` counts it, when it has the wrong number of cells or its time
    or quantity cannot be read.
    """
    header, reader, fh = _open_rows(path, schema.delimiter)
    needed = [schema.roles.time, schema.roles.quantity]
    with fh:
        width = len(schema.columns)
        for cells in reader:
            if len(cells) != width:
                continue
            row: list[Any] = []
            for text, column in zip(cells, schema.columns, strict=True):
                text = text.strip()
                try:
                    row.append(_value(text, column, schema.decimal) if text else None)
                except ValueError:
                    row.append(None)
            if any(n is not None and row[_index(schema, n)] is None for n in needed):
                continue
            yield row


def _index(schema: SourceSchema, column: str) -> int:
    return [c.name for c in schema.columns].index(column)


def check(path: str | Path, schema: SourceSchema, limits: SourceLimits = SourceLimits()) -> SourceReport:
    """Read every row of ``path`` under ``schema`` and report what it found.

    Raises ``SourceTooLarge`` over the row or column limit, and ``ValueError`` when the header is
    not the schema's columns or a time or quantity column is unreadable on more than 5 % of its rows.
    """
    path = Path(path)
    header, reader, fh = _open_rows(path, schema.delimiter)
    report = SourceReport()
    columns = schema.columns
    with fh:
        if len(header) > limits.max_columns:
            raise SourceTooLarge(f"the file has {len(header)} columns; at most {limits.max_columns} are accepted")
        if header != [c.name for c in columns]:
            raise ValueError(f"the file's columns {header} are not the schema's {[c.name for c in columns]}")
        needed = {i for i, c in enumerate(columns) if c.name in (schema.roles.time, schema.roles.quantity)}
        time_role = _index(schema, schema.roles.time) if schema.roles.time else None
        first = last = None
        with_time: set[str] = set()
        try:
            for cells in reader:
                report.rows_read += 1
                if report.rows_read > limits.max_rows:
                    raise SourceTooLarge(f"the file has more than {limits.max_rows:,} rows, the most accepted")
                if len(cells) != len(columns):
                    report.skipped["malformed rows"] = report.skipped.get("malformed rows", 0) + 1
                    continue
                unusable = False
                for i, (text, column) in enumerate(zip(cells, columns, strict=True)):
                    text = text.strip()
                    if not text:
                        report.blank[column.name] = report.blank.get(column.name, 0) + 1
                        unusable = unusable or i in needed
                        continue
                    try:
                        value = _value(text, column, schema.decimal)
                    except ValueError:
                        report.unreadable[column.name] = report.unreadable.get(column.name, 0) + 1
                        examples = report.examples.setdefault(column.name, [])
                        if len(examples) < 3:
                            examples.append(text)
                        unusable = unusable or i in needed
                        continue
                    if column.kind == "time":
                        if value.hour or value.minute or value.second:
                            with_time.add(column.name)
                        if i == time_role:
                            day = value.date()
                            first = day if first is None or day < first else first
                            last = day if last is None or day > last else last
                if unusable:
                    reason = "rows without a readable time or quantity"
                    report.skipped[reason] = report.skipped.get(reason, 0) + 1
                    continue
                report.rows_kept += 1
        except UnicodeDecodeError as exc:
            raise ValueError(f"the file is not UTF-8 text: {exc.reason} near row {report.rows_read + 1}") from None
        except csv.Error as exc:
            raise ValueError(f"row {report.rows_read + 1} is not valid CSV: {exc}") from None
    for column in (schema.roles.time, schema.roles.quantity):
        bad = report.unreadable.get(column, 0) if column else 0
        if column and report.rows_read and bad / report.rows_read > MAX_UNREADABLE:
            raise ValueError(
                f"column {column}: {bad:,} of {report.rows_read:,} values cannot be read as"
                f" {schema.column(column).kind} (e.g. {', '.join(repr(e) for e in report.examples[column])});"
                " check its kind and format"
            )
    report.first_date = first.isoformat() if first else None
    report.last_date = last.isoformat() if last else None
    report.times_of_day = [c.name for c in columns if c.name in with_time]
    return report


# -- inference ---------------------------------------------------------------------------------------


def _words(name: str) -> list[str]:
    """A column name's words, split at spaces, underscores, dashes and capitals: ``InvoiceDate`` → invoice, date."""
    return [w.lower() for w in re.findall(r"[A-Z]+(?=[A-Z][a-z]|[^A-Za-z]|$)|[A-Z]?[a-z]+|[0-9]+", name)]


def _time_formats(values: list[str]) -> tuple[tuple[str, ...], bool] | None:
    """The formats every value parses with, and whether day and month order is ambiguous; ``None``: not times."""
    if all(_ISO.fullmatch(v) for v in values):
        try:
            for v in values:
                datetime.fromisoformat(v)
            return (), False
        except ValueError:
            pass
    fitting = []
    for fmt in INFER_FORMATS:
        try:
            for v in values:
                datetime.strptime(v, fmt)
        except ValueError:
            continue
        fitting.append(fmt)
    if not fitting:
        return None
    month_first = [f for f in fitting if f.startswith("%m/%d")]
    day_first = [f for f in fitting if f.startswith("%d/%m")]
    if month_first and day_first:
        return (month_first[0], day_first[0]), True
    return (fitting[0],), False


def _kind(name: str, values: list[str], decimal: str) -> ColumnSpec:
    """The kind of one column from its non-blank sampled values; the rules run in the contract's order."""
    if values:
        formats = _time_formats(values)
        if formats is not None:
            return ColumnSpec(name, "time", formats=formats[0], ambiguous=formats[1])
    if ID_WORDS.intersection(_words(name)):
        return ColumnSpec(name, "id")
    if not values:
        return ColumnSpec(name, "category")
    numbers = []
    for v in values:
        try:
            numbers.append(_number(v, decimal))
        except ValueError:
            break
    numeric = len(numbers) == len(values)
    whole = all(_WHOLE.fullmatch(v) for v in values)
    distinct = len(set(values))
    if len(values) >= 20 and distinct / len(values) > 0.95:
        if whole or (not numeric and not any(" " in v for v in values)):
            return ColumnSpec(name, "id")
    if numeric:
        return ColumnSpec(name, "integer" if all(n.is_integer() for n in numbers) else "real")
    if (distinct > 100 and any(" " in v for v in values)) or statistics.median(len(v) for v in values) > 40:
        return ColumnSpec(name, "text")
    return ColumnSpec(name, "category")


def _guess_roles(columns: tuple[ColumnSpec, ...]) -> Roles:
    chosen: dict[str, str] = {}
    for role in ROLES:
        for c in columns:
            if c.name in chosen.values() or c.kind not in ROLE_KINDS[role]:
                continue
            key = re.sub(r"[^a-z0-9]", "", c.name.lower())
            if key in ROLE_WORDS[role] or ROLE_WORDS[role].intersection(_words(c.name)):
                chosen[role] = c.name
                break
    return Roles(**chosen)


def infer_schema(path: str | Path, *, name: str, label: str | None = None) -> SourceSchema:
    """A proposed schema for ``path``: the delimiter, each column's kind and the roles guessed from names.

    Reads the header and up to 10,000 rows. The proposal is for the user to confirm or correct.
    """
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        try:
            first = fh.readline()
        except UnicodeDecodeError as exc:
            raise ValueError(f"the file is not UTF-8 text: {exc.reason}") from None
    delimiter = ";" if first.count(";") > first.count(",") else ","
    decimal = "," if delimiter == ";" else "."
    header, reader, fh = _open_rows(path, delimiter)
    if any(not h for h in header):
        fh.close()
        raise ValueError(f"every column needs a name in the header row; got {header}")
    samples: list[list[str]] = [[] for _ in header]
    with fh:
        try:
            for n, cells in enumerate(reader):
                if n >= INFER_ROWS:
                    break
                if len(cells) != len(header):
                    continue
                for values, text in zip(samples, cells, strict=True):
                    if text.strip():
                        values.append(text.strip())
        except UnicodeDecodeError as exc:
            raise ValueError(f"the file is not UTF-8 text: {exc.reason}") from None
        except csv.Error as exc:
            raise ValueError(f"the file is not valid CSV: {exc}") from None
    columns = tuple(_kind(h, values, decimal) for h, values in zip(header, samples, strict=True))
    return SourceSchema(
        name=name,
        label=label or name,
        columns=columns,
        roles=_guess_roles(columns),
        delimiter=delimiter,
        decimal=decimal,
    )


# -- the dataset view of a source ---------------------------------------------------------------------


def _field_name(column: str) -> str:
    """``InvoiceDate`` → ``invoice_date``, ``Customer ID`` → ``customer_id``: a lower_snake_case field name."""
    words = _words(column) or ["column"]
    name = "_".join(words)
    return name if name[0].isalpha() else "c_" + name


def dataset_info(entry: SourceEntry) -> DatasetInfo:
    """The dataset a source is: ``source-<name>``, a field per column (text left out), a time's hour as its own."""
    fields: list[Field] = []
    taken: set[str] = set()

    def add(base: str, label: str, kind: str, **kw: Any) -> None:
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base}_{n}"
        taken.add(name)
        fields.append(Field(name, label, kind, **kw))

    roles = {column: role for role, column in entry.schema.roles.items()}
    for c in entry.schema.columns:
        base = _field_name(c.name)
        if c.kind in ("id", "category"):
            add(base, c.name, "dimension")
        elif c.kind in ("integer", "real"):
            role = roles.get(c.name)
            unit = "units" if role == "quantity" else "currency" if role in ("price", "cost") else None
            add(base, c.name, "measure", unit=unit, aggregate="mean" if role in ("price", "cost") else "sum")
        elif c.kind == "time":
            add(base, c.name, "time")
            if c.name in entry.report.times_of_day:
                add(base + "_hour", f"{c.name} (hour)", "dimension")
    description = f"The {entry.origin} data source {entry.name}: one row per line of its file"
    return DatasetInfo(DATASET_PREFIX + entry.name, entry.schema.label, description, tuple(fields))


def _dataset_row(entry: SourceEntry, row: list[Any]) -> tuple[Any, ...]:
    out: list[Any] = []
    for c, value in zip(entry.schema.columns, row, strict=True):
        if c.kind == "text":
            continue
        if c.kind == "time":
            out.append(value.date().isoformat() if value is not None else None)
            if c.name in entry.report.times_of_day:
                out.append(f"{value.hour:02d}" if value is not None else None)
        else:
            out.append(value)
    return tuple(out)


# -- the store ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BundledSource:
    """A file that ships with the framework, read-only, with its declared schema."""

    file: str  # relative to the data directory
    schema: SourceSchema


def _retail_schema(name: str, label: str) -> SourceSchema:
    """The UCI Online Retail II layout of the two bundled files."""
    return SourceSchema(
        name=name,
        label=label,
        columns=(
            ColumnSpec("Invoice", "id"),
            ColumnSpec("StockCode", "id"),
            ColumnSpec("Description", "text"),
            ColumnSpec("Quantity", "integer"),
            ColumnSpec("InvoiceDate", "time", formats=DATE_FORMATS),
            ColumnSpec("Price", "real"),
            ColumnSpec("Customer ID", "id"),
            ColumnSpec("Country", "category"),
        ),
        roles=Roles(time="InvoiceDate", item="StockCode", quantity="Quantity", price="Price"),
    )


BUNDLED = {
    "sample": BundledSource(
        "sample_online_retail_ii.csv", _retail_schema("sample", "Synthetic sample (Online Retail II layout)")
    ),
    "retail-10k": BundledSource(
        "online_retail_ii_2010_10k.csv", _retail_schema("retail-10k", "Online Retail II, 10,000 real rows (Dec 2010)")
    ),
}


class Upload:
    """One file arriving: written to a temporary folder with a byte count, then checked and moved into place."""

    def __init__(self, store: SourceStore, name: str) -> None:
        self._store = store
        self.name = name
        self._dir = store.root / f".upload-{uuid.uuid4().hex}"
        self._dir.mkdir(parents=True)
        self._fh: BinaryIO | None = open(self._dir / "data.csv", "wb")
        self.size = 0

    def write(self, chunk: bytes) -> None:
        """Append ``chunk``; ``SourceTooLarge`` as soon as the upload passes the byte limit."""
        self.size += len(chunk)
        if self.size > self._store.limits.max_bytes:
            raise SourceTooLarge(f"the file is larger than {self._store.limits.max_bytes:,} bytes, the most accepted")
        assert self._fh is not None
        self._fh.write(chunk)

    def commit(self, schema: SourceSchema | None = None) -> SourceEntry:
        """Check the file under ``schema`` (inferred when ``None``) and add it to the store under its name."""
        assert self._fh is not None
        self._fh.close()
        self._fh = None
        path = self._dir / "data.csv"
        if self.size == 0:
            raise ValueError("the file is empty: a CSV needs a header row")
        if schema is None:
            schema = infer_schema(path, name=self.name)
        elif schema.name != self.name:
            raise ValueError(f"the schema is for {schema.name!r}, not {self.name!r}")
        report = check(path, schema, self._store.limits)
        _write_json(self._dir / "schema.json", schema.to_dict())
        _write_json(self._dir / "report.json", report.to_dict())
        with self._store._lock:
            self._store._check_free(self.name)
            self._dir.rename(self._store.root / self.name)
        return self._store.get(self.name)

    def discard(self) -> None:
        """Remove the temporary folder, if the upload was not committed."""
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        shutil.rmtree(self._dir, ignore_errors=True)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class SourceStore:
    """The bundled sources and the user's, one folder per user source under ``root``."""

    def __init__(
        self,
        root: str | Path,
        *,
        bundled: dict[str, tuple[Path, SourceSchema]] | None = None,
        limits: SourceLimits = SourceLimits(),
    ) -> None:
        self.root = Path(root)
        self.limits = limits
        self._bundled = dict(bundled or {})
        self._bundled_reports: dict[str, SourceReport] = {}
        self._lock = threading.Lock()

    # -- reading -----------------------------------------------------------------------------------

    def list(self) -> list[SourceEntry]:
        """Bundled sources first, then the user's, each by name."""
        return [self.get(n) for n in sorted(self._bundled)] + [self.get(n) for n in self._user_names()]

    def get(self, name: str) -> SourceEntry:
        """The source ``name``; ``KeyError`` naming the sources there are."""
        if name in self._bundled:
            path, schema = self._bundled[name]
            with self._lock:
                if name not in self._bundled_reports:
                    self._bundled_reports[name] = check(path, schema, SourceLimits())
                report = self._bundled_reports[name]
            return SourceEntry(schema, report, "bundled", path, path.stat().st_size)
        folder = self.root / name
        if not _NAME.fullmatch(name) or not (folder / "schema.json").is_file():
            raise KeyError(f"no source {name!r}; the sources: {sorted(self._bundled) + self._user_names()}")
        schema = SourceSchema.from_dict(json.loads((folder / "schema.json").read_text(encoding="utf-8")))
        report = SourceReport.from_dict(json.loads((folder / "report.json").read_text(encoding="utf-8")))
        path = folder / "data.csv"
        return SourceEntry(schema, report, "user", path, path.stat().st_size)

    def _user_names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if _NAME.fullmatch(p.name) and (p / "schema.json").is_file())

    def preview(self, name: str, rows: int = PREVIEW_ROWS) -> list[list[str]]:
        """The first ``rows`` rows as the file holds them, one text per cell."""
        entry = self.get(name)
        _, reader, fh = _open_rows(entry.path, entry.schema.delimiter)
        with fh:
            return [cells for _, cells in zip(range(rows), reader)]

    def rows(
        self, name: str, *, columns: list[str] | None = None, limit: int | None = None, seed: int | None = None
    ) -> Table:
        """The source as its dataset (``dataset_info``): at most ``limit`` rows, a uniform sample with ``seed``.

        Without ``seed`` the first ``limit`` rows are returned. ``columns`` keeps only those source columns.
        ``ValueError`` while the schema has problems to settle.
        """
        entry = self._ready(name)
        info = dataset_info(entry)
        rows: list[tuple[Any, ...]] = []
        if limit is None or limit >= entry.report.rows_kept:
            rows = [_dataset_row(entry, r) for r in _iter_kept(entry.path, entry.schema)]
        elif seed is None:
            rows = [_dataset_row(entry, r) for _, r in zip(range(limit), _iter_kept(entry.path, entry.schema))]
        else:
            keep = set(random.Random(seed).sample(range(entry.report.rows_kept), limit))
            rows = [_dataset_row(entry, r) for i, r in enumerate(_iter_kept(entry.path, entry.schema)) if i in keep]
        if columns is not None:
            fields = _fields_of(entry, info, columns)
            idx = [info.fields.index(f) for f in fields]
            info = DatasetInfo(info.name, info.label, info.description, tuple(fields))
            rows = [tuple(r[i] for i in idx) for r in rows]
        return Table(info, rows)

    def orders(self, name: str) -> tuple[list[SKU], list[OutboundOrder]]:
        """The source as canonical entities: one SKU per item and one outbound line per kept row.

        Needs the time and quantity roles; without an item every row is one SKU, ``all``. As in the
        retail adapter, a negative quantity is a return (a cancelled line) and a zero quantity is
        skipped; a real quantity is rounded to whole units. A SKU's unit price is the median
        positive price of its lines (0 without a price role), and its unit cost the median positive
        cost, else 0.6 × the price.
        """
        entry = self._ready(name)
        schema = entry.schema
        if not schema.has_demand:
            raise ValueError(f"source {name} has no demand: declare its time and quantity columns")
        at = {role: _index(schema, column) for role, column in schema.roles.items()}
        orders: list[OutboundOrder] = []
        prices: dict[str, list[float]] = {}
        costs: dict[str, list[float]] = {}
        for i, row in enumerate(_iter_kept(entry.path, schema)):
            item = row[at["item"]] if "item" in at else "all"
            qty = round(row[at["quantity"]])
            if item is None or qty == 0:
                continue
            item = str(item)
            prices.setdefault(item, [])
            costs.setdefault(item, [])
            for role, bucket in (("price", prices), ("cost", costs)):
                value = row[at[role]] if role in at else None
                if value is not None and value > 0:
                    bucket[item].append(float(value))
            orders.append(
                OutboundOrder(
                    order_id=f"{name}-{i}",
                    ts=row[at["time"]],
                    sku_id=item,
                    quantity=abs(qty),
                    channel="ecommerce",
                    priority="standard",
                    status="shipped" if qty > 0 else "cancelled",
                )
            )
        skus = []
        for item in prices:
            price = statistics.median(prices[item]) if prices[item] else 0.0
            cost = statistics.median(costs[item]) if costs[item] else round(price * 0.6, 2)
            skus.append(
                SKU(
                    sku_id=item,
                    name=item,
                    category="unknown",
                    unit_cost=cost,
                    unit_price=price,
                    weight_kg=0.1,
                    volume_m3=0.001,
                    abc_class="?",
                )
            )
        return skus, orders

    def _ready(self, name: str) -> SourceEntry:
        entry = self.get(name)
        if entry.schema.problems:
            raise ValueError(f"source {name} cannot be read yet: " + "; ".join(entry.schema.problems))
        return entry

    # -- changing ----------------------------------------------------------------------------------

    def _check_free(self, name: str) -> None:
        """``SourceConflict`` when ``name`` is taken or reserved, or the store holds its most user sources."""
        check_name(name)
        if name in self._bundled or name in BUNDLED:
            raise SourceConflict(f"{name!r} is the name of a bundled source")
        if (self.root / name).exists():
            raise SourceConflict(f"a source named {name!r} already exists")
        if len(self._user_names()) >= self.limits.max_sources:
            raise SourceConflict(
                f"the store holds {self.limits.max_sources} user sources, the most accepted; remove one first"
            )

    def begin(self, name: str) -> Upload:
        """Start adding a source called ``name``; the name and the room are checked now and again at commit."""
        with self._lock:
            self._check_free(name)
        return Upload(self, name)

    def add(self, source: str | Path | BinaryIO, *, name: str, schema: SourceSchema | None = None) -> SourceEntry:
        """Add the CSV at ``source`` (a path or a binary file) as ``name``; ``schema=None`` infers it."""
        upload = self.begin(name)
        try:
            with open(source, "rb") if isinstance(source, (str, Path)) else nullcontext(source) as fh:
                while chunk := fh.read(_CHUNK):
                    upload.write(chunk)
            return upload.commit(schema)
        finally:
            upload.discard()

    def update_schema(self, name: str, schema: SourceSchema) -> SourceEntry:
        """Replace a user source's schema, after checking every row under it."""
        if name in self._bundled:
            raise SourceConflict(f"{name} is a bundled source and cannot be changed")
        entry = self.get(name)
        if schema.name != name:
            raise ValueError(f"the schema is for {schema.name!r}, not {name!r}")
        report = check(entry.path, schema, self.limits)
        with self._lock:
            _write_json(entry.path.parent / "report.json", report.to_dict())
            _write_json(entry.path.parent / "schema.json", schema.to_dict())
        return self.get(name)

    def remove(self, name: str) -> None:
        """Delete a user source and its folder."""
        if name in self._bundled:
            raise SourceConflict(f"{name} is a bundled source and cannot be removed")
        self.get(name)  # KeyError when there is none
        with self._lock:
            shutil.rmtree(self.root / name)


def _fields_of(entry: SourceEntry, info: DatasetInfo, columns: list[str]) -> list[Field]:
    """The dataset fields of the named source columns (a field's label is its column), a time's hour included."""
    fields = []
    for column in columns:
        if entry.schema.column(column).kind == "text":  # KeyError for an unknown column
            raise ValueError(f"column {column} is text, which is shown but never read as a field")
        fields.extend(f for f in info.fields if f.label in (column, f"{column} (hour)"))
    return fields


def default_store(limits: SourceLimits = SourceLimits()) -> SourceStore:
    """The store of this installation: user sources under ``$SDF_DATA_DIR/sources``, the bundled files beside."""
    folder = data_dir()
    bundled = {name: (folder / b.file, b.schema) for name, b in BUNDLED.items() if (folder / b.file).is_file()}
    return SourceStore(folder / "sources", bundled=bundled, limits=limits)
