from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from pathlib import Path

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library, pin_page_position
from schgen.layout import place
from schgen.layout import textmetrics as tm
from schgen.output.emit import (
    HierLabel,
    PlacedDesign,
    SheetPin,
    SheetSymbol,
    Wire,
    emit,
    stable_uuid,
)
from schgen.output.emit import Junction as EJunction
from schgen.verify import netlist_gate

_REF_RE = re.compile(r"^(#?[A-Za-z_]+?)0*(\d+)$")

_UNIQ_STRIDE = 1000

SHEET_X = 127.0
SHEET_GAP = 12.7
PIN_PITCH = 2.54
STUB = 12.7
TOP_Y = 25.4


def _renamed_ref(ref: str, index: int, *, sheet: str = "") -> str:
    m = _REF_RE.match(ref)
    if not m:
        raise ValueError(f"cannot uniquify reference {ref!r}")
    prefix, num = m.group(1), int(m.group(2))
    if not 0 <= num < _UNIQ_STRIDE:
        where = f" on sheet {sheet!r}" if sheet else ""
        raise ValueError(
            f"uniquify: reference {ref!r}{where} has number {num} >= "
            f"{_UNIQ_STRIDE} (or a sheet has {_UNIQ_STRIDE}+ '{prefix}' "
            f"parts) — the index*{_UNIQ_STRIDE}+num stride would collide "
            f"into sheet {index + 1}'s band; widen _UNIQ_STRIDE before this "
            f"many parts exist")
    return f"{prefix}{index * _UNIQ_STRIDE + num}"


def uniquify(design: PlacedDesign, index: int) -> PlacedDesign:
    d = copy.deepcopy(design)
    c = d.circuit
    ref_map = {ref: _renamed_ref(ref, index, sheet=c.name) for ref in c.parts}
    c.parts = {ref_map[ref]: part for ref, part in c.parts.items()}
    for part in c.parts.values():
        part.ref = ref_map[part.ref]
    for net in c.nets.values():
        net.pins = [PinRef(ref_map[pr.ref], pr.pin) for pr in net.pins]
    c.nc_pins = {PinRef(ref_map[pr.ref], pr.pin) for pr in c.nc_pins}
    for p in d.parts:
        p.ref = ref_map[p.ref]
    for pw in d.powers:
        pw.ref = _renamed_ref(pw.ref, index, sheet=c.name)
    d.standalone = False
    return d


def _port_nets(c: Circuit) -> list[str]:
    return [n.name for n in c.nets.values() if n.net_class == NetClass.PORT]


def strip_duplicate_flags(designs: list[PlacedDesign], lib: Library) -> None:
    driven: set[str] = set()
    for d in designs:
        etype_of = {}
        for p in d.parts:
            for pin in lib.get(p.lib_id).pins:
                etype_of[(p.ref, pin.number)] = pin.etype
        for net in d.circuit.nets.values():
            if net.net_class == NetClass.SIGNAL:
                continue
            if any(etype_of.get((pr.ref, pr.pin)) == "power_out"
                   for pr in net.pins):
                driven.add(net.name)

    flagged: set[tuple[int | None, str]] = set()
    for sheet_i, d in enumerate(designs):
        pin_points = set()
        for p in d.parts:
            for pin in lib.get(p.lib_id).pins:
                pin_points.add(pin_page_position(pin, p.x, p.y, p.rotation))
        label_points = {(h.x, h.y) for h in d.hlabels} \
            | {(ll.x, ll.y) for ll in d.llabels}
        junction_points = {(j.x, j.y) for j in d.junctions}
        for flag in [pw for pw in d.powers if pw.lib_id == "power:PWR_FLAG"]:
            net = flag.net_name
            n = d.circuit.nets.get(net)
            local = n is not None and n.net_class == NetClass.SIGNAL
            scope = (sheet_i if local else None, net)
            if not local and net in driven:
                pass
            elif scope not in flagged:
                flagged.add(scope)
                continue
            fpos = (flag.x, flag.y)
            touching = [w for w in d.wires
                        if (w.x0, w.y0) == fpos or (w.x1, w.y1) == fpos]
            if len(touching) != 1:
                continue
            stub = touching[0]
            far = (stub.x1, stub.y1) if (stub.x0, stub.y0) == fpos \
                else (stub.x0, stub.y0)
            anchors = [pw for pw in d.powers
                       if (pw.x, pw.y) == far and pw is not flag
                       and pw.net_name == net]
            others = [w for w in d.wires if w is not stub
                      and ((w.x0, w.y0) in (fpos, far)
                           or (w.x1, w.y1) in (fpos, far))]
            if (len(anchors) != 1 or others
                    or fpos in pin_points or far in pin_points
                    or fpos in label_points or far in label_points
                    or fpos in junction_points or far in junction_points):
                continue
            d.powers.remove(flag)
            d.powers.remove(anchors[0])
            d.wires.remove(stub)


