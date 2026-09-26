"""Run a synthesizer against a sample of real data and score it.

``evaluate`` fits any series or table synthesizer on one of the repository's
sample CSVs (or a CSV path), scores the result with the existing checks
(``fidelity_report`` for a series; for a table, ``privacy_report`` and the detection
test's ``detection_*`` metrics, from ``detection_report``) and returns
the scores with a real-against-synthetic table that a client can pivot. It is
what ``sdf synth``, ``sdf privacy`` and ``POST /api/v1/synthesis/runs`` share.
The scorers keep their algorithm hooks (checklist rows B1, B3 and B4).
"""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field
from typing import Any, Literal

from sdf.foundation.adapters.retail_csv import LoadReport, load_online_retail_csv
from sdf.foundation.sources import (
    BUNDLED,
    DATA_DIR_ENV,
    SourceEntry,
    SourceStore,
    data_dir,
    default_store,
    field_name,
)
from sdf.foundation.tables import DatasetInfo, Field, Table
from sdf.synthesis.api import TableData
from sdf.synthesis.fit import FittedHourlyDemand
from sdf.synthesis.registry import SynthesizerRegistry, default_registry
from .detection import detection_metrics
from .fidelity import fidelity_report
from .privacy import FEATURE_COLUMNS, FEATURE_KINDS, privacy_report, read_retail_feature_table

EVALUATION_SEED = 7  # the seed of a run that leaves a synthesizer's seed out, so every run can be repeated
MAX_TABLE_ROWS = 3000  # rows a table run fits on, as the retail reader reads
RowChoice = Literal["sample", "first"]
SOURCE_HINT = "check the source's roles and kinds (sdf data show)"
DATA_KINDS = ("integer", "real", "category")  # the source column kinds a table synthesizer reads
DERIVED = {"hour": "integer", "weekday": "category"}  # what <time>.hour and <time>.weekday are
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# The repository's sample CSVs (Online Retail II layout), by source ID: the bundled sources. They live in data/.
SOURCE_FILES = {name: b.file for name, b in BUNDLED.items()}

SERIES_FIELDS = (
    Field("step", "Step", "dimension"),
    Field("origin", "Origin", "dimension"),
    Field("value", "Demand", "measure", unit="units"),
)
TABLE_FIELDS = (
    Field("origin", "Origin", "dimension"),
    Field("qty", "Quantity", "measure", unit="units", aggregate="mean"),
    Field("price", "Unit price", "measure", unit="currency", aggregate="mean"),
    Field("hour", "Hour of day", "measure", aggregate="mean"),
    Field("weekday", "Weekday (0 = Monday)", "measure", aggregate="mean"),
)


@dataclass(frozen=True)
class EvaluationRun:
    """One evaluated run: the parameters it used, its scores and the real and synthetic data side by side."""

    synthesizer: str
    source: str
    kind: Literal["series", "table"]
    params: dict[str, Any]  # every parameter used, defaults and the filled-in seed included
    metrics: dict[str, Any]
    table: Table
    repeatable: bool  # True when the synthesizer has a seed: the same params give the same table
    load: LoadReport | None = field(default=None, repr=False, compare=False)  # a series run's CSV load report
    columns: tuple[str, ...] = ()  # a table run on a source: the columns fitted; () for the retail feature table
    rows: RowChoice | None = None  # a table run on a source: how its rows were chosen
    notes: tuple[str, ...] = ()  # what a reader of the scores should know about this run


class RunFailed(RuntimeError):
    """The synthesizer itself failed while being created, fitted or sampled: a fault of the plug-in, not of the request."""


class NoUsableRows(ValueError):
    """The source gave no row to fit on; ``reason`` says why (a load summary, or the scorer's error)."""

    def __init__(
        self,
        path: str,
        reason: str,
        load: LoadReport | None = None,
        *,
        hint: str = "check the file and the date format",
    ) -> None:
        super().__init__(f"{path}: no usable rows ({reason}); {hint}")
        self.path = path
        self.reason = reason
        self.load = load


