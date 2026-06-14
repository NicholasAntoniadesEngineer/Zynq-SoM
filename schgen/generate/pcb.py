"""Emit an openable KiCad PCB FOUNDATION (Stream D) — NOT autorouted.

``schgen pcb`` (also run by ``schgen board``) writes
``carrier/Zynq_Carrier.kicad_pcb`` + ``carrier/manufacturing/
Zynq_Carrier_pcb.kicad_dru``: a real, openable, DRC-clean (unrouted-net
violations only) PCB seeded from the SAME netlists/floorplan the schematic
flow uses. It does FOUR things, every number DERIVED:

1. **Board OUTLINE** on Edge.Cuts — a rectangle sized from the floorplan
   suggestion (SoM mezzanine footprint + the edge connectors), with the 4 M3
   mounting holes (already netted to CHASSIS_GND in the model) forced to the
   board corners.
2. **A FORCED 4-LAYER controlled-impedance stackup** (Sig / GND / PWR / Sig),
   the JLC04161H-7628 1.6 mm build the constraints already target — written
   into both the ``(layers)`` table and the ``(setup (stackup ...))`` block.
3. **NET CLASSES + a .kicad_dru** — default clearances/widths, the
   impedance-controlled classes for the high-speed nets (TMDS / USB2 / RGMII-
   class diff pairs) and a POWER class for the rails, with per-net
   ``netclass_patterns`` so KiCad assigns every high-speed/rail net to its
   class on open. Reuses ``schgen/generate/constraints.py`` geometry.
4. **FOOTPRINT PLACEMENT** — every BOM footprint embedded into the .kicad_pcb
   at a floorplan-derived position, with its pads bound to the schematic nets
   (the merged board netlist KiCad itself extracts from the root sheet) so the
   ratsnest is correct. NO routing.

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
# The outline is DERIVED from the floorplan suggestion (itself derived from the
# SoM mezzanine + the edge connectors). The floorplan owns BOARD_W/BOARD_H and
# the to-scale block plan; the PCB places parts inside those blocks. The
# coordinate frame is shifted by ORIGIN_OFF so the board sits in positive KiCad
# page space (KiCad's drawing sheet origin is top-left, +y down — same as the
# floorplan's board frame).
ORIGIN_X = 25.0          # board top-left in KiCad page mm
ORIGIN_Y = 25.0
MH_INSET = 5.0          # M3 hole center inset from each board corner
GRID = 1.27             # placement snap grid (mm)


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


# ---- footprint resolution + parsing ----------------------------------------------

_PAD_RE = re.compile(r'\(pad\s+"([^"]+)"')


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
    match the merged netlist's refs exactly."""
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.generate.board import _renamed_ref
    out: dict[str, tuple[str, str, str, str]] = {}
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    for i, sc in enumerate(sheets, start=1):
        for ref, part in sc.circuit.parts.items():
            bref = _renamed_ref(ref, i, sheet=sc.name)
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


