"""Command-line entry point for the shell demo.

    python -m sdf.cli demo            # run the end-to-end pipeline, print report
    python -m sdf.cli export outdir/  # generate + write CSVs to a directory
    python -m sdf.cli backtest [csv]  # Phase 2: forecast backtest on real data
    python -m sdf.cli synth [csv]     # Phase 2.1: fit synthesizer + fidelity score
    python -m sdf.cli tstr [csv]      # Phase 3: train-on-synthetic, test-on-real
"""

from __future__ import annotations

import csv
import json
import os
import sys
from typing import List

from sdf.foundation.registry import DataSourceRegistry
from sdf.synthesis.warehouse import WarehouseGenerator, GenerationSpec
from sdf.synthesis.quality import structural_quality_check
from sdf.application.warehouse_demo import WarehouseIntelligence


def build_registry(spec: GenerationSpec) -> tuple:
    wh = WarehouseGenerator(spec).generate()
    reg = DataSourceRegistry()
    reg.register("syn_skus", "SKU", wh.skus)
    reg.register("syn_locations", "Location", wh.locations)
    reg.register("syn_inventory", "InventorySnapshot", wh.inventory)
    reg.register("syn_inbound", "InboundOrder", wh.inbound)
    reg.register("syn_outbound", "OutboundOrder", wh.outbound)
    reg.register("syn_sensors", "SensorReading", wh.sensors)
    return wh, reg


def cmd_demo() -> int:
    spec = GenerationSpec()
    wh, reg = build_registry(spec)
    intel = WarehouseIntelligence(reg)
    report = structural_quality_check(wh)

    print("=" * 68)
    print("  Synthetic Data Framework — AI Warehouse Management (shell demo)")
    print("=" * 68)
    print("\n[Foundation] registry summary:")
    print("  " + json.dumps(reg.summary(), indent=2).replace("\n", "\n  "))

    print("\n[Synthesis] structural quality (shell mode, no stat validation):")
    print(f"  passed={report.passed}  metrics={report.metrics}")

    print("\n[Application] KPIs:")
    for kk, vv in intel.kpis().__dict__.items():
        print(f"  {kk:>18}: {vv}")

    print("\n[Application] ABC distribution:", intel.abc_distribution())

    print("\n[Application] top replenishment suggestions:")
    for s in intel.replenishment_suggestions(top_n=5):
        print(f"  {s['sku_id']}  order {s['suggested_order_qty']:>4}  "
              f"(avail {s['available']}, ROP {s['reorder_point']})")

    print("\n[Application] insights:")
    for line in intel.insights():
        print("  • " + line)
    print()
    return 0


def _write_csv(path: str, rows: List) -> None:
    if not rows:
        return
    keys = list(rows[0].to_dict().keys())
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: _flat(v) for k, v in r.to_dict().items()})


def _flat(v):
    return json.dumps(v) if isinstance(v, (dict, list)) else v


def cmd_export(outdir: str) -> int:
    os.makedirs(outdir, exist_ok=True)
    wh, _ = build_registry(GenerationSpec())
    for name, rows in [
        ("skus", wh.skus), ("locations", wh.locations),
        ("inventory", wh.inventory), ("inbound", wh.inbound),
        ("outbound", wh.outbound), ("sensors", wh.sensors),
    ]:
        _write_csv(os.path.join(outdir, f"{name}.csv"), rows)
    print(f"Wrote 6 CSVs to {outdir}/")
    return 0


