"""Warehouse synthetic data generator (Synthesis Layer).

Design intent
-------------
The brief calls for: *"clear reference dataset + generation requirements, so an
AI can produce high-quality scripts and data."* We model that as a
:class:`GenerationSpec` — a declarative description of the reference dataset and
the generation requirements. In the shell, the generator is a deterministic,
seeded, rule-based sampler (pure stdlib). In the real system the same spec is
handed to an AI/statistical model (SDV / CTGAN / an LLM code-gen step) that
learns from a real reference dataset and emits a fitted generator.

Everything an algorithm would eventually own is marked ``# ALGORITHM-HOOK``.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sdf.foundation.schema import (
    SKU,
    Location,
    InventorySnapshot,
    InboundOrder,
    OutboundOrder,
    SensorReading,
)


@dataclass
class GenerationSpec:
    """Declarative reference-dataset + generation-requirements description.

    This is the artefact that separates the *shell* from the *algorithm*: it is
    identical whether data is produced by the stdlib sampler here or by a fitted
    generative model later. ``reference_dataset`` names the open/real dataset the
    distributions should eventually be learned from (see docs/DATASETS.md).
    """

    n_skus: int = 200
    n_locations: int = 120
    horizon_days: int = 90
    start: datetime = field(default_factory=lambda: datetime(2025, 1, 1))
    seed: int = 42

    # Business shape knobs (stand-ins for learned distribution parameters).
    abc_split: tuple = (0.2, 0.3, 0.5)          # A/B/C class proportions
    daily_orders_per_a_sku: float = 6.0          # demand intensity, class A
    express_ratio: float = 0.25
    stockout_pressure: float = 0.08              # fraction of SKUs kept tight

    # Provenance / requirements (documentation carried with the data).
    reference_dataset: str = "synthetic-only (shell mode)"
    requirements: Dict[str, str] = field(default_factory=lambda: {
        "realism": "structurally valid; distributions are plausible, not fitted",
        "validation": "shell mode = no statistical validation (see roadmap)",
    })


@dataclass
class SyntheticWarehouse:
    """The full generated bundle handed to the Foundation Layer."""

    skus: List[SKU]
    locations: List[Location]
    inventory: List[InventorySnapshot]
    inbound: List[InboundOrder]
    outbound: List[OutboundOrder]
    sensors: List[SensorReading]
    spec: GenerationSpec


_CATEGORIES = [
    "fasteners", "electronics", "packaging", "textiles",
    "lubricants", "spare-parts", "safety-gear", "adhesives",
]


class WarehouseGenerator:
    """Seeded, deterministic generator for a complete warehouse dataset."""

    def __init__(self, spec: Optional[GenerationSpec] = None) -> None:
        self.spec = spec or GenerationSpec()
        self._rng = random.Random(self.spec.seed)

    # -- public API --------------------------------------------------------

    def generate(self) -> SyntheticWarehouse:
        skus = self._gen_skus()
        locations = self._gen_locations()
        inventory = self._gen_inventory(skus, locations)
        inbound = self._gen_inbound(skus)
        outbound = self._gen_outbound(skus)
        sensors = self._gen_sensors(locations)
        return SyntheticWarehouse(
            skus=skus,
            locations=locations,
            inventory=inventory,
            inbound=inbound,
            outbound=outbound,
            sensors=sensors,
            spec=self.spec,
        )

    # -- entity generators -------------------------------------------------

    def _gen_skus(self) -> List[SKU]:
        skus: List[SKU] = []
        a, b, _c = self.spec.abc_split
        for i in range(self.spec.n_skus):
            r = self._rng.random()
            abc = "A" if r < a else ("B" if r < a + b else "C")
            cost = round(self._rng.uniform(0.5, 400.0), 2)
            skus.append(SKU(
                sku_id=f"SKU-{i:05d}",
                name=self._rand_name(),
                category=self._rng.choice(_CATEGORIES),
                unit_cost=cost,
                unit_price=round(cost * self._rng.uniform(1.15, 2.4), 2),
                weight_kg=round(self._rng.uniform(0.01, 25.0), 3),
                volume_m3=round(self._rng.uniform(0.0001, 0.5), 4),
                abc_class=abc,
                shelf_life_days=self._rng.choice([None, None, 180, 365, 730]),
            ))
        return skus

    def _gen_locations(self) -> List[Location]:
        locs: List[Location] = []
        zones = ["INBOUND", "BULK", "PICK", "COLD", "OUTBOUND"]
        for i in range(self.spec.n_locations):
            zone = self._rng.choice(zones)
            locs.append(Location(
                location_id=f"LOC-{i:04d}",
                zone=zone,
                aisle=f"A{self._rng.randint(1, 20):02d}",
                rack=f"R{self._rng.randint(1, 40):02d}",
                level=self._rng.randint(1, 6),
                capacity_units=self._rng.choice([50, 100, 200, 500]),
                temperature_controlled=(zone == "COLD"),
            ))
        return locs

    def _gen_inventory(
        self, skus: List[SKU], locations: List[Location]
    ) -> List[InventorySnapshot]:
        # ALGORITHM-HOOK: on-hand levels here are heuristic. A real system fits
        # these from historical inventory series (seasonality, safety stock).
        snaps: List[InventorySnapshot] = []
        ts = self.spec.start + timedelta(days=self.spec.horizon_days)
        tight = set(self._rng.sample(
            [s.sku_id for s in skus],
            k=max(1, int(len(skus) * self.spec.stockout_pressure)),
        ))
        for sku in skus:
            loc = self._rng.choice(locations)
            base = {"A": 400, "B": 150, "C": 40}[sku.abc_class]
            on_hand = int(self._rng.uniform(0.0 if sku.sku_id in tight else 0.3,
                                            1.6) * base)
            snaps.append(InventorySnapshot(
                ts=ts,
                sku_id=sku.sku_id,
                location_id=loc.location_id,
                on_hand=on_hand,
                reserved=int(on_hand * self._rng.uniform(0.0, 0.3)),
                in_transit=self._rng.choice([0, 0, 0, base // 2]),
            ))
        return snaps

    def _gen_inbound(self, skus: List[SKU]) -> List[InboundOrder]:
        orders: List[InboundOrder] = []
        n = self.spec.horizon_days * 2
        for i in range(n):
            sku = self._rng.choice(skus)
            day = self._rng.randint(0, self.spec.horizon_days)
            orders.append(InboundOrder(
                order_id=f"IN-{i:06d}",
                ts=self.spec.start + timedelta(days=day),
                sku_id=sku.sku_id,
                quantity=self._rng.choice([50, 100, 200, 500]),
                supplier_id=f"SUP-{self._rng.randint(1, 25):03d}",
                lead_time_days=self._rng.randint(2, 30),
                status=self._rng.choice(["received", "received", "in_transit"]),
            ))
        return orders

    def _gen_outbound(self, skus: List[SKU]) -> List[OutboundOrder]:
        # ALGORITHM-HOOK: demand is a class-scaled Poisson-ish draw. The real
        # system models demand with a fitted time-series / intermittent-demand
        # model (Croston, DeepAR, TimeGAN) learned from order history.
        orders: List[OutboundOrder] = []
        rate = {"A": self.spec.daily_orders_per_a_sku, "B": 1.5, "C": 0.3}
        oid = 0
        for day in range(self.spec.horizon_days):
            ts_day = self.spec.start + timedelta(days=day)
            weekday_factor = 0.6 if ts_day.weekday() >= 5 else 1.0
            for sku in skus:
                lam = rate[sku.abc_class] * weekday_factor
                k = self._poisson(lam)
                for _ in range(k):
                    orders.append(OutboundOrder(
                        order_id=f"OUT-{oid:07d}",
                        ts=ts_day + timedelta(minutes=self._rng.randint(0, 1439)),
                        sku_id=sku.sku_id,
                        quantity=self._rng.choice([1, 1, 1, 2, 3, 5]),
                        channel=self._rng.choice(
                            ["ecommerce", "ecommerce", "wholesale", "store"]),
                        priority=("express"
                                  if self._rng.random() < self.spec.express_ratio
                                  else "standard"),
                        status=self._rng.choices(
                            ["shipped", "picked", "cancelled"],
                            weights=[0.86, 0.11, 0.03])[0],
                    ))
                    oid += 1
        return orders

    def _gen_sensors(self, locations: List[Location]) -> List[SensorReading]:
        readings: List[SensorReading] = []
        sample = self._rng.sample(locations, k=min(30, len(locations)))
        for loc in sample:
            for day in range(0, self.spec.horizon_days, 3):
                ts = self.spec.start + timedelta(days=day)
                if loc.temperature_controlled:
                    readings.append(SensorReading(
                        ts=ts, location_id=loc.location_id,
                        modality="temperature",
                        value=round(self._rng.uniform(1.0, 7.0), 2), unit="C"))
                # DATA-HOOK: vision_occupancy would come from the CV pipeline
                # (reuse of the fabric-defect / multimodal work).
                readings.append(SensorReading(
                    ts=ts, location_id=loc.location_id,
                    modality="vision_occupancy",
                    value=round(self._rng.uniform(0.1, 1.0), 3), unit="ratio",
                    meta={"source": "synthetic-cv-stub"}))
        return readings

    # -- helpers -----------------------------------------------------------

    def _poisson(self, lam: float) -> int:
        """Knuth's Poisson sampler (stdlib-only stand-in for numpy)."""
        if lam <= 0:
            return 0
        import math
        l_bound = math.exp(-lam)
        k, p = 0, 1.0
        while True:
            k += 1
            p *= self._rng.random()
            if p <= l_bound:
                return k - 1

    def _rand_name(self) -> str:
        return "".join(self._rng.choice(string.ascii_uppercase) for _ in range(3)) \
            + "-" + str(self._rng.randint(100, 999))
