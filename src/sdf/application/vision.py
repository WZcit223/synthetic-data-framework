"""Vision stocktake: shelf-occupancy heatmap and vision-versus-book discrepancies (Application Layer)."""

from __future__ import annotations

from collections import defaultdict

from sdf.foundation.registry import DataSourceRegistry


def latest_vision(reg: DataSourceRegistry) -> dict:
    """Latest vision_occupancy reading per location."""
    readings = reg.stream("SensorReading", where=lambda r: r.modality == "vision_occupancy")
    latest: dict = {}
    for r in readings:
        cur = latest.get(r.location_id)
        if cur is None or r.ts >= cur.ts:
            latest[r.location_id] = r
    return latest


def shelf_occupancy_grid(reg: DataSourceRegistry) -> list[dict]:
    """Zone → aisle → cells, each cell an occupancy ratio for a heatmap.

    DATA-HOOK: occupancy is a synthetic CV estimate. Replace with real
    shelf-occupancy from the vision pipeline (camera frames / defect model).
    """
    locs = {l.location_id: l for l in reg.stream("Location")}
    latest = latest_vision(reg)
    zones: dict = defaultdict(lambda: defaultdict(list))
    for loc_id, r in latest.items():
        loc = locs.get(loc_id)
        if not loc:
            continue
        zones[loc.zone][loc.aisle].append(
            {
                "location_id": loc_id,
                "occupancy": r.value,
                "book_units": r.meta.get("book_units"),
                "est_units": r.meta.get("est_units"),
                "capacity": r.meta.get("capacity"),
            }
        )
    out: list[dict] = []
    for zone in sorted(zones):
        aisles = [
            {"aisle": a, "cells": sorted(zones[zone][a], key=lambda c: c["location_id"])} for a in sorted(zones[zone])
        ]
        out.append({"zone": zone, "aisles": aisles})
    return out


def stocktake_discrepancies(reg: DataSourceRegistry, *, rel_threshold: float = 0.25, min_abs: int = 15) -> dict:
    """Compare vision-estimated units vs book-of-record; flag mismatches.

    This is the 'AI stocktake' story: the camera mostly confirms the books,
    but flags locations where physical ≠ system (miscount / misplacement /
    shrinkage). ALGORITHM-HOOK: the real unit estimate comes from a trained
    counting/detection model, not occupancy × capacity.
    """
    latest = latest_vision(reg)
    flagged: list[dict] = []
    matched = 0
    for loc_id, r in latest.items():
        book = r.meta.get("book_units", 0)
        est = r.meta.get("est_units", 0)
        diff = est - book
        rel = abs(diff) / max(1, book)
        if abs(diff) >= min_abs and rel >= rel_threshold:
            flagged.append(
                {
                    "location_id": loc_id,
                    "book_units": book,
                    "vision_units": est,
                    "diff": diff,
                    "direction": "shortage" if diff < 0 else "surplus",
                    "rel": round(rel, 2),
                    "occupancy": r.value,
                }
            )
        else:
            matched += 1
    flagged.sort(key=lambda x: abs(x["diff"]), reverse=True)
    total = len(latest)
    return {
        "locations_scanned": total,
        "matched": matched,
        "flagged": len(flagged),
        "match_rate": round(matched / max(1, total), 4),
        "net_unit_variance": sum(f["diff"] for f in flagged),
        "discrepancies": flagged[:20],
    }
