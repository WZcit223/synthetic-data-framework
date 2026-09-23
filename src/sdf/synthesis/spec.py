"""Declarative generation specification (Synthesis Layer).

``GenerationSpec`` is the artefact that separates the *framework* from the
*algorithm*: it is identical whether data is produced by the stdlib sampler in
``warehouse.py`` or by a fitted generative model later. It lives in its own
module so that scenario transforms, the API and the workflow can depend on the
spec without importing the generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class GenerationSpec:
    """Declarative reference-dataset + generation-requirements description.

    ``reference_dataset`` names the open/real dataset the distributions should
    eventually be learned from (see docs/DATASETS.md).
    """

    n_skus: int = 200
    n_locations: int = 120
    horizon_days: int = 90
    start: datetime = field(default_factory=lambda: datetime(2025, 1, 1))
    seed: int = 42

    # Business shape knobs (stand-ins for learned distribution parameters).
    abc_split: tuple = (0.2, 0.3, 0.5)  # A/B/C class proportions
    daily_orders_per_a_sku: float = 6.0  # demand intensity, class A
    express_ratio: float = 0.25
    stockout_pressure: float = 0.08  # fraction of SKUs kept tight

    # Provenance / requirements (documentation carried with the data).
    reference_dataset: str = "synthetic-only (framework mode)"
    requirements: Dict[str, str] = field(
        default_factory=lambda: {
            "realism": "structurally valid; distributions are plausible, not fitted",
            "validation": "framework mode = no statistical validation (see roadmap)",
        }
    )
