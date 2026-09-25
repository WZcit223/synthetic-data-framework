"""The detector contract (docs/refactor/algorithms/interfaces.md §6): the guard, the built-ins, the scores."""

from __future__ import annotations

from datetime import date, timedelta
from typing import ClassVar

import numpy as np
import pytest

from sdf.analytics.anomaly import seasonal_residual_anomalies
from . import CUTS, Detection, DetectorInfo, DetectorRegistry, SignalFrame, default_detectors, score_detectors, top_k
from .builtin import IsolationForestDetector, SeasonalResidual

START = date(2025, 1, 6)


def frame(demand: np.ndarray, **other: np.ndarray) -> SignalFrame:
    n_skus, n_days = demand.shape
    return SignalFrame(
        days=tuple(START + timedelta(days=i) for i in range(n_days)),
        sku_ids=tuple(f"S{i}" for i in range(n_skus)),
        signals={"demand": demand.astype(float), **{k: v.astype(float) for k, v in other.items()}},
    )


def weekly(n_skus: int = 4, n_days: int = 56) -> np.ndarray:
    pattern = np.array([4, 5, 6, 7, 8, 12, 3], dtype=float)
    return np.array([(1 + s) * pattern[np.arange(n_days) % 7] for s in range(n_skus)])


class Exact:
    """Reports exactly the places it is given: the scoring's reference point."""

    info: ClassVar[DetectorInfo] = DetectorInfo("exact", "reports the given places")

    def __init__(self, places=frozenset()):
        self.places = places

    def scores(self, f):
        out = np.zeros(f.shape)
        for s, d in self.places:
            out[f.sku_ids.index(s), f.days.index(d)] = 1.0
        return out

    def detect(self, f):
        return [Detection(s, d, 1.0, "spike") for s, d in self.places]


def registry(*classes) -> DetectorRegistry:
    reg = DetectorRegistry()
    for cls in classes:
        reg.register(cls)
    return reg


def test_the_built_ins_are_mounted_with_their_parameters():
    reg = default_detectors()
    assert {"seasonal-residual", "isolation-forest"} <= set(reg.names())
    assert {p.name: (p.default, p.min, p.max) for p in reg.params("seasonal-residual")} == {
        "k": (3.5, 2.0, 10.0),
        "period": (7, 2, 28),
    }
    assert {p.name: (p.default, p.min, p.max) for p in reg.params("isolation-forest")} == {
        "contamination": (0.01, 0.001, 0.2),
        "seed": (0, 0, None),
    }
    assert reg.info("isolation-forest").signals == ("demand", "on_hand", "receipts")
    with pytest.raises(ValueError, match="k must be from 2.0 to 10.0"):
        reg.create("seasonal-residual", k=1)


def test_seasonal_residual_reports_what_the_function_it_wraps_reports():
    rng = np.random.default_rng(0)
    demand = rng.poisson(5, (3, 60)).astype(float)
    demand[1, 30] = 60
    f = frame(demand)
    det = SeasonalResidual()
    found = {(d.sku_id, d.day, d.direction, d.score) for d in det.detect(f)}
    expected = {
        (f.sku_ids[i], f.days[a["index"]], a["direction"], abs(a["robust_z"]))
        for i in range(3)
        for a in seasonal_residual_anomalies(list(demand[i]), 7, 3.5)
    }
    assert found == expected and any(s == "S1" and d == f.days[30] for s, d, *_ in found)
    scores = det.scores(f)
    assert scores[1, 30] == scores.max() and (scores >= 0).all()
    assert (det.scores(frame(demand[:, :10])) == 0).all()  # too short for the rule: 0 everywhere


