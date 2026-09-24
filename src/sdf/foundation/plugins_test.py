"""The shared plug-in loader, tested once on a minimal catalogue: what every catalogue inherits."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint
from typing import ClassVar

import pytest

from . import plugins as plugins_module
from .plugins import DISTRIBUTION, PluginRegistry


@dataclass(frozen=True)
class GadgetInfo:
    name: str
    requires: tuple[str, ...] = ()


class GadgetRegistry(PluginRegistry[object]):
    kind: ClassVar[str] = "gadget"
    info_type: ClassVar[type] = GadgetInfo
    group: ClassVar[str] = "sdf.test-gadgets"
    made_by: ClassVar[str] = "make(name)"

    def check(self, cls):
        if getattr(cls, "broken", False):
            raise ValueError(f"{cls.info.name}: broken on purpose")
        super().check(cls)


class Widget:
    info: ClassVar[GadgetInfo] = GadgetInfo("widget")


class OtherWidget:
    info: ClassVar[GadgetInfo] = GadgetInfo("widget")


class Sprocket:
    info: ClassVar[GadgetInfo] = GadgetInfo("sprocket")


class NeedsArgument:
    info: ClassVar[GadgetInfo] = GadgetInfo("needs-argument")

    def __init__(self, path):
        self.path = path


class Broken:
    info: ClassVar[GadgetInfo] = GadgetInfo("broken")
    broken = True


class NeedsAbsent:
    info: ClassVar[GadgetInfo] = GadgetInfo("needs-absent", requires=("no_such_parent_pkg.backend",))


class BadRequires:
    info: ClassVar[GadgetInfo] = GadgetInfo("bad-requires", requires="numpy")  # a string, not a tuple


class NoInfo:
    pass


def entry_point(name: str, value: str, dist: str | None = None) -> EntryPoint:
    ep = EntryPoint(name=name, value=value, group=GadgetRegistry.group)
    if dist is None:
        return ep

    class FakeDist:
        def __init__(self, n):
            self.name = n

    return ep._for(FakeDist(dist)) if hasattr(ep, "_for") else ep


def with_distributions() -> None:
    if entry_point("x", f"{__name__}:Widget", "pkg").dist is None:
        pytest.skip("EntryPoint cannot carry a distribution on this Python")


# -- register ---------------------------------------------------------------------------------------


def test_register_runs_the_shared_checks_then_the_kind_s_own():
    reg = GadgetRegistry()
    with pytest.raises(TypeError, match=r"'NoInfo' has no GadgetInfo `info` class attribute"):
        reg.register(NoInfo)
    bad_name = type("BadName", (), {"info": GadgetInfo("Bad_Name")})
    with pytest.raises(ValueError, match=r"gadget name 'Bad_Name' must be lower-case words joined by dashes"):
        reg.register(bad_name)
    with pytest.raises(
        TypeError,
        match=r"needs-argument: every constructor argument needs a default so make\(name\) works; missing \['path'\]",
    ):
        reg.register(NeedsArgument)
    with pytest.raises(ValueError, match="broken: broken on purpose"):  # the subclass's check
        reg.register(Broken)
    with pytest.raises(ValueError, match=r"^needs no_such_parent_pkg.backend$"):  # a missing parent package is missing
        reg.register(NeedsAbsent)
    with pytest.raises(TypeError, match="info.requires must be a tuple of module names"):
        reg.register(BadRequires)
    assert reg.names() == []


def test_a_name_is_taken_once_unless_replaced():
    reg = GadgetRegistry()
    reg.register(Widget)
    with pytest.raises(ValueError, match=r"gadget 'widget' is already registered; pass replace=True to override"):
        reg.register(OtherWidget)
    reg.register(OtherWidget, replace=True, origin="plugin")
    assert reg.info("widget") is OtherWidget.info and reg.origin("widget") == "plugin"


def test_reading_the_catalogue():
    reg = GadgetRegistry()
    reg.register(Widget, origin="builtin")
    reg.register(Sprocket)
    assert reg.names() == ["sprocket", "widget"]
    assert reg.names(origin="builtin") == ["widget"] and reg.names(origin="runtime") == ["sprocket"]
    with pytest.raises(KeyError, match=r"unknown gadget 'nope'; choose from \['sprocket', 'widget'\]"):
        reg.info("nope")
    reg.unavailable()["x"] = "y"  # a copy: the catalogue's own record is untouched
    assert reg.unavailable() == {}


# -- entry points -----------------------------------------------------------------------------------


def test_built_ins_and_plug_ins_mount_with_their_origin(monkeypatch):
    with_distributions()
    eps = [
        entry_point("sprocket", f"{__name__}:Sprocket", "vendor-pkg"),
        entry_point("widget", f"{__name__}:Widget", DISTRIBUTION),
    ]
    monkeypatch.setattr(plugins_module, "entry_points", lambda group: eps if group == GadgetRegistry.group else [])
    reg = GadgetRegistry()
    assert reg.load_entry_points() == ["widget", "sprocket"]  # built-ins first
    assert reg.origin("widget") == "builtin" and reg.origin("sprocket") == "plugin"
    assert reg.load_entry_points() == [] and reg.unavailable() == {}  # loading again changes nothing


def test_loading_again_with_extras_changes_nothing(monkeypatch):
    monkeypatch.setattr(
        plugins_module, "entry_points", lambda group: [entry_point("widget", f"{__name__}:Widget [extra]")]
    )
    reg = GadgetRegistry()
    assert reg.load_entry_points() == ["widget"]
    assert reg.load_entry_points() == [] and reg.unavailable() == {}


def test_a_plug_in_never_takes_a_built_in_name_and_the_reason_names_the_holder(monkeypatch):
    with_distributions()
    builtin = entry_point("widget", f"{__name__}:Widget", DISTRIBUTION)
    squatter = entry_point("widget", f"{__name__}:OtherWidget", "vendor-pkg")
    for order in ([squatter, builtin], [builtin, squatter]):
        monkeypatch.setattr(plugins_module, "entry_points", lambda group, order=order: order)
        reg = GadgetRegistry()
        reg.load_entry_points()
        assert reg.info("widget") is Widget.info and reg.origin("widget") == "builtin"
        assert reg.unavailable() == {
            "widget (vendor-pkg)": f"name already provided by a builtin gadget ({__name__}); {__name__}:OtherWidget not mounted"
        }
    # a built-in that cannot mount still reserves its name
    absent = entry_point("needs-absent", f"{__name__}:NeedsAbsent", DISTRIBUTION)
    squatter = entry_point("needs-absent", f"{__name__}:Sprocket", "vendor-pkg")
    monkeypatch.setattr(plugins_module, "entry_points", lambda group: [squatter, absent])
    reg = GadgetRegistry()
    assert reg.load_entry_points() == []
    assert reg.unavailable() == {
        "needs-absent": "needs no_such_parent_pkg.backend",
        "needs-absent (vendor-pkg)": f"name already provided by an unavailable built-in; {__name__}:Sprocket not mounted",
    }


def test_equal_names_from_two_plug_ins_resolve_by_distribution_name(monkeypatch):
    with_distributions()
    a = entry_point("widget", f"{__name__}:Widget", "a-pkg")
    b = entry_point("widget", f"{__name__}:OtherWidget", "b-pkg")
    for order in ([a, b], [b, a]):
        monkeypatch.setattr(plugins_module, "entry_points", lambda group, order=order: order)
        reg = GadgetRegistry()
        reg.load_entry_points()
        assert reg.info("widget") is Widget.info  # a-pkg sorts first, on every run
        assert "a plugin gadget" in reg.unavailable()["widget (b-pkg)"]


def test_a_declared_plug_in_that_cannot_mount_is_listed_with_why(monkeypatch):
    eps = [
        entry_point("missing", "no_such_package.gadgets:Nope"),
        entry_point("no-info", f"{__name__}:NoInfo"),
        entry_point("wrong-name", f"{__name__}:Widget"),
        entry_point("needs-argument", f"{__name__}:NeedsArgument"),
        entry_point("broken", f"{__name__}:Broken"),
        entry_point("sprocket", f"{__name__}:Sprocket"),
    ]
    monkeypatch.setattr(plugins_module, "entry_points", lambda group: eps)
    reg = GadgetRegistry()
    assert reg.load_entry_points() == ["sprocket"]
    problems = reg.unavailable()
    assert problems["missing"].startswith("failed to load no_such_package.gadgets:Nope: ")
    assert problems["no-info"] == f"{__name__}:NoInfo has no GadgetInfo `info` class attribute"
    assert problems["wrong-name"] == "entry point name differs from info.name 'widget'"
    assert "constructor argument needs a default" in problems["needs-argument"]
    assert problems["broken"] == "broken: broken on purpose"
    with pytest.raises(KeyError, match=r"unknown gadget 'broken' \(broken: broken on purpose\)"):
        reg.info("broken")  # the reason travels with the refusal


def test_registering_a_listed_name_clears_its_reason(monkeypatch):
    monkeypatch.setattr(plugins_module, "entry_points", lambda group: [entry_point("widget", "no_such_package:W")])
    reg = GadgetRegistry()
    reg.load_entry_points()
    assert "widget" in reg.unavailable()
    reg.register(Widget)
    assert reg.unavailable() == {} and reg.origin("widget") == "runtime"


def test_another_group_can_be_named(monkeypatch):
    asked = []
    monkeypatch.setattr(plugins_module, "entry_points", lambda group: asked.append(group) or [])
    GadgetRegistry().load_entry_points()
    GadgetRegistry().load_entry_points("sdf.other")
    assert asked == ["sdf.test-gadgets", "sdf.other"]
