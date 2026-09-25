from __future__ import annotations

import argparse
from pathlib import Path
from schgen.core import native
from schgen.core.project import PROJECT_ROOT
from schgen.generate import _native_docs

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_ROOT / "docs" / "BRINGUP.md"


def missing_requirements() -> list[str]:
    return _native_docs.missing("manual")


def generate(out: Path = DEFAULT_OUT) -> Path:
    text = native.module().firmware_docs_render(*_native_docs.inputs(), "manual")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


def cmd_manual(args: argparse.Namespace) -> int:
    missing = missing_requirements()
    if missing:
        print(f"BRINGUP MANUAL: SKIP — project has no {', '.join(missing)}")
        return 1
    out = generate(getattr(args, "output", None) or DEFAULT_OUT)
    lines = out.read_text().count("\n")
    print(f"BRINGUP MANUAL: {out} ({lines} lines)")
    return 0
