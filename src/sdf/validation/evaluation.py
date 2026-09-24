"""Run a synthesizer against a sample of real data and score it.

``evaluate`` fits any series or table synthesizer on one of the repository's
sample CSVs (or a CSV path), scores the result with the existing checks
(``fidelity_report`` for a series, ``privacy_report`` for a table) and returns
the scores with a real-against-synthetic table that a client can pivot. It is
what ``sdf synth``, ``sdf privacy`` and ``POST /api/v1/synthesis/runs`` share.
The scorers keep their algorithm hooks (checklist rows B1 and B3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sdf.foundation.adapters.retail_csv import LoadReport, load_online_retail_csv
from sdf.foundation.tables import DatasetInfo, Field, Table
from sdf.synthesis.api import TableData
from sdf.synthesis.fit import FittedHourlyDemand
from sdf.synthesis.registry import SynthesizerRegistry, default_registry
from .fidelity import fidelity_report
from .privacy import FEATURE_COLUMNS, privacy_report, read_retail_feature_table

EVALUATION_SEED = 7  # the seed of a run that leaves a synthesizer's seed out, so every run can be repeated
DATA_DIR_ENV = "SDF_DATA_DIR"
# The repository's sample CSVs (Online Retail II layout), by source ID. They live in data/, not in the package.
SOURCE_FILES = {"sample": "sample_online_retail_ii.csv", "retail-10k": "online_retail_ii_2010_10k.csv"}

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


class NoUsableRows(ValueError):
    """The source gave no row to fit on; ``reason`` says why (a load summary, or the scorer's error)."""

    def __init__(self, path: str, reason: str, load: LoadReport | None = None) -> None:
        super().__init__(f"{path}: no usable rows ({reason}); check the file and the date format")
        self.path = path
        self.reason = reason
        self.load = load


def data_dir() -> Path:
    """Where the sample CSVs are read from: ``$SDF_DATA_DIR``, default ``./data``."""
    return Path(os.environ.get(DATA_DIR_ENV) or "data")


def sources() -> dict[str, str]:
    """The sample sources that exist, by ID: ``{'sample': 'data/sample_online_retail_ii.csv', …}``."""
    folder = data_dir()
    return {sid: str(folder / name) for sid, name in SOURCE_FILES.items() if (folder / name).is_file()}


def evaluate(
    synthesizer: str,
    *,
    source: str,
    params: dict[str, Any] | None = None,
    date_format: str | None = None,
    registry: SynthesizerRegistry | None = None,
) -> EvaluationRun:
    """Fit ``synthesizer`` on ``source`` (a source ID or a CSV path) and score it.

    Raises ``KeyError`` for an unknown or unavailable synthesizer, and
    ``ValueError`` for a warehouse synthesizer, a parameter it does not take or
    whose value it refuses, an unknown source, or a source with no usable row.
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
    path = _resolve(source)
    model = reg.create(synthesizer, **used)

    if info.produces == "series":
        _skus, orders, load = load_online_retail_csv(path, date_format=date_format)
        if not load.rows_kept:
            raise NoUsableRows(path, load.summary(), load)
        fitted = FittedHourlyDemand(model).fit(orders)
        synth = fitted.generate()
        metrics = fidelity_report(fitted.real_series, synth, fitted.ppd)
        rows = [(str(i), "real", round(v, 4)) for i, v in enumerate(fitted.real_series)]
        rows += [(str(i), "synthetic", round(v, 4)) for i, v in enumerate(synth)]
        table = Table(_info(synthesizer, "series", SERIES_FIELDS), rows)
        return EvaluationRun(synthesizer, source, "series", used, metrics, table, repeatable, load)

    real = read_retail_feature_table(path, date_format=date_format)
    synth_rows = model.fit(TableData(rows=real, columns=FEATURE_COLUMNS)).sample() if real else []
    metrics = privacy_report(real, synth_rows)
    if "error" in metrics:
        raise NoUsableRows(path, metrics["error"])
    rows = [("real", *(round(float(v), 4) for v in r)) for r in real]
    rows += [("synthetic", *(round(float(v), 4) for v in r)) for r in synth_rows]
    table = Table(_info(synthesizer, "table", TABLE_FIELDS), rows)
    return EvaluationRun(synthesizer, source, "table", used, metrics, table, repeatable)


def _resolve(source: str) -> str:
    listed = sources()
    if source in listed:
        return listed[source]
    if source in SOURCE_FILES:
        raise ValueError(
            f"source {source!r} is not available: {data_dir() / SOURCE_FILES[source]} does not exist "
            f"(set {DATA_DIR_ENV} to the folder that holds it)"
        )
    if os.path.isfile(source):
        return source
    raise ValueError(f"unknown source {source!r}; choose from {sorted(listed)} or give a CSV path")


def _info(synthesizer: str, kind: str, fields: tuple[Field, ...]) -> DatasetInfo:
    what = "demand series" if kind == "series" else "feature table"
    return DatasetInfo(
        name=f"run-{synthesizer}",
        label=f"{synthesizer}: real and synthetic",
        description=f"The real {what} and the one {synthesizer} generated from it, told apart by origin.",
        fields=fields,
    )
