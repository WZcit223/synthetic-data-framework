"""The estimator catalogue, and ``score``: every chosen estimator on the same rows, one row each.

Estimators are plug-ins in the ``sdf.estimators`` entry-point group, mounted by the
shared loader (``sdf.foundation.plugins``). The contract is
``docs/refactor/causal/interfaces.md`` §3.1 to §3.3 and §5.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from typing import Any, ClassVar

from sdf.foundation.plugins import PluginRegistry
from sdf.foundation.tables import DatasetInfo, Field, Table
from .core import CausalQuestion, Estimate, Estimator, EstimatorInfo, check_confidence, design, identify

ENTRY_POINT_GROUP = "sdf.estimators"
MAX_ESTIMATE_SECONDS = 30.0  # a request's budget: estimators not started by then are "not run" rows


class EstimatorRegistry(PluginRegistry[Estimator]):
    """Estimators by name; built-ins and plug-ins are mounted from the ``sdf.estimators`` group."""

    kind: ClassVar[str] = "estimator"
    info_type: ClassVar[type] = EstimatorInfo
    group: ClassVar[str] = ENTRY_POINT_GROUP
    made_by: ClassVar[str] = "estimate(name)"

    def check(self, cls: type[Estimator]) -> None:
        if not callable(getattr(cls, "estimate", None)):
            raise TypeError(f"{cls.info.name}: an estimator needs an estimate() method")
        super().check(cls)

    def info(self, name: str) -> EstimatorInfo:
        return self._entry(name).cls.info

    def estimate(
        self, name: str, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7
    ) -> Estimate:
        """Check the question against the table, then run ``name`` on it.

        Raises ``KeyError`` for an unknown or unavailable estimator, ``ValueError`` for a
        question the table cannot answer, a design the estimator cannot identify, a
        confidence outside (0.5, 1) or a result that is not finite, and lets the
        estimator's own exception through (``score`` turns each into a row).

        An Estimate may have no interval (both bounds None): that is a valid result.
        Exactly one bound None is not.
        """
        cls = self._entry(name).cls
        check_confidence(confidence)
        d = design(table, question)
        identify(d, uses_covariates=cls.info.uses_covariates)
        return _checked(name, cls().estimate(table, question, confidence=confidence, seed=seed))


def _checked(name: str, est: Any) -> Estimate:
    """The one test on a result: an Estimate whose effect and bounds are finite (or both bounds absent)."""
    if not isinstance(est, Estimate):
        raise ValueError(f"{name} returned {type(est).__name__}, not an Estimate")
    if est.estimator != name:  # one row per requested name: a result labelled otherwise would break that
        raise ValueError(f"{name} returned an estimate labelled {est.estimator!r}")
    if not _finite(est.effect):
        raise ValueError(f"{name} returned a non-finite effect {est.effect!r}")
    if (est.ci_low is None) != (est.ci_high is None):
        raise ValueError(f"{name} returned one interval bound without the other")
    for bound in (est.ci_low, est.ci_high):
        if bound is not None and not _finite(bound):
            raise ValueError(f"{name} returned a non-finite interval bound {bound!r}")
    return est


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def default_estimators() -> EstimatorRegistry:
    """A registry with the ``sdf.estimators`` group mounted, like ``default_registry()``."""
    reg = EstimatorRegistry()
    reg.load_entry_points()
    return reg


def scores_info(unit: str | None = None) -> DatasetInfo:
    """The ``estimator-scores`` table: one row per estimator; effects in the outcome's ``unit``."""
    return DatasetInfo(
        name="estimator-scores",
        label="Estimator scores",
        description="Each estimator's effect and interval on the same rows, against the true effect when it is known",
        fields=(
            Field("estimator", "Estimator", "dimension"),
            Field("effect", "Estimated effect", "measure", unit=unit, aggregate="mean"),
            Field("ci_low", "Interval low", "measure", unit=unit, aggregate="mean"),
            Field("ci_high", "Interval high", "measure", unit=unit, aggregate="mean"),
            Field("true_effect", "True effect", "measure", unit=unit, aggregate="mean"),
            Field("bias", "Bias", "measure", unit=unit, aggregate="mean"),
            Field("relative_bias", "Relative bias", "measure", unit="share", aggregate="mean"),
            Field("covers", "Interval covers the truth", "dimension"),
            Field("n_treated", "Treated rows", "measure", unit="rows", aggregate="sum"),
            Field("n_control", "Control rows", "measure", unit="rows", aggregate="sum"),
            Field("seconds", "Run time", "measure", unit="s", aggregate="sum"),
            Field("method", "Method", "dimension"),
        ),
    )


SCORES_INFO = scores_info()  # the fields without an outcome unit, for reference


def score(
    table: Table,
    question: CausalQuestion,
    registry: EstimatorRegistry,
    *,
    names: Sequence[str],
    true_effect: float | None = None,
    confidence: float = 0.95,
    seed: int = 7,
    deadline: float | None = None,
) -> Table:
    """Run every estimator in ``names`` on the same rows; one row each, in ``names`` order.

    Raises ``ValueError``, as ``design`` does, when the question cannot be answered at all
    (a request problem), and ``KeyError`` for an unknown name. An estimator that raises,
    that cannot identify the effect with the columns it uses, or that returns a non-finite
    value becomes an error row. ``deadline`` (a ``time.monotonic()`` instant) is checked
    before each estimator: once it has passed, the estimators not yet started are
    "not run" rows (§5).
    """
    check_confidence(confidence)
    if not names:
        raise ValueError("estimators must name at least one")
    repeated = sorted({n for n in names if list(names).count(n) > 1})
    if repeated:
        raise ValueError(f"estimators: each may appear once, repeated {repeated}")
    classes = [registry._entry(n).cls for n in names]  # KeyError, with the unavailable reason, before any run
    d = design(table, question)
    unit = next(f.unit for f in table.info.fields if f.name == question.outcome)
    rows: list[tuple[Any, ...]] = []
    for name, cls in zip(names, classes):
        if deadline is not None and time.monotonic() > deadline:
            rows.append(_error_row(name, f"not run: the request's {MAX_ESTIMATE_SECONDS:g} s were used", None))
            continue
        started = time.monotonic()
        try:
            identify(d, uses_covariates=cls.info.uses_covariates)
            est = _checked(name, cls().estimate(table, question, confidence=confidence, seed=seed))
        except Exception as exc:  # one broken estimator must not hide the others
            rows.append(_error_row(name, _reason(exc), time.monotonic() - started))
            continue
        rows.append(_row(est, true_effect, time.monotonic() - started))
    return Table(scores_info(unit), rows)


def _row(est: Estimate, truth: float | None, seconds: float) -> tuple[Any, ...]:
    bias = relative = covers = None
    if truth is not None:
        bias = est.effect - truth
        relative = bias / truth if truth != 0 else None
        if est.ci_low is not None:
            covers = "yes" if est.ci_low <= truth <= est.ci_high else "no"
    return (
        est.estimator,
        est.effect,
        est.ci_low,
        est.ci_high,
        truth,
        bias,
        relative,
        covers,
        est.n_treated,
        est.n_control,
        round(seconds, 4),
        est.method,
    )


def _error_row(name: str, reason: str, seconds: float | None) -> tuple[Any, ...]:
    return (
        name,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None if seconds is None else round(seconds, 4),
        reason,
    )


def _reason(exc: Exception) -> str:
    text = str(exc) or type(exc).__name__
    return text if isinstance(exc, ValueError) else f"{type(exc).__name__}: {text}"
