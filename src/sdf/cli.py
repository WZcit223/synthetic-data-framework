"""Command-line entry point for the framework demo.

``uv run sdf --help`` lists the commands; ``uv run sdf`` with no command runs ``demo``.
"""

from __future__ import annotations

import csv
import json
import os
from typing import List

import click

from . import __version__
from .application.agent import WarehouseAgent
from .application.economics import financial_impact
from .application.scenarios import run_scenarios
from .application.warehouse_demo import WarehouseIntelligence
from .foundation.adapters.retail_csv import load_online_retail_csv
from .synthesis.fidelity import fidelity_report
from .synthesis.fit import FittedHourlyDemand
from .synthesis.forecast import build_series, compare_models, models_for
from .synthesis.materialise import build_registry
from .synthesis.privacy import bootstrap_synthesize, privacy_report, read_retail_feature_table
from .synthesis.quality import structural_quality_check
from .synthesis.sdv_synth import gaussian_copula_fidelity
from .synthesis.spec import GenerationSpec
from .synthesis.tstr import tstr_report
from .workflow import warehouse_pipeline

DEFAULT_CSV = os.path.join("data", "sample_online_retail_ii.csv")


def cmd_demo() -> int:
    spec = GenerationSpec()
    wh, reg = build_registry(spec)
    intel = WarehouseIntelligence(reg)
    report = structural_quality_check(wh)

    print("=" * 68)
    print("  Synthetic Data Framework — AI Warehouse Management (framework demo)")
    print("=" * 68)
    print("\n[Foundation] registry summary:")
    print("  " + json.dumps(reg.summary(), indent=2).replace("\n", "\n  "))

    print("\n[Synthesis] structural quality (framework mode, no stat validation):")
    print(f"  passed={report.passed}  metrics={report.metrics}")

    print("\n[Application] KPIs:")
    for kk, vv in intel.kpis().__dict__.items():
        print(f"  {kk:>18}: {vv}")

    print("\n[Application] ABC distribution:", intel.abc_distribution())

    print("\n[Application] top replenishment suggestions:")
    for s in intel.replenishment_suggestions(top_n=5):
        print(
            f"  {s['sku_id']}  order {s['suggested_order_qty']:>4}  (avail {s['available']}, ROP {s['reorder_point']})"
        )

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
        ("skus", wh.skus),
        ("locations", wh.locations),
        ("inventory", wh.inventory),
        ("inbound", wh.inbound),
        ("outbound", wh.outbound),
        ("sensors", wh.sensors),
    ]:
        _write_csv(os.path.join(outdir, f"{name}.csv"), rows)
    print(f"Wrote 6 CSVs to {outdir}/")
    return 0


def cmd_backtest(path: str) -> int:
    """Phase 2: forecast backtest on a real/open dataset (Online Retail II)."""

    skus, orders = load_online_retail_csv(path)
    series, freq, period = build_series(orders)
    report = compare_models(series, test_len=2 * period, models=models_for(period))

    print("=" * 60)
    print("  Forecast backtest — real-data-driven (Phase 2)")
    print("=" * 60)
    print(f"  source        : {path}")
    print(f"  SKUs / orders : {len(skus)} / {len(orders)}")
    print(f"  granularity   : {freq} (seasonal period {period})")
    print(f"  series        : {report['series_len']} points, mean {report['series_mean']:.1f} units/bucket")
    print(f"  {'model':<10}{'MAE':>9}{'RMSE':>9}{'MAPE%':>9}{'bias':>9}")
    for r in report["results"]:
        print(f"  {r['model']:<10}{r['MAE']:>9}{r['RMSE']:>9}{r['MAPE_pct']:>9}{r['bias']:>9}")
    print(f"\n  best (lowest MAE): {report['best_model']}")
    print("  ALGORITHM-HOOK: beat these baselines with DeepAR/TFT/LightGBM.\n")
    return 0


def cmd_synth(path: str) -> int:
    """Phase 2.1: fit a synthesizer on real data and score its fidelity."""

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
    print(f"  ratio TSTR/TRTR              : {r['ratio_tstr_over_trtr']}  (→1.0 = synthetic as useful as real)\n")
    return 0


def cmd_sdv(path: str) -> int:
    """Phase 2.1 (full): Gaussian-copula synthesis scored by SDMetrics."""
    try:
        rep = gaussian_copula_fidelity(path)
    except ImportError:
        print("This command needs: uv sync --extra synthesis")
        return 1
    print("=" * 60)
    print("  Gaussian-copula synthesis + SDMetrics (Phase 2.1 full, B1)")
    print("=" * 60)
    print(f"  source          : {path}")
    print(f"  rows used        : {rep['rows_used']}")
    print(f"  column-shape KS  : {rep['column_shape_ks']}")
    print(f"  pair-trend corr  : {rep['pair_trend_corr']}")
    print(f"  column-shape score : {rep['column_shape_score']}")
    print(f"  pair-trend score   : {rep['pair_trend_score']}")
    print(f"  SDMetrics overall  : {rep['sdmetrics_overall']}  (1.0 = identical)\n")
    return 0


def cmd_agent(query: str) -> int:
    """Phase 4: tool-using warehouse agent with an audit trace."""

    _wh, reg = build_registry(GenerationSpec())
    agent = WarehouseAgent(WarehouseIntelligence(reg))
    res = agent.handle(query)
    print("=" * 64)
    print("  Warehouse Agent — tool calls + audit trace (Phase 4)")
    print("=" * 64)
    print(f"  Q: {query}")
    print(f"  A: {res['answer']}")
    print(f"  plan: {' → '.join(res['plan'])}")
    if res["proposed_actions"]:
        print(f"  proposed actions (need approval): {res['proposed_actions']}")
    print("  audit trace:")
    for e in res["trace"]:
        print(
            f"    #{e['seq']} {e['name']:<16} {e['status']:<5} {e['duration_ms']}ms"
            + ("  [approval]" if "approval" in e.get("note", "") else "")
        )
    print(f"  run: {res['run']['run_id']}  steps={res['run']['steps']}\n")
    return 0


