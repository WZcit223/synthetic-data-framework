"""Causal estimation: the question's refusals, identification, the built-ins on closed-form cases, and score."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from typing import ClassVar

import numpy as np
import pytest
from scipy import stats

from sdf.foundation.tables import DatasetInfo, Field, Table
from . import CausalQuestion, Estimate, EstimatorInfo, EstimatorRegistry, default_estimators, design, score, scores_info
from .builtin import DifferenceInMeans, Ipw, RegressionAdjustment


def table(columns: dict[str, list], kinds: dict[str, str] | None = None, units: dict[str, str] | None = None) -> Table:
    """A table from columns; kinds default to measure, except text columns, which are dimensions."""
    kinds = kinds or {}
    fields = []
    for name, values in columns.items():
        kind = kinds.get(name) or ("dimension" if any(isinstance(v, str) for v in values) else "measure")
        unit = (units or {}).get(name) if kind == "measure" else None
        fields.append(Field(name, name, kind, unit=unit))
    rows = list(zip(*columns.values()))
    return Table(DatasetInfo("test-table", "Test", "a test table", tuple(fields)), rows)


def registry(*classes) -> EstimatorRegistry:
    reg = EstimatorRegistry()
    for cls in classes or (DifferenceInMeans, RegressionAdjustment, Ipw):
        reg.register(cls)
    return reg


Q = CausalQuestion("t", "y")


# -- the built-ins on closed-form cases ------------------------------------------------------------


def test_difference_in_means_is_the_difference_with_welch_s_interval():
    tab = table({"t": [1, 1, 1, 0, 0, 0, 0], "y": [5.0, 7.0, 9.0, 1.0, 3.0, 2.0, 6.0]})
    est = registry().estimate("difference-in-means", tab, Q, confidence=0.9)
    assert est.effect == pytest.approx(7 - 3)
    welch = stats.ttest_ind([5.0, 7.0, 9.0], [1.0, 3.0, 2.0, 6.0], equal_var=False).confidence_interval(0.9)
    assert (est.ci_low, est.ci_high) == (pytest.approx(welch.low), pytest.approx(welch.high))
    assert (est.n_treated, est.n_control, est.method) == (3, 4, "Welch t, 90 %")


def test_regression_adjustment_recovers_a_linear_outcome_exactly():
    x = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 1.5, 2.5]
    t = [1, 0, 1, 0, 1, 0, 0, 1]
    y = [2 + 3 * ti + 1.5 * xi for ti, xi in zip(t, x)]  # confounded: no noise, so OLS is exact
    est = registry().estimate(
        "regression-adjustment", table({"t": t, "y": y, "x": x}), CausalQuestion("t", "y", ("x",))
    )
    assert est.effect == pytest.approx(3.0)
    assert est.ci_high - est.ci_low == pytest.approx(0.0, abs=1e-9)
    assert est.method == "OLS, HC1 errors, 95 %"


def test_regression_adjustment_s_hc1_errors_without_covariates():
    y1, y0 = np.array([5.0, 7.0, 9.0, 4.0]), np.array([1.0, 3.0, 2.0, 6.0, 5.0])
    tab = table({"t": [1] * 4 + [0] * 5, "y": [*y1, *y0]})
    est = registry().estimate("regression-adjustment", tab, Q)
    n, p = 9, 2  # with only the treatment, OLS is the difference in means and HC0 its unpooled variance
    hc0 = y1.var() / len(y1) + y0.var() / len(y0)
    half = stats.t.ppf(0.975, n - p) * math.sqrt(hc0 * n / (n - p))
    assert est.effect == pytest.approx(y1.mean() - y0.mean())
    assert (est.ci_low, est.ci_high) == (pytest.approx(est.effect - half), pytest.approx(est.effect + half))


def test_ipw_with_balanced_propensities_is_the_difference_in_means():
    x = [0.0, 1.0, 2.0, 3.0] * 4  # the same covariate values in both groups: every propensity is 1/2
    t = [1] * 8 + [0] * 8
    y = [4.0, 6.0, 5.0, 9.0, 3.0, 7.0, 8.0, 2.0, 1.0, 2.0, 0.5, 3.0, 2.5, 1.5, 0.0, 4.0]
    tab = table({"t": t, "y": y, "x": x})
    q = CausalQuestion("t", "y", ("x",))
    ipw = registry().estimate("ipw", tab, q)
    assert ipw.effect == pytest.approx(registry().estimate("difference-in-means", tab, q).effect, abs=1e-6)
    assert ipw.method == "Hajek IPW, logistic propensity, 200 bootstrap resamples, 95 %"


def test_ipw_s_bootstrap_is_seeded():
    rng = np.random.default_rng(3)
    x = rng.normal(size=120)
    t = (rng.random(120) < 1 / (1 + np.exp(-x))).astype(int)
    y = 2 * t + x + rng.normal(size=120)
    tab = table({"t": t.tolist(), "y": y.tolist(), "x": x.tolist()})
    q = CausalQuestion("t", "y", ("x",))
    reg = registry()
    a, b, c = (reg.estimate("ipw", tab, q, seed=s) for s in (1, 1, 2))
    assert (a.ci_low, a.ci_high) == (b.ci_low, b.ci_high)
    assert (a.ci_low, a.ci_high) != (c.ci_low, c.ci_high)
    assert a.effect == c.effect  # the point estimate does not resample


def test_ipw_refuses_no_overlap_and_clips_a_few_extreme_propensities():
    reg = registry()
    separated = table({"t": [1] * 10 + [0] * 10, "y": list(range(20)), "x": [float(i) for i in range(20)]})
    rows = score(separated, CausalQuestion("t", "y", ("x",)), reg, names=["ipw", "difference-in-means"]).rows
    assert (
        rows[0][1] is None
        and rows[0][11].startswith("no overlap: ")
        and "of 20 rows have a propensity outside" in rows[0][11]
    )
    assert rows[1][1] is not None  # the naive estimate still arrives
    # 4 of 100 rows at an extreme covariate, all treated: their propensities pass 0.99 and are clipped
    rng = np.random.default_rng(1)
    bulk = rng.normal(size=96)
    x = [*bulk.tolist(), 6.0, 6.0, 6.0, 6.0]
    t = [*(rng.random(96) < 1 / (1 + np.exp(-bulk))).astype(int).tolist(), 1, 1, 1, 1]
    y = [float(v) for v in range(100)]
    est = reg.estimate("ipw", table({"t": t, "y": y, "x": x}), CausalQuestion("t", "y", ("x",)))
    assert est.method.endswith(", 4 rows clipped")


# -- design: the rows, the encoding and every refusal ------------------------------------------------


def test_design_drops_rows_with_a_missing_value_and_encodes_dimensions():
    tab = table(
        {
            "t": [1, 0, 1, 0, None, 1, 0],
            "y": [1.0, 2.0, None, 4.0, 5.0, 6.0, 7.0],
            "cls": ["B", "C", "A", "B", "A", "C", "B"],  # "A" is only in dropped rows: B is the first level kept
            "x": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
        }
    )
    d = design(tab, CausalQuestion("t", "y", ("cls", "x")))
    assert d.dropped == 2
    assert d.columns == ("cls=C", "x")
    assert d.treated.tolist() == [True, False, False, True, False]
    assert d.covariates[:, 0].tolist() == [0.0, 1.0, 0.0, 1.0, 0.0]
    assert d.outcome.tolist() == [1.0, 2.0, 4.0, 6.0, 7.0]
    assert design(tab, CausalQuestion("t", "y")).covariates.shape == (5, 0)
    # the first level the kept rows present is the one dropped, not the first in sort order
    later = table({"t": [1, 0, 1, 0], "y": [1.0, 2.0, 3.0, 4.0], "cls": ["C", "B", "B", "A"]})
    assert design(later, CausalQuestion("t", "y", ("cls",))).columns == ("cls=B", "cls=A")


def refusal(tab, question):
    with pytest.raises(ValueError) as exc:
        design(tab, question)
    return str(exc.value)


BASE = {"t": [1, 1, 0, 0, 1, 0], "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "x": [1.0, 2.0, 2.0, 3.0, 5.0, 1.0]}


def test_design_refuses_a_treatment_it_cannot_read():
    dated = table({**BASE, "d": ["2025-01-01"] * 6}, kinds={"d": "time"})
    assert (
        refusal(dated, CausalQuestion("d", "y"))
        == "treatment d is a time field; use a dimension or a measure holding 0 and 1"
    )
    three = table({**BASE, "t": [1, 2, 0, 0, 1, 0]})
    assert "measure with values other than 0 and 1 (for example 2)" in refusal(three, Q)
    prio = table({**BASE, "p": ["express", "standard", "express", "standard", "express", "standard"]})
    expected = "p has values ['express', 'standard']; set treated_value to one of them"
    assert refusal(prio, CausalQuestion("p", "y")) == expected  # the default 1 is never read as all-control
    assert refusal(prio, CausalQuestion("p", "y", treated_value="urgent")) == expected
    assert "treated_value must be 0 or 1" in refusal(table(BASE), CausalQuestion("t", "y", treated_value="yes"))
    assert design(prio, CausalQuestion("p", "y", treated_value="express")).treated.sum() == 3


def test_design_refuses_questions_about_the_wrong_fields():
    tab = table({**BASE, "d": ["2025-01-01"] * 6, "c": list("abcabc")}, kinds={"d": "time"})
    assert refusal(tab, CausalQuestion("t", "nope")).startswith("unknown field 'nope'; test-table has ")
    assert refusal(tab, CausalQuestion("t", "c")) == "outcome c is a dimension; it must be a measure"
    assert (
        refusal(tab, CausalQuestion("t", "t")) == "t is both the treatment and the outcome; an effect needs two fields"
    )
    assert refusal(tab, CausalQuestion("t", "y", ("d",))) == "covariate d is a time field; use a dimension or a measure"
    assert refusal(tab, CausalQuestion("t", "y", ("t",))) == "covariate t is the treatment itself"
    assert "covariate y is the outcome itself" in refusal(tab, CausalQuestion("t", "y", ("y",)))
    assert refusal(tab, CausalQuestion("t", "y", ("x", "x"))) == "covariate x appears twice"
    few = table({"t": [1, 0, 0, 0], "y": [1.0, 2.0, 3.0, 4.0]})
    assert refusal(few, Q) == "needs at least two treated and two control rows; got 1 treated and 3 control"


@pytest.mark.parametrize("confidence", [0.5, 1, 1.0, float("nan"), True])
def test_a_confidence_outside_the_open_interval_is_refused(confidence):
    with pytest.raises(ValueError, match="confidence must be"):
        registry().estimate("difference-in-means", table(BASE), Q, confidence=confidence)
    with pytest.raises(ValueError, match="confidence must be"):
        score(table(BASE), Q, registry(), names=["difference-in-means"], confidence=confidence)


# -- identification ---------------------------------------------------------------------------------


def not_identified(tab, question, name="regression-adjustment"):
    with pytest.raises(ValueError, match="^not identified: ") as exc:
        registry().estimate(name, tab, question)
    return str(exc.value).removeprefix("not identified: ")


def test_a_rank_deficient_design_is_refused_naming_the_dependency():
    x = [1.0, 2.0, 2.0, 3.0, 5.0, 1.0, 4.0, 2.5]
    base = {"t": [1, 1, 0, 0, 1, 0, 1, 0], "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], "x": x}
    copy = table({**base, "x_copy": list(x)})
    assert not_identified(copy, CausalQuestion("t", "y", ("x", "x_copy"))) == "x_copy equals x"
    double = table({**base, "log_units": list(x), "log_demand": [2 * v for v in x]})
    assert (
        not_identified(double, CausalQuestion("t", "y", ("log_units", "log_demand"))) == "log_demand is 2 × log_units"
    )
    constant = table({**base, "k": [4.0] * 8})
    assert not_identified(constant, CausalQuestion("t", "y", ("k",))) == "k is constant (4)"
    # a measure that is the indicator of level A: with the intercept, the dummy for B is 1 − it
    cls = ["A", "B", "A", "B", "B", "A", "B", "A"]
    dummies = table({**base, "cls": cls, "is_a": [1.0 if c == "A" else 0.0 for c in cls]})
    assert not_identified(dummies, CausalQuestion("t", "y", ("cls", "is_a"))) == "is_a is 1 × intercept + -1 × cls=B"


def test_a_covariate_constant_within_one_group_but_varying_in_the_other_is_kept():
    tab = table({"t": [1, 1, 1, 0, 0, 0], "y": [3.0, 4.0, 5.0, 1.0, 2.0, 2.5], "x": [2.0, 2.0, 2.0, 1.0, 3.0, 0.5]})
    assert registry().estimate("regression-adjustment", tab, CausalQuestion("t", "y", ("x",))).effect is not None


def test_no_residual_degree_of_freedom_is_refused():
    tab = table({"t": [1, 1, 0, 0], "y": [1.0, 2.0, 3.0, 5.0], "a": [1.0, 2.0, 4.0, 3.0], "b": [3.0, 1.0, 2.0, 7.0]})
    assert not_identified(tab, CausalQuestion("t", "y", ("a", "b"))) == (
        "4 rows for 4 columns (intercept, treatment, a, b) leave no residual degree of freedom"
    )


def test_redundant_covariates_do_not_refuse_an_estimator_that_ignores_them():
    x = [1.0, 2.0, 2.0, 3.0, 5.0, 1.0]
    tab = table({**BASE, "x": x, "x_copy": list(x)})
    q = CausalQuestion("t", "y", ("x", "x_copy"))
    reg = registry()
    assert reg.estimate("difference-in-means", tab, q).effect == pytest.approx(8 / 3 - 13 / 3)
    rows = score(tab, q, reg, names=["difference-in-means", "regression-adjustment"]).rows
    assert rows[0][1] == pytest.approx(8 / 3 - 13 / 3)
    assert rows[1][1] is None and rows[1][11] == "not identified: x_copy equals x"


# -- the registry's guard and score ------------------------------------------------------------------


@dataclass
class Returns:
    """An estimator that returns whatever it is told to."""

    effect: float = 1.0
    low: float | None = 0.0
    high: float | None = 2.0

    def estimate(self, table, question, *, confidence=0.95, seed=7):
        return Estimate(self.info.name, self.effect, self.low, self.high, 2, 2, "told")


def returning(name, **values):
    return type(
        name.title().replace("-", ""),
        (Returns,),
        {"info": EstimatorInfo(name, "returns"), "__init__": lambda self: Returns.__init__(self, **values)},
    )


class Mislabelled:
    info: ClassVar[EstimatorInfo] = EstimatorInfo("mislabelled", "answers under another name")

    def estimate(self, table, question, *, confidence=0.95, seed=7):
        return Estimate("someone-else", 1.0, 0.0, 2.0, 2, 2, "told")


class Raises:
    info: ClassVar[EstimatorInfo] = EstimatorInfo("raises", "always fails")

    def estimate(self, table, question, *, confidence=0.95, seed=7):
        raise RuntimeError("library error")


def test_a_non_finite_result_or_a_lone_bound_becomes_an_error_row():
    reg = registry(
        returning("nan-effect", effect=float("nan")),
        returning("inf-bound", high=float("inf")),
        returning("one-bound", high=None),
        returning("no-interval", low=None, high=None),
        Raises,
        Mislabelled,
    )
    names = ["nan-effect", "inf-bound", "one-bound", "no-interval", "raises", "mislabelled"]
    rows = score(table(BASE), Q, reg, names=names, true_effect=1.5).rows
    assert [r[11] for r in rows] == [
        "nan-effect returned a non-finite effect nan",
        "inf-bound returned a non-finite interval bound inf",
        "one-bound returned one interval bound without the other",
        "told",  # no interval at all is a valid result
        "RuntimeError: library error",
        "mislabelled returned an estimate labelled 'someone-else'",
    ]
    assert [r[0] for r in rows] == names  # one row per requested name, whatever the estimator called itself
    assert rows[3][1:8] == (
        1.0,
        None,
        None,
        1.5,
        -0.5,
        pytest.approx(-1 / 3),
        None,
    )  # covers is empty without an interval
    for r in (rows[0], rows[1], rows[2], rows[4], rows[5]):
        assert r[1:10] == (None,) * 9 and r[10] is not None  # an error row keeps its run time
    with pytest.raises(ValueError, match="non-finite effect"):
        reg.estimate("nan-effect", table(BASE), Q)
    with pytest.raises(RuntimeError, match="library error"):  # estimate() lets the estimator's own error through
        reg.estimate("raises", table(BASE), Q)


def test_a_constant_outcome_shared_by_both_groups_is_a_zero_width_row():
    tab = table({"t": [1, 1, 1, 0, 0, 0], "y": [4.0] * 6, "x": [1.0, 2.0, 3.0, 1.5, 2.5, 0.5]})
    rows = score(
        tab,
        CausalQuestion("t", "y", ("x",)),
        registry(),
        names=["difference-in-means", "regression-adjustment"],
        true_effect=0.0,
    ).rows
    for r in rows:  # finite, zero effect, zero width: the row stays
        assert r[1] == pytest.approx(0, abs=1e-12)
        assert r[2] == pytest.approx(r[1], abs=1e-12) and r[3] == pytest.approx(r[1], abs=1e-12)
        assert r[5] == pytest.approx(0, abs=1e-12) and r[6] is None  # a zero truth: a bias, no relative bias
    assert rows[0][7] == "yes"  # the exact difference covers the truth 0


def test_score_s_rows_follow_names_with_truth_fields_only_when_a_truth_is_given():
    tab = table({"t": [1, 1, 1, 0, 0, 0], "y": [5.0, 7.0, 9.0, 1.0, 3.0, 2.0]}, units={"y": "units"})
    reg = registry()
    with_truth = score(tab, Q, reg, names=["regression-adjustment", "difference-in-means"], true_effect=4.0)
    assert [r[0] for r in with_truth.rows] == ["regression-adjustment", "difference-in-means"]
    r = with_truth.rows[1]
    assert r[4:8] == (4.0, pytest.approx(r[1] - 4.0), pytest.approx((r[1] - 4.0) / 4.0), "yes")
    assert r[8:10] == (3, 3) and r[10] >= 0
    without = score(tab, Q, reg, names=["difference-in-means"]).rows[0]
    assert without[4:8] == (None, None, None, None)
    assert with_truth.info.name == "estimator-scores"
    assert {f.name: f.unit for f in with_truth.info.fields}["effect"] == "units"  # the outcome's unit
    with pytest.raises(KeyError, match="unknown estimator 'nope'"):
        score(tab, Q, reg, names=["difference-in-means", "nope"])
    with pytest.raises(ValueError, match=r"repeated \['ipw'\]"):
        score(tab, Q, reg, names=["ipw", "ipw"])
    with pytest.raises(ValueError, match="unknown field"):  # a question problem is the request's, not a row
        score(tab, CausalQuestion("t", "nope"), reg, names=["ipw"])


def test_the_scores_table_s_fields():
    info = scores_info("units")
    assert [(f.name, f.kind, f.unit, f.aggregate) for f in info.fields] == [
        ("estimator", "dimension", None, None),
        ("effect", "measure", "units", "mean"),
        ("ci_low", "measure", "units", "mean"),
        ("ci_high", "measure", "units", "mean"),
        ("true_effect", "measure", "units", "mean"),
        ("bias", "measure", "units", "mean"),
        ("relative_bias", "measure", "share", "mean"),
        ("covers", "dimension", None, None),
        ("n_treated", "measure", "rows", "sum"),
        ("n_control", "measure", "rows", "sum"),
        ("seconds", "measure", "s", "sum"),
        ("method", "dimension", None, None),
    ]


class Sleeps:
    info: ClassVar[EstimatorInfo] = EstimatorInfo("sleeps", "uses up the budget", uses_covariates=False)

    def estimate(self, table, question, *, confidence=0.95, seed=7):
        time.sleep(0.3)
        est = DifferenceInMeans().estimate(table, question, confidence=confidence, seed=seed)
        return replace(est, estimator=self.info.name)


def test_estimators_not_started_before_the_deadline_are_not_run():
    reg = registry(Sleeps, DifferenceInMeans, RegressionAdjustment)
    deadline = time.monotonic() + 0.1
    rows = score(
        table(BASE), Q, reg, names=["sleeps", "difference-in-means", "regression-adjustment"], deadline=deadline
    ).rows
    assert rows[0][1] is not None and rows[0][10] >= 0.3  # the one already running finishes
    for r in rows[1:]:
        assert r[1:11] == (None,) * 10  # not run: no run time either
        assert r[11] == "not run: the request's 30 s were used"


# -- the registry --------------------------------------------------------------------------------------


def test_the_catalogue_mounts_the_built_ins_and_lists_the_pywhy_two_by_what_they_need():
    reg = default_estimators()
    assert {"difference-in-means", "ipw", "regression-adjustment"} <= set(reg.names(origin="builtin"))
    for name, module in (("dowhy-backdoor", "dowhy"), ("econml-dml", "econml")):
        assert name in reg.names() or reg.unavailable()[name] == f"needs {module}"
    assert reg.info("difference-in-means").uses_covariates is False


def test_an_estimator_needs_an_estimate_method():
    class NoEstimate:
        info: ClassVar[EstimatorInfo] = EstimatorInfo("no-estimate", "nothing")

    with pytest.raises(TypeError, match=r"no-estimate: an estimator needs an estimate\(\) method"):
        EstimatorRegistry().register(NoEstimate)


class MedianDifference:
    """The contract's minimal plug-in (interfaces.md §3.1), as written."""

    info: ClassVar[EstimatorInfo] = EstimatorInfo("median-difference", "Difference of the groups' medians, no interval")

    def estimate(self, table, question: CausalQuestion, *, confidence=0.95, seed=7) -> Estimate:
        d = design(table, question)  # arrays: d.treated (bool), d.outcome, d.covariates (2-D)
        effect = float(np.median(d.outcome[d.treated]) - np.median(d.outcome[~d.treated]))
        return Estimate(self.info.name, effect, None, None, int(d.treated.sum()), int((~d.treated).sum()), "medians")


def test_the_contract_s_minimal_plug_in_runs_as_written():
    reg = default_estimators()
    reg.register(MedianDifference)
    tab = table({"t": [1, 1, 1, 0, 0, 0], "y": [5.0, 7.0, 90.0, 1.0, 3.0, 2.0]})
    est = reg.estimate("median-difference", tab, Q)
    assert (est.effect, est.ci_low, est.ci_high) == (5.0, None, None)
