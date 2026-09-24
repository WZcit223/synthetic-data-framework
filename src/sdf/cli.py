"""Command-line entry point for the framework demo.

``uv run sdf --help`` lists the commands; ``uv run sdf`` with no command runs ``demo``.
"""

from __future__ import annotations

import csv
import json
import os

import click

from . import __version__, hooks
from .analytics.causal import CausalQuestion, default_estimators, score
from .analytics.forecast import build_series, compare_models, models_for
from .application.agent import WarehouseAgent
from .application.economics import financial_impact
from .application.intelligence import WarehouseIntelligence
from .application.scenarios import run_scenarios
from .application.snapshot import render_markdown, replace_doc_block, snapshot
from .foundation.adapters.retail_csv import load_online_retail_csv
from .simulation import catalog
from .simulation.benchmark import PromotionBenchmark
from .simulation.effects import EffectStudy
from .simulation.world import World
from .synthesis.materialise import build_registry
from .synthesis.registry import default_registry
from .synthesis.spec import GenerationSpec
from .validation.evaluation import NoUsableRows, evaluate
from .validation.quality import structural_quality_check
from .validation.tstr import tstr_report
from .workflow import warehouse_pipeline

DEFAULT_CSV = os.path.join("data", "sample_online_retail_ii.csv")
DEFAULT_RETAIL_CSV = os.path.join("data", "online_retail_ii_2010_10k.csv")
DEFAULT_CHECKLIST = os.path.join("docs", "ALGORITHM_AND_DATA_CHECKLIST.md")


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

    print("\n[Application] top replenishment orders (95% service-level (s,S) policy):")
    for s in intel.replenishment_ss_policy(service_level=0.95, top_n=5)["rows"]:
        if s["order_qty"] > 0:
            print(f"  {s['sku_id']}  order {s['order_qty']:>4}  (avail {s['available']}, s {s['reorder_point_s']})")

    print("\n[Application] insights:")
    for line in intel.insights():
        print("  • " + line)
    print()
    return 0


def _write_csv(path: str, rows: list) -> None:
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


def _print_load(load) -> None:
    if load.skipped:
        print(f"  load          : {load.summary()}")


def _no_usable_rows(path: str, load) -> bool:
    """Report a CSV that yielded no usable order; the caller then exits 1."""
    if load.rows_kept:
        return False
    print(f"  {path}: no usable rows ({load.summary()}); check the file and --date-format\n")
    return True


def cmd_backtest(path: str, date_format: str | None = None) -> int:
    """Phase 2: forecast backtest on a real/open dataset (Online Retail II)."""

    skus, orders, load = load_online_retail_csv(path, date_format=date_format)
    if _no_usable_rows(path, load):
        return 1
    series, freq, period = build_series(orders)
    report = compare_models(series, test_len=2 * period, models=models_for(period))

    print("=" * 60)
    print("  Forecast backtest — real-data-driven (Phase 2)")
    print("=" * 60)
    print(f"  source        : {path}")
    print(f"  SKUs / orders : {len(skus)} / {len(orders)}")
    _print_load(load)
    print(f"  granularity   : {freq} (seasonal period {period})")
    if "error" in report:
        print(f"  {report['error']}\n")
        return 0
    print(f"  series        : {report['series_len']} points, mean {report['series_mean']:.1f} units/bucket")
    print(f"  {'model':<13}{'MAE':>10}{'RMSE':>10}{'MAPE%':>8}{'WAPE%':>8}{'bias':>10}")
    for r in report["results"]:
        mape, wape = (f"{v}" if v is not None else "n/a" for v in (r["MAPE_pct"], r["WAPE_pct"]))
        print(f"  {r['model']:<13}{r['MAE']:>10}{r['RMSE']:>10}{mape:>8}{wape:>8}{r['bias']:>10}")
    print("  MAPE% averages |error|/actual over days with sales; WAPE% = Σ|error| / Σactual.")
    print(f"\n  best (lowest MAE): {report['best_model']}")
    print("  ALGORITHM-HOOK[C1]: beat these baselines with DeepAR/TFT/LightGBM.\n")
    return 0


