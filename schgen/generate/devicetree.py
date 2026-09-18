"""Temporary CLI/import adapter; device-tree extraction, gates and rendering are C++."""
from __future__ import annotations

import argparse
from pathlib import Path

from schgen.core import native
from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOM = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"
DEFAULT_CONTRACT = PROJECT_ROOT / "som_interface.json"
DEFAULT_OUT = PROJECT_ROOT / "firmware" / "carrier_pl.dtsi"


class DeviceTreeError(ValueError):
    pass


def generate(out: Path = DEFAULT_OUT, *,
             som_sch: Path = DEFAULT_SOM,
             contract_path: Path = DEFAULT_CONTRACT,
             refs: tuple[str, ...] = ("J1", "J2", "J3")) -> Path:
    try:
        text, _count = native.module().generate_devicetree(
            str(REPO_ROOT), str(PROJECT_ROOT), str(som_sch),
            str(contract_path), list(refs))
    except ValueError as exc:
        raise DeviceTreeError(str(exc)) from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


def cmd_devicetree(args: argparse.Namespace) -> int:
    out = generate(getattr(args, "output", None) or DEFAULT_OUT,
                   som_sch=getattr(args, "som", None) or DEFAULT_SOM)
    n_mio = sum(1 for line in out.read_text().splitlines()
                if line.lstrip().startswith("/* MIO"))
    print(f"DEVICETREE: {out} ({n_mio} PS MIO lines mapped)")
    return 0
