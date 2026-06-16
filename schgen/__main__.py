"""schgen CLI.

    python -m schgen build <subsystem> [-o OUTDIR] [--no-render]
    python -m schgen bom <subsystem>... [-o CSV]

Builds carrier/subsystems/<subsystem>.py end-to-end: model -> place
(feasibility loop) -> route (exclusive grid) -> emit -> THREE gates
(netlist == declared, ERC errors == 0, visual zero-overlap) -> render PNG.
Exit is non-zero unless every gate passes. The gates are judges, not knobs.

`build` is a GATING/PREVIEW tool for ONE sheet: it emits the .kicad_sch and
render into a transient tempdir (auto-removed) and persists NOTHING — the
authoritative committed per-sheet renders come ONLY from `schgen board`
(its standalone single-sheet render differs from the hierarchy render, so
letting it write carrier/renders/ would drift the goldens). Pass `-o OUTDIR`
to keep the artifacts somewhere of your choosing.

`bom` exports a JLCPCB-assembly CSV (Comment,Designator,Footprint,LCSC) from
the declared circuits — manufacture-ready part selection lives in the model.
"""

from __future__ import annotations

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

from schgen.layout import place
from schgen.output.emit import PlacedDesign, Wire, emit
from schgen.output.emit import Junction as EJunction
from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library
from schgen.verify import netlist_gate, visual_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBSYSTEMS_DIR = REPO_ROOT / "carrier" / "subsystems"


def _subsystem_path(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if not path.suffix == ".py":
        stem = Path(name_or_path).stem
        # Support BOTH the flat carrier/subsystems/<name>.py layout AND the
        # foldered carrier/subsystems/<name>/<name>.py package layout (the
        # foldered form wins if both somehow exist) — same resolution as
        # schgen.core.link._carrier_subsystem_file, so `schgen build`/`board`
        # discover a folded carrier subsystem exactly as the linker does.
        foldered = SUBSYSTEMS_DIR / stem / f"{stem}.py"
        path = foldered if foldered.exists() else SUBSYSTEMS_DIR / f"{stem}.py"
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
# A subsystem .py may import schgen.core.model (and stdlib) — NOTHING geometric.
# Manual placement is banned structurally: defining `placer` or importing any
# placement/emit/route/text-metrics API fails the build BEFORE the module is
# even executed (the scan is on the source, so a broken geometry import still
# yields the clear gate message, not a stack trace).

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

# Pin types KiCad's ERC accepts as net drivers (pin_not_driven test).
_ERC_DRIVER_ETYPES = {"output", "bidirectional", "tri_state", "passive",
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
        if "input" in etypes and not (etypes & _ERC_DRIVER_ETYPES):
            problems.append(
                f"net {net.name!r}: input pin(s) with no same-sheet driver "
                f"and not a PORT — undriven input")
    return problems


def strip_report_timestamp(report: Path) -> None:
    """kicad-cli stamps its ERC report with wall-clock time — the one
    non-content byte in an otherwise fully content-derived regeneration.
    Elide it from the SAVED artifact (the committed proof) so building the
    board twice produces zero git diff. The gate itself is the kicad-cli
    EXIT CODE plus the violation lines, both untouched."""
    if report.exists():
        first, _, rest = report.read_text().partition("\n")
        report.write_text(
            re.sub(r"\([^)]*?(Encoding [^)]*)\)", r"(\1)", first)
            + "\n" + rest)


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
    # `build` is a GATING/PREVIEW tool: with no -o it writes the emitted
    # .kicad_sch + render into a transient TemporaryDirectory and persists
    # NOTHING. The committed per-sheet renders come ONLY from `schgen board`
    # (the hierarchy render), so a standalone build never overwrites
    # carrier/renders/<name>.png (which would drift the goldens).
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
    """JLCPCB assembly BOM: Comment,Designator,Footprint,LCSC (one row per
    value+footprint+LCSC group). Parts missing an LCSC field are listed and
    fail the export unless --allow-missing."""
    rows: dict[tuple[str, str, str], list[str]] = {}
    missing: list[str] = []
    for name in args.subsystems:
        mod = _load_subsystem(name)
        c = mod.circuit()
        for ref, part in sorted(c.parts.items()):
            if part.fields.get("BOM") == "exclude":
                continue       # pad-only test points: copper, no BOM line
            lcsc = part.fields.get("LCSC", "")
            if not lcsc:
                missing.append(f"{c.name}:{ref} ({part.value})")
            rows.setdefault((part.value, part.footprint, lcsc), []).append(ref)
    # Standalone preview: default to the CWD (the authoritative per-board
    # bom_jlc.csv is written into carrier/manufacturing/ by `schgen board`);
    # pass -o to choose. Never carrier/out.
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


CARRIER = REPO_ROOT / "carrier"


def _pcb_error_count(pcb_path: Path) -> int:
    """kicad-cli pcb drc at ERROR severity → number of real (non-unrouted)
    violations. Unrouted-net items are reported separately by kicad-cli and do
    NOT count as DRC violations, so a clean foundation returns 0."""
    import tempfile as _tf
    with _tf.TemporaryDirectory(prefix="schgen_pcbdrc_") as td:
        rpt = Path(td) / "drc.json"
        subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json",
             "--severity-error", "-o", str(rpt), str(pcb_path)],
            capture_output=True, text=True)
        if not rpt.exists():
            return -1
        try:
            data = json.loads(rpt.read_text())
        except Exception:  # noqa: BLE001
            return -1
    return len(data.get("violations", []))


