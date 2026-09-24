"""The causal question, the estimate, and the shared preparation every estimator starts from.

An estimator answers one question about a table: the average effect of a
treatment on an outcome, adjusting for a declared set of covariates. The set is
the user's claim, never discovered. ``design`` turns the table and the question
into arrays once, with every refusal named, so no estimator re-implements the
missing-value rule or the encoding. The contract is
``docs/refactor/causal/interfaces.md`` §3.1.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

import numpy as np

from sdf.foundation.tables import Field, Table


@dataclass(frozen=True)
class CausalQuestion:
    treatment: str  # a field: a dimension, or a measure holding 0 and 1
    outcome: str  # a measure field
    covariates: tuple[str, ...] = ()  # the adjustment set: the user's claim, not discovered
    # The value that counts as treated (every other value is control): 1 by default for a 0/1
    # measure; for a dimension treatment, a text value the caller must give.
    treated_value: Any = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "treatment": self.treatment,
            "outcome": self.outcome,
            "covariates": list(self.covariates),
            "treated_value": self.treated_value,
        }


@dataclass(frozen=True)
class EstimatorInfo:
    name: str  # lower-case words joined by dashes
    description: str
    requires: tuple[str, ...] = ()  # modules; missing ones list the estimator as unavailable
    uses_covariates: bool = True  # False for an estimator that ignores them, e.g. difference-in-means


@dataclass(frozen=True)
class Estimate:
    estimator: str
    effect: float  # average treatment effect, in the outcome's unit
    ci_low: float | None
    ci_high: float | None
    n_treated: int
    n_control: int
    method: str  # how the interval was made, e.g. "OLS, HC1 errors, 95 %"


class Estimator(Protocol):
    info: ClassVar[EstimatorInfo]

    def estimate(
        self, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7
    ) -> Estimate: ...


@dataclass(frozen=True)
class Design:
    treated: np.ndarray  # bool, one per kept row
    outcome: np.ndarray  # float, one per kept row
    covariates: np.ndarray  # float, 2-D: kept rows × encoded columns (0 columns without covariates)
    columns: tuple[str, ...]  # the encoded columns' names, e.g. ("log_demand", "abc_class=B", "abc_class=C")
    dropped: int  # rows left out for a missing value


def design(table: Table, question: CausalQuestion) -> Design:
    """The question's arrays over the table's complete rows; ``ValueError`` naming what cannot be answered.

    Two checks are not design's, because they need more than the table and the
    question: the confidence level (``check_confidence``), and identification
    (``identify``), which depends on the columns an estimator uses.
    """
    fields = {f.name: f for f in table.info.fields}
    names = [question.treatment, question.outcome, *question.covariates]
    unknown = [n for n in names if n not in fields]
    if unknown:
        raise ValueError(f"unknown field {unknown[0]!r}; {table.info.name} has {sorted(fields)}")
    treatment, outcome = fields[question.treatment], fields[question.outcome]
    if treatment.kind == "time":
        raise ValueError(f"treatment {treatment.name} is a time field; use a dimension or a measure holding 0 and 1")
    if outcome.kind != "measure":
        raise ValueError(f"outcome {outcome.name} is a {outcome.kind}; it must be a measure")
    seen: set[str] = set()
    for c in question.covariates:
        if c == question.treatment:
            raise ValueError(f"covariate {c} is the treatment itself")
        if c == question.outcome:
            raise ValueError(f"covariate {c} is the outcome itself; adjusting for it would leak the outcome")
        if c in seen:
            raise ValueError(f"covariate {c} appears twice")
        seen.add(c)
        if fields[c].kind == "time":
            raise ValueError(f"covariate {c} is a time field; use a dimension or a measure")

    at = {f.name: i for i, f in enumerate(table.info.fields)}
    idx = [at[n] for n in names]
    kept = [r for r in table.rows if all(not _missing(r[i]) for i in idx)]
    dropped = len(table.rows) - len(kept)
    t_values = [r[at[treatment.name]] for r in kept]
    treated = _treated(treatment, t_values, question.treated_value)
    n_treated, n_control = int(treated.sum()), int((~treated).sum())
    if n_treated < 2 or n_control < 2:
        raise ValueError(
            f"needs at least two treated and two control rows; got {n_treated} treated and {n_control} control"
            + (f" ({dropped} rows dropped for a missing value)" if dropped else "")
        )
    y = np.array([float(r[at[outcome.name]]) for r in kept], dtype=float)
    blocks: list[np.ndarray] = []
    columns: list[str] = []
    for c in question.covariates:
        values = [r[at[c]] for r in kept]
        if fields[c].kind == "measure":
            blocks.append(np.array(values, dtype=float).reshape(-1, 1))
            columns.append(c)
            continue
        levels = sorted(set(values))  # the first level present among the kept rows is the one dropped
        for level in levels[1:]:
            blocks.append(np.array([v == level for v in values], dtype=float).reshape(-1, 1))
            columns.append(f"{c}={level}")
    x = np.hstack(blocks) if blocks else np.empty((len(kept), 0))
    return Design(treated=treated, outcome=y, covariates=x, columns=tuple(columns), dropped=dropped)


def _missing(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _treated(field: Field, values: Sequence[Any], treated_value: Any) -> np.ndarray:
    if field.kind == "measure":
        other = sorted({v for v in values if v not in (0, 1)})
        if other:
            raise ValueError(
                f"treatment {field.name} is a measure with values other than 0 and 1 (for example {other[0]!r});"
                " use a 0/1 measure or a dimension"
            )
        if isinstance(treated_value, bool) or treated_value not in (0, 1):
            raise ValueError(
                f"treatment {field.name} holds 0 and 1; treated_value must be 0 or 1, got {treated_value!r}"
            )
        return np.array([v == treated_value for v in values], dtype=bool)
    present = sorted(set(values))
    if not isinstance(treated_value, str) or treated_value not in present:
        raise ValueError(f"{field.name} has values {present}; set treated_value to one of them")
    return np.array([v == treated_value for v in values], dtype=bool)


def check_confidence(confidence: float) -> None:
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(f"confidence must be a number above 0.5 and below 1, got {confidence!r}")
    if not (math.isfinite(confidence) and 0.5 < confidence < 1):
        raise ValueError(f"confidence must be above 0.5 and below 1, got {confidence!r}")


def model_matrix(d: Design, *, uses_covariates: bool) -> tuple[np.ndarray, tuple[str, ...]]:
    """The matrix an estimator fits: an intercept, the treatment and, when it uses them, the covariates."""
    base = np.column_stack([np.ones(len(d.outcome)), d.treated.astype(float)])
    if not uses_covariates or not d.columns:
        return base, ("intercept", "treatment")
    return np.hstack([base, d.covariates]), ("intercept", "treatment", *d.columns)


def identify(d: Design, *, uses_covariates: bool) -> None:
    """Refuse a design that cannot identify the effect: collinear columns, or no residual degree of freedom.

    Kept exactly when ``rank(X) == columns(X)`` and ``rows > columns(X)``, with X the matrix
    the estimator fits (``model_matrix``); the message names the columns of a dependency.
    """
    x, names = model_matrix(d, uses_covariates=uses_covariates)
    rows, cols = x.shape
    if rows <= cols:
        raise ValueError(
            f"not identified: {rows} rows for {cols} columns ({', '.join(names)}) leave no residual degree of freedom"
        )
    if np.linalg.matrix_rank(x) == cols:
        return
    raise ValueError(f"not identified: {_dependency(x, names)}")


def _dependency(x: np.ndarray, names: tuple[str, ...]) -> str:
    """The first column that is an exact linear combination of the columns before it, in words."""
    independent: list[int] = []
    for j in range(x.shape[1]):
        trial = [*independent, j]
        if np.linalg.matrix_rank(x[:, trial]) == len(trial):
            independent.append(j)
            continue
        coef, *_ = np.linalg.lstsq(x[:, independent], x[:, j], rcond=None)
        terms = [(c, names[i]) for c, i in zip(coef, independent) if abs(c) > 1e-9]
        if not terms:
            return f"{names[j]} is always 0"
        if len(terms) == 1:
            c, other = terms[0]
            if other == "intercept":
                return f"{names[j]} is constant ({_num(c)})"
            return f"{names[j]} equals {other}" if abs(c - 1) < 1e-9 else f"{names[j]} is {_num(c)} × {other}"
        return f"{names[j]} is " + " + ".join(f"{_num(c)} × {n}" for c, n in terms)
    return "the columns are collinear"  # matrix_rank said so, but no single column shows it


def _num(c: float) -> str:
    return f"{c:.6g}"