def cmd_synth(path: str, date_format: str | None = None, synthesizer: str = "seasonal-profile") -> int:
    """Phase 2.1: fit a synthesizer on real data and score its fidelity."""

    try:
        run = evaluate(synthesizer, source=path, date_format=date_format)
    except NoUsableRows as exc:
        print(f"  {path}: no usable rows ({exc.reason}); check the file and --date-format\n")
        return 1
    rep = run.metrics
    n_real = sum(1 for row in run.table.rows if row[1] == "real")

    print("=" * 60)
    print("  Fitted synthesis + fidelity — real-data-conditioned (Phase 2.1)")
    print("=" * 60)
    print(f"  source          : {path}")
    _print_load(run.load)
    print(f"  synthesizer      : {synthesizer}")
    print(f"  real / synth pts : {n_real} / {len(run.table.rows) - n_real}")
    print(f"  KS statistic     : {rep['ks_statistic']}   (0 = identical dist.)")
    print(f"  profile corr     : {rep['profile_corr']}   (1 = identical seasonality)")
    print(f"  mean delta       : {rep['mean_delta_pct']} %")
    print(f"  std delta        : {rep['std_delta_pct']} %")
    print(f"  fidelity score   : {rep['fidelity_score']} / 100")
    print("  ALGORITHM-HOOK[B1]: swap in SDV CTGAN/TVAE + SDMetrics for full B1.\n")
    return 0


def cmd_tstr(path: str, date_format: str | None = None, synthesizer: str = "seasonal-profile") -> int:
    """Phase 3: TSTR — train on synthetic, test on real (checklist B2)."""

    _skus, orders, load = load_online_retail_csv(path, date_format=date_format)
    if _no_usable_rows(path, load):
        return 1
    r = tstr_report(orders, synthesizer=synthesizer)
    print("=" * 60)
    print("  TSTR — train on synthetic, test on real (Phase 3, B2)")
    print("=" * 60)
    print(f"  source        : {path}")
    _print_load(load)
    print(f"  synthesizer   : {synthesizer}")
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
        from sdf.synthesis.sdv_synth import gaussian_copula_fidelity

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


def cmd_agent(query: str, audit_log: str | None = None) -> int:
    """Phase 4: tool-using warehouse agent with an audit trace."""

    _wh, reg = build_registry(GenerationSpec())
    agent = WarehouseAgent(WarehouseIntelligence(reg), sink_path=audit_log)
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
    print(f"  run: {res['run']['run_id']}  steps={res['run']['steps']}")
    if audit_log:
        print(f"  full audit log appended to {audit_log}")
    print()
    return 0


def cmd_pipeline(audit_log: str | None = None) -> int:
    """Run the Data Intelligence Workflow (DAG) and print its run record."""

    result = warehouse_pipeline(GenerationSpec()).run(sink_path=audit_log)
    print("=" * 64)
    print("  Data Intelligence Workflow — DAG run record")
    print("=" * 64)
    print(f"  order: {' → '.join(result['order'])}")
    for e in result["trace"]:
        print(f"    {e['seq']}. {e['name']:<14} {e['status']:<5} {e['duration_ms']}ms")
    econ = result["artifacts"].get("report", {}).get("economics", {})
    econ_text = f"annual_saving≈{econ['annual_saving']}" if "annual_saving" in econ else f"economics: {econ}"
    print(f"  run: {result['run']['run_id']}  total={result['run']['total_ms']}ms  {econ_text}")
    if audit_log:
        print(f"  full audit log appended to {audit_log}")
    print()
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
        f"z={rep['assumptions']['service_z']})  DATA-HOOK[C2]: real unit costs.\n"
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


