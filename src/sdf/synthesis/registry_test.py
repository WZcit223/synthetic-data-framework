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


class NeedsAbsentChild(ShuffleSeries):
    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        "needs-absent-child", "series", True, "x", requires=("no_such_parent_pkg.backend",)
    )


def test_a_missing_dotted_requirement_is_listed_not_raised(monkeypatch):
    monkeypatch.setattr(
        registry_module, "entry_points", _fake_entry_points(("needs-absent-child", f"{__name__}:NeedsAbsentChild"))
    )
    reg = default_registry()
    assert reg.names() == [] and reg.unavailable() == {"needs-absent-child": "needs no_such_parent_pkg.backend"}


class InfoIsNone:
    info = None


class RequiresIsAString(ShuffleSeries):
    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("requires-a-string", "series", True, "x", requires="numpy")  # type: ignore[arg-type]


class NeedsConfig(ShuffleSeries):
    info: ClassVar[SynthesizerInfo] = SynthesizerInfo("needs-config", "series", True, "x")

    def __init__(self, window: int) -> None:
        super().__init__()


def test_malformed_plug_in_metadata_is_listed_not_raised(monkeypatch):
    monkeypatch.setattr(
        registry_module,
        "entry_points",
        _fake_entry_points(
            ("info-is-none", f"{__name__}:InfoIsNone"),
            ("requires-a-string", f"{__name__}:RequiresIsAString"),
            ("needs-config", f"{__name__}:NeedsConfig"),
        ),
    )
    reg = default_registry()
    problems = reg.unavailable()
    assert reg.names() == [] and sorted(problems) == ["info-is-none", "needs-config", "requires-a-string"]
    assert "no SynthesizerInfo" in problems["info-is-none"]
    assert "tuple of module names" in problems["requires-a-string"]
    assert "needs a default" in problems["needs-config"] and "window" in problems["needs-config"]


def test_a_plug_in_cannot_take_a_built_in_name(monkeypatch):
    from importlib.metadata import EntryPoint

    class FakeDist:
        def __init__(self, name):
            self.name = name

    def ep(name, value, dist):
        e = EntryPoint(name=name, value=value, group=registry_module.ENTRY_POINT_GROUP)
        return e._for(FakeDist(dist)) if hasattr(e, "_for") else e

    plugin = ep("seasonal-profile", f"{__name__}:ShuffleSeries", "vendor-pkg")
    builtin = ep("seasonal-profile", "sdf.synthesis.fit:FittedSeasonalDemand", registry_module.DISTRIBUTION)
    if plugin.dist is None:
        pytest.skip("EntryPoint cannot carry a distribution on this Python")
    for order in ([plugin, builtin], [builtin, plugin]):
        monkeypatch.setattr(registry_module, "entry_points", lambda group, order=order: order)
        reg = default_registry()
        assert reg.origin("seasonal-profile") == "builtin" and reg.info("seasonal-profile").name == "seasonal-profile"
        assert "seasonal-profile" not in reg.unavailable()
        assert "already provided by a builtin" in reg.unavailable()["seasonal-profile (vendor-pkg)"]

    # A built-in that cannot be mounted still reserves its name.
    unavailable_builtin = ep("needs-absent-child", f"{__name__}:NeedsAbsentChild", registry_module.DISTRIBUTION)
    squatter = ep("needs-absent-child", f"{__name__}:ShuffleSeries", "vendor-pkg")
    monkeypatch.setattr(registry_module, "entry_points", lambda group: [squatter, unavailable_builtin])
    reg = default_registry()
    assert reg.names() == []
    assert reg.unavailable()["needs-absent-child"] == "needs no_such_parent_pkg.backend"
    assert "an unavailable built-in" in reg.unavailable()["needs-absent-child (vendor-pkg)"]


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
    [
        ("Bad Name", "series", "lower-case words joined by dashes"),
        ("ok-name\n", "series", "lower-case words joined by dashes"),
        ("ok-name", "image", "produces must be one of"),
    ],
)
def test_metadata_is_validated(name, produces, message):
    bad = type("Bad", (ShuffleSeries,), {"info": SynthesizerInfo(name, produces, True, "x")})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=message):
        SynthesizerRegistry().register(bad)


def test_runtime_registration_checks_requires():
    with pytest.raises(ValueError, match="needs no_such_parent_pkg.backend"):
        SynthesizerRegistry().register(NeedsAbsentChild)
    with pytest.raises(TypeError, match="tuple of module names"):
        SynthesizerRegistry().register(RequiresIsAString)


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
def test_gaussian_copula_matches_the_fitted_marginals():
    rng = random.Random(0)
    rows = [(x, 2 * x + rng.gauss(0, 1)) for x in (rng.gauss(10, 2) for _ in range(400))]
    model = default_registry().create("gaussian-copula", seed=1).fit(TableData(rows=rows, columns=("x", "y")))
    sample = model.sample(4000)
    xs, ys = [r[0] for r in sample], [r[1] for r in sample]
    assert abs(sum(xs) / len(xs) - 10) < 0.3 and abs(sum(ys) / len(ys) - 20) < 0.6
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    corr = cov / (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    assert corr > 0.9  # the dependence survives, not just the marginals


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
