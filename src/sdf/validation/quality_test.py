"""Tests for the structural quality check."""

from __future__ import annotations

from sdf.synthesis.spec import GenerationSpec
from sdf.synthesis.warehouse import WarehouseGenerator
from .quality import structural_quality_check


def test_structural_quality_passes():
    wh = WarehouseGenerator(GenerationSpec(n_skus=80)).generate()
    report = structural_quality_check(wh)
    assert report.passed, report.to_dict()
