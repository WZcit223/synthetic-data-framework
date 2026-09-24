"""Adapter for the UCI 'Online Retail II' dataset schema (Phase 2).

Columns: Invoice, StockCode, Description, Quantity, InvoiceDate, Price,
Customer ID, Country.

This maps a real (or sample) transactional retail feed into our canonical
``SKU`` and ``OutboundOrder`` entities, so the exact same Application-Layer
demand/forecast code runs on real data instead of the synthetic generator.

Get the real data (≈1M rows, .xlsx) from:
    https://archive.ics.uci.edu/dataset/502/online+retail+ii
Convert a sheet to CSV, then point ``load_online_retail_csv`` at it. A tiny
schema-compatible SAMPLE ships in ``data/sample_online_retail_ii.csv`` so the
pipeline runs with no download.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime

from sdf.foundation.registry import DataSourceRegistry
from sdf.foundation.schema import SKU, OutboundOrder


def _parse_dt(s: str, date_format: str | None = None) -> datetime:
    """Parse an InvoiceDate. With ``date_format`` only that format is accepted.

    Without it the known formats are tried in order, month-first before
    day-first, which is right for the UCI export; a day-first source must pass
    its format explicitly or ``03/04/2011`` is read as 4 March.
    """
    s = (s or "").strip()  # a truncated CSV row yields None
    if date_format is not None:
        return datetime.strptime(s, date_format)
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%d/%m/%y %H:%M",  # 2-digit year (UCI export)
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognised InvoiceDate format: {s!r}")


@dataclass
class LoadReport:
    """What a CSV load kept and what it skipped, by reason."""

    path: str
    rows_read: int = 0
    rows_kept: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    skus: int = 0
    orders: int = 0

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def summary(self) -> str:
        text = f"kept {self.rows_kept:,} of {self.rows_read:,} rows"
        if self.skipped:
            text += "; skipped " + ", ".join(f"{n:,} {reason}" for reason, n in sorted(self.skipped.items()))
        return text

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "rows_read": self.rows_read,
            "rows_kept": self.rows_kept,
            "skipped": dict(sorted(self.skipped.items())),
            "skus": self.skus,
            "orders": self.orders,
        }


def load_online_retail_csv(
    path: str, *, date_format: str | None = None
) -> tuple[list[SKU], list[OutboundOrder], LoadReport]:
    """Read the CSV and return canonical ``(skus, outbound_orders, report)``.

    Rows that cannot be used are skipped and counted by reason in ``report``;
    a row whose values fail the entity checks (such as a negative price) is
    counted as ``invalid_record``.

    Negative quantities (returns) become ``status="cancelled"`` orders so demand
    logic that already filters cancelled lines stays correct.
    """
    skus: dict[str, SKU] = {}
    orders: list[OutboundOrder] = []
    report = LoadReport(path=path)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            report.rows_read += 1
            code = (row.get("StockCode") or "").strip()
            if not code:
                report.skip("missing StockCode")
                continue
            try:
                qty = int(float(row.get("Quantity")))  # None (truncated row) -> TypeError
                price = float(row.get("Price", row.get("UnitPrice", "0")) or 0)
            except (TypeError, ValueError):
                report.skip("non-numeric Quantity or Price")
                continue
            if qty == 0:
                report.skip("zero Quantity")
                continue
            try:
                ts = _parse_dt(row.get("InvoiceDate", ""), date_format)
            except ValueError:
                report.skip("unparseable InvoiceDate")
                continue
            try:
                sku = skus.get(code) or SKU(
                    sku_id=code,
                    name=(row.get("Description") or code).strip()[:60],
                    category="retail",
                    unit_cost=round(price * 0.6, 2),
                    unit_price=price,
                    weight_kg=0.1,
                    volume_m3=0.001,
                    abc_class="?",  # unclassified: the source carries no velocity class
                )
                order = OutboundOrder(
                    order_id=f"{row.get('Invoice', 'INV')}-{i}",
                    ts=ts,
                    sku_id=code,
                    quantity=abs(qty),
                    channel="ecommerce",
                    priority="standard",
                    status="shipped" if qty > 0 else "cancelled",
                )
            except ValueError:
                report.skip("invalid_record")
                continue
            report.rows_kept += 1
            skus[code] = sku
            orders.append(order)
    report.skus, report.orders = len(skus), len(orders)
    return list(skus.values()), orders, report


def register_online_retail(reg: DataSourceRegistry, path: str, *, date_format: str | None = None) -> LoadReport:
    """Load the CSV, register both entity streams as an open dataset, return the load report."""
    skus, orders, report = load_online_retail_csv(path, date_format=date_format)
    reg.register("retail_skus", "SKU", skus, origin="external-open-dataset")
    reg.register("retail_outbound", "OutboundOrder", orders, origin="external-open-dataset")
    return report
