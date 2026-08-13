"""Quality reporting (Synthesis Layer).

IMPORTANT — this is the deliberate shell/algorithm boundary.

Per the agreed scope: *"the shell demo needs no data validation; real datasets
are introduced in the algorithm-validation phase."* So this module only does
**structural** checks (referential integrity, non-negativity, coverage). It does
NOT assess statistical fidelity, privacy, or downstream ML utility — those are
the algorithm team's deliverables and are catalogued as HOOKS below and in
docs/ALGORITHM_AND_DATA_CHECKLIST.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class QualityReport:
    mode: str
    checks: Dict[str, bool] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def to_dict(self) -> Dict:
        return {
            "mode": self.mode,
            "passed": self.passed,
            "checks": self.checks,
            "metrics": self.metrics,
            "notes": self.notes,
        }


def structural_quality_check(warehouse) -> QualityReport:
    """Referential-integrity + sanity checks only (shell mode)."""

    sku_ids = {s.sku_id for s in warehouse.skus}
    loc_ids = {l.location_id for l in warehouse.locations}

    inv_refs_ok = all(
        s.sku_id in sku_ids and s.location_id in loc_ids
        for s in warehouse.inventory
    )
    non_negative_ok = all(s.on_hand >= 0 and s.reserved >= 0
                          for s in warehouse.inventory)
    outbound_refs_ok = all(o.sku_id in sku_ids for o in warehouse.outbound)
    coverage = len({s.sku_id for s in warehouse.inventory}) / max(1, len(sku_ids))

    report = QualityReport(mode="structural-only (shell)")
    report.checks = {
        "inventory_referential_integrity": inv_refs_ok,
        "inventory_non_negative": non_negative_ok,
        "outbound_referential_integrity": outbound_refs_ok,
        "sku_coverage_full": coverage >= 0.99,
    }
    report.metrics = {
        "sku_count": float(len(sku_ids)),
        "location_count": float(len(loc_ids)),
        "outbound_lines": float(len(warehouse.outbound)),
        "sku_coverage": round(coverage, 4),
    }
    report.notes = [
        "Shell mode: structural checks only.",
        # ALGORITHM-HOOK: statistical fidelity (KS / correlation / detection AUC),
        # ALGORITHM-HOOK: privacy (DCR, membership-inference),
        # ALGORITHM-HOOK: ML-utility (train-on-synthetic / test-on-real) — TODO.
    ]
    return report
