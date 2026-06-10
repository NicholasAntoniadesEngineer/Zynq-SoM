"""Board-level hierarchy emission + the BOARD NETLIST GATE.

Builds every subsystem with the normal place/route pipeline, re-emits each
sheet in HIERARCHY mode (``PlacedDesign.standalone=False`` → true
hierarchical labels; symbol-instance paths chained under the board root),
generates a root ``board.kicad_sch`` whose sheet symbols carry one
hierarchical pin per PORT, and PROVES with ``kicad-cli sch export netlist``
on the root that every linked PORT net is merged across sheets:

- references are uniquified per sheet (U1 -> U101/U201/...) so the netlist
  is unambiguous board-wide;
- each sheet pin gets a short wire stub + a root-level label carrying the
  port's canonical name — same name = same root net, which is exactly how
  the wave-3 generated J1/J2/J3 connector sheets will bind;
- the gate then checks, pin by pin, that every sheet's PORT pins and every
  rail's pins land on ONE extracted net with the right name. Rails (GND,
  +3V3, +VIN) merge through power symbols and are checked the same way.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import uuid
from pathlib import Path

from schgen import place
from schgen import textmetrics as tm
from schgen.emit import (HierLabel, Junction as EJunction, PlacedDesign,
                         SheetPin, SheetSymbol, Wire, emit)
from schgen.model import Circuit, NetClass, PinRef
from schgen.symbols import Library, pin_page_position
from schgen.verify import netlist_gate

_REF_RE = re.compile(r"^(#?[A-Za-z_]+?)0*(\d+)$")

# root-sheet geometry (1.27 grid)
SHEET_X = 127.0          # left edge of every sheet symbol
SHEET_GAP = 12.7         # vertical gap between sheet symbols
PIN_PITCH = 2.54
STUB = 12.7              # sheet pin -> root label stub length
TOP_Y = 25.4


def _u() -> str:
    return str(uuid.uuid4())


def _renamed_ref(ref: str, index: int) -> str:
    m = _REF_RE.match(ref)
    if not m:
        raise ValueError(f"cannot uniquify reference {ref!r}")
    prefix, num = m.group(1), int(m.group(2))
    return f"{prefix}{index * 100 + num}"


def uniquify(design: PlacedDesign, index: int) -> PlacedDesign:
    """Deep-copy ``design`` with board-unique references (sheet ``index`` is
    1-based: U1 -> U101 on sheet 1, U201 on sheet 2, ...). The circuit's
    parts / net pins / NC pins are renamed in lock-step with the placed
    geometry — the netlist stays graph-identical, only labels change."""
    d = copy.deepcopy(design)
    c = d.circuit
    ref_map = {ref: _renamed_ref(ref, index) for ref in c.parts}
    c.parts = {ref_map[ref]: part for ref, part in c.parts.items()}
    for part in c.parts.values():
        part.ref = ref_map[part.ref]
    for net in c.nets.values():
        net.pins = [PinRef(ref_map[pr.ref], pr.pin) for pr in net.pins]
    c.nc_pins = {PinRef(ref_map[pr.ref], pr.pin) for pr in c.nc_pins}
    for p in d.parts:
        p.ref = ref_map[p.ref]
    for pw in d.powers:
        pw.ref = _renamed_ref(pw.ref, index)   # #PWR01 -> #PWR101 ...
    d.standalone = False
    return d


def _port_nets(c: Circuit) -> list[str]:
    return [n.name for n in c.nets.values() if n.net_class == NetClass.PORT]


def strip_duplicate_flags(designs: list[PlacedDesign], lib: Library) -> None:
    """Keep exactly ONE PWR_FLAG per global rail board-wide.

    Standalone sheets each carry their own PWR_FLAG corner (rail power symbol
    + 2.54 stub + flag); in a hierarchy two flags on one global net are two
    power_out pins in conflict (ERC pin_to_pin error). Duplicates are removed
    as the WHOLE isolated cluster — flag, stub wire and the corner's power
    symbol — and ONLY after proving (net-aware, LAW 0) that nothing else
    touches either stub endpoint: exactly one wire at the flag, a same-net
    power symbol at its far end, no junction/label/part-pin on either point.
    If any check fails the flag stays (ERC noise over netlist risk)."""
    flagged: set[str] = set()
    for d in designs:
        pin_points = set()
        for p in d.parts:
            for pin in lib.get(p.lib_id).pins:
                pin_points.add(pin_page_position(pin, p.x, p.y, p.rotation))
        label_points = {(h.x, h.y) for h in d.hlabels} \
            | {(ll.x, ll.y) for ll in d.llabels}
        junction_points = {(j.x, j.y) for j in d.junctions}
        for flag in [pw for pw in d.powers if pw.lib_id == "power:PWR_FLAG"]:
            net = flag.net_name
            if net not in flagged:
                flagged.add(net)
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


def build_board(sheets, lib: Library, outdir: Path) -> bool:
    """Emit the hierarchy into ``outdir`` and run the board netlist gate.
    ``sheets``: list of schgen.link.SheetCircuit. Returns gate verdict."""
    outdir.mkdir(parents=True, exist_ok=True)
    board_uuid = _u()

    placed: list[tuple[str, PlacedDesign, str]] = []   # (name, design, sym_uuid)
    for i, sc in enumerate(sheets, start=1):
        placement, routed, _geo = place.place_and_route(
            sc.circuit, lib, builder=getattr(sc.module, "placer", None))
        design = PlacedDesign(
            circuit=sc.circuit,
            parts=placement.parts,
            powers=placement.powers,
            wires=[Wire(s.x0, s.y0, s.x1, s.y1) for s in routed.segs],
            junctions=[EJunction(x, y) for x, y in routed.junctions],
            hlabels=placement.hlabels,
            llabels=placement.llabels,
            no_connects=placement.no_connects,
        )
        d = uniquify(design, i)
        placed.append((sc.name, d, _u()))

    # one PWR_FLAG per rail board-wide (duplicates are two power_out pins)
    strip_duplicate_flags([d for _, d, _ in placed], lib)

    for name, d, sym_uuid in placed:
        emit(d, outdir / f"{name}.kicad_sch", lib,
             instance_path=f"/{board_uuid}/{sym_uuid}",
             project="board", sheet_uuid=_u())

    # ---- root sheet -----------------------------------------------------------
    root = PlacedDesign(circuit=Circuit("board", "carrier board root"))
    root.paper = "A3"
    y = TOP_Y
    for page, (name, d, sym_uuid) in enumerate(placed, start=2):
        ports = sorted(_port_nets(d.circuit))
        # the sheet pin SHAPE must mirror the sub-sheet's hierarchical-label
        # shape (input/output/bidirectional): a mismatched pin breaks root
        # connectivity in ERC even though the netlist still resolves.
        shapes = {h.name: h.shape for h in d.hlabels}
        h = PIN_PITCH * (len(ports) + 1)
        w = place.gceil(max((tm.text_wh(p)[0] for p in ports), default=10)
                        + 12.7)
        sym = SheetSymbol(name=name, file=f"{name}.kicad_sch",
                          x=SHEET_X, y=y, w=w, h=h, uuid=sym_uuid, pins=[],
                          page=str(page))
        for k, port in enumerate(ports):
            py = y + PIN_PITCH * (k + 1)
            sym.pins.append(SheetPin(port, SHEET_X, py, rotation=180,
                                     shape=shapes.get(port, "bidirectional")))
            root.wires.append(Wire(SHEET_X, py, SHEET_X - STUB, py))
            # GLOBAL label at the root (the root design is standalone, so
            # hlabels emit as global_label): merges same-named ports across
            # sheet stubs AND sidesteps a kicad-cli ERC quirk where a root
            # LOCAL label on a multi-pin sub-sheet net reports label_dangling
            # despite correct geometry + netlist (minimal repro verified).
            root.hlabels.append(HierLabel(port, SHEET_X - STUB, py,
                                          rotation=180))
        root.sheets.append(sym)
        y += h + SHEET_GAP
    root_path = outdir / "board.kicad_sch"
    emit(root, root_path, lib, sheet_uuid=board_uuid, project="board")
    # board ERC policy == the per-sheet fragment policy (schgen/__main__.py):
    # pin_not_driven at WARNING — author-deferred ports' drivers arrive with
    # later-wave subsystems; the per-sheet build already enforces the
    # STRICTER schgen-side _check_inputs_driven.
    (outdir / "board.kicad_pro").write_text(json.dumps({
        "meta": {"filename": "board.kicad_pro", "version": 3},
        "erc": {"rule_severities": {"pin_not_driven": "warning"}},
    }, indent=2) + "\n")
    print(f"board: emitted {root_path} (+{len(placed)} sub-sheets, "
          f"root labels bind ports by canonical name)")

    ok = _board_gate(placed, root_path, outdir)
    return ok


def _board_gate(placed, root_path: Path, outdir: Path) -> bool:
    """kicad-cli netlist on the ROOT: every linked PORT net and every rail
    must come back as ONE net carrying every expected pin, rightly named."""
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

    # expected pin sets: ports per (canonical name), rails per name
    port_pins: dict[str, list[tuple[str, PinRef]]] = {}
    rail_pins: dict[str, list[tuple[str, PinRef]]] = {}
    for name, d, _sym in placed:
        for net in d.circuit.nets.values():
            tgt = None
            if net.net_class == NetClass.PORT:
                tgt = port_pins
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

    verdict = "PASS" if failures == 0 else f"FAIL ({failures})"
    lines.append(f"BOARD GATE: {verdict} — every linked net merged across "
                 f"sheets" if failures == 0 else f"BOARD GATE: {verdict}")

    # informational ERC (NOT the gate — the gate is the netlist merge)
    erc_rpt = outdir / "board.erc.rpt"
    proc = subprocess.run(
        ["kicad-cli", "sch", "erc", "--severity-error",
         "--exit-code-violations", "-o", str(erc_rpt), str(root_path)],
        capture_output=True, text=True)
    lines.append(f"  (info) root ERC errors: "
                 f"{'0' if proc.returncode == 0 else 'present — see ' + str(erc_rpt)}")

    report = "\n".join(lines)
    (outdir / "board_gate.txt").write_text(report + "\n")
    print(report)
    return failures == 0
