"""Emit an openable KiCad PCB FOUNDATION (Stream D) — NOT autorouted.

``schgen pcb`` (also run by ``schgen board``) writes
``carrier/Zynq_Carrier.kicad_pcb`` + ``carrier/manufacturing/
Zynq_Carrier_pcb.kicad_dru``: a real, openable, DRC-clean (unrouted-net
violations only) PCB seeded from the SAME netlists/floorplan the schematic
flow uses. It does FOUR things, every number DERIVED:

1. **Board OUTLINE** on Edge.Cuts — a rectangle whose W x H is DERIVED by
   ``floorplan.derive_outline`` (SoM body + escape halo + a connector band on
   each edge + the total component area at a generous fill + a perimeter
   keep-out), sized for routing headroom; the 4 M3 mounting holes (already
   netted to CHASSIS_GND in the model) are forced to the board corners, and a
   SoM-body keep-out zone keeps routing/copper out from under the mezzanine.
2. **A FORCED 4-LAYER controlled-impedance stackup** (Sig / GND / PWR / Sig),
   the JLC04161H-7628 1.6 mm build the constraints already target — written
   into both the ``(layers)`` table and the ``(setup (stackup ...))`` block.
3. **NET CLASSES + a .kicad_dru** — default clearances/widths, the
   impedance-controlled classes for the high-speed nets (TMDS / USB2 / RGMII-
   class diff pairs) and a POWER class for the rails, with per-net
   ``netclass_patterns`` so KiCad assigns every high-speed/rail net to its
   class on open. Reuses ``schgen/generate/constraints.py`` geometry.
4. **FOOTPRINT PLACEMENT** — every BOM footprint embedded into the .kicad_pcb,
   its pads bound to the schematic nets (the merged board netlist KiCad itself
   extracts from the root sheet). Placement is THREE policies layered:
   (A1) the SoM DF40 mezzanine J1/J2/J3 placed at the centered, MIRRORED SoM
   positions (board-to-board mate) with each connector's SoM rotation; (A3)
   every other sheet's footprints packed INTO that sheet's floorplan block, so
   each subsystem clusters contiguously and its ratsnest is a local bundle, not
   a board-wide hairball; and (4) 2-SIDE assembly (default ON, the JLCPCB
   both-sides build) — SoM/edge connectors + large/active ICs on TOP (F.Cu),
   decoupling caps + small passives on BOTTOM (B.Cu) under their cluster, which
   roughly halves top-side area pressure. NO routing.

The merged board netlist is the authoritative source: it is extracted from the
already-emitted ``carrier/Zynq_Carrier.kicad_sch`` with the SAME
``netlist_gate.extract_netlist`` the electrical gate uses, so the PCB's
connectivity is exactly the schematic's — board-unique refs and all. The part
set is therefore identical to the schematic BOM by construction.

DETERMINISM: every uuid is content-derived (``emit.stable_uuid``), positions
are rounded, footprints are emitted in a fixed (ref) order — building twice
yields a byte-identical .kicad_pcb (no timestamps, no random ids).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.output.emit import stable_uuid
from schgen.generate import constraints as cst

REPO_ROOT = Path(__file__).resolve().parents[2]
PARTS_DIR = REPO_ROOT / "parts"
CARRIER = REPO_ROOT / "carrier"

# KiCad-installed standard footprint libraries (the non-parts/ footprints —
# Resistor_SMD, Capacitor_SMD, Package_*, Diode_SMD, LED_SMD, TestPoint,
# MountingHole). Probed at the standard macOS/Linux locations.
_KICAD_FP_DIRS = [
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"),
    Path("/usr/share/kicad/footprints"),
    Path("/usr/local/share/kicad/footprints"),
]

# A few footprint names this project authored that a given KiCad install may
# ship under a near-identical dimensional name. Same body, same pads — the
# substitution is dimensionally faithful and reported. (3225 vs 3216 is the
# 1206 metric body; some KiCad lib versions ship one, some the other.)
_FOOTPRINT_ALIASES = {
    "Capacitor_SMD:C_1206_3225Metric": "Capacitor_SMD:C_1206_3216Metric",
}


def _kicad_fp_root() -> Path | None:
    for d in _KICAD_FP_DIRS:
        if d.is_dir():
            return d
    return None


# ---- board geometry --------------------------------------------------------------
# The outline is DERIVED from the ACTUAL packed-zone extents (build_model): the
# board grows until the centered SoM region + every per-subsystem zone + the 4
# corner mounting holes + a perimeter keepout all fit, so EVERY footprint sits
# inside Edge.Cuts (LAW 5 — no off-board parts). The coordinate frame is shifted
# by ORIGIN_X/Y so the board sits in positive KiCad page space (KiCad's drawing
# sheet origin is top-left, +y down).
ORIGIN_X = 25.0          # board top-left in KiCad page mm
ORIGIN_Y = 25.0
MH_INSET = 5.0          # M3 hole center inset from each board corner
GRID = 1.27             # placement snap grid (mm)

# --- subsystem-zone outline derivation (LAW 5) -------------------------------
PERIM = 3.0              # perimeter keepout ring (no zone touches the edge)
MH_KEEPOUT = 5.0         # extra inset reserving the corner mounting-hole pads
SOM_HALO_PCB = 7.0       # routing/escape halo reserved around the SoM body
SOM_CORE_CLEARANCE = 0.03  # grow the SoM-body silk outline + keepout 3% (1.5% per
#                            side) past the bare DF40 span for mating clearance
EDGE_BAND_PCB = 10.0     # nominal connector band each side (board-aspect seed)
ZONE_FILL = 0.58         # zone-area packing efficiency for the seed board size
ZONE_STEP = 2.54         # zone-placement raster scan step (mm)
OUTLINE_GROW = 5.0       # board grow increment per fit attempt (mm)
OUTLINE_SNAP_PCB = 5.0   # round the final W/H UP to this grid (mm)


def _snap_up(v: float) -> float:
    n = int((v + OUTLINE_SNAP_PCB - 1e-6) / OUTLINE_SNAP_PCB)
    return round(n * OUTLINE_SNAP_PCB, 1)


@dataclass
class FootprintInst:
    ref: str
    value: str
    footprint: str        # lib:name
    x: float              # KiCad page mm (center)
    y: float
    rotation: float
    pad_nets: dict[str, tuple[int, str]]   # pad name -> (net number, net name)
    mod_path: Path
    sheet: str
    side: str = "top"     # "top" (F.Cu) | "bottom" (B.Cu) — 2-side assembly


@dataclass
class PcbModel:
    board_w: float
    board_h: float
    insts: list[FootprintInst]
    net_numbers: dict[str, int]            # net name -> number (0 = no-net)
    netclass_of: dict[str, str]            # net name -> net class
    classes: dict[str, cst.DiffGeometry | None]
    placed: int
    deferred: list[str]
    som_keepout: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1
    n_top: int = 0
    n_bottom: int = 0
    two_side: bool = True
    # SoM module-body CORE rectangle in the board page frame (NO halo) — the
    # footprint of the plugged-in SoM. Under it ONLY low-profile passives may
    # sit (LAW 6); the placement_mech gate enforces it.
    som_core: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1


# ---- footprint resolution + parsing ----------------------------------------------

_PAD_RE = re.compile(r'\(pad\s+"([^"]+)"')
# a pad that occupies EVERY copper layer (through-hole / NPTH) — its copper is
# on both F.Cu and B.Cu, so a bottom-side SMD part placed at the same XY would
# short to it. The 2-side packer reserves such top-side footprints on the
# bottom too.
_THRU_PAD_RE = re.compile(r'\(pad\s+"[^"]*"\s+(?:thru_hole|np_thru_hole)\b')


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


# ---- net classes -----------------------------------------------------------------
# Reuse the constraints exporter's class names + geometry: the high-speed diff
# classes (DP90_USB / DP100_TMDS / DP<imp>_DIFF) plus a POWER class for rails.

POWER_CLASS = "POWER"
POWER_TRACK_MM = 0.4            # rail trace minimum (sensible default; user widens)
POWER_CLEARANCE_MM = 0.2
DEFAULT_TRACK_MM = 0.2032       # 8 mil — JLCPCB default minimum trace width
# Board-wide copper clearance: 0.15 mm (6 mil) — a standard JLCPCB process
# minimum. The 8-mil figure is the trace WIDTH target, not the pad-to-pad
# clearance; several faithful fine-pitch QFN/SOT footprints in the BOM have an
# intrinsic pad-to-EP gap of ~0.198 mm, so an 8-mil clearance rule would flag
# the footprints' OWN geometry (350+ intra-footprint false positives) before a
# single track is routed. 6 mil clears those and stays manufacturable.
DEFAULT_CLEARANCE_MM = 0.15


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


# Mandatory clearance between any two footprint courtyards AND between a
# footprint and the board edge — so the emitted PCB has NO courtyard-overlap /
# pad-clearance / copper-edge DRC errors (only the expected unrouted-net items).
PLACE_CLEAR = 0.5
EDGE_CLEAR = 2.0
ZONE_GAP = 0.8             # gap between two adjacent subsystem zones
ZONE_PAD = 0.3            # padding inside a subsystem zone around its parts
# N/S EDGE-connector subsystems pack WIDE + SHALLOW (their shelf target width is
# multiplied by this) so the zone spreads ALONG the horizontal top/bottom edge
# instead of eating deep into the interior behind the connector (a deep edge
# block forces the board to grow). ~halves the depth of the deepest connector
# blocks (microSD 30->20, pd_input 33->17, hdmi 29->20). W/E edges are left
# squarish (a wide pack there would be DEEP into the board) — the floorplan
# spreads them down the vertical edge as-is.
EDGE_ZONE_ASPECT = 2.2

# ---- LAW 6: off-board connector ORIENTATION ---------------------------------------
# Every connector that mates with an external cable/plug/card MUST sit on a board
# EDGE with its mating face (the slot/mouth/cable-exit) pointing OFF-BOARD, so the
# mate physically inserts. The placer ROTATES each such connector to its assigned
# edge — never axis-aligned — and seats it flush at the edge; the rest of its
# subsystem packs behind it, inward. DRC=0 + the ratsnest gate are blind to this
# (an interior or inward-facing connector is not a DRC/airwire error), so this is
# encoded here AND enforced by the placement_mech gate.
#
# MATING_FACE: the direction the connector's mouth points in its footprint LOCAL
# frame at rotation 0 (researched from the parts/<MPN>/<MPN>.kicad_mod pad/post
# asymmetry + datasheet). KiCad's page frame is +y DOWN, so -Y is toward the
# board top (N edge) and +Y toward the bottom (S edge).
CONN_MATING_FACE: dict[str, str] = {
    "TYPE-C-31-M-12":  "-Y",   # USB-C receptacle mouth
    "HDMI-019S":       "+Y",   # HDMI receptacle mouth (plug enters OPPOSITE the
                               # SMT contact row at -Y; verified from footprint
                               # geometry — was -Y, faced inward in the render)
    "AFC07-S40FCA-00": "-Y",   # LCD FPC slot
    "KH-5224-8P8C-D":  "-Y",   # RJ45 jack mouth (plug enters at the pin-1..8
                               # CONTACT end at -Y; shield tails/posts at +Y are
                               # the board-attach back — was +Y, faced inward)
    "TF-01A":          "+Y",   # microSD card slot
    "SFW15R-1STE1LF":  "-Y",   # camera FFC slot opens away from the solder tabs
                               # (posts at +Y -> cable entry at -Y), same as the
                               # geometrically-identical AFC07 LCD FPC
    "ZX-SH1.0-4PWT":   "+Y",   # QWIIC shrouded header
    "DS1024-2x6R2":    "+Y",   # PMOD 2x6 socket
}
# EDGE -> placement rotation (deg, KiCad CCW) that turns the mating face OFF-BOARD.
# Derived in the CODE's actual page frame (+y DOWN: N/top edge = MIN y, off-board
# from N is toward -Y; S/bottom = MAX y, off-board +Y; E/right off-board +X;
# W/left off-board -X) using the SAME rotation matrix _inst_pad_geom applies:
# (x,y) -> (x cos r - y sin r, x sin r + y cos r). NOTE this differs from the
# research spec's table by swapping N<->S: the research derived in a +y-UP frame
# (it called +Y "North/away"), but this codebase places on a +y-DOWN page, so the
# off-board direction of the top/bottom edges is the opposite sign. The
# _mating_face_out_dir oracle (and the placement_mech gate that uses it) is the
# ground truth that proves each mouth points off-board after rotation.
_ROT_FACE_NEG_Y = {"N": 0.0, "S": 180.0, "E": 90.0, "W": 270.0}
_ROT_FACE_POS_Y = {"N": 180.0, "S": 0.0, "E": 270.0, "W": 90.0}


def connector_edge_rotation(mating_face: str, edge: str) -> float:
    """Placement rotation (deg) so a connector whose 0-deg mouth points
    ``mating_face`` (-Y/+Y) faces OFF-BOARD when placed on ``edge`` (N/E/S/W)."""
    table = _ROT_FACE_NEG_Y if mating_face == "-Y" else _ROT_FACE_POS_Y
    return table.get(edge, 0.0)


def _mating_face_out_dir(mating_face: str, rot: float) -> tuple[int, int]:
    """The board-frame unit vector the mating mouth points after a placement
    rotation ``rot`` (deg, KiCad CCW about origin, page +y DOWN). Used by the
    gate to confirm the mouth faces off-board, and by the placer to seat the
    connector flush. Returns one of (0,-1)=N, (0,1)=S, (1,0)=E, (-1,0)=W."""
    fx, fy = (0, -1) if mating_face == "-Y" else (0, 1)
    r = int(round(rot)) % 360
    # KiCad rotates a point (x,y) CCW on a +y-DOWN screen as the matrix
    # (x*cos - y*sin, x*sin + y*cos) with the screen-CCW convention used in
    # _inst_pad_geom; for 90-deg steps this maps (0,-1)->(rot) deterministically.
    import math as _m
    a = _m.radians(r)
    cs, sn = round(_m.cos(a)), round(_m.sin(a))
    return (fx * cs - fy * sn, fx * sn + fy * cs)


def _rot_bbox(bbox: tuple[float, float, float, float],
              rot: float) -> tuple[float, float, float, float]:
    """The footprint's local bbox after a 0/90/180/270 placement rotation —
    the box KiCad's courtyard occupies once the footprint is turned. KiCad
    rotates COUNTER-clockwise about the origin; for an axis-aligned box the
    90/270 cases swap width/height."""
    bx0, by0, bx1, by1 = bbox
    r = int(round(rot)) % 360
    if r == 90:
        return (-by1, bx0, -by0, bx1)
    if r == 180:
        return (-bx1, -by1, -bx0, -by0)
    if r == 270:
        return (by0, -bx1, by1, -bx0)
    return bbox


def _rot_pad_bbox(mod_path: Path, rotation: float,
                  side: str = "top") -> tuple[float, float, float, float] | None:
    """The COPPER (pad) bounding box of a footprint after its placement rotation
    + (for a bottom part) the F->B X-mirror, in the footprint-local frame —
    includes each pad's real size (and the 90/270 size swap of a rotated pad).
    Used to seat an off-board connector so its OUTERMOST pad sits exactly at the
    board-edge copper clearance (the mouth/shell then reaches/overhangs the edge,
    as a real hand-laid connector does). Returns None for a pad-less footprint."""
    doc = sexpr.loads(mod_path.read_text())
    R = math.radians(rotation or 0.0)
    cs, sn = math.cos(R), math.sin(R)
    xs: list[float] = []
    ys: list[float] = []
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        at = sexpr.find(node, "at")
        sz = sexpr.find(node, "size")
        if not (at and len(at) >= 3):
            continue
        px, py = float(at[1]), float(at[2])
        prot = math.radians(float(at[3])
                            if len(at) > 3 and isinstance(at[3], (int, float))
                            else 0.0)
        sw, sh = (float(sz[1]), float(sz[2])) if sz and len(sz) >= 3 else (0.0, 0.0)
        if side == "bottom":
            px = -px                            # F->B mirror about origin X
            prot = -prot
        # pad CENTER under KiCad's CLOCKWISE footprint rotation (y-axis points
        # down): cx = px·cos + py·sin, cy = -px·sin + py·cos. This matches where
        # KiCad/DRC actually place an asymmetric pad (a CCW transform mirrors the
        # off-axis pads ~1.2mm — the bug that seated the FPC mechanical pads on
        # the edge). The outer courtyard bbox is ~symmetric so it was unaffected.
        cx = px * cs + py * sn
        cy = -px * sn + py * cs
        # axis-aligned half-extent of the (sw x sh) pad rotated by the footprint
        # rotation + the pad's own rotation — robust for any angle (not just 90s).
        tot = R + prot
        ct, st = abs(math.cos(tot)), abs(math.sin(tot))
        hx = ct * sw / 2 + st * sh / 2
        hy = st * sw / 2 + ct * sh / 2
        xs += [cx - hx, cx + hx]
        ys += [cy - hy, cy + hy]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


# off-board connector seating: the outermost PAD sits this far (mm) from the
# board edge — just clears the 0.3 mm copper_edge_clearance with grid-snap margin;
# the connector's mouth/shell (ahead of the pads) then reaches/overhangs the edge
# so a cable actually mates (LAW 6 — user: "connectors at the absolute edge").
EDGE_PAD_CLEAR = 0.4


def _shelf_pack(items: list[tuple[str, tuple, float]], target_w: float,
                blockers: list[tuple[float, float, float, float]] | None = None
                ) -> tuple[dict[str, tuple[float, float]], float, float]:
    """Deterministic shelf packer for ONE subsystem's footprints.

    ``items`` is [(ref, bbox, rotation), ...]; ``target_w`` is the width to
    fill before wrapping to a new shelf row. ``blockers`` are zone-relative
    rectangles (x0,y0,x1,y1) the placed boxes must AVOID — used to keep a
    bottom-side SMD out from under a top-side through-hole pad (whose copper is
    on every layer): a bottom part there would short to the THT pad. Returns
    ``(origin_of_ref, packed_w, packed_h)`` where ``origin_of_ref[ref]`` is the
    (x, y) to put at the footprint ORIGIN so its haloed rotated bbox sits inside
    the [0, packed_w] x [0, packed_h] zone with a ZONE_PAD margin. Parts are
    laid LARGEST-first (by haloed height, then width, then ref) so tall parts
    anchor each row. There is NO overflow path: the returned box is exactly
    large enough to hold every part, so the caller sizes the zone to fit and
    never spills a part off-board."""
    blk = list(blockers or [])
    placed: dict[str, tuple[float, float]] = {}
    occ: list[tuple[float, float, float, float]] = list(blk)
    # haloed rotated bbox per ref
    halo: dict[str, tuple[float, float, float, float]] = {}
    for ref, bbox, rot in items:
        rb = _rot_bbox(bbox, rot)
        halo[ref] = (rb[0] - PLACE_CLEAR / 2, rb[1] - PLACE_CLEAR / 2,
                     rb[2] + PLACE_CLEAR / 2, rb[3] + PLACE_CLEAR / 2)
    order = sorted(items, key=lambda it: (
        -(halo[it[0]][3] - halo[it[0]][1]),
        -(halo[it[0]][2] - halo[it[0]][0]), it[0]))

    def _free(x0, y0, x1, y1, w_lim) -> bool:
        if x1 > ZONE_PAD + w_lim + 1e-6:
            return False
        for rx0, ry0, rx1, ry1 in occ:
            if not (x1 <= rx0 or rx1 <= x0 or y1 <= ry0 or ry1 <= y0):
                return False
        return True

    used_w = ZONE_PAD
    used_h = ZONE_PAD
    cy = ZONE_PAD
    row_h = 0.0
    for ref, _bbox, _rot in order:
        hx0, hy0, hx1, hy1 = halo[ref]
        hw, hh = hx1 - hx0, hy1 - hy0
        w_lim = max(target_w, hw)
        # raster scan within the growing shelf area; blockers force a slide.
        cx = ZONE_PAD
        slot = None
        guard = 0
        scan_cy = cy
        scan_row_h = row_h
        while slot is None and guard < 100000:
            guard += 1
            if cx + hw > ZONE_PAD + w_lim + 1e-6:
                cx = ZONE_PAD
                scan_cy += scan_row_h if scan_row_h else hh
                scan_row_h = 0.0
                continue
            if _free(cx, scan_cy, cx + hw, scan_cy + hh, w_lim):
                slot = (cx, scan_cy)
                break
            cx += GRID
        sx, sy = slot
        occ.append((sx, sy, sx + hw, sy + hh))
        placed[ref] = (round(sx - hx0, 4), round(sy - hy0, 4))
        used_w = max(used_w, sx + hw)
        used_h = max(used_h, sy + hh)
        # advance the primary shelf cursor in row order
        if sy == cy:
            row_h = max(row_h, hh)
        else:
            cy, row_h = sy, hh
    packed_w = round(max(used_w, ZONE_PAD) + ZONE_PAD, 4)
    packed_h = round(max(used_h, ZONE_PAD) + ZONE_PAD, 4)
    return placed, packed_w, packed_h


# inter-button air gap (mm) inside the tactile-button grid — wider than the
# generic PLACE_CLEAR so the buttons read as a spaced, finger-friendly array.
BUTTON_GAP = 2.0


def _is_button(mod_path: Path) -> bool:
    """A user-facing tactile PUSHBUTTON (the round 6 mm TS-1187A). DIP/SLIDE
    config switches (DSHP*) are NOT included — they are set-once configuration,
    not pressable controls, and pack with the passives. LAW 6: pressable controls
    read as an organised array, never scattered among the passives."""
    return "TS-1187A" in mod_path.stem


def _grid_controls(refs: list[str], bbox_of: dict, resolvable: dict,
                   target_w: float
                   ) -> tuple[dict[str, tuple[float, float]],
                              list[tuple[float, float, float, float]],
                              float, float]:
    """Lay tactile buttons in a CLEAN uniform grid in a reserved band at the top
    of the zone (LAW 6 — controls organised, not ugly). All buttons share one
    square cell = the largest button halo, so identical buttons align perfectly.
    Returns (origin_of_ref, occupied_cells, band_w, band_h); the occupied cells
    are handed to the rest-of-zone shelf pack as blockers so no passive intrudes
    into the button array."""
    cell = 0.0
    bb: dict[str, tuple[float, float, float, float]] = {}
    for r in refs:
        bx0, by0, bx1, by1 = bbox_of[r]
        bb[r] = (bx0, by0, bx1, by1)
        # BUTTON_GAP (not just PLACE_CLEAR) gives a finger-friendly air gap
        # between adjacent buttons so the array reads cleanly + presses easily
        # (user: "switches need slightly more spacing between them").
        cell = max(cell, (bx1 - bx0) + BUTTON_GAP, (by1 - by0) + BUTTON_GAP)
    cols = max(1, min(len(refs), int((target_w) // cell) or 1))
    off: dict[str, tuple[float, float]] = {}
    occ: list[tuple[float, float, float, float]] = []
    order = sorted(refs)
    for i, r in enumerate(order):
        cx, cy = i % cols, i // cols
        x0 = ZONE_PAD + cx * cell
        y0 = ZONE_PAD + cy * cell
        bx0, by0, bx1, by1 = bb[r]
        # seat the footprint's halo box centred in its square cell
        fw, fh = (bx1 - bx0) + PLACE_CLEAR, (by1 - by0) + PLACE_CLEAR
        ox = x0 + (cell - fw) / 2 - bx0 + PLACE_CLEAR / 2
        oy = y0 + (cell - fh) / 2 - by0 + PLACE_CLEAR / 2
        off[r] = (round(ox, 4), round(oy, 4))
        occ.append((x0, y0, x0 + cell, y0 + cell))
    rows = (len(refs) + cols - 1) // cols
    return off, occ, ZONE_PAD + cols * cell, ZONE_PAD + rows * cell


# ---- 2-side assembly: layer-assignment policy ------------------------------------
# JLCPCB assembles BOTH sides. The policy keeps the mechanically-/cable-/heat-
# critical parts on TOP and pushes the small decoupling/bypass passives to the
# BOTTOM (placed directly under their cluster), which roughly halves the
# top-side area pressure. Default ON; a forced single-side build keeps all on
# top (every classification then returns "top").

# Footprint families that MUST stay on the top (component) side regardless of
# size: the SoM mezzanine, every off-board edge connector, the mounting holes,
# test points (probe from the top), and through-hole headers.
_TOP_ALWAYS_LIBS = (
    "DF40C", "MountingHole", "Mechanical:", "TestPoint",
    "PinHeader", "PinSocket", "Connector", "Conn_",
)
# Active/large IC area floor (mm^2 of the footprint bbox): a part this big or
# bigger is an IC/connector/magnetic and stays on top.
TOP_AREA_MM2 = 12.0


def _is_passive_ref(ref: str) -> bool:
    """A discrete passive whose reference designator starts R/C/L (the parts a
    2-side build may relocate to the bottom). FB (ferrite), D (diode) stay on
    top — they are often in the signal path or LED-visible."""
    return ref[:1] in ("R", "C", "L") and not ref.startswith(("RJ", "LED"))


def _decoupling_caps(nets: dict[str, list]) -> set[str]:
    """Refs of decoupling/bypass caps: a 2-pin cap across GROUND and exactly
    one other (rail) net. These are the bottom-side candidates placed directly
    under their IC's supply pins — derived from the netlist, never guessed."""
    cap_nets: dict[str, set[str]] = {}
    for name, pins in nets.items():
        if name.startswith("unconnected-"):
            continue
        for pr in pins:
            if pr.ref.startswith("C") and not pr.ref.startswith("#"):
                cap_nets.setdefault(pr.ref, set()).add(name)
    out: set[str] = set()
    for ref, ns in cap_nets.items():
        has_gnd = "GND" in ns
        rails = {n for n in ns if n != "GND"}
        if has_gnd and len(rails) == 1 and len(ns) == 2:
            out.add(ref)
    return out


