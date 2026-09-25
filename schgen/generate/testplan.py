from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from schgen.core import native
from schgen.core.project import PROJECT_ROOT
from schgen.generate import bringup_facts as bf, _native_docs
from schgen.verify import spice, testpoints

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_ROOT / "docs" / "TEST_PLAN.md"


def _i2c_devices(sheets) -> list[tuple[int, str, str, bool]]:
    from schgen.verify.powertree import _native_sheets
    return native.module().testplan_i2c_devices(_native_sheets(sheets))



def generate(out: Path = DEFAULT_OUT, sheets=None) -> Path:
    rows = _native_docs.sheets() if sheets is None else sheets
    rows = sorted(rows, key=lambda sc: sc.name)
    probes = {net: ", ".join(locs) for net, locs in testpoints.check_coverage(rows).have.items()}
    text = native.module().firmware_testplan_render(
        *_native_docs.inputs(rows, need_stm32=False),
        asdict(spice.extract_checks(rows)), probes)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


def cmd_testplan(args: argparse.Namespace) -> int:
    out = generate(getattr(args, "output", None) or DEFAULT_OUT)
    lines = out.read_text().count("\n")
    print(f"TEST PLAN: {out} ({lines} lines)")
    return 0