def build_board(sheets, lib: Library, outdir: Path, *,
                placements: dict | None = None,
                root_name: str = "board",
                sheet_subdir: str = "",
                sheet_index: dict | None = None,
                reports_dir: Path | None = None) -> bool:
    outdir.mkdir(parents=True, exist_ok=True)
    sheet_dir = outdir / sheet_subdir if sheet_subdir else outdir
    sheet_dir.mkdir(parents=True, exist_ok=True)
    board_uuid = stable_uuid(root_name, "root")

    placed: list[tuple[str, PlacedDesign, str]] = []
    for i, sc in enumerate(sheets, start=1):
        idx = sheet_index.get(sc.name, i) if sheet_index else i
        if placements and sc.name in placements:
            placement, routed = placements[sc.name]
        else:
            placement, routed, _geo = place.place_and_route(sc.circuit, lib)
        design = PlacedDesign(
            circuit=sc.circuit,
            parts=placement.parts,
            powers=placement.powers,
            wires=[Wire(s.x0, s.y0, s.x1, s.y1) for s in routed.segs],
            junctions=[EJunction(x, y) for x, y in routed.junctions],
            hlabels=placement.hlabels,
            llabels=placement.llabels,
            no_connects=placement.no_connects,
            paper=placement.paper,
        )
        d = uniquify(design, idx)
        placed.append((sc.name, d,
                       stable_uuid(root_name, "sheet-symbol", sc.name)))

    strip_duplicate_flags([d for _, d, _ in placed], lib)

    def _emit_and_check(item: tuple) -> tuple[str, str | None]:
        name, d, sym_uuid = item
        emit(d, sheet_dir / f"{name}.kicad_sch", lib,
             instance_path=f"/{board_uuid}/{sym_uuid}",
             project=root_name,
             sheet_uuid=stable_uuid(root_name, "sheet", name))
        verify = copy.deepcopy(d)
        verify.standalone = True
        vpath = sheet_dir / f"{name}.uniqcheck.kicad_sch"
        emit(verify, vpath, lib)
        res = netlist_gate.check(verify.circuit, vpath)
        vpath.unlink(missing_ok=True)
        if res.ok:
            return name, None
        lines = res.summary().splitlines()
        return name, (f"{name}: {lines[1].strip()}"
                      if len(lines) > 1 else name)

    per_sheet_fail: list[str] = []
    if placed:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=(os.cpu_count() or 8)) as ex:
            for _name, fail in ex.map(_emit_and_check, placed):
                if fail is not None:
                    per_sheet_fail.append(fail)
    if per_sheet_fail:
        print("BOARD: per-sheet netlist gate FAIL on uniquified circuit:")
        for f in per_sheet_fail:
            print(f"  {f}")

    root = PlacedDesign(circuit=Circuit(root_name, "carrier board root"))
    entries = []
    for page, (name, d, sym_uuid) in enumerate(placed, start=2):
        ports = sorted(_port_nets(d.circuit))
        shapes = {h.name: h.shape for h in d.hlabels}
        h = PIN_PITCH * (len(ports) + 1)
        w = place.gceil(max((tm.text_wh(p)[0] for p in ports), default=10)
                        + 12.7)
        entries.append((name, sym_uuid, ports, shapes, w, h, page))

    PAPERS = (("A3", 420.0, 297.0), ("A2", 594.0, 420.0), ("A1", 841.0, 594.0))
    TITLE_CLEAR = 25.4
    MARGIN = 10.16
    paper, col_geo = PAPERS[-1][0], []
    for paper, page_w, page_h in PAPERS:  # noqa: B007
        usable_h = page_h - TOP_Y - TITLE_CLEAR
        if max(e[5] for e in entries) > usable_h:
            continue
        cols, col, col_h = [], [], 0.0
        for e in entries:
            if col and col_h + e[5] > usable_h:
                cols.append(col)
                col, col_h = [], 0.0
            col.append(e)
            col_h += e[5] + SHEET_GAP
        if col:
            cols.append(col)
        x_right, col_geo = MARGIN, []
        for col in cols:
            label_w = max((tm.text_wh(p)[0] for e in col for p in e[2]),
                          default=10.0)
            x_col = place.gceil(x_right + label_w + STUB)
            col_geo.append((x_col, col))
            x_right = x_col + max(e[4] for e in col) + SHEET_GAP
        if x_right <= page_w - MARGIN:
            break
    root.paper = paper

    for x_col, col in col_geo:
        y = TOP_Y
        for name, sym_uuid, ports, shapes, w, h, page in col:
            fref = f"{sheet_subdir}/{name}.kicad_sch" if sheet_subdir \
                else f"{name}.kicad_sch"
            sym = SheetSymbol(name=name, file=fref,
                              x=x_col, y=y, w=w, h=h, uuid=sym_uuid, pins=[],
                              page=str(page))
            for k, port in enumerate(ports):
                py = y + PIN_PITCH * (k + 1)
                sym.pins.append(SheetPin(port, x_col, py, rotation=180,
                                         shape=shapes.get(port,
                                                          "bidirectional")))
                root.wires.append(Wire(x_col, py, x_col - STUB, py))
                root.hlabels.append(HierLabel(port, x_col - STUB, py,
                                              rotation=180))
            root.sheets.append(sym)
            y += h + SHEET_GAP
    root_path = outdir / f"{root_name}.kicad_sch"
    emit(root, root_path, lib, sheet_uuid=board_uuid, project=root_name)
    (outdir / f"{root_name}.kicad_pro").write_text(json.dumps({
        "meta": {"filename": f"{root_name}.kicad_pro", "version": 3},
        "erc": {"rule_severities": {"pin_not_driven": "warning"}},
    }, indent=2) + "\n")
    print(f"board: emitted {root_path} (+{len(placed)} sub-sheets, "
          f"root labels bind ports by canonical name)")

    ok = _board_gate(placed, root_path, reports_dir or outdir, lib)
    return ok and not per_sheet_fail


