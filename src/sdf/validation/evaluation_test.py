"""Tests for evaluating a synthesizer against a sample of real data."""

from __future__ import annotations

import random
from typing import ClassVar

import pytest

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from sdf.synthesis.api import SynthesizerInfo, TableData
from sdf.synthesis.fit import FittedHourlyDemand
from sdf.synthesis.registry import default_registry
from .evaluation import EVALUATION_SEED, NoUsableRows, data_dir, evaluate, sources
from .fidelity import fidelity_report
from .privacy import FEATURE_COLUMNS, privacy_report, read_retail_feature_table

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
    synth = default_registry().create("bootstrap-table").fit(TableData(rows=real, columns=FEATURE_COLUMNS)).sample()
    assert run.metrics == privacy_report(real, synth)
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


@pytest.mark.parametrize("name", ["seasonal-profile", "bootstrap-table"])
def test_a_source_without_usable_rows_is_refused(tmp_path, name):
    empty = tmp_path / "empty.csv"
    empty.write_text("Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n")
    with pytest.raises(NoUsableRows, match="no usable rows"):
        evaluate(name, source=str(empty))