def _amount(x: float | None, *, signed: bool = False) -> str:
    """A number as the effects table prints it: whole with space-grouped thousands from 100 up, else 3 digits."""
    if x is None:
        return "—"
    sign = "+" if signed and x > 0 else ("−" if x < 0 else "")
    ax = abs(x)
    text = f"{ax:,.0f}".replace(",", " ") if ax >= 100 else f"{ax:.3g}"
    return sign + text


def cmd_effects(
    interventions: list[str],
    policies: list[str],
    outcomes: list[str],
    replicates: int,
    confidence: float,
    csv_path: str | None = None,
) -> int:
    """Effects of interventions against the baseline, over paired replicates of the default world."""
    try:
        study = EffectStudy(
            GenerationSpec(),
            [catalog.intervention(n) for n in interventions],
            [_policy(p) for p in policies],
            [catalog.outcome(n) for n in outcomes],
            replicates=replicates,
            confidence=confidence,
        )
        result = study.run()
    except (KeyError, ValueError) as exc:
        click.echo(f"sdf effects: {exc.args[0] if isinstance(exc, KeyError) else exc}", err=True)
        return 1
    print(
        f"{', '.join(interventions)} vs baseline, {', '.join(p.name for p in study.policies)},"
        f" {replicates} paired replicates, {study.confidence * 100:g} % intervals"
    )
    width = max(len("metric"), *(len(r[2]) for r in result.effects.rows))
    multi = len(study.interventions) > 1 or len(study.policies) > 1
    head = f"{'metric':<{width}}{'baseline':>12}{'treated':>12}{'effect':>12}   interval"
    for (intervention, policy), rows in _grouped(result.effects.rows):
        if multi:
            print(f"\n{intervention} · {policy}")
        print(head)
        for r in rows:
            low, high = r[6], r[7]
            covers = "   (covers 0)" if low <= 0 <= high else ""
            print(
                f"{r[2]:<{width}}{_amount(r[3]):>12}{_amount(r[4]):>12}{_amount(r[5], signed=True):>12}"
                f"   {_amount(low, signed=True)} … {_amount(high, signed=True)}{covers}"
            )
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([f.name for f in result.effects.info.fields])
            writer.writerows(result.effects.rows)
        print(f"\nwrote {csv_path}")
    return 0


BUILT_IN_ESTIMATORS = ("difference-in-means", "regression-adjustment", "ipw")


def cmd_estimate(
    estimators: list[str],
    *,
    uplift: float = 0.3,
    confounding: float = 1.0,
    noise: float = 0.25,
    seed: int = 7,
    drop: list[str] | None = None,
    confidence: float = 0.95,
    csv_path: str | None = None,
) -> int:
    """Estimators scored on the promotion benchmark over the default world, against its known effect."""
    try:
        bench = PromotionBenchmark(uplift=uplift, confounding=confounding, noise=noise, seed=seed)
        draw = bench.draw(World.generate(GenerationSpec()))
        q = draw.question
        unknown = [c for c in drop or () if c not in q.covariates]
        if unknown:
            raise ValueError(f"--drop {unknown[0]}: the benchmark's covariates are {list(q.covariates)}")
        question = CausalQuestion(q.treatment, q.outcome, tuple(c for c in q.covariates if c not in (drop or ())))
        table = score(
            draw.table,
            question,
            default_estimators(),
            names=estimators,
            true_effect=draw.true_effect,
            confidence=confidence,
        )
    except (KeyError, ValueError) as exc:
        click.echo(f"sdf estimate: {exc.args[0] if isinstance(exc, KeyError) else exc}", err=True)
        return 1
    adjusted = ", ".join(question.covariates) or "nothing"
    print(
        f"promotion benchmark: {len(draw.table.rows)} SKUs, uplift {uplift * 100:g} %, confounding {confounding:g},"
        f" seed {seed}; true effect {_amount(draw.true_effect, signed=True)} units/week; adjusting for {adjusted}"
    )
    width = max(len("estimator"), *(len(r[0]) for r in table.rows))
    intervals = [
        f"{_amount(r[2], signed=True)} … {_amount(r[3], signed=True)}" if r[2] is not None else "" for r in table.rows
    ]
    iw = max(len(f"{confidence * 100:g} % interval"), *(len(i) for i in intervals))
    print(f"{'estimator':<{width}}{'effect':>10}   {f'{confidence * 100:g} % interval':<{iw}}{'bias':>10}   covers")
    for r, interval in zip(table.rows, intervals):
        if r[1] is None:
            print(f"{r[0]:<{width}}   error: {r[11]}")
            continue
        print(
            f"{r[0]:<{width}}{_amount(r[1], signed=True):>10}   {interval:<{iw}}{_amount(r[5], signed=True):>10}   {r[7] or ''}"
        )
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([f.name for f in table.info.fields])
            writer.writerows(table.rows)
        print(f"\nwrote {csv_path}")
    return 0


