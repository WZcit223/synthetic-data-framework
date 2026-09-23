"""Every recorded number in one place (``sdf validate``).

The golden tests and ``docs/VALIDATION.md`` used to compute or copy their
numbers separately, so a document could silently drift from the code. This
module is now the only place that computes them:

- ``default_world_snapshot`` covers the default synthetic world,
- ``csv_snapshot`` covers one bundled retail CSV,
- ``snapshot`` combines the default world with both bundled CSVs,
- ``render_markdown`` turns a snapshot into the tables embedded in
  ``docs/VALIDATION.md``, and ``replace_doc_block`` swaps them into a document
  between the ``sdf-validate`` markers.

Values are plain JSON types, rounded exactly as the underlying functions
already round them.
"""

from __future__ import annotations

from pathlib import Path

from sdf.analytics.forecast import build_series, compare_models, models_for
from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from sdf.synthesis.fit import FittedHourlyDemand
from sdf.synthesis.materialise import build_registry
from sdf.synthesis.spec import GenerationSpec
from sdf.validation.fidelity import fidelity_report
from sdf.validation.privacy import bootstrap_synthesize, privacy_report, read_retail_feature_table
from sdf.validation.quality import structural_quality_check
from sdf.validation.tstr import tstr_report
from .agent import WarehouseAgent
from .economics import financial_impact
from .intelligence import WarehouseIntelligence
from .scenarios import run_scenarios

DOC_BEGIN = "<!-- sdf-validate:begin -->"
DOC_END = "<!-- sdf-validate:end -->"
SERVICE_LEVELS = (0.90, 0.95, 0.99)
AGENT_QUERY = "should I reorder and what is the money impact?"
_BACKTEST_KEYS = ("model", "MAE", "RMSE", "MAPE_pct", "bias")


def _backtest(orders) -> dict:
    series, freq, period = build_series(orders)
    report = compare_models(series, test_len=2 * period, models=models_for(period))
    return {
        "granularity": freq,
        "seasonal_period": period,
        "series_len": len(series),
        "best_model": report["best_model"],
        "results": [{k: r[k] for k in _BACKTEST_KEYS} for r in report["results"]],
    }


def default_world_snapshot(spec: GenerationSpec | None = None) -> dict:
    """Every recorded number for one generated world (the default world by default)."""
    spec = spec or GenerationSpec()
    wh, reg = build_registry(spec)
    intel = WarehouseIntelligence(reg)
    kpis = intel.kpis()
    rule = intel.replenishment_suggestions(9999)
    rule_anomalies = intel.anomalies()
    demand_anomalies = intel.demand_anomalies()
    stocktake = intel.stocktake_discrepancies()
    impact = financial_impact(intel)
    agent = WarehouseAgent(intel).handle(AGENT_QUERY)
    return {
        "spec": {"n_skus": spec.n_skus, "horizon_days": spec.horizon_days, "seed": spec.seed},
        "registry": reg.summary()["by_entity"],
        "quality": structural_quality_check(wh).to_dict(),
        "kpis": dict(kpis.__dict__),
        "abc": intel.abc_distribution(),
        "rule_replenishment": {
            "skus_flagged": len(rule),
            "top": [{"sku_id": s["sku_id"], "suggested_order_qty": s["suggested_order_qty"]} for s in rule[:3]],
        },
        "replenishment_simulation": intel.replenishment_simulation(),
        "ss_policy": [
            {k: p[k] for k in ("service_level", "z", "skus_needing_order", "total_safety_stock_units")}
            for p in (intel.replenishment_ss_policy(service_level=sl) for sl in SERVICE_LEVELS)
        ],
        "rule_anomalies": {
            "stockout": sum(1 for a in rule_anomalies if a["type"] == "stockout"),
            "dead_stock": sum(1 for a in rule_anomalies if a["type"] == "dead_stock"),
        },
        "demand_anomalies": {
            "granularity": demand_anomalies["granularity"],
            "seasonal_period": demand_anomalies["seasonal_period"],
            "series_len": demand_anomalies["series_len"],
            "count": demand_anomalies["count"],
            "top": demand_anomalies["anomalies"][0] if demand_anomalies["anomalies"] else None,
        },
        "stocktake": {k: v for k, v in stocktake.items() if k != "discrepancies"},
        "backtest": _backtest(reg.stream("OutboundOrder")),
        "economics": {
            k: impact[k]
            for k in (
                "skus_considered",
                "horizon_days",
                "unmet_units",
                "stockout_units_avoided",
                "annualised_net_saving",
            )
        },
        "agent": {
            "query": AGENT_QUERY,
            "plan": agent["plan"],
            "steps": agent["run"]["steps"],
            "proposed_actions": agent["proposed_actions"],
        },
        "scenarios": run_scenarios(spec)["scenarios"],
    }