def evaluate(
    synthesizer: str,
    *,
    source: str,
    params: dict[str, Any] | None = None,
    date_format: str | None = None,
    registry: SynthesizerRegistry | None = None,
    store: SourceStore | None = None,
    columns: list[str] | None = None,
    rows: RowChoice | None = None,
) -> EvaluationRun:
    """Fit ``synthesizer`` on ``source`` (a data source's name, or a CSV path) and score it.

    A bundled source with no ``columns`` and no ``rows``, or a path, is read as it always was:
    the retail feature table, or the retail adapter's orders. Any other source is read through
    its schema (``docs/refactor/userdata/interfaces.md`` §2): a table synthesizer is fitted on
    ``columns`` (default: every integer, real and category column; ``<time>.hour`` and
    ``<time>.weekday`` may be named), at most 3,000 rows, ``rows="sample"`` (the default, a
    uniform sample drawn with the run's seed) or ``"first"``; a series synthesizer on its demand.
    ``store`` is the source store (default: ``default_store()``).

    Raises ``KeyError`` for an unknown or unavailable synthesizer, and
    ``ValueError`` for a warehouse synthesizer, a parameter it does not take or
    whose value it refuses, an unknown source or column, or a source with no usable row:
    all problems of the request. ``RunFailed`` means the synthesizer's own code
    raised while it was created, fitted or sampled.
    """
    reg = registry if registry is not None else default_registry()
    info = reg.info(synthesizer)
    if info.produces == "warehouse":
        raise ValueError(f"{synthesizer} produces a warehouse; choose it for the world instead")
    declared = {p.name: p for p in reg.params(synthesizer)}
    given = dict(params or {})
    unknown = sorted(set(given) - set(declared))
    if unknown:
        raise ValueError(f"{synthesizer} takes no parameter {unknown}; it takes {sorted(declared)}")
    for name, value in given.items():
        problem = declared[name].check(value)
        if problem:
            raise ValueError(f"{synthesizer}: {name} {problem}")
    used = {name: given.get(name, p.default) for name, p in declared.items()}
    repeatable = "seed" in declared
    if repeatable and used["seed"] is None:
        used["seed"] = EVALUATION_SEED
    for name, value in used.items():  # the values the synthesizer gets, defaults included
        problem = declared[name].check(value)
        if problem:
            raise ValueError(f"{synthesizer}: {name} {problem}")
    store = store if store is not None else default_store()
    if rows not in (None, "sample", "first"):
        raise ValueError(f"rows is 'sample' or 'first', got {rows!r}")
    path, entry = _resolve(source, store, choice=columns is not None or rows is not None)
    if entry is not None and info.produces == "series" and (columns is not None or rows is not None):
        raise ValueError("a series synthesizer is fitted on the source's demand; columns and rows are for tables")
    seed = used["seed"] if repeatable else EVALUATION_SEED
    # the source is read before the synthesizer is created: a bad column or a source without demand is ours
    if entry is not None and info.produces == "table":
        data, fields, decode, notes = _source_table(store, entry, columns, rows or "sample", seed)
    if entry is not None and info.produces == "series":
        orders = _source_orders(store, entry)
    model = _run(synthesizer, "creating it", lambda: reg.create(synthesizer, **used))

    if entry is not None and info.produces == "series":
        fitted = _run(synthesizer, "fitting it", lambda: FittedHourlyDemand(model).fit(orders))
        if not fitted.real_series:
            raise NoUsableRows(source, "no demand left after removing cancelled lines", hint=SOURCE_HINT)
        synth = _run(synthesizer, "sampling from it", fitted.generate)
        metrics = fidelity_report(fitted.real_series, synth, fitted.ppd)
        series_rows = [(str(i), "real", round(v, 4)) for i, v in enumerate(fitted.real_series)]
        series_rows += [(str(i), "synthetic", round(v, 4)) for i, v in enumerate(synth)]
        table = Table(_info(synthesizer, "series", SERIES_FIELDS), series_rows)
        return EvaluationRun(synthesizer, source, "series", used, metrics, table, repeatable)

    if entry is not None:  # a table run on a source
        synth_rows = _run(synthesizer, "fitting and sampling it", lambda: model.fit(data).sample())
        _check_width(synthesizer, synth_rows, data.columns)
        metrics = privacy_report(data.rows, synth_rows)
        if "error" in metrics:
            raise NoUsableRows(source, metrics["error"], hint=SOURCE_HINT)
        metrics |= detection_metrics(data.rows, synth_rows, columns=data.columns)
        table_rows = [("real", *decode(r)) for r in data.rows] + [("synthetic", *decode(r)) for r in synth_rows]
        table = Table(_info(synthesizer, "table", fields), table_rows)
        choice = rows or "sample"
        return EvaluationRun(
            synthesizer, source, "table", used, metrics, table, repeatable, None, data.columns, choice, notes
        )

    if info.produces == "series":
        _skus, orders, load = load_online_retail_csv(path, date_format=date_format)
        if not load.rows_kept:
            raise NoUsableRows(path, load.summary(), load)
        fitted = _run(synthesizer, "fitting it", lambda: FittedHourlyDemand(model).fit(orders))
        if not fitted.real_series:  # the fit keeps demand only: a file of returns or cancellations has none
            raise NoUsableRows(path, f"{load.summary()}; no demand left after removing cancelled lines", load)
        synth = _run(synthesizer, "sampling from it", fitted.generate)
        metrics = fidelity_report(fitted.real_series, synth, fitted.ppd)
        series_rows = [(str(i), "real", round(v, 4)) for i, v in enumerate(fitted.real_series)]
        series_rows += [(str(i), "synthetic", round(v, 4)) for i, v in enumerate(synth)]
        table = Table(_info(synthesizer, "series", SERIES_FIELDS), series_rows)
        return EvaluationRun(synthesizer, source, "series", used, metrics, table, repeatable, load)

    real = read_retail_feature_table(path, date_format=date_format)
    synth_rows = (
        _run(
            synthesizer,
            "fitting and sampling it",
            lambda: model.fit(TableData(rows=real, columns=FEATURE_COLUMNS, kinds=FEATURE_KINDS)).sample(),
        )
        if real
        else []
    )
    _check_width(synthesizer, synth_rows, FEATURE_COLUMNS)
    metrics = privacy_report(real, synth_rows)
    if "error" in metrics:
        raise NoUsableRows(path, metrics["error"])
    metrics |= detection_metrics(real, synth_rows, columns=FEATURE_COLUMNS)
    table_rows = [("real", *(round(float(v), 4) for v in r)) for r in real]
    table_rows += [("synthetic", *(round(float(v), 4) for v in r)) for r in synth_rows]
    table = Table(_info(synthesizer, "table", TABLE_FIELDS), table_rows)
    return EvaluationRun(synthesizer, source, "table", used, metrics, table, repeatable)