def cmd_pipeline() -> int:
    """Run the Data Intelligence Workflow (DAG) and print its run record."""

    result = warehouse_pipeline(GenerationSpec()).run()
    print("=" * 64)
    print("  Data Intelligence Workflow — DAG run record")
    print("=" * 64)
    print(f"  order: {' → '.join(result['order'])}")
    for e in result["trace"]:
        print(f"    {e['seq']}. {e['name']:<14} {e['status']:<5} {e['duration_ms']}ms")
    econ = result["artifacts"].get("report", {}).get("economics_annual_saving")
    print(f"  run: {result['run']['run_id']}  total={result['run']['total_ms']}ms  annual_saving≈{econ}\n")
    return 0


def cmd_impact() -> int:
    """Business-outcome economics: counterfactual £ savings."""

    _wh, reg = build_registry(GenerationSpec())
    rep = financial_impact(WarehouseIntelligence(reg))
    print("=" * 64)
    print("  Business-outcome economics — £ counterfactual")
    print("=" * 64)
    print(f"  SKUs considered      : {rep['skus_considered']}  over {rep['horizon_days']} days")
    print(f"  stockout units       : naive {rep['unmet_units']['naive']:,}  → ours {rep['unmet_units']['ours']:,}")
    print(f"  stockout units avoided: {rep['stockout_units_avoided']:,}")
    print(f"  period net saving    : {rep['period']['net_saving']:,}")
    print(f"  ANNUALISED net saving : ≈ {rep['annualised_net_saving']:,}")
    print(
        f"  (assumptions: {rep['assumptions']['holding_cost_annual_rate']:.0%} holding, "
        f"z={rep['assumptions']['service_z']})  DATA-HOOK: real unit costs.\n"
    )
    return 0


def cmd_scenarios() -> int:
    """What-if scenario simulation across a family of specs."""

    rep = run_scenarios(GenerationSpec())
    print("=" * 72)
    print("  What-if scenario simulation")
    print("=" * 72)
    print(f"  {'scenario':<20}{'out-lines':>10}{'need-order':>11}{'safety':>9}{'vs base':>9}")
    for r in rep["scenarios"]:
        print(
            f"  {r['scenario']:<20}{r['outbound_lines']:>10}{r['skus_needing_order']:>11}"
            f"{int(r['safety_stock_units']):>9}{r['safety_stock_vs_baseline_pct']:>8}%"
        )
    print()
    return 0


def cmd_privacy(path: str) -> int:
    """Synthetic-data privacy metrics (DCR / NNDR / clone risk)."""

    real = read_retail_feature_table(path)
    synth = bootstrap_synthesize(real)
    rep = privacy_report(real, synth)
    print("=" * 60)
    print("  Synthetic-data privacy (B3)")
    print("=" * 60)
    for k in ("n_real", "n_synth", "dcr_median", "dcr_p05", "nndr_median", "clone_risk_pct", "verdict"):
        print(f"  {k:<16}: {rep.get(k)}")
    print("  ALGORITHM-HOOK: full membership-inference + differential privacy.\n")
    return 0


# -- click surface ------------------------------------------------------------

_csv_argument = click.argument(
    "csv_path",
    metavar="[CSV]",
    default=DEFAULT_CSV,
    type=click.Path(exists=True, dir_okay=False),
)


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="sdf")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Synthetic Data Framework — AI warehouse demo. With no command, runs ``demo``.

    CSV arguments default to the bundled sample, data/sample_online_retail_ii.csv.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(demo)


@main.command()
def demo() -> None:
    """Run the end-to-end pipeline and print the report."""
    cmd_demo()


@main.command()
@click.argument("outdir", default="out", type=click.Path(file_okay=False))
def export(outdir: str) -> None:
    """Generate the synthetic world and write one CSV per entity to OUTDIR."""
    cmd_export(outdir)


@main.command()
@_csv_argument
def backtest(csv_path: str) -> None:
    """Phase 2: walk-forward forecast backtest on real data."""
    cmd_backtest(csv_path)


@main.command()
@_csv_argument
def synth(csv_path: str) -> None:
    """Phase 2.1: fit a synthesizer on real data and score its fidelity."""
    cmd_synth(csv_path)


@main.command()
@_csv_argument
def tstr(csv_path: str) -> None:
    """Phase 3: train on synthetic, test on real."""
    cmd_tstr(csv_path)


@main.command()
@_csv_argument
def sdv(csv_path: str) -> None:
    """Phase 2.1 (full): Gaussian-copula synthesis scored by SDMetrics (needs the synthesis extra)."""
    if cmd_sdv(csv_path):
        raise click.exceptions.Exit(1)


@main.command()
@click.argument("query", default="what can you do?")
def agent(query: str) -> None:
    """Phase 4: tool-using agent with an audit trace, answering QUERY."""
    cmd_agent(query)


@main.command()
def pipeline() -> None:
    """Run the Data Intelligence Workflow DAG and print its run record."""
    cmd_pipeline()


@main.command()
def impact() -> None:
    """Business-outcome economics: counterfactual £ savings."""
    cmd_impact()


@main.command()
def scenarios() -> None:
    """What-if scenario simulation across a family of specs."""
    cmd_scenarios()


@main.command()
@_csv_argument
def privacy(csv_path: str) -> None:
    """Synthetic-data privacy metrics (DCR / NNDR / clone risk)."""
    cmd_privacy(csv_path)


if __name__ == "__main__":
    main()
