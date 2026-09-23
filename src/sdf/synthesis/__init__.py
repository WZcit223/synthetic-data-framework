"""Synthesis Layer: synthetic / predictive data generation."""

from .quality import QualityReport, structural_quality_check
from .spec import GenerationSpec
from .warehouse import WarehouseGenerator

__all__ = [
    "WarehouseGenerator",
    "GenerationSpec",
    "QualityReport",
    "structural_quality_check",
]