def _classify_side(ref: str, lib: str, bbox: tuple,
                   decoupling: set[str], two_side: bool) -> str:
    """top|bottom for a footprint. Single-side -> always top. The SoM,
    connectors, mounting holes, test points and large/active ICs are top;
    decoupling caps and other small passives go to the bottom."""
    if not two_side:
        return "top"
    if any(tok in lib for tok in _TOP_ALWAYS_LIBS):
        return "top"
    bx0, by0, bx1, by1 = bbox
    area = (bx1 - bx0) * (by1 - by0)
    if area >= TOP_AREA_MM2:
        return "top"               # an IC / large part: top
    if ref in decoupling:
        return "bottom"            # bypass cap under its IC's supply pins
    if _is_passive_ref(ref):
        return "bottom"            # other small passive: relieve top pressure
    return "top"


# ---- SHARED subsystem zone packing (ONE source of truth) -------------------------
# Both the floorplan (block SIZING) and the PCB (block PLACEMENT) must agree on how
# big each subsystem's 2-sided packed cluster is, or the FLOORPLAN.svg and the PCB
# ratsnest diverge (the historical 235x215-vs-165x155 split). This function is the
# single sizing oracle: it shelf-packs every subsystem's TOP + BOTTOM footprints
# (the exact STEP-1 geometry the PCB places with) and returns the per-sheet packed
# (w, h) + per-part offsets. It runs from the subsystem circuits + the stable
# board-unique ref namespace (carrier/sheet_index.json), so it is identical whether
# called standalone (`schgen floorplan`, no emitted root sch) or inside the board
# flow — proven: per-sheet decoupling classification == merged classification, and
# board-unique-ref packing is byte-identical to build_model's old inline packing.

