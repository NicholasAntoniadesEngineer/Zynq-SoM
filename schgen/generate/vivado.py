from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from schgen.core.project import PROJECT_ROOT
from schgen.core.som_interface import extract_zynq
from schgen.generate import xdc

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOM = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"
DEFAULT_CONTRACT = PROJECT_ROOT / "som_interface.json"
DEFAULT_OUT = PROJECT_ROOT / "fpga" / "create_project.tcl"
DEFAULT_XDC = PROJECT_ROOT / "fpga" / "Zynq_Carrier_pins.xdc"

PROJECT_NAME = "zynq_carrier"
BD_NAME = "system"
PS_IP_VLNV = "xilinx.com:ip:processing_system7:5.5"

KNOWN_CLOCK_PERIODS_NS: dict[str, float] = {}


class VivadoError(ValueError):
    pass


def _rel(target: Path, start: Path) -> str:
    try:
        rel = Path(target).resolve().relative_to(start.resolve())
        return rel.as_posix()
    except ValueError:
        import os
        return Path(os.path.relpath(Path(target).resolve(),
                                    start.resolve())).as_posix()


def _fmt_period(p: float) -> str:
    if p == int(p):
        return str(int(p))
    return f"{p:g}"


def generate(sheets, out_path: Path = DEFAULT_OUT, *,
             som_sch: Path = DEFAULT_SOM,
             contract_path: Path = DEFAULT_CONTRACT,
             xdc_path: Path = DEFAULT_XDC,
             refs: tuple[str, ...] = ("J1", "J2", "J3")) -> Path:
    live = extract_zynq(som_sch, jrefs=tuple(refs))
    device = live["value"]
    if not device:
        raise VivadoError(
            f"SoM Zynq {live['zynq_ref']} carries no value field in "
            f"{som_sch} — cannot determine the Vivado part")

    with tempfile.TemporaryDirectory(prefix="schgen_vivado_") as td:
        xres = xdc.generate(sheets, Path(td) / "pins.xdc",
                            som_sch=som_sch, contract_path=contract_path,
                            refs=refs)
    from schgen.core import native

    text = native.module().render_vivado(
        [(e.net, e.jpin, e.pin_name) for e in xres.entries],
        device, live["zynq_ref"], _rel(xdc_path, out_path.parent),
        list(refs), KNOWN_CLOCK_PERIODS_NS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return out_path


def cmd_vivado(args: argparse.Namespace) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    refs = tuple(r.strip() for r in args.refs.split(",") if r.strip())
    try:
        out = generate(sheets, args.output or DEFAULT_OUT,
                       som_sch=args.som or DEFAULT_SOM,
                       xdc_path=args.xdc or DEFAULT_XDC, refs=refs)
    except (VivadoError, xdc.XdcError) as exc:
        print(f"VIVADO: FAIL — {exc}")
        return 1
    n_clk = sum(1 for ln in out.read_text().splitlines()
                if ln.startswith("create_clock"))
    print(f"VIVADO: {out} ({n_clk} real create_clock lines)")
    return 0