def _ahash(png: Path) -> str:
    """16x16 average hash — perceptual, robust to PNG byte noise."""
    from PIL import Image
    im = Image.open(png).convert("L").resize((16, 16))
    px = list(im.getdata())
    avg = sum(px) / len(px)
    return "".join("1" if v > avg else "0" for v in px)


def _golden_check(ren_dir: Path, bless: bool) -> None:
    """Golden render snapshots: drift WARNS, --bless accepts new goldens.

    Only the per-sheet SCHEMATIC renders are golden-tracked. The PCB ratsnest
    images (ratsnest_top/bottom.png) are PLACEMENT renders that legitimately
    change whenever the placer moves a part, and are gated separately by the
    LAW-5 ratsnest gate — so they are excluded from the schematic golden set."""
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
    """ONE command: every sheet gated, link + board netlist gate, an
    openable carrier KiCad project, constraints, block diagram, JLC BOM —
    all written into the committed carrier/ output taxonomy."""
    import tempfile

    from schgen.generate import constraints
    from schgen.output import diagram
    from schgen.generate import board as board_mod
    from schgen.core.link import all_subsystem_paths, link, load_som_contract, load_subsystem

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

    # Per-phase wall-time breakdown (printed only with --timing; stdout-only, so
    # it changes no committed artifact). Build observability: the board build is
    # dominated by the kicad-cli passes + PCB DRC + downstream generators, NOT by
    # place/route — `--timing` makes that visible so speed work stays targeted.
    import time as _time
    _laps: list[tuple[str, float]] = []
    _t_mark = [_time.perf_counter()]

    def _lap(label: str) -> None:
        now = _time.perf_counter()
        _laps.append((label, now - _t_mark[0]))
        _t_mark[0] = now

    # Pass 1 (sequential, CPU-bound): purity / validate / place+route / emit /
    # visual. Records the per-name outcome so the parallel gate pass and the
    # verdict pass below preserve EXACT names-order semantics — gates.txt is
    # written from `verdicts` and is order-sensitive.
    prepared: list[tuple] = []            # sheets that reached the kicad-cli gates
    early_fail: dict[str, str | None] = {}  # name -> gates.txt verdict (or None)
    for name in names:
        spath = _subsystem_path(name)
        purity = _purity_violations(spath)
        if purity:
            print(f"{name}: PURITY GATE FAIL")
            for v in purity:
                print(f"  {v}")
            ok_all = False
            early_fail[name] = None         # no gates.txt verdict (as before)
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
        except Exception as exc:  # noqa: BLE001 — one blocked sheet must not
            # kill the whole board run: record the FAIL verdict (board exits
            # non-zero) and keep gating/linking every other sheet.
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

    # Pass 2 (parallel): the three per-sheet kicad-cli gates are independent
    # across sheets and dominate wall time. netlist export (unique tempdir),
    # ERC (per-sheet .kicad_pro + report), render (per-sheet PNG) all write
    # only per-sheet paths, so running the child processes concurrently is
    # behaviour-preserving — each gate sees the exact same inputs/outputs as
    # the serial run; only the dispatch is threaded.
    def _gate_one(item: tuple):
        name, _sc, c, sch, _vis, _paper = item
        net_res = netlist_gate.check(c, sch)
        erc_ok, _txt = _erc(sch, rep_dir / f"{name}.erc.rpt")
        _render(sch, ren_dir / f"{name}.png")
        return name, net_res, erc_ok

    gate_out: dict[str, tuple] = {}
    if prepared:
        from concurrent.futures import ThreadPoolExecutor
        # kicad-cli ops are I/O-bound subprocess waits, so use all cores (not the
        # old min(8,...) cap) — more concurrent launches, same per-sheet inputs.
        with ThreadPoolExecutor(max_workers=(os.cpu_count() or 8)) as ex:
            for name, net_res, erc_ok in ex.map(_gate_one, prepared):
                gate_out[name] = (net_res, erc_ok)

    _lap("pass1+2: place/route + per-sheet kicad-cli (netlist/erc/render)")

    # Pass 3 (sequential, names order): assemble verdicts (-> gates.txt) and
    # the ordered `sheets` list exactly as the original serial loop did.
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

    # INDEPENDENT connected-components gate (verification P4, no kicad-cli):
    # rebuilds connectivity from the emitted GEOMETRY (net-blind union-find over
    # wires/junctions/pins, legal same-name label/power merges) and compares to
    # the declared nets — a SHORT = two declared nets in one component, an OPEN
    # = one net split. A second oracle disjoint from kicad-cli, so the board
    # never rests on a single netlist witness (LAW 0). Reuses the in-memory
    # placements/prepared already built — no extra place/route.
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

    # SYMBOL-LAW gate (user decree "0 hand-built symbols"): every board part on
    # a schgen-local lib_id must be a (power) rail flag, never a hand-drawn
    # real-part symbol. HARD-FAIL the board on any violation (a tracked-pending
    # exception list keeps a documented in-progress migration from blocking).
    from schgen.verify import symbol_law
    sl_res = symbol_law.check([sc.circuit for sc in sheets], lib)
    (rep_dir / "symbol_law.txt").write_text(sl_res.summary() + "\n")
    print(sl_res.summary().splitlines()[0]
          + f" -> {rep_dir / 'symbol_law.txt'}")
    for _v in sl_res.violations:
        print(f"  {_v}")
    ok_all = ok_all and sl_res.ok

    # link + constraints + diagram
    som_nets = load_som_contract()
    res = link(sheets, som_nets)
    (rep_dir / "link_report.txt").write_text(res.report() + "\n")
    print(f"LINK: {'PASS' if res.ok else 'FAIL'} "
          f"({len(res.errors)} errors, {len(res.warnings)} warnings)")
    ok_all = ok_all and res.ok
    constraints.export(sheets, man_dir)
    diagram.render(res, som_nets, REPO_ROOT / "docs" / "block_diagram.svg")

    # STABLE refdes: a part's board-unique reference is a permanent identity.
    # carrier/sheet_index.json is a FROZEN, APPEND-ONLY name->band-index map, so
    # adding/removing/reordering a sheet never re-strides another sheet's refdes
    # (the old scheme keyed the band on alphabetical position -> inserting a
    # mid-alphabet sheet renumbered every later sheet). New sheets append at the
    # next free index; the registry is committed so the assignment is permanent.
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

    # hierarchy: the openable carrier project + the board netlist gate
    board_ok = board_mod.build_board(
        sheets, lib, CARRIER, placements=placements,
        root_name="Zynq_Carrier", sheet_subdir="schematic",
        sheet_index=_sheet_index, reports_dir=rep_dir)
    ok_all = ok_all and board_ok

    _lap("pass3 + cc_gate + link + build_board (hierarchy + board ERC)")

    # SPEED: the PCB foundation + its kicad-cli DRC (~70 s, the 2nd-biggest
    # phase) is independent of every verify gate + downstream doc generator that
    # follows — nothing before the SI step (which extends the .dru it writes)
    # reads the .kicad_pcb/.dru. Run it on a worker thread NOW so its ~70 s
    # overlaps the ~90 s verify+downstream phase, and JOIN it just before SI.
    # Outputs are content-derived, so concurrency changes not one emitted byte.
    import threading as _threading
    from schgen.generate import pcb as pcb_mod
    _pcb_holder: dict[str, object] = {}

    def _run_pcb() -> None:
        try:
            _pcb_holder["res"] = pcb_mod.generate(run_drc=True)
        except Exception as exc:  # noqa: BLE001 — re-raised at the join site
            _pcb_holder["exc"] = exc
    _pcb_thread = _threading.Thread(target=_run_pcb, name="pcb+drc", daemon=True)
    _pcb_thread.start()

    # JLC BOM across every sheet (missing LCSC = warning at board level)
    rows: dict[tuple[str, str, str], list[str]] = {}
    missing: list[str] = []
    for sc in sheets:
        for ref, part in sorted(sc.circuit.parts.items()):
            if part.fields.get("BOM") == "exclude":
                continue       # pad-only test points: copper, no BOM line
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

    # BOM footprint gate (DEF-3): a BOM line with no footprint is un-orderable
    # — JLC (and any assembler) cannot place it. Inline Device:C/Device:R now
    # default a 0603/0805 footprint (model._default_footprint), so this gate
    # backstops any remaining footprint-less BOM part (e.g. a use_part whose
    # library FOOTPRINT is blank).
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

    # power-tree budget gate (round 4): regulator tree from the netlists +
    # declared draws -> headroom proof, numbered SVG, verdict report.
    from schgen.verify import powertree
    pt_res = powertree.run(sheets, rep_dir, CARRIER / "docs")
    print(f"POWER TREE: {'PASS' if pt_res.ok else 'FAIL'} "
          f"({len(pt_res.regs)} regulators, {len(pt_res.findings)} findings"
          f" -> {rep_dir / 'power_tree.txt'})")
    for e in pt_res.errors:
        print(f"  POWER TREE ERROR: {e}")
    ok_all = ok_all and pt_res.ok

    # per-device thermal (Tj) gate (verification P2): turns the PWR-2/PWR-3
    # thermal decisions (prose-only) into a regression lock. Reuses pt_res'
    # regulator tree + I_out; FAILS on any device whose Tj = Ta + Pd*RthJA
    # exceeds Tj_max - margin (real exceptions author-waived: c.waive_thermal).
    from schgen.verify import thermal
    th_res = thermal.run(sheets, rep_dir, pt_res=pt_res)
    print(f"THERMAL: {'PASS' if th_res.ok else 'FAIL'} "
          f"({len(th_res.devices)} devices, {len(th_res.errors)} over-limit, "
          f"{len(th_res.findings)} unspeced -> {rep_dir / 'thermal.txt'})")
    for e in th_res.errors:
        print(f"  THERMAL ERROR: {e}")
    ok_all = ok_all and th_res.ok

    # test-point coverage gate (round 4): every rail + key single-ended bus
    # owns a probe point or an explicit author waiver.
    from schgen.verify import testpoints
    tp_res = testpoints.check_coverage(sheets)
    (rep_dir / "testpoints.txt").write_text(tp_res.report() + "\n")
    print(f"TESTPOINTS: {'PASS' if tp_res.ok else 'FAIL'} "
          f"({tp_res.covered}/{len(tp_res.required)} required covered, "
          f"{len(tp_res.waived)} waived -> {rep_dir / 'testpoints.txt'})")
    for e in tp_res.errors:
        print(f"  TESTPOINT ERROR: {e}")
    ok_all = ok_all and tp_res.ok

    # design-rule completeness gate (verification P1): infers pin FUNCTION by
    # NAME (etypes are flat 'passive') and proves the netlist is electrically
    # COMPLETE — every IC supply pin decoupled, every i2c bus pulled, every
    # reset has an RC, no config strap floats. Strict (LAW 4): real exceptions
    # are author-waived (c.waive_decap/_pull/_reset/_strap), never relaxed.
    from schgen.verify import design_rules
    dr_res = design_rules.run(sheets, rep_dir, lib=lib)
    print(f"DESIGN RULES: {'PASS' if dr_res.ok else 'FAIL'} "
          f"({len(dr_res.findings)} findings, {len(dr_res.waived)} waived "
          f"-> {rep_dir / 'design_rules.txt'})")
    for f in dr_res.findings:
        print(f"  DESIGN RULE: {f}")
    ok_all = ok_all and dr_res.ok

    # per-part RULE engine (verification): cap voltage derating + regulator
    # input abs-max vs the rail the netlist puts each part on (ratings from
    # schgen/ratings.py; rail tree reused from pt_res). Fail-soft on unspeced;
    # tight margins are author-waived (c.waive_part_rule). LAW 4.
    from schgen.verify import part_rules
    pr_res = part_rules.run(sheets, rep_dir, pt_res=pt_res)
    print(f"PART RULES: {'PASS' if pr_res.ok else 'FAIL'} "
          f"({pr_res.checked} checks, {len(pr_res.findings)} findings, "
          f"{len(pr_res.unspecced)} unspeced, {len(pr_res.waived)} waived "
          f"-> {rep_dir / 'part_rules.txt'})")
    for f in pr_res.findings:
        print(f"  PART RULE: {f}")
    ok_all = ok_all and pr_res.ok

    # BOM value gate (data-integrity, LAW 0): the LCSC code behind every inline
    # passive must resolve to the DECLARED value/package (live-verified catalog
    # in schgen/verify/data/lcsc_values.json). Closes the C25750-class hole — a
    # mis-keyed 40.2k FB resistor that was really a 120k part (~13 V on the 5 V
    # rail). HARD-FAIL on a value mismatch; uncatalogued codes are reported.
    from schgen.verify import bom_values
    bv_res = bom_values.run(sheets, rep_dir)
    print(f"BOM VALUES: {'PASS' if bv_res.ok else 'FAIL'} "
          f"({bv_res.checked} checks, {len(bv_res.mismatches)} mismatch, "
          f"{len(bv_res.unverified)} unverified -> {rep_dir / 'bom_values.txt'})")
    for m in bv_res.mismatches:
        print(f"  BOM VALUE: {m}")
    ok_all = ok_all and bv_res.ok

    # footprint pad-coverage gate (LAW 0): every symbol pin NUMBER must exist as
    # a PAD in the part's assigned footprint — a pin with no pad is a guaranteed
    # OPEN that ERC/netlist/cc gates are all blind to (they reason about the
    # SYMBOL, never the footprint). This is the exact hole that let ethernet:T1
    # (HX5008NLT) use pins 25/26 on a 24-pad SOIC-24W — the 4th gigabit pair was
    # dead copper. That T1 defect is now fixed (faithful 24-pad HX5008NL
    # dossier), so the board has zero pin-without-pad and this gate is HARD-FAIL.
    from schgen.verify import footprint_pads
    fpp_res = footprint_pads.run(sheets, rep_dir, lib=lib)
    print(f"FOOTPRINT PADS: {'PASS' if fpp_res.ok else 'FAIL'} "
          f"({fpp_res.checked} parts, {len(fpp_res.violations)} pin(s) with "
          f"no pad, {len(set(fpp_res.unresolved))} unresolved fp "
          f"-> {rep_dir / 'footprint_pads.txt'})")
    for v in fpp_res.violations:
        print(f"  FOOTPRINT PAD: {v}")
    ok_all = ok_all and fpp_res.ok

    # pin-completeness gate (LAW 0): every multi-pin IC pin is netted or an
    # explicit NC — a pin in neither is a silent float (probable missing
    # connection). Circuit.validate() already enforces this at build time, so
    # this is the standalone regression witness + the curated NC ALLOWLIST
    # emitter (the artifact that lets the gate promote to hard-fail once every
    # NC is blessed). REPORT-FIRST: reports the float count + NC allowlist and
    # writes pin_completeness.txt but does NOT fail the board. PROMOTE TO
    # HARD-FAIL once the NC allowlist is fully blessed (uncomment below).
    from schgen.verify import pin_completeness
    pc_res = pin_completeness.run(sheets, rep_dir, lib=lib)
    print(f"PIN COMPLETENESS: {'PASS' if pc_res.ok else 'REPORT'} "
          f"({pc_res.parts_checked} parts, {len(pc_res.floats)} silent float(s), "
          f"{pc_res.nc_total} NC pins: {len(pc_res.nc_seeded)} blessed/"
          f"{len(pc_res.nc_new)} to-bless -> {rep_dir / 'pin_completeness.txt'})")
    for f in pc_res.floats:
        print(f"  PIN COMPLETENESS: {f}")
    # REPORT-FIRST: ok_all unchanged until the NC allowlist is fully blessed.
    # ok_all = ok_all and pc_res.ok

    # reusable-subsystem PACKAGE-STRUCTURE gate (REPORT-FIRST): every migrated
    # subsystems/<name>/ library package has its four contract artifacts +
    # a declared abstract INTERFACE that matches its netlist's externals. The
    # HARD-FAIL (promoted 2026-06-15 once every portable subsystem was packaged):
    # every subsystems/<name>/ package must be COMPLETE + well-formed (the four
    # contract artifacts + a circuit(meta=) exposing a declared abstract
    # INTERFACE that matches the built externals). An incomplete/ drifted package
    # now FAILS the board — the reusable-subsystem library cannot silently rot.
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

    # carrier PACKAGE-STRUCTURE gate (HARD): every carrier/subsystems/<name>/ is
    # a complete package (the four artifacts + __init__ + a callable circuit()),
    # uniform with the generic library — adapters AND carrier-local sheets alike.
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

    # SPICE/analytic spot-checks (round 4, P5 pulled forward): dividers,
    # RC ramps, ISET/FB math auto-extracted from the netlists, thresholds
    # hard. The closed-form analytics ARE the gate; the ngspice .op
    # cross-check layer runs whenever ngspice is installed (1% agreement
    # enforced) and degrades honestly to analytic-only when it is not.
    from schgen.verify import spice
    sp_res = spice.run(sheets, rep_dir, allow_ngspice=True)
    print(f"SPICE: {'PASS' if sp_res.ok else 'FAIL'} "
          f"({sp_res.n_checks} checks, {sp_res.engine} "
          f"-> {rep_dir / 'spice.txt'})")
    for e in sp_res.errors:
        print(f"  SPICE ERROR: {e}")
    ok_all = ok_all and sp_res.ok

    # Vivado pin constraints (round 4): every carrier PORT bound through
    # J2/J3 to a Zynq PL ball, ball map live-extracted from the SoM project
    # and cross-checked against the committed contract.
    from schgen.generate import xdc
    try:
        xres = xdc.generate(sheets, CARRIER / "fpga" / "Zynq_Carrier_pins.xdc")
        print(f"XDC: {xres.path} ({xres.count} pins; "
              + "; ".join(xres.checks[-2:]) + ")")
    except xdc.XdcError as exc:
        print(f"XDC: FAIL — {exc}")
        ok_all = False

    # Vivado project-creation TCL (downstream P2): turns the generated XDC into
    # a sourceable Vivado project — same device + clock-capable port set as the
    # XDC, derived the same way (live SoM extraction).
    from schgen.generate import vivado
    try:
        vtcl = vivado.generate(sheets, CARRIER / "fpga" / "create_project.tcl")
        print(f"VIVADO: {vtcl}")
    except (vivado.VivadoError, xdc.XdcError) as exc:
        print(f"VIVADO: FAIL — {exc}")
        ok_all = False

    # round-4 system artifacts, derived from the same netlists.
    from schgen.generate import firmware, gallery, manual, testplan
    try:
        fw_out = firmware.generate()
        print(f"FIRMWARE CONTRACT: {fw_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"FIRMWARE CONTRACT: FAIL — {exc}")
        ok_all = False
    try:
        mn_out = manual.generate()
        print(f"BRINGUP MANUAL: {mn_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"BRINGUP MANUAL: FAIL — {exc}")
        ok_all = False
    try:
        # measurable acceptance test plan (downstream P4 + DFM-3): SPICE
        # expected/limit values joined to test-point probe pads + DIP stages.
        tp_out = testplan.generate(sheets=sheets)
        print(f"TEST PLAN: {tp_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"TEST PLAN: FAIL — {exc}")
        ok_all = False
    try:
        changed = gallery.generate()
        print("GALLERY: README.md + carrier/README.md "
              + ("updated" if changed else "unchanged"))
    except Exception as exc:  # noqa: BLE001
        print(f"GALLERY: FAIL — {exc}")
        ok_all = False

    # PS-side device-tree fragment (downstream P3): the PS twin of the XDC —
    # microSD bus + the bare PS MIO pins the XDC drops, into a commented .dtsi.
    from schgen.generate import devicetree
    try:
        dt_out = devicetree.generate(CARRIER / "firmware" / "carrier_pl.dtsi")
        print(f"DEVICETREE: {dt_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"DEVICETREE: FAIL — {exc}")
        ok_all = False

    # SC bring-up firmware SCAFFOLD (Stream E): the IMPLEMENTATION twin of the
    # firmware CONTRACT — portable C behind a sc_hal abstraction a Zephyr port
    # backs (rail-sequencing state machine + I2C/EN/monitor tables + WDT/PD
    # hooks), all netlist-derived. Additive; deterministic.
    from schgen.generate import scfw
    try:
        scfw_out = scfw.generate(CARRIER / "firmware" / "sc")
        print(f"SCFW SCAFFOLD: {CARRIER / 'firmware' / 'sc'} "
              f"({len(scfw_out)} files)")
    except Exception as exc:  # noqa: BLE001
        print(f"SCFW SCAFFOLD: FAIL — {exc}")
        ok_all = False

    # floorplan suggestion (SVG + MD), derived from the same sheets/link
    from schgen.generate import floorplan
    try:
        fp_paths = floorplan.generate(sheets, res)
        print("FLOORPLAN: " + " + ".join(
            str(p.relative_to(REPO_ROOT)) for p in fp_paths)
            + " (suggestion, not constraint)")
    except Exception as exc:  # noqa: BLE001
        print(f"FLOORPLAN: FAIL — {exc}")
        ok_all = False

    # power-up SEQUENCE diagram (SVG), derived from the SAME pt_res power-tree
    # analysis the budget gate above ran — the staged bring-up drawn (stage-0
    # always-on rails -> the DIP-gated rail chain -> the gated module rails), so
    # the diagram can never drift from the netlist. Deterministic; additive.
    from schgen.generate import power_sequence
    try:
        ps_out = power_sequence.generate(sheets, pt_res)
        print(f"POWER SEQUENCE: {ps_out.relative_to(REPO_ROOT)} "
              f"(staged bring-up diagram)")
    except Exception as exc:  # noqa: BLE001
        print(f"POWER SEQUENCE: FAIL — {exc}")
        ok_all = False

    _lap("verify gates (powertree..spice) + xdc/vivado + downstream doc generators")

    # PCB FOUNDATION (Stream D): an openable .kicad_pcb seeded from the merged
    # board netlist just emitted — outline + forced 4-layer Sig/GND/PWR/Sig
    # stackup + net classes + .kicad_dru + every BOM footprint placed net-
    # accurately (NOT routed). Additive: a DRC ERROR (beyond the expected
    # unrouted-net items) fails the board; warnings (silk, lib-not-in-config)
    # do not. Started on a worker thread right after build_board (above) so its
    # ~70 s DRC overlaps the verify+downstream phase; JOINED here, before SI
    # extends the .dru it wrote. It merged into the same .kicad_pro build_board
    # opened (build_board finished before the thread started).
    try:
        _pcb_thread.join()
        if "exc" in _pcb_holder:
            raise _pcb_holder["exc"]      # type: ignore[misc]
        pcb_res = _pcb_holder["res"]
        drc = pcb_res["drc"]
        derr = (drc or {}).get("n_violations", 0)
        # n_violations counts errors+warnings; the gate is the error count via
        # a second strict pass (severity-error only) inside run_pcb_drc's rc.
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

        # LAW-5 RATSNEST/PLACEMENT gate (HARD): the visual oracle DRC=0 can't be.
        # The PCB step already drew the per-side ratsnest images + ran the gate
        # on the SAME model (no rebuild). FAIL the board on any off-board part, a
        # dispersed (non-grouped) subsystem, or a cross-subsystem airwire budget
        # overrun. The IMAGES (carrier/renders/ratsnest_{top,bottom}.png +
        # carrier/docs/RATSNEST.svg) are the human check this gate backstops.
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
    except Exception as exc:  # noqa: BLE001
        print(f"PCB: FAIL — {exc}")
        ok_all = False

    _lap("pcb gen + DRC + ratsnest images + LAW-5 gate")

    # 3D-MODEL COVERAGE (SOFT): every custom footprint at parts/<MPN>/ should
    # reference a stock KiCad 3D model that EXISTS on disk so the carrier 3D
    # viewer populates. A missing model is neither an ERC nor a DRC nor a
    # netlist defect — no other gate sees it — so this reports coverage + the
    # exact gaps so the number can only move DOWN visibly, never silently. SOFT
    # by design: some bespoke parts (mezzanines, magnetics module, an exotic RTC
    # package) have no faithful stock body, and a WRONG 3D body is worse than
    # none. Does NOT touch ok_all (only an UNEXPECTED broken/missing ref, not a
    # documented unmatched part, makes the gate verdict False).
    from schgen.verify import model3d_gate
    m3d = model3d_gate.run(rep_dir)
    print(f"{m3d.line()} -> {rep_dir / 'model3d.txt'}")
    for _mpn in sorted(m3d.broken):
        print(f"  3D MODEL BROKEN: {_mpn}: {m3d.broken[_mpn]}")
    for _mpn in sorted(m3d.missing):
        print(f"  3D MODEL MISSING (model ...) clause: {_mpn}")

    # SIGNAL-INTEGRITY CONSTRAINTS (not routing): harvest every diff pair the
    # schematic declares, join to the researched si_spec targets, and APPEND
    # diff-pair + matched-length design rules to the board .kicad_dru just
    # written by the PCB step, plus a human-readable SI_CONSTRAINTS.md. Runs
    # AFTER the PCB foundation (it extends that .dru) and after every existing
    # gate. The assertion (every declared pair has an emitted constraint) flips
    # the board verdict ONLY if a declared pair is uncovered — additive, like
    # the PCB hook above; it never relaxes an existing gate (LAW 4).
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

    # design manifest (downstream P5, integration spine): machine-readable
    # serialization of the state this run already holds (device, rails,
    # i2c/gpio maps, xdc census, bom census, test-point coverage) + a sha256 of
    # every generated carrier/ file. Deterministic; the stable contract other
    # tools consume instead of scraping text.
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
    print(f"BOARD: {'PASS' if ok_all else 'FAIL'} "
          f"({len(sheets)} sheets -> {CARRIER / 'Zynq_Carrier.kicad_pro'})")
    return 0 if ok_all else 1


def cmd_model3d(args: argparse.Namespace) -> int:
    """3D-MODEL COVERAGE check (SOFT): how many custom footprints reference a
    stock KiCad 3D model that EXISTS on disk, and which are unmatched + why.
    Prints the same one-line summary cmd_board emits plus the full report;
    exit 0 always (SOFT) unless an UNEXPECTED broken/missing ref appears."""
    from schgen.verify import model3d_gate
    rep_dir = CARRIER / "reports"
    res = model3d_gate.run(rep_dir)
    print(res.report())
    print()
    print(res.line() + f" -> {rep_dir / 'model3d.txt'}")
    return 0 if res.ok else 1


def cmd_check(args: argparse.Namespace) -> int:
    """The schgen regression bar (formerly scripts/check.sh): run the four gates
    that must ALL pass before a commit, stopping at the first failure —
      1. board    every sheet gated + board link/merge + cc/short detector
      2. selftest gate MUTATION kills + cross-PYTHONHASHSEED determinism
      3. m1_rc    the M1 RC-spine engine smoke sheet
      4. pytest   the unit suite (model, gates, part-gen, foldering, ...)
    Local only (no online CI by project policy)."""
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
                        help="extract J-connector pin->net contract from the SoM project")
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
                    default=REPO_ROOT / "carrier" / "fpga"
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
    from schgen.generate.floorplan import cmd_floorplan
    fl.set_defaults(func=cmd_floorplan)
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
                         "m1_rc_sheet.py + carrier/subsystems/uart_bridge/uart_bridge.py)")
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
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