def _grouped(rows: list[tuple]) -> list[tuple[tuple[str, str], list[tuple]]]:
    groups: dict[tuple[str, str], list[tuple]] = {}
    for r in rows:
        groups.setdefault((r[0], r[1]), []).append(r)
    return list(groups.items())


def _policy(text: str):
    """``naive`` or ``service-level[:LEVEL]``, as ``--policy`` takes it."""
    kind, _, level = text.partition(":")
    if kind == "service-level" and level:
        try:
            value = float(level)
        except ValueError as exc:
            raise click.BadParameter(f"{text!r}: the level must be a number, e.g. service-level:0.95") from exc
        if not 0.5 < value < 1:  # the bounds POST /experiments and /effects enforce
            raise click.BadParameter(f"{text!r}: the level must be above 0.5 and below 1")
        return catalog.policy(kind, service_level=value)
    if level:
        raise click.BadParameter(f"{text!r}: only service-level takes a level")
    return catalog.policy(kind)


def cmd_privacy(path: str, date_format: str | None = None, synthesizer: str = "bootstrap-table") -> int:
    """Synthetic-data privacy metrics (DCR / NNDR / clone risk)."""

    try:
        rep = evaluate(synthesizer, source=path, date_format=date_format).metrics
    except NoUsableRows as exc:
        rep = {"error": exc.reason}
    print("=" * 60)
    print("  Synthetic-data privacy (B3)")
    print("=" * 60)
    if "error" in rep:
        print(f"  {path}: {rep['error']} — no usable rows; check the file and --date-format\n")
        return 1
    print(f"  {'synthesizer':<16}: {synthesizer}")
    for k in ("n_real", "n_synth", "dcr_median", "dcr_p05", "nndr_median", "clone_risk_pct", "verdict"):
        print(f"  {k:<16}: {rep.get(k)}")
    print("  ALGORITHM-HOOK[B3]: full membership-inference + differential privacy.\n")
    return 0


# -- click surface ------------------------------------------------------------

_date_format_option = click.option(
    "--date-format",
    default=None,
    metavar="FORMAT",
    help="strptime format of InvoiceDate, e.g. '%d/%m/%Y %H:%M' for day-first sources. "
    "Default: try the known formats, month-first first (right for the UCI export).",
)


def _synthesizer_option(produces: str, default: str):
    """``--synthesizer NAME``, limited to registered synthesizers that produce ``produces``."""
    registry = default_registry()
    names = [n for n in registry.names() if registry.info(n).produces == produces]
    return click.option(
        "--synthesizer",
        type=click.Choice(names),
        default=default,
        show_default=True,
        help=f"Registered synthesizer that produces a {produces}.",
    )


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
@_date_format_option
def backtest(csv_path: str, date_format: str | None) -> None:
    """Phase 2: walk-forward forecast backtest on real data."""
    if cmd_backtest(csv_path, date_format):
        raise click.exceptions.Exit(1)


