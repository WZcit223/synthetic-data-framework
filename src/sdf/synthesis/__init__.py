"""Synthesis Layer: synthetic / predictive data generation."""

from sdf.synthesis.quality import QualityReport, structural_quality_check
from sdf.synthesis.warehouse import GenerationSpec, WarehouseGenerator

__all__ = [
    "WarehouseGenerator",
    "GenerationSpec",
    "QualityReport",
    "structural_quality_check",
]