@dataclass
class ZoneGeom:
    zone_box: dict[str, tuple[float, float]]                # sheet -> (w, h)
    top_off: dict[str, dict[str, tuple[float, float]]]      # sheet -> {bref:(x,y)}
    bot_off: dict[str, dict[str, tuple[float, float]]]
    side_of: dict[str, str]                                 # bref -> top|bottom
    bbox_of: dict[str, tuple[float, float, float, float]]   # bref -> local bbox
    resolvable: dict[str, Path]                             # bref -> .kicad_mod
    refs_by_sheet: dict[str, list[str]]                     # sheet -> [bref,...]
    mh_refs: list[str]                                      # mounting-hole brefs
    deferred: list[str]
    conn_rot: dict[str, float] = field(default_factory=dict)  # bref -> LAW-6 rot
    conn_edge: dict[str, str] = field(default_factory=dict)   # bref -> edge N/E/S/W


def _eff_bbox_for(bbox: tuple[float, float, float, float],
                  side: str) -> tuple[float, float, float, float]:
    """The footprint's on-board local bbox. A BOTTOM part is flipped to B.Cu,
    which mirrors its geometry about the origin's X axis (KiCad's F->B
    convention), so its courtyard occupies the X-mirror of the top bbox."""
    bx0, by0, bx1, by1 = bbox
    if side == "bottom":
        return (-bx1, by0, -bx0, by1)
    return (bx0, by0, bx1, by1)


def _pack_one_zone(sheet_refs: list[str], side_of: dict[str, str],
                   bbox_of: dict, resolvable: dict, aspect: float = 1.0,
                   conn_rot: dict[str, float] | None = None,
                   outer_dir: str | None = None
                   ) -> tuple[dict[str, tuple[float, float]],
                              dict[str, tuple[float, float]],
                              float, float]:
    """Shelf-pack ONE subsystem's footprints 2-sided (TOP + BOTTOM overlay on
    the same XY area; the zone holds the LARGER of the two). Returns
    (top_off, bot_off, packed_w, packed_h). The BOTTOM pack avoids the TOP
    through-hole pads (copper on all layers) so no bottom SMD shorts to a THT
    pad. ``aspect`` widens the shelf target (>1 => wider + SHALLOWER zone): an
    EDGE-connector subsystem packs WIDE-and-SHALLOW so its block does not eat
    deep into the board behind its edge, which keeps the interior — and the whole
    board — tight. Deterministic in the given ref order.

    LAW 6: ``conn_rot`` (bref -> placement rotation) ROTATES each off-board
    connector so its mating face points off-board; ``outer_dir`` (N/S/E/W, the
    zone-LOCAL direction the board edge lies in once this zone is placed) makes
    the connector seat FLUSH at that outer boundary with the rest of the
    subsystem packed behind it, inward. When both are given the zone uses the
    dedicated edge-aware packer; otherwise it is the plain shelf pack."""
    sr = {"top": [], "bottom": []}
    for r in sheet_refs:
        sr[side_of[r]].append(r)
    conn_rot = conn_rot or {}

    def items(refs, side):
        return [(r, _eff_bbox_for(bbox_of[r], side), conn_rot.get(r, 0.0))
                for r in refs]

    if conn_rot and outer_dir:
        return _pack_connector_zone(sr, items, bbox_of, resolvable,
                                    conn_rot, outer_dir, aspect)

    tot_area = sum((bbox_of[r][2] - bbox_of[r][0] + PLACE_CLEAR) *
                   (bbox_of[r][3] - bbox_of[r][1] + PLACE_CLEAR)
                   for r in sheet_refs)
    target_w = max(8.0, (tot_area * 0.62) ** 0.5) * aspect
    # LAW 6: pull the tactile buttons into a clean uniform grid at the top of the
    # zone, then shelf-pack the remaining parts around that array (its cells are
    # blockers). >=2 buttons trigger the grid; otherwise the plain shelf pack.
    top_btns = [r for r in sr["top"] if _is_button(resolvable[r])]
    if len(top_btns) >= 2:
        g_off, g_occ, g_w, g_h = _grid_controls(top_btns, bbox_of, resolvable,
                                                target_w)
        rest_top = [r for r in sr["top"] if r not in set(top_btns)]
        r_off, rw, rh = _shelf_pack(items(rest_top, "top"), target_w, g_occ)
        t_off = {**g_off, **r_off}
        tw, th = max(g_w, rw), max(g_h, rh)
    else:
        t_off, tw, th = _shelf_pack(items(sr["top"], "top"), target_w)
    blockers: list[tuple[float, float, float, float]] = []
    for r in sr["top"]:
        if not has_thru_pads(resolvable[r]):
            continue
        ox, oy = t_off[r]
        bx0, by0, bx1, by1 = bbox_of[r]
        blockers.append((ox + bx0 - PLACE_CLEAR / 2,
                         oy + by0 - PLACE_CLEAR / 2,
                         ox + bx1 + PLACE_CLEAR / 2,
                         oy + by1 + PLACE_CLEAR / 2))
    b_off, bw, bh = _shelf_pack(items(sr["bottom"], "bottom"),
                                target_w, blockers)
    return t_off, b_off, round(max(tw, bw), 4), round(max(th, bh), 4)


# how close (mm) a connector courtyard outer face must sit to the board edge to
# count as "flush" (LAW 6 / placement_mech gate). The post-placement edge-snap
# seats every off-board connector with its outer PAD at EDGE_PAD_CLEAR and its
# mouth/shell reaching or overhanging the edge, so the courtyard outer face lands
# at ~0.4 mm or NEGATIVE (overhang). TIGHTENED 9.0 -> 1.5: a connector left
# recessed (the old ~2.4 mm inset that wouldn't mate — user complaint) now FAILS
# the gate. Overhang (negative flush) passes; only an INBOARD recess fails.
EDGE_FLUSH_MM = 1.5


def _pack_connector_zone(sr: dict[str, list[str]], items, bbox_of: dict,
                         resolvable: dict, conn_rot: dict[str, float],
                         outer_dir: str, aspect: float
                         ) -> tuple[dict[str, tuple[float, float]],
                                    dict[str, tuple[float, float]],
                                    float, float]:
    """Pack an EDGE-connector subsystem so every off-board connector seats FLUSH
    at the zone's OUTER boundary (the board edge), mouth pointing off-board, with
    the rest of the subsystem packed BEHIND it, inward (LAW 6).

    ``outer_dir`` is the zone-LOCAL direction (N/S/E/W) of the board edge once
    the zone is placed: N -> outer is local -y (top), S -> +y (bottom),
    W -> -x (left), E -> +x (right). The connectors form one row flush along that
    boundary; the non-connector parts shelf-pack into the remaining inboard area.
    Offsets are returned for the connector ROTATED in place (so its haloed rotated
    bbox sits inside the zone) and for every other part at rotation 0.
    Deterministic in the given ref order."""
    conn_refs_top = [r for r in sr["top"] if r in conn_rot]
    conn_refs_bot = [r for r in sr["bottom"] if r in conn_rot]
    rest_top = [r for r in sr["top"] if r not in conn_rot]
    rest_bot = [r for r in sr["bottom"] if r not in conn_rot]

    horiz = outer_dir in ("N", "S")     # connectors row spreads along X (N/S) ...
    #                                     ... or down Y (W/E)
    # haloed ROTATED bbox of each connector (the box it really occupies)
    def hbox(r, side):
        rb = _rot_bbox(_eff_bbox_for(bbox_of[r], side), conn_rot.get(r, 0.0))
        return (rb[0] - PLACE_CLEAR / 2, rb[1] - PLACE_CLEAR / 2,
                rb[2] + PLACE_CLEAR / 2, rb[3] + PLACE_CLEAR / 2)

    # 1) lay the connectors in one flush row along the outer boundary. Largest
    # cross-axis first so the row is tight; deterministic by (-cross, ref).
    conn_all = [(r, "top") for r in conn_refs_top] + \
               [(r, "bottom") for r in conn_refs_bot]
    if horiz:
        conn_all.sort(key=lambda rs: (-(hbox(*rs)[2] - hbox(*rs)[0]), rs[0]))
    else:
        conn_all.sort(key=lambda rs: (-(hbox(*rs)[3] - hbox(*rs)[1]), rs[0]))

    placed: dict[str, dict[str, tuple[float, float]]] = {"top": {}, "bottom": {}}
    occ: list[tuple[float, float, float, float]] = []
    conn_depth = 0.0                      # how deep the connector row reaches in
    cursor = ZONE_PAD                     # position along the boundary axis
    for r, side in conn_all:
        hx0, hy0, hx1, hy1 = hbox(r, side)
        hw, hh = hx1 - hx0, hy1 - hy0
        if horiz:                          # row along X, flush at top (y=ZONE_PAD)
            ox = cursor - hx0
            oy = ZONE_PAD - hy0
            occ.append((cursor, ZONE_PAD, cursor + hw, ZONE_PAD + hh))
            cursor += hw + PLACE_CLEAR
            conn_depth = max(conn_depth, ZONE_PAD + hh)
        else:                              # column along Y, flush at left (x=PAD)
            ox = ZONE_PAD - hx0
            oy = cursor - hy0
            occ.append((ZONE_PAD, cursor, ZONE_PAD + hw, cursor + hh))
            cursor += hh + PLACE_CLEAR
            conn_depth = max(conn_depth, ZONE_PAD + hw)
        placed[side][r] = (round(ox, 4), round(oy, 4))

    # 2) shelf-pack the remaining parts into the inboard area, OFFSET behind the
    # connector row (so they never poke past the connector toward the edge). The
    # inter-band gap is generous (CONN_REST_GAP) — a faithful connector's KiCad
    # F.CrtYd (arcs / mechanical-post polygons) can exceed the parsed pad+line
    # bbox the packer reserves, and a thin gap then trips courtyards_overlap with
    # an inboard part (the camera FFC vs its CAM_SCL test point).
    CONN_REST_GAP = 2.0
    behind = conn_depth + CONN_REST_GAP
    tot_area = sum((bbox_of[r][2] - bbox_of[r][0] + PLACE_CLEAR) *
                   (bbox_of[r][3] - bbox_of[r][1] + PLACE_CLEAR)
                   for r in rest_top + rest_bot)
    # the connector row sets the boundary-axis span; keep the rest at least that
    # wide so the zone stays wide+shallow.
    row_span = max(cursor, 8.0)
    target_w = max(row_span - ZONE_PAD, (tot_area * 0.62) ** 0.5 * aspect)

    rt = [(r, _eff_bbox_for(bbox_of[r], "top"), 0.0) for r in rest_top]
    t_rest, _tw, _th = _shelf_pack(rt, target_w)
    blockers: list[tuple[float, float, float, float]] = []
    for r in rest_top:
        if not has_thru_pads(resolvable[r]):
            continue
        ox, oy = t_rest[r]
        bx0, by0, bx1, by1 = bbox_of[r]
        blockers.append((ox + bx0 - PLACE_CLEAR / 2 + (0 if horiz else behind),
                         oy + by0 - PLACE_CLEAR / 2 + (behind if horiz else 0),
                         ox + bx1 + PLACE_CLEAR / 2 + (0 if horiz else behind),
                         oy + by1 + PLACE_CLEAR / 2 + (behind if horiz else 0)))
    rb = [(r, _eff_bbox_for(bbox_of[r], "bottom"), 0.0) for r in rest_bot]
    b_rest, _bw, _bh = _shelf_pack(rb, target_w, blockers)

    for r, (dx, dy) in t_rest.items():
        placed["top"][r] = (round(dx + (0 if horiz else behind), 4),
                            round(dy + (behind if horiz else 0), 4))
    for r, (dx, dy) in b_rest.items():
        placed["bottom"][r] = (round(dx + (0 if horiz else behind), 4),
                               round(dy + (behind if horiz else 0), 4))

    # 3) zone extent = max over every placed haloed (rotated for conns) bbox.
    zw = zh = ZONE_PAD
    for side in ("top", "bottom"):
        for r, (ox, oy) in placed[side].items():
            if r in conn_rot:
                rb2 = _rot_bbox(_eff_bbox_for(bbox_of[r], side),
                                conn_rot.get(r, 0.0))
            else:
                rb2 = _eff_bbox_for(bbox_of[r], side)
            zw = max(zw, ox + rb2[2] + PLACE_CLEAR / 2)
            zh = max(zh, oy + rb2[3] + PLACE_CLEAR / 2)
    zw = round(zw + ZONE_PAD, 4)
    zh = round(zh + ZONE_PAD, 4)

    # 4) for a BOTTOM (S/+y) or RIGHT (E/+x) outer edge, the connectors were laid
    # flush at the LOW boundary (top/left); flip the depth axis so they end flush
    # at the HIGH boundary (the actual board edge) with the rest behind, inward.
    if outer_dir in ("S", "E"):
        flip_y = (outer_dir == "S")
        out: dict[str, dict[str, tuple[float, float]]] = {"top": {}, "bottom": {}}
        for side in ("top", "bottom"):
            for r, (ox, oy) in placed[side].items():
                if r in conn_rot:
                    rb2 = _rot_bbox(_eff_bbox_for(bbox_of[r], side),
                                    conn_rot.get(r, 0.0))
                else:
                    rb2 = _eff_bbox_for(bbox_of[r], side)
                bw = rb2[2] - rb2[0]
                bh = rb2[3] - rb2[1]
                if flip_y:
                    noy = zh - (oy + rb2[3]) - rb2[1]
                    out[side][r] = (round(ox, 4), round(noy, 4))
                else:
                    nox = zw - (ox + rb2[2]) - rb2[0]
                    out[side][r] = (round(nox, 4), round(oy, 4))
        placed = out

    return placed["top"], placed["bottom"], zw, zh


