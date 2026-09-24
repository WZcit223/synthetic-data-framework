"""Tests for the entity field checks."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from sdf.foundation.adapters.retail_csv import load_online_retail_csv
from .schema import (
    SKU,
    InboundOrder,
    InventorySnapshot,
    Location,
    OutboundOrder,
    SensorReading,
)

TS = datetime(2025, 1, 1)
VALID = {
    "sku": SKU("S1", "widget", "fasteners", 1.0, 2.0, 0.5, 0.01, "A", 365),
    "location": Location("L1", "PICK", "A01", "R01", 1, 100),
    "inventory": InventorySnapshot(TS, "S1", "L1", 10, 2, 0),
    "inbound": InboundOrder("IN-1", TS, "S1", 50, "SUP-001", 7, "received"),
    "outbound": OutboundOrder("OUT-1", TS, "S1", 1, "ecommerce", "standard", "shipped"),
    "sensor": SensorReading(TS, "L1", "temperature", 4.2, "C"),
}

# One invalid value per rule: (entity, field, value).
INVALID = [
    ("sku", "sku_id", ""),
    ("sku", "sku_id", "  "),
    ("sku", "unit_cost", -0.01),
    ("sku", "unit_price", float("nan")),
    ("sku", "weight_kg", float("inf")),
    ("sku", "volume_m3", -1.0),
    ("sku", "abc_class", "D"),
    ("sku", "shelf_life_days", 0),
    ("location", "location_id", ""),
    ("location", "level", -1),
    ("location", "capacity_units", -1),
    ("inventory", "sku_id", ""),
    ("inventory", "location_id", None),
    ("inventory", "on_hand", -1),
    ("inventory", "reserved", -1),
    ("inventory", "in_transit", -1),
    ("inbound", "order_id", ""),
    ("inbound", "supplier_id", ""),
    ("inbound", "quantity", 0),
    ("inbound", "lead_time_days", -1),
    ("inbound", "status", "lost"),
    ("outbound", "order_id", ""),
    ("outbound", "quantity", 0),
    ("outbound", "quantity", True),
    ("outbound", "channel", "fax"),
    ("outbound", "channel", []),
    ("sku", "abc_class", {}),
    ("outbound", "priority", "urgent"),
    ("outbound", "status", "returned"),
    ("sensor", "location_id", ""),
    ("sensor", "modality", "sound"),
    ("sensor", "value", float("nan")),
]


@pytest.mark.parametrize(("entity", "name", "value"), INVALID)
def test_an_invalid_value_is_rejected_with_its_field_named(entity, name, value):
    record = VALID[entity]
    with pytest.raises(ValueError, match=rf"^{type(record).__name__}\.{name} "):
        replace(record, **{name: value})


def test_valid_records_and_the_allowed_edges_build():
    assert replace(VALID["sku"], abc_class="?", shelf_life_days=None, unit_cost=0.0).abc_class == "?"
    assert replace(VALID["outbound"], status="cancelled").status == "cancelled"
    assert replace(VALID["sensor"], value=-3.5).value == -3.5  # a temperature may be negative
    assert replace(VALID["location"], level=0).level == 0  # ground level
    assert replace(VALID["inventory"], on_hand=10**400).on_hand == 10**400  # an int of any size is finite
    assert replace(VALID["inbound"], lead_time_days=0).lead_time_days == 0  # same-day delivery


def test_every_record_of_the_default_world_validates(default_world):
    wh = default_world[0]
    for record in [*wh.skus, *wh.locations, *wh.inventory, *wh.inbound, *wh.outbound, *wh.sensors]:
        replace(record)  # rebuilds the record, running its checks


@pytest.mark.parametrize("csv_fixture", ["sample_csv", "retail_10k_csv"])
def test_both_bundled_csvs_load_without_an_invalid_record(request, csv_fixture):
    _, _, report = load_online_retail_csv(request.getfixturevalue(csv_fixture))
    assert "invalid_record" not in report.skipped
