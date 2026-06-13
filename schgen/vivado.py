"""Generated Vivado project-creation TCL (downstream P2).

``schgen vivado`` (also run by ``schgen board``) writes
``carrier/fpga/create_project.tcl`` — the one script that turns the orphan
``Zynq_Carrier_pins.xdc`` into a sourceable Vivado project:

    cd carrier/fpga && vivado -mode batch -source create_project.tcl

It emits, in order:
- ``create_project`` + ``set_property part`` with the EXACT device string
  schgen already knows for the XDC — sourced the SAME way ``schgen xdc``
  gets it (``schgen.som_interface.extract_zynq`` on the SoM project, the
  ``value`` field, e.g. ``XC7Z020-CLG484``).  NOTHING is hard-coded; if the
  SoM device changes, the XDC and this TCL move together.
- ``read_xdc`` of the generated pin constraints by RELATIVE path (the .tcl
  and the .xdc live side-by-side in ``carrier/fpga/``), so the project picks
  up every PACKAGE_PIN/IOSTANDARD the XDC already proved against the
  hardware.
- a commented Zynq7 PS instantiation stub (``create_bd_design`` +
  ``create_bd_cell`` + a TODO to apply the PS preset), because the PS DDR /
  MIO preset is board-revision intent that does not live in the carrier
  netlist — left commented so ``source`` succeeds with zero PL design and the
  user opts in.
- the ``create_clock`` lines the XDC prints as templates: PROMOTED to real
  ``create_clock`` where a port binds to an MRCC/SRCC ball AND a documented
  period exists (``KNOWN_CLOCK_PERIODS_NS``); every other clock-capable port
  stays a commented ``# create_clock ... -period <ns>`` template exactly as
  in the XDC, so no fictitious timing constraint is ever asserted.

Deterministic: the device + pin set + clock list all come from the same
netlists the XDC reads, ordering is sorted, and no wall-clock timestamp is
emitted — re-running yields a byte-identical file.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from schgen import xdc
from schgen.som_interface import extract_zynq

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOM = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"
DEFAULT_CONTRACT = REPO_ROOT / "carrier" / "som_interface.json"
DEFAULT_OUT = REPO_ROOT / "carrier" / "fpga" / "create_project.tcl"
DEFAULT_XDC = REPO_ROOT / "carrier" / "fpga" / "Zynq_Carrier_pins.xdc"

# Vivado project + block-design names (stable identifiers, not timestamps).
PROJECT_NAME = "zynq_carrier"
BD_NAME = "system"
# The carrier mates a Zynq SoM; the PS IP is the Processing System 7.
PS_IP_VLNV = "xilinx.com:ip:processing_system7:5.5"

# Documented FIXED PL clock periods (ns), keyed by carrier PORT net name.
# A create_clock template is PROMOTED to a real constraint ONLY for a
# P-side MRCC/SRCC port whose net appears here with a known source period.
# It is INTENTIONALLY EMPTY: this carrier feeds its PL clock pins from
# source-synchronous / recovered sources (HDMI RX TMDS clock, camera D-PHY
# clock) and FPGA-driven outputs (LCD pixel clock), none of which has a
# fixed board-level oscillator period to assert.  Asserting a made-up period
# would be a fictitious timing constraint, so every clock-capable port stays
# a commented template (matching the XDC).  Add an entry here only when a
# real on-board oscillator with a known frequency drives that PL ball.
KNOWN_CLOCK_PERIODS_NS: dict[str, float] = {}


class VivadoError(ValueError):
    pass


def _rel(target: Path, start: Path) -> str:
    """POSIX relative path from the .tcl's directory to ``target`` (Vivado
    TCL is forward-slash on every platform)."""
    try:
        rel = Path(target).resolve().relative_to(start.resolve())
        return rel.as_posix()
    except ValueError:
        # Different roots: fall back to os-level relpath, still POSIX-ised.
        import os
        return Path(os.path.relpath(Path(target).resolve(),
                                    start.resolve())).as_posix()


def _fmt_period(p: float) -> str:
    """Stable period rendering: integer if whole, else trimmed decimal."""
    if p == int(p):
        return str(int(p))
    return f"{p:g}"


def generate(sheets, out_path: Path = DEFAULT_OUT, *,
             som_sch: Path = DEFAULT_SOM,
             contract_path: Path = DEFAULT_CONTRACT,
             xdc_path: Path = DEFAULT_XDC,
             refs: tuple[str, ...] = ("J1", "J2", "J3")) -> Path:
    """Build + write ``create_project.tcl``.

    The device string and the clock-capable port list are derived the SAME
    way ``schgen xdc`` derives them: ``extract_zynq`` for the ``value``, and a
    throwaway ``xdc.generate`` into a tempdir for the verified ``entries``
    (so the TCL and the committed XDC cannot disagree about which ports are
    MRCC/SRCC).  No XDC file is rewritten here.

    Raises :class:`VivadoError` if the XDC derivation fails (the project
    would be unsourceable) — surfaced as an :class:`xdc.XdcError` upstream.
    """
    live = extract_zynq(som_sch, jrefs=tuple(refs))
    device = live["value"]
    if not device:
        raise VivadoError(
            f"SoM Zynq {live['zynq_ref']} carries no value field in "
            f"{som_sch} — cannot determine the Vivado part")

    # Re-derive the EXACT pin entries the XDC emits, by running the proven
    # xdc generator into a tempdir (the committed XDC is left untouched).
    with tempfile.TemporaryDirectory(prefix="schgen_vivado_") as td:
        xres = xdc.generate(sheets, Path(td) / "pins.xdc",
                            som_sch=som_sch, contract_path=contract_path,
                            refs=refs)
    entries = xres.entries

    # Clock-capable P-side ports (the ones the XDC prints a create_clock
    # template for), sorted for determinism.
    clk_entries = sorted(
        (e for e in entries if e.clock_capable and e.p_side),
        key=lambda e: e.net)
    promoted = [e for e in clk_entries
                if e.net in KNOWN_CLOCK_PERIODS_NS]
    templated = [e for e in clk_entries
                 if e.net not in KNOWN_CLOCK_PERIODS_NS]

    xdc_rel = _rel(xdc_path, out_path.parent)

    lines: list[str] = []
    lines += [
        "#" * 78,
        "# create_project.tcl — GENERATED by `schgen vivado`. DO NOT EDIT.",
        "#",
        "# One-shot Vivado project from the schgen-generated pin constraints:",
        "#     cd carrier/fpga",
        "#     vivado -mode batch -source create_project.tcl",
        "#",
        f"# Device: {device} ({live['zynq_ref']} on the SoM, "
        f"live kicad-cli extraction — never hard-coded)",
        f"# Pin constraints: {xdc_rel} "
        f"({len(entries)} ports, generated by `schgen xdc`)",
        "# Determinism: device + pins + clocks all derive from the SoM "
        "netlist;",
        "# no timestamps, sorted ordering -> byte-identical on re-run.",
        "#" * 78,
        "",
        "# Resolve paths relative to THIS script so it sources from any cwd.",
        "set script_dir [file dirname [file normalize [info script]]]",
        "",
        f"set project_name {PROJECT_NAME}",
        f"set part {device}",
        "",
        "# ---- project ----------------------------------------------------",
        "# In-memory project under the script dir; -force overwrites a prior "
        "run.",
        "create_project -force $project_name $script_dir/$project_name "
        "-part $part",
        "set_property part $part [current_project]",
        "",
        "# ---- pin + IO constraints (schgen xdc, proved against the SoM) --",
        f'set xdc_file [file normalize $script_dir/{xdc_rel}]',
        "if {![file exists $xdc_file]} {",
        '    error "missing constraints: $xdc_file — run `schgen xdc` '
        '(or `schgen board`) first"',
        "}",
        "add_files -fileset constrs_1 -norecurse $xdc_file",
        "read_xdc $xdc_file",
        "",
    ]

    # ---- create_clock section -------------------------------------------------
    lines.append("# ---- clocks -----------------------------------------------------")
    lines.append("# MRCC/SRCC-capable PL ports the XDC flags as clock candidates.")
    if promoted:
        lines.append("# Promoted to real constraints (documented fixed source "
                     "period):")
        for e in promoted:
            period = KNOWN_CLOCK_PERIODS_NS[e.net]
            lines.append(
                f"create_clock -name {e.net} -period {_fmt_period(period)} "
                f"[get_ports {{{e.net}}}]"
                f"  ;# {e.jpin} {e.pin_name} ({e.clock_capable})")
    if templated:
        lines.append(
            "# No documented fixed period for these (source-synchronous / "
            "recovered /")
        lines.append(
            "# FPGA-driven). Left as TEMPLATES — uncomment and set <ns> for "
            "the real")
        lines.append(
            "# source frequency before timing closure (matches the XDC "
            "templates).")
        for e in templated:
            lines.append(
                f"# create_clock -name {e.net} -period <ns> "
                f"[get_ports {{{e.net}}}]"
                f"  ;# {e.jpin} {e.pin_name} ({e.clock_capable})")
    if not clk_entries:
        lines.append("# (no clock-capable PL ports bound through "
                     f"{'/'.join(refs)})")
    lines.append("")

    # ---- Zynq7 PS stub --------------------------------------------------------
    lines += [
        "# ---- Zynq7 Processing System (PS) — COMMENTED STUB ---------------",
        "# The PS DDR/MIO preset is SoM-revision intent and does NOT live in",
        "# the carrier netlist, so the PS is left for you to instantiate.",
        "# Uncomment to start a block design with a PS7, then APPLY THE SoM'S",
        "# PS PRESET (DDR3 timing, MIO, clocks) before generating the "
        "wrapper.",
        "#",
        f"# create_bd_design {BD_NAME}",
        f"# set ps [create_bd_cell -type ip -vlnv {PS_IP_VLNV} "
        "processing_system7_0]",
        "# # TODO: apply the SoM PS7 preset (board-specific DDR3/MIO/clock "
        "config):",
        "# #   set_property -dict [list CONFIG.preset {<SoM_preset.xml or "
        "board file>}] $ps",
        "# #   or: apply_bd_automation -rule "
        "xilinx.com:bd_rule:processing_system7 \\",
        "# #         -config {make_external \"FIXED_IO, DDR\" apply_board_"
        "preset \"1\"} $ps",
        f"# validate_bd_design",
        f"# save_bd_design",
        f"# make_wrapper -files [get_files {BD_NAME}.bd] -top",
        f"# add_files -norecurse "
        "$script_dir/$project_name/$project_name.srcs/sources_1/bd/"
        f"{BD_NAME}/hdl/{BD_NAME}_wrapper.v",
        "",
        "puts \"schgen: project '$project_name' created for part $part; "
        "pin constraints loaded from [file tail $xdc_file].\"",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    out_path.write_text(text)
    return out_path


# ---- CLI ----------------------------------------------------------------------

def cmd_vivado(args: argparse.Namespace) -> int:
    from schgen.link import all_subsystem_paths, load_subsystem
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
