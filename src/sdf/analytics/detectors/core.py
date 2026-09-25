"""The detector contract: rate every SKU-day of a frame of daily signals, and report the anomalous ones.

A ``SignalFrame`` holds, per SKU and day, the signals a detector may read (demand,
and the stock and receipts of a replayed policy for the world's frame). A detector
rates every SKU-day (``scores``), so it can be ranked apart from its own threshold,
and reports the points it would alarm on (``detect``). Nothing here knows a world or
a policy: the frame is built one layer up, in ``sdf.simulation.signals``. The
contract is ``docs/refactor/algorithms/interfaces.md`` §6.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Protocol

import numpy as np

DIRECTIONS = ("spike", "drop", "other")


@dataclass(frozen=True)
class DetectorInfo:
    name: str  # lower-case words joined by dashes
    description: str
    requires: tuple[str, ...] = ()  # modules; missing ones list the detector as unavailable
    signals: tuple[str, ...] = ("demand",)  # the columns of a SignalFrame it reads


@dataclass(frozen=True)
class SignalFrame:
    days: tuple[date, ...]
    sku_ids: tuple[str, ...]
    signals: dict[str, np.ndarray]  # name -> SKUs × days, float; np.nan where unknown

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.sku_ids), len(self.days))


@dataclass(frozen=True)
class Detection:
    sku_id: str
    day: date
    score: float  # larger is more anomalous; comparable within one detector only
    direction: str  # 'spike', 'drop' or 'other'
    signals: tuple[str, ...] = ()  # the signals that made it anomalous, when the detector can say


class Detector(Protocol):
    info: ClassVar[DetectorInfo]

    def scores(self, frame: SignalFrame) -> np.ndarray: ...  # SKUs × days, float, finite; larger is more anomalous

    def detect(self, frame: SignalFrame) -> list[Detection]: ...  # the points it reports at its own threshold