def _connector_sheet_edges() -> dict[str, str]:
    """sheet -> board EDGE (N/E/S/W) for every subsystem that carries an off-board
    connector (LAW 6). The edge is read from the DECLARATIVE carrier/floorplan.json
    (the same spec build_plan pins blocks from); a connector sheet pinned to an
    INTERIOR slot, or absent from the spec, is reported (the placement_mech gate
    then HARD-FAILS it — an off-board connector that is not on an edge is
    unbuildable). Deterministic: the spec is read once and keyed by sheet name."""
    from schgen.generate.floorplan import (load_floorplan_spec,
                                           FLOORPLAN_SPEC)
    out: dict[str, str] = {}
    if not FLOORPLAN_SPEC.exists():
        return out
    try:
        spec = load_floorplan_spec()
    except Exception:  # noqa: BLE001 — a malformed spec is reported by build_plan
        return out
    if spec is None:
        return out
    return dict(spec.edge_of)


def subsystem_zone_geometry(two_side: bool = True) -> ZoneGeom:
    """The SHARED packer: for every non-SoM subsystem, its REAL 2-sided packed
    zone (w, h) + per-part offsets, keyed on the STABLE board-unique refs. Built
    from the subsystem circuits (no dependence on the emitted root schematic), so
    `schgen floorplan` and `schgen board` get byte-identical geometry."""
    import json as _json
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.generate.board import _renamed_ref
    from schgen.core.model import PinRef

    idx_path = CARRIER / "sheet_index.json"
    sheet_index = (_json.loads(idx_path.read_text())
                   if idx_path.exists() else {})
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]

    from schgen.generate.floorplan import _EDGE_FAMILIES

    refs_by_sheet: dict[str, list[str]] = {}
    bbox_of: dict[str, tuple[float, float, float, float]] = {}
    resolvable: dict[str, Path] = {}
    side_of: dict[str, str] = {}
    mh_refs: list[str] = []
    deferred: list[str] = []
    edge_sheets: set[str] = set()       # sheets with an off-board edge connector
    # LAW 6: off-board connector refs per sheet + their MPN (for the rotation).
    conn_mpn_of: dict[str, str] = {}    # bref -> mating-face MPN

    sheet_edge = _connector_sheet_edges()    # sheet -> board edge (from the spec)

    for i, sc in enumerate(sheets, start=1):
        if sc.name.startswith("som_j") or sc.name == "som_decoupling":
            continue        # receptacles ARE the SoM; som_decoupling is placed
            #                 BOTTOM-side under the SoM core, not in a zone (LAW 6)
        band = sheet_index.get(sc.name, i)
        c = sc.circuit
        # per-sheet decoupling on the board-unique ref namespace (equivalent to
        # the merged-netlist classification — proven — and side-stable).
        snets: dict[str, list[PinRef]] = {}
        for nname, net in c.nets.items():
            snets[nname] = [
                PinRef(_renamed_ref(p.ref, band, sheet=sc.name)
                       if not p.ref.startswith("#") else p.ref, p.pin)
                for p in net.pins]
        sdec = _decoupling_caps(snets)
        for ref, part in c.parts.items():
            bref = _renamed_ref(ref, band, sheet=sc.name)
            if part.value in _EDGE_FAMILIES:
                edge_sheets.add(sc.name)
            if part.value in CONN_MATING_FACE:
                conn_mpn_of[bref] = part.value
            if part.lib_id.startswith("Mechanical:MountingHole"):
                mh_refs.append(bref)
                continue
            mod = resolve_mod(part.footprint)
            if mod is None:
                deferred.append(f"{bref} ({sc.name}): footprint "
                                f"{part.footprint!r} not found")
                continue
            resolvable[bref] = mod
            bbox_of[bref] = _footprint_bbox(mod)
            side_of[bref] = _classify_side(bref, part.lib_id, bbox_of[bref],
                                           sdec, two_side)
            refs_by_sheet.setdefault(sc.name, []).append(bref)

    # LAW 6: per-connector placement rotation (mating face -> off-board) keyed on
    # the connector's assigned board edge; the local OUTER direction the edge lies
    # in once the zone is placed (== the edge, since the zone keeps board axes).
    conn_rot: dict[str, float] = {}
    conn_edge: dict[str, str] = {}
    sheet_conn_rot: dict[str, dict[str, float]] = {}
    sheet_outer: dict[str, str] = {}
    for sheet, brefs in refs_by_sheet.items():
        edge = sheet_edge.get(sheet)
        for bref in brefs:
            mpn = conn_mpn_of.get(bref)
            if mpn is None or bref not in bbox_of:
                continue
            if edge is None:
                # connector NOT pinned to an edge — leave un-rotated; the
                # placement_mech gate HARD-FAILS it (off-board connector off-edge).
                continue
            rot = connector_edge_rotation(CONN_MATING_FACE[mpn], edge)
            conn_rot[bref] = rot
            conn_edge[bref] = edge
            sheet_conn_rot.setdefault(sheet, {})[bref] = rot
            sheet_outer[sheet] = edge

    zone_box: dict[str, tuple[float, float]] = {}
    top_off: dict[str, dict[str, tuple[float, float]]] = {}
    bot_off: dict[str, dict[str, tuple[float, float]]] = {}
    for sheet in sorted(refs_by_sheet):
        # EDGE-connector subsystems pack WIDE + SHALLOW (aspect > 1) so their
        # block sits behind the edge without eating deep into the board; INTERIOR
        # subsystems stay squarish.
        aspect = EDGE_ZONE_ASPECT if sheet in edge_sheets else 1.0
        t_off, b_off, zw, zh = _pack_one_zone(
            refs_by_sheet[sheet], side_of, bbox_of, resolvable, aspect,
            conn_rot=sheet_conn_rot.get(sheet),
            outer_dir=sheet_outer.get(sheet))
        top_off[sheet] = t_off
        bot_off[sheet] = b_off
        zone_box[sheet] = (zw, zh)

    return ZoneGeom(zone_box=zone_box, top_off=top_off, bot_off=bot_off,
                    side_of=side_of, bbox_of=bbox_of, resolvable=resolvable,
                    refs_by_sheet=refs_by_sheet, mh_refs=sorted(mh_refs),
                    deferred=deferred, conn_rot=conn_rot, conn_edge=conn_edge)


# ---- the model build -------------------------------------------------------------