@main.command()
@_csv_argument
@_date_format_option
@_synthesizer_option("series", "seasonal-profile")
def synth(csv_path: str, date_format: str | None, synthesizer: str) -> None:
    """Phase 2.1: fit a synthesizer on real data and score its fidelity."""
    if cmd_synth(csv_path, date_format, synthesizer):
        raise click.exceptions.Exit(1)


@main.command()
@_csv_argument
@_date_format_option
@_synthesizer_option("series", "seasonal-profile")
def tstr(csv_path: str, date_format: str | None, synthesizer: str) -> None:
    """Phase 3: train on synthetic, test on real."""
    if cmd_tstr(csv_path, date_format, synthesizer):
        raise click.exceptions.Exit(1)


@main.command()
@_csv_argument
def sdv(csv_path: str) -> None:
    """Phase 2.1 (full): Gaussian-copula synthesis scored by SDMetrics (needs the synthesis extra)."""
    if cmd_sdv(csv_path):
        raise click.exceptions.Exit(1)


_audit_log_option = click.option(
    "--audit-log",
    "audit_log",
    type=click.Path(dir_okay=False, writable=True),
    help="Append the run's full log (every input and output whole, then a summary line) to this JSONL file.",
)


@main.command()
@click.argument("query", default="what can you do?")
@_audit_log_option
def agent(query: str, audit_log: str | None) -> None:
    """Phase 4: tool-using agent with an audit trace, answering QUERY."""
    cmd_agent(query, audit_log)


@main.command()
@_audit_log_option
def pipeline(audit_log: str | None) -> None:
    """Run the Data Intelligence Workflow DAG and print its run record."""
    cmd_pipeline(audit_log)


@main.command()
@click.option(
    "--intervention",
    "interventions",
    multiple=True,
    required=True,
    help="An intervention to compare with the baseline (repeatable).",
)
@click.option(
    "--policy",
    "policies",
    multiple=True,
    default=("service-level:0.95",),
    show_default=True,
    help="naive or service-level[:LEVEL] (repeatable).",
)
@click.option(
    "--outcome",
    "outcomes",
    multiple=True,
    default=("simulated_cost",),
    show_default=True,
    help="An outcome to measure (repeatable).",
)
@click.option("--replicates", default=10, show_default=True, type=int, help="Paired replicate worlds, 2 to 20.")
@click.option(
    "--confidence",
    default=0.95,
    show_default=True,
    type=float,
    help="The intervals' confidence, above 0.5 and below 1.",
)
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(dir_okay=False, writable=True),
    help="Also write the effects table to this CSV file.",
)
def effects(
    interventions: tuple[str, ...],
    policies: tuple[str, ...],
    outcomes: tuple[str, ...],
    replicates: int,
    confidence: float,
    csv_path: str | None,
) -> None:
    """Effects of interventions against the baseline, with intervals, over paired replicate worlds."""
    if cmd_effects(list(interventions), list(policies), list(outcomes), replicates, confidence, csv_path):
        raise click.exceptions.Exit(1)