def _run(synthesizer: str, step: str, call):
    """``call()``; an exception from the synthesizer's code becomes ``RunFailed``, so it never reads as a bad request."""
    try:
        return call()
    except Exception as exc:
        raise RunFailed(f"{synthesizer} failed while {step}: {type(exc).__name__}: {exc}") from exc


def _check_width(synthesizer: str, synth_rows: list, columns: tuple[str, ...]) -> None:
    """``RunFailed`` unless every sampled row has one finite number per column: the synthesizer's fault, not ours."""
    for row in synth_rows:
        if len(row) != len(columns):
            raise RunFailed(
                f"{synthesizer} failed while sampling from it: a row of {len(row)} values, "
                f"not one per column {list(columns)}"
            )
        for column, v in zip(columns, row, strict=True):
            try:
                ok = math.isfinite(float(v)) and not isinstance(v, (bool, str))
            except (TypeError, ValueError):
                ok = False
            if not ok:
                raise RunFailed(f"{synthesizer} failed while sampling from it: {column} = {v!r}, not a finite number")


def _resolve(source: str, store: SourceStore, *, choice: bool) -> tuple[str | None, SourceEntry | None]:
    """``(path, None)`` for a file read as it always was, or ``(None, entry)`` for a source read by its schema.

    A bundled source is read as its file unless a column or row ``choice`` is made.
    """
    try:
        entry = store.get(source)
    except KeyError:
        entry = None
    if entry is not None:
        if entry.schema.problems:
            raise ValueError(f"source {source} cannot be read yet: " + "; ".join(entry.schema.problems))
        return (str(entry.path), None) if entry.origin == "bundled" and not choice else (None, entry)
    if source in SOURCE_FILES:
        raise ValueError(
            f"source {source!r} is not available: {data_dir() / SOURCE_FILES[source]} does not exist "
            f"(set {DATA_DIR_ENV} to the folder that holds it)"
        )
    if os.path.isfile(source):
        if choice:
            raise ValueError(f"{source}: a column or row choice needs a source (sdf data add), not a file path")
        return source, None
    names = [e.name for e in store.list() if not e.schema.problems]
    raise ValueError(f"unknown source {source!r}; choose from {names} or give a CSV path")