def build_model(two_side: bool = True) -> PcbModel:
    from schgen.core.link import all_subsystem_paths, load_subsystem, link, \
        load_som_contract
    from schgen.generate import floorplan as fp
    from schgen.verify import powertree

    nets = board_netlist()
    parts = board_parts()

    # net-number table: 0 reserved for "no net"; deterministic by sorted name.
    real_nets = sorted(n for n in nets if n and not n.startswith("unconnected-"))
    net_numbers: dict[str, int] = {"": 0}
    for i, name in enumerate(real_nets, start=1):
        net_numbers[name] = i
    # pin -> (net number, net name)
    pin_net: dict[tuple[str, str], tuple[int, str]] = {}
    for name, pins in nets.items():
        if name.startswith("unconnected-"):
            continue          # unrouted/un-netted: pad stays net 0
        num = net_numbers.get(name, 0)
        for pr in pins:
            if not pr.ref.startswith("#"):
                pin_net[(pr.ref, pr.pin)] = (num, name)

    # SHARED zone geometry: the REAL 2-sided packed (w, h) + per-part offsets for
    # every subsystem, keyed on the stable board-unique refs. This is the SAME
    # function the FLOORPLAN sizes its blocks from, so the floorplan block (w, h)
    # and the PCB zone (w, h) are byte-identical -> the placement lands inside the
    # floorplan block and FLOORPLAN.svg agrees with the PCB ratsnest by
    # construction (no more 235x215-vs-165x155 divergence).
    zg = subsystem_zone_geometry(two_side=two_side)
    zone_box = zg.zone_box
    top_off = zg.top_off
    bot_off = zg.bot_off
    side_of = dict(zg.side_of)
    bbox_of = dict(zg.bbox_of)
    resolvable = dict(zg.resolvable)
    deferred = list(zg.deferred)
    mh_refs = list(zg.mh_refs)
    mh_set = set(mh_refs)

    # The shared packer omits the FIXED-position parts (mounting holes + the SoM
    # DF40 receptacles) + the under-SoM decoupling — they are not zone-packed.
    # Resolve their footprints from the board parts so the emission loop still
    # places them (positions set in STEP 3: corner-forced holes, centered/mirrored
    # mezzanine, and the bottom-side SoM-shadow decoupling grid).
    for ref, (sheet, footprint, _value, _lib) in parts.items():
        if ref in resolvable:
            continue
        if not (ref in mh_set or sheet.startswith("som_j")
                or sheet == "som_decoupling"):
            continue
        mod = resolve_mod(footprint)
        if mod is None:
            deferred.append(f"{ref} ({sheet}): footprint {footprint!r} "
                            f"not found in parts/ or the KiCad std libs")
            continue
        resolvable[ref] = mod
        bbox_of[ref] = _footprint_bbox(mod)
        side_of[ref] = "top"

    # floorplan plan (block POSITIONS + the derived outline) + net classes. The
    # floorplan calls the SAME subsystem_zone_geometry above for its block sizes,
    # so plan.blocks[*].w/h == zone_box[*] and the floorplan outline (fp.BOARD_W/H)
    # holds every packed block. The PCB honours both as the source of truth.
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    link_result = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    plan = fp.build_plan(sheets, link_result, regs)
    classes, netclass_of = _net_classes(sheets)
    board_w, board_h = fp.BOARD_W, fp.BOARD_H

    # The SoM mezzanine receptacles (sheets som_j1/2/3) are FIXED at the
    # centered, SoM-mirrored DF40 positions and form the SoM region; every
    # other sheet is a SUBSYSTEM whose footprints cluster into one contiguous
    # zone. Per-connector ROTATION matches the SoM (J3 vertical, others flat).
    som = plan.som
    som_rot = {j.ref: (90.0 if j.w < j.h else 0.0) for j in som.js}
    som_rel = {j.ref: (j.x, j.y) for j in som.js}     # SoM-relative centers
    som_j_refs: dict[str, str] = {}                    # board ref -> J1/J2/J3
    fixed_rot: dict[str, float] = {}
    for ref, (sheet, _fp, _v, _lib) in parts.items():
        if ref not in resolvable or not sheet.startswith("som_j"):
            continue
        m = re.match(r"som_j(\d)", sheet)
        if m and ref.startswith("J"):
            jname = f"J{m.group(1)}"
            if jname in som_rel:
                som_j_refs[ref] = jname
                fixed_rot[ref] = som_rot[jname]

    # LAW 6: every off-board edge connector carries the placement rotation that
    # turns its mating face OFF-BOARD (computed in subsystem_zone_geometry from the
    # connector's assigned board edge). The shared packer already reserved the
    # ROTATED bbox + seated the connector flush at the zone's outer edge, so this
    # rotation lands the footprint exactly where the zone expects it.
    for ref, rot in zg.conn_rot.items():
        if ref in resolvable:
            fixed_rot[ref] = rot

    # ---- STEP 1: zone geometry comes from the SHARED packer (above) ----------
    # zone_box / top_off / bot_off already hold every subsystem's REAL 2-sided
    # packed (w, h) + per-part offsets (zg). The floorplan sized its blocks from
    # the SAME zg, so each block's (w, h) == zone_box[sheet] exactly.

    # ---- STEP 2: HONOUR the floorplan — positions + outline are the truth ----
    # The board outline is the floorplan's derived+grown outline (fp.BOARD_W/H),
    # and every subsystem zone is anchored at its FLOORPLAN block top-left
    # (plan.blocks). The SoM is at the floorplan's centered origin. No re-sizing,
    # no re-layout, no independent board grow: the FLOORPLAN.svg and this PCB are
    # the same picture. (The floorplan layout proved every block fits inside the
    # outline with the SoM region clear, so nothing lands off-board.)
    block_of = {b.name: b for b in plan.blocks}
    zorigin: dict[str, tuple[float, float]] = {}
    for sheet in zone_box:
        b = block_of.get(sheet)
        if b is None:
            continue
        zorigin[sheet] = (b.x, b.y)

    sx_off, sy_off = plan.som_x - SOM_HALO_PCB, plan.som_y - SOM_HALO_PCB
    som_w = som.w + 2 * SOM_HALO_PCB
    som_h = som.h + 2 * SOM_HALO_PCB

    # SoM keep-out (centered on the floorplan SoM body) + SoM mezzanine J
    # positions (the floorplan-centered, SoM-mirrored DF40 centers).
    halo = 1.0
    keepout = (plan.som_x - halo, plan.som_y - halo,
               plan.som_x + som.w + halo, plan.som_y + som.h + halo)
    som_view = {jn: (plan.som_x + sx, plan.som_y + sy)
                for jn, (sx, sy) in som_rel.items()}

    # ---- STEP 3: final origins (board frame) for every footprint ------------
    pos: dict[str, tuple[float, float]] = {}
    # mounting holes -> the 4 corners of the FLOORPLAN-sized board
    corners = [(MH_INSET, MH_INSET),
               (board_w - MH_INSET, MH_INSET),
               (board_w - MH_INSET, board_h - MH_INSET),
               (MH_INSET, board_h - MH_INSET)]
    for i, ref in enumerate(mh_refs):
        pos[ref] = corners[i % 4]
    # SoM receptacles
    for ref, jname in som_j_refs.items():
        pos[ref] = som_view[jname]
    # subsystem footprints: GRID-SNAPPED zone origin + per-part packed offset.
    # The shelf packer (above) reserved EXACT PLACE_CLEAR gaps between the parts
    # in each zone's local frame; snapping each part's ABSOLUTE board position to
    # the coarse GRID afterwards would round two neighbours across a half-grid
    # boundary in OPPOSITE directions and collapse a 2.46 mm row pitch to 1.27 mm
    # — a 0.19 mm courtyard overlap (the intra-zone courtyards_overlap DRC errors
    # this caused). Instead snap the zone ORIGIN once and add the raw packed
    # offsets, so the packer's exact intra-zone clearance is preserved verbatim
    # while the zone as a whole still lands on the placement grid.
    grid_placed: set[str] = set()
    for sheet in zorigin:
        zx, zy = zorigin[sheet]
        gzx = _gridify(ORIGIN_X + zx) - ORIGIN_X
        gzy = _gridify(ORIGIN_Y + zy) - ORIGIN_Y
        for r, (dx, dy) in top_off[sheet].items():
            pos[r] = (gzx + dx, gzy + dy)
            grid_placed.add(r)
        for r, (dx, dy) in bot_off[sheet].items():
            pos[r] = (gzx + dx, gzy + dy)
            grid_placed.add(r)

    # LAW 6: SoM power-entry decoupling — grid the som_decoupling caps on the
    # BOTTOM side, spread across the SoM shadow (the dead area under the
    # mezzanine). They bypass the rails the carrier delivers to the DF40 right at
    # the power entry. Bottom side clears the top-side DF40 receptacles (different
    # copper layer); the shadow is otherwise empty so the grid never collides.
    udec = sorted(r for r, (sh, _f, _v, _l) in parts.items()
                  if sh == "som_decoupling" and r in resolvable)
    if udec:
        M = 6.0                                    # inset from the SoM core edge
        rx0, ry0 = plan.som_x + M, plan.som_y + M
        rw = max(1.0, som.w - 2 * M)
        rh = max(1.0, som.h - 2 * M)
        n = len(udec)
        cols = max(1, min(n, round((n * rw / rh) ** 0.5)))
        rows = max(1, (n + cols - 1) // cols)
        for i, ref in enumerate(udec):
            cxi, cyi = i % cols, i // cols
            px = rx0 + rw * (cxi + 0.5) / cols
            py = ry0 + rh * (cyi + 0.5) / rows
            pos[ref] = (round(px, 4), round(py, 4))
            side_of[ref] = "bottom"
            grid_placed.add(ref)

    # ---- LEVER L4: BOTTOM-PULL toward the SoM (cross-airwire reduction) ------
    # The board is AIRWIRE-BUDGET bound (LAW 5) and the BOTTOM is ~82% empty. Every
    # subsystem nets most of its pins to the SoM DF40 J-strips at the board centre,
    # so its cross-subsystem airwire is dominated by the span from its cluster to
    # the SoM. The 2-side policy already put its small passives on the BOTTOM layer,
    # so that bottom sub-cluster can slide toward the SoM to SHORTEN those net spans
    # and drop the REAL cross-airwire the LAW-5 gate measures. The cluster moves as
    # a RIGID GROUP (internal packing — every intra-cluster clearance — preserved),
    # by the LARGEST shift toward the SoM centre that still: (a) keeps every part
    # on-board; (b) clears — with full courtyard halo — EVERY other part already on
    # the BOTTOM layer (other subsystems' clusters, the som_decoupling grid, and the
    # not-yet-moved bottom parts) so no bottom-vs-bottom overlap/short; (c) never
    # lands a bottom SMD over a TOP through-hole pad (copper on all layers); and
    # (d) keeps the subsystem's combined top+bottom dispersion under a conservative
    # cap (below the LAW-5 9x gate) so it still reads as ONE cluster. ADDS no net,
    # RELOCATES no net (LAW 0): only the physical XY of already-bottom passives
    # moves. The REAL DRC + ratsnest gates remain the arbiters.
    if two_side:
        som_cx = plan.som_x + som.w / 2.0
        som_cy = plan.som_y + som.h / 2.0

        def _eff_box(ref: str, px: float, py: float
                     ) -> tuple[float, float, float, float]:
            ex0, ey0, ex1, ey1 = _eff_bbox_for(bbox_of[ref],
                                               side_of.get(ref, "top"))
            return (px + ex0, py + ey0, px + ex1, py + ey1)

        def _halo(b: tuple[float, float, float, float], m: float
                  ) -> tuple[float, float, float, float]:
            return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)

        def _hit(b: tuple[float, float, float, float],
                 boxes: list[tuple[float, float, float, float]]) -> bool:
            for o in boxes:
                if (b[0] < o[2] and b[2] > o[0]
                        and b[1] < o[3] and b[3] > o[1]):
                    return True
            return False

        # TOP through-hole pad keepout boxes (haloed) — a bottom SMD over one is a
        # cross-layer short (copper on all layers).
        tht_boxes: list[tuple[float, float, float, float]] = [
            _halo(_eff_box(r, pos[r][0], pos[r][1]), PLACE_CLEAR)
            for r in pos
            if side_of.get(r) == "top" and r in resolvable
            and has_thru_pads(resolvable[r])]

        # occupancy of every BOTTOM-layer part (haloed) — the moving cluster must
        # not overlap any of these. Built once; each subsystem removes its own
        # movers before testing and re-adds them (shifted) after committing, so a
        # later subsystem sees the earlier one's final seat.
        bot_box: dict[str, tuple[float, float, float, float]] = {
            r: _halo(_eff_box(r, pos[r][0], pos[r][1]), PLACE_CLEAR / 2)
            for r in pos
            if side_of.get(r) == "bottom" and r in bbox_of}

        DISP_CAP_L4 = 5.0          # conservative; LAW-5 gate fails only at 9.0x
        EDGE_MARGIN = 0.6          # keep shifted copper this far inside Edge.Cuts
        STEP = 1.0
        for sheet in sorted(zorigin):
            movers = [r for r in bot_off.get(sheet, {})
                      if side_of.get(r) == "bottom" and r in pos
                      and r[:1] in ("R", "C", "L")
                      and not r.startswith(("RJ", "LED"))]
            if len(movers) < 2:
                continue
            gcx = sum(pos[r][0] for r in movers) / len(movers)
            gcy = sum(pos[r][1] for r in movers) / len(movers)
            vx, vy = som_cx - gcx, som_cy - gcy
            dist = (vx * vx + vy * vy) ** 0.5
            if dist < 1.0:
                continue
            ux, uy = vx / dist, vy / dist
            # bottom occupancy EXCLUDING this subsystem's own movers
            others = [bot_box[r] for r in bot_box if r not in set(movers)]
            allr = [r for r in (list(top_off.get(sheet, {}))
                                + list(bot_off.get(sheet, {})))
                    if r in pos and r in bbox_of]
            sum_area = sum((_eff_box(r, 0.0, 0.0)[2] - _eff_box(r, 0.0, 0.0)[0])
                           * (_eff_box(r, 0.0, 0.0)[3] - _eff_box(r, 0.0, 0.0)[1])
                           for r in allr) or 1.0
            chosen = 0.0
            for k in range(int(min(dist, 40.0) / STEP), 0, -1):
                shift = k * STEP
                ok = True
                shifted: dict[str, tuple[float, float]] = {}
                for r in movers:
                    nx, ny = pos[r][0] + ux * shift, pos[r][1] + uy * shift
                    bb = _eff_box(r, nx, ny)
                    if (bb[0] < EDGE_MARGIN or bb[1] < EDGE_MARGIN
                            or bb[2] > board_w - EDGE_MARGIN
                            or bb[3] > board_h - EDGE_MARGIN):
                        ok = False
                        break
                    hb = _halo(bb, PLACE_CLEAR / 2)
                    if _hit(hb, others) or _hit(hb, tht_boxes):
                        ok = False
                        break
                    shifted[r] = (nx, ny)
                if not ok:
                    continue
                xs0 = []
                ys0 = []
                xs1 = []
                ys1 = []
                for r in allr:
                    px, py = shifted.get(r, pos[r])
                    bb = _eff_box(r, px, py)
                    xs0.append(bb[0])
                    ys0.append(bb[1])
                    xs1.append(bb[2])
                    ys1.append(bb[3])
                if ((max(xs1) - min(xs0)) * (max(ys1) - min(ys0))
                        / sum_area) > DISP_CAP_L4:
                    continue
                chosen = shift
                break
            if chosen > 0.0:
                for r in movers:
                    nx, ny = (round(pos[r][0] + ux * chosen, 4),
                              round(pos[r][1] + uy * chosen, 4))
                    pos[r] = (nx, ny)
                    bot_box[r] = _halo(_eff_box(r, nx, ny), PLACE_CLEAR / 2)

    # LAW 6: seat every off-board connector AT the board edge — push it outward
    # (perpendicular to its edge) until its outermost PAD clears EDGE_PAD_CLEAR,
    # so the mouth/shell reaches/overhangs the edge and a cable actually mates
    # (user: "connectors at the absolute edge or they won't mate"). Only the
    # perpendicular axis moves; the along-edge position from the zone pack stays.
    # Connectors keep their exact (non-gridified) seat so the pad clearance holds.
    for ref, edge in zg.conn_edge.items():
        if ref not in resolvable or ref not in pos:
            continue
        pb = _rot_pad_bbox(resolvable[ref], fixed_rot.get(ref, 0.0),
                           side_of.get(ref, "top"))
        if pb is None:
            continue
        px0, py0, px1, py1 = pb
        x, y = pos[ref]
        if edge == "N":
            y = EDGE_PAD_CLEAR - py0
        elif edge == "S":
            y = board_h - EDGE_PAD_CLEAR - py1
        elif edge == "W":
            x = EDGE_PAD_CLEAR - px0
        elif edge == "E":
            x = board_w - EDGE_PAD_CLEAR - px1
        pos[ref] = (round(x, 4), round(y, 4))
        grid_placed.add(ref)

    fixed = set(mh_refs) | set(som_j_refs)

    insts: list[FootprintInst] = []
    placed = 0
    n_top = n_bottom = 0
    for ref in sorted(resolvable):
        sheet, footprint, value, lib = parts[ref]
        mod = resolvable[ref]
        bx, by = pos[ref]
        side = "top" if ref in fixed else side_of[ref]
        # pad -> net
        pad_nets: dict[str, tuple[int, str]] = {}
        for pad in pad_names(mod):
            pad_nets[pad] = pin_net.get((ref, pad), (0, ""))
        # subsystem parts carry a grid-snapped zone origin + the packer's RAW
        # offset (intra-zone clearance preserved — see STEP 3 above), so they are
        # NOT re-gridified here; only the fixed-position parts (mounting holes,
        # SoM receptacles) snap their absolute board position to the grid.
        if ref in grid_placed:
            fx, fy = round(ORIGIN_X + bx, 4), round(ORIGIN_Y + by, 4)
        else:
            fx, fy = _gridify(ORIGIN_X + bx), _gridify(ORIGIN_Y + by)
        insts.append(FootprintInst(
            ref=ref, value=value, footprint=footprint,
            x=fx, y=fy,
            rotation=fixed_rot.get(ref, 0.0), pad_nets=pad_nets,
            mod_path=mod, sheet=sheet, side=side))
        placed += 1
        if side == "bottom":
            n_bottom += 1
        else:
            n_top += 1

    kx0, ky0, kx1, ky1 = keepout
    # SoM module-body CORE (board page frame, NO halo) — the rectangle the
    # plugged-in SoM physically covers. Grown SOM_CORE_CLEARANCE (3%, 1.5% each
    # side, centred) beyond the bare DF40 body span so the silk outline + the
    # keepout reserve a mating-clearance margin around the module (user request).
    # The placement_mech gate forbids any non-passive/test-point/tall part inside
    # it AND any carrier TOP-side part (the SoM's own bottom components occupy the
    # standoff gap) — LAW 6.
    _ccx = som.w * SOM_CORE_CLEARANCE / 2
    _ccy = som.h * SOM_CORE_CLEARANCE / 2
    som_core = (ORIGIN_X + plan.som_x - _ccx, ORIGIN_Y + plan.som_y - _ccy,
                ORIGIN_X + plan.som_x + som.w + _ccx,
                ORIGIN_Y + plan.som_y + som.h + _ccy)
    return PcbModel(
        board_w=board_w, board_h=board_h, insts=insts,
        net_numbers=net_numbers, netclass_of=netclass_of, classes=classes,
        placed=placed, deferred=deferred,
        som_keepout=(ORIGIN_X + kx0, ORIGIN_Y + ky0,
                     ORIGIN_X + kx1, ORIGIN_Y + ky1),
        n_top=n_top, n_bottom=n_bottom, two_side=two_side,
        som_core=som_core)


# ---- placed-geometry queries (for the ratsnest renderer + LAW-5 gate) ------------

def _inst_pad_geom(inst: FootprintInst) -> list[tuple[str, float, float, str]]:
    """Every pad of a placed footprint as (pad_name, x, y, net_name) in the
    BOARD page frame. Applies the footprint rotation and, for a bottom-side
    part, the F->B X-mirror about the origin (KiCad's flip convention) — so the
    pad centers match where the copper actually lands."""
    out: list[tuple[str, float, float, str]] = []
    doc = sexpr.loads(inst.mod_path.read_text())
    rot = math.radians(inst.rotation or 0.0)
    cs, sn = math.cos(rot), math.sin(rot)
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        name = str(node[1]) if len(node) > 1 else ""
        at = sexpr.find(node, "at")
        if not (at and len(at) >= 3):
            continue
        px, py = float(at[1]), float(at[2])
        if inst.side == "bottom":
            px = -px                       # F->B mirror about the origin X axis
        # rotate about origin (KiCad +rot is counter-clockwise on screen,
        # but for a symmetric airwire endpoint the sign is immaterial; use the
        # standard math rotation for determinism)
        rx = px * cs - py * sn
        ry = px * sn + py * cs
        _num, nname = inst.pad_nets.get(name, (0, ""))
        out.append((name, round(inst.x + rx, 3), round(inst.y + ry, 3), nname))
    return out


def _inst_courtyard(inst: FootprintInst) -> tuple[float, float, float, float]:
    """The placed footprint's courtyard bbox in the BOARD page frame, with the
    placement rotation and (for a bottom part) the F->B X-mirror applied. This
    is the box the LAW-5 off-board + grouping gate reasons about."""
    bx0, by0, bx1, by1 = _footprint_bbox(inst.mod_path)
    if inst.side == "bottom":
        bx0, bx1 = -bx1, -bx0
    rb = _rot_bbox((bx0, by0, bx1, by1), inst.rotation or 0.0)
    return (round(inst.x + rb[0], 3), round(inst.y + rb[1], 3),
            round(inst.x + rb[2], 3), round(inst.y + rb[3], 3))


