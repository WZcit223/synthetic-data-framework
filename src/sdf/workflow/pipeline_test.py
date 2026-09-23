"""Tests for the DAG pipeline."""

from __future__ import annotations

import pytest

from sdf.synthesis.spec import GenerationSpec
from . import warehouse_pipeline
from .pipeline import Step


def test_pipeline_dag():
    res = warehouse_pipeline(GenerationSpec(n_skus=60, horizon_days=45)).run()
    assert res["order"] == ["ingest", "validate", "application", "economics", "report"]
    assert res["run"]["errors"] == 0
    assert "annualised_net_saving" in res["artifacts"]["economics"]


def test_step_defaults_validate():
    Step("load", lambda ctx: 1)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"name": ""}, "name"),
        ({"name": "a", "depends_on": ["a"]}, "depends_on"),
    ],
)
def test_step_invalid_raises_value_error(kwargs, expected):
    with pytest.raises(ValueError, match=expected):
        Step(run=lambda ctx: 1, **kwargs)


def test_real_csv_run_keeps_load_report_and_skip_reason(sample_csv):
    res = warehouse_pipeline(real_csv=sample_csv).run()
    ingest = res["artifacts"]["ingest"]
    assert ingest["origin"] == "real" and ingest["load"]["rows_kept"] == 3428
    assert res["artifacts"]["report"]["economics"] == {"skipped": "economics runs on the synthetic world in this demo"}


def test_synthetic_run_reports_the_saving():
    res = warehouse_pipeline(GenerationSpec(n_skus=60, horizon_days=45)).run()
    assert "annual_saving" in res["artifacts"]["report"]["economics"]
