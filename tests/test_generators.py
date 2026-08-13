"""Shell-mode tests: determinism + structural integrity (no stat validation)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sdf.synthesis.warehouse import WarehouseGenerator, GenerationSpec
from sdf.synthesis.quality import structural_quality_check
from sdf.cli import build_registry
from sdf.application.warehouse_demo import WarehouseIntelligence


def test_deterministic_seed():
    a = WarehouseGenerator(GenerationSpec(seed=7, n_skus=50)).generate()
    b = WarehouseGenerator(GenerationSpec(seed=7, n_skus=50)).generate()
    assert [s.sku_id for s in a.skus] == [s.sku_id for s in b.skus]
    assert len(a.outbound) == len(b.outbound)


def test_structural_quality_passes():
    wh = WarehouseGenerator(GenerationSpec(n_skus=80)).generate()
    report = structural_quality_check(wh)
    assert report.passed, report.to_dict()


def test_counts_match_spec():
    spec = GenerationSpec(n_skus=123, n_locations=45)
    wh = WarehouseGenerator(spec).generate()
    assert len(wh.skus) == 123
    assert len(wh.locations) == 45


def test_application_layer_runs():
    _, reg = build_registry(GenerationSpec(n_skus=60, horizon_days=30))
    intel = WarehouseIntelligence(reg)
    k = intel.kpis()
    assert k.total_skus == 60
    assert isinstance(intel.replenishment_suggestions(5), list)
    assert len(intel.insights()) >= 3


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
