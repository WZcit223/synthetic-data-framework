"""The detection test (checklist B4; docs/refactor/algorithms/interfaces.md §7.3)."""

from __future__ import annotations

import numpy as np
import pytest

from .detection import detection_metrics, detection_report, verdict

COLUMNS = ("qty", "price", "hour")


def rows(rng: np.random.Generator, n: int, shift: float = 0.0) -> list[tuple[float, ...]]:
    return [tuple(r) for r in np.column_stack([rng.poisson(3, n), rng.normal(5 + shift, 1, n), rng.integers(8, 18, n)])]


def test_rows_from_one_distribution_cannot_be_told_apart():
    rng = np.random.default_rng(0)
    rep = detection_report(rows(rng, 600), rows(rng, 600), columns=COLUMNS)
    assert 0.4 < rep["auc"] < 0.6 and rep["verdict"] == "hard to distinguish"
    assert rep["auc_low"] <= rep["auc"] <= rep["auc_high"]
    assert (rep["n_real"], rep["n_synth"], rep["model"]) == (600, 600, "HistGradientBoostingClassifier, 5-fold")


def test_rows_from_two_distributions_are_told_apart_by_the_column_that_differs():
    rng = np.random.default_rng(0)
    rep = detection_report(rows(rng, 600), rows(rng, 600, shift=3.0), columns=COLUMNS)
    assert rep["auc"] > 0.95 and rep["verdict"] == "easily distinguished"
    assert rep["top_features"][0] == "price"


def test_the_report_is_repeatable_with_its_seed_and_uses_as_many_rows_of_each():
    rng = np.random.default_rng(1)
    real, synth = rows(rng, 900), rows(rng, 400, shift=0.5)
    first = detection_report(real, synth, columns=COLUMNS)
    assert detection_report(real, synth, columns=COLUMNS) == first
    assert detection_report(real, synth, columns=COLUMNS, seed=8) != first
    assert (first["n_real"], first["n_synth"]) == (400, 400)
    assert detection_report(real, synth)["top_features"][0].startswith("column ")  # unnamed columns


def test_too_few_rows_is_an_error_and_mismatched_columns_are_refused():
    assert "too few rows" in detection_report([(1.0,)] * 3, [(1.0,)] * 10)["error"]
    assert detection_metrics([(1.0,)] * 3, [(1.0,)] * 10) == {
        "detection_auc": None,
        "detection_auc_low": None,
        "detection_auc_high": None,
        "detection_verdict": "too few rows for 5-fold detection: 3 real, 10 synthetic",
        "detection_top_features": None,
    }
    with pytest.raises(ValueError, match="same columns"):
        detection_report([(1.0, 2.0)] * 10, [(1.0,)] * 10)
    with pytest.raises(ValueError, match="2 column names for 1 columns"):
        detection_report([(1.0,)] * 10, [(1.0,)] * 10, columns=("a", "b"))


def test_the_verdicts_follow_the_published_bounds():
    assert [verdict(a) for a in (0.5, 0.5999, 0.6, 0.8, 0.8001, 1.0)] == [
        "hard to distinguish",
        "hard to distinguish",
        "distinguishable",
        "distinguishable",
        "easily distinguished",
        "easily distinguished",
    ]


def test_the_classifier_learns_from_balanced_classes_and_is_judged_on_held_out_rows(monkeypatch):
    import sklearn.ensemble
    import sklearn.inspection

    fits, judged = [], []
    real_classifier, real_importance = (
        sklearn.ensemble.HistGradientBoostingClassifier,
        sklearn.inspection.permutation_importance,
    )

    class Spy(real_classifier):
        def fit(self, x, y):
            fits.append((len(x), int(y.sum())))
            return super().fit(x, y)

    def importance(model, x, y, **kw):
        judged.append(len(x))
        return real_importance(model, x, y, **kw)

    monkeypatch.setattr(sklearn.ensemble, "HistGradientBoostingClassifier", Spy)
    monkeypatch.setattr(sklearn.inspection, "permutation_importance", importance)
    rng = np.random.default_rng(2)
    detection_report(rows(rng, 900), rows(rng, 400), columns=COLUMNS)
    assert fits == [(640, 320)] * 5  # 400 of each side, 4 folds of 5 to learn from, half of them synthetic
    assert judged == [160] * 5  # the fifth fold, never learnt from


def test_the_classifier_runs_on_one_thread_and_the_setting_is_restored(monkeypatch):
    from threadpoolctl import threadpool_info

    from . import detection

    limits = []
    real_limits = detection.threadpool_limits

    def spy(**kw):
        limits.append(kw)
        return real_limits(**kw)

    monkeypatch.setattr(detection, "threadpool_limits", spy)
    before = [(i["user_api"], i["num_threads"]) for i in threadpool_info()]
    detection_report(rows(np.random.default_rng(0), 50), rows(np.random.default_rng(1), 50))
    assert limits == [{"limits": 1, "user_api": "openmp"}]
    assert [(i["user_api"], i["num_threads"]) for i in threadpool_info()] == before