def _inst_pad_bbox(inst: FootprintInst) -> tuple[float, float, float, float]:
    """The placed footprint's COPPER (pad) bbox in the board page frame. Unlike
    _inst_courtyard (which includes an off-board mating area — a USB-C shell, an
    SD-card slot, a PMOD module outline — that legitimately overhangs the edge on
    an edge connector), this is the copper that MUST sit on the board. The LAW-5
    off-board check uses THIS so a correctly-seated edge connector (pads on-board,
    mouth overhanging) is not false-flagged, while a genuinely off-board part
    (copper outside Edge.Cuts) still fails."""
    pb = _rot_pad_bbox(inst.mod_path, inst.rotation or 0.0, inst.side)
    if pb is None:
        return _inst_courtyard(inst)        # pad-less fab-art: fall back
    return (round(inst.x + pb[0], 3), round(inst.y + pb[1], 3),
            round(inst.x + pb[2], 3), round(inst.y + pb[3], 3))


def net_pad_positions(model: PcbModel) -> dict[str, list[tuple[float, float, str, str]]]:
    """net name -> [(x, y, ref, sheet), ...] pad centers in the board page
    frame, for every REAL net (skips no-net + the unconnected- placeholders).
    Used to draw the unrouted airwires and to budget cross-subsystem nets."""
    out: dict[str, list[tuple[float, float, str, str]]] = {}
    for inst in model.insts:
        for _pad, x, y, nname in _inst_pad_geom(inst):
            if not nname or nname.startswith("unconnected-"):
                continue
            out.setdefault(nname, []).append((x, y, inst.ref, inst.sheet))
    return out


# ---- emission --------------------------------------------------------------------

def _flip_layer_token(name: str) -> str:
    """F.<x> -> B.<x> (and vice-versa, idempotent for non-F/B layers)."""
    if name.startswith("F."):
        return "B." + name[2:]
    if name.startswith("B."):
        return name
    return name


def _flip_to_bottom(node: list) -> None:
    """Recursively flip a footprint subtree from the top (F.Cu) to the bottom
    (B.Cu) side, the KiCad way: swap every (layer ...)/(layers ...) F.* token to
    its B.* twin, and add (justify mirror) to text effects. Local coordinates
    are NOT touched — KiCad mirrors at render time from the layer. Deterministic
    and reversible (re-running on a B.* tree is a no-op for the layers)."""
    for sub in node:
        if not isinstance(sub, list) or not sub:
            continue
        head = sub[0]
        if head in (Sym("layer"), Sym("layers")):
            for i in range(1, len(sub)):
                if isinstance(sub[i], str):
                    sub[i] = _flip_layer_token(sub[i])
        elif head == Sym("effects"):
            # add (justify mirror) if no justify present; else ensure mirror
            just = next((x for x in sub if isinstance(x, list) and x
                         and x[0] == Sym("justify")), None)
            if just is None:
                sub.append([Sym("justify"), Sym("mirror")])
            elif Sym("mirror") not in just:
                just.append(Sym("mirror"))
            _flip_to_bottom(sub)
        else:
            _flip_to_bottom(sub)


def _embed_footprint(inst: FootprintInst, uid) -> list:
    """Parse the .kicad_mod, set its placement + pad nets, return the
    (footprint ...) node for the .kicad_pcb. Every nested uuid is content-
    derived so regeneration is byte-identical."""
    mod = sexpr.loads(inst.mod_path.read_text())
    assert isinstance(mod, list) and mod and mod[0] == Sym("footprint")

    # lib_id (footprint name) -> the full "lib:name". Use the RESOLVED name so
    # an aliased footprint (e.g. C_1206_3225Metric -> _3216Metric) carries the
    # name of the .kicad_mod actually embedded, not the requested one.
    mod[1] = _FOOTPRINT_ALIASES.get(inst.footprint, inst.footprint)

    # placement: (at x y rot) at the top level (after version/generator/layer)
    # remove any existing (at ...) then insert ours right after (layer ...).
    body = [x for x in mod
            if not (isinstance(x, list) and x and x[0] == Sym("at"))]
    at_node = [Sym("at"), inst.x, inst.y] + (
        [inst.rotation] if inst.rotation else [])
    # find insert point: after the first (layer ...) child
    out: list = []
    inserted = False
    for x in body:
        out.append(x)
        if (not inserted and isinstance(x, list) and x and x[0] == Sym("layer")):
            out.append(at_node)
            inserted = True
    if not inserted:
        out.insert(1, at_node)

    # 2-side assembly: a bottom-side footprint flips to B.Cu. KiCad's on-disk
    # convention keeps the local pad/graphic COORDINATES unchanged and only
    # swaps every F.* layer token to its B.* twin (the renderer mirrors based on
    # the layer), plus a (justify mirror) on text. Done before the uuid/net pass
    # so the flipped tree is what gets stamped.
    if inst.side == "bottom":
        _flip_to_bottom(out)

    # stamp a stable top-level uuid, replace placement+pad uuids deterministically
    _set_or_add(out, [Sym("uuid"), uid(f"fp:{inst.ref}")])

    # thermal-via inheritance: a faithful EP-bearing footprint carries blank
    # ("") no-net thermal vias/pads SITTING INSIDE its exposed pad's copper
    # (e.g. the TPS26631 EP + its thermal vias). They are physically the SAME
    # copper as the EP, so they inherit the EP pad's net — that removes the
    # false "no-net via vs GND EP" clearance/mask error without touching the
    # footprint geometry (we only assign nets, exactly like every other pad).
    inherit = _thermal_via_nets(out, inst.pad_nets)

    # set Reference/Value property text + assign pad nets + restamp child uuids
    pad_seq = 0
    prop_seq = 0
    for node in out:
        if not isinstance(node, list) or not node:
            continue
        head = node[0]
        if head == Sym("property") and len(node) > 2:
            if node[1] == "Reference":
                node[2] = inst.ref
            elif node[1] == "Value":
                node[2] = inst.value
            _restamp_uuid(node, uid(f"fp:{inst.ref}:prop:{prop_seq}"))
            prop_seq += 1
        elif head == Sym("pad") and len(node) > 1:
            pad_name = str(node[1])
            num, nname = inst.pad_nets.get(pad_name, (0, ""))
            if (num, nname) == (0, "") and pad_seq in inherit:
                num, nname = inherit[pad_seq]
            _set_pad_net(node, num, nname)
            # propagate the footprint rotation into each pad's LOCAL orientation
            # — KiCad's native representation of a rotated footprint (its own
            # SoM J1/J2/J3 store (at x y <fp-rot>) on every pad). Without this a
            # non-square rect pad authored for the 0-deg frame keeps its 0-deg
            # orientation and KiCad's pad-clearance check sees the rect's long
            # side fall along the pitch axis -> false intra-footprint shorts.
            if inst.rotation:
                _rotate_pad(node, inst.rotation)
            _restamp_uuid(node, uid(f"fp:{inst.ref}:pad:{pad_seq}"))
            pad_seq += 1
        elif head in (Sym("fp_text"), Sym("fp_line"), Sym("fp_rect"),
                      Sym("fp_circle"), Sym("fp_arc"), Sym("fp_poly")):
            _restamp_uuid(node, uid(f"fp:{inst.ref}:gfx:{pad_seq}:{prop_seq}"))
    return out


def _rotate_pad(pad: list, fp_rot: float) -> None:
    """Add ``fp_rot`` to a pad's LOCAL (at x y [rot]) orientation, matching how
    KiCad stores a rotated footprint (every pad carries the footprint rotation
    in its own (at)). The pad's local x/y are NOT changed — KiCad rotates the
    positions by the footprint (at) at load; only the pad's own rect must turn
    so a non-square pad keeps its correct orientation relative to the row."""
    at = next((x for x in pad
               if isinstance(x, list) and x and x[0] == Sym("at")), None)
    if at is None:
        return
    cur = float(at[3]) if len(at) > 3 else 0.0
    new = round((cur + fp_rot) % 360.0, 4)
    if len(at) > 3:
        at[3] = new
    else:
        at.append(new)


def _pad_geom(node: list) -> tuple[float, float, float, float] | None:
    """(cx, cy, half_w, half_h) of a (pad ...) node, in footprint-local mm."""
    at = sexpr.find(node, "at")
    size = sexpr.find(node, "size")
    if not (at and len(at) >= 3 and size and len(size) >= 3):
        return None
    hw, hh = float(size[1]) / 2, float(size[2]) / 2
    rot = int(float(at[3])) % 180 if len(at) > 3 else 0
    if rot == 90:
        hw, hh = hh, hw
    return float(at[1]), float(at[2]), hw, hh


def _thermal_via_nets(out: list, pad_nets: dict) -> dict[int, tuple[int, str]]:
    """pad ORDINAL -> inherited (net number, name) for blank no-net pads whose
    center lies inside a netted pad's copper of the same footprint. Returns
    only the inheritances (empty for the common no-thermal-via case)."""
    pads = [n for n in out if isinstance(n, list) and n and n[0] == Sym("pad")]
    netted: list[tuple[float, float, float, float, int, str]] = []
    for n in pads:
        nm = str(n[1]) if len(n) > 1 else ""
        net = pad_nets.get(nm)
        g = _pad_geom(n)
        if net and net[0] > 0 and g is not None:
            netted.append((*g, net[0], net[1]))
    if not netted:
        return {}
    out_map: dict[int, tuple[int, str]] = {}
    for seq, n in enumerate(pads):
        nm = str(n[1]) if len(n) > 1 else ""
        if pad_nets.get(nm, (0, ""))[0] > 0 or nm not in ("", " "):
            continue                       # only blank, currently-no-net pads
        g = _pad_geom(n)
        if g is None:
            continue
        cx, cy, _hw, _hh = g
        for px, py, phw, phh, num, name in netted:
            if abs(cx - px) <= phw and abs(cy - py) <= phh:
                out_map[seq] = (num, name)
                break
    return out_map


def _set_or_add(node: list, kv: list) -> None:
    tag = kv[0]
    for i, x in enumerate(node):
        if isinstance(x, list) and x and x[0] == tag:
            node[i] = kv
            return
    node.append(kv)


def _restamp_uuid(node: list, new: str) -> None:
    for i, x in enumerate(node):
        if isinstance(x, list) and x and x[0] == Sym("uuid"):
            node[i] = [Sym("uuid"), new]
            return
    node.append([Sym("uuid"), new])


def _set_pad_net(pad: list, num: int, name: str) -> None:
    """Insert/replace the pad's (net N "name"). Drop any stale net first; net 0
    (no net) gets NO net node (KiCad treats the absence as the no-net pad)."""
    pad[:] = [x for x in pad
              if not (isinstance(x, list) and x and x[0] == Sym("net"))]
    if num <= 0:
        return
    # net node must precede (pintype ...)/(uuid ...) but KiCad accepts it
    # anywhere inside the pad; append before the uuid for tidiness.
    net_node = [Sym("net"), num, name]
    for i, x in enumerate(pad):
        if isinstance(x, list) and x and x[0] == Sym("uuid"):
            pad.insert(i, net_node)
            return
    pad.append(net_node)


# 4-layer controlled-impedance stackup: Sig / GND / PWR / Sig, JLC04161H-7628
# 1.6 mm (the build schgen/generate/constraints.py already targets).
_FOUR_LAYER = [
    (0, "F.Cu", "signal", "L1 (Sig)"),
    (1, "In1.Cu", "power", "L2 (GND)"),
    (2, "In2.Cu", "power", "L3 (PWR)"),
    (31, "B.Cu", "signal", "L4 (Sig)"),
    (32, "B.Adhes", "user", "B.Adhesive"),
    (33, "F.Adhes", "user", "F.Adhesive"),
    (34, "B.Paste", "user", None),
    (35, "F.Paste", "user", None),
    (36, "B.SilkS", "user", "B.Silkscreen"),
    (37, "F.SilkS", "user", "F.Silkscreen"),
    (38, "B.Mask", "user", None),
    (39, "F.Mask", "user", None),
    (40, "Dwgs.User", "user", "User.Drawings"),
    (41, "Cmts.User", "user", "User.Comments"),
    (42, "Eco1.User", "user", "User.Eco1"),
    (43, "Eco2.User", "user", "User.Eco2"),
    (44, "Edge.Cuts", "user", None),
    (45, "Margin", "user", None),
    (46, "B.CrtYd", "user", "B.Courtyard"),
    (47, "F.CrtYd", "user", "F.Courtyard"),
    (48, "B.Fab", "user", None),
    (49, "F.Fab", "user", None),
]


def _layers_node() -> list:
    node: list = [Sym("layers")]
    for idx, name, ltype, user in _FOUR_LAYER:
        entry = [idx, name, Sym(ltype)]
        if user is not None:
            entry.append(user)
        node.append(entry)
    return node


