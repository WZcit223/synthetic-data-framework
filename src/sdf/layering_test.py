"""Layer-direction test: no module imports a module from a higher layer.

Ranks (lower may not import higher):
foundation 0 · synthesis 1 · observability 1 · application 2 · workflow 3 · api 4 · cli 4.
``api`` and ``cli`` are peers that must not import each other. Re-export
shims are not allowed, so every edge the parser sees is a real dependency.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent
RANK = {"foundation": 0, "synthesis": 1, "observability": 1, "application": 2, "workflow": 3, "api": 4, "cli": 4}


def _layer(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def _module_name(path: Path) -> str:
    rel = path.relative_to(PACKAGE.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve(importer: str, node: ast.ImportFrom, is_package: bool) -> str | None:
    if node.level == 0:
        return node.module if node.module and node.module.startswith("sdf") else None
    base = importer.split(".")
    if not is_package:
        base = base[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def _edges():
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name.endswith("_test.py") or path.name == "conftest.py":
            continue
        importer = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("sdf."):
                        yield importer, alias.name
            elif isinstance(node, ast.ImportFrom):
                target = _resolve(importer, node, path.name == "__init__.py")
                if target and target != "sdf":
                    yield importer, target


def test_no_module_imports_a_higher_layer():
    violations = [
        f"{importer} -> {target}" for importer, target in _edges() if RANK[_layer(importer)] < RANK[_layer(target)]
    ]
    assert not violations, "\n".join(violations)


def test_api_and_cli_do_not_import_each_other():
    peers = [f"{i} -> {t}" for i, t in _edges() if {_layer(i), _layer(t)} == {"api", "cli"}]
    assert not peers, "\n".join(peers)


@pytest.mark.parametrize(
    ("module", "must_not_load"),
    [
        ("sdf.foundation.schema", "sdf.application"),
        ("sdf.synthesis.scenarios", "sdf.application"),
        ("sdf.synthesis.scenarios", "sdf.cli"),
        ("sdf.synthesis.materialise", "sdf.application"),
    ],
)
def test_importing_a_lower_layer_does_not_load_a_higher_one(module, must_not_load):
    code = f"import sys, {module}; assert '{must_not_load}' not in sys.modules, sorted(m for m in sys.modules if m.startswith('sdf'))"
    subprocess.run([sys.executable, "-c", code], check=True)