def _board_gate(placed, root_path: Path, outdir: Path, lib: Library) -> bool:
    extracted = netlist_gate.extract_netlist(root_path)
    pin_to_net: dict[PinRef, str] = {}
    for name, pins in extracted.items():
        for pr in pins:
            if not pr.ref.startswith("#"):
                pin_to_net[pr] = name

    def norm(n: str) -> str:
        return n.lstrip("/")

    lines: list[str] = ["board netlist gate", "=" * 60]
    failures = 0

    port_pins: dict[str, list[tuple[str, PinRef]]] = {}
    rail_pins: dict[str, list[tuple[str, PinRef]]] = {}
    port_has_input: set[str] = set()
    port_deferred: set[str] = set()
    for name, d, _sym in placed:
        pts = getattr(d.circuit, "port_types", {})
        for net in d.circuit.nets.values():
            tgt = None
            if net.net_class == NetClass.PORT:
                tgt = port_pins
                pt = pts.get(net.name)
                if pt is not None and getattr(pt, "expect", None):
                    port_deferred.add(net.name)
                for pr in net.pins:
                    op = d.circuit.parts.get(pr.ref)
                    if op is None:
                        continue
                    try:
                        pins = lib.get(op.lib_id).pins
                    except Exception:        # noqa: BLE001
                        continue
                    if any(q.number == pr.pin and q.etype == "input"
                           for q in pins):
                        port_has_input.add(net.name)
            elif net.net_class in (NetClass.POWER, NetClass.GROUND):
                tgt = rail_pins
            if tgt is not None:
                tgt.setdefault(net.name, []).extend(
                    (name, pr) for pr in net.pins)

    for kind, table in (("port", port_pins), ("rail", rail_pins)):
        for net_name, members in sorted(table.items()):
            got = {}
            missing = []
            for sheet, pr in members:
                e = pin_to_net.get(pr)
                if e is None or e.startswith("unconnected-"):
                    missing.append(f"{sheet}:{pr}")
                else:
                    got.setdefault(norm(e), []).append(f"{sheet}:{pr}")
            sheets_in = sorted({s for s, _ in members})
            if missing or len(got) != 1 or norm(next(iter(got))) != net_name:
                failures += 1
                lines.append(
                    f"  FAIL {kind} {net_name!r}: extracted as "
                    f"{sorted(got)} " + (f"missing {missing}" if missing else "")
                )
            else:
                lines.append(
                    f"  ok   {kind} {net_name!r}: 1 net, "
                    f"{len(members)} pins across {len(sheets_in)} sheet(s) "
                    f"[{', '.join(sheets_in)}]")

    for net_name in sorted(port_pins):
        if net_name not in port_has_input or net_name in port_deferred:
            continue
        sheets_in = sorted({s for s, _ in port_pins[net_name]})
        if len(sheets_in) < 2:
            failures += 1
            lines.append(
                f"  FAIL port {net_name!r}: undriven input — carries an input "
                f"pin but resolves to a single sheet {sheets_in} with no cross-"
                f"sheet driver (silent OPEN); drive it, add its peer sheet, or "
                f"declare expect= on the port")
    lines.append(f"  (info) undriven-input PORT check: {len(port_has_input)} "
                 f"input-bearing PORT nets examined "
                 f"({len(port_deferred)} expect-deferred)")

    verdict = "PASS" if failures == 0 else f"FAIL ({failures})"
    lines.append(f"BOARD GATE: {verdict} — every linked net merged across "
                 f"sheets" if failures == 0 else f"BOARD GATE: {verdict}")

    from schgen.__main__ import strip_report_timestamp
    erc_rpt = outdir / "board.erc.rpt"
    proc = subprocess.run(
        ["kicad-cli", "sch", "erc", "--severity-error",
         "--exit-code-violations", "-o", str(erc_rpt), str(root_path)],
        capture_output=True, text=True)
    strip_report_timestamp(erc_rpt)
    lines.append(f"  (info) root ERC errors: "
                 f"{'0' if proc.returncode == 0 else 'present — see ' + str(erc_rpt)}")

    report = "\n".join(lines)
    (outdir / "board_gate.txt").write_text(report + "\n")
    print(report)
    return failures == 0
