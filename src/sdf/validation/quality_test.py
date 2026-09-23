"""Tests for the structural quality check."""

from __future__ import annotations

from sdf.synthesis.spec import GenerationSpec
from sdf.synthesis.warehouse import WarehouseGenerator
from .quality import structural_quality_check


def test_structural_quality_passes():
    wh = WarehouseGenerator(GenerationSpec(n_skus=80)).generate()
    report = structural_quality_check(wh)
    assert report.passed, report.to_dict()


def test_a_report_without_checks_does_not_pass():
    from .quality import QualityReport

    assert QualityReport(mode="empty").passed is False