def cmd_backtest(path: str) -> int:
    """Phase 2: forecast backtest on a real/open dataset (Online Retail II)."""
    from sdf.foundation.adapters.retail_csv import load_online_retail_csv
    from sdf.synthesis.forecast import build_series, models_for, compare_models

    skus, orders = load_online_retail_csv(path)
    series, freq, period = build_series(orders)
    report = compare_models(series, test_len=2 * period,
                            models=models_for(period))

    print("=" * 60)
    print("  Forecast backtest — real-data-driven (Phase 2)")
    print("=" * 60)
    print(f"  source        : {path}")
    print(f"  SKUs / orders : {len(skus)} / {len(orders)}")
    print(f"  granularity   : {freq} (seasonal period {period})")
    print(f"  series        : {report['series_len']} points, "
          f"mean {report['series_mean']:.1f} units/bucket")
    print(f"  {'model':<10}{'MAE':>9}{'RMSE':>9}{'MAPE%':>9}{'bias':>9}")
    for r in report["results"]:
        print(f"  {r['model']:<10}{r['MAE']:>9}{r['RMSE']:>9}"
              f"{r['MAPE_pct']:>9}{r['bias']:>9}")
    print(f"\n  best (lowest MAE): {report['best_model']}")
    print("  ALGORITHM-HOOK: beat these baselines with DeepAR/TFT/LightGBM.\n")
    return 0


def cmd_synth(path: str) -> int:
    """Phase 2.1: fit a synthesizer on real data and score its fidelity."""
    from sdf.foundation.adapters.retail_csv import load_online_retail_csv
    from sdf.synthesis.fit import FittedHourlyDemand
    from sdf.synthesis.fidelity import fidelity_report

    _skus, orders = load_online_retail_csv(path)
    model = FittedHourlyDemand().fit(orders)
    synth = model.generate()
    rep = fidelity_report(model.real_series, synth, model.ppd)

    print("=" * 60)
    print("  Fitted synthesis + fidelity — real-data-conditioned (Phase 2.1)")
    print("=" * 60)
    print(f"  source          : {path}")
    print(f"  real / synth pts : {len(model.real_series)} / {len(synth)}")
    print(f"  KS statistic     : {rep['ks_statistic']}   (0 = identical dist.)")
    print(f"  profile corr     : {rep['profile_corr']}   (1 = identical seasonality)")
    print(f"  mean delta       : {rep['mean_delta_pct']} %")
    print(f"  std delta        : {rep['std_delta_pct']} %")
    print(f"  fidelity score   : {rep['fidelity_score']} / 100")
    print("  ALGORITHM-HOOK: swap in SDV CTGAN/TVAE + SDMetrics for full B1.\n")
    return 0


def cmd_tstr(path: str) -> int:
    """Phase 3: TSTR — train on synthetic, test on real (checklist B2)."""
    from sdf.foundation.adapters.retail_csv import load_online_retail_csv
    from sdf.synthesis.tstr import tstr_report

    _skus, orders = load_online_retail_csv(path)
    r = tstr_report(orders)
    print("=" * 60)
    print("  TSTR — train on synthetic, test on real (Phase 3, B2)")
    print("=" * 60)
    print(f"  source        : {path}")
    if "error" in r:
        print(f"  {r['error']} (series_len={r['series_len']})\n")
        return 0
    print(f"  granularity   : {r['granularity']} (period {r['seasonal_period']})")
    print(f"  train / test  : {r['train_len']} / {r['test_len']}")
    print(f"  TRTR MAE (real-trained)      : {r['TRTR_mae']}")
    print(f"  TSTR MAE (synthetic-trained) : {r['TSTR_mae']}")
    print(f"  ratio TSTR/TRTR              : {r['ratio_tstr_over_trtr']}  "
          f"(→1.0 = synthetic as useful as real)\n")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "demo"
    default_csv = os.path.join("data", "sample_online_retail_ii.csv")
    if cmd == "demo":
        return cmd_demo()
    if cmd == "export":
        return cmd_export(argv[1] if len(argv) > 1 else "out")
    if cmd == "backtest":
        return cmd_backtest(argv[1] if len(argv) > 1 else default_csv)
    if cmd == "synth":
        return cmd_synth(argv[1] if len(argv) > 1 else default_csv)
    if cmd == "tstr":
        return cmd_tstr(argv[1] if len(argv) > 1 else default_csv)
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