def _stackup_node() -> list:
    """JLC04161H-7628 1.6 mm 4-layer build. Outer signal layers reference the
    L2 GND plane through one sheet of 7628 prepreg (0.2104 mm, er~4.6) — the
    geometry schgen/generate/constraints.py's diff-pair widths are calculated
    for. L2/L3 core is 1.065 mm; total ~1.6 mm."""
    def cu(name, th):
        return [Sym("layer"), name, [Sym("type"), "copper"],
                [Sym("thickness"), th]]

    def diel(name, dtype, th, er):
        return [Sym("layer"), name, [Sym("type"), dtype],
                [Sym("thickness"), th], [Sym("material"), "FR4"],
                [Sym("epsilon_r"), er], [Sym("loss_tangent"), 0.02]]

    return [Sym("stackup"),
            [Sym("layer"), "F.SilkS", [Sym("type"), "Top Silk Screen"]],
            [Sym("layer"), "F.Paste", [Sym("type"), "Top Solder Paste"]],
            [Sym("layer"), "F.Mask", [Sym("type"), "Top Solder Mask"],
             [Sym("thickness"), 0.01]],
            cu("F.Cu", 0.035),
            diel("dielectric 1", "prepreg", 0.2104, 4.6),
            cu("In1.Cu", 0.0152),
            diel("dielectric 2", "core", 1.065, 4.6),
            cu("In2.Cu", 0.0152),
            diel("dielectric 3", "prepreg", 0.2104, 4.6),
            cu("B.Cu", 0.035),
            [Sym("layer"), "B.Mask", [Sym("type"), "Bottom Solder Mask"],
             [Sym("thickness"), 0.01]],
            [Sym("layer"), "B.Paste", [Sym("type"), "Bottom Solder Paste"]],
            [Sym("layer"), "B.SilkS", [Sym("type"), "Bottom Silk Screen"]],
            [Sym("copper_finish"), "ENIG"],
            [Sym("dielectric_constraints"), Sym("no")]]


def _edge_rect(x0, y0, x1, y1, uid) -> list:
    """Four Edge.Cuts lines forming the board outline rectangle."""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    out: list = []
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        out.append([Sym("gr_line"),
                    [Sym("start"), ax, ay], [Sym("end"), bx, by],
                    [Sym("stroke"), [Sym("width"), 0.1],
                     [Sym("type"), Sym("default")]],
                    [Sym("layer"), "Edge.Cuts"],
                    [Sym("uuid"), uid(f"edge:{i}")]])
    return out


def _som_body_silk(box: tuple[float, float, float, float], uid) -> list:
    """Top-silk outline of the SoM module body (the DF40 mezzanine footprint) on
    the carrier, so an assembler sees exactly where the module lands and that its
    shadow is a passives-only keepout (LAW 6). Drawn at the module-body edge — the
    carrier DF40 receptacles + any under-SoM passives sit inboard of it, so the
    line never crosses a pad. A pin-1 corner chamfer + a small corner label give
    orientation. The user explicitly called out that this outline was missing."""
    x0, y0, x1, y1 = box
    out: list = []
    # body rectangle
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        out.append([Sym("gr_line"),
                    [Sym("start"), round(ax, 3), round(ay, 3)],
                    [Sym("end"), round(bx, 3), round(by, 3)],
                    [Sym("stroke"), [Sym("width"), 0.15],
                     [Sym("type"), Sym("default")]],
                    [Sym("layer"), "F.SilkS"],
                    [Sym("uuid"), uid(f"som-silk:{i}")]])
    # pin-1 / orientation chamfer across the top-left corner
    ch = 3.0
    out.append([Sym("gr_line"),
                [Sym("start"), round(x0, 3), round(y0 + ch, 3)],
                [Sym("end"), round(x0 + ch, 3), round(y0, 3)],
                [Sym("stroke"), [Sym("width"), 0.15],
                 [Sym("type"), Sym("default")]],
                [Sym("layer"), "F.SilkS"],
                [Sym("uuid"), uid("som-silk:ch")]])
    # corner label just OUTSIDE the top-left corner (clear of the module shadow)
    out.append([Sym("gr_text"), "Zynq SoM",
                [Sym("at"), round(x0 + 1.0, 3), round(y0 - 1.2, 3), 0],
                [Sym("layer"), "F.SilkS"],
                [Sym("uuid"), uid("som-silk:label")],
                [Sym("effects"),
                 [Sym("font"), [Sym("size"), 1.4, 1.4], [Sym("thickness"), 0.25]],
                 [Sym("justify"), Sym("left"), Sym("bottom")]]])
    return out


def _som_keepout_zone(box: tuple[float, float, float, float], uid) -> list:
    """A rule-area MARKER over the SoM body on both copper layers (drawn in the
    ratsnest view + KiCad as a hatched region). It is PERMISSIVE: under an SMD
    DF40 mezzanine the shadow is the most power-critical region — it must carry
    full GND/PWR planes, the bottom-side rail-entry decoupling (som_decoupling)
    and its fanout vias right beneath the connector. An old restrictive keepout
    (no tracks/vias/pour) would have starved the SoM of power planes and left the
    under-SoM decoupling unroutable (a LAW-0 open). So everything is allowed; the
    zone only LABELS the mezzanine shadow. Drawn as the rectangle's 4 corners."""
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pts = [Sym("pts")] + [[Sym("xy"), round(px, 3), round(py, 3)]
                          for px, py in corners]
    return [Sym("zone"),
            [Sym("net"), 0], [Sym("net_name"), ""],
            [Sym("layers"), "F.Cu", "B.Cu"],
            [Sym("uuid"), uid("som-keepout")],
            [Sym("name"), "SoM_body_keepout"],
            [Sym("hatch"), Sym("edge"), 0.5],
            [Sym("connect_pads"), [Sym("clearance"), 0]],
            [Sym("min_thickness"), 0.25],
            # PERMISSIVE marker: the SoM shadow is the power-entry region — it
            # carries the GND/PWR planes, the bottom-side rail decoupling and its
            # vias beneath the SMD mezzanine. Everything is allowed; the zone
            # only labels the region (see docstring).
            [Sym("keepout"),
             [Sym("tracks"), Sym("allowed")],
             [Sym("vias"), Sym("allowed")],
             [Sym("pads"), Sym("allowed")],
             [Sym("copperpour"), Sym("allowed")],
             [Sym("footprints"), Sym("allowed")]],
            [Sym("fill"), [Sym("thermal_gap"), 0.5],
             [Sym("thermal_bridge_width"), 0.5]],
            [Sym("polygon"), pts]]


def emit_pcb(model: PcbModel, out_path: Path) -> Path:
    """Serialise the .kicad_pcb."""
    board_uuid = stable_uuid("Zynq_Carrier", "pcb")
    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return stable_uuid(board_uuid, "pcb-id", kind, n)

    doc: list = [
        Sym("kicad_pcb"),
        [Sym("version"), 20241229],
        [Sym("generator"), "schgen"],
        [Sym("generator_version"), "1.0"],
        [Sym("general"), [Sym("thickness"), 1.6],
         [Sym("legacy_teardrops"), Sym("no")]],
        [Sym("paper"), "A3"],
        [Sym("title_block"),
         [Sym("title"), "Zynq Carrier — PCB foundation (schgen)"],
         [Sym("company"), "Zynq SoM Carrier"],
         [Sym("comment"), 1,
          "FOUNDATION: derived outline + SoM-body keep-out + 4L stackup + net "
          "classes + 2-side placement (SoM-mirror mezzanine, per-subsystem "
          "ratsnest bundles). NOT routed — schgen-generated (do not hand-edit)."]],
        _layers_node(),
    ]

    # setup: stackup + a couple of standard knobs. allow_soldermask_bridges_
    # in_footprints=yes accepts the intra-footprint mask apertures shared by a
    # faithful part's EP/thermal-via group (e.g. the TPS26631 EP + its thermal
    # vias) — a footprint-internal property, never a placement defect.
    doc.append([Sym("setup"),
                _stackup_node(),
                [Sym("pad_to_mask_clearance"), 0],
                [Sym("allow_soldermask_bridges_in_footprints"), Sym("yes")],
                [Sym("aux_axis_origin"), ORIGIN_X, ORIGIN_Y]])

    # net table (net 0 first, then by number)
    by_num = sorted(model.net_numbers.items(), key=lambda kv: kv[1])
    for name, num in by_num:
        doc.append([Sym("net"), num, name])

    # board outline rectangle on Edge.Cuts
    x0, y0 = ORIGIN_X, ORIGIN_Y
    x1, y1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    doc.extend(_edge_rect(x0, y0, x1, y1, uid))

    # SoM body keep-out (A1) — nothing routes/places under the mezzanine.
    if model.som_keepout is not None:
        doc.append(_som_keepout_zone(model.som_keepout, uid))

    # SoM module-body OUTLINE on the top silk (LAW 6 documentation) — the
    # rectangle around the DF40 receptacles the user expected to see.
    if model.som_core is not None:
        doc.extend(_som_body_silk(model.som_core, uid))

    # footprints (fixed ref order — determinism)
    for inst in model.insts:
        doc.append(_embed_footprint(inst, uid))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sexpr.dumps(doc) + "\n")
    return out_path


# ---- .kicad_pro net classes + .kicad_dru ----------------------------------------

def _design_settings() -> dict:
    """The COMPLETE KiCad-10 board.design_settings block. KiCad's GUI writes
    every one of these keys on save; emitting them all here means opening the
    project in KiCad changes nothing (build twice -> clean .kicad_pro). Carrier-
    specific rule minimums are kept; all other values are the KiCad 10 defaults
    so the block round-trips byte-stable."""
    return {
        "defaults": {
            "apply_defaults_to_fp_barcodes": False,
            "apply_defaults_to_fp_dimensions": False,
            "apply_defaults_to_fp_fields": False,
            "apply_defaults_to_fp_shapes": False,
            "apply_defaults_to_fp_text": False,
            "board_outline_line_width": 0.1,
            "copper_line_width": 0.2,
            "copper_text_italic": False,
            "copper_text_size_h": 1.5,
            "copper_text_size_v": 1.5,
            "copper_text_thickness": 0.3,
            "copper_text_upright": False,
            "courtyard_line_width": 0.05,
            "dimension_precision": 4,
            "dimension_units": 3,
            "dimensions": {
                "arrow_length": 1270000,
                "extension_offset": 500000,
                "keep_text_aligned": True,
                "suppress_zeroes": False,
                "text_position": 0,
                "units_format": 1,
            },
            "fab_line_width": 0.1,
            "fab_text_italic": False,
            "fab_text_size_h": 1.0,
            "fab_text_size_v": 1.0,
            "fab_text_thickness": 0.15,
            "fab_text_upright": False,
            "other_line_width": 0.15,
            "other_text_italic": False,
            "other_text_size_h": 1.0,
            "other_text_size_v": 1.0,
            "other_text_thickness": 0.15,
            "other_text_upright": False,
            "pads": {"drill": 0.0, "height": 1.8, "width": 1.0},
            "silk_line_width": 0.15,
            "silk_text_italic": False,
            "silk_text_size_h": 1.0,
            "silk_text_size_v": 1.0,
            "silk_text_thickness": 0.15,
            "silk_text_upright": False,
            "zones": {
                "border_display_style": 2,
                "border_hatch_pitch": 0.5,
                "corner_radius": 0.0,
                "corner_smoothing": 0,
                "fill_mode": 0,
                "hatch_gap": 1.5,
                "hatch_orientation": 0.0,
                "hatch_smoothing_level": 0,
                "hatch_smoothing_value": 0.1,
                "hatch_thickness": 1.0,
                "min_clearance": 0.127,
                "min_island_area": 10.0,
                "min_thickness": 0.25,
                "pad_connection": 1,
                "remove_islands": 0,
                "thermal_relief_gap": 0.5,
                "thermal_relief_spoke_width": 0.5,
            },
        },
        "diff_pair_dimensions": [
            {"gap": 0.0, "via_gap": 0.0, "width": 0.0},
            {"gap": 0.2, "via_gap": 0.5, "width": 0.1},
            {"gap": 0.25, "via_gap": 0.5, "width": 0.1},
            {"gap": 0.25, "via_gap": 0.5, "width": 0.104},
            {"gap": 0.3, "via_gap": 0.5, "width": 0.11},
            {"gap": 0.2, "via_gap": 0.5, "width": 0.12},
        ],
        "drc_exclusions": [],
        "meta": {"version": 2},
        "rule_severities": {
            "annular_width": "error",
            "clearance": "error",
            "connection_width": "warning",
            "copper_edge_clearance": "error",
            "copper_sliver": "warning",
            "courtyards_overlap": "error",
            "creepage": "error",
            "diff_pair_gap_out_of_range": "error",
            "diff_pair_uncoupled_length_too_long": "error",
            "drill_out_of_range": "error",
            "duplicate_footprints": "warning",
            "extra_footprint": "warning",
            "footprint": "error",
            "footprint_filters_mismatch": "ignore",
            "footprint_symbol_field_mismatch": "warning",
            "footprint_symbol_mismatch": "warning",
            "footprint_type_mismatch": "ignore",
            "hole_clearance": "error",
            "hole_near_hole": "error",
            "hole_to_hole": "error",
            "holes_co_located": "warning",
            "invalid_outline": "error",
            "isolated_copper": "warning",
            "item_on_disabled_layer": "error",
            "items_not_allowed": "error",
            "length_out_of_range": "error",
            "lib_footprint_issues": "warning",
            "lib_footprint_mismatch": "warning",
            "malformed_courtyard": "error",
            "microvia_drill_out_of_range": "error",
            "mirrored_text_on_front_layer": "warning",
            "missing_courtyard": "ignore",
            "missing_footprint": "warning",
            "missing_tuning_profile": "warning",
            "net_conflict": "warning",
            "nonmirrored_text_on_back_layer": "warning",
            "npth_inside_courtyard": "ignore",
            "padstack": "warning",
            "pth_inside_courtyard": "ignore",
            "shorting_items": "error",
            "silk_edge_clearance": "warning",
            "silk_over_copper": "warning",
            "silk_overlap": "warning",
            "skew_out_of_range": "error",
            "solder_mask_bridge": "error",
            "starved_thermal": "error",
            "text_height": "warning",
            "text_on_edge_cuts": "error",
            "text_thickness": "warning",
            "through_hole_pad_without_hole": "error",
            "too_many_vias": "error",
            "track_angle": "error",
            "track_dangling": "warning",
            "track_not_centered_on_via": "ignore",
            "track_on_post_machined_layer": "error",
            "track_segment_length": "error",
            "track_width": "error",
            "tracks_crossing": "error",
            "tuning_profile_track_geometries": "ignore",
            "unconnected_items": "error",
            "unresolved_variable": "error",
            "via_dangling": "warning",
            "zones_intersect": "error",
        },
        "rules": {
            "max_error": 0.005,
            "min_clearance": 0.09,
            "min_connection": 0.0,
            "min_copper_edge_clearance": 0.3,
            "min_groove_width": 0.0,
            "min_hole_clearance": 0.2,
            "min_hole_to_hole": 0.25,
            "min_microvia_diameter": 0.2,
            "min_microvia_drill": 0.1,
            "min_resolved_spokes": 2,
            "min_silk_clearance": 0.0,
            "min_text_height": 0.8,
            "min_text_thickness": 0.08,
            "min_through_hole_diameter": 0.2,
            "min_track_width": 0.09,
            "min_via_annular_width": 0.05,
            "min_via_diameter": 0.3,
            "solder_mask_clearance": 0.0,
            "solder_mask_min_width": 0.0,
            "solder_mask_to_copper_clearance": 0.0,
            "use_height_for_length_calcs": True,
        },
        "teardrop_options": [{
            "td_onpthpad": True,
            "td_onroundshapesonly": False,
            "td_onsmdpad": True,
            "td_ontrackend": False,
            "td_onvia": True,
        }],
        "teardrop_parameters": [
            {"td_allow_use_two_tracks": True, "td_curve_segcount": 0,
             "td_height_ratio": 1.0, "td_length_ratio": 0.5,
             "td_maxheight": 2.0, "td_maxlen": 1.0, "td_on_pad_in_zone": False,
             "td_target_name": "td_round_shape",
             "td_width_to_size_filter_ratio": 0.9},
            {"td_allow_use_two_tracks": True, "td_curve_segcount": 0,
             "td_height_ratio": 1.0, "td_length_ratio": 0.5,
             "td_maxheight": 2.0, "td_maxlen": 1.0, "td_on_pad_in_zone": False,
             "td_target_name": "td_rect_shape",
             "td_width_to_size_filter_ratio": 0.9},
            {"td_allow_use_two_tracks": True, "td_curve_segcount": 0,
             "td_height_ratio": 1.0, "td_length_ratio": 0.5,
             "td_maxheight": 2.0, "td_maxlen": 1.0, "td_on_pad_in_zone": False,
             "td_target_name": "td_track_end",
             "td_width_to_size_filter_ratio": 0.9},
        ],
        "track_widths": [0.0, 0.1, 0.11, 0.135, 0.15, 0.2, 0.25, 0.3, 0.5],
        "tuning_pattern_settings": {
            "diff_pair_defaults": {
                "corner_radius_percentage": 50, "corner_style": 0,
                "max_amplitude": 1.2, "min_amplitude": 0.1,
                "single_sided": True, "spacing": 0.6},
            "diff_pair_skew_defaults": {
                "corner_radius_percentage": 100, "corner_style": 1,
                "max_amplitude": 1.0, "min_amplitude": 0.05,
                "single_sided": False, "spacing": 0.3},
            "single_track_defaults": {
                "corner_radius_percentage": 50, "corner_style": 0,
                "max_amplitude": 1.0, "min_amplitude": 0.1,
                "single_sided": True, "spacing": 0.4},
        },
        "via_dimensions": [
            {"diameter": 0.0, "drill": 0.0},
            {"diameter": 0.3, "drill": 0.2},
            {"diameter": 0.35, "drill": 0.2},
            {"diameter": 0.4, "drill": 0.25},
            {"diameter": 0.4, "drill": 0.3},
            {"diameter": 0.45, "drill": 0.3},
            {"diameter": 0.55, "drill": 0.4},
        ],
        "zones_allow_external_fillets": True,
    }


