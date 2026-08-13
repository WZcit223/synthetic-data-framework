"""Synthetic Data Framework (SDF).

A three-layer industrial-AI framework prototype:

    Foundation Layer  -> canonical entities + multi-source data registry
    Synthesis Layer   -> synthetic / predictive data generation
    Application Layer  -> operation / application logic (AI warehouse demo)

This package is the *engineering shell*: it demonstrates the end-to-end flow
with zero heavy dependencies so it runs anywhere. The places where a real
algorithm or real dataset must eventually plug in are marked with
``# ALGORITHM-HOOK`` / ``# DATA-HOOK`` and catalogued in
``docs/ALGORITHM_AND_DATA_CHECKLIST.md``.
"""

__version__ = "0.1.0"

from sdf.foundation.registry import DataSourceRegistry
from sdf.synthesis.warehouse import WarehouseGenerator, GenerationSpec
from sdf.application.warehouse_demo import WarehouseIntelligence

__all__ = [
    "DataSourceRegistry",
    "WarehouseGenerator",
    "GenerationSpec",
    "WarehouseIntelligence",
    "__version__",
]
