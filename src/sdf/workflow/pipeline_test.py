"""Tests for the DAG pipeline."""

from __future__ import annotations

from sdf.synthesis.spec import GenerationSpec
from . import warehouse_pipeline


def test_pipeline_dag():
    res = warehouse_pipeline(GenerationSpec(n_skus=60, horizon_days=45)).run()
    assert res["order"] == ["ingest", "validate", "application", "economics", "report"]
    assert res["run"]["errors"] == 0
    assert "annualised_net_saving" in res["artifacts"]["economics"]
