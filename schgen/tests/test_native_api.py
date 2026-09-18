"""Temporary migration guard: every direct native call must have an export."""
from __future__ import annotations

import ast
from pathlib import Path

from schgen.core import native


def test_direct_native_calls_have_exports():
    root = Path(__file__).resolve().parents[1]
    geom = native.module()
    missing = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text())
        aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "schgen.core"
            for alias in node.names if alias.name == "native"
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            if (isinstance(func, ast.Attribute) and func.attr == "module"
                    and isinstance(func.value, ast.Name)
                    and func.value.id in aliases and not hasattr(geom, node.attr)):
                missing.append(f"{path.relative_to(root)}:{node.lineno}: {node.attr}")
    assert not missing, "Missing native exports:\n" + "\n".join(missing)