@main.command()
@click.option(
    "--estimator",
    "estimators",
    multiple=True,
    default=BUILT_IN_ESTIMATORS,
    show_default=True,
    help="An estimator to score (repeatable); see GET /api/v1/estimators for what is mounted.",
)
@click.option("--uplift", default=0.3, show_default=True, type=float, help="The promotion's true uplift, -0.9 to 3.")
@click.option(
    "--confounding",
    default=1.0,
    show_default=True,
    type=float,
    help="How strongly high-demand SKUs are promoted, 0 (random) to 3.",
)
@click.option("--noise", default=0.25, show_default=True, type=float, help="Lognormal noise of weekly units, 0 to 1.")
@click.option("--seed", default=7, show_default=True, type=int, help="The benchmark draw's seed.")
@click.option(
    "--drop",
    multiple=True,
    help="Leave this covariate out of the adjustment set (repeatable), to watch the bias return.",
)
@click.option(
    "--confidence",
    default=0.95,
    show_default=True,
    type=float,
    help="The intervals' confidence, above 0.5 and below 1.",
)
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(dir_okay=False, writable=True),
    help="Also write the scores table to this CSV file.",
)
def estimate(
    estimators: tuple[str, ...],
    uplift: float,
    confounding: float,
    noise: float,
    seed: int,
    drop: tuple[str, ...],
    confidence: float,
    csv_path: str | None,
) -> None:
    """Causal estimators scored against the known effect of the promotion benchmark."""
    code = cmd_estimate(
        list(estimators),
        uplift=uplift,
        confounding=confounding,
        noise=noise,
        seed=seed,
        drop=list(drop),
        confidence=confidence,
        csv_path=csv_path,
    )
    if code:
        raise click.exceptions.Exit(code)


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
@_date_format_option
@_synthesizer_option("table", "bootstrap-table")
def privacy(csv_path: str, date_format: str | None, synthesizer: str) -> None:
    """Synthetic-data privacy metrics (DCR / NNDR / clone risk)."""
    if cmd_privacy(csv_path, date_format, synthesizer):
        raise click.exceptions.Exit(1)


@main.command()
@click.option("--format", "fmt", type=click.Choice(["json", "markdown"]), default="json", show_default=True)
@click.option(
    "--sample", "sample_csv", default=DEFAULT_CSV, show_default=True, type=click.Path(exists=True, dir_okay=False)
)
@click.option(
    "--retail",
    "retail_csv",
    default=DEFAULT_RETAIL_CSV,
    show_default=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--update-doc",
    "doc_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Rewrite the block between the sdf-validate markers in this markdown file.",
)
def validate(fmt: str, sample_csv: str, retail_csv: str, doc_path: str | None) -> None:
    """Print every recorded number (default world + bundled CSVs) as JSON or markdown."""
    snap = snapshot(sample_csv, retail_csv)
    if doc_path:
        with open(doc_path, encoding="utf-8") as fh:
            text = fh.read()
        updated = replace_doc_block(text, render_markdown(snap))
        if updated != text:
            with open(doc_path, "w", encoding="utf-8") as fh:
                fh.write(updated)
        click.echo(f"{doc_path}: {'updated' if updated != text else 'already up to date'}")
        return
    click.echo(render_markdown(snap) if fmt == "markdown" else json.dumps(snap, indent=2, ensure_ascii=False))


@main.command("hooks")
@click.option(
    "--checklist",
    default=DEFAULT_CHECKLIST,
    show_default=True,
    type=click.Path(exists=True, dir_okay=False),
    help="The checklist whose row IDs the markers must name.",
)
@click.option(
    "--update-doc",
    "doc_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Rewrite the block between the sdf-hooks markers in this markdown file (and read its IDs).",
)
def hooks_command(checklist: str, doc_path: str | None) -> None:
    """Print where each checklist item plugs into the code, from the hook markers in the source."""
    with open(checklist, encoding="utf-8") as fh:
        ids = hooks.checklist_ids(fh.read())
    found = hooks.scan()
    bad = hooks.problems(found, ids)
    if bad:
        for line in bad:
            click.echo(line, err=True)
        raise click.exceptions.Exit(1)
    index = hooks.render_index(found, ids, doc_path or DEFAULT_CHECKLIST)
    if doc_path:
        with open(doc_path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            updated = hooks.replace_doc_block(text, index)
        except ValueError as exc:
            raise click.ClickException(f"{doc_path}: {exc}") from exc
        if updated != text:
            with open(doc_path, "w", encoding="utf-8") as fh:
                fh.write(updated)
        click.echo(f"{doc_path}: {'updated' if updated != text else 'already up to date'}")
        return
    click.echo(index, nl=False)


if __name__ == "__main__":
    main()