def csv_snapshot(path: str) -> dict:
    """Every recorded number for one retail CSV (backtest, fidelity, TSTR, privacy)."""
    skus, orders = load_online_retail_csv(path)
    model = FittedHourlyDemand().fit(orders)
    real = read_retail_feature_table(path)
    return {
        "file": Path(path).name,
        "skus": len(skus),
        "orders": len(orders),
        "backtest": _backtest(orders),
        "fidelity": fidelity_report(model.real_series, model.generate(), model.ppd),
        "tstr": tstr_report(orders),
        "privacy": privacy_report(real, bootstrap_synthesize(real)),
    }


def snapshot(sample_csv: str, retail_csv: str) -> dict:
    """The default world plus both bundled CSVs: the full set of recorded numbers."""
    return {
        "default_world": default_world_snapshot(),
        "sample_csv": csv_snapshot(sample_csv),
        "retail_csv": csv_snapshot(retail_csv),
    }


# -- markdown ---------------------------------------------------------------


def _fmt(v) -> str:
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return str(v)


def _table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows]
    return out + [""]


def _backtest_table(bt: dict) -> list[str]:
    lines = [
        f"Backtest ({bt['granularity']}, seasonal period {bt['seasonal_period']}, "
        f"{bt['series_len']} points; ranked by MAE):",
        "",
    ]
    return lines + _table(
        ["model", "MAE", "RMSE", "MAPE %", "bias"],
        [[r["model"], r["MAE"], r["RMSE"], r["MAPE_pct"], r["bias"]] for r in bt["results"]],
    )


def _world_markdown(w: dict) -> list[str]:
    k, sim, st, da, eco = (
        w["kpis"],
        w["replenishment_simulation"],
        w["stocktake"],
        w["demand_anomalies"],
        w["economics"],
    )
    top = da["top"] or {}
    lines = [
        f"### Default world (`GenerationSpec()`: {w['spec']['n_skus']} SKUs, {w['spec']['horizon_days']} days, seed {w['spec']['seed']})",
        "",
    ]
    lines += _table(
        ["metric", "value"],
        [
            ["outbound order lines", w["registry"]["OutboundOrder"]],
            ["structural quality passed", w["quality"]["passed"]],
            ["units on hand", k["total_on_hand"]],
            ["inventory value", k["inventory_value"]],
            ["cancel rate", k["cancel_rate"]],
            ["express rate", k["express_rate"]],
            ["ABC mix (A / B / C)", " / ".join(str(w["abc"].get(c, 0)) for c in "ABC")],
            ["rule-based: SKUs at/below reorder point", w["rule_replenishment"]["skus_flagged"]],
            [
                "rule-based simulation: stockouts before → after",
                f"{sim['stockouts_before']} → {sim['stockouts_after']}",
            ],
            [
                "rule-based simulation: service level before → after",
                f"{_fmt(sim['service_level_before'])} → {_fmt(sim['service_level_after'])}",
            ],
            [
                "rule anomalies: stockout / dead stock",
                f"{w['rule_anomalies']['stockout']} / {w['rule_anomalies']['dead_stock']}",
            ],
            ["demand anomalies (robust-z ≥ 3.5)", da["count"]],
            [
                "largest demand anomaly: day, value, expected, robust-z",
                f"{top.get('index')}, {_fmt(top.get('value'))}, {_fmt(top.get('expected'))}, {_fmt(top.get('robust_z'))}",
            ],
            [
                "vision stocktake: scanned / matched / flagged",
                f"{st['locations_scanned']} / {st['matched']} / {st['flagged']}",
            ],
            ["vision stocktake: net unit variance", st["net_unit_variance"]],
        ],
    )
    lines += _backtest_table(w["backtest"])
    lines += ["(s,S) policy (lead time 7 days, review 7 days):", ""]
    lines += _table(
        ["service level", "z", "SKUs needing an order", "total safety stock (units)"],
        [[p["service_level"], p["z"], p["skus_needing_order"], p["total_safety_stock_units"]] for p in w["ss_policy"]],
    )
    lines += ["Economics (counterfactual, default `CostModel`):", ""]
    lines += _table(
        ["metric", "value"],
        [
            ["SKUs considered", eco["skus_considered"]],
            [
                "stockout units, naive → ours",
                f"{_fmt(eco['unmet_units']['naive'])} → {_fmt(eco['unmet_units']['ours'])}",
            ],
            ["stockout units avoided", eco["stockout_units_avoided"]],
            ["annualised net saving (estimate)", eco["annualised_net_saving"]],
        ],
    )
    lines += ["Scenarios (95 % service level):", ""]
    lines += _table(
        ["scenario", "SKUs needing an order", "safety stock (units)", "vs baseline %"],
        [
            [s["scenario"], s["skus_needing_order"], s["safety_stock_units"], s["safety_stock_vs_baseline_pct"]]
            for s in w["scenarios"]
        ],
    )
    ag = w["agent"]
    actions = ", ".join(f"{a['sku_id']} × {a['quantity']} ({a['status']})" for a in ag["proposed_actions"]) or "none"
    lines += [
        f'Agent, "{ag["query"]}": plan `{" → ".join(ag["plan"])}`, {ag["steps"]} logged steps, proposed {actions}.',
        "",
    ]
    return lines


