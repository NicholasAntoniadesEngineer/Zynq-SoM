"""Board-level hierarchy emission + the BOARD NETLIST GATE.

Builds every subsystem with the normal place/route pipeline, re-emits each
sheet in HIERARCHY mode (``PlacedDesign.standalone=False`` → true
hierarchical labels; symbol-instance paths chained under the board root),
generates a root ``board.kicad_sch`` whose sheet symbols carry one
hierarchical pin per PORT, and PROVES with ``kicad-cli sch export netlist``
on the root that every linked PORT net is merged across sheets:

- references are uniquified per sheet (U1 -> U1001/U2001/... at the default
  _UNIQ_STRIDE of 1000) so the netlist is unambiguous board-wide;
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

# Per-sheet band width for board-unique references. Each sheet `index`
# owns the band [index*STRIDE, index*STRIDE+STRIDE-1] PER PREFIX, so the
# renamed number decodes uniquely ONLY while every original number is
# < STRIDE. The old stride of 100 was BELOW the real maximum: a dense
# sheet legitimately emits 100+ power symbols (#PWR), and at stride 100
# sheet i's #PWR(100+k) collided with sheet i+1's #PWR(k) board-wide
# (electrically harmless — power symbols merge by NET NAME and the
# netlist gates skip '#'-refs — but a genuine reference-uniqueness break
# the original stride produced silently). 1000 clears the observed 128
# with a 7x margin; the guard below still fires loudly if any sheet ever
# approaches it (F4).
_UNIQ_STRIDE = 1000

# root-sheet geometry (1.27 grid)
SHEET_X = 127.0          # left edge of every sheet symbol
SHEET_GAP = 12.7         # vertical gap between sheet symbols
PIN_PITCH = 2.54
STUB = 12.7              # sheet pin -> root label stub length
TOP_Y = 25.4


def _renamed_ref(ref: str, index: int, *, sheet: str = "") -> str:
    m = _REF_RE.match(ref)
    if not m:
        raise ValueError(f"cannot uniquify reference {ref!r}")
    prefix, num = m.group(1), int(m.group(2))
    # The board-unique number is `index*_UNIQ_STRIDE + num`, so each sheet
    # owns the band [index*STRIDE, index*STRIDE+STRIDE-1] PER PREFIX. That
    # decodes uniquely ONLY while every original number is < STRIDE; a sheet
    # with STRIDE+ same-prefix parts (or an authored number >= STRIDE) would
    # silently collide into the NEXT sheet's band — for a REAL part that
    # merges two distinct parts in the board netlist (a LAW-0 short behind a
    # passing gate). Guard loudly (F4).
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
    """Deep-copy ``design`` with board-unique references (sheet ``index`` is
    1-based: U1 -> U1001 on sheet 1, U2001 on sheet 2, ... at the default
    _UNIQ_STRIDE of 1000). The circuit's parts / net pins / NC pins are
    renamed in lock-step with the placed geometry — the netlist stays
    graph-identical, only labels change."""
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
        # #PWR01 -> #PWR101 ...; power-symbol refs share the same band guard
        pw.ref = _renamed_ref(pw.ref, index, sheet=c.name)
    d.standalone = False
    return d


def _port_nets(c: Circuit) -> list[str]:
    return [n.name for n in c.nets.values() if n.net_class == NetClass.PORT]


def strip_duplicate_flags(designs: list[PlacedDesign], lib: Library) -> None:
    """Board-wide PWR_FLAG policy — the flag exists ONLY for undriven rails.

    Standalone sheets each carry their own PWR_FLAG corner (rail power symbol
    + 2.54 stub + flag) because, alone, no real driver is in sight. In the
    hierarchy two rules apply, both net-aware:

    1. A rail driven by a REAL power_out pin anywhere board-wide keeps NO
       flag at all: the flag (itself a power_out pin) conflicts with the
       real driver exactly like a second flag would (ERC pin_to_pin error —
       the microsd +1V8 flag vs the power sheet's LDO VOUT).
    2. Every other globally-merged net keeps exactly ONE flag board-wide
       (two flags on one global net are two power_out pins in conflict).

    Net identity is scoped the way KiCad merges nets in the hierarchy:
    POWER/GROUND rails and PORT nets merge by NAME board-wide; a
    SIGNAL-class net is sheet-local, so its flag is never deduplicated
    against another sheet's same-named net.

    Removals take the WHOLE isolated cluster — flag, stub wire and the
    corner's power symbol — and ONLY after proving (net-aware, LAW 0) that
    nothing else touches either stub endpoint: exactly one wire at the flag,
    a same-net power symbol at its far end, no junction/label/part-pin on
    either point. If any check fails the flag stays (ERC noise over netlist
    risk)."""
    # rails/ports driven by a real power_out part pin, anywhere board-wide
    driven: set[str] = set()
    for d in designs:
        etype_of = {}
        for p in d.parts:
            for pin in lib.get(p.lib_id).pins:
                etype_of[(p.ref, pin.number)] = pin.etype
        for net in d.circuit.nets.values():
            if net.net_class == NetClass.SIGNAL:
                continue       # sheet-local: cannot drive another sheet's net
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
                pass                      # rule 1: real driver — remove flag
            elif scope not in flagged:
                flagged.add(scope)        # rule 2: first flag on the net stays
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
    """Emit the hierarchy into ``outdir`` and run the board netlist gate.
    ``sheets``: list of schgen.link.SheetCircuit. ``placements`` optionally
    maps sheet name -> (placement, routed) computed by the caller (one
    place/route per sheet board-wide). Sub-sheets go to
    ``outdir/sheet_subdir/<name>.kicad_sch``; the root project is
    ``outdir/<root_name>.kicad_sch`` + ``.kicad_pro``. Returns the gate
    verdict."""
    outdir.mkdir(parents=True, exist_ok=True)
    sheet_dir = outdir / sheet_subdir if sheet_subdir else outdir
    sheet_dir.mkdir(parents=True, exist_ok=True)
    # Content-derived hierarchy uuids (emit.stable_uuid): regenerating the
    # board yields byte-identical files; per-name seeds keep every sheet
    # uuid and sheet-symbol uuid (instance-path components) unique.
    board_uuid = stable_uuid(root_name, "root")

    placed: list[tuple[str, PlacedDesign, str]] = []   # (name, design, sym_uuid)
    for i, sc in enumerate(sheets, start=1):
        # Board-unique refdes band index. Default = the 1-based enumerate
        # position (legacy / selftest). A project may pass a STABLE name->index
        # registry (sheet_index) so a part's refdes is a permanent identity that
        # does NOT re-stride when an alphabetically-earlier sheet is added or
        # removed (carrier/sheet_index.json — frozen + append-only).
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

    # one PWR_FLAG per rail board-wide (duplicates are two power_out pins)
    strip_duplicate_flags([d for _, d, _ in placed], lib)

    # Per-sheet netlist gate on the UNIQUIFIED circuit (F5): the standalone
    # build proves each sheet's ORIGINAL refs, but the board re-emits every
    # sheet through a DIFFERENT path — uniquify renaming every ref + the
    # hier-mode label layer. A defect there (a SIGNAL net mis-renamed, a pin
    # lost in uniquify) would otherwise be caught only by the board MERGE
    # gate, which checks PORT/rail pins but NOT sheet-local SIGNAL topology.
    #
    # The proof must re-emit the uniquified design in STANDALONE mode: a
    # hierarchy-mode sheet's symbol-instance path is /<board>/<sym>, which
    # only resolves WITH the board root present, so kicad-cli on the hier
    # FILE ALONE drops every pad-derived internal net (the DESIGN.md M3 trap)
    # — a false OPEN on every wired SIGNAL. A standalone re-emit (own root
    # uuid as the instance path, PORT labels as same-named global labels)
    # resolves those nets and proves the uniquified netlist is graph-identical
    # pin-for-pin. This adds a gate, never relaxes one.
    # Each sheet's work is independent: the real-sheet emit writes a distinct
    # carrier/schematic/<name>.kicad_sch (path-keyed, order-free → byte-
    # identical regardless of dispatch order), and the uniqcheck flow emits a
    # distinct <name>.uniqcheck.kicad_sch, runs the kicad-cli netlist gate (its
    # own per-call TemporaryDirectory — no shared state), then unlinks it. The
    # kicad-cli netlist export dominates this loop and is an I/O-bound
    # subprocess wait, so run the per-sheet work on a thread pool; collect the
    # per-name verdicts and aggregate per_sheet_fail in the original `placed`
    # order so the printed report (and the build outcome) is deterministic.
    def _emit_and_check(item: tuple) -> tuple[str, str | None]:
        name, d, sym_uuid = item
        emit(d, sheet_dir / f"{name}.kicad_sch", lib,
             instance_path=f"/{board_uuid}/{sym_uuid}",
             project=root_name,
             sheet_uuid=stable_uuid(root_name, "sheet", name))
        verify = copy.deepcopy(d)
        verify.standalone = True          # resolve pad-derived internal nets
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
        # ex.map preserves submission order, so iterating it walks `placed` in
        # order — per_sheet_fail stays deterministic, and any worker exception
        # (e.g. a kicad-cli netlist export failure) is re-raised at the same
        # point the serial loop would have propagated it.
        with ThreadPoolExecutor(max_workers=(os.cpu_count() or 8)) as ex:
            for _name, fail in ex.map(_emit_and_check, placed):
                if fail is not None:
                    per_sheet_fail.append(fail)
    if per_sheet_fail:
        print("BOARD: per-sheet netlist gate FAIL on uniquified circuit:")
        for f in per_sheet_fail:
            print(f"  {f}")

    # ---- root sheet -----------------------------------------------------------
    root = PlacedDesign(circuit=Circuit(root_name, "carrier board root"))
    entries = []
    for page, (name, d, sym_uuid) in enumerate(placed, start=2):
        ports = sorted(_port_nets(d.circuit))
        # the sheet pin SHAPE must mirror the sub-sheet's hierarchical-label
        # shape (input/output/bidirectional): a mismatched pin breaks root
        # connectivity in ERC even though the netlist still resolves.
        shapes = {h.name: h.shape for h in d.hlabels}
        h = PIN_PITCH * (len(ports) + 1)
        w = place.gceil(max((tm.text_wh(p)[0] for p in ports), default=10)
                        + 12.7)
        entries.append((name, sym_uuid, ports, shapes, w, h, page))

    # page-fit: wrap the sheet symbols into columns and grow the paper size
    # until everything sits inside the frame, clear of the title block. A
    # single sheet taller than the usable height forces the next size up.
    PAPERS = (("A3", 420.0, 297.0), ("A2", 594.0, 420.0), ("A1", 841.0, 594.0))
    TITLE_CLEAR = 25.4       # band reserved at the page bottom
    MARGIN = 10.16
    paper, col_geo = PAPERS[-1][0], []
    for paper, page_w, page_h in PAPERS:  # noqa: B007  paper escapes loop below
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
        # each column reserves room on its left for the port label stubs
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
                # GLOBAL label at the root (the root design is standalone, so
                # hlabels emit as global_label): merges same-named ports
                # across sheet stubs AND sidesteps a kicad-cli ERC quirk
                # where a root LOCAL label on a multi-pin sub-sheet net
                # reports label_dangling despite correct geometry + netlist
                # (minimal repro verified).
                root.hlabels.append(HierLabel(port, x_col - STUB, py,
                                              rotation=180))
            root.sheets.append(sym)
            y += h + SHEET_GAP
    root_path = outdir / f"{root_name}.kicad_sch"
    emit(root, root_path, lib, sheet_uuid=board_uuid, project=root_name)
    # board ERC policy == the per-sheet fragment policy (schgen/__main__.py):
    # pin_not_driven at WARNING — author-deferred ports' drivers arrive with
    # later-wave subsystems; the per-sheet build already enforces the
    # STRICTER schgen-side _check_inputs_driven.
    (outdir / f"{root_name}.kicad_pro").write_text(json.dumps({
        "meta": {"filename": f"{root_name}.kicad_pro", "version": 3},
        "erc": {"rule_severities": {"pin_not_driven": "warning"}},
    }, indent=2) + "\n")
    print(f"board: emitted {root_path} (+{len(placed)} sub-sheets, "
          f"root labels bind ports by canonical name)")

    ok = _board_gate(placed, root_path, reports_dir or outdir, lib)
    return ok and not per_sheet_fail


def _board_gate(placed, root_path: Path, outdir: Path, lib: Library) -> bool:
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
    port_has_input: set[str] = set()       # PORT net carrying an input-etype pin
    port_deferred: set[str] = set()        # PORT net the author expect=-deferred
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
                    except Exception:        # noqa: BLE001 — unresolved: skip
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

    # DEF-I: undriven-input PORT detector (LAW-0 silent OPEN). A PORT carrying
    # an input-etype pin that merges to only ONE sheet — no cross-sheet driver —
    # and is NOT expect=-deferred is a stranded input. The linker's name
    # resolution catches a port that resolves NOWHERE, but not one that resolves
    # to a peer-less single sheet; expect= ports are author-deferred (a later
    # wave drives them).
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

    # informational ERC (NOT the gate — the gate is the netlist merge)
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
