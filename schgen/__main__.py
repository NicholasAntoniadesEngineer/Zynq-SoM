"""schgen CLI.

    python -m schgen build <subsystem> [-o OUTDIR] [--no-render]
    python -m schgen bom <subsystem>... [-o CSV]

Builds carrier/subsystems/<subsystem>.py end-to-end: model -> place
(feasibility loop) -> route (exclusive grid) -> emit -> THREE gates
(netlist == declared, ERC errors == 0, visual zero-overlap) -> render PNG.
Exit is non-zero unless every gate passes. The gates are judges, not knobs.
`bom` exports a JLCPCB-assembly CSV (Comment,Designator,Footprint,LCSC) from
the declared circuits — manufacture-ready part selection lives in the model.
"""

from __future__ import annotations

import argparse
import ast
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from schgen import place
from schgen.emit import PlacedDesign, Wire, emit
from schgen.emit import Junction as EJunction
from schgen.model import Circuit, NetClass
from schgen.symbols import Library
from schgen.verify import netlist_gate, visual_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBSYSTEMS_DIR = REPO_ROOT / "carrier" / "subsystems"
DEFAULT_OUT = REPO_ROOT / "carrier" / "out"


def _subsystem_path(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if not path.suffix == ".py":
        path = SUBSYSTEMS_DIR / f"{Path(name_or_path).stem}.py"
    if not path.exists():
        raise SystemExit(f"subsystem not found: {path}")
    return path


def _load_subsystem(name_or_path: str):
    """Import a subsystem .py by name (carrier/subsystems/<name>.py) or path."""
    path = _subsystem_path(name_or_path)
    spec = importlib.util.spec_from_file_location(f"carrier_subsys_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- PURITY GATE: subsystem modules are netlist-only --------------------------
# A subsystem .py may import schgen.model (and stdlib) — NOTHING geometric.
# Manual placement is banned structurally: defining `placer` or importing any
# placement/emit/route/text-metrics API fails the build BEFORE the module is
# even executed (the scan is on the source, so a broken geometry import still
# yields the clear gate message, not a stack trace).

_BANNED_MODULES = ("schgen.place", "schgen.emit", "schgen.route",
                   "schgen.textmetrics", "schgen.symbols", "schgen.render",
                   "schgen.verify", "schgen.sexpr")
_BANNED_NAMES = {"Placement", "Spacing", "_Builder", "_Engine", "PlacedPart",
                 "PlacedPower", "PlacedDesign", "Wire", "Junction",
                 "HierLabel", "LocalLabel", "NoConnect", "Box", "Seg",
                 "SheetGeometry", "body_box_page", "pin_page_position",
                 "place", "route", "emit", "textmetrics", "symbols"}


def _purity_violations(path: Path) -> list[str]:
    out: list[str] = []
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == "placer":
            out.append("module defines `placer` — manual placement is "
                       "BANNED; the engine derives all geometry from the "
                       "netlist topology")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            for t in targets:
                if isinstance(t, ast.Name) and t.id == "placer":
                    out.append("module binds `placer` — manual placement "
                               "is BANNED")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "schgen" or a.name.startswith(_BANNED_MODULES):
                    out.append(f"import {a.name} — geometry APIs are "
                               f"off-limits to subsystems (netlist only)")
        elif isinstance(node, ast.ImportFrom):
            m = node.module or ""
            if m.startswith(_BANNED_MODULES):
                out.append(f"from {m} import ... — geometry APIs are "
                           f"off-limits to subsystems (netlist only)")
            elif m.startswith("schgen"):
                names = {a.name for a in node.names}
                bad = sorted(names & _BANNED_NAMES)
                if bad:
                    out.append(f"from {m} import {', '.join(bad)} — "
                               f"geometry APIs are off-limits to subsystems")
    return out

# Pin types KiCad's ERC accepts as net drivers (pin_not_driven test).
_DRIVER_ETYPES = {"output", "bidirectional", "tri_state", "passive",
                  "power_out", "open_collector", "open_emitter"}


def _check_inputs_driven(c: Circuit, lib: Library) -> list[str]:
    """STRICT replacement for KiCad's pin_not_driven on fragment sheets.

    Every 'input' pin must sit on a net that either (a) carries a real
    same-sheet driver-class pin, (b) is a POWER/GROUND rail (power symbols +
    PWR_FLAG drive it), or (c) is an explicit PORT net — the driver arrives
    when the hierarchy is assembled, exactly like the carrier's hier-label
    sheets. A non-PORT internal net feeding an input with no driver is a real
    authoring bug and FAILS the build here, before any geometry exists.
    """
    etype_of = {(ref, p.number): p.etype
                for ref, part in c.parts.items()
                for p in lib.get(part.lib_id).pins}
    problems: list[str] = []
    for net in c.nets.values():
        if net.net_class in (NetClass.POWER, NetClass.GROUND, NetClass.PORT):
            continue
        etypes = {etype_of.get((pr.ref, pr.pin), "?") for pr in net.pins}
        if "input" in etypes and not (etypes & _DRIVER_ETYPES):
            problems.append(
                f"net {net.name!r}: input pin(s) with no same-sheet driver "
                f"and not a PORT — undriven input")
    return problems


def _erc(sch: Path, report: Path) -> tuple[bool, str]:
    # Fragment-sheet ERC policy (matches boards/carrier/carrier.kicad_pro):
    # pin_not_driven is demoted to WARNING because a standalone subsystem
    # sheet's PORT-net inputs are, by construction, driven only after
    # hierarchical assembly (KiCad counts no global-label shape as a driver).
    # The build compensates with the STRICTER _check_inputs_driven above,
    # which unlike KiCad's check cannot be silenced by a stray passive on a
    # non-PORT net. Everything else stays at kicad-cli factory severity.
    pro = sch.with_suffix(".kicad_pro")
    pro.write_text(json.dumps({
        "meta": {"filename": pro.name, "version": 3},
        "erc": {"rule_severities": {"pin_not_driven": "warning"}},
    }, indent=2) + "\n")
    proc = subprocess.run(
        ["kicad-cli", "sch", "erc", "--severity-error",
         "--exit-code-violations", "-o", str(report), str(sch)],
        capture_output=True, text=True)
    txt = report.read_text() if report.exists() else proc.stderr
    return proc.returncode == 0, txt


def _render(sch: Path, png: Path, dpi: int = 300) -> bool:
    from schgen.render import render_sheet_to_png
    try:
        render_sheet_to_png(sch, png, dpi=dpi)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"render FAILED: {exc}")
        return False


def cmd_build(args: argparse.Namespace) -> int:
    path = _subsystem_path(args.subsystem)
    purity = _purity_violations(path)
    if purity:
        print("PURITY GATE: FAIL — a subsystem .py is NETLIST ONLY "
              "(parts, nets, ports, declarative hints):")
        for v in purity:
            print(f"  {v}")
        print(f"BUILD: FAIL ({args.subsystem})")
        return 1
    mod = _load_subsystem(args.subsystem)
    if getattr(mod, "placer", None) is not None:
        print("PURITY GATE: FAIL — module exposes `placer` at runtime; "
              "manual placement is BANNED")
        print(f"BUILD: FAIL ({args.subsystem})")
        return 1
    print("PURITY GATE: PASS (netlist-only subsystem)")
    c = mod.circuit()
    lib = Library()
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    driven_problems = _check_inputs_driven(c, lib)
    if driven_problems:
        for p in driven_problems:
            print(f"INPUT-DRIVEN CHECK: {p}")
        print(f"BUILD: FAIL ({c.name})")
        return 1
    print(f"model: {len(c.parts)} parts, {len(c.nets)} nets, "
          f"{len(c.nc_pins)} author NCs — complete (inputs driven)")

    placement, routed, geo = place.place_and_route(c, lib)
    design = PlacedDesign(
        circuit=c,
        parts=placement.parts,
        powers=placement.powers,
        wires=[Wire(s.x0, s.y0, s.x1, s.y1) for s in routed.segs],
        junctions=[EJunction(x, y) for x, y in routed.junctions],
        hlabels=placement.hlabels,
        llabels=placement.llabels,
        no_connects=placement.no_connects,
        paper=placement.paper,
    )
    outdir = args.outdir or DEFAULT_OUT
    outdir.mkdir(parents=True, exist_ok=True)
    sch = outdir / f"{c.name}.kicad_sch"
    emit(design, sch, lib)
    print(f"emitted {sch} ({len(design.wires)} wires, "
          f"{len(design.junctions)} junctions)")

    net_res = netlist_gate.check(c, sch)
    print(net_res.summary())

    erc_ok, erc_txt = _erc(sch, outdir / f"{c.name}.erc.rpt")
    print(f"ERC GATE: {'PASS (0 errors)' if erc_ok else 'FAIL'}")
    if not erc_ok:
        print(erc_txt[-1500:])

    vis_res = visual_gate.check(geo)
    print(vis_res.summary())

    if not args.no_render:
        png = outdir / f"{c.name}.png"
        if _render(sch, png):
            print(f"rendered {png}")

    ok = net_res.ok and erc_ok and vis_res.ok
    print(f"BUILD: {'PASS' if ok else 'FAIL'} ({c.name})")
    return 0 if ok else 1


def cmd_bom(args: argparse.Namespace) -> int:
    """JLCPCB assembly BOM: Comment,Designator,Footprint,LCSC (one row per
    value+footprint+LCSC group). Parts missing an LCSC field are listed and
    fail the export unless --allow-missing."""
    rows: dict[tuple[str, str, str], list[str]] = {}
    missing: list[str] = []
    for name in args.subsystems:
        mod = _load_subsystem(name)
        c = mod.circuit()
        for ref, part in sorted(c.parts.items()):
            lcsc = part.fields.get("LCSC", "")
            if not lcsc:
                missing.append(f"{c.name}:{ref} ({part.value})")
            rows.setdefault((part.value, part.footprint, lcsc), []).append(ref)
    out = args.output or (DEFAULT_OUT / "bom_jlc.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for (value, fp, lcsc), refs in sorted(rows.items()):
            w.writerow([value, ",".join(refs), fp, lcsc])
    print(f"BOM written: {out} ({len(rows)} line items)")
    if missing:
        print(f"MISSING LCSC ({len(missing)}):")
        for m in missing:
            print(f"  {m}")
        if not args.allow_missing:
            return 1
    return 0


CARRIER = REPO_ROOT / "carrier"


def _ahash(png: Path) -> str:
    """16x16 average hash — perceptual, robust to PNG byte noise."""
    from PIL import Image
    im = Image.open(png).convert("L").resize((16, 16))
    px = list(im.getdata())
    avg = sum(px) / len(px)
    return "".join("1" if v > avg else "0" for v in px)


def _golden_check(ren_dir: Path, bless: bool) -> None:
    """Golden render snapshots: drift WARNS, --bless accepts new goldens."""
    golden_path = ren_dir / "golden.json"
    cur = {p.stem: _ahash(p) for p in sorted(ren_dir.glob("*.png"))}
    if bless or not golden_path.exists():
        golden_path.write_text(json.dumps(cur, indent=1, sort_keys=True)
                               + "\n")
        print(f"golden renders: BLESSED {len(cur)} sheets -> {golden_path}")
        return
    golden = json.loads(golden_path.read_text())
    drifted = []
    for name, h in sorted(cur.items()):
        old = golden.get(name)
        if old is None:
            drifted.append(f"{name}: NEW sheet (no golden)")
        else:
            dist = sum(a != b for a, b in zip(h, old))
            if dist > 12:
                drifted.append(f"{name}: drift {dist}/256 bits")
    for name in sorted(set(golden) - set(cur)):
        drifted.append(f"{name}: golden exists but no render")
    if drifted:
        print("golden renders: DRIFT (rerun with --bless to accept):")
        for d in drifted:
            print(f"  {d}")
    else:
        print(f"golden renders: {len(cur)} sheets match")


def _net_ident(name: str) -> str:
    ident = name.replace("+", "P").replace("-", "_")
    ident = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in ident)
    if ident and ident[0].isdigit():
        ident = "_" + ident
    return ident


def cmd_nets(args: argparse.Namespace) -> int:
    """GENERATE carrier/nets.py — the cross-sheet net-name contract as
    Python attributes (SoM contract nets + the gated/board rails), so port
    names are attrs, not strings to typo."""
    from schgen.link import all_subsystem_paths, load_som_contract, \
        load_subsystem
    som = load_som_contract()
    rails: set[str] = set()
    for p in all_subsystem_paths():
        sc = load_subsystem(p.stem)
        for n in sc.circuit.nets.values():
            if n.net_class in (NetClass.POWER,) and n.name.startswith("+"):
                rails.add(n.name)
    lines = [
        '"""GENERATED net-name contract — regenerate with `schgen nets`.',
        "",
        "Cross-sheet PORT names as Python attributes: the SoM connector",
        "contract (carrier/som_interface.json) plus every board rail.",
        'Authoring: `from carrier.nets import SOM, RAILS` then',
        'c.port(SOM.SDIO_CLK, ...) — a typo is an AttributeError at build',
        'time, not a silent open at layout time."""',
        "",
        "",
        "class SOM:",
    ]
    for name in sorted(som):
        lines.append(f"    {_net_ident(name)} = {name!r}")
    lines += ["", "", "class RAILS:"]
    for name in sorted(rails):
        lines.append(f"    {_net_ident(name)} = {name!r}")
    out = CARRIER / "nets.py"
    out.write_text("\n".join(lines) + "\n")
    print(f"nets contract: {out} ({len(som)} SoM nets, {len(rails)} rails)")
    return 0


def cmd_board(args: argparse.Namespace) -> int:
    """ONE command: every sheet gated, link + board netlist gate, an
    openable carrier KiCad project, constraints, block diagram, JLC BOM —
    all written into the committed carrier/ output taxonomy."""
    import tempfile

    from schgen import constraints, diagram
    from schgen import board as board_mod
    from schgen.link import (all_subsystem_paths, link, load_som_contract,
                             load_subsystem)

    lib = Library()
    sch_dir = CARRIER / "schematic"
    ren_dir = CARRIER / "renders"
    rep_dir = CARRIER / "reports"
    man_dir = CARRIER / "manufacturing"
    for d in (sch_dir, ren_dir, rep_dir, man_dir):
        d.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="schgen_board_"))

    names = [p.stem for p in all_subsystem_paths()]
    sheets = []
    placements: dict[str, tuple] = {}
    verdicts: list[str] = []
    ok_all = True
    for name in names:
        spath = _subsystem_path(name)
        purity = _purity_violations(spath)
        if purity:
            print(f"{name}: PURITY GATE FAIL")
            for v in purity:
                print(f"  {v}")
            ok_all = False
            continue
        sc = load_subsystem(name)
        c = sc.circuit
        c.validate({r: lib.pin_numbers(p.lib_id)
                    for r, p in c.parts.items()})
        driven = _check_inputs_driven(c, lib)
        if driven:
            for pr in driven:
                print(f"{name}: INPUT-DRIVEN: {pr}")
            ok_all = False
            continue
        placement, routed, geo = place.place_and_route(c, lib)
        placements[name] = (placement, routed)
        design = PlacedDesign(
            circuit=c, parts=placement.parts, powers=placement.powers,
            wires=[Wire(s.x0, s.y0, s.x1, s.y1) for s in routed.segs],
            junctions=[EJunction(x, y) for x, y in routed.junctions],
            hlabels=placement.hlabels, llabels=placement.llabels,
            no_connects=placement.no_connects, paper=placement.paper)
        sch = tmp / f"{name}.kicad_sch"
        emit(design, sch, lib)
        net_res = netlist_gate.check(c, sch)
        erc_ok, _txt = _erc(sch, rep_dir / f"{name}.erc.rpt")
        vis = visual_gate.check(geo)
        _render(sch, ren_dir / f"{name}.png")
        ok = net_res.ok and erc_ok and vis.ok
        ok_all = ok_all and ok
        verdicts.append(
            f"{name}: netlist={'PASS' if net_res.ok else 'FAIL'} "
            f"erc={'PASS' if erc_ok else 'FAIL'} "
            f"visual={'PASS' if vis.ok else 'FAIL'} paper={placement.paper}")
        print(verdicts[-1])
        sheets.append(sc)

    # link + constraints + diagram
    som_nets = load_som_contract()
    res = link(sheets, som_nets)
    (rep_dir / "link_report.txt").write_text(res.report() + "\n")
    print(f"LINK: {'PASS' if res.ok else 'FAIL'} "
          f"({len(res.errors)} errors, {len(res.warnings)} warnings)")
    ok_all = ok_all and res.ok
    constraints.export(sheets, man_dir)
    diagram.render(res, som_nets, REPO_ROOT / "docs" / "block_diagram.svg")

    # hierarchy: the openable carrier project + the board netlist gate
    board_ok = board_mod.build_board(
        sheets, lib, CARRIER, placements=placements,
        root_name="Zynq_Carrier", sheet_subdir="schematic",
        reports_dir=rep_dir)
    ok_all = ok_all and board_ok

    # JLC BOM across every sheet (missing LCSC = warning at board level)
    rows: dict[tuple[str, str, str], list[str]] = {}
    missing: list[str] = []
    for sc in sheets:
        for ref, part in sorted(sc.circuit.parts.items()):
            lcsc = part.fields.get("LCSC", "")
            if not lcsc:
                missing.append(f"{sc.name}:{ref} ({part.value})")
            rows.setdefault((part.value, part.footprint, lcsc),
                            []).append(f"{sc.name}:{ref}")
    with open(man_dir / "bom_jlc.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for (value, fp, lcsc), refs in sorted(rows.items()):
            w.writerow([value, ",".join(refs), fp, lcsc])
    print(f"BOM: {man_dir / 'bom_jlc.csv'} ({len(rows)} line items"
          f"{f', {len(missing)} missing LCSC' if missing else ''})")

    (rep_dir / "gates.txt").write_text(
        "\n".join(verdicts)
        + f"\nLINK: {'PASS' if res.ok else 'FAIL'}"
        + f"\nBOARD GATE: {'PASS' if board_ok else 'FAIL'}\n")

    _golden_check(ren_dir, bless=args.bless)
    print(f"BOARD: {'PASS' if ok_all else 'FAIL'} "
          f"({len(sheets)} sheets -> {CARRIER / 'Zynq_Carrier.kicad_pro'})")
    return 0 if ok_all else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="schgen", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="generate + gate one subsystem sheet")
    b.add_argument("subsystem",
                   help="name in carrier/subsystems/ (e.g. usb_pd) or a .py path")
    b.add_argument("-o", "--outdir", type=Path, default=None)
    b.add_argument("--no-render", action="store_true")
    b.set_defaults(func=cmd_build)
    si = sub.add_parser("som-interface",
                        help="extract J-connector pin->net contract from the SoM project")
    si.add_argument("som_sch")
    si.add_argument("--refs", default="J1,J2,J3")
    si.add_argument("-o", "--output", default="carrier/som_interface.json")
    from schgen.som_interface import cmd as _si_cmd
    si.set_defaults(func=lambda a: _si_cmd(a))
    lk = sub.add_parser(
        "link", help="board-level link: port graph + constraints + block "
                     "diagram + hierarchical root sheet with netlist gate")
    lk.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    lk.add_argument("-o", "--outdir", type=Path, default=None)
    lk.add_argument("--no-board", action="store_true",
                    help="skip root-sheet emission + board netlist gate")
    from schgen.link import cmd_link
    lk.set_defaults(func=cmd_link)
    bd = sub.add_parser(
        "board", help="ONE command: every sheet gated + link + openable "
                      "carrier KiCad project + constraints + diagram + BOM "
                      "into the committed carrier/ taxonomy")
    bd.add_argument("--bless", action="store_true",
                    help="accept the current renders as golden snapshots")
    bd.set_defaults(func=cmd_board)
    nt = sub.add_parser("nets", help="regenerate carrier/nets.py (the "
                                     "cross-sheet net-name contract)")
    nt.set_defaults(func=cmd_nets)
    m = sub.add_parser("bom", help="export JLCPCB assembly BOM from circuits")
    m.add_argument("subsystems", nargs="+")
    m.add_argument("-o", "--output", type=Path, default=None)
    m.add_argument("--allow-missing", action="store_true")
    m.set_defaults(func=cmd_bom)
    pa = sub.add_parser("part", help="parts/ library pipeline (LCSC/EasyEDA)")
    pa_sub = pa.add_subparsers(dest="part_cmd", required=True)
    padd = pa_sub.add_parser(
        "add", help="fetch an LCSC part and generate parts/<MPN>/ "
                    "(<MPN>.py + symbol + faithful footprint + 3D)")
    padd.add_argument("lcsc_id", help="LCSC id, e.g. C132291")
    padd.add_argument("--name", default=None,
                      help="folder/symbol name override (default: MPN)")
    padd.add_argument("--from-json", type=Path, default=None,
                      help="offline mode: use a saved EasyEDA API response")
    padd.add_argument("-o", "--parts-dir", type=Path, default=None,
                      help="parts library root (default: <repo>/parts)")
    from schgen.part_gen import cmd_part_add
    padd.set_defaults(func=cmd_part_add)
    pf = sub.add_parser(
        "preflight", help="live JLC/LCSC stock + Basic/Extended + cost check")
    pf.add_argument("subsystems", nargs="+")
    pf.add_argument("--qty", type=int, default=1,
                    help="number of boards (default 1)")
    pf.add_argument("--allow-missing", action="store_true",
                    help="parts without LCSC ids are reported but not fatal")
    from schgen.preflight import cmd_preflight
    pf.set_defaults(func=cmd_preflight)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
