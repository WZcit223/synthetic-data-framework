"""Tests for the Online Retail II adapter."""

from __future__ import annotations

from datetime import datetime

from sdf.foundation.registry import DataSourceRegistry
from .retail_csv import load_online_retail_csv, register_online_retail

HEADER = "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"


def _write(tmp_path, rows: str):
    path = tmp_path / "retail.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return str(path)


def test_skipped_rows_are_counted_by_reason(tmp_path):
    path = _write(
        tmp_path,
        "1,A1,ok,2,2010-01-04 10:00:00,1.5,1,UK\n"
        "2,,no code,2,2010-01-04 10:00:00,1.5,1,UK\n"
        "3,A2,bad qty,two,2010-01-04 10:00:00,1.5,1,UK\n"
        "4,A3,zero,0,2010-01-04 10:00:00,1.5,1,UK\n"
        "5,A4,bad date,1,yesterday,1.5,1,UK\n",
    )
    skus, orders, report = load_online_retail_csv(path)
    assert (len(skus), len(orders)) == (1, 1)
    assert (report.rows_read, report.rows_kept, report.skus, report.orders) == (5, 1, 1, 1)
    assert report.skipped == {
        "missing StockCode": 1,
        "non-numeric Quantity or Price": 1,
        "zero Quantity": 1,
        "unparseable InvoiceDate": 1,
    }
    assert "kept 1 of 5 rows" in report.summary()


def test_day_first_dates_need_an_explicit_format(tmp_path):
    path = _write(tmp_path, "1,A1,ok,2,03/04/2011 10:00,1.5,1,UK\n")
    _, default_orders, _ = load_online_retail_csv(path)
    assert default_orders[0].ts == datetime(2011, 3, 4, 10, 0)  # month-first by default
    _, orders, _ = load_online_retail_csv(path, date_format="%d/%m/%Y %H:%M")
    assert orders[0].ts == datetime(2011, 4, 3, 10, 0)


def test_explicit_format_rejects_other_formats(tmp_path):
    path = _write(tmp_path, "1,A1,ok,2,2011-04-03 10:00:00,1.5,1,UK\n")
    _, orders, report = load_online_retail_csv(path, date_format="%d/%m/%Y %H:%M")
    assert orders == [] and report.skipped == {"unparseable InvoiceDate": 1}


def test_register_returns_the_load_report(sample_csv):
    reg = DataSourceRegistry()
    report = register_online_retail(reg, sample_csv)
    assert (report.skus, report.orders) == (12, 3428)
    assert len(reg.stream("OutboundOrder")) == report.orders


def test_truncated_rows_are_counted_not_fatal(tmp_path):
    path = _write(tmp_path, "1,A1,ok,2,2010-01-04 10:00:00,1.5,1,UK\n2,A2,short\n3,A3,short,4\n")
    _, orders, report = load_online_retail_csv(path)
    assert len(orders) == 1
    assert report.skipped == {"non-numeric Quantity or Price": 1, "unparseable InvoiceDate": 1}


def test_a_row_that_fails_the_entity_checks_is_an_invalid_record(tmp_path):
    path = _write(
        tmp_path,
        "1,A1,ok,2,2010-01-04 10:00:00,1.5,1,UK\n"
        "2,A2,bad debt,1,2010-01-04 10:00:00,-11062.06,1,UK\n"
        "3,A3,no price,1,2010-01-04 10:00:00,nan,1,UK\n"
        "5,A5,infinite price,1,2010-01-04 10:00:00,inf,1,UK\n"
        "6,A6,infinite qty,inf,2010-01-04 10:00:00,1.5,1,UK\n"
        "4,A1,later row of a kept SKU,3,2010-01-04 11:00:00,-1,1,UK\n",
    )
    skus, orders, report = load_online_retail_csv(path)
    assert [s.sku_id for s in skus] == ["A1"]
    assert [o.quantity for o in orders] == [2, 3]  # only a new SKU's own values are checked against its price
    assert report.skipped == {"invalid_record": 3, "non-numeric Quantity or Price": 1}
