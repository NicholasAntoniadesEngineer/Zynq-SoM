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
from dataclasses import dataclass
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
SOM_HALO_PCB = 6.0       # routing/escape halo reserved around the SoM body
EDGE_BAND_PCB = 18.0     # nominal connector band each side (board-aspect seed)
ZONE_FILL = 0.42         # zone-area packing efficiency for the seed board size
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
PLACE_CLEAR = 2.0
EDGE_CLEAR = 2.0
ZONE_GAP = 2.5             # gap between two adjacent subsystem zones
ZONE_PAD = 1.0            # padding inside a subsystem zone around its parts


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

    # floorplan plan (block positions) + net classes
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    link_result = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    plan = fp.build_plan(sheets, link_result, regs)
    classes, netclass_of = _net_classes(sheets)

    # footprint bboxes + per-sheet ref grouping
    refs_by_sheet: dict[str, list[str]] = {}
    bbox_of: dict[str, tuple[float, float, float, float]] = {}
    deferred: list[str] = []
    resolvable: dict[str, Path] = {}
    for ref, (sheet, footprint, _value, _lib) in parts.items():
        mod = resolve_mod(footprint)
        if mod is None:
            deferred.append(f"{ref} ({sheet}): footprint {footprint!r} "
                            f"not found in parts/ or the KiCad std libs")
            continue
        resolvable[ref] = mod
        bbox_of[ref] = _footprint_bbox(mod)
        refs_by_sheet.setdefault(sheet, []).append(ref)

    # 2-side classification: decoupling caps + small passives -> bottom.
    decoupling = _decoupling_caps(nets)
    side_of: dict[str, str] = {}
    for ref in resolvable:
        _sheet, _ftp, _val, lib = parts[ref]
        side_of[ref] = _classify_side(ref, lib, bbox_of[ref],
                                      decoupling, two_side)

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

    mh_refs = sorted(r for r, (_s, _fp, _v, lib) in parts.items()
                     if lib.startswith("Mechanical:MountingHole"))
    mh_set = set(mh_refs)

    # ---- STEP 1: size every subsystem ZONE from its REAL packed footprints ---
    # For each non-SoM sheet, shelf-pack its TOP parts and (separately) its
    # BOTTOM parts; the zone must hold the LARGER of the two (top and bottom
    # overlay on the same XY area). The packers return part offsets relative to
    # the zone origin AND the exact box, so the zone is sized to FIT — there is
    # no overflow, no off-board shelf. Aspect: a target width ~ sqrt of the
    # per-side area scaled by the SoM aspect keeps zones squarish.
    #
    # MOUNTING HOLES are NOT zone-packed: like the SoM receptacles they are
    # FIXED-position parts (corner-forced to the four board corners in STEP 3).
    # Packing a hole into its sheet's zone would give it a zone-relative offset
    # that STEP 3's subsystem loop then writes over the corner position with —
    # so the holes must be excluded from the zone entirely. A sheet that holds
    # ONLY holes (the carrier 'mechanical' fab-art sheet) thus contributes no
    # zone at all; its holes become their own corner-forced cluster.
    side_refs: dict[str, dict[str, list[str]]] = {}
    for sheet in refs_by_sheet:
        if sheet.startswith("som_j"):
            continue
        zoned = [r for r in refs_by_sheet[sheet] if r not in mh_set]
        if not zoned:
            continue          # sheet is mounting-holes-only -> no zone
        side_refs[sheet] = {"top": [], "bottom": []}
        for r in zoned:
            side_refs[sheet][side_of[r]].append(r)

    zone_box: dict[str, tuple[float, float]] = {}            # sheet -> (w,h)
    top_off: dict[str, dict[str, tuple[float, float]]] = {}  # sheet -> {ref:(x,y)}
    bot_off: dict[str, dict[str, tuple[float, float]]] = {}

    def _eff_bbox(ref: str, side: str) -> tuple[float, float, float, float]:
        """The footprint's on-board local bbox. A BOTTOM part is flipped to
        B.Cu, which mirrors its geometry about the origin's X axis (KiCad's
        F->B convention), so its courtyard occupies the X-mirror of the top
        bbox — pack/derive/gate must all use this mirrored box for a bottom
        part or its left edge could land off-zone/off-board."""
        bx0, by0, bx1, by1 = bbox_of[ref]
        if side == "bottom":
            return (-bx1, by0, -bx0, by1)
        return (bx0, by0, bx1, by1)

    def _items(refs, side):
        return [(r, _eff_bbox(r, side), 0.0) for r in refs]

    for sheet in sorted(side_refs):
        tot_area = sum((bbox_of[r][2] - bbox_of[r][0] + PLACE_CLEAR) *
                       (bbox_of[r][3] - bbox_of[r][1] + PLACE_CLEAR)
                       for r in refs_by_sheet[sheet] if r not in mh_set)
        target_w = max(8.0, (tot_area * 0.62) ** 0.5)   # squarish per-side fill
        t_off, tw, th = _shelf_pack(_items(side_refs[sheet]["top"], "top"),
                                    target_w)
        # blockers: every TOP through-hole part's top-frame haloed box (copper
        # on all layers) — the bottom pack must keep its SMD parts out from
        # under them (a bottom pad there shorts to the THT pad).
        blockers: list[tuple[float, float, float, float]] = []
        for r in side_refs[sheet]["top"]:
            if not has_thru_pads(resolvable[r]):
                continue
            ox, oy = t_off[r]
            bx0, by0, bx1, by1 = bbox_of[r]
            blockers.append((ox + bx0 - PLACE_CLEAR / 2,
                             oy + by0 - PLACE_CLEAR / 2,
                             ox + bx1 + PLACE_CLEAR / 2,
                             oy + by1 + PLACE_CLEAR / 2))
        b_off, bw, bh = _shelf_pack(_items(side_refs[sheet]["bottom"],
                                           "bottom"), target_w, blockers)
        top_off[sheet] = t_off
        bot_off[sheet] = b_off
        zone_box[sheet] = (round(max(tw, bw), 4), round(max(th, bh), 4))

    # ---- STEP 2: lay the zones out around a centered SoM keep-out ------------
    # The SoM region (J1/J2/J3 extent + a routing halo) is reserved in the
    # board center; subsystem zones tile the free area in a deterministic
    # row-major shelf, and the BOARD GROWS until every zone + the SoM region +
    # the 4 corner mounting holes + a perimeter keepout fit. No part is ever
    # placed off-board: the outline is DERIVED from the packed extents.
    som_w = som.w + 2 * SOM_HALO_PCB
    som_h = som.h + 2 * SOM_HALO_PCB

    # ---- subsystem AFFINITY: which sheets share nets (placement attraction) ---
    # For every real net, the sheets it touches form a clique; accumulate a
    # pairwise weight inversely proportional to the net's fan-out (a 2-sheet
    # SIGNAL net pulls hard; a board-wide rail/GND across 30 sheets barely pulls
    # — it is unavoidably long no matter where blocks sit, so it must not drive
    # placement). The SoM (som_j*) is the central anchor: a sheet's pull toward
    # the SoM is folded into the centroid via the fixed SoM center.
    sheets_of_net: dict[str, set[str]] = {}
    for nname, pins in nets.items():
        if not nname or nname.startswith("unconnected-"):
            continue
        ss = {parts[pr.ref][0] for pr in pins
              if pr.ref in parts and not pr.ref.startswith("#")}
        if len(ss) >= 2:
            sheets_of_net[nname] = ss
    affinity: dict[str, dict[str, float]] = {}
    som_pull: dict[str, float] = {}
    for nname, ss in sheets_of_net.items():
        k = len(ss)
        w = 1.0 / (k * (k - 1) / 2)        # split a unit of pull over the clique
        non_som = sorted(s for s in ss if not s.startswith("som_j"))
        has_som = any(s.startswith("som_j") for s in ss)
        for i, a in enumerate(non_som):
            if has_som:
                som_pull[a] = som_pull.get(a, 0.0) + w
            for b in non_som[i + 1:]:
                affinity.setdefault(a, {})[b] = \
                    affinity.get(a, {}).get(b, 0.0) + w
                affinity.setdefault(b, {})[a] = \
                    affinity.get(b, {}).get(a, 0.0) + w

    # placement order: most-connected first (largest total affinity), then area,
    # then name — so the hub subsystems anchor near the SoM and pull the rest in.
    def _conn(s: str) -> float:
        return sum(affinity.get(s, {}).values()) + 3.0 * som_pull.get(s, 0.0)
    zone_order = sorted(zone_box, key=lambda s: (-_conn(s),
                                                 -(zone_box[s][0] *
                                                   zone_box[s][1]), s))

    def _layout(board_w: float, board_h: float):
        """Place the SoM region (centered) + every subsystem zone so that
        net-sharing subsystems sit NEAR each other (short cross-block airwires)
        AND every zone fits inside the interior (perimeter keepout + corner-hole
        insets). Greedy + deterministic: zones in affinity order, each dropped at
        the free slot whose center is NEAREST the weighted centroid of its
        already-placed neighbors (the SoM center is the seed pull). No part is
        ever placed off-board. Returns (zone_origin, som_origin) or None."""
        x_lo = PERIM + MH_KEEPOUT
        x_hi = board_w - PERIM - MH_KEEPOUT
        y_lo = PERIM + MH_KEEPOUT
        y_hi = board_h - PERIM - MH_KEEPOUT
        sx = round((board_w - som_w) / 2, 4)
        sy = round((board_h - som_h) / 2, 4)
        som_cx, som_cy = sx + som_w / 2, sy + som_h / 2
        som_rect = (sx, sy, sx + som_w, sy + som_h)
        placed_rects: list[tuple[float, float, float, float]] = [som_rect]
        centers: dict[str, tuple[float, float]] = {}

        def collide(x0, y0, x1, y1):
            if x0 < x_lo or y0 < y_lo or x1 > x_hi or y1 > y_hi:
                return True
            for rx0, ry0, rx1, ry1 in placed_rects:
                if not (x1 + ZONE_GAP <= rx0 or rx1 + ZONE_GAP <= x0 or
                        y1 + ZONE_GAP <= ry0 or ry1 + ZONE_GAP <= y0):
                    return True
            return False

        zorigin: dict[str, tuple[float, float]] = {}
        for sheet in zone_order:
            zw, zh = zone_box[sheet]
            # weighted anchor = SoM-pull + placed-neighbour-pull centroid
            wsum = max(som_pull.get(sheet, 0.0), 0.1)
            ax = som_pull.get(sheet, 0.1) * som_cx
            ay = som_pull.get(sheet, 0.1) * som_cy
            for nb, w in affinity.get(sheet, {}).items():
                if nb in centers:
                    cxn, cyn = centers[nb]
                    ax += w * cxn
                    ay += w * cyn
                    wsum += w
            ax /= wsum
            ay /= wsum
            # deterministic raster of candidate slots; pick the one whose center
            # is nearest the anchor (ties -> top-left for stability).
            best = None
            best_key = None
            y = y_lo
            while y + zh <= y_hi + 1e-6:
                x = x_lo
                while x + zw <= x_hi + 1e-6:
                    if not collide(x, y, x + zw, y + zh):
                        ccx, ccy = x + zw / 2, y + zh / 2
                        d = abs(ccx - ax) + abs(ccy - ay)
                        key = (round(d, 3), round(y, 3), round(x, 3))
                        if best_key is None or key < best_key:
                            best_key = key
                            best = (round(x, 4), round(y, 4))
                    x += ZONE_STEP
                y += ZONE_STEP
            if best is None:
                return None
            zorigin[sheet] = best
            placed_rects.append((best[0], best[1], best[0] + zw, best[1] + zh))
            centers[sheet] = (best[0] + zw / 2, best[1] + zh / 2)
        return zorigin, (sx, sy)

    # grow the board (keep the SoM aspect) until _layout succeeds
    total_zone_area = sum(w * h for (w, h) in zone_box.values()) + som_w * som_h
    aspect = (som_w + 2 * EDGE_BAND_PCB) / (som_h + 2 * EDGE_BAND_PCB)
    base = (total_zone_area / ZONE_FILL) ** 0.5
    bw0 = max(som_w + 2 * (PERIM + MH_KEEPOUT + EDGE_BAND_PCB),
              base * aspect ** 0.5)
    bh0 = max(som_h + 2 * (PERIM + MH_KEEPOUT + EDGE_BAND_PCB),
              base / aspect ** 0.5)
    board_w = board_h = None
    layout = None
    grow = 0
    while layout is None and grow < 400:
        cand_w = _snap_up(bw0 + grow * OUTLINE_GROW)
        cand_h = _snap_up(bh0 + grow * OUTLINE_GROW * (bh0 / bw0))
        layout = _layout(cand_w, cand_h)
        if layout is not None:
            board_w, board_h = cand_w, cand_h
            break
        grow += 1
    if layout is None:
        raise RuntimeError("pcb: could not fit every subsystem zone on a "
                           "grown board — packing is broken")
    zorigin, (sx_off, sy_off) = layout

    # SoM keep-out (centered) + SoM mezzanine J positions, in the grown board
    halo = 1.0
    j_halo = SOM_HALO_PCB
    keepout = (sx_off + SOM_HALO_PCB - halo, sy_off + SOM_HALO_PCB - halo,
               sx_off + SOM_HALO_PCB + som.w + halo,
               sy_off + SOM_HALO_PCB + som.h + halo)
    som_view = {jn: (sx_off + j_halo + sx, sy_off + j_halo + sy)
                for jn, (sx, sy) in som_rel.items()}

    # ---- STEP 3: final origins (board frame) for every footprint ------------
    pos: dict[str, tuple[float, float]] = {}
    # mounting holes -> the 4 corners of the GROWN board
    corners = [(MH_INSET, MH_INSET),
               (board_w - MH_INSET, MH_INSET),
               (board_w - MH_INSET, board_h - MH_INSET),
               (MH_INSET, board_h - MH_INSET)]
    for i, ref in enumerate(mh_refs):
        pos[ref] = corners[i % 4]
    # SoM receptacles
    for ref, jname in som_j_refs.items():
        pos[ref] = som_view[jname]
    # subsystem footprints: zone origin + per-part packed offset
    for sheet in zorigin:
        zx, zy = zorigin[sheet]
        for r, (dx, dy) in top_off[sheet].items():
            pos[r] = (zx + dx, zy + dy)
        for r, (dx, dy) in bot_off[sheet].items():
            pos[r] = (zx + dx, zy + dy)

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
        insts.append(FootprintInst(
            ref=ref, value=value, footprint=footprint,
            x=_gridify(ORIGIN_X + bx), y=_gridify(ORIGIN_Y + by),
            rotation=fixed_rot.get(ref, 0.0), pad_nets=pad_nets,
            mod_path=mod, sheet=sheet, side=side))
        placed += 1
        if side == "bottom":
            n_bottom += 1
        else:
            n_top += 1

    kx0, ky0, kx1, ky1 = keepout
    return PcbModel(
        board_w=board_w, board_h=board_h, insts=insts,
        net_numbers=net_numbers, netclass_of=netclass_of, classes=classes,
        placed=placed, deferred=deferred,
        som_keepout=(ORIGIN_X + kx0, ORIGIN_Y + ky0,
                     ORIGIN_X + kx1, ORIGIN_Y + ky1),
        n_top=n_top, n_bottom=n_bottom, two_side=two_side)


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