def test_the_guard_refuses_a_wrong_result_before_anyone_scores_it():
    f = frame(weekly())

    class Wrong(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("wrong", "x")
        result: ClassVar[dict] = {}

        def scores(self, f):
            return self.result.get("scores", np.zeros(f.shape))

        def detect(self, f):
            return self.result.get("detect", [])

    reg = registry(Wrong)
    cases = [
        ({"scores": np.zeros((1, 1))}, "scores of shape"),
        ({"scores": np.full(f.shape, np.nan)}, "non-finite score"),
        ({"detect": [Detection("nope", f.days[0], 1.0, "spike")]}, "not in the frame"),
        ({"detect": [Detection("S0", START - timedelta(days=1), 1.0, "spike")]}, "not in the frame"),
        ({"detect": [Detection("S0", f.days[0], 1.0, "sideways")]}, "direction 'sideways'"),
    ]
    for result, message in cases:
        Wrong.result = result
        with pytest.raises(ValueError, match=message):
            reg.run(reg.create("wrong"), f)
    for score in ("1.5", None, np.nan):
        Wrong.result = {"detect": [Detection("S0", f.days[0], score, "spike")]}
        with pytest.raises(ValueError, match="not a finite number"):
            reg.run(reg.create("wrong"), f)
    for signals in (("on_hand",), ["demand"], (1,)):
        Wrong.result = {"detect": [Detection("S0", f.days[0], 1.0, "spike", signals)]}
        with pytest.raises(ValueError, match="must be a tuple of the frame's signals"):
            reg.run(reg.create("wrong"), f)
    # a number of numpy's own types is taken, and passed on as a plain float
    Wrong.result = {"detect": [Detection("S0", f.days[0], np.int64(3), "spike", ("demand",))]}
    (found,) = reg.run(reg.create("wrong"), f)[1]
    assert type(found.score) is float and found == Detection("S0", f.days[0], 3.0, "spike", ("demand",))

    class NeedsStock(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("needs-stock", "x", signals=("demand", "on_hand"))

    with pytest.raises(ValueError, match=r"reads the signals \['on_hand'\]"):
        reg.run(NeedsStock(), f)


def test_exact_detection_scores_one_and_the_empty_detector_recall_zero():
    f = frame(weekly())
    injected = {("S0", f.days[10], "spike"), ("S1", f.days[20], "drop"), ("S2", f.days[30], "spike")}
    places = frozenset((s, d) for s, d, _ in injected)

    class Perfect(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("perfect", "x")

        def __init__(self):
            super().__init__(places)

    class Empty(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("empty", "x")

    table = score_detectors(["perfect", "empty"], f, injected, registry=registry(Perfect, Empty))
    names = [x.name for x in table.info.fields]
    rows = {(r[0], r[1], r[2]): dict(zip(names, r)) for r in table.rows}
    assert {(d, k, c) for d, k, c in rows} == {
        (d, k, c) for d in ("perfect", "empty") for k in ("spike", "drop", "all") for c in CUTS
    }
    for kind in ("spike", "drop", "all"):
        for cut in CUTS:
            assert (rows["perfect", kind, cut]["precision"], rows["perfect", kind, cut]["recall"]) == (1.0, 1.0)
    empty = rows["empty", "all", "threshold"]
    assert (empty["precision"], empty["recall"], empty["f1"], empty["flagged"]) == (None, 0.0, None, 0)
    # the empty detector has no alarm, but top-k ranks every SKU-day by its scores: it still has k rows
    assert rows["empty", "all", "top-k"]["flagged"] == 3
    assert (
        rows["perfect", "all", "threshold"]["seconds"] is not None
        and rows["perfect", "spike", "threshold"]["seconds"] is None
    )


def test_precision_per_kind_counts_that_kind_and_the_false_alarms_only():
    f = frame(weekly())
    injected = {("S0", f.days[10], "spike"), ("S1", f.days[20], "drop")}

    class Some(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("some", "x")

        def __init__(self):  # the spike, the drop, and one false alarm
            super().__init__(frozenset({("S0", f.days[10]), ("S1", f.days[20]), ("S3", f.days[5])}))

    table = score_detectors(["some"], f, injected, registry=registry(Some))
    rows = {(r[1], r[2]): r for r in table.rows}
    assert rows["spike", "threshold"][3:7] == [0.5, 1.0, pytest.approx(2 / 3), 2]  # the spike and the false alarm
    assert rows["all", "threshold"][3:7] == [pytest.approx(2 / 3), 1.0, 0.8, 3]


def test_top_k_breaks_ties_by_sku_order_then_day():
    f = frame(weekly(3, 10))
    scores = np.zeros(f.shape)
    scores[2, 1] = 5.0
    assert top_k(scores, f, 3) == {("S2", f.days[1]), ("S0", f.days[0]), ("S0", f.days[1])}


def test_a_failing_detector_is_an_error_row_and_the_others_still_score():
    f = frame(weekly())

    class Broken(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("broken", "x")

        def scores(self, f):
            raise RuntimeError("no scores today")

    table = score_detectors(["broken", "exact"], f, {("S0", f.days[3], "spike")}, registry=registry(Broken, Exact))
    broken = [r for r in table.rows if r[0] == "broken"]
    assert len(broken) == 1 and broken[0][1] == "all" and broken[0][8] == "RuntimeError: no scores today"
    assert any(r[0] == "exact" and r[8] is None for r in table.rows)

    class FailsToStart(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("fails-to-start", "x")

        def __init__(self):
            raise RuntimeError("no model file")

    table = score_detectors(["fails-to-start"], f, {("S0", f.days[3], "spike")}, registry=registry(FailsToStart))
    assert [r[8] for r in table.rows] == ["RuntimeError: no model file"]
    with pytest.raises(ValueError, match="each detector may appear once"):
        score_detectors(["exact", "exact"], f, set(), registry=registry(Exact))
    with pytest.raises(KeyError, match="unknown detector 'nope'"):
        score_detectors(["exact", "nope"], f, set(), registry=registry(Exact))
    with pytest.raises(ValueError, match="parameters for nope"):
        score_detectors(["exact"], f, set(), params={"nope": {}}, registry=registry(Exact))


def test_isolation_forest_names_the_missing_stock_as_the_reason():
    demand = weekly(6, 70)
    on_hand = 10_000 - np.cumsum(demand, axis=1)  # every day accounted for: stock falls by the demand
    receipts = np.zeros(demand.shape)
    on_hand[2, 40:] -= 30.0  # stock goes missing on day 40
    f = frame(demand, on_hand=on_hand, receipts=receipts)
    found = IsolationForestDetector(contamination=0.005).detect(f)
    hit = [d for d in found if d.sku_id == "S2" and d.day == f.days[40]]
    assert hit and hit[0].signals == ("on_hand",) and hit[0].direction == "other"
    assert IsolationForestDetector().scores(f).shape == f.shape


def test_the_rows_follow_the_benchmark_s_kinds_and_each_place_holds_one_kind():
    f = frame(weekly())
    injected = {("S0", f.days[3], "shrinkage"), ("S1", f.days[9], "spike"), ("S2", f.days[20], "odd")}
    table = score_detectors(["exact"], f, injected, kinds=("spike", "drop", "shrinkage"), registry=registry(Exact))
    assert [r[1] for r in table.rows if r[2] == "threshold"] == ["spike", "shrinkage", "odd", "all"]
    with pytest.raises(ValueError, match="holds two kinds"):
        score_detectors(["exact"], f, {("S0", f.days[3], "spike"), ("S0", f.days[3], "drop")}, registry=registry(Exact))


def test_nothing_injected_leaves_only_the_false_alarms():
    f = frame(weekly())

    class One(Exact):
        info: ClassVar[DetectorInfo] = DetectorInfo("one", "x")

        def __init__(self):
            super().__init__(frozenset({("S0", f.days[5])}))

    rows = {r[2]: r for r in score_detectors(["one"], f, set(), registry=registry(One)).rows}
    assert rows["threshold"][1:7] == ["all", "threshold", 0.0, None, None, 1]
    assert rows["top-k"][1:7] == ["all", "top-k", None, None, None, 0]  # k = 0: nothing ranked


def test_seasonal_residual_detects_exactly_the_scores_at_or_beyond_k():
    rng = np.random.default_rng(1)
    demand = rng.poisson(6, (8, 84)).astype(float)
    demand[rng.integers(0, 8, 20), rng.integers(0, 84, 20)] *= 8
    f = frame(demand)
    det = SeasonalResidual(k=3.0)
    scores = det.scores(f)
    found = {(f.sku_ids.index(d.sku_id), f.days.index(d.day)) for d in det.detect(f)}
    assert found and found == set(zip(*np.nonzero(scores >= 3.0)))


def test_isolation_forest_is_repeatable_with_its_seed():
    demand = weekly(6, 70)
    on_hand = 10_000 - np.cumsum(demand, axis=1)
    on_hand[2, 40:] -= 30.0
    f = frame(demand, on_hand=on_hand, receipts=np.zeros(demand.shape))
    one, again = IsolationForestDetector(seed=3), IsolationForestDetector(seed=3)
    assert np.array_equal(one.scores(f), again.scores(f)) and one.detect(f) == again.detect(f)
    assert not np.array_equal(one.scores(f), IsolationForestDetector(seed=4).scores(f))
