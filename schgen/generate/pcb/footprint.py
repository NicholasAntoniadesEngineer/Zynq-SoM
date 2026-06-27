"""Footprint resolution / parsing + the merged board netlist + net classes.
PURE MOVE out of the old monolithic ``schgen/generate/pcb.py`` — no behaviour
change. Depends only on ``constants``.
"""

from __future__ import annotations

from pathlib import Path

from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.generate import constraints as cst

from .constants import (
    _FOOTPRINT_ALIASES,
    _PAD_RE,
    _THRU_PAD_RE,
    CARRIER,
    GRID,
    PARTS_DIR,
    POWER_CLASS,
    _kicad_fp_root,
)


def resolve_mod(footprint: str) -> Path | None:
    """lib:name -> the .kicad_mod path (parts/ first, then KiCad std libs)."""
    fp = _FOOTPRINT_ALIASES.get(footprint, footprint)
    lib, _, name = fp.partition(":")
    local = PARTS_DIR / lib / f"{name}.kicad_mod"
    if local.exists():
        return local
    root = _kicad_fp_root()
    if root is not None:
        std = root / f"{lib}.pretty" / f"{name}.kicad_mod"
        if std.exists():
            return std
    return None


def pad_names(mod_path: Path) -> list[str]:
    """Ordered list of pad NAMES (KiCad pad number strings) in the footprint.
    A name repeats for multi-pad nets (e.g. two GND pads named 'GND')."""
    return _PAD_RE.findall(mod_path.read_text())


_thru_cache: dict[str, bool] = {}


def has_thru_pads(mod_path: Path) -> bool:
    """True if the footprint has any thru_hole/np_thru_hole pad (copper on all
    layers). Cached by path."""
    key = str(mod_path)
    if key not in _thru_cache:
        _thru_cache[key] = bool(_THRU_PAD_RE.search(mod_path.read_text()))
    return _thru_cache[key]


# ---- the merged board netlist ---------------------------------------------------

def board_netlist() -> dict[str, list]:
    """net name -> [PinRef,...], the KiCad-extracted merged board netlist.

    Extracted from the already-emitted root schematic with the SAME extractor
    the electrical gate uses, so the PCB connectivity == the schematic's. Refs
    are the board-unique ones (U1 -> U1001 ...). Requires ``schgen board`` (or
    the board flow) to have written carrier/Zynq_Carrier.kicad_sch first."""
    from schgen.verify.netlist_gate import extract_netlist
    root = CARRIER / "Zynq_Carrier.kicad_sch"
    if not root.exists():
        raise FileNotFoundError(
            f"{root} not found — run `schgen board` first (the PCB seeds its "
            f"net-accurate connectivity from the emitted root schematic).")
    return extract_netlist(root)


def board_parts() -> dict[str, tuple[str, str, str, str]]:
    """board-unique ref -> (sheet, footprint, value, lib_id).

    Rebuilt from the subsystem models through the SAME uniquify renaming the
    board flow applies (schgen/generate/board._renamed_ref), so the ref keys
    match the merged netlist's refs exactly.

    CRITICAL — must use the SAME band index ``build_board`` used to emit the root
    schematic: the STABLE, frozen registry ``carrier/sheet_index.json`` (band =
    ``sheet_index[name]``), NOT the 1-based enumerate position. The two coincide
    only while every sheet's alphabetical order equals its band; the instant a
    sheet is inserted alphabetically before others (e.g. ``mechanical`` lands
    between ``lcd`` and ``microsd`` but its band is appended at 34), the enumerate
    position of every later sheet shifts by one while its registry band stays put.
    Keying ``board_parts`` off the enumerate position then yields refs (U18001…)
    that DISAGREE with the schematic-derived ``board_netlist`` refs (U17001…), so
    ``build_model``'s pad<->net join silently misses — every pad of the affected
    parts lands no-net. For a plain pad that is only an extra unrouted item, but
    for a thermal-pad part the EP itself goes no-net, so its blank thermal vias
    (which inherit the EP's net) can no longer inherit a net and clash with the
    no-net EP copper -> intra-footprint clearance DRC errors. Reading the same
    registry keeps every ref permanent and the pad-net join exact."""
    import json as _json

    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.generate.board import _renamed_ref
    _idx_path = CARRIER / "sheet_index.json"
    sheet_index = (_json.loads(_idx_path.read_text())
                   if _idx_path.exists() else {})
    out: dict[str, tuple[str, str, str, str]] = {}
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    for i, sc in enumerate(sheets, start=1):
        idx = sheet_index.get(sc.name, i)     # stable band (matches build_board)
        for ref, part in sc.circuit.parts.items():
            bref = _renamed_ref(ref, idx, sheet=sc.name)
            out[bref] = (sc.name, part.footprint, part.value, part.lib_id)
    return out