def derived_columns(entry: SourceEntry) -> list[str]:
    """The columns a table run may derive from the time role: its weekday, and its hour when it holds times."""
    time = entry.schema.roles.time
    if time is None:
        return []
    return ([f"{time}.hour"] if time in entry.report.times_of_day else []) + [f"{time}.weekday"]


def _source_orders(store: SourceStore, entry: SourceEntry) -> list:
    """The orders a series synthesizer is fitted on; ``ValueError`` when the source has no hourly demand."""
    schema = entry.schema
    if not schema.has_demand:
        raise ValueError(f"source {entry.name} has no demand: declare its time and quantity columns")
    if schema.roles.time not in entry.report.times_of_day:
        raise ValueError(
            f"source {entry.name}: its time column {schema.roles.time} holds dates without times of day; "
            "a series synthesizer is fitted on hourly demand"
        )
    return store.orders(entry.name)[1]


def _source_table(
    store: SourceStore, entry: SourceEntry, columns: list[str] | None, choice: RowChoice, seed: int
) -> tuple[TableData, tuple[Field, ...], Any, tuple[str, ...]]:
    """A source's rows as a synthesizer's table: the data, the run table's fields, a decoder, and the notes.

    Categories are coded 0, 1, … from the most frequent label down (ties in first-seen order); the
    decoder turns a row of codes back into labels, a synthetic code rounded (halves up) and clipped to a
    label. A sampled row is checked to hold finite numbers before it is decoded.
    """
    schema = entry.schema
    time = schema.roles.time
    names = [c.name for c in schema.columns]
    chosen = list(columns) if columns is not None else [c.name for c in schema.columns if c.kind in DATA_KINDS]
    if not chosen:
        raise ValueError(f"source {entry.name} has no integer, real or category column; name the columns to fit")
    if len(set(chosen)) != len(chosen):
        raise ValueError(f"a column is named twice in {chosen}")
    specs = []  # (column, kind, index in the schema, derived part or None)
    for col in chosen:
        base, _, part = col.rpartition(".")
        if col not in names and time is not None and base == time and part in DERIVED:
            if part == "hour" and time not in entry.report.times_of_day:
                raise ValueError(f"{col}: the time column {time} holds dates without times of day")
            specs.append((col, DERIVED[part], names.index(time), part))
            continue
        if col not in names:
            derived = f" (and {', '.join(derived_columns(entry))})" if derived_columns(entry) else ""
            raise ValueError(f"source {entry.name} has no column {col!r}; its columns: {names}{derived}")
        kind = schema.column(col).kind
        if kind not in DATA_KINDS:
            raise ValueError(f"column {col} is {kind}; a table synthesizer reads integer, real and category columns")
        specs.append((col, kind, names.index(col), None))
    positive = {
        i
        for i, (col, _, _, part) in enumerate(specs)
        if part is None and col in (schema.roles.quantity, schema.roles.price)
    }

    def value(row: list[Any], spec: tuple) -> Any:
        v = row[spec[2]]
        if v is None or spec[3] is None:
            return v
        return v.hour if spec[3] == "hour" else WEEKDAYS[v.weekday()]

    picked: list[tuple[int, list[Any]]] = []
    rng = random.Random(seed)
    usable = 0
    for row in store.records(entry.name):
        values = [value(row, spec) for spec in specs]
        if any(v is None for v in values) or any(values[i] <= 0 for i in positive):
            continue
        usable += 1
        if len(picked) < MAX_TABLE_ROWS:
            picked.append((usable, values))
        elif choice == "sample":  # reservoir sampling: every usable row equally likely
            k = rng.randrange(usable)
            if k < MAX_TABLE_ROWS:
                picked[k] = (usable, values)
        else:
            break
    if not picked:
        raise NoUsableRows(
            entry.name, "no row has every chosen column, with a positive quantity and price", hint=SOURCE_HINT
        )
    picked.sort(key=lambda p: p[0])  # the file's order
    rows_in = [values for _, values in picked]

    labels: list[list[str] | None] = []
    for i, (_, kind, _, _) in enumerate(specs):
        if kind != "category":
            labels.append(None)
            continue
        counts: dict[str, int] = {}
        for r in rows_in:
            counts[str(r[i])] = counts.get(str(r[i]), 0) + 1
        order = list(counts)  # first seen
        labels.append(sorted(order, key=lambda lab: (-counts[lab], order.index(lab))))
    codes = [{lab: float(k) for k, lab in enumerate(ls)} if ls else None for ls in labels]
    data = TableData(
        rows=[tuple(codes[i][str(v)] if codes[i] else float(v) for i, v in enumerate(r)) for r in rows_in],
        columns=tuple(col for col, *_ in specs),
        kinds=tuple(kind for _, kind, *_ in specs),
    )

    def decode(row: tuple[float, ...]) -> tuple[Any, ...]:
        out: list[Any] = []
        for v, ls in zip(row, labels, strict=True):
            if ls is None:
                out.append(round(float(v), 4))
            else:
                out.append(ls[min(max(math.floor(v + 0.5), 0), len(ls) - 1)])  # the nearest code, halves up
        return tuple(out)

    roles = {column: role for role, column in schema.roles.items()}
    taken = {"origin"}
    fields = [Field("origin", "Origin", "dimension")]
    for col, kind, _, part in specs:
        base = field_name(time) + "_" + part if part else field_name(col)
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base}_{n}"
        taken.add(name)
        if kind == "category":
            fields.append(Field(name, col, "dimension"))
        else:
            role = roles.get(col) if part is None else None
            unit = "units" if role == "quantity" else "currency" if role in ("price", "cost") else None
            fields.append(Field(name, col, "measure", unit=unit, aggregate="mean"))
    notes = tuple(
        f"{spec[0]}: its {len(ls)} labels are coded 0 to {len(ls) - 1}, most frequent first; the privacy and "
        "detection distances, and synthesizers that read numbers (such as the Gaussian copula), treat the "
        "codes as ordered"
        for spec, ls in zip(specs, labels, strict=True)
        if ls is not None and len(ls) > 2
    )
    return data, tuple(fields), decode, notes


def _info(synthesizer: str, kind: str, fields: tuple[Field, ...]) -> DatasetInfo:
    what = "demand series" if kind == "series" else "feature table"
    return DatasetInfo(
        name=f"run-{synthesizer}",
        label=f"{synthesizer}: real and synthetic",
        description=f"The real {what} and the one {synthesizer} generated from it, told apart by origin.",
        fields=fields,
    )