def _class_dict(name: str, geo, *, is_power: bool, is_default: bool) -> dict:
    """A KiCad net_settings class dict. Diff classes carry the impedance
    geometry; POWER widens the track; Default is the JLC minimum."""
    track = DEFAULT_TRACK_MM
    clearance = DEFAULT_CLEARANCE_MM
    dp_w = 0.2
    dp_g = 0.2
    if is_power:
        track = POWER_TRACK_MM
        clearance = POWER_CLEARANCE_MM
    elif geo is not None:
        track = geo.width_mm
        dp_w = geo.width_mm
        dp_g = geo.gap_mm
    return {
        "bus_width": 12,
        "clearance": round(clearance, 4),
        "diff_pair_gap": round(dp_g, 4),
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": round(dp_w, 4),
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": name,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "priority": 2147483647 if is_default else (10 if is_power else 5),
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": round(track, 4),
        "tuning_profile": "",
        "via_diameter": 0.6,
        "via_drill": 0.3,
        "wire_width": 6,
    }


def write_project(model: PcbModel, pro_path: Path) -> None:
    """Add net_settings (classes + per-net patterns) to the carrier .kicad_pro,
    preserving the existing keys (ERC severities). The schematic flow owns the
    rest of the project file; this is additive."""
    data: dict = {}
    if pro_path.exists():
        data = json.loads(pro_path.read_text())
    data.setdefault("meta", {"filename": pro_path.name, "version": 3})
    data.setdefault("erc", {"rule_severities": {"pin_not_driven": "warning"}})

    # board.design_settings — the COMPLETE KiCad-10 design-settings block, not a
    # minimal subset. KiCad's GUI rewrites the WHOLE block (defaults / severities
    # / rules / teardrops / track+via+diff-pair tables / tuning / zones) on the
    # first save, so a partial emit shows the project DIRTY after every build/
    # open. Emitting the full block (the values KiCad would write) makes a GUI
    # open a no-op: build twice -> git diff empty on the .kicad_pro. The carrier
    # rules (min_hole_clearance 0.2 for USB-C NPTH posts, min_hole_to_hole 0.25)
    # are kept; every other key matches the KiCad 10 default so it round-trips.
    data["board"] = data.get("board", {})
    data["board"]["design_settings"] = _design_settings()

    classes = [_class_dict("Default", None, is_power=False, is_default=True)]
    for name in sorted(model.classes):
        geo = model.classes[name]
        classes.append(_class_dict(name, geo, is_power=(name == POWER_CLASS),
                                   is_default=False))
    patterns = [{"netclass": cls, "pattern": net}
                for net, cls in sorted(model.netclass_of.items())]
    data["net_settings"] = {
        "classes": classes,
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": patterns,
    }
    # a minimal pcbnew block so KiCad does not complain about a bare project
    data.setdefault("pcbnew", {"last_paths": {}, "page_layout_descr_file": ""})
    pro_path.write_text(json.dumps(data, indent=2) + "\n")


def write_dru(model: PcbModel, dru_path: Path) -> None:
    """A board-level .kicad_dru: default clearance/width minimums + the
    impedance-controlled diff geometry per class + a POWER track-width floor.
    Distinct from the schematic-flow layout_constraints.kicad_dru (which is the
    typed-port table); this one is keyed on the PCB net classes."""
    L = [
        "(version 1)",
        "",
        "# Generated by schgen/generate/pcb.py — board-level design rules for",
        "# the PCB foundation. Stackup: JLCPCB JLC04161H-7628 (4L 1.6mm).",
        "# Net classes + per-net assignment live in the .kicad_pro net_settings;",
        "# these rules pin the geometry KiCad's DRC enforces.",
        "",
        "(rule \"minimum_clearance\"",
        f"  (constraint clearance (min {DEFAULT_CLEARANCE_MM}mm))",
        ")",
        "",
        "(rule \"minimum_track\"",
        f"  (constraint track_width (min {DEFAULT_TRACK_MM}mm))",
        ")",
        "",
        "(rule \"POWER_track\"",
        "  (condition \"A.NetClass == 'POWER'\")",
        f"  (constraint track_width (min {POWER_TRACK_MM}mm) (opt {POWER_TRACK_MM}mm))",
        ")",
        "",
    ]
    for name in sorted(model.classes):
        geo = model.classes[name]
        if geo is None:
            continue
        L += [
            f'(rule "{name}_geometry"',
            f"  (condition \"A.NetClass == '{name}'\")",
            f"  (constraint track_width (min {geo.width_mm}mm) "
            f"(opt {geo.width_mm}mm) (max {geo.width_mm}mm))",
            f"  (constraint diff_pair_gap (min {geo.gap_mm}mm) "
            f"(opt {geo.gap_mm}mm))",
            ")",
            "",
        ]
    dru_path.parent.mkdir(parents=True, exist_ok=True)
    dru_path.write_text("\n".join(L))


# ---- entry point -----------------------------------------------------------------

def generate(*, run_drc: bool = True, two_side: bool = True,
             ratsnest: bool = True) -> dict:
    """Build + write the PCB foundation. Returns a result dict (paths, counts,
    drc verdict, LAW-5 ratsnest gate + images). ``two_side`` (default ON, the
    JLCPCB both-sides assembly policy) pushes decoupling/small passives to the
    bottom; set False for a forced single-side build (everything on top).
    ``ratsnest`` (default ON) emits the per-side ratsnest images + runs the
    LAW-5 placement gate on the SAME model (no rebuild)."""
    model = build_model(two_side=two_side)

    pcb_path = CARRIER / "Zynq_Carrier.kicad_pcb"
    emit_pcb(model, pcb_path)

    pro_path = CARRIER / "Zynq_Carrier.kicad_pro"
    write_project(model, pro_path)

    dru_path = CARRIER / "manufacturing" / "Zynq_Carrier_pcb.kicad_dru"
    write_dru(model, dru_path)

    result = {
        "pcb": pcb_path, "pro": pro_path, "dru": dru_path,
        "board_w": model.board_w, "board_h": model.board_h,
        "placed": model.placed, "total": len(board_parts()),
        "nets": len([n for n in model.net_numbers if n]),
        "classes": sorted(model.classes), "deferred": model.deferred,
        "n_top": model.n_top, "n_bottom": model.n_bottom,
        "two_side": model.two_side, "som_keepout": model.som_keepout,
        "som_core": model.som_core,
        "drc": None, "ratsnest": None, "ratsnest_gate": None,
        "placement_mech": None,
        "connector_model": None, "connector_spacing": None,
    }
    if ratsnest:
        from schgen.generate import ratsnest as rn_mod
        from schgen.verify import ratsnest_gate
        from schgen.verify import placement_mech
        from schgen.verify import connector_model_gate
        from schgen.verify import connector_spacing_gate
        result["ratsnest"] = rn_mod.generate(model)
        result["ratsnest_gate"] = ratsnest_gate.check(model)
        # LAW-6 mechanical/use-case gate — runs on the SAME placed model (no
        # rebuild) so its connector-edge/orientation + SoM-keepout verdict is
        # exactly the board just emitted.
        result["placement_mech"] = placement_mech.check(model)
        # LAW-6 connector hardening (catch the recurring orientation + spacing
        # bug classes the other gates miss): 3D-model rotate must not flip the
        # rendered opening vs the pads, and simultaneous-mate cable connectors
        # (HDMI TX+RX) need an overmold gap.
        result["connector_model"] = connector_model_gate.check(model)
        result["connector_spacing"] = connector_spacing_gate.check(model)
    if run_drc:
        result["drc"] = run_pcb_drc(pcb_path)
    return result


def run_pcb_drc(pcb_path: Path) -> dict:
    """Run kicad-cli pcb drc; classify violations. Unrouted-net violations are
    expected (no routing); clearance/overlap errors are not."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="schgen_drc_") as td:
        rpt = Path(td) / "drc.json"
        proc = subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json",
             "--severity-error", "--severity-warning",
             "-o", str(rpt), str(pcb_path)],
            capture_output=True, text=True)
        data = {}
        if rpt.exists():
            try:
                data = json.loads(rpt.read_text())
            except Exception:  # noqa: BLE001
                data = {}
    viols = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])
    by_type: dict[str, int] = {}
    other: list[str] = []
    for v in viols:
        t = v.get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1
        if t not in ("silk_overlap", "silk_over_copper",
                     "courtyards_overlap", "footprint_type_mismatch"):
            # collect a few non-silk violation descriptions for the report
            if len(other) < 12:
                other.append(t)
    return {
        "returncode": proc.returncode,
        "n_violations": len(viols),
        "n_unconnected": len(unconnected),
        "by_type": by_type,
        "other_sample": other,
        "stderr": proc.stderr[-400:],
    }


def cmd_pcb(args: argparse.Namespace) -> int:
    res = generate(run_drc=not args.no_drc,
                   two_side=not getattr(args, "single_side", False))
    print(f"PCB: {res['pcb'].relative_to(REPO_ROOT)} "
          f"({res['board_w']:g} x {res['board_h']:g} mm outline, "
          f"4-layer Sig/GND/PWR/Sig stackup)")
    side = (f"2-side (top {res['n_top']} / bottom {res['n_bottom']})"
            if res["two_side"] else "single-side (all top)")
    print(f"  footprints placed: {res['placed']}/{res['total']}  "
          f"nets: {res['nets']}  net classes: {len(res['classes'])} "
          f"({', '.join(res['classes'])})")
    print(f"  assembly: {side}")
    print(f"  net classes + patterns -> {res['pro'].relative_to(REPO_ROOT)}")
    print(f"  design rules -> {res['dru'].relative_to(REPO_ROOT)}")
    if res["deferred"]:
        print(f"  DEFERRED ({len(res['deferred'])} footprints unresolved):")
        for d in res["deferred"]:
            print(f"    {d}")
    drc = res["drc"]
    if drc is not None:
        print(f"  DRC: {drc['n_violations']} violations, "
              f"{drc['n_unconnected']} unconnected (unrouted — expected)")
        for t, n in sorted(drc["by_type"].items()):
            print(f"    {t}: {n}")
    return 0


if __name__ == "__main__":
    import sys
    p = argparse.ArgumentParser(prog="schgen pcb")
    p.add_argument("--no-drc", action="store_true")
    p.add_argument("--single-side", action="store_true",
                   help="force all footprints on top (default: 2-side, "
                        "decoupling/small passives on the bottom)")
    sys.exit(cmd_pcb(p.parse_args()))
