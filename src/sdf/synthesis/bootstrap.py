"""Per-column bootstrap with Gaussian jitter: a dependency-free table synthesizer."""

from __future__ import annotations

import random
import statistics
from typing import ClassVar

from .api import SynthesizerInfo, TableData


class BootstrapTable:
    """Resample each column independently and add Gaussian jitter.

    Stands in for a fitted table generator so privacy can be measured with no
    heavy dependencies. Each ``sample()`` continues the instance's random
    stream unless ``seed`` pins it. ALGORITHM-HOOK: use SDV CTGAN/copula rows instead.
    """

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="bootstrap-table",
        produces="table",
        needs_fit=True,
        description="Per-column bootstrap + Gaussian jitter (jitter × column std)",
    )

    def __init__(self, *, seed: int = 7, jitter: float = 0.05) -> None:
        self.jitter = jitter
        self._rng = random.Random(seed)
        self._cols: list[tuple[float, ...]] = []
        self._stds: list[float] = []
        self._n_rows = 0

    def fit(self, data: TableData) -> BootstrapTable:
        self._n_rows = len(data.rows)
        self._cols = list(zip(*data.rows))
        self._stds = [statistics.pstdev(c) or 1.0 for c in self._cols]
        return self

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[tuple[float, ...]]:
        """``n`` rows (default: as many as were fitted); empty when fitted on no rows."""
        if not self._n_rows:
            return []
        rng = random.Random(seed) if seed is not None else self._rng
        n = self._n_rows if n is None else n
        return [
            tuple(rng.choice(col) + rng.gauss(0, self.jitter * std) for col, std in zip(self._cols, self._stds))
            for _ in range(n)
        ]