def _som_keepout_zone(box: tuple[float, float, float, float], uid) -> list:
    """A rule-area (keep-out) zone over the SoM body on both copper layers, so
    the layout tool keeps tracks/vias/copper out from under the mezzanine stack
    (the receptacles + SoM board occupy that volume). It is a planning aid, not
    a DRC error source — KiCad keep-outs only constrain routing/copper, which
    this unrouted foundation has none of. Drawn as the rectangle's 4 corners."""
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
            # disallow ROUTING copper only (tracks/vias/pour). Pads and
            # footprints are ALLOWED: the SoM mezzanine receptacles (J1/J2/J3)
            # legitimately sit inside this area — the keep-out keeps the layout
            # tool from routing carrier signals THROUGH the SoM shadow, it does
            # not forbid the receptacle pads themselves.
            [Sym("keepout"),
             [Sym("tracks"), Sym("not_allowed")],
             [Sym("vias"), Sym("not_allowed")],
             [Sym("pads"), Sym("allowed")],
             [Sym("copperpour"), Sym("not_allowed")],
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
        "drc": None, "ratsnest": None, "ratsnest_gate": None,
    }
    if ratsnest:
        from schgen.generate import ratsnest as rn_mod
        from schgen.verify import ratsnest_gate
        result["ratsnest"] = rn_mod.generate(model)
        result["ratsnest_gate"] = ratsnest_gate.check(model)
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