class _Occ:
    """Non-overlapping shelf packer with a fixed clearance halo around every
    footprint's true bbox. Deterministic: a left-to-right, top-to-bottom shelf
    fill inside the board, reserving the SoM keep-out and the corner mounting
    holes. Parts that do not fit the board spill into a staging strip below it.

    Footprints carry an asymmetric bbox (bx0,by0,bx1,by1) RELATIVE to their
    origin; the packer returns the ORIGIN position that lands the haloed bbox
    in the next free slot, so the emitted (at ...) is correct and the
    courtyards never collide."""

    def __init__(self, board_w: float, board_h: float,
                 reserved: list[tuple[float, float, float, float]]):
        self.bw = board_w
        self.bh = board_h
        self.rects: list[tuple[float, float, float, float]] = list(reserved)
        self.cx = EDGE_CLEAR
        self.cy = EDGE_CLEAR
        self.row_h = 0.0
        self.staging_y = board_h + 12.0     # below-board staging origin
        self.staging_cx = EDGE_CLEAR
        self.staging_row_h = 0.0

    def _free(self, x0, y0, x1, y1) -> bool:
        for rx0, ry0, rx1, ry1 in self.rects:
            if not (x1 <= rx0 or rx1 <= x0 or y1 <= ry0 or ry1 <= y0):
                return False
        return True

    @staticmethod
    def _wh(bbox) -> tuple[float, float]:
        bx0, by0, bx1, by1 = bbox
        return (bx1 - bx0) + PLACE_CLEAR, (by1 - by0) + PLACE_CLEAR

    def _origin(self, slot_x, slot_y, bbox) -> tuple[float, float]:
        """Origin position so the haloed bbox top-left sits at (slot_x,slot_y)."""
        bx0, by0, _bx1, _by1 = bbox
        return (slot_x + PLACE_CLEAR / 2 - bx0, slot_y + PLACE_CLEAR / 2 - by0)

    def _scan_row(self, bbox) -> tuple[float, float] | None:
        hw, hh = self._wh(bbox)
        guard = 0
        while self.cy + hh <= self.bh - EDGE_CLEAR and guard < 200000:
            guard += 1
            if self.cx + hw > self.bw - EDGE_CLEAR:
                self.cx = EDGE_CLEAR
                self.cy += self.row_h
                self.row_h = 0.0
                continue
            x0, y0 = self.cx, self.cy
            if self._free(x0, y0, x0 + hw, y0 + hh):
                self.cx = x0 + hw
                self.row_h = max(self.row_h, hh)
                self.rects.append((x0, y0, x0 + hw, y0 + hh))
                return self._origin(x0, y0, bbox)
            self.cx += GRID
        return None

    def _stage(self, bbox) -> tuple[float, float]:
        hw, hh = self._wh(bbox)
        max_w = self.bw * 1.7
        if self.staging_cx + hw > max_w:
            self.staging_cx = EDGE_CLEAR
            self.staging_y += self.staging_row_h
            self.staging_row_h = 0.0
        x0, y0 = self.staging_cx, self.staging_y
        self.staging_cx = x0 + hw
        self.staging_row_h = max(self.staging_row_h, hh)
        return self._origin(x0, y0, bbox)

    def place(self, bbox) -> tuple[float, float]:
        slot = self._scan_row(bbox)
        return slot if slot is not None else self._stage(bbox)

    def reserve_origin(self, ox, oy, bbox) -> None:
        """Mark a fixed-origin footprint's haloed bbox as occupied."""
        bx0, by0, bx1, by1 = bbox
        h = PLACE_CLEAR / 2
        self.rects.append((ox + bx0 - h, oy + by0 - h,
                           ox + bx1 + h, oy + by1 + h))


# ---- the model build -------------------------------------------------------------

def build_model() -> PcbModel:
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

    def _area(ref: str) -> float:
        bx0, by0, bx1, by1 = bbox_of[ref]
        return (bx1 - bx0) * (by1 - by0)

    # ---- fixed positions: corner mounting holes + SoM DF40 mezzanine --------
    # mounting holes -> board corners (CHASSIS_GND, model H1..H4)
    mh_refs = sorted(r for r, (_s, _fp, _v, lib) in parts.items()
                     if lib.startswith("Mechanical:MountingHole"))
    corners = [(MH_INSET, MH_INSET),
               (fp.BOARD_W - MH_INSET, MH_INSET),
               (fp.BOARD_W - MH_INSET, fp.BOARD_H - MH_INSET),
               (MH_INSET, fp.BOARD_H - MH_INSET)]
    fixed: dict[str, tuple[float, float]] = {}
    for i, ref in enumerate(mh_refs):
        fixed[ref] = corners[i % 4]

    # SoM DF40 connectors at the extracted SoM footprint positions (centered).
    som = plan.som
    bx_off = (fp.BOARD_W - som.w) / 2
    by_off = (fp.BOARD_H - som.h) / 2
    som_view = {j.ref: (bx_off + j.x, by_off + j.y) for j in som.js}
    som_ref_of: dict[str, str] = {}     # board-ref -> J1/J2/J3
    for ref, (sheet, _fp, _v, _lib) in parts.items():
        if ref not in resolvable or not sheet.startswith("som_j"):
            continue
        m = re.match(r"som_j(\d)", sheet)
        if m and ref.startswith("J") and f"J{m.group(1)}" in som_view:
            jname = f"J{m.group(1)}"
            som_ref_of[ref] = jname
            fixed[ref] = som_view[jname]

    # ---- non-overlapping shelf pack of everything else ----------------------
    # reserve the SoM keep-out (its full footprint area) + every fixed part.
    reserved: list[tuple[float, float, float, float]] = []
    sx0, sy0 = bx_off - 1.0, by_off - 1.0
    reserved.append((sx0, sy0, sx0 + som.w + 2.0, sy0 + som.h + 2.0))
    occ = _Occ(fp.BOARD_W, fp.BOARD_H, reserved)
    for ref, (ox, oy) in fixed.items():
        occ.reserve_origin(ox, oy, bbox_of[ref])

    pos: dict[str, tuple[float, float]] = dict(fixed)
    # pack sheet-by-sheet (locality), largest-first within a sheet; sheets in a
    # stable order — the floorplan's edge sheets first, then interior, both
    # alphabetical, so output is deterministic.
    def _sheet_key(name: str) -> tuple[int, str]:
        return (0 if name.startswith("som_j") else 1, name)
    for sheet in sorted(refs_by_sheet, key=_sheet_key):
        refs = sorted(refs_by_sheet[sheet], key=lambda r: (-_area(r), r))
        for ref in refs:
            if ref in fixed:
                continue
            pos[ref] = occ.place(bbox_of[ref])

    insts: list[FootprintInst] = []
    placed = 0
    for ref in sorted(resolvable):
        sheet, footprint, value, lib = parts[ref]
        mod = resolvable[ref]
        bx, by = pos[ref]
        # pad -> net
        pad_nets: dict[str, tuple[int, str]] = {}
        for pad in pad_names(mod):
            pad_nets[pad] = pin_net.get((ref, pad), (0, ""))
        insts.append(FootprintInst(
            ref=ref, value=value, footprint=footprint,
            x=_gridify(ORIGIN_X + bx), y=_gridify(ORIGIN_Y + by),
            rotation=0.0, pad_nets=pad_nets, mod_path=mod, sheet=sheet))
        placed += 1

    return PcbModel(
        board_w=fp.BOARD_W, board_h=fp.BOARD_H, insts=insts,
        net_numbers=net_numbers, netclass_of=netclass_of, classes=classes,
        placed=placed, deferred=deferred)


