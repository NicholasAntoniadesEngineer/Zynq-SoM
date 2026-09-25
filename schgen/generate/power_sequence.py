from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from schgen.core import native
from schgen.core.project import PROJECT_ROOT
from schgen.verify import powertree
from schgen.verify.powertree import Result

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_ROOT / "docs" / "power_sequence.svg"
ALWAYS_ON_RAILS = ("+3V3_SC", "+5V_SOM")


def build(sheets, res: Result | None = None) -> dict:
    if res is None:
        res = powertree.analyze(sheets)
    return native.module().power_sequence_build(
        powertree._native_sheets(sheets), asdict(res), powertree._native_policy())


def render_svg(seq: dict, out: Path, *, ok: bool = True) -> Path:
    text = native.module().power_sequence_svg(seq, ok, powertree._native_policy())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


def generate(sheets, res: Result | None = None,
             out: Path = DEFAULT_OUT) -> Path:
    if res is None:
        res = powertree.analyze(sheets)
    seq = build(sheets, res)
    return render_svg(seq, out, ok=res.ok)


def cmd_power_sequence(args: argparse.Namespace) -> int:
    from schgen.core.link import (
        all_subsystem_paths,
        link,
        load_som_contract,
        load_subsystem,
    )
    names = [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    link(sheets, load_som_contract())
    out = generate(sheets, out=getattr(args, "output", None) or DEFAULT_OUT)
    seq = build(sheets)
    print(f"POWER SEQUENCE: {out.relative_to(REPO_ROOT)} "
          f"({len(seq['stage0'])} always-on, {len(seq['chain'])} chain, "
          f"{len(seq['modules'])} gated module rails)")
    return 0
