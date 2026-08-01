"""Netlist-first KiCad generator: subsystem sheets, board hierarchy, PCB
foundation and the gates that judge them."""

from __future__ import annotations

import os as _os
import sys as _sys

# SCHGEN_PROJECT must be set BEFORE the engine imports below resolve their paths.
if "--project" in _sys.argv:
    _i = _sys.argv.index("--project")
    if _i + 1 < len(_sys.argv):
        _os.environ["SCHGEN_PROJECT"] = _sys.argv[_i + 1]
        del _sys.argv[_i:_i + 2]

import argparse
import ast
import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from schgen.core.model import Circuit, NetClass
from schgen.core.project import PROJECT_ROOT
from schgen.core.symbols import Library
from schgen.layout import place
from schgen.output.emit import Junction as EJunction
from schgen.output.emit import PlacedDesign, Wire, emit
from schgen.verify import netlist_gate, visual_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBSYSTEMS_DIR = PROJECT_ROOT / "subsystems"


def _subsystem_path(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if not path.suffix == ".py":
        stem = Path(name_or_path).stem
        foldered = SUBSYSTEMS_DIR / stem / f"{stem}.py"
        path = foldered if foldered.exists() else SUBSYSTEMS_DIR / f"{stem}.py"
    if not path.exists():
        raise SystemExit(f"subsystem not found: {path}")
    return path


def _load_subsystem(name_or_path: str):
    path = _subsystem_path(name_or_path)
    spec = importlib.util.spec_from_file_location(f"carrier_subsys_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_BANNED_MODULES = ("schgen.layout.place", "schgen.output.emit",
                   "schgen.layout.route", "schgen.layout.textmetrics",
                   "schgen.core.symbols", "schgen.output.render",
                   "schgen.verify", "schgen.core.sexpr")
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

_ERC_DRIVER_ETYPES = {"output", "bidirectional", "tri_state", "passive",
                  "power_out", "open_collector", "open_emitter"}


def _check_inputs_driven(c: Circuit, lib: Library) -> list[str]:
    etype_of = {(ref, p.number): p.etype
                for ref, part in c.parts.items()
                for p in lib.get(part.lib_id).pins}
    problems: list[str] = []
    for net in c.nets.values():
        if net.net_class in (NetClass.POWER, NetClass.GROUND, NetClass.PORT):
            continue
        etypes = {etype_of.get((pr.ref, pr.pin), "?") for pr in net.pins}
        if "input" in etypes and not (etypes & _ERC_DRIVER_ETYPES):
            problems.append(
                f"net {net.name!r}: input pin(s) with no same-sheet driver "
                f"and not a PORT — undriven input")
    return problems


def strip_report_timestamp(report: Path) -> None:
    if report.exists():
        first, _, rest = report.read_text().partition("\n")
        report.write_text(
            re.sub(r"\([^)]*?(Encoding [^)]*)\)", r"(\1)", first)
            + "\n" + rest)


def _erc(sch: Path, report: Path) -> tuple[bool, str]:
    pro = sch.with_suffix(".kicad_pro")
    pro.write_text(json.dumps({
        "meta": {"filename": pro.name, "version": 3},
        "erc": {"rule_severities": {"pin_not_driven": "warning"}},
    }, indent=2) + "\n")
    proc = subprocess.run(
        ["kicad-cli", "sch", "erc", "--severity-error",
         "--exit-code-violations", "-o", str(report), str(sch)],
        capture_output=True, text=True)
    strip_report_timestamp(report)
    txt = report.read_text() if report.exists() else proc.stderr
    return proc.returncode == 0, txt


def _render(sch: Path, png: Path, dpi: int = 300) -> bool:
    from schgen.output.render import render_sheet_to_png
    try:
        render_sheet_to_png(sch, png, dpi=dpi)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"render FAILED: {exc}")
        return False


def cmd_build(args: argparse.Namespace) -> int:
    import tempfile
    if args.outdir is not None:
        return _build_into(args, args.outdir)
    with tempfile.TemporaryDirectory(prefix="schgen_build_") as tmp:
        return _build_into(args, Path(tmp))


def _build_into(args: argparse.Namespace, outdir: Path) -> int:
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
    rows: dict[tuple[str, str, str], list[str]] = {}
    missing: list[str] = []
    for name in args.subsystems:
        mod = _load_subsystem(name)
        c = mod.circuit()
        for ref, part in sorted(c.parts.items()):
            if part.fields.get("BOM") == "exclude":
                continue
            lcsc = part.fields.get("LCSC", "")
            if not lcsc:
                missing.append(f"{c.name}:{ref} ({part.value})")
            rows.setdefault((part.value, part.footprint, lcsc), []).append(ref)
    out = args.output or (Path.cwd() / "bom_jlc.csv")
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


CARRIER = PROJECT_ROOT


def _pcb_error_count(pcb_path: Path) -> int:
    import tempfile as _tf
    with _tf.TemporaryDirectory(prefix="schgen_pcbdrc_") as td:
        rpt = Path(td) / "drc.json"
        # Zones are unfilled on disk; --refill-zones makes DRC judge the real fill.
        subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json",
             "--severity-error", "--refill-zones",
             "-o", str(rpt), str(pcb_path)],
            capture_output=True, text=True)
        if not rpt.exists():
            return -1
        try:
            data = json.loads(rpt.read_text())
        except Exception:  # noqa: BLE001
            return -1
    return len(data.get("violations", []))


def _ahash(png: Path) -> str:
    from PIL import Image
    im = Image.open(png).convert("L").resize((16, 16))
    px = list(im.getdata())
    avg = sum(px) / len(px)
    return "".join("1" if v > avg else "0" for v in px)


