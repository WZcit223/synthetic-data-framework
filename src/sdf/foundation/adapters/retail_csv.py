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
from datetime import datetime
from typing import List, Tuple

from sdf.foundation.schema import SKU, OutboundOrder
from sdf.foundation.registry import DataSourceRegistry


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%m/%d/%Y %H:%M", "%d/%m/%Y %H:%M",
                "%m/%d/%y %H:%M", "%d/%m/%y %H:%M",   # 2-digit year (UCI export)
                "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognised InvoiceDate format: {s!r}")


def load_online_retail_csv(path: str) -> Tuple[List[SKU], List[OutboundOrder]]:
    """Read the CSV and return canonical (skus, outbound_orders).

    Negative quantities (returns) become ``status="cancelled"`` orders so demand
    logic that already filters cancelled lines stays correct.
    """
    skus: dict = {}
    orders: List[OutboundOrder] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            code = (row.get("StockCode") or "").strip()
            if not code:
                continue
            try:
                qty = int(float(row.get("Quantity", "0")))
                price = float(row.get("Price", row.get("UnitPrice", "0")) or 0)
            except ValueError:
                continue
            if qty == 0:
                continue
            try:
                ts = _parse_dt(row.get("InvoiceDate", ""))
            except ValueError:
                continue

            if code not in skus:
                skus[code] = SKU(
                    sku_id=code,
                    name=(row.get("Description") or code).strip()[:60],
                    category="retail",
                    unit_cost=round(price * 0.6, 2),
                    unit_price=price,
                    weight_kg=0.1, volume_m3=0.001,
                    abc_class="?",  # assigned downstream if needed
                )
            orders.append(OutboundOrder(
                order_id=f"{row.get('Invoice','INV')}-{i}",
                ts=ts,
                sku_id=code,
                quantity=abs(qty),
                channel="ecommerce",
                priority="standard",
                status="shipped" if qty > 0 else "cancelled",
            ))
    return list(skus.values()), orders


def register_online_retail(reg: DataSourceRegistry, path: str) -> Tuple[int, int]:
    """Load the CSV and register both entity streams as an open dataset."""
    skus, orders = load_online_retail_csv(path)
    reg.register("retail_skus", "SKU", skus, origin="external-open-dataset")
    reg.register("retail_outbound", "OutboundOrder", orders,
                 origin="external-open-dataset")
    return len(skus), len(orders)