def _net_classes(sheets) -> tuple[dict[str, cst.DiffGeometry | None],
                                  dict[str, str]]:
    """(class name -> geometry, net name -> class).

    Diff-pair classes from the typed ports (constraints.py); POWER class for
    every POWER-class rail. The net->class map keys on the canonical net name
    used board-wide (POWER/GROUND/PORT merge by name), so KiCad's
    netclass_patterns hit the merged nets."""
    from schgen.core.model import NetClass
    classes: dict[str, cst.DiffGeometry | None] = {}
    netclass_of: dict[str, str] = {}
    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class == NetClass.PORT:
                pt = c.port_type_of(net.name)
                if pt.kind == "single":
                    continue
                ncls = cst._net_class(pt.kind, pt.impedance, pt.level_v)
                geo = cst.GEOMETRY.get(pt.impedance) if pt.impedance else None
                classes.setdefault(ncls, geo)
                netclass_of[net.name] = ncls
            elif net.net_class == NetClass.POWER:
                classes.setdefault(POWER_CLASS, None)
                netclass_of[net.name] = POWER_CLASS
    return classes, netclass_of


# ---- placement -------------------------------------------------------------------

def _gridify(v: float) -> float:
    return round(round(v / GRID) * GRID, 4)


_bbox_cache: dict[str, tuple[float, float, float, float]] = {}


def _footprint_bbox(mod_path: Path) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) of the footprint relative to its origin,
    over BOTH the F.CrtYd courtyard graphics AND every pad's copper rectangle
    (pad at + half-size, with the pad's own rotation). This is the box KiCad's
    courtyards_overlap / clearance DRC reasons about, so packing with a halo
    around it yields no overlap/clearance errors.

    Cached by path — every footprint .kicad_mod is parsed at most once."""
    key = str(mod_path)
    if key in _bbox_cache:
        return _bbox_cache[key]
    doc = sexpr.loads(mod_path.read_text())
    xs: list[float] = []
    ys: list[float] = []

    def add(x: float, y: float) -> None:
        xs.append(x)
        ys.append(y)

    def walk(node: list) -> None:
        for sub in node:
            if not isinstance(sub, list) or not sub:
                continue
            head = sub[0]
            if head in (Sym("fp_line"), Sym("fp_rect"), Sym("fp_poly"),
                        Sym("fp_circle"), Sym("fp_arc")):
                lyr = sexpr.find(sub, "layer")
                if lyr and len(lyr) > 1 and "CrtYd" in str(lyr[1]):
                    # an fp_circle's (center .) + (end .) are the CENTRE and a
                    # point ON the circumference: the courtyard extends a full
                    # RADIUS on every side, not just to the (end) point. Adding
                    # only center+end (as the generic point loop below does) under-
                    # measures the bbox to one quadrant — e.g. the D1.5mm TestPoint
                    # courtyard circle (center 0,0 / end 1.25,0) read as a
                    # (-0.75..1.25) box instead of the true (-1.25..1.25), so the
                    # packer placed test points a radius too close and KiCad's real
                    # circular courtyard then overlapped. Expand by the radius.
                    if head == Sym("fp_circle"):
                        ctr = sexpr.find(sub, "center")
                        end = sexpr.find(sub, "end")
                        if (ctr and len(ctr) >= 3 and end and len(end) >= 3):
                            cxf, cyf = float(ctr[1]), float(ctr[2])
                            r = ((float(end[1]) - cxf) ** 2
                                 + (float(end[2]) - cyf) ** 2) ** 0.5
                            add(cxf - r, cyf - r)
                            add(cxf + r, cyf + r)
                    for tag in ("start", "end", "mid", "center"):
                        p = sexpr.find(sub, tag)
                        if p and len(p) >= 3:
                            add(float(p[1]), float(p[2]))
                    pts = sexpr.find(sub, "pts")
                    if pts:
                        for xy in sexpr.find_all(pts, "xy"):
                            if len(xy) >= 3:
                                add(float(xy[1]), float(xy[2]))
            elif head == Sym("pad"):
                at = sexpr.find(sub, "at")
                size = sexpr.find(sub, "size")
                if at and len(at) >= 3 and size and len(size) >= 3:
                    px, py = float(at[1]), float(at[2])
                    sw, sh = float(size[1]) / 2, float(size[2]) / 2
                    rot = int(float(at[3])) % 180 if len(at) > 3 else 0
                    if rot == 90:
                        sw, sh = sh, sw
                    add(px - sw, py - sh)
                    add(px + sw, py + sh)
            else:
                walk(sub)

    walk(doc)
    if not xs:
        bbox = (-1.0, -1.0, 1.0, 1.0)
    else:
        bbox = (round(min(xs), 3), round(min(ys), 3),
                round(max(xs), 3), round(max(ys), 3))
    _bbox_cache[key] = bbox
    return bbox
