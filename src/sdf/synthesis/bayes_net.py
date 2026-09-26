"""A tree-shaped Bayesian network over binned columns: a table synthesizer that learns how columns depend.

``bootstrap-table`` and ``gaussian-copula`` sample each column on its own or through linear
correlation only, so a row can pair a price with a quantity or an hour it never comes with.
This synthesizer bins every column (a category column by its observed values, any other
column by quantiles), links the columns in the tree that keeps the most mutual information
between neighbours (the Chow–Liu tree), and learns each column's distribution given its
parent's bin. A row is sampled down the tree, bin by bin, then each value is drawn from the
real values of its bin, and the table's column kinds are applied.

It is written as any plug-in author would write one: against the public synthesizer
contract (``sdf.synthesis.api``) only, and mounted from the ``sdf.synthesizers``
entry-point group like the other built-ins.
ALGORITHM-HOOK[A1]: a network with more than one parent per column, or CTGAN once deep
models are allowed.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from .api import SynthesizerInfo, TableData, apply_kinds

# one row's worth of count, spread over a column's bins, is added to each parent bin's distribution: a pair
# never seen keeps a small chance (at most 1 in the parent bin's rows + 1), and a rare parent bin is not all noise
SMOOTHING = 1.0


class BayesianNetworkTable:
    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="bayesian-network",
        produces="table",
        needs_fit=True,
        description="A Chow–Liu tree over binned columns: each column drawn given the column it depends on most",
    )
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {"bins": (2, 100)}

    def __init__(self, *, seed: int = 7, bins: int = 20) -> None:
        self.bins = bins
        self._rng = np.random.default_rng(seed)
        self._data: TableData | None = None
        self._order: list[int] = []  # columns, each after its parent
        self._parent: dict[int, int | None] = {}
        self._tables: dict[int, np.ndarray] = {}  # column -> P(bin | parent's bin), parent bins × bins
        self._values: list[list[np.ndarray]] = []  # column -> bin -> the real values in it

    def fit(self, data: TableData) -> BayesianNetworkTable:
        """Learn the tree and its distributions from ``data``; ``ValueError`` for a ``nan`` in it."""
        self._data = data
        rows = np.asarray(data.rows, dtype=float).reshape(len(data.rows), len(data.columns))
        if np.isnan(rows).any():
            raise ValueError("bayesian-network: the table has a nan; fill or drop it first")
        if not len(rows):
            return self
        kinds = data.kinds or ("real",) * len(data.columns)
        codes, self._values = [], []
        for j, kind in enumerate(kinds):
            code, values = _binned(rows[:, j], self.bins, kind == "category")
            codes.append(code)
            self._values.append(values)
        self._parent, self._order = _chow_liu([(c, len(v)) for c, v in zip(codes, self._values)])
        self._tables = {}
        for j in self._order:
            size = len(self._values[j])
            p = self._parent[j]
            if p is None:
                counts = np.bincount(codes[j], minlength=size)[None, :].astype(float)
            else:
                counts = np.zeros((len(self._values[p]), size))
                np.add.at(counts, (codes[p], codes[j]), 1.0)
            counts += SMOOTHING / size
            self._tables[j] = counts / counts.sum(axis=1, keepdims=True)
        return self

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[tuple[float, ...]]:
        """``n`` rows (default: as many as were fitted); empty when fitted on no rows."""
        if self._data is None:
            raise RuntimeError("bayesian-network: call fit() before sample()")
        n = len(self._data.rows) if n is None else n
        if not self._data.rows or n == 0:
            return []
        rng = np.random.default_rng(seed) if seed is not None else self._rng
        width = len(self._data.columns)
        bins = np.zeros((n, width), dtype=int)
        out = np.zeros((n, width))
        for j in self._order:
            p = self._parent[j]
            size = len(self._values[j])
            if p is None:
                bins[:, j] = rng.choice(size, size=n, p=self._tables[j][0])
            else:  # each row's own distribution, given its parent's bin: inverse-CDF draws, one per row
                cdf = np.cumsum(self._tables[j][bins[:, p]], axis=1)
                bins[:, j] = np.minimum((rng.random(n)[:, None] > cdf).sum(axis=1), size - 1)
            for b, values in enumerate(self._values[j]):
                picked = bins[:, j] == b
                if picked.any():
                    out[picked, j] = rng.choice(values, size=int(picked.sum()))
        return apply_kinds([tuple(float(v) for v in row) for row in out], self._data)


def _binned(x: np.ndarray, bins: int, category: bool) -> tuple[np.ndarray, list[np.ndarray]]:
    """Each value's bin, and the real values of each bin: one bin per observed value for a category column or a
    column with at most ``bins`` of them, otherwise up to ``bins`` quantile bins."""
    levels = np.unique(x)
    if category or len(levels) <= bins:
        code = np.searchsorted(levels, x)
        return code, [x[code == b] for b in range(len(levels))]
    edges = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)[1:-1]))
    code = np.searchsorted(edges, x, side="right")
    kept = np.unique(code)  # a quantile edge can leave a bin empty: renumber the bins that hold values
    code = np.searchsorted(kept, code)
    return code, [x[code == b] for b in range(len(kept))]


def _chow_liu(columns: list[tuple[np.ndarray, int]]) -> tuple[dict[int, int | None], list[int]]:
    """The maximum spanning tree of the columns' pairwise mutual information, rooted at column 0: each column's
    parent, and the columns in an order where every parent comes first."""
    k = len(columns)
    mi = np.zeros((k, k))
    for a in range(k):
        for b in range(a + 1, k):
            mi[a, b] = mi[b, a] = _mutual_information(*columns[a], *columns[b])
    parent: dict[int, int | None] = {0: None}
    order = [0]
    best = {j: (mi[0, j], 0) for j in range(1, k)}
    while best:
        j = max(best, key=lambda c: (best[c][0], -c))  # ties go to the earlier column: the tree is repeatable
        parent[j] = best.pop(j)[1]
        order.append(j)
        for c in best:
            if mi[j, c] > best[c][0]:
                best[c] = (mi[j, c], j)
    return parent, order


def _mutual_information(a: np.ndarray, na: int, b: np.ndarray, nb: int) -> float:
    joint = np.zeros((na, nb))
    np.add.at(joint, (a, b), 1.0)
    joint /= joint.sum()
    outer = joint.sum(axis=1, keepdims=True) @ joint.sum(axis=0, keepdims=True)
    held = joint > 0
    return float((joint[held] * np.log(joint[held] / outer[held])).sum())
