"""Declarative generation specification (Synthesis Layer).

``GenerationSpec`` is the artefact that separates the *framework* from the
*algorithm*: it is identical whether data is produced by the stdlib sampler in
``warehouse.py`` or by a fitted generative model later. It lives in its own
module so that scenario transforms, the API and the workflow can depend on the
spec without importing the generator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime


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
    requirements: dict[str, str] = field(
        default_factory=lambda: {
            "realism": "structurally valid; distributions are plausible, not fitted",
            "validation": "framework mode = no statistical validation (see roadmap)",
        }
    )

    def __post_init__(self) -> None:
        """Reject values the generator cannot run on; every message names the field."""
        for name in ("n_skus", "n_locations", "horizon_days"):
            v = getattr(self, name)
            if not (math.isfinite(v) and v >= 1):
                raise ValueError(f"{name} must be a finite number >= 1, got {v!r}")
        if len(self.abc_split) != 3 or any(not (math.isfinite(p) and p >= 0) for p in self.abc_split):
            raise ValueError(f"abc_split must have three finite non-negative entries, got {self.abc_split!r}")
        if abs(sum(self.abc_split) - 1.0) > 1e-9:
            raise ValueError(f"abc_split must sum to 1, got {self.abc_split!r}")
        if not (math.isfinite(self.daily_orders_per_a_sku) and self.daily_orders_per_a_sku > 0):
            raise ValueError(f"daily_orders_per_a_sku must be a finite number > 0, got {self.daily_orders_per_a_sku!r}")
        for name in ("express_ratio", "stockout_pressure"):
            v = getattr(self, name)
            if not (math.isfinite(v) and 0.0 <= v <= 1.0):
                raise ValueError(f"{name} must be a finite number in [0, 1], got {v!r}")
