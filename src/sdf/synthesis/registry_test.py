"""Tests for the synthesizer registry and the built-ins behind the contract."""

from __future__ import annotations

import importlib.util
import random
from typing import ClassVar

import pytest

from . import registry as registry_module
from .api import SeriesData, SynthesizerInfo, TableData
from .registry import SynthesizerRegistry, default_registry
from .spec import GenerationSpec
from .warehouse import SyntheticWarehouse

BUILT_INS = ["bootstrap-table", "seasonal-profile", "warehouse-spec"]
SERIES = [10.0 + (i % 7) + (i * 37 % 11) for i in range(42)]
ROWS = [(float(i % 7), float(i % 5) + 0.5, float(i % 24), float(i % 7)) for i in range(60)]


class ShuffleSeries:
    """The contract's minimal plug-in (interfaces.md §2.2)."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="shuffle-series", produces="series", needs_fit=True, description="Random permutation of the fitted series"
    )

    def __init__(self, *, seed: int = 0) -> None:
        self._rng = random.Random(seed)
        self._values: list[float] = []

    def fit(self, data: SeriesData) -> ShuffleSeries:
        self._values = list(data.values)
        return self

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[float]:
        rng = random.Random(seed) if seed is not None else self._rng
        values = self._values[:]
        rng.shuffle(values)
        return values if n is None else values[:n]


def test_built_ins_are_mounted_from_our_entry_points():
    reg = default_registry()
    has_copula = importlib.util.find_spec("copulas") is not None
    assert reg.names(origin="builtin") == sorted(BUILT_INS + (["gaussian-copula"] if has_copula else []))
    assert all(reg.origin(n) == "builtin" for n in BUILT_INS)
    if not has_copula:
        assert reg.unavailable()["gaussian-copula"].startswith("needs copulas")
        with pytest.raises(KeyError, match=r"'gaussian-copula' \(needs copulas"):
            reg.create("gaussian-copula")


def _fake_entry_points(*specs):
    from importlib.metadata import EntryPoint

    eps = [EntryPoint(name=name, value=value, group=registry_module.ENTRY_POINT_GROUP) for name, value in specs]
    return lambda group: [ep for ep in eps if ep.group == group]


def test_a_packaged_plug_in_mounts_like_a_built_in(monkeypatch):
    monkeypatch.setattr(
        registry_module, "entry_points", _fake_entry_points(("shuffle-series", f"{__name__}:ShuffleSeries"))
    )
    reg = default_registry()
    assert reg.names() == ["shuffle-series"] and reg.origin("shuffle-series") == "plugin"
    assert sorted(reg.create("shuffle-series").fit(SeriesData(values=[1.0, 2.0], period=1)).sample()) == [1.0, 2.0]


def test_a_broken_plug_in_is_listed_not_raised(monkeypatch):
    monkeypatch.setattr(
        registry_module,
        "entry_points",
        _fake_entry_points(
            ("missing-module", "no_such_package.synth:Nope"),
            ("wrong-name", f"{__name__}:ShuffleSeries"),
            ("shuffle-series", f"{__name__}:ShuffleSeries"),
        ),
    )
    reg = default_registry()
    assert reg.names() == ["shuffle-series"]
    problems = reg.unavailable()
    assert problems["missing-module"].startswith("failed to load no_such_package.synth:Nope")
    assert "differs from info.name 'shuffle-series'" in problems["wrong-name"]


def test_info_describes_each_built_in():
    reg = default_registry()
    assert reg.info("seasonal-profile") == SynthesizerInfo(
        name="seasonal-profile",
        produces="series",
        needs_fit=True,
        description="Per-cycle mean profile × resampled multiplicative residuals",
    )
    assert [reg.info(n).produces for n in BUILT_INS] == ["table", "series", "warehouse"]
    assert reg.info("warehouse-spec").needs_fit is False


def test_contract_examples_run():
    reg = default_registry()
    series_model = reg.create("seasonal-profile", seed=7).fit(SeriesData(values=SERIES, period=7))
    assert len(series_model.sample(42)) == 42
    assert series_model.sample(42, seed=1) == series_model.sample(42, seed=1)
    table_model = reg.create("bootstrap-table", seed=7).fit(
        TableData(rows=ROWS, columns=("qty", "price", "hour", "weekday"))
    )
    rows = table_model.sample()
    assert len(rows) == len(ROWS) and all(len(r) == 4 for r in rows)
    world = reg.create("warehouse-spec", spec=GenerationSpec(n_skus=50, horizon_days=5)).sample()
    assert isinstance(world, SyntheticWarehouse) and len(world.skus) == 50


def test_a_plug_in_registers_and_runs():
    reg = default_registry()
    reg.register(ShuffleSeries)
    out = reg.create("shuffle-series", seed=3).fit(SeriesData(values=[1.0, 2.0, 3.0], period=1)).sample()
    assert sorted(out) == [1.0, 2.0, 3.0]
    assert reg.origin("shuffle-series") == "runtime" and "shuffle-series" not in default_registry().names()


def test_duplicate_name_needs_replace():
    reg = SynthesizerRegistry()
    reg.register(ShuffleSeries)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(ShuffleSeries)
    reg.register(ShuffleSeries, replace=True)


@pytest.mark.parametrize(
    ("name", "produces", "message"),
    [("Bad Name", "series", "lower-case words joined by dashes"), ("ok-name", "image", "produces must be one of")],
)
def test_metadata_is_validated(name, produces, message):
    bad = type("Bad", (ShuffleSeries,), {"info": SynthesizerInfo(name, produces, True, "x")})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=message):
        SynthesizerRegistry().register(bad)


def test_a_class_without_fit_or_sample_is_rejected():
    class NoSample:
        info = SynthesizerInfo("no-sample", "series", True, "x")

        def fit(self, data):
            return self

    with pytest.raises(TypeError, match="sample"):
        SynthesizerRegistry().register(NoSample)  # type: ignore[arg-type]


def test_a_class_without_info_is_rejected():
    class NoInfo:
        pass

    with pytest.raises(TypeError, match="SynthesizerInfo"):
        SynthesizerRegistry().register(NoInfo)  # type: ignore[arg-type]


def test_unknown_name_lists_the_valid_ones():
    with pytest.raises(KeyError, match=r"unknown synthesizer 'nope'; choose from \['bootstrap-table'"):
        default_registry().create("nope")
    with pytest.raises(KeyError, match="unknown synthesizer"):
        default_registry().info("nope")


@pytest.mark.parametrize("name", BUILT_INS)
def test_every_built_in_conforms_to_the_protocol(name):
    reg = default_registry()
    info = reg.info(name)
    assert info.name == name and info.name == info.name.lower() and " " not in info.name
    data = {"series": SeriesData(values=SERIES, period=7), "table": TableData(rows=ROWS, columns=("a", "b", "c", "d"))}
    config = {"spec": GenerationSpec(n_skus=20, horizon_days=3)} if info.produces == "warehouse" else {"seed": 1}
    model = reg.create(name, **config)
    assert model.fit(data.get(info.produces)) is model
    assert model.sample(seed=5) is not None
    if info.produces != "warehouse":
        assert model.sample(seed=5) == model.sample(seed=5)
        assert len(model.sample(3)) == 3 and model.sample(0) == []


def test_warehouse_spec_seed_overrides_the_spec():
    gen = default_registry().create("warehouse-spec", spec=GenerationSpec(n_skus=20, horizon_days=3, seed=1))
    assert gen.sample(seed=2).skus != gen.sample().skus
    with pytest.raises(ValueError, match="sized by its GenerationSpec"):
        gen.sample(5)


@pytest.mark.skipif(importlib.util.find_spec("copulas") is None, reason="needs the synthesis extra")
def test_gaussian_copula_samples_a_table():
    model = default_registry().create("gaussian-copula", seed=3).fit(TableData(rows=ROWS, columns=("a", "b", "c", "d")))
    rows = model.sample(10)
    assert len(rows) == 10 and all(len(r) == 4 for r in rows)
    assert model.sample(10, seed=4) == model.sample(10, seed=4)
    assert model.sample(10) != model.sample(10)  # the model's own stream continues


@pytest.mark.skipif(importlib.util.find_spec("copulas") is None, reason="needs the synthesis extra")
def test_gaussian_copula_leaves_numpy_global_state_alone():
    import numpy as np

    model = default_registry().create("gaussian-copula", seed=3).fit(TableData(rows=ROWS, columns=("a", "b", "c", "d")))
    np.random.seed(123)
    expected = np.random.random_sample(3)
    np.random.seed(123)
    model.sample(10, seed=9)
    model.sample(10)
    assert (np.random.random_sample(3) == expected).all()