# ---- emission --------------------------------------------------------------------

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
            _restamp_uuid(node, uid(f"fp:{inst.ref}:pad:{pad_seq}"))
            pad_seq += 1
        elif head in (Sym("fp_text"), Sym("fp_line"), Sym("fp_rect"),
                      Sym("fp_circle"), Sym("fp_arc"), Sym("fp_poly")):
            _restamp_uuid(node, uid(f"fp:{inst.ref}:gfx:{pad_seq}:{prop_seq}"))
    return out


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
          "FOUNDATION: outline + 4L stackup + net classes + placed "
          "footprints. NOT routed — generated by schgen (do not hand-edit)."]],
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

    # footprints (fixed ref order — determinism)
    for inst in model.insts:
        doc.append(_embed_footprint(inst, uid))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sexpr.dumps(doc) + "\n")
    return out_path


# ---- .kicad_pro net classes + .kicad_dru ----------------------------------------

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

    # board.design_settings.rules — the manufacturable JLC constraint set (the
    # SAME values the SoM project uses). These are the board-wide minimums
    # KiCad's DRC enforces; the per-class geometry lives in net_settings +
    # the .kicad_dru. min_hole_clearance 0.2 mm accepts a faithful connector's
    # NPTH alignment posts (USB-C: 0.2436 mm to the shield pad), an intrinsic
    # footprint property, not a placement defect.
    data["board"] = data.get("board", {})
    data["board"]["design_settings"] = {
        "rule_severities": {
            "copper_edge_clearance": "error",
            "hole_clearance": "error",
            "hole_to_hole": "error",
            "silk_edge_clearance": "warning",
            "silk_overlap": "warning",
            "text_height": "warning",
        },
        "rules": {
            "max_error": 0.005,
            "min_clearance": 0.09,
            "min_connection": 0.0,
            "min_copper_edge_clearance": 0.3,
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
            "use_height_for_length_calcs": True,
        },
    }

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

def generate(*, run_drc: bool = True) -> dict:
    """Build + write the PCB foundation. Returns a result dict (paths, counts,
    drc verdict)."""
    model = build_model()

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
        "drc": None,
    }
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
    res = generate(run_drc=not args.no_drc)
    print(f"PCB: {res['pcb'].relative_to(REPO_ROOT)} "
          f"({res['board_w']:g} x {res['board_h']:g} mm outline, "
          f"4-layer Sig/GND/PWR/Sig stackup)")
    print(f"  footprints placed: {res['placed']}/{res['total']}  "
          f"nets: {res['nets']}  net classes: {len(res['classes'])} "
          f"({', '.join(res['classes'])})")
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
    sys.exit(cmd_pcb(p.parse_args()))