def _golden_check(ren_dir: Path, bless: bool) -> None:
    golden_path = ren_dir / "golden.json"
    cur = {p.stem: _ahash(p) for p in sorted(ren_dir.glob("*.png"))
           if not p.stem.startswith("ratsnest")}
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
            dist = sum(a != b for a, b in zip(h, old, strict=False))
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
    from schgen.core.link import all_subsystem_paths, load_som_contract, load_subsystem
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
    import tempfile

    from schgen.core.link import (
        all_subsystem_paths,
        link,
        load_som_contract,
        load_subsystem,
    )
    from schgen.generate import board as board_mod
    from schgen.generate import constraints
    from schgen.output import diagram

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

    import time as _time
    _laps: list[tuple[str, float]] = []
    _t_mark = [_time.perf_counter()]

    def _lap(label: str) -> None:
        now = _time.perf_counter()
        _laps.append((label, now - _t_mark[0]))
        _t_mark[0] = now

    prepared: list[tuple] = []
    early_fail: dict[str, str | None] = {}
    for name in names:
        spath = _subsystem_path(name)
        purity = _purity_violations(spath)
        if purity:
            print(f"{name}: PURITY GATE FAIL")
            for v in purity:
                print(f"  {v}")
            ok_all = False
            early_fail[name] = None
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
            early_fail[name] = None
            continue
        try:
            placement, routed, geo = place.place_and_route(c, lib)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).splitlines()[-1][:140]
            early_fail[name] = f"{name}: place/route=FAIL ({msg})"
            print(early_fail[name])
            ok_all = False
            continue
        placements[name] = (placement, routed)
        design = PlacedDesign(
            circuit=c, parts=placement.parts, powers=placement.powers,
            wires=[Wire(s.x0, s.y0, s.x1, s.y1) for s in routed.segs],
            junctions=[EJunction(x, y) for x, y in routed.junctions],
            hlabels=placement.hlabels, llabels=placement.llabels,
            no_connects=placement.no_connects, paper=placement.paper)
        sch = tmp / f"{name}.kicad_sch"
        emit(design, sch, lib)
        vis = visual_gate.check(geo)
        prepared.append((name, sc, c, sch, vis, placement.paper))

    def _gate_one(item: tuple):
        name, _sc, c, sch, _vis, _paper = item
        net_res = netlist_gate.check(c, sch)
        erc_ok, _txt = _erc(sch, rep_dir / f"{name}.erc.rpt")
        if not getattr(args, "no_render", False):
            _render(sch, ren_dir / f"{name}.png")
        return name, net_res, erc_ok

    gate_out: dict[str, tuple] = {}
    if prepared:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=(os.cpu_count() or 8)) as ex:
            for name, net_res, erc_ok in ex.map(_gate_one, prepared):
                gate_out[name] = (net_res, erc_ok)

    _lap("pass1+2: place/route + per-sheet kicad-cli (netlist/erc/render)")

    prep_by_name = {p[0]: p for p in prepared}
    for name in names:
        if name in early_fail:
            if early_fail[name] is not None:
                verdicts.append(early_fail[name])
            continue
        _n, sc, _c, _sch, vis, paper = prep_by_name[name]
        net_res, erc_ok = gate_out[name]
        ok = net_res.ok and erc_ok and vis.ok
        ok_all = ok_all and ok
        verdicts.append(
            f"{name}: netlist={'PASS' if net_res.ok else 'FAIL'} "
            f"erc={'PASS' if erc_ok else 'FAIL'} "
            f"visual={'PASS' if vis.ok else 'FAIL'} paper={paper}")
        print(verdicts[-1])
        sheets.append(sc)

    from schgen.verify import cc_gate
    cc_prepared = [(name, c, placements[name][0], placements[name][1])
                   for (name, sc, c, _sch, _vis, _paper) in prepared
                   if name in placements]
    cc_res = cc_gate.check_board(cc_prepared, lib)
    (rep_dir / "cc_gate.txt").write_text(cc_res.summary() + "\n")
    print(f"CC GATE: {'PASS' if cc_res.ok else 'FAIL'} "
          f"(geometry-only, independent of kicad-cli -> {rep_dir / 'cc_gate.txt'})")
    for _r in cc_res.per_sheet:
        if not _r.ok:
            print("  " + _r.summary().replace("\n", "\n  "))
    ok_all = ok_all and cc_res.ok

    from schgen.verify import symbol_law
    sl_res = symbol_law.check([sc.circuit for sc in sheets], lib)
    (rep_dir / "symbol_law.txt").write_text(sl_res.summary() + "\n")
    print(sl_res.summary().splitlines()[0]
          + f" -> {rep_dir / 'symbol_law.txt'}")
    for _v in sl_res.violations:
        print(f"  {_v}")
    ok_all = ok_all and sl_res.ok

    som_nets = load_som_contract()
    res = link(sheets, som_nets)
    (rep_dir / "link_report.txt").write_text(res.report() + "\n")
    print(f"LINK: {'PASS' if res.ok else 'FAIL'} "
          f"({len(res.errors)} errors, {len(res.warnings)} warnings)")
    ok_all = ok_all and res.ok
    constraints.export(sheets, man_dir)
    diagram.render(res, som_nets, REPO_ROOT / "docs" / "block_diagram.svg")

    _idx_path = CARRIER / "sheet_index.json"
    _sheet_index = json.loads(_idx_path.read_text()) if _idx_path.exists() else {}
    _new = sorted(sc.name for sc in sheets if sc.name not in _sheet_index)
    if _new:
        _nxt = max(_sheet_index.values(), default=0) + 1
        for _n in _new:
            _sheet_index[_n] = _nxt
            _nxt += 1
        _idx_path.write_text(json.dumps(_sheet_index, indent=2) + "\n")
        print(f"sheet-index: assigned {len(_new)} new sheet(s) a stable refdes "
              f"band -> {', '.join(f'{n}={_sheet_index[n]}' for n in _new)}")

    board_ok = board_mod.build_board(
        sheets, lib, CARRIER, placements=placements,
        root_name="Zynq_Carrier", sheet_subdir="schematic",
        sheet_index=_sheet_index, reports_dir=rep_dir)
    ok_all = ok_all and board_ok

    _lap("pass3 + cc_gate + link + build_board (hierarchy + board ERC)")

    import threading as _threading

    from schgen.generate import pcb as pcb_mod
    _pcb_holder: dict[str, object] = {}

    def _run_pcb() -> None:
        try:
            _pcb_holder["res"] = pcb_mod.generate(run_drc=True)
        except Exception as exc:  # noqa: BLE001
            _pcb_holder["exc"] = exc
    _pcb_thread = _threading.Thread(target=_run_pcb, name="pcb+drc", daemon=True)
    _pcb_thread.start()

    rows: dict[tuple[str, str, str], list[str]] = {}
    missing: list[str] = []
    for sc in sheets:
        for ref, part in sorted(sc.circuit.parts.items()):
            if part.fields.get("BOM") == "exclude":
                continue
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

    no_fp = [(value, ",".join(refs))
             for (value, fp, lcsc), refs in rows.items() if not fp]
    if no_fp:
        print("BOM FOOTPRINT GATE: FAIL — BOM line(s) with no footprint "
              "(an assembler cannot place them):")
        for value, refs in sorted(no_fp):
            print(f"  {value}: {refs}")
        ok_all = False
    else:
        print(f"BOM FOOTPRINT GATE: PASS — all {len(rows)} BOM lines placeable")

    from schgen.verify import powertree
    pt_res = powertree.run(sheets, rep_dir, CARRIER / "docs")
    print(f"POWER TREE: {'PASS' if pt_res.ok else 'FAIL'} "
          f"({len(pt_res.regs)} regulators, {len(pt_res.findings)} findings"
          f" -> {rep_dir / 'power_tree.txt'})")
    for e in pt_res.errors:
        print(f"  POWER TREE ERROR: {e}")
    ok_all = ok_all and pt_res.ok

    from schgen.verify import rail_ampacity
    ra_res = rail_ampacity.run(sheets, rep_dir, pt_res=pt_res)
    print(f"RAIL AMPACITY: {'PASS' if ra_res.ok else 'FAIL'} "
          f"({len(ra_res.rails)} delivery rails, {len(ra_res.errors)} "
          f"under-contacted, {len(ra_res.findings)} unbooked "
          f"-> {rep_dir / 'rail_ampacity.txt'})")
    for e in ra_res.errors:
        print(f"  RAIL AMPACITY ERROR: {e}")
    ok_all = ok_all and ra_res.ok

    from schgen.verify import testpoints
    tp_res = testpoints.check_coverage(sheets)
    (rep_dir / "testpoints.txt").write_text(tp_res.report() + "\n")
    print(f"TESTPOINTS: {'PASS' if tp_res.ok else 'FAIL'} "
          f"({tp_res.covered}/{len(tp_res.required)} required covered, "
          f"{len(tp_res.waived)} waived -> {rep_dir / 'testpoints.txt'})")
    for e in tp_res.errors:
        print(f"  TESTPOINT ERROR: {e}")
    ok_all = ok_all and tp_res.ok

    from schgen.verify import design_rules
    dr_res = design_rules.run(sheets, rep_dir, lib=lib)
    print(f"DESIGN RULES: {'PASS' if dr_res.ok else 'FAIL'} "
          f"({len(dr_res.findings)} findings, {len(dr_res.waived)} waived "
          f"-> {rep_dir / 'design_rules.txt'})")
    for f in dr_res.findings:
        print(f"  DESIGN RULE: {f}")
    ok_all = ok_all and dr_res.ok

    from schgen.verify import part_rules
    pr_res = part_rules.run(sheets, rep_dir, pt_res=pt_res)
    print(f"PART RULES: {'PASS' if pr_res.ok else 'FAIL'} "
          f"({pr_res.checked} checks, {len(pr_res.findings)} findings, "
          f"{len(pr_res.unspecced)} unspeced, {len(pr_res.waived)} waived "
          f"-> {rep_dir / 'part_rules.txt'})")
    for f in pr_res.findings:
        print(f"  PART RULE: {f}")
    ok_all = ok_all and pr_res.ok

    from schgen.verify import bom_values
    bv_res = bom_values.run(sheets, rep_dir)
    print(f"BOM VALUES: {'PASS' if bv_res.ok else 'FAIL'} "
          f"({bv_res.checked} checks, {len(bv_res.mismatches)} mismatch, "
          f"{len(bv_res.unverified)} unverified -> {rep_dir / 'bom_values.txt'})")
    for m in bv_res.mismatches:
        print(f"  BOM VALUE: {m}")
    ok_all = ok_all and bv_res.ok

    from schgen.verify import footprint_pads
    fpp_res = footprint_pads.run(sheets, rep_dir, lib=lib)
    print(f"FOOTPRINT PADS: {'PASS' if fpp_res.ok else 'FAIL'} "
          f"({fpp_res.checked} parts, {len(fpp_res.violations)} pin(s) with "
          f"no pad, {len(set(fpp_res.unresolved))} unresolved fp "
          f"-> {rep_dir / 'footprint_pads.txt'})")
    for v in fpp_res.violations:
        print(f"  FOOTPRINT PAD: {v}")
    ok_all = ok_all and fpp_res.ok

    from schgen.verify import pin_completeness
    pc_res = pin_completeness.run(sheets, rep_dir, lib=lib)
    print(f"PIN COMPLETENESS: {'PASS' if pc_res.ok else 'REPORT'} "
          f"({pc_res.parts_checked} parts, {len(pc_res.floats)} silent float(s), "
          f"{pc_res.nc_total} NC pins: {len(pc_res.nc_seeded)} blessed/"
          f"{len(pc_res.nc_new)} to-bless -> {rep_dir / 'pin_completeness.txt'})")
    for f in pc_res.floats:
        print(f"  PIN COMPLETENESS: {f}")

    from schgen.verify import subsystem_structure
    ssr = subsystem_structure.run(rep_dir)
    print(f"SUBSYSTEM STRUCTURE: {'PASS' if ssr.ok else 'FAIL'} "
          f"({ssr.n_ok}/{len(ssr.packages)} package(s) complete "
          f"-> {rep_dir / 'subsystem_structure.txt'})")
    for _p in ssr.packages:
        if not _p.ok:
            for _m in (_p.missing or _p.interface_drift or _p.errors):
                print(f"  SUBSYSTEM {_p.name}: {_m}")
    ok_all = ok_all and ssr.ok

    from schgen.verify import carrier_structure
    csr = carrier_structure.run(rep_dir)
    print(f"CARRIER STRUCTURE: {'PASS' if csr.ok else 'FAIL'} "
          f"({csr.n_ok}/{len(csr.packages)} package(s) complete "
          f"-> {rep_dir / 'carrier_structure.txt'})")
    for _p in csr.packages:
        if not _p.ok:
            for _m in (_p.missing or _p.errors or ["no callable circuit()"]):
                print(f"  CARRIER {_p.name}: {_m}")
    ok_all = ok_all and csr.ok

    from schgen.verify import spice
    sp_res = spice.run(sheets, rep_dir, allow_ngspice=True)
    print(f"SPICE: {'PASS' if sp_res.ok else 'FAIL'} "
          f"({sp_res.n_checks} checks, {sp_res.engine} "
          f"-> {rep_dir / 'spice.txt'})")
    for e in sp_res.errors:
        print(f"  SPICE ERROR: {e}")
    ok_all = ok_all and sp_res.ok

    from schgen.generate import xdc
    try:
        xres = xdc.generate(sheets, CARRIER / "fpga" / "Zynq_Carrier_pins.xdc")
        print(f"XDC: {xres.path} ({xres.count} pins; "
              + "; ".join(xres.checks[-2:]) + ")")
    except xdc.XdcError as exc:
        print(f"XDC: FAIL — {exc}")
        ok_all = False

    from schgen.generate import vivado
    try:
        vtcl = vivado.generate(sheets, CARRIER / "fpga" / "create_project.tcl")
        print(f"VIVADO: {vtcl}")
    except (vivado.VivadoError, xdc.XdcError) as exc:
        print(f"VIVADO: FAIL — {exc}")
        ok_all = False

    from schgen.generate import firmware, gallery, manual, testplan
    try:
        fw_out = firmware.generate()
        fw_absent = firmware.absent_inputs()
        print(f"FIRMWARE CONTRACT: {fw_out}"
              + (f" (inputs absent on this project, sections omitted: "
                 f"{', '.join(fw_absent)})" if fw_absent else ""))
    except Exception as exc:  # noqa: BLE001
        print(f"FIRMWARE CONTRACT: FAIL — {exc}")
        ok_all = False
    mn_missing = manual.missing_requirements()
    if mn_missing:
        print(f"BRINGUP MANUAL: SKIP — project has no "
              f"{', '.join(mn_missing)} (the staged bring-up procedure "
              f"derives from them)")
    else:
        try:
            mn_out = manual.generate()
            print(f"BRINGUP MANUAL: {mn_out}")
        except Exception as exc:  # noqa: BLE001
            print(f"BRINGUP MANUAL: FAIL — {exc}")
            ok_all = False
    try:
        tp_out = testplan.generate(sheets=sheets)
        print(f"TEST PLAN: {tp_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"TEST PLAN: FAIL — {exc}")
        ok_all = False
    try:
        changed = gallery.generate()
        print(f"GALLERY: {gallery.readme_targets()} "
              + ("updated" if changed else "unchanged"))
    except Exception as exc:  # noqa: BLE001
        print(f"GALLERY: FAIL — {exc}")
        ok_all = False

    from schgen.generate import devicetree
    try:
        dt_out = devicetree.generate(CARRIER / "firmware" / "carrier_pl.dtsi")
        print(f"DEVICETREE: {dt_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"DEVICETREE: FAIL — {exc}")
        ok_all = False

    from schgen.generate import scfw
    scfw_missing = scfw.missing_requirements()
    if scfw_missing:
        print(f"SCFW SCAFFOLD: SKIP — project has no "
              f"{', '.join(scfw_missing)} (the SC bring-up scaffold derives "
              f"from the full bring-up complement)")
    else:
        try:
            scfw_out = scfw.generate(CARRIER / "firmware" / "sc")
            print(f"SCFW SCAFFOLD: {CARRIER / 'firmware' / 'sc'} "
                  f"({len(scfw_out)} files)")
        except Exception as exc:  # noqa: BLE001
            print(f"SCFW SCAFFOLD: FAIL — {exc}")
            ok_all = False

    from schgen.generate import power_sequence
    try:
        ps_out = power_sequence.generate(sheets, pt_res)
        print(f"POWER SEQUENCE: {ps_out.relative_to(REPO_ROOT)} "
              f"(staged bring-up diagram)")
    except Exception as exc:  # noqa: BLE001
        print(f"POWER SEQUENCE: FAIL — {exc}")
        ok_all = False

    _lap("verify gates (powertree..spice) + xdc/vivado + downstream doc generators")

    pcb_res = None
    try:
        # Joined here, before SI extends the .kicad_dru the PCB thread wrote.
        _pcb_thread.join()
        if "exc" in _pcb_holder:
            raise _pcb_holder["exc"]      # type: ignore[misc]
        pcb_res = _pcb_holder["res"]
        drc = pcb_res["drc"]
        derr = (drc or {}).get("n_violations", 0)
        pcb_errs = _pcb_error_count(pcb_res["pcb"])
        print(f"PCB: {pcb_res['pcb'].relative_to(REPO_ROOT)} "
              f"({pcb_res['board_w']:g} x {pcb_res['board_h']:g} mm, 4L "
              f"Sig/GND/PWR/Sig, {pcb_res['placed']}/{pcb_res['total']} "
              f"footprints, {len(pcb_res['classes'])} net classes, "
              f"{pcb_res['nets']} nets) — DRC {pcb_errs} errors, "
              f"{(drc or {}).get('n_unconnected', 0)} unrouted (expected)")
        if pcb_res["deferred"]:
            for d in pcb_res["deferred"]:
                print(f"  PCB DEFERRED: {d}")
        if pcb_errs:
            print(f"  PCB DRC: FAIL — {pcb_errs} non-unrouted error(s)")
            ok_all = False

        rg = pcb_res.get("ratsnest_gate")
        rimg = pcb_res.get("ratsnest") or {}
        if rg is not None:
            (rep_dir / "ratsnest.txt").write_text(rg.summary() + "\n")
            print(f"RATSNEST (LAW 5): {'PASS' if rg.ok else 'FAIL'} "
                  f"({len(rg.off_board)} off-board, {len(rg.dispersed)} "
                  f"dispersed, cross-airwire {rg.cross_mm:g}/"
                  f"{rg.cross_budget_mm:.0f} mm budget "
                  f"-> {rep_dir / 'ratsnest.txt'})")
            if rimg.get("png_top"):
                print(f"  ratsnest images: "
                      f"{rimg['png_top'].relative_to(REPO_ROOT)} + "
                      f"{rimg['png_bottom'].relative_to(REPO_ROOT)} + "
                      f"{rimg['svg'].relative_to(REPO_ROOT)}")
            for _o in rg.off_board:
                print(f"  RATSNEST OFF-BOARD: {_o}")
            for _d in rg.dispersed:
                print(f"  RATSNEST DISPERSED: {_d}")
            if not rg.cross_ok:
                print(f"  RATSNEST CROSS-AIRWIRE OVER BUDGET: "
                      f"{rg.cross_mm:g} > {rg.cross_budget_mm:.0f} mm")
            ok_all = ok_all and rg.ok
        else:
            print("RATSNEST (LAW 5): FAIL — gate did not run")
            ok_all = False

        from schgen.generate import assembly as _asm_mod
        _asm_ok, _asm_line = _asm_mod.verdict(pcb_res.get("assembly"))
        print(_asm_line)
        ok_all = ok_all and _asm_ok

        mg = pcb_res.get("placement_mech")
        if mg is not None:
            (rep_dir / "placement_mech.txt").write_text(mg.summary() + "\n")
            print(f"PLACEMENT (LAW 6): {'PASS' if mg.ok else 'FAIL'} "
                  f"({mg.n_connectors} off-board connectors, "
                  f"{len(mg.bad_connectors)} mis-placed; "
                  f"{len(mg.under_som)} non-passive under SoM; "
                  f"{len(mg.controls_under_som)} controls under SoM; "
                  f"{len(mg.top_under_som)} TOP-side under SoM; "
                  f"{len(mg.face_top_on_bottom)}/{mg.n_face_top} user-facing "
                  f"face-down -> {rep_dir / 'placement_mech.txt'})")
            for _b in mg.bad_connectors:
                print(f"  PLACEMENT CONNECTOR: {_b}")
            for _u in mg.under_som:
                print(f"  PLACEMENT UNDER-SoM: {_u}")
            for _t in mg.top_under_som:
                print(f"  PLACEMENT TOP-UNDER-SoM: {_t}")
            ok_all = ok_all and mg.ok
        else:
            print("PLACEMENT (LAW 6): FAIL — gate did not run")
            ok_all = False
        cmr = pcb_res.get("connector_model")
        if cmr is not None:
            (rep_dir / "connector_model.txt").write_text(cmr.summary() + "\n")
            print(f"CONNECTOR MODEL (LAW 6): {'PASS' if cmr.ok else 'FAIL'} "
                  f"({cmr.n_connectors} connectors, {len(cmr.bad_z)} bad-Z, "
                  f"{len(cmr.geom_conflicts)} geom-conflict "
                  f"-> {rep_dir / 'connector_model.txt'})")
            for _b in cmr.bad_z:
                print(f"  CONNECTOR-MODEL BAD-Z: {_b}")
            for _g in cmr.geom_conflicts:
                print(f"  CONNECTOR-MODEL GEOM: {_g}")
            ok_all = ok_all and cmr.ok
        else:
            print("CONNECTOR MODEL (LAW 6): FAIL — gate did not run")
            ok_all = False
        cg = pcb_res.get("connector_spacing")
        if cg is not None:
            (rep_dir / "connector_spacing.txt").write_text(cg.summary() + "\n")
            print(f"CONNECTOR SPACING (LAW 6): {'PASS' if cg.ok else 'FAIL'} "
                  f"({len(cg.pairs)} overmold pairs, "
                  f"{len(cg.violations)} too-tight "
                  f"-> {rep_dir / 'connector_spacing.txt'})")
            for _v in cg.violations:
                print(f"  CONNECTOR SPACING: {_v}")
            ok_all = ok_all and cg.ok
        else:
            print("CONNECTOR SPACING (LAW 6): FAIL — gate did not run")
            ok_all = False
        rg = pcb_res.get("refdes_silk")
        if rg is not None:
            print(f"REFDES SILK (LAW 1): {'PASS' if rg.ok else 'FAIL'} "
                  f"({rg.n_top} top refs, {len(rg.top_pairs)} F.SilkS overlaps; "
                  f"{rg.n_bottom} bottom refs, {rg.bottom_pairs} B.SilkS overlaps)")
            for _v in rg.top_pairs[:10]:
                print(f"  REFDES SILK (F): {_v[0]} <-> {_v[1]} overprint")
            ok_all = ok_all and rg.ok
        else:
            print("REFDES SILK (LAW 1): FAIL — gate did not run")
            ok_all = False
        pcg = pcb_res.get("placement_contract")
        if pcg is not None:
            (rep_dir / "placement_contract.txt").write_text(pcg.summary() + "\n")
            print(f"PLACEMENT CONTRACT (Phase L): "
                  f"{'PASS' if pcg.ok else 'FAIL'} "
                  f"(contract={'yes' if pcg.have_contract else 'none'}, "
                  f"{pcg.checked} structures, {len(pcg.violations)} violations, "
                  f"{len(pcg.missing_refs)} unresolved "
                  f"-> {rep_dir / 'placement_contract.txt'})")
            for _v in sorted(pcg.violations):
                print(f"  PLACEMENT CONTRACT: {_v}")
            for _m in sorted(pcg.missing_refs):
                print(f"  PLACEMENT CONTRACT MISSING: {_m}")
            ok_all = ok_all and pcg.ok
        else:
            print("PLACEMENT CONTRACT (Phase L): FAIL — gate did not run")
            ok_all = False
        cov = pcb_res.get("contract_coverage")
        if cov is not None:
            from schgen.verify import placement_contract_gate as _cov_g
            _cov_txt, _nw, _nm, _nv = _cov_g.coverage_report(cov)
            (rep_dir / "contract_coverage.txt").write_text(_cov_txt + "\n")
            print(f"CONTRACT COVERAGE (advisory): {_nw} wired-gated / {_nm} "
                  f"inert-met / {_nv} inert-VIOLATED (un-enforced SI/PI intent) "
                  f"-> {rep_dir / 'contract_coverage.txt'}")
        from schgen.verify import contract_coverage_lint as _ccl
        _cl = _ccl.lint_project()
        (rep_dir / "contract_coverage_lint.txt").write_text(_cl.report() + "\n")
        print(f"{_cl.summary_line()} "
              f"-> {rep_dir / 'contract_coverage_lint.txt'}")
        if _ccl.ENFORCE:
            ok_all = ok_all and _cl.ok
        pfg = pcb_res.get("placement_flow")
        if pfg is not None:
            (rep_dir / "placement_flow.txt").write_text(pfg.summary() + "\n")
            print(f"PLACEMENT FLOW (Phase L): "
                  f"{'PASS' if pfg.ok else 'FAIL'} "
                  f"({pfg.n_contracts} external contract(s); "
                  f"flow {pfg.flow_fail}/{pfg.flow_checked}, "
                  f"facing {pfg.facing_fail}/{pfg.facing_checked}, "
                  f"far {pfg.far_fail}/{pfg.far_checked} "
                  f"-> {rep_dir / 'placement_flow.txt'})")
            for _v in sorted(pfg.violations):
                print(f"  PLACEMENT FLOW: {_v}")
            for _u in sorted(pfg.unresolved):
                print(f"  PLACEMENT FLOW UNRESOLVED: {_u}")
            ok_all = ok_all and pfg.ok
        else:
            print("PLACEMENT FLOW (Phase L): FAIL — gate did not run")
            ok_all = False
        fcomp = pcb_res.get("floorplan_composition")
        if fcomp is not None:
            (rep_dir / "floorplan_composition.txt").write_text(fcomp + "\n")
            head = fcomp.splitlines()[0] if fcomp else ""
            print(f"COMPOSITION LEDGER (T1, advisory): {head} "
                  f"-> {rep_dir / 'floorplan_composition.txt'}")
        rsg_ = pcb_res.get("return_stitch")
        if rsg_ is not None:
            (rep_dir / "return_stitch.txt").write_text(rsg_.summary() + "\n")
            print(f"RETURN STITCH (T2 v2): {'PASS' if rsg_.ok else 'FAIL'} "
                  f"({rsg_.n_covered}/{rsg_.n_contacts} contacts covered, "
                  f"worst {rsg_.worst_mm:.3f}/{rsg_.radius} mm, "
                  f"{rsg_.n_vias} stitch vias, parity {rsg_.file_parity} "
                  f"-> {rep_dir / 'return_stitch.txt'})")
            for _v in rsg_.violations[:10]:
                print(f"  RETURN STITCH: {_v}")
            ok_all = ok_all and rsg_.ok
        else:
            print("RETURN STITCH (T2 v2): FAIL — gate did not run")
            ok_all = False
        elg_ = pcb_res.get("escape_lanes")
        if elg_ is not None:
            (rep_dir / "escape_lanes.txt").write_text(elg_.summary() + "\n")
            print(f"ESCAPE LANES (T2 plan): {'PASS' if elg_.ok else 'FAIL'} "
                  f"({elg_.n_lanes} lanes, {elg_.n_pairs} pair records, "
                  f"{elg_.n_genuine} GENUINE "
                  f"-> {rep_dir / 'escape_lanes.txt'})")
            for _v in elg_.violations[:10]:
                print(f"  ESCAPE LANES: {_v}")
            ok_all = ok_all and elg_.ok
        else:
            print("ESCAPE LANES (T2 plan): FAIL — gate did not run")
            ok_all = False
        rp_ = pcb_res.get("return_path")
        if rp_ is not None:
            (rep_dir / "return_path.txt").write_text(
                "REPORT-ONLY: the SoM pinout is FIXED — v1's contact-level "
                "verdict is a design fact of the mated interface, remediated "
                "carrier-side by the RETURN-STITCH copper (see "
                "return_stitch.txt). Nothing claims 'return path fixed'.\n\n"
                + rp_.summary() + "\n")
            print(f"RETURN PATH (v1, report-only): "
                  f"{'PASS' if rp_.ok else 'FAIL — SoM-design fact'} "
                  f"({rp_.n_fail} contacts beyond K={rp_.k} steps "
                  f"-> {rep_dir / 'return_path.txt'})")
        fo_ = pcb_res.get("fanout")
        if fo_ is not None:
            (rep_dir / "fanout.txt").write_text(fo_.summary() + "\n")
            print(f"FAN-OUT CLEARANCE (D13, report-first): "
                  f"{'PASS' if fo_.ok else 'FAIL — RATCHET REGRESSION'} "
                  f"({fo_.n_subjects} multi-pin subjects, {fo_.n_starved} starved, "
                  f"baseline {fo_.baseline} "
                  f"-> {rep_dir / 'fanout.txt'})")
            for _r in fo_.starved_records:
                print(f"  FAN-OUT STARVED: {_r.ref} ({_r.sheet}) {_r.pins}pin "
                      f"clr={_r.clearance:.3f} need={_r.need:.2f} "
                      f"slack={_r.slack:+.3f} nearest={_r.nearest_ref}")
            for _g in fo_.regressions:
                print(f"  FAN-OUT REGRESSION: {_g}")
            ok_all = ok_all and fo_.ok
            if fo_.ok:
                from schgen.verify import fanout_gate
                fanout_gate.write_baseline(fo_.n_starved)
        else:
            print("FAN-OUT CLEARANCE (D13, report-first): FAIL — gate did not run")
            ok_all = False
    except Exception as exc:  # noqa: BLE001
        print(f"PCB: FAIL — {exc}")
        ok_all = False

    from schgen.verify import thermal
    _pcb_file = pcb_res["pcb"] if isinstance(pcb_res, dict) else None
    th_res = thermal.run(sheets, rep_dir, pt_res=pt_res, pcb_path=_pcb_file)
    print(f"THERMAL: {'PASS' if th_res.ok else 'FAIL'} "
          f"({len(th_res.devices)} devices, {len(th_res.errors)} over-limit, "
          f"{len(th_res.findings)} unspeced; pour evidence: "
          f"{th_res.copper_src or 'NONE (credits withheld)'} "
          f"-> {rep_dir / 'thermal.txt'})")
    for e in th_res.errors:
        print(f"  THERMAL ERROR: {e}")
    ok_all = ok_all and th_res.ok

    from schgen.verify import copper_debt
    try:
        cd_res = copper_debt.run(rep_dir, _pcb_file)
        print(f"COPPER DEBT: {cd_res.n_entries} copper-predicated claims "
              f"({cd_res.n_status('EMITTED')} emitted, "
              f"{cd_res.n_status('PARTIAL')} partial, "
              f"{cd_res.n_status('NOTHING')} unemitted, "
              f"{cd_res.n_status('UNMEASURED')} unmeasured) "
              f"-> {rep_dir / 'copper_debt.txt'} (report-only)")
    except Exception as exc:  # noqa: BLE001
        print(f"COPPER DEBT: FAIL — {exc}")
        ok_all = False

    if _pcb_file is not None:
        cpl_path = man_dir / "Zynq_Carrier_cpl.csv"
        try:
            _cpl = subprocess.run(
                ["kicad-cli", "pcb", "export", "pos", "--format", "csv",
                 "--units", "mm", "--side", "both",
                 "--output", str(cpl_path), str(_pcb_file)],
                capture_output=True, text=True, timeout=120)
            if _cpl.returncode == 0 and cpl_path.exists():
                n_cpl = max(0, sum(1 for _ in cpl_path.open()) - 1)
                print(f"CPL: {cpl_path.relative_to(REPO_ROOT)} "
                      f"({n_cpl} placements — pick-and-place position file)")
            else:
                print(f"CPL: skipped — kicad-cli export pos rc="
                      f"{_cpl.returncode}: {_cpl.stderr.strip()[:120]}")
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"CPL: skipped — {exc}")

    from schgen.verify import fab_profile
    fab_res = fab_profile.run(rep_dir)
    print(f"FAB PROFILE: {'PASS' if fab_res.ok else 'FAIL'} "
          f"({fab_res.profile.name}; "
          f"{sum(1 for *_r, ok in fab_res.rows if ok)}/{len(fab_res.rows)} "
          f"metrics at/above floor -> {rep_dir / 'fab_profile.txt'})")
    for e in fab_res.errors:
        print(f"  FAB PROFILE ERROR: {e}")
    ok_all = ok_all and fab_res.ok

    from schgen.generate import floorplan
    try:
        fp_paths = floorplan.generate(sheets, res)
        print("FLOORPLAN: " + " + ".join(
            str(p.relative_to(REPO_ROOT)) for p in fp_paths)
            + " (suggestion, not constraint)")
    except Exception as exc:  # noqa: BLE001
        print(f"FLOORPLAN: FAIL — {exc}")
        ok_all = False

    from schgen.core import fallbacks as _fbmod
    from schgen.verify import fallback_gate, quantize_census
    qc_res = quantize_census.check()
    (rep_dir / "quantize_census.txt").write_text(qc_res.summary() + "\n")
    print(f"QUANTIZE CENSUS: {'PASS' if qc_res.ok else 'FAIL'} "
          f"({qc_res.n_registered} registered transforms, {qc_res.n_files} "
          f"geometry files, {qc_res.n_sites} raw site(s), {qc_res.n_new} NEW "
          f"-> {rep_dir / 'quantize_census.txt'})")
    for _s in qc_res.new:
        print(f"  QUANTIZE NEW RAW SITE: {_s}")
    ok_all = ok_all and qc_res.ok
    if isinstance(pcb_res, dict):
        if pcb_res.get("fallbacks") is not None:
            _fbc = _fbmod.census()
            pcb_res["fallbacks"] = _fbc
            fb_res = fallback_gate.check(_fbc)
            _fired = {k: v for k, v in sorted(_fbc.items()) if v}
            print(f"FALLBACKS: {'PASS' if fb_res.ok else 'FAIL — RATCHET'} "
                  f"({len(_fbc)} registered paths; "
                  + (", ".join(f"{k}={v}" for k, v in _fired.items())
                     if _fired else "none fired")
                  + (" — baseline PINNED this build" if fb_res.pinned else "")
                  + ")")
            for _r in fb_res.regressions:
                print(f"  FALLBACK REGRESSION: {_r}")
            ok_all = ok_all and fb_res.ok
            pcb_res["fallback_gate"] = {
                "ok": fb_res.ok, "pinned": fb_res.pinned,
                "n_names": fb_res.n_names, "n_fired": fb_res.n_fired}
        else:
            print("FALLBACKS: FAIL — census did not run")
            ok_all = False
        _sm = pcb_res.get("stage_movement")
        if _sm is not None:
            _moved = {k: v for k, v in sorted(_sm.items()) if v}
            print("STAGE MOVEMENT: may_move=no tripwire armed; "
                  + (", ".join(f"{k}={v}" for k, v in _moved.items())
                     if _moved else "no stage moved a part")
                  + " (moved parts per stage)")
        else:
            print("STAGE MOVEMENT: FAIL — tracker did not run")
            ok_all = False
        pcb_res["quantize_census"] = {
            "ok": qc_res.ok, "n_registered": qc_res.n_registered,
            "n_files": qc_res.n_files, "n_sites": qc_res.n_sites,
            "n_new": qc_res.n_new}
    from schgen.generate import pipeline_doc
    try:
        _pd_path, _pd_changed = pipeline_doc.generate()
        print(f"GEOMETRY PIPELINE: {_pd_path.relative_to(REPO_ROOT)} "
              + ("updated" if _pd_changed else "unchanged"))
    except Exception as exc:  # noqa: BLE001
        print(f"GEOMETRY PIPELINE: FAIL — {exc}")
        ok_all = False

    _lap("pcb gen + DRC + ratsnest images + LAW-5 gate")

    from schgen.verify import model3d_gate
    m3d = model3d_gate.run(rep_dir)
    print(f"{m3d.line()} -> {rep_dir / 'model3d.txt'}")
    for _mpn in sorted(m3d.misfit):
        print(f"  3D MODEL size-misfit (SOFT, render-verify): {_mpn}: "
              f"{m3d.misfit[_mpn]}")
    for _mpn in sorted(m3d.broken):
        print(f"  3D MODEL BROKEN: {_mpn}: {m3d.broken[_mpn]}")
    for _mpn in sorted(m3d.missing):
        print(f"  3D MODEL MISSING (model ...) clause: {_mpn}")
    ok_all = ok_all and m3d.ok

    try:
        from schgen.output import render3d
        _pcb_path = pcb_res.get("pcb") if isinstance(pcb_res, dict) else None
        if getattr(args, "no_render", False):
            _pcb_path = None
        if _pcb_path is not None:
            _r3d = render3d.render(Path(_pcb_path),
                                   PROJECT_ROOT / "renders")
            if _r3d:
                from schgen.generate import gallery as _gal
                if _gal.generate():
                    print(f"GALLERY: {_gal.readme_targets()} "
                          "updated (3D board views)")
    except Exception as exc:  # noqa: BLE001
        print(f"3D RENDERS: skipped — {exc}")

    from schgen.generate import si_constraints
    try:
        si_res = si_constraints.generate(sheets=sheets)
        si_v = si_res["verdict"]
        print(f"SI: {si_res['n_pairs']} diff pairs, {si_res['n_groups']} "
              f"length-match groups -> "
              f"{si_res['dru'].relative_to(REPO_ROOT)} + "
              f"{si_res['md'].relative_to(REPO_ROOT)} — "
              f"{'PASS' if si_v.ok else 'FAIL'}")
        if not si_v.ok:
            print(f"  SI: FAIL — {si_v.summary()}")
            ok_all = False
    except Exception as exc:  # noqa: BLE001
        print(f"SI: FAIL — {exc}")
        ok_all = False

    (rep_dir / "gates.txt").write_text(
        "\n".join(verdicts)
        + f"\nLINK: {'PASS' if res.ok else 'FAIL'}"
        + f"\nBOARD GATE: {'PASS' if board_ok else 'FAIL'}\n")

    from schgen.generate import manifest
    try:
        man_out = manifest.generate(
            sheets, res, pt_res=pt_res, tp_res=tp_res,
            xdc_res=locals().get("xres"))
        print(f"MANIFEST: {man_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"MANIFEST: FAIL — {exc}")
        ok_all = False

    _golden_check(ren_dir, bless=args.bless)
    _lap("si_constraints + manifest + golden check")
    if getattr(args, "timing", False):
        total = sum(d for _, d in _laps)
        print("\n=== board phase timing (wall s) ===")
        for label, dt in sorted(_laps, key=lambda x: -x[1]):
            print(f"  {dt:7.2f}  ({100 * dt / total:4.1f}%)  {label}")
        print(f"  {total:7.2f}  TOTAL")
    if pcb_res is not None:
        import dataclasses as _dc

        def _lean(o):
            if _dc.is_dataclass(o) and not isinstance(o, type):
                out = {}
                for f in _dc.fields(o):
                    v = getattr(o, f.name)
                    if isinstance(v, (int, float, str, bool)) or v is None:
                        out[f.name] = v
                    elif (isinstance(v, (list, tuple))
                          and all(isinstance(x, str) for x in v)):
                        out[f.name] = list(v)[:200]
                return out
            if isinstance(o, dict):
                sub = {k: _lean(v) for k, v in o.items()}
                return {k: v for k, v in sub.items() if v not in (None, {})}
            if isinstance(o, (int, float, str, bool)) or o is None:
                return o
            return None

        _verd = {k: _lean(v) for k, v in pcb_res.items()}
        _verd = {k: v for k, v in _verd.items() if v not in (None, {})}
        _verd["board_ok"] = ok_all
        (rep_dir / "board_verdicts.json").write_text(
            json.dumps(_verd, indent=1, default=str, sort_keys=True) + "\n")
        print(f"VERDICTS: {rep_dir / 'board_verdicts.json'} "
              f"({len(_verd)} gates, machine-readable)")

    print(f"BOARD: {'PASS' if ok_all else 'FAIL'} "
          f"({len(sheets)} sheets -> {CARRIER / 'Zynq_Carrier.kicad_pro'})")
    return 0 if ok_all else 1


def cmd_model3d(args: argparse.Namespace) -> int:
    from schgen.verify import model3d_gate
    rep_dir = CARRIER / "reports"
    res = model3d_gate.run(rep_dir)
    print(res.report())
    print()
    print(res.line() + f" -> {rep_dir / 'model3d.txt'}")
    return 0 if res.ok else 1


def cmd_devkit(args: argparse.Namespace) -> int:
    from schgen.generate import devkit
    return devkit.cmd(args)


def cmd_render3d(args: argparse.Namespace) -> int:
    from schgen.output import render3d
    return render3d.cmd(args)


def cmd_check(args: argparse.Namespace) -> int:
    import subprocess
    stages = [
        ("1/4  board — all sheets + link + cc/short gate",
         [sys.executable, "-m", "schgen", "board"]),
        ("2/4  selftest — mutation kills + determinism",
         [sys.executable, "-m", "schgen", "selftest"]),
        ("3/4  m1_rc — engine smoke",
         [sys.executable, "-m", "schgen.tests.m1_rc"]),
        ("4/4  pytest — unit tests",
         [sys.executable, "-m", "pytest", "schgen/tests", "-q"]),
    ]
    for label, cmd in stages:
        print(f"\n\033[1m==== {label} ====\033[0m")
        rc = subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode
        if rc != 0:
            print(f"\n\033[1;31mREGRESSION FAIL at: {label}\033[0m")
            return rc
    print("\n\033[1;32mREGRESSION PASS — board + selftest + m1_rc + pytest "
          "all green.\033[0m")
    return 0


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
                        help="extract J-connector pin->net contract from "
                             "the SoM project")
    si.add_argument("som_sch")
    si.add_argument("--refs", default="J1,J2,J3")
    si.add_argument("-o", "--output", default="carrier/som_interface.json")
    from schgen.core.som_interface import cmd as _si_cmd
    si.set_defaults(func=lambda a: _si_cmd(a))
    lk = sub.add_parser(
        "link", help="board-level link: port graph + constraints + block "
                     "diagram + hierarchical root sheet with netlist gate")
    lk.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    lk.add_argument("-o", "--outdir", type=Path, default=None)
    lk.add_argument("--no-board", action="store_true",
                    help="skip root-sheet emission + board netlist gate")
    from schgen.core.link import cmd_link
    lk.set_defaults(func=cmd_link)
    bd = sub.add_parser(
        "board", help="ONE command: every sheet gated + link + openable "
                      "carrier KiCad project + constraints + diagram + BOM "
                      "into the committed carrier/ taxonomy")
    bd.add_argument("--bless", action="store_true",
                    help="accept the current renders as golden snapshots")
    bd.add_argument("--timing", action="store_true",
                    help="print a per-phase wall-time breakdown at the end "
                         "(build observability; does not change any artifact)")
    bd.add_argument("--no-render", action="store_true",
                    help="skip the OUTPUT renders (the 37 per-sheet schematic PNGs "
                         "+ the serial ~28 s multi-angle 3D raytrace) — runs every "
                         "GATE on the same emitted board. Fast gate-verify loop; "
                         "the emitted .kicad_sch/.kicad_pcb are byte-identical "
                         "either way (~40 s off a ~300 s build — the per-sheet PNGs "
                         "draw concurrently with ERC so the 3D raytrace is the real "
                         "saving; the 2 ratsnest PNGs still draw in the PCB thread).")
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
    from schgen.partlib.part_gen import cmd_part_add
    padd.set_defaults(func=cmd_part_add)
    xd = sub.add_parser(
        "xdc", help="generate carrier/fpga/Zynq_Carrier_pins.xdc — Vivado "
                    "PACKAGE_PIN+IOSTANDARD for every carrier port on a "
                    "Zynq PL ball (ball map live-extracted from the SoM)")
    xd.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    xd.add_argument("--som", type=Path,
                    default=REPO_ROOT / "som" / "Zynq_SoM.kicad_sch")
    xd.add_argument("--refs", default="J1,J2,J3",
                    help="SoM connectors to trace (default: J1,J2,J3 — the "
                         "PL fans out on J1 too: bank-35 FMC LA08-11)")
    xd.add_argument("-o", "--output", type=Path,
                    default=PROJECT_ROOT / "fpga"
                    / "Zynq_Carrier_pins.xdc")
    from schgen.generate.xdc import cmd_xdc
    xd.set_defaults(func=cmd_xdc)
    fw = sub.add_parser(
        "firmware", help="generate carrier/firmware/zynq_carrier_contract.h "
                         "— the SC-firmware hardware contract (J1 pins + "
                         "STM32 GPIOs + BOOTSEL decode + I2C map + rail/"
                         "module EN map, all netlist-derived)")
    fw.add_argument("-o", "--output", type=Path, default=None)
    from schgen.generate.firmware import cmd_firmware
    fw.set_defaults(func=cmd_firmware)
    sf = sub.add_parser(
        "scfw", help="generate carrier/firmware/sc/ — the SC bring-up "
                     "firmware SCAFFOLD (portable C behind a sc_hal "
                     "abstraction a Zephyr port backs): rail-sequencing "
                     "state machine + I2C/EN/monitor tables + WDT/PD hooks, "
                     "all netlist-derived")
    sf.add_argument("-o", "--output", type=Path, default=None,
                    help="output directory (default: carrier/firmware/sc)")
    from schgen.generate.scfw import cmd_scfw
    sf.set_defaults(func=cmd_scfw)
    mn = sub.add_parser(
        "manual", help="generate carrier/docs/BRINGUP.md — the ordered "
                       "bring-up procedure derived from the netlists")
    mn.add_argument("-o", "--output", type=Path, default=None)
    from schgen.generate.manual import cmd_manual
    mn.set_defaults(func=cmd_manual)
    ga = sub.add_parser(
        "gallery", help="regenerate the render-gallery sections (between "
                        "markers) in README.md + carrier/README.md")
    from schgen.generate.gallery import cmd_gallery
    ga.set_defaults(func=cmd_gallery)
    fl = sub.add_parser(
        "floorplan", help="generate carrier/docs/FLOORPLAN.svg + .md — a "
                          "to-scale 2D placement SUGGESTION derived from "
                          "the netlists (SoM DF40 positions extracted from "
                          "the SoM PCB, edge connectors pinned by mating "
                          "direction, JLC-7628 constraint notes)")
    fl.add_argument("--export", action="store_true",
                    help="write the CURRENT derived plan to carrier/"
                         "floorplan.json (an editable round-trip seed) "
                         "instead of the SVG/MD — edit it to drive placement")
    from schgen.generate.floorplan import cmd_floorplan
    fl.set_defaults(func=cmd_floorplan)
    cp = sub.add_parser(
        "compose", help="T1 composition driver — measure the emitted board's "
                        "composition term ledger (advisory floors = repair "
                        "TRIGGERS, never gates) and, with --repair, propose/"
                        "apply ONE reviewed floorplan.json SpecEdit per "
                        "invocation (pull tuning; edge moves only via "
                        "--allow-intent — the D-1 reviewed-JSON-diff rule)")
    cp.add_argument("--measure", action="store_true",
                    help="measure + write carrier/reports/compose_ledger.* "
                         "(driver-written; a plain board build never touches "
                         "them)")
    cp.add_argument("--repair", action="store_true",
                    help="propose candidate SpecEdits from the repair "
                         "triggers; applies the best ONE unless --dry-run")
    cp.add_argument("--dry-run", action="store_true",
                    help="rank + print candidates; records the measurement "
                         "ledger but NEVER edits carrier/floorplan.json")
    cp.add_argument("--allow-intent", action="append", default=[],
                    metavar="NAME:FROM->TO",
                    help="ratify ONE edge move (repeatable), e.g. "
                         "motor_sense:E->W (D9)")
    cp.add_argument("--max-steps", type=int, default=4,
                    help="reserved (one step per invocation today)")

    def _cmd_compose(args: argparse.Namespace) -> int:
        from schgen.generate import compose_repair as cr
        if args.repair:
            return cr.repair(dry_run=args.dry_run,
                             allow_intent=args.allow_intent,
                             max_steps=args.max_steps)
        from schgen.generate.pcb.placement import build_model
        print("compose: measuring the emitted board (build_model + gates)...")
        led = cr.measure_ledger(build_model())
        cr.write_ledger(led, "measure")
        b = led["board"]
        agg = led["aggregate_hard_margin"]
        print(f"compose: board {b['w']:g}x{b['h']:g} = {b['area_mm2']} mm^2; "
              f"hard margin sum {agg['sum']} / min {agg['min']} mm; "
              f"{len(led['repair_triggers'])} trigger(s) -> "
              f"{cr.LEDGER_JSON}")
        for t in led["repair_triggers"]:
            print(f"  TRIGGER: {t}")
        for s in led["seat_consistency"]:
            print(f"  SEAT-CONSISTENCY: {s}")
        return 0

    cp.set_defaults(func=_cmd_compose)
    pq = sub.add_parser(
        "power-sequence", help="generate carrier/docs/power_sequence.svg — the "
                               "staged power-up bring-up diagram derived from "
                               "the power-tree netlist (always-on rails -> DIP-"
                               "gated rail chain -> gated module rails)")
    pq.add_argument("-o", "--output", type=Path, default=None)
    from schgen.generate.power_sequence import cmd_power_sequence
    pq.set_defaults(func=cmd_power_sequence)
    vv = sub.add_parser(
        "vivado", help="generate carrier/fpga/create_project.tcl — a "
                       "sourceable Vivado project (create_project + part + "
                       "read_xdc + commented PS7 stub), device live-extracted")
    vv.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    vv.add_argument("-o", "--output", type=Path, default=None)
    vv.add_argument("--som", type=Path, default=None)
    vv.add_argument("--xdc", type=Path, default=None)
    vv.add_argument("--refs", default="J1,J2,J3")
    from schgen.generate.vivado import cmd_vivado
    vv.set_defaults(func=cmd_vivado)
    dt = sub.add_parser(
        "devicetree", help="generate carrier/firmware/carrier_pl.dtsi — the "
                           "Zynq PS device-tree fragment (microSD bus + the "
                           "PS MIO pinmux the XDC drops)")
    dt.add_argument("-o", "--output", type=Path, default=None)
    dt.add_argument("--som", type=Path, default=None)
    from schgen.generate.devicetree import cmd_devicetree
    dt.set_defaults(func=cmd_devicetree)
    mf = sub.add_parser(
        "manifest", help="generate carrier/manifest.json — the machine-"
                         "readable design manifest (device, rails, i2c/gpio "
                         "maps, xdc, bom census, TP coverage, artifact hashes)")
    mf.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    mf.add_argument("-o", "--output", type=Path, default=None)
    from schgen.generate.manifest import cmd_manifest
    mf.set_defaults(func=cmd_manifest)
    tpl = sub.add_parser(
        "testplan", help="generate carrier/docs/TEST_PLAN.md — a measurable "
                         "acceptance checklist (spice expected/min/max + "
                         "test-point pads + bring-up DIP stages)")
    tpl.add_argument("-o", "--output", type=Path, default=None)
    from schgen.generate.testplan import cmd_testplan
    tpl.set_defaults(func=cmd_testplan)
    dr = sub.add_parser(
        "design-rules", help="design-rule completeness gate: decoupling, i2c "
                             "pull-ups, reset RC, floating straps — pin "
                             "function inferred by NAME, model-only, waivable")
    dr.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    from schgen.verify.design_rules import cmd_design_rules
    dr.set_defaults(func=cmd_design_rules)
    th = sub.add_parser(
        "thermal", help="per-device thermal Tj gate: Tj = Ta + Pd*RthJA vs "
                        "Tj_max per regulator/load device (reuses the power "
                        "tree); waivable per part")
    th.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    from schgen.verify.thermal import cmd_thermal
    th.set_defaults(func=cmd_thermal)
    prr = sub.add_parser(
        "part-rules", help="per-part rating gate: cap voltage derating + "
                           "regulator input abs-max vs the netlist rail "
                           "(ratings from schgen/ratings.py); waivable per part")
    prr.add_argument("subsystems", nargs="*",
                     help="names in carrier/subsystems/ (default: all)")
    from schgen.verify.part_rules import cmd_part_rules
    prr.set_defaults(func=cmd_part_rules)
    st = sub.add_parser(
        "selftest", help="gate MUTATION testing + build-determinism proof "
                         "(the no-CI answer to 'who watches the watchmen')")
    st.add_argument("sheets", nargs="*",
                    help="sheet names/paths (default: schgen/tests/"
                         "m1_rc_sheet.py + "
                         "carrier/subsystems/uart_bridge/uart_bridge.py)")
    st.add_argument("--keep", action="store_true",
                    help="keep the scratch dir with all mutants")
    from schgen.verify.selftest import cmd_selftest
    st.set_defaults(func=cmd_selftest)
    pt = sub.add_parser(
        "powertree", help="power-tree budget gate: regulator tree from the "
                          "netlists + declared draws -> headroom proof, "
                          "numbered SVG diagram, verdict report")
    pt.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    from schgen.verify.powertree import cmd_powertree
    pt.set_defaults(func=cmd_powertree)
    sx = sub.add_parser(
        "spice", help="auto-extracted divider/RC/ISET/FB spot-checks with "
                      "hard thresholds — analytic closed-form gate + an "
                      "ngspice cross-check layer when installed")
    sx.add_argument("subsystems", nargs="*",
                    help="names in carrier/subsystems/ (default: all)")
    sx.add_argument("--no-ngspice", action="store_true",
                    help="closed-form only (skip the ngspice layer)")
    from schgen.verify.spice import cmd_spice
    sx.set_defaults(func=cmd_spice)
    pc = sub.add_parser(
        "pcb", help="emit carrier/Zynq_Carrier.kicad_pcb — an openable PCB "
                    "FOUNDATION (board outline + forced 4-layer Sig/GND/PWR/"
                    "Sig stackup + net classes + .kicad_dru + every BOM "
                    "footprint placed net-accurately; NOT routed). Requires "
                    "`schgen board` to have emitted the root schematic first.")
    pc.add_argument("--no-drc", action="store_true",
                    help="skip the kicad-cli pcb drc verification pass")
    from schgen.generate.pcb import cmd_pcb
    pc.set_defaults(func=cmd_pcb)
    rn_p = sub.add_parser(
        "ratsnest", help="draw the PLACED board (LAW 5): per-side PNGs + a "
                         "combined SVG showing every footprint as a box colored "
                         "by subsystem + the unrouted airwires + Edge.Cuts + the "
                         "SoM keep-out — the human check that the layout groups "
                         "by subsystem and has zero off-board parts")
    from schgen.generate.ratsnest import cmd_ratsnest
    rn_p.set_defaults(func=cmd_ratsnest)
    pf = sub.add_parser(
        "preflight", help="live JLC/LCSC stock + Basic/Extended + cost check")
    pf.add_argument("subsystems", nargs="+")
    pf.add_argument("--qty", type=int, default=1,
                    help="number of boards (default 1)")
    pf.add_argument("--allow-missing", action="store_true",
                    help="parts without LCSC ids are reported but not fatal")
    from schgen.verify.preflight import STOCK_FLOOR as _SF
    pf.add_argument("--min-stock", type=int, default=_SF,
                    help=f"procurement stock floor; below it a part WARNs even "
                         f"when stock>=need (default {_SF})")
    from schgen.verify.preflight import cmd_preflight
    pf.set_defaults(func=cmd_preflight)
    ss = sub.add_parser(
        "subsystem", help="scaffold a new reusable subsystems/<name>/ package "
                          "skeleton (abstract-port netlist + README + local "
                          "test + SPICE subckt stub)")
    ss.add_argument("name", help="package name (a Python identifier, e.g. usb_pd)")
    ss.add_argument("--force", action="store_true",
                    help="overwrite an existing package skeleton")
    from schgen.generate.subsystem_scaffold import cmd as _ss_cmd
    ss.set_defaults(func=_ss_cmd)
    sc = sub.add_parser(
        "subsystem-check", help="REPORT-FIRST structure gate: every "
                                "subsystems/<name>/ has {<name>.py, README.md, "
                                "test_<name>.py, <name>.cir} + a declared "
                                "abstract INTERFACE matching the netlist")
    sc.add_argument("--strict", action="store_true",
                    help="exit non-zero if any package is incomplete "
                         "(default: report-only)")
    from schgen.verify.subsystem_structure import cmd as _sc_cmd
    sc.set_defaults(func=_sc_cmd)
    cc = sub.add_parser(
        "carrier-check", help="HARD structure gate: every "
                              "carrier/subsystems/<name>/ has {<name>.py, "
                              "__init__.py, README.md, test_<name>.py, "
                              "<name>.cir} + a callable circuit()")
    from schgen.verify.carrier_structure import cmd as _cc_cmd
    cc.set_defaults(func=_cc_cmd)
    ck = sub.add_parser(
        "check", help="the regression bar: board + selftest + m1_rc + pytest "
                      "(stops at first failure; local-only, replaces "
                      "scripts/check.sh)")
    ck.set_defaults(func=cmd_check)
    m3 = sub.add_parser(
        "model3d-check",
        help="3D-model coverage of custom footprints (SOFT): n/m covered + "
             "which are unmatched and why")
    m3.set_defaults(func=cmd_model3d)
    r3 = sub.add_parser(
        "render3d",
        help="3D board renders (top + perspective) for VISUAL verification "
             "(LAW 1) -> carrier/renders/3d_*.png")
    r3.set_defaults(func=cmd_render3d)
    dk = sub.add_parser(
        "devkit", help="build examples/devkit_mini (the 2nd board that reuses "
                       "the subsystems/ library) -> real KiCad schematics + "
                       "hierarchy + renders; proves library reuse")
    dk.add_argument("--no-render", action="store_true",
                    help="skip the per-sheet PNG renders")
    dk.set_defaults(func=cmd_devkit)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
