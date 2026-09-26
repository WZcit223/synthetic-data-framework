"""Tests for evaluating a synthesizer against a sample of real data."""

from __future__ import annotations

import random
from typing import ClassVar

import pytest

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from sdf.foundation.sources import data_dir
from sdf.synthesis.api import SynthesizerInfo, TableData
from sdf.synthesis.fit import FittedHourlyDemand
from sdf.synthesis.registry import default_registry
from .detection import detection_metrics
from .evaluation import EVALUATION_SEED, NoUsableRows, RunFailed, evaluate, sources
from .fidelity import fidelity_report
from .privacy import FEATURE_COLUMNS, FEATURE_KINDS, privacy_report, read_retail_feature_table

SAMPLE = "data/sample_online_retail_ii.csv"


def test_sources_lists_the_sample_csvs_that_exist(monkeypatch, tmp_path):
    monkeypatch.delenv("SDF_DATA_DIR", raising=False)
    assert sources() == {"sample": SAMPLE, "retail-10k": "data/online_retail_ii_2010_10k.csv"}
    monkeypatch.setenv("SDF_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path and sources() == {}
    (tmp_path / "sample_online_retail_ii.csv").write_text("x\n")
    assert sources() == {"sample": str(tmp_path / "sample_online_retail_ii.csv")}


def test_a_series_run_scores_what_sdf_synth_prints():
    run = evaluate("seasonal-profile", source="sample", params={"seed": 7})
    # the numbers `sdf synth` printed before evaluate existed, computed the same way
    _skus, orders, _load = load_online_retail_csv(SAMPLE)
    model = FittedHourlyDemand(default_registry().create("seasonal-profile")).fit(orders)
    assert run.metrics == fidelity_report(model.real_series, model.generate(), model.ppd)
    assert (run.kind, run.params, run.repeatable) == ("series", {"seed": 7}, True)
    assert [f.name for f in run.table.info.fields] == ["step", "origin", "value"]
    origins = [r[1] for r in run.table.rows]
    assert origins.count("real") == origins.count("synthetic") == len(model.real_series)
    assert run.load is not None and run.load.rows_kept > 0


def test_a_table_run_scores_what_sdf_privacy_prints():
    run = evaluate("bootstrap-table", source="sample")
    real = read_retail_feature_table(SAMPLE)
    data = TableData(rows=real, columns=FEATURE_COLUMNS, kinds=FEATURE_KINDS)
    synth = default_registry().create("bootstrap-table").fit(data).sample()
    assert run.metrics == privacy_report(real, synth) | detection_metrics(real, synth, columns=FEATURE_COLUMNS)
    assert run.metrics["detection_auc_low"] <= run.metrics["detection_auc"] <= run.metrics["detection_auc_high"]
    assert run.metrics["detection_verdict"] in ("hard to distinguish", "distinguishable", "easily distinguished")
    assert set(run.metrics["detection_top_features"].split(", ")) <= set(FEATURE_COLUMNS)
    assert (run.kind, run.params, run.repeatable) == ("table", {"seed": 7, "jitter": 0.05}, True)
    assert [f.name for f in run.table.info.fields] == ["origin", "qty", "price", "hour", "weekday"]
    assert run.table.info.fields[1].aggregate == "mean"


class UnseededJitter:
    """A table synthesizer whose seed is nullable, as gaussian-copula's is: left out, each run differs."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("unseeded-jitter", "table", True, "Rows plus uniform noise")

    def __init__(self, *, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._rows: list = []

    def fit(self, data: TableData) -> UnseededJitter:
        self._rows = list(data.rows)
        return self

    def sample(self, n=None, *, seed=None):
        return [tuple(v + self._rng.random() for v in row) for row in self._rows]


@pytest.mark.parametrize("name", ["seasonal-profile", "bootstrap-table", "unseeded-jitter"])
def test_a_run_with_the_seed_left_out_is_repeatable(name):
    reg = default_registry()
    reg.register(UnseededJitter)
    first = evaluate(name, source="sample", registry=reg)
    assert first.params["seed"] == EVALUATION_SEED and first.repeatable
    assert evaluate(name, source="sample", registry=reg).table == first.table
    assert evaluate(name, source="sample", params=first.params, registry=reg).table == first.table
    assert evaluate(name, source="sample", params={"seed": 8}, registry=reg).table != first.table


def test_a_left_out_seed_uses_its_declared_default():
    class SeedFive(UnseededJitter):
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("seed-five", "table", True, "x")

        def __init__(self, *, seed: int = 5) -> None:
            super().__init__(seed=seed)

    reg = default_registry()
    reg.register(SeedFive)
    run = evaluate("seed-five", source="sample", registry=reg)
    assert run.params == {"seed": 5}
    assert evaluate("seed-five", source="sample", params={"seed": 5}, registry=reg).table == run.table
    with pytest.raises(ValueError, match="seed must not be null"):  # only a nullable seed may be None
        evaluate("seed-five", source="sample", params={"seed": None}, registry=reg)


def test_a_plug_in_that_ignores_column_kinds_still_evaluates_with_the_detection_test():
    reg = default_registry()
    reg.register(UnseededJitter)  # adds uniform noise to every column, whatever its kind
    metrics = evaluate("unseeded-jitter", source="sample", registry=reg).metrics
    assert metrics["detection_auc"] > 0.9 and metrics["detection_verdict"] == "easily distinguished"
    assert evaluate("bootstrap-table", source="sample").metrics["detection_auc"] < 0.75  # the built-in honours them


def test_the_bayesian_network_meets_the_detection_target_on_the_real_extract():
    # plan 05's acceptance: under 0.75 on the extract, which no per-column synthesizer can reach (0.78 at best)
    metrics = evaluate("bayesian-network", source="retail-10k").metrics
    assert metrics["detection_auc"] < 0.75 and metrics["detection_verdict"] == "hard to distinguish"


def test_a_row_of_the_wrong_width_is_the_synthesizer_s_failure():
    class Wide(UnseededJitter):
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("wide", "table", True, "x")

        def sample(self, n=None, *, seed=None):
            return [(*r, 0.0) for r in self._rows]

    reg = default_registry()
    reg.register(Wide)
    with pytest.raises(RunFailed, match=r"wide failed while sampling from it: a row of 5 values"):
        evaluate("wide", source="sample", registry=reg)


def test_a_run_without_a_seed_parameter_is_not_repeatable():
    class NoSeed(UnseededJitter):
        info: ClassVar[SynthesizerInfo] = SynthesizerInfo("no-seed", "table", True, "x")

        def __init__(self) -> None:
            super().__init__(seed=None)

    reg = default_registry()
    reg.register(NoSeed)
    run = evaluate("no-seed", source="sample", registry=reg)
    assert (run.params, run.repeatable) == ({}, False)


def test_a_csv_path_is_accepted_like_a_source_id():
    assert evaluate("seasonal-profile", source=SAMPLE).metrics == evaluate("seasonal-profile", source="sample").metrics


@pytest.mark.parametrize(
    ("name", "kwargs", "error", "message"),
    [
        ("warehouse-spec", {}, ValueError, "warehouse-spec produces a warehouse; choose it for the world instead"),
        ("nope", {}, KeyError, "unknown synthesizer 'nope'"),
        (
            "seasonal-profile",
            {"params": {"jitter": 0.1}},
            ValueError,
            r"takes no parameter \['jitter'\]; it takes \['seed'\]",
        ),
        ("seasonal-profile", {"params": {"seed": "7"}}, ValueError, "seed must be a number"),
        ("bootstrap-table", {"params": {"jitter": 2.0}}, ValueError, "jitter must be from 0.0 to 1.0"),
        ("seasonal-profile", {"source": "elsewhere"}, ValueError, "unknown source 'elsewhere'"),
    ],
)
def test_each_rejection_says_why(name, kwargs, error, message):
    with pytest.raises(error, match=message):
        evaluate(name, **{"source": "sample", **kwargs})


def test_a_source_id_whose_file_is_missing_names_the_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("SDF_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match=r"source 'sample' is not available: .* does not exist \(set SDF_DATA_DIR"):
        evaluate("seasonal-profile", source="sample")


class Broken(UnseededJitter):
    """A plug-in whose own code raises ValueError while sampling."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("broken-sample", "table", True, "x")

    def sample(self, n=None, *, seed=None):
        raise ValueError("internal bug")


def test_a_failing_synthesizer_is_a_run_failure_not_a_bad_request():
    reg = default_registry()
    reg.register(Broken)
    with pytest.raises(RunFailed, match="broken-sample failed while fitting and sampling it: ValueError: internal bug"):
        evaluate("broken-sample", source="sample", registry=reg)
    assert not issubclass(RunFailed, (KeyError, ValueError))


def test_a_file_of_returns_only_has_no_demand_to_fit(tmp_path):
    lines = open(SAMPLE, encoding="utf-8").read().splitlines()[:30]
    returns = [lines[0]]
    for line in lines[1:]:
        cells = line.split(",")
        cells[0], cells[3] = "C" + cells[0], "-" + cells[3]  # a cancellation: invoice C…, negative quantity
        returns.append(",".join(cells))
    path = tmp_path / "returns.csv"
    path.write_text("\n".join(returns) + "\n", encoding="utf-8")
    with pytest.raises(NoUsableRows, match="no demand left after removing cancelled lines"):
        evaluate("seasonal-profile", source=str(path))


@pytest.mark.parametrize("name", ["seasonal-profile", "bootstrap-table"])
def test_a_source_without_usable_rows_is_refused(tmp_path, name):
    empty = tmp_path / "empty.csv"
    empty.write_text("Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n")
    with pytest.raises(NoUsableRows, match="no usable rows"):
        evaluate(name, source=str(empty))