def _csv_markdown(title: str, c: dict) -> list[str]:
    fid, tstr, priv = c["fidelity"], c["tstr"], c["privacy"]
    lines = [f"### {title} (`{c['file']}`: {c['skus']:,} SKUs, {c['orders']:,} orders)", ""]
    lines += _backtest_table(c["backtest"])
    lines += _table(
        ["metric", "value"],
        [
            ["fidelity: KS statistic (0 = identical)", fid["ks_statistic"]],
            ["fidelity: profile correlation (1 = identical)", fid["profile_corr"]],
            ["fidelity: mean / std delta %", f"{_fmt(fid['mean_delta_pct'])} / {_fmt(fid['std_delta_pct'])}"],
            ["fidelity score (0–100)", fid["fidelity_score"]],
            ["TSTR: TRTR MAE (real-trained)", tstr.get("TRTR_mae")],
            ["TSTR: TSTR MAE (synthetic-trained)", tstr.get("TSTR_mae")],
            ["TSTR: ratio TSTR / TRTR (→ 1.0 = as useful as real)", tstr.get("ratio_tstr_over_trtr")],
            ["privacy: DCR median / p05", f"{_fmt(priv['dcr_median'])} / {_fmt(priv['dcr_p05'])}"],
            ["privacy: clone risk %", priv["clone_risk_pct"]],
            ["privacy: verdict", priv["verdict"]],
        ],
    )
    return lines


def render_markdown(snap: dict) -> str:
    """The tables embedded in ``docs/VALIDATION.md`` (without the markers)."""
    lines = [
        "_Generated by `uv run sdf validate --update-doc docs/VALIDATION.md`; do not edit by hand._",
        "",
    ]
    lines += _world_markdown(snap["default_world"])
    lines += _csv_markdown("Bundled sample CSV (daily)", snap["sample_csv"])
    lines += _csv_markdown("Real UCI extract (hourly)", snap["retail_csv"])
    return "\n".join(lines).rstrip() + "\n"


def replace_doc_block(text: str, block: str) -> str:
    """Return ``text`` with the content between the ``sdf-validate`` markers replaced by ``block``."""
    begin, end = text.find(DOC_BEGIN), text.find(DOC_END)
    if begin < 0 or end < 0 or end < begin:
        raise ValueError(f"document has no {DOC_BEGIN} … {DOC_END} block")
    return text[: begin + len(DOC_BEGIN)] + "\n" + block + text[end:]


def doc_block(text: str) -> str:
    """Return the current content between the ``sdf-validate`` markers."""
    begin, end = text.find(DOC_BEGIN), text.find(DOC_END)
    if begin < 0 or end < 0 or end < begin:
        raise ValueError(f"document has no {DOC_BEGIN} … {DOC_END} block")
    return text[begin + len(DOC_BEGIN) + 1 : end]
