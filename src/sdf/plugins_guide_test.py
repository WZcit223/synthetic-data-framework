"""docs/PLUGINS.md's examples run as written: through the registry, the catalogue, a run and the API."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from sdf.application.datasets import default_datasets
from sdf.application.kpi import kpis
from sdf.simulation.world import World
from sdf.synthesis.api import Param
from sdf.synthesis.registry import default_registry
from sdf.synthesis.spec import GenerationSpec
from sdf.validation.evaluation import evaluate

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "PLUGINS.md"


def example(tag: str) -> type:
    """Execute the guide's code block marked ``# plugins-example: <tag>`` and return the class it defines."""
    blocks = re.findall(r"```python\n(# plugins-example: (\w+)\n.*?)```", GUIDE.read_text(encoding="utf-8"), re.S)
    code = next(src for src, name in blocks if name == tag)
    namespace: dict = {"__name__": f"plugins_guide_{tag}"}
    exec(compile(code, f"{GUIDE.name}:{tag}", "exec"), namespace)  # noqa: S102 - the repository's own guide
    return next(
        v
        for v in namespace.values()
        if isinstance(v, type) and hasattr(v, "info") and v.__module__ == namespace["__name__"]
    )


def test_the_guide_declares_its_examples_under_their_own_names():
    synth, dataset = example("synthesizer"), example("dataset")
    blocks = re.findall(r"```toml\n(.*?)```", GUIDE.read_text(encoding="utf-8"), re.S)
    toml = tomllib.loads(blocks[0])["project"]["entry-points"]
    assert toml["sdf.synthesizers"] == {synth.info.name: "my_plugins.series:MovingAverageSeries"}
    assert toml["sdf.datasets"] == {dataset.info.name: "my_plugins.tables:StockByZone"}


def test_the_synthesizer_example_mounts_publishes_its_parameters_and_runs():
    synthesizers = default_registry()
    synthesizers.register(example("synthesizer"))
    assert synthesizers.params("moving-average") == (Param("seed", "int", 7), Param("window", "int", 5, min=1, max=48))
    run = evaluate("moving-average", source="sample", params={"window": 7}, registry=synthesizers)
    assert (run.kind, run.params, run.repeatable) == ("series", {"seed": 7, "window": 7}, True)
    assert 0 <= run.metrics["fidelity_score"] <= 100
    assert evaluate("moving-average", source="sample", params=run.params, registry=synthesizers).table == run.table
    with pytest.raises(ValueError, match="window must be from 1 to 48"):
        evaluate("moving-average", source="sample", params={"window": 0}, registry=synthesizers)


def test_the_dataset_example_mounts_and_adds_up():
    datasets = default_datasets()
    datasets.register(example("dataset"))
    world = World.generate(GenerationSpec())
    table = datasets.build("stock-by-zone", world)
    assert [f.name for f in table.info.fields] == ["category", "zone", "on_hand"]
    assert sum(r[2] for r in table.rows) == kpis(world.registry).total_on_hand


def test_the_examples_are_served_by_the_api():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from sdf.api.app import create_app

    synthesizers, datasets = default_registry(), default_datasets()
    synthesizers.register(example("synthesizer"))
    datasets.register(example("dataset"))
    client = TestClient(create_app(synthesizers=synthesizers, datasets=datasets))
    listed = {s["name"]: s for s in client.get("/api/v1/synthesizers").json()["synthesizers"]}
    assert [p["name"] for p in listed["moving-average"]["params"]] == ["seed", "window"]
    res = client.post(
        "/api/v1/synthesis/runs", json={"synthesizer": "moving-average", "source": "sample", "params": {"window": 7}}
    )
    assert res.status_code == 200 and res.json()["repeatable"] is True
    assert client.get("/api/v1/datasets/stock-by-zone").status_code == 200
