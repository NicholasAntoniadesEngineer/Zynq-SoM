"""Carrier floorplan SUGGESTION — generated from the netlists, to scale.

``schgen floorplan`` (also run by ``schgen board``) writes
``carrier/docs/FLOORPLAN.svg`` + ``carrier/docs/FLOORPLAN.md``: a 2D
placement suggestion for the PCB layout's first hour. Every number is
DERIVED, never invented:

  - SoM outline + DF40 J1/J2/J3 mezzanine positions: parsed live from
    ``som/Zynq_SoM.kicad_pcb`` (Edge.Cuts bbox + footprint ``at`` + pad
    extents), mirrored to the carrier-top view;
  - block sizes: per-part courtyard boxes (``parts/<MPN>/<MPN>.kicad_mod``
    F.CrtYd bbox; KiCad-standard footprints from the dimensions encoded in
    their own names) plus a routing factor on small parts;
  - edge pinning + zone affinity: connector parts found in each sheet's
    netlist + the linker's J1/J2/J3 bindings (including author-declared
    ``expect=`` deferrals naming their target connector);
  - electrical notes: schgen/constraints.py JLC04161H-7628 geometry, the
    power-tree analysis (regulator stages -> thermal), typed-port levels
    (the 1.8V SDIO island).

SUGGESTION, NOT CONSTRAINT: PLAN.md round 2 leaves the form factor free
("connector-driven ~120x100 class expected; user owns outline"). The SVG is
one self-consistent, to-scale starting point; the MD explains every WHY so
each decision can be overruled deliberately. Deterministic output: same
inputs -> byte-identical files (no timestamps).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from heapq import heappop, heappush
from pathlib import Path

from schgen.core import fallbacks as _fb
from schgen.core import quantize as _q
from schgen.core.project import PROJECT_ROOT
from schgen.core.project import spec as _project_spec

REPO_ROOT = Path(__file__).resolve().parents[2]
SOM_PCB = REPO_ROOT / "som" / "Zynq_SoM.kicad_pcb"
PARTS_DIR = REPO_ROOT / "parts"
OUT_SVG = PROJECT_ROOT / "docs" / "FLOORPLAN.svg"
OUT_MD = PROJECT_ROOT / "docs" / "FLOORPLAN.md"
# DECLARATIVE floorplan spec (human-editable). When present, build_plan reads it
# and OVERRIDES the auto-derivation: a subsystem listed under an edge is pinned
# to that edge, in the listed order; an interior entry sets its anchor. Any
# subsystem NOT named in the spec falls back to the auto-derivation, so the spec
# is optional + incremental. Round-trip seeded by `schgen floorplan --export`.
FLOORPLAN_SPEC = PROJECT_ROOT / "floorplan.json"

_EDGES = ("N", "E", "S", "W")
_LAYER_SIDES = ("top", "bottom", "either")

# The edge-seat override (Decision D11) is now SPEC DATA: an interior entry in
# carrier/floorplan.json may carry a validated ``pull`` knob (T1 P3, decision
# D-1 — seat authority lives in the reviewed JSON, not a code constant). An
# EXCLUSIVE pull replaces the old ``_EDGE_SEAT_BLOCKS`` hack verbatim (zone
# weight = pull.weight, SoM pull dropped, anchor aimed at the pulled edge
# block's inboard face); a non-exclusive pull adds ONE weighted point to the
# anchor accumulation. Schema + invariants: ``load_floorplan_spec``.

# Board outline — DERIVED, not hardcoded. ``derive_outline`` (below) computes
# BOARD_W/BOARD_H from the SoM footprint + the edge-connector depths + the
# total component area + a perimeter keepout; ``build_plan`` calls it FIRST and
# rebinds these module globals before any packing reads them, so every
# downstream consumer (the packer, the SVG/MD, the PCB) sees the derived
# dimensions. The seed values here are only a fallback for a direct import that
# never calls ``derive_outline`` (and match the historical ~120x100 class).
BOARD_W = 120.0
BOARD_H = 100.0
OUTLINE_NOTE = ""        # human-readable derivation, set by derive_outline

# Module (SoM) placement OFFSET from board centre (mm) — the project's SHIPPING
# pose, read from project.json placement.module_offset (P1: the pose is project
# POLICY, not an engine constant). For the carrier, (-8,+6) is the measured optimum
# of a 20-configuration build sweep (demand-weighted connector centroid sits W+S of
# centre; larger shifts break fan-out / thermal / the DF40 stitch corridor — see the
# som-offset record). SCHGEN_SOM_DX/DY env overrides for experiments; 0/0 recovers
# the centred pose. The LAW-5 + placement gates remain the arbiters.
SOM_DX = float(os.environ.get("SCHGEN_SOM_DX",
                              str(_project_spec().module_offset[0])))
SOM_DY = float(os.environ.get("SCHGEN_SOM_DY",
                              str(_project_spec().module_offset[1])))

EDGE_MARGIN = 10.0       # board corners kept clear of edge connectors AND the
                         # corner-forced M3 mounting holes (MH_INSET 5 + pad ~3)
MH_CORNER_KO = 10.0      # corner square reserved for each corner-forced M3 hole
                         # (the PCB corner-forces a hole into each corner) so no
                         # edge/interior block overlaps it (was a DRC short)
EDGE_DEPTH_CAP = 15.0    # edge block max depth into the board
EDGE_INSET = 1.5         # depth-wise gap an edge block is held off the board edge
                         # (LAW 6: a flush off-board connector's pads must still
                         # clear the 0.3mm copper_edge_clearance after grid snap)
CABLE_NEIGHBOR_GAP = 20.0
_OVERMOLD_FAMILIES = {"HDMI-019S"}
OVERMOLD_PLUG_W_MAX = 22.0
OVERMOLD_COPPER_HALF_W = 8.0
OVERMOLD_SIDE_GAP = round(OVERMOLD_PLUG_W_MAX / 2.0 - OVERMOLD_COPPER_HALF_W, 4)


def _is_overmold_block(b) -> bool:
    """True if this edge block carries a wide-overmold cable connector (HDMI).

    OVERMOLD DATUM (the two constants above, and the only place they are set).
    ``OVERMOLD_PLUG_W_MAX`` 22.0 mm is the ceiling of the mated HDMI Type-A cable
    plug's moulded boot, taken about the receptacle centre-line: the plug's metal
    shell is 13.9 x 4.45 mm (HDMI spec Type-A plug outline) and real cable hoods
    measure ~20 mm across, so 22.0 is an UPPER BOUND, not a fitted value — no
    first-party dimensioned hood drawing could be obtained (the L-com CTLHDMI-MM-1
    outline drawing leaves the hood undimensioned: "UNDIMENSIONED FEATURES MAY
    VARY"). ``OVERMOLD_COPPER_HALF_W`` 8.0 mm is MEASURED from
    parts/HDMI-019S/HDMI-019S.kicad_mod: shield through-holes at x = +/-7.2499
    with size 1.5, so the copper bbox is 15.9998 mm wide about the centre.
    The receptacle body itself is 15.000 x 11.900 x 8.000 mm (HDMI-019S.wrl).

    Everything downstream is derived from those two numbers; nothing else in the
    tree may restate the boot width."""
    return any(v in _OVERMOLD_FAMILIES for (_r, v, _w, _h) in b.conns)


def _fanout_sep(a_reach: tuple, a_inset: tuple, b_reach: tuple, b_inset: tuple,
                axis: str) -> float:
    """Required extra separation (mm) between two blocks abutting along ``axis``,
    from the D13 per-side reaches + insets. ``axis`` is "E" when B is to the +x
    (right) of A, "W" for -x, "S" for +y (below), "N" for -y; the facing sides
    are A's axis side vs B's opposite. PAIR-EXACT composition: the gate demand
    between a subject in A and the nearest countable part in B is one-sided —
    subject apron minus the neighbour's real border inset — and two facing
    demands share the same gap, so they compose by MAX, never by SUM (summing
    doubled the reservation and inflated the board; aprons legally overlap in
    the shared void). A side with no under-margined subject (reach 0) demands
    nothing."""
    ia, ib = {"W": (0, 1), "E": (1, 0), "N": (2, 3), "S": (3, 2)}[axis]
    sa = a_reach[ia] - b_inset[ib] if a_reach[ia] > 0.0 else 0.0
    sb = b_reach[ib] - a_inset[ia] if b_reach[ib] > 0.0 else 0.0
    return max(sa, sb)


def _pair_gap(a, b) -> float:
    """Along-edge clearance between two adjacent edge blocks: the overmold charge
    when one or both carry an overmold cable connector, else the fan-out default.

    OVERMOLD IS NOT SYMMETRIC — the charge depends on how many boots meet in the
    gap, not on whether one is present:

    * BOTH overmold (HDMI <-> HDMI): two boots meet, ``CABLE_NEIGHBOR_GAP``.
      Kept at its historical 20.0 mm. The datum-derived copper requirement is
      ``OVERMOLD_PLUG_W_MAX - 2 * OVERMOLD_COPPER_HALF_W`` = 6.0 mm, but cutting
      to it was MEASURED to buy nothing (174x162, worse than leaving it), so the
      protective value stands.
    * ONE overmold (HDMI <-> plain socket): only the HDMI's OWN boot enters the
      gap, and it overhangs its own copper by at most
      ``OVERMOLD_PLUG_W_MAX / 2 - OVERMOLD_COPPER_HALF_W`` = ``OVERMOLD_SIDE_GAP``
      = 3.0 mm per side. Charging the full pair gap here double-counted a boot the
      plain neighbour does not have: it billed 20.0 mm for a 3.0 mm requirement,
      and since the charge is between BLOCK BOXES while the connectors sit
      0.555-3.500 mm inside their own block edges, that 3.0 mm is itself already
      conservative at the copper. ``connector_spacing_gate`` re-proves the derived
      value on the emitted board, copper to copper.

    D13 FAN-OUT CLEARANCE: two abutting blocks in an edge RUN are laid along the
    edge axis (N/S runs spread along X, W/E runs along Y), so ``a`` sits before ``b``
    on that axis. They are held the sum of their FACING-side reaches apart (never
    below CLEAR) so a multi-pin subject whose zone-internal margin does not already
    cover its fan-out floor still gets that floor to the foreign part in the
    neighbouring block. The one-overmold charge composes with it by MAX (both are
    floors on the same gap); the pair charge dominates any reach. The facing sides
    are resolved from the edge orientation."""
    om_a, om_b = _is_overmold_block(a), _is_overmold_block(b)
    if om_a and om_b:
        return CABLE_NEIGHBOR_GAP
    # a run on the N/S edge spreads along X (a is to the W of b); a W/E run spreads
    # along Y (a is to the N of b). Use the facing-side reaches accordingly.
    axis = "E" if (a.edge or b.edge) in ("N", "S") else "S"
    floor = OVERMOLD_SIDE_GAP if (om_a or om_b) else CLEAR
    return round(max(floor, _fanout_sep(a.fanout_reach, a.fanout_inset,
                                        b.fanout_reach, b.fanout_inset, axis)), 4)


# (reach_w, reach_e, reach_n, reach_s): extra clearance (mm) a multi-pin subject
# needs beyond a neighbour's zone on each of the 4 board-frame sides of this block.
# DIRECTIONAL (not a single scalar) so a reservation is spent ONLY on the side an IC
# is actually exposed, not all four — a flat scalar reach over-reserved 3 sides and
# blew the board (the escape router then had no via seat). A zone is placed axis-
# aligned (never block-rotated), so its local W/E/N/S ARE the board W/E/N/S.
_ZeroReach = (0.0, 0.0, 0.0, 0.0)


def _block_fanout_reach(sheet: str, zg) -> tuple[tuple, tuple]:
    """Per-SIDE (reach, inset) for ``sheet``'s zone — the two sufficient
    statistics of the pair-exact D13 composition.

    REACH: for each multi-pin subject (>=3 pins, the gate's tiers) with
    intelligent NEED, its courtyard's margin to EACH of the 4 zone-box edges
    reserves ``need - margin`` (clamped >=0) on a side ONLY when it is the CLOSE
    subject to that edge, so an IC buried mid-zone reserves nothing and only an
    edge-hugging IC pushes a neighbour on the one side it is exposed.

    INSET: the min courtyard margin of ANY gate-countable part (fiducials
    excluded — the gate never counts them as crowding) to each zone side — the
    credit this zone grants a neighbour's subject, since the gate measures
    courtyard-to-courtyard, not courtyard-to-border. Negative when a courtyard
    overhangs the zone box (the overhang then genuinely eats the pair gap).
    Matches the emitted board (same zone geometry + rotations the PCB places);
    tiers/subject rule from the fan-out gate."""
    zbox = zg.zone_box.get(sheet)
    if zbox is None:
        return _ZeroReach, _ZeroReach
    zw, zh = zbox
    rot_of = dict(zg.conn_rot)
    rot_of.update(zg.zone_extra_rot)
    return _zone_fanout_reach(zw, zh,
                              (zg.top_off.get(sheet, {}),
                               zg.bot_off.get(sheet, {})), rot_of, zg)


def _shape_fanout_reach(shape, zg) -> tuple[tuple, tuple]:
    """The SAME derivation as :func:`_block_fanout_reach` on ONE shape variant
    (its own box/offsets/rotations, chirality-mirrored members through their
    mirrored documents) — so the occupancy lattice reserves the fan-out floor
    of the shape actually chosen, never shape 0's. extra_rot composes
    ADDITIVELY onto conn_rot (the emission/evaluate convention — a
    conn-seated mirror shape carries extra 0.0 for its connector)."""
    rot_of = dict(zg.conn_rot)
    for r, e in shape.extra_rot.items():
        rot_of[r] = (rot_of.get(r, 0.0) + e) % 360.0
    return _zone_fanout_reach(shape.w, shape.h,
                              (shape.top_off, shape.bot_off), rot_of, zg,
                              mods=shape.mirror)


def _zone_components(zg, t_off: dict, b_off: dict, extra_rot: dict,
                     side: str, mods: dict | None = None,
                     pad_punch: bool = True) -> tuple:
    """Occupancy COMPONENTS of one zone shape (bottom-side P1), zone-local:
    the SECONDARY-side content bbox on the OPPOSITE copper face's mask (a
    2-sided overlay pack really occupies both surfaces) plus a PUNCH box per
    THROUGH-HOLE PAD (wave-11: the pad copper is the only geometry that
    pierces — a THT connector's shell, courtyard and empty zone area are
    top-side body and never blocked B.Cu). Zero-reach sub-rects — the
    block's D13 reach rides its main rect; for an all-top population every
    component check is implied by the main-rect check (contained boxes), the
    byte-inertness argument. ``mods`` (wave-9 chirality): per-ref mirrored-
    document override — a mirrored member's box is its mirrored document's
    bbox. Deterministic: sorted refs, 4dp rounding."""
    from schgen.generate.pcb.footprint import _footprint_bbox, has_thru_pads
    from schgen.generate.pcb.mating_face import _rot_bbox_cw, thru_pad_boxes
    rot_of = dict(zg.conn_rot)
    for r, e in extra_rot.items():
        rot_of[r] = (rot_of.get(r, 0.0) + e) % 360.0

    def _cb(r: str, ox: float, oy: float
            ) -> tuple[float, float, float, float] | None:
        mp = (mods or {}).get(r)
        bb = _footprint_bbox(mp) if mp is not None else zg.bbox_of.get(r)
        if bb is None:
            return None
        c = _rot_bbox_cw(bb, rot_of.get(r, 0.0))
        return (ox + c[0], oy + c[1], ox + c[2], oy + c[3])

    comps: list[tuple] = []
    minor = [b for b in (_cb(r, *o) for r, o in sorted(b_off.items()))
             if b is not None]
    if minor:
        x0 = min(b[0] for b in minor)
        y0 = min(b[1] for b in minor)
        x1 = max(b[2] for b in minor)
        y1 = max(b[3] for b in minor)
        comps.append((round(x0, 4), round(y0, 4), round(x1 - x0, 4),
                      round(y1 - y0, 4),
                      OCC_TOP if side == "bottom" else OCC_BOTTOM))
    for off in (t_off, b_off):
        for r, (ox, oy) in sorted(off.items()):
            mod = (mods or {}).get(r) or zg.resolvable.get(r)
            if mod is None or not has_thru_pads(mod):
                continue
            if not pad_punch:
                c = _cb(r, ox, oy)
                if c is not None:
                    comps.append((round(c[0], 4), round(c[1], 4),
                                  round(c[2] - c[0], 4), round(c[3] - c[1], 4),
                                  OCC_PUNCH))
                continue
            boxes = thru_pad_boxes(mod, rot_of.get(r, 0.0))
            if not boxes:
                raise AssertionError(
                    f"floorplan: {r} ({mod}) declares through-hole pads but "
                    f"the pad kernel found none — the punch set would silently "
                    f"lose the geometry that pierces both copper faces")
            for p in boxes:
                comps.append((round(ox + p[0], 4), round(oy + p[1], 4),
                              round(p[2] - p[0], 4), round(p[3] - p[1], 4),
                              OCC_PUNCH))
    return tuple(comps)


def _zone_fanout_reach(zw: float, zh: float, side_offs, rot_of: dict, zg,
                       mods: dict | None = None) -> tuple[tuple, tuple]:
    from schgen.generate.pcb import placement as _pl
    from schgen.generate.pcb.footprint import _footprint_bbox
    from schgen.generate.pcb.mating_face import _rot_bbox_cw
    from schgen.verify.fanout_gate import (
        MIN_SUBJECT_PINS,
        intelligent_need,
        is_testpoint_ref,
    )
    rw = re = rn = rs = 0.0
    iw = ie = in_ = is_ = float("inf")
    for side_off in side_offs:
        for ref, (ox, oy) in side_off.items():
            mod = zg.resolvable.get(ref)
            bbox = zg.bbox_of.get(ref)
            mp = (mods or {}).get(ref)
            if mp is not None:
                mod, bbox = mp, _footprint_bbox(mp)
            if mod is None or bbox is None:
                continue
            if "Fiducial" in mod.stem or is_testpoint_ref(ref):
                continue
            # KiCad's CW rotation sign — the SAME kernel emission and the D13
            # gate measure with (_eff_box/_inst_courtyard); the math-CCW
            # _rot_bbox skews an asymmetric part's rot-90/270 margins by its
            # bbox asymmetry (TYPE-C: 1.97 mm).
            rb = _rot_bbox_cw(bbox, rot_of.get(ref, 0.0))
            cx0, cy0 = ox + rb[0], oy + rb[1]
            cx1, cy1 = ox + rb[2], oy + rb[3]
            mw, me = cx0, zw - cx1          # margin to W (left) / E (right) edge
            mn, ms = cy0, zh - cy1          # margin to N (top) / S (bottom) edge
            iw, ie = min(iw, mw), min(ie, me)
            in_, is_ = min(in_, mn), min(is_, ms)
            pins = len(_pl.pad_names(mod))
            if pins < MIN_SUBJECT_PINS:
                continue
            need = intelligent_need(pins)[0]
            # EXACT credit: zones emit at their exact floorplan pose and
            # _pack_edges emits exact run positions, so the reservation
            # transfers verbatim; movers that shift parts afterwards (BREATHE,
            # edge-seat) validate need themselves. +0.05: 4dp quantization eats
            # microns — a reach met exactly emerged 15um short (measured).
            lim = _q.quant_credit(need)
            if mw <= lim:
                rw = max(rw, lim - mw)
            if me <= lim:
                re = max(re, lim - me)
            if mn <= lim:
                rn = max(rn, lim - mn)
            if ms <= lim:
                rs = max(rs, lim - ms)
    if iw == float("inf"):
        iw = ie = in_ = is_ = 0.0
    return ((round(rw, 4), round(re, 4), round(rn, 4), round(rs, 4)),
            (round(iw, 4), round(ie, 4), round(in_, 4), round(is_, 4)))


CLEAR = 0.3              # block-to-block clearance — TIGHTENED (was 1.5). The
                         # interior occupancy lattice + the edge run both pack to
                         # this gap, so a smaller value pulls every subsystem
                         # closer, directly SHORTENING the cross-subsystem airwire
                         # (the binding LAW-5 term) and letting the grow loop stop
                         # at a smaller board. It is a FLOOR, not the operative
                         # gap: every pair that carries a D13 fan-out demand is
                         # separated by _fanout_sep's pair-exact composition, which
                         # is >= this. DRC stays 0; the strict gate judges.
BIG_PART_MM2 = 40.0      # parts at/above this use raw courtyard area
ROUTE_FACTOR = 3.5       # small-part area multiplier (escape + routing)

# --- outline-derivation parameters --------------------------------------------
# PERIM_KEEPOUT + SOM_HALO are DRC-load-bearing (perimeter ring + SoM escape
# halo) and stay; EDGE_BAND / PACK_EFFICIENCY are the SIZING knobs tightened for
# 2-sided assembly so the board no longer carries 70% empty area.
PERIM_KEEPOUT = 3.0      # board-edge keepout ring kept free of components (KEEP)
SOM_HALO = 7.0           # routing/escape halo reserved around the SoM body (KEEP)
EDGE_BAND = EDGE_DEPTH_CAP - 4.0   # depth of the connector band on each edge —
                         # TIGHTENED (was +4). The deepest edge connectors sit
                         # within EDGE_DEPTH_CAP; the band only seeds the outline
                         # (the grow loop still proves every real block fits), so
                         # a shallower seed band shrinks the starting box without
                         # risking an edge block off-board.
# component-area packing efficiency: top-side usable area must exceed the total
# component area divided by this. RAISED 0.30 -> 0.50 for the 2-sided build
# (pcb.py splits parts across both copper sides, ~halving the TOP pressure), so
# the outline seed is sized for the real 2-sided fill instead of a single-side
# worst case that left the board ~70% empty. The grow loop + the STRICT LAW-5
# ratsnest gate remain the final arbiters of routing headroom.
PACK_EFFICIENCY = 0.60

FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"
SCALE = 6.0              # SVG px per mm


# ---- SoM PCB extraction ----------------------------------------------------------

@dataclass(frozen=True)
class SomJ:
    ref: str
    pcb_x: float          # raw position in the SoM PCB file
    pcb_y: float
    rot: float
    x: float              # carrier-top view, SoM-relative (mirrored)
    y: float
    w: float              # pad-extent box in that view
    h: float


@dataclass(frozen=True)
class SomGeom:
    w: float
    h: float
    js: tuple[SomJ, ...]
    source: str


_NUMS = re.compile(r"-?\d+(?:\.\d+)?")


def _floats(s: str) -> list[float]:
    return [float(m) for m in _NUMS.findall(s)]


def extract_som(pcb: Path = SOM_PCB) -> SomGeom:
    """Outline bbox (Edge.Cuts) + the three DF40 mezzanine footprints,
    identified by their Reference property. Positions are mirrored about the
    vertical axis: the connectors sit on the SoM's BOTTOM copper, so the
    carrier-top view of the mating receptacles is the bottom-side view."""
    edge_pts: list[tuple[float, float]] = []
    js_raw: dict[str, tuple[float, float, float, float, float]] = {}

    in_gr = False
    gr_pts: list[tuple[float, float]] = []
    in_fp = False
    fp_at: tuple[float, float, float] | None = None
    fp_ref: str | None = None
    pad_xs: list[float] = []
    pad_ys: list[float] = []
    pad_at: tuple[float, float] | None = None
    pad_pending = False

    def commit_fp() -> None:
        nonlocal in_fp
        if in_fp and fp_ref in ("J1", "J2", "J3") and fp_at and pad_xs:
            w = max(pad_xs) - min(pad_xs)
            h = max(pad_ys) - min(pad_ys)
            js_raw[fp_ref] = (fp_at[0], fp_at[1], fp_at[2], w, h)
        in_fp = False

    for raw in pcb.read_text().splitlines():
        s = raw.strip()
        if s.startswith("(gr_line") or s.startswith("(gr_arc"):
            commit_fp()
            in_gr, gr_pts = True, []
            continue
        if in_gr:
            if s.startswith(("(start ", "(mid ", "(end ")):
                v = _floats(s)
                if len(v) >= 2:
                    gr_pts.append((v[0], v[1]))
            elif s.startswith("(layer "):
                if '"Edge.Cuts"' in s:
                    edge_pts.extend(gr_pts)
                in_gr = False
            continue
        if s.startswith("(footprint "):
            commit_fp()
            in_fp = True
            fp_at, fp_ref = None, None
            pad_xs, pad_ys = [], []
            pad_pending, pad_at = False, None
            continue
        if not in_fp:
            continue
        if fp_at is None and s.startswith("(at "):
            v = _floats(s)
            fp_at = (v[0], v[1], v[2] if len(v) > 2 else 0.0)
        elif s.startswith('(property "Reference"'):
            q = s.split('"')
            if len(q) >= 4:
                fp_ref = q[3]
        elif s.startswith("(pad "):
            pad_pending, pad_at = True, None
        elif pad_pending and s.startswith("(at "):
            v = _floats(s)
            pad_at = (v[0], v[1])
        elif pad_pending and pad_at and s.startswith("(size "):
            v = _floats(s)
            pad_xs += [pad_at[0] - v[0] / 2, pad_at[0] + v[0] / 2]
            pad_ys += [pad_at[1] - v[1] / 2, pad_at[1] + v[1] / 2]
            pad_pending = False
    commit_fp()

    if not edge_pts:
        raise RuntimeError(f"no Edge.Cuts outline found in {pcb}")
    missing = {"J1", "J2", "J3"} - set(js_raw)
    if missing:
        raise RuntimeError(f"DF40 footprints not found in {pcb}: "
                           f"{sorted(missing)}")
    x0 = min(p[0] for p in edge_pts)
    y0 = min(p[1] for p in edge_pts)
    w = max(p[0] for p in edge_pts) - x0
    h = max(p[1] for p in edge_pts) - y0
    js = []
    for ref in ("J1", "J2", "J3"):
        px, py, rot, pw, ph = js_raw[ref]
        ew, eh = (ph, pw) if rot % 180 == 90 else (pw, ph)
        js.append(SomJ(ref=ref, pcb_x=px, pcb_y=py, rot=rot,
                       x=round(w - (px - x0), 3),       # mirror (bottom view)
                       y=round(py - y0, 3),
                       w=round(ew, 3), h=round(eh, 3)))
    return SomGeom(w=round(w, 3), h=round(h, 3), js=tuple(js),
                   source=str(pcb.relative_to(REPO_ROOT)))


# ---- part footprint areas --------------------------------------------------------

_DIMS_IN_NAME = re.compile(r"_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm")
_METRIC = re.compile(r"_(\d{2})(\d{2})Metric")
# nominal body+lead spans for name-only footprints (JEDEC class, mm)
_FIXED_DIMS = {
    "TSOT-23-6": (2.9, 2.8),
    "SOT-23-5": (2.9, 2.8),
    "SOT-23": (2.9, 2.4),
    "D_SMA": (4.3, 2.6),
    "D_SMB": (5.4, 3.6),
    "TestPoint_Pad_D1.5mm": (1.5, 1.5),
    "MountingHole_3.2mm_M3_Pad": (6.4, 6.4),   # M3 plated pad OD (no parts/ folder)
}
_DEFAULT_DIMS = (1.6, 0.8)      # unspecified passive

_crtyd_cache: dict[str, tuple[float, float] | None] = {}


def _courtyard_dims(lib: str) -> tuple[float, float] | None:
    """F.CrtYd bbox of parts/<lib>/<lib>.kicad_mod (pads as fallback)."""
    if lib in _crtyd_cache:
        return _crtyd_cache[lib]
    mod = PARTS_DIR / lib / f"{lib}.kicad_mod"
    dims = None
    if mod.exists():
        text = mod.read_text()
        xs: list[float] = []
        ys: list[float] = []
        for m in re.finditer(
                r"\(fp_(?:line|rect|poly|circle|arc)\b(.*?)"
                r"\(layer \"F\.CrtYd\"\)", text, re.S):
            for c in re.finditer(
                    r"\((?:start|end|mid|xy|center) (-?\d+(?:\.\d+)?) "
                    r"(-?\d+(?:\.\d+)?)\)", m.group(1)):
                xs.append(float(c.group(1)))
                ys.append(float(c.group(2)))
        if not xs:
            for m in re.finditer(
                    r"\(pad [^\n]*\n\s*\(at (-?\d+(?:\.\d+)?) "
                    r"(-?\d+(?:\.\d+)?)", text):
                xs.append(float(m.group(1)))
                ys.append(float(m.group(2)))
        if xs:
            dims = (round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2))
    _crtyd_cache[lib] = dims
    return dims


def part_dims(footprint: str) -> tuple[float, float]:
    lib, _, name = footprint.partition(":")
    if lib:
        d = _courtyard_dims(lib)
        if d:
            return d
    for key in sorted(_FIXED_DIMS, key=len, reverse=True):
        if key in name:
            return _FIXED_DIMS[key]
    m = _DIMS_IN_NAME.search(name)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = _METRIC.search(name)
    if m:
        return (int(m.group(1)) / 10.0, int(m.group(2)) / 10.0)
    return _DEFAULT_DIMS


def sheet_area(c, factor: float) -> float:
    """Component area estimate: big parts (connectors, magnetics, headers)
    count at raw courtyard area; small parts get the routing factor."""
    total = 0.0
    for part in c.parts.values():
        w, h = part_dims(part.footprint)
        a = w * h
        total += a if a >= BIG_PART_MM2 else a * factor
    return total


def _raw_component_area(sheets) -> float:
    """Sum of every part's raw courtyard area (mm^2), SoM mezzanine receptacles
    excluded (they live in the SoM region, not the free area). Used for the
    OUTLINE derivation — distinct from sheet_area's block-sizing estimate which
    inflates small parts by the routing factor."""
    total = 0.0
    for sc in sheets:
        if sc.name.startswith("som_j") or sc.name == "som_decoupling":
            continue        # the receptacles ARE the SoM; som_decoupling lives
            #                 UNDER the SoM shadow, not in the free area (LAW 6)
        for part in sc.circuit.parts.values():
            w, h = part_dims(part.footprint)
            total += w * h
    return total


@dataclass(frozen=True)
class Outline:
    w: float
    h: float
    note: str


def derive_outline(sheets, som: SomGeom) -> Outline:
    """Board W x H DERIVED from the design, generously sized for routing
    headroom — replaces the old hardcoded 120x100. Every term is from data:

      - the SoM body + a routing halo, centered, sets the core;
      - a connector BAND on each of the four edges (deep enough for the
        deepest edge connector: HDMIx2 / RJ45 / USB-Cx4 / FMC overhang / FFCs)
        wraps the SoM core on all sides;
      - the TOTAL raw component area / PACK_EFFICIENCY sets a floor on the
        usable interior so every block fits with routing channels;
      - a PERIM_KEEPOUT ring is added on every side.

    The result is rounded UP to OUTLINE_SNAP. Deterministic: same inputs ->
    same dimensions (no randomness, no timestamp)."""
    # core = SoM body + escape halo on all sides + a connector band on each
    # edge. The band depth is the same on every edge so the SoM stays centered
    # and any edge can host its connector family (the packer chooses which).
    core_w = som.w + 2 * SOM_HALO
    core_h = som.h + 2 * SOM_HALO
    banded_w = core_w + 2 * EDGE_BAND
    banded_h = core_h + 2 * EDGE_BAND

    # area floor: the usable interior (inside the perimeter keepout) must hold
    # the whole component set at PACK_EFFICIENCY fill. Keep the SoM aspect so
    # the area term grows the board proportionally rather than stretching it.
    comp_area = _raw_component_area(sheets)
    som_keepout = (som.w + 2 * SOM_HALO) * (som.h + 2 * SOM_HALO)
    need_area = comp_area / PACK_EFFICIENCY + som_keepout
    aspect = banded_w / banded_h
    area_w = (need_area * aspect) ** 0.5
    area_h = (need_area / aspect) ** 0.5

    w = max(banded_w, area_w) + 2 * PERIM_KEEPOUT
    h = max(banded_h, area_h) + 2 * PERIM_KEEPOUT

    w, h = _q.outline_snap_up(w), _q.outline_snap_up(h)
    note = (f"SoM {som.w:g}x{som.h:g} + {SOM_HALO:g}mm halo + {EDGE_BAND:g}mm "
            f"connector band/edge -> core {banded_w:g}x{banded_h:g}; "
            f"component area {comp_area:.0f}mm2 / {PACK_EFFICIENCY:g} fill "
            f"-> area floor {area_w:.0f}x{area_h:.0f}; + {PERIM_KEEPOUT:g}mm "
            f"perimeter keepout -> {w:g}x{h:g} mm (rounded up to "
            f"{_q.OUTLINE_SNAP_MM:g}mm grid)")
    return Outline(w=w, h=h, note=note)


# ---- edge-connector classification ------------------------------------------------
# Which connector FAMILIES mate off-board horizontally (a cable/plug/card
# enters across the board edge) — the mating direction is a property of the
# part, the membership of a sheet is read from its netlist.
_EDGE_FAMILIES: dict[str, str] = {
    "TYPE-C-31-M-12": "USB-C receptacle",
    "HDMI-019S": "HDMI receptacle",
    "AFC07-S40FCA-00": "FFC 40-pin 0.5mm (LCD)",
    "SFW15R-1STE1LF": "FFC 15-pin 1mm (camera)",
    "TF-01A": "microSD push-pull",
    "DS1024-2x6R2": "PMOD 2x6 socket",
    "XT60PW-M": "XT60 ESC power inlet (horizontal)",
    # ^ MUST mirror pcb.CONN_MATING_FACE: a connector registered there for
    # rotation/seating but NOT here gets is_edge=False, and a >1-connector zone
    # then trips the interior re-flow guard (which re-packs WITHOUT connector
    # spread) -> the two motor_sense XT60s landed coincident (a real pad short).
}
# author-declared expect= deferrals that name a future EDGE connector
_DEFERRED_EDGE = re.compile(r"\b(rj45|usb_uart)_connector\b")

# j1/j2/j3 tokens inside expect= strings ("som_j3_connector",
# "som_j2/j3 bank-33 spare"): underscore is a \w char, so \b alone misses
# the som_jN forms — bound by not-alphanumeric instead.
_J_IN_EXPECT = re.compile(r"(?<![A-Za-z0-9])j([123])(?![A-Za-z0-9])",
                          re.IGNORECASE)


# ---- model -----------------------------------------------------------------------

@dataclass
class Block:
    name: str                    # sheet name
    kind: str                    # "edge" | "interior"
    x: float = 0.0               # top-left, board frame (mm)
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    edge: str = ""               # N/E/S/W for edge blocks
    conns: list[tuple[str, str, float, float]] = field(default_factory=list)
    reserved: list[str] = field(default_factory=list)   # deferred connectors
    n_parts: int = 0
    area: float = 0.0            # block area target (mm^2)
    j_aff: dict[str, int] = field(default_factory=dict)
    zone: str = ""               # N/E/S/W zone for interior blocks
    notes: list[int] = field(default_factory=list)
    order_hint: int | None = None  # spec-pinned slot ALONG the edge (overrides
                                   # the auto J-affinity sort when not None)
    pinned: bool = False          # placed by carrier/floorplan.json (vs auto)
    pull: dict | None = None      # validated floorplan.json pull knob (T1 P3):
                                  # {"to","weight","face","exclusive","basis"}
    shape_idx: int = 0            # MULTI-SHAPE: index into this sheet's legal
                                  # shape set (ZoneGeom.shapes) picked by the
                                  # pack search; 0 = the legacy single shape
    side: str = "top"             # copper face the pack search assigned this
                                  # block to ("top"|"bottom") — the side of the
                                  # chosen shape; "top" for every block whose
                                  # sheet declares no bottom eligibility
    layer_pref: str = "top"       # the DECLARED floorplan.json eligibility
                                  # ("top"|"bottom"|"either") for export
                                  # round-trip; the engine consumes shapes
    fanout_reach: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
                                  # D13 FAN-OUT CLEARANCE, per board-frame side
                                  # (W, E, N, S): extra clearance (mm) a multi-pin
                                  # subject exposed on that side of THIS block needs
                                  # beyond a neighbour's zone edge — the intelligent
                                  # fan-out floor not already met by the zone's own
                                  # internal margin. Composed PAIR-EXACTLY with the
                                  # neighbour's facing reach/inset by _fanout_sep
                                  # (MAX of one-sided demands, never SUM), so an
                                  # edge-hugging IC keeps its fan-out floor to the
                                  # foreign part next door WITHOUT reserving space on
                                  # the 3 sides it is not exposed on.
    fanout_inset: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
                                  # per-side min courtyard margin of ANY countable
                                  # part to this block's border — the credit granted
                                  # to a facing subject's apron (negative = overhang).

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def _j_affinity(sheets, link_result) -> dict[str, dict[str, int]]:
    """sheet -> {J1: n, ...} from bound targets AND deferred expects."""
    aff: dict[str, dict[str, int]] = {sc.name: {} for sc in sheets}
    for b in link_result.bindings:
        d = aff.setdefault(b.sheet, {})
        if b.status == "deferred" and b.ptype.expect:
            for m in _J_IN_EXPECT.finditer(b.ptype.expect):
                jn = f"J{m.group(1)}"
                d[jn] = d.get(jn, 0) + 1
            continue
        for t in b.targets:
            jn = None
            if t.startswith("sheet som_j"):
                jn = "J" + t.split()[1][len("som_j"):].split(":")[0]
            elif t.startswith("SoM ") and "(J" in t:
                jn = t.split("(", 1)[1][:2]
            if jn in ("J1", "J2", "J3"):
                d[jn] = d.get(jn, 0) + 1
    return aff


def _dominant_j(aff: dict[str, int]) -> str | None:
    if not aff:
        return None
    return sorted(aff.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _j_edge_map(som: SomGeom) -> dict[str, str]:
    """Which board edge each mezzanine connector faces (nearest SoM edge in
    the carrier-top view) — derived from the extracted positions."""
    out: dict[str, str] = {}
    for j in som.js:
        cands = [(j.y, "N"), (som.h - j.y, "S"),
                 (j.x, "W"), (som.w - j.x, "E")]
        out[j.ref] = min(cands)[1]
    return out


# ---- declarative floorplan spec --------------------------------------------------

@dataclass(frozen=True)
class FloorplanSpec:
    """Parsed + validated carrier/floorplan.json.

    ``outline``  : "auto" (derive) or {"w": <mm>, "h": <mm>} (a fixed board).
    ``edges``    : edge -> ordered list of subsystem names PINNED to that edge.
                   The list ORDER is the order ALONG the edge (N/S left->right,
                   W/E top->bottom), overriding the auto J-affinity sort.
    ``interior`` : subsystem -> {"side": N/E/S/W} or {"near": <subsystem>} —
                   the anchor the interior packer pulls the block toward —
                   optionally + {"pull": {to, weight, face, exclusive, basis}}
                   (T1 P3: the validated seat-authority knob; see
                   ``_validate_pull``). The copper-face degree of freedom
                   "top"|"bottom"|"either" (bottom-side P1) is the ``layer``
                   key — combinable with a real N/E/S/W anchor — or, for an
                   anchor-less block, a ``side`` holding the layer value (the
                   P1 spelling; declaring both raises). Exposed as
                   ``layer_of``; absent = top, and seated-connector blocks
                   may never declare bottom/either (validated loudly in the
                   shared packer, where the connector content is known).
    Every other subsystem (not named anywhere) keeps the auto-derivation, so the
    spec is optional and incremental. ``edge_of`` / ``edge_order`` / ``anchor_of``
    are the flat lookups build_plan consumes. Deterministic: the spec is read
    once, dict iteration is never relied on (lists carry order, lookups are by
    explicit key)."""
    outline: object                       # "auto" | (w, h)
    edges: dict[str, tuple[str, ...]]     # edge -> ordered names
    interior: dict[str, dict]             # name -> {"side":..} | {"near":..}
    ordered_edges: dict[str, list[str]] = field(default_factory=dict)
    source: str = ""

    @property
    def edge_of(self) -> dict[str, str]:
        return {name: e for e, names in self.edges.items() for name in names}

    @property
    def edge_order(self) -> dict[str, int]:
        """name -> its 0-based slot, ONLY for edges listed in the OPTIONAL
        ``edge_order`` spec key. A bare ``edges`` list is MEMBERSHIP — the
        along-edge order derives from J-affinity targets (list-index pinning
        froze every edge in authored order and left the affinity mechanism
        dead: hdmi + camera/lcd crossings, user-measured)."""
        out: dict[str, int] = {}
        for names in self.ordered_edges.values():
            for i, name in enumerate(names):
                out[name] = i
        return out

    @property
    def layer_of(self) -> dict[str, str]:
        """name -> declared copper-face eligibility: the ``layer`` key, or a
        ``side`` holding a layer value (the anchor-less P1 spelling — the
        parser raises when both are given); every other block defaults top."""
        out = {n: a["side"] for n, a in self.interior.items()
               if a.get("side") in _LAYER_SIDES}
        out.update({n: a["layer"] for n, a in self.interior.items()
                    if "layer" in a})
        return out

    @property
    def names(self) -> set[str]:
        s = set(self.edge_of)
        s.update(self.interior)
        return s


class FloorplanSpecError(ValueError):
    """A malformed carrier/floorplan.json — reported with the offending key."""


def _validate_pull(path: Path, name: str, anchor: dict,
                   edges: dict[str, tuple[str, ...]],
                   valid_names: set[str] | None) -> None:
    """Validate one interior entry's ``pull`` knob (T1 P3, decision D-1).

    Schema: ``{"to": <existing block>, "weight": >0, "face":
    "inboard"|"center" (default center), "exclusive": bool (default false),
    "basis": non-empty}``. Invariants (each a loud FloorplanSpecError, never a
    silent mis-anchor):
      - unknown keys rejected (a typo must fail the build);
      - ``exclusive`` requires the entry's ``near`` anchor to BE ``pull.to``
        AND ``pull.to`` to sit on an edge list — the exact precondition of the
        packer's edge-seat branch, so an exclusive pull can never silently do
        nothing;
      - ``face: inboard`` aims at an edge block's inner face — meaningless for
        an interior target, so it too requires ``pull.to`` on an edge list;
      - one pull per block (the dict shape enforces it)."""
    pull = anchor["pull"]
    if not isinstance(pull, dict):
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull must be an object")
    allowed = {"to", "weight", "face", "exclusive", "basis"}
    if set(pull) - allowed:
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull unknown key(s) "
            f"{sorted(set(pull) - allowed)} (allowed: {sorted(allowed)})")
    for req in ("to", "weight", "basis"):
        if req not in pull:
            raise FloorplanSpecError(
                f"{path.name}: interior[{name!r}].pull requires {req!r} "
                f"(weight/basis make the seat auditable)")
    to = pull["to"]
    if not isinstance(to, str) or (valid_names is not None
                                   and to not in valid_names):
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull.to references unknown "
            f"subsystem {to!r}")
    try:
        weight = float(pull["weight"])
    except (TypeError, ValueError) as exc:
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull.weight must be a number"
        ) from exc
    if weight <= 0:
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull.weight must be > 0 "
            f"(got {weight:g})")
    face = pull.get("face", "center")
    if face not in ("inboard", "center"):
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull.face must be "
            f"\"inboard\" or \"center\" (got {face!r})")
    basis = pull.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull.basis must be a non-empty "
            f"string (LAW 7: every seat carries its why)")
    edge_names = {n for names in edges.values() for n in names}
    if face == "inboard" and to not in edge_names:
        raise FloorplanSpecError(
            f"{path.name}: interior[{name!r}].pull.face=\"inboard\" requires "
            f"pull.to {to!r} to be on an edge list (an interior block has no "
            f"inboard face)")
    if bool(pull.get("exclusive", False)):
        if anchor.get("near") != to or to not in edge_names:
            raise FloorplanSpecError(
                f"{path.name}: interior[{name!r}].pull.exclusive requires "
                f"the entry's \"near\" anchor to be pull.to ({to!r}) AND "
                f"{to!r} to be an edge block — the packer's edge-seat branch "
                f"fires only on that anchor, so a mismatched exclusive pull "
                f"would silently do nothing")


def load_floorplan_spec(path: Path = FLOORPLAN_SPEC,
                        valid_names: set[str] | None = None) -> FloorplanSpec | None:
    """Read + VALIDATE carrier/floorplan.json. Returns None if the file is
    absent (the spec is optional). Raises FloorplanSpecError with a clear message
    on any unknown subsystem name, illegal edge, duplicate placement, or bad
    ``near`` target — a typo must FAIL the build, never silently mis-place."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise FloorplanSpecError(f"{path.name}: invalid JSON — {exc}") from exc
    if not isinstance(raw, dict):
        raise FloorplanSpecError(f"{path.name}: top level must be a JSON object")

    # outline
    o = raw.get("outline", "auto")
    if o == "auto":
        outline: object = "auto"
    elif isinstance(o, dict) and "w" in o and "h" in o:
        try:
            outline = (float(o["w"]), float(o["h"]))
        except (TypeError, ValueError) as exc:
            raise FloorplanSpecError(
                f"{path.name}: outline w/h must be numbers") from exc
        if outline[0] <= 0 or outline[1] <= 0:
            raise FloorplanSpecError(f"{path.name}: outline w/h must be > 0")
    else:
        raise FloorplanSpecError(
            f"{path.name}: outline must be \"auto\" or {{\"w\":<mm>,\"h\":<mm>}}")

    # edges
    edges_raw = raw.get("edges", {})
    if not isinstance(edges_raw, dict):
        raise FloorplanSpecError(f"{path.name}: edges must be an object")
    edges: dict[str, tuple[str, ...]] = {}
    seen: dict[str, str] = {}             # name -> where (for duplicate detection)
    for edge, names in sorted(edges_raw.items()):
        if edge not in _EDGES:
            raise FloorplanSpecError(
                f"{path.name}: edges[{edge!r}] — illegal edge "
                f"(must be one of N/E/S/W)")
        if not isinstance(names, list):
            raise FloorplanSpecError(
                f"{path.name}: edges[{edge!r}] must be a list of subsystem names")
        clean: list[str] = []
        for name in names:
            if not isinstance(name, str):
                raise FloorplanSpecError(
                    f"{path.name}: edges[{edge!r}] entries must be strings")
            if valid_names is not None and name not in valid_names:
                raise FloorplanSpecError(
                    f"{path.name}: edges[{edge!r}] names unknown subsystem "
                    f"{name!r}")
            if name in seen:
                raise FloorplanSpecError(
                    f"{path.name}: subsystem {name!r} placed twice "
                    f"({seen[name]} and edges[{edge!r}])")
            seen[name] = f"edges[{edge!r}]"
            clean.append(name)
        edges[edge] = tuple(clean)

    # interior
    interior_raw = raw.get("interior", {})
    if not isinstance(interior_raw, dict):
        raise FloorplanSpecError(f"{path.name}: interior must be an object")
    interior: dict[str, dict] = {}
    for name, anchor in sorted(interior_raw.items()):
        if valid_names is not None and name not in valid_names:
            raise FloorplanSpecError(
                f"{path.name}: interior names unknown subsystem {name!r}")
        if name in seen:
            raise FloorplanSpecError(
                f"{path.name}: subsystem {name!r} placed twice "
                f"({seen[name]} and interior)")
        if not isinstance(anchor, dict):
            raise FloorplanSpecError(
                f"{path.name}: interior[{name!r}] must be an object "
                f"(\"side\" or \"near\")")
        keys = set(anchor)
        if keys - {"side", "near", "pull", "layer"}:
            raise FloorplanSpecError(
                f"{path.name}: interior[{name!r}] only \"side\", \"near\", "
                f"\"pull\" or \"layer\" are allowed (got {sorted(keys)})")
        if "side" in anchor and anchor["side"] not in _EDGES + _LAYER_SIDES:
            raise FloorplanSpecError(
                f"{path.name}: interior[{name!r}].side must be N/E/S/W "
                f"(zone anchor) or top/bottom/either (copper-face "
                f"eligibility, bottom-side P1)")
        if "layer" in anchor and anchor["layer"] not in _LAYER_SIDES:
            raise FloorplanSpecError(
                f"{path.name}: interior[{name!r}].layer must be "
                f"top/bottom/either (copper-face eligibility; use \"side\" "
                f"for the N/E/S/W zone anchor)")
        if "layer" in anchor and anchor.get("side") in _LAYER_SIDES:
            raise FloorplanSpecError(
                f"{path.name}: interior[{name!r}] declares the copper face "
                f"twice (side={anchor['side']!r} and layer="
                f"{anchor['layer']!r}) — keep exactly one")
        if "near" in anchor:
            tgt = anchor["near"]
            if not isinstance(tgt, str):
                raise FloorplanSpecError(
                    f"{path.name}: interior[{name!r}].near must be a subsystem name")
            if valid_names is not None and tgt not in valid_names:
                raise FloorplanSpecError(
                    f"{path.name}: interior[{name!r}].near references unknown "
                    f"subsystem {tgt!r}")
        if "pull" in anchor:
            _validate_pull(path, name, anchor, edges, valid_names)
        seen[name] = "interior"
        interior[name] = dict(anchor)

    ordered: dict[str, list[str]] = {}
    for e, names in (raw.get("edge_order") or {}).items():
        if e not in edges:
            raise FloorplanSpecError(
                f"{path.name}: edge_order[{e!r}] — edge not in 'edges'")
        if not isinstance(names, list) or set(names) - set(edges[e]):
            raise FloorplanSpecError(
                f"{path.name}: edge_order[{e!r}] must list only members of "
                f"edges[{e!r}]")
        ordered[e] = [str(n) for n in names]
    return FloorplanSpec(outline=outline, edges=edges, interior=interior,
                         ordered_edges=ordered,
                         source=str(path.relative_to(REPO_ROOT)
                                    if path.is_relative_to(REPO_ROOT)
                                    else path))


def export_floorplan_spec(plan: Plan, path: Path = FLOORPLAN_SPEC) -> Path:
    """Write the CURRENT derived plan as a carrier/floorplan.json the user can
    edit — a round-trip seed. Edge sheets are grouped by edge (each list in the
    placed order along that edge); interior sheets carry their derived anchor
    (``near`` for a port-paired @block, else ``side``). Re-running ``schgen
    board`` with this file reproduces today's layout, then editing it changes it.
    Deterministic: edges in N/E/S/W order, names by placed coordinate."""
    edges: dict[str, list[str]] = {e: [] for e in _EDGES}
    for b in plan.edge_blocks:
        if b.edge in edges:
            edges[b.edge].append(b)
    ordered_edges: dict[str, list[str]] = {}
    for e in _EDGES:
        bs = edges[e]
        # order along the edge: x for N/S, y for W/E (the placed coordinate)
        key = (lambda b: (b.x, b.name)) if e in ("N", "S") \
            else (lambda b: (b.y, b.name))
        names = [b.name for b in sorted(bs, key=key)]
        if names:
            ordered_edges[e] = names

    interior: dict[str, dict] = {}
    for b in sorted(plan.interior_blocks, key=lambda b: b.name):
        if b.zone.startswith("@"):
            entry: dict = {"near": b.zone[1:]}
        elif b.zone in _EDGES:
            entry = {"side": b.zone}
        else:
            entry = {"side": "E"}   # default cluster side
        if b.layer_pref != "top":
            entry["layer"] = b.layer_pref
        interior[b.name] = entry
        if b.pull:
            entry["pull"] = dict(b.pull)   # round-trip the knob

    spec = {
        "outline": "auto",
        "_comment": ("DECLARATIVE carrier floorplan - edit this to drive the "
                     "PCB placement. Each edge list = MEMBERSHIP; along-edge "
                     "order derives from J-affinity unless an optional "
                     "top-level edge_order key pins it. interior: "
                     "{\"side\":N/E/S/W} or {\"near\":<subsystem>}. Any "
                     "subsystem omitted falls back to auto-derivation. "
                     "Regenerate this seed with `schgen floorplan --export`."),
        "edges": ordered_edges,
        "interior": interior,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2) + "\n")
    return path


# ---- layout ----------------------------------------------------------------------

class Plan:
    def __init__(self, som: SomGeom):
        self.som = som
        self.som_x = _q.som_pose_half_mm((BOARD_W - som.w) / 2 + SOM_DX)
        self.som_y = _q.som_pose_half_mm((BOARD_H - som.h) / 2 + SOM_DY)
        self.edge_blocks: list[Block] = []
        self.interior_blocks: list[Block] = []
        self.factor = ROUTE_FACTOR
        self.spilled: list[str] = []      # edge blocks moved off their edge
        self.composition: list[str] = []  # T1 P6 legalizer log (final pack)
        self.dec_bank: tuple[int, float] = (0, 0.0)
        """(cap count, max courtyard half-extent) of the som_decoupling bank —
        the REAL bottom-side occupancy under the SoM (wave-11 P2). The lattice
        reserves the emission grid's own cells (placement.som_decoupling_cells)
        instead of blanking the whole SoM rect on both faces."""
        self.punch_free = True
        """Reservation policy of the CURRENT pack (wave-11 monotonicity guard).
        True = reserve only what genuinely pierces; False = the conservative
        SUPERSET (edge blocks and the SoM claim whole rectangles on both copper
        faces, a THT part punches its whole footprint bbox), which is exactly
        the pre-wave-11 model. build_plan runs the outline search under both
        and keeps the strictly better plan, ties to the conservative one."""

    @property
    def blocks(self) -> list[Block]:
        return self.edge_blocks + self.interior_blocks


def _edge_target(b: Block, edge: str, plan: Plan) -> float:
    """Ideal coordinate ALONG ``edge`` for block ``b`` — the J-affinity-weighted
    SoM mezzanine position projected onto the edge axis (x for N/S, y for W/E).
    A block talking mostly to J1 lands near J1's x/y on its edge, so the
    cross-subsystem airwire from this connector to its SoM strip stays short
    (LAW 5). Blocks with no J affinity fall back to the SoM-centre projection so
    they cluster centrally rather than at an arbitrary alphabetical slot."""
    jpos = {j.ref: (plan.som_x + j.x, plan.som_y + j.y) for j in plan.som.js}
    axis = 0 if edge in ("N", "S") else 1     # 0 -> use x, 1 -> use y
    aff = {jn: w for jn, w in b.j_aff.items() if jn in jpos}
    if aff:
        tot = sum(aff.values())
        return sum(w * jpos[jn][axis] for jn, w in aff.items()) / tot
    return (plan.som_x + plan.som.w / 2) if axis == 0 \
        else (plan.som_y + plan.som.h / 2)


def _pack_edges(plan: Plan, edge_of: dict[str, str]) -> None:
    """Place edge blocks flush on their edge; overflow spills to the next
    edge in a fixed cycle (recorded honestly in plan.spilled).

    Block (w, h) are the REAL 2-sided packed zone dimensions (the SAME box the
    PCB places), so along a N/S edge the block spans ``b.w`` and is ``b.h`` deep,
    and along a W/E edge it spans ``b.h`` and is ``b.w`` deep. The zone is NOT
    rotated (the PCB places it axis-aligned at this very (x, y)), so the span
    along the edge is the relevant dimension per edge — chosen here, never a
    width/height swap that would diverge from the PCB."""
    def span_of(b: Block, edge: str) -> float:
        return b.w if edge in ("N", "S") else b.h

    def depth_of(b: Block, edge: str) -> float:
        return b.h if edge in ("N", "S") else b.w

    spill_next = {"W": "S", "S": "N", "N": "E", "E": "W"}
    pending: dict[str, list[Block]] = {"N": [], "E": [], "S": [], "W": []}
    for b in plan.edge_blocks:
        pending[edge_of[b.name]].append(b)

    placed: dict[str, list[Block]] = {"N": [], "E": [], "S": [], "W": []}
    for _round in range(4):
        for edge in ("W", "S", "N", "E"):
            cap = (BOARD_H if edge in "WE" else BOARD_W) - 2 * EDGE_MARGIN
            def _trail(bb):       # trailing gap reserved after a block on this edge
                return CABLE_NEIGHBOR_GAP if _is_overmold_block(bb) else CLEAR
            used = sum(span_of(bb, edge) + _trail(bb) for bb in placed[edge])
            queue = sorted(pending[edge],
                           key=lambda bb: (-span_of(bb, edge), bb.name))
            pending[edge] = []
            for b in queue:
                if used + span_of(b, edge) <= cap:
                    placed[edge].append(b)
                    used += span_of(b, edge) + _trail(b)
                else:
                    nxt = spill_next[edge]
                    pending[nxt].append(b)
                    plan.spilled.append(
                        f"{b.name}: {edge} edge full -> {nxt}")
    for edge in ("N", "E", "S", "W"):
        # ORDER along the edge: a spec-pinned block (order_hint not None, set from
        # carrier/floorplan.json) keeps its DECLARED slot — the user's list order
        # along the edge wins. Auto blocks order by the J-affinity target
        # coordinate (NOT alphabetically): the connector that talks to J1 sits
        # near J1's x/y, etc. — the lever that holds the LAW-5 cross-subsystem
        # airwire under budget. Pinned blocks sort first (by their declared
        # slot), then auto blocks by target; deterministic, name breaks ties.
        def _ord_key(bb: Block, _edge: str = edge) -> tuple:
            if bb.order_hint is not None:
                return (0, float(bb.order_hint), bb.name)
            return (1, _edge_target(bb, _edge, plan), bb.name)
        blocks = sorted(placed[edge], key=_ord_key)
        if not blocks:
            continue
        span = (BOARD_H if edge in "WE" else BOARD_W)
        # RUN-END reach: the corner windows hold the M3 mounting-hole courtyards
        # (flat EDGE_MARGIN), but the FIRST/LAST block's facing fan-out reach
        # must be consumed here exactly as _pair_gap consumes it between blocks
        # — the run clamp was blind to it and the old per-zone emit snap merely
        # masked that by luck (measured: hdmi_tx's J14001 emitted 1.370 < its
        # 1.50 need from the SW corner hole once zones emit at exact poses).
        lo_r = blocks[0].fanout_reach[0 if edge in ("N", "S") else 2]
        hi_r = blocks[-1].fanout_reach[1 if edge in ("N", "S") else 3]
        lo, hi = EDGE_MARGIN + lo_r, span - EDGE_MARGIN - hi_r
        # CONTIGUOUS band packed with minimal CLEAR gaps, then SLID so its
        # weighted centroid sits on the mean of the blocks' J-affinity targets —
        # this hauls the whole edge run toward the SoM strips it talks to (so the
        # cross airwire is short) instead of spreading the blocks edge-to-edge
        # with big gaps. The slide is clamped to the edge margins (no overlap, no
        # off-board) and the order is already net-affinity sorted above.
        # per-PAIR along-edge gaps: a wide CABLE gap beside an overmold connector
        # (so two HDMI cables mate at once), the tight CLEAR elsewhere.
        gaps = [_pair_gap(blocks[i], blocks[i + 1])
                for i in range(len(blocks) - 1)]
        total = sum(span_of(bb, edge) for bb in blocks) + sum(gaps)
        offs: list[float] = []        # centre offset of each block from run start
        acc = 0.0
        for i, b in enumerate(blocks):
            sp = span_of(b, edge)
            offs.append(acc + sp / 2)
            acc += sp + (gaps[i] if i < len(gaps) else 0.0)
        # rigid-run slide that MINIMISES sum_i w_i (slot_i - target_i)^2 where
        # w_i is the block's total J-affinity: the run translates so the
        # STRONGEST-talking block (e.g. lcd, 30 nets to J3) gets the slot best
        # aligned with its strip, instead of an equal-weight centroid that lets a
        # weak block hog the spot next to the J. start* = sum w_i(target_i-off_i)
        # / sum w_i. Falls back to the equal-weight centroid if no affinity.
        wts = [max(sum(b.j_aff.values()), 0.0) + 0.05 for b in blocks]
        tgts = [_edge_target(b, edge, plan) for b in blocks]
        wsum = sum(wts)
        start = sum(
            w * (t - o) for w, t, o in zip(wts, tgts, offs, strict=False)
        ) / wsum
        start = max(lo, min(start, hi - total))   # clamp inside the edge
        pos = start
        for i, b in enumerate(blocks):
            b.edge = edge
            sp, dp = span_of(b, edge), depth_of(b, edge)
            # EDGE_INSET: every edge block is held this far OFF the board edge so
            # a flush off-board connector's PAD copper clears the board edge by
            # >= the copper_edge_clearance rule (0.3 mm). The connector mouth
            # still sits at the perimeter (LAW 6 — the cable/plug overhangs the
            # inset), but no pad is at the edge.
            # EXACT emission: blocks land at the run positions verbatim — there
            # is NO per-block position snap here (the old _r5 half-mm snap is
            # retired; it moved ADJACENT blocks independently by up to +/-0.25
            # each, eroding a reach-reserved pair gap by up to 0.5 mm —
            # measured: pd_input/usbc_otg reserved 0.75, emitted 0.5446 ->
            # J17001 starved 0.890 < 1.00 vs C32001).
            if edge == "N":
                b.x, b.y = round(pos, 4), EDGE_INSET
            elif edge == "S":
                b.x, b.y = round(pos, 4), round(BOARD_H - dp - EDGE_INSET, 4)
            elif edge == "W":
                b.x, b.y = EDGE_INSET, round(pos, 4)
            else:
                b.x, b.y = round(BOARD_W - dp - EDGE_INSET, 4), round(pos, 4)
            pos += sp + (gaps[i] if i < len(gaps) else 0.0)


_SPATIAL_TRACE = os.environ.get("SCHGEN_SPATIAL_TRACE", "") == "1"

OCC_TOP = 1
OCC_BOTTOM = 2
OCC_PUNCH = OCC_TOP | OCC_BOTTOM

_Comp = tuple[float, float, float, float, int]

_Rect = tuple[float, float, float, float,
              tuple[float, float, float, float],
              tuple[float, float, float, float], int, int, bool]


def _side_mask(side: str) -> int:
    return OCC_BOTTOM if side == "bottom" else OCC_TOP


def _occ_pair_active(a_mask: int, a_pmask: int, a_main: bool,
                     b_mask: int, b_pmask: int, b_main: bool) -> bool:
    """Whether two occupancy rects constrain each other. MAIN rects pair by
    face-mask intersection (the historical predicate — a mask-blind all-top
    population is byte-identical). COMPONENT sub-rects (opposite-face content
    box, THT punch boxes) pair ONLY when the two PARENT blocks' masks are
    disjoint: that cross-face pair is exactly the information a main check
    cannot carry, and every same-parent-face pair is already covered by the
    stricter main-vs-main composition — so with zero bottom blocks no comp
    check ever fires (the provable inertness rule, no analytic edge cases)."""
    if not (a_mask & b_mask):
        return False
    if a_main and b_main:
        return True
    return not (a_pmask & b_pmask)


def _halo4(reach: tuple, inset: tuple) -> tuple[float, float, float, float]:
    """Per-side spatial-index inflation: a rect interacts out to its own reach
    (its subjects' demand) OR its own courtyard overhang (-inset, the demand it
    imposes on a neighbour's subject), whichever is larger; never negative."""
    return (max(reach[0], -inset[0], 0.0), max(reach[1], -inset[1], 0.0),
            max(reach[2], -inset[2], 0.0), max(reach[3], -inset[3], 0.0))


def _spatial_bounds(far_ceil: float = 0.0,
                    max_reach: float | None = None) -> tuple[float, float]:
    """Static spatial-index bounds derived from the same constants/inputs the
    separation checks read: the per-side reach bound (the intelligent_need
    tier top + 0.05 quantization floor, raised to the max ACTUAL block reach
    value of this query set — reaches exceed the tier floor when a courtyard
    overhangs its zone box), and the interaction envelope (max over CLEAR,
    PLACE_CLEAR, the doubled reach bound, the overmold CABLE_NEIGHBOR_GAP and
    the contract far_min ceiling) used as the bucket size. Pure derivation
    from pre-pack inputs — recomputed per index, no state, never touched by
    solve results."""
    from schgen.generate.pcb.constants import PLACE_CLEAR
    from schgen.verify.fanout_gate import _TIER_TOP, _TIERS
    need_ceil = max(_TIER_TOP[0], max(n for _p, n, _b in _TIERS))
    reach_floor = round(_q.quant_credit(need_ceil), 4)
    reach_bound = max(reach_floor, max_reach or 0.0)
    envelope = max(CLEAR, PLACE_CLEAR, 2 * reach_bound,
                   CABLE_NEIGHBOR_GAP, far_ceil)
    return reach_bound, envelope


class _Occupancy:
    """Lattice occupancy for first-fit-nearest-anchor placement. STEP TIGHTENED
    2.0 -> 1.0: a finer lattice lets each interior block land closer to its
    anchor centroid (less quantisation slop), so net-sharing subsystems cluster
    tighter and the cross-subsystem airwire (the binding LAW-5 term) drops,
    letting the grow loop stop at a smaller board. Determinism is preserved (the
    scan order is still distance-sorted then lattice-index stable).

    SPATIAL NEIGHBORHOOD INDEX: rects are bucketed into a uniform grid
    (bucket = the static interaction envelope), each inserted over its own
    box inflated per side by ITS OWN halo (max of fan-out reach and courtyard
    overhang, _halo4) + CLEAR; a ``fits`` query scans only the cells covered
    by the candidate box inflated per side by the CANDIDATE'S own halo. Any
    rect outside those cells is provably non-interacting: the per-axis gap is
    max(CLEAR, rA - iB, rB - iA) and each one-sided term is bounded by the
    two halos (rX <= hX, -iX <= hX), so a gap-violating pair's inflated
    boxes always intersect and share a cell.
    The accept/reject boolean is identical to the exhaustive scan — pure
    indexing acceleration, no caching, index dies with the instance. Bucket
    lists append in insertion order and cells scan in fixed row-major order,
    so iteration is deterministic. ``SCHGEN_SPATIAL_TRACE=1`` swaps in the
    trace kernel (both scans per query, divergence raises); selected once at
    import — zero cost when off.

    TWO SURFACES + PUNCH (bottom-side P1): every rect carries a copper-face
    mask — OCC_TOP / OCC_BOTTOM for the two surfaces, OCC_PUNCH (both bits)
    for content that pierces or blocks both (THT pads, the mounting-hole
    corners, the SoM region + DF40 corridors, the connector edge bands). Two
    rects interact only when their masks intersect, so a bottom-assigned
    block may share XY with a top block while its ``comps`` sub-rects (the
    opposite-face content box + THT punch boxes) keep the content that
    really occupies the other surface separated. Historical add sites
    default to PUNCH and a mask-blind population is byte-identical to the
    single-surface allocator (an all-top board's comp checks are implied by
    the main-rect checks — contained boxes, zero reach)."""
    STEP = 1.0

    def __init__(self, far_ceil: float = 0.0,
                 max_reach: float | None = None) -> None:
        # (x, y, w, h, reach): reach is the occupant's D13 per-side fan-out reach
        # (W, E, N, S) — the extra clearance a multi-pin subject exposed on that side
        # needs. SoM/corner reservations carry the zero reach.
        self.rects: list[_Rect] = []
        reach_bound, envelope = _spatial_bounds(far_ceil, max_reach)
        if max(CLEAR, 2 * reach_bound) > envelope + 1e-9:
            raise AssertionError(
                f"spatial index: max pair interaction "
                f"{max(CLEAR, 2 * reach_bound):.4f} mm (CLEAR {CLEAR:g} vs "
                f"doubled reach bound {reach_bound:.4f}) exceeds the static "
                f"interaction envelope {envelope:.4f} mm (max over CLEAR, "
                f"PLACE_CLEAR, 2x reach bound, CABLE_NEIGHBOR_GAP "
                f"{CABLE_NEIGHBOR_GAP:g}, contract far_min ceiling "
                f"{far_ceil:g}) — the derived bounds drifted; fix "
                f"_spatial_bounds, never widen a gate")
        self._reach_bound = reach_bound
        self._bucket = envelope
        self._cells: dict[tuple[int, int], list[_Rect]] = {}

    def _add_one(self, x: float, y: float, w: float, h: float,
                 reach: tuple, inset: tuple, mask: int, pmask: int,
                 main: bool) -> None:
        for c in _halo4(reach, inset):
            if c > self._reach_bound:
                raise AssertionError(
                    f"spatial index: fan-out halo component {c} mm exceeds "
                    f"the static reach bound {self._reach_bound:.4f} mm "
                    f"(max of the intelligent_need tier top + 0.05 "
                    f"floor and this query set's declared max reach) — "
                    f"this rect was not in the bound derivation; re-derive "
                    f"_spatial_bounds before indexing it")
        rect = (x, y, w, h, reach, inset, mask, pmask, main)
        self.rects.append(rect)
        b = self._bucket
        rw_, re_, rn_, rs_ = _halo4(reach, inset)
        iy0 = int((y - rn_ - CLEAR) // b)
        iy1 = int((y + h + rs_ + CLEAR) // b)
        for ix in range(int((x - rw_ - CLEAR) // b),
                        int((x + w + re_ + CLEAR) // b) + 1):
            for iy in range(iy0, iy1 + 1):
                self._cells.setdefault((ix, iy), []).append(rect)

    def add(self, x: float, y: float, w: float, h: float,
            reach: tuple[float, float, float, float] = _ZeroReach,
            inset: tuple[float, float, float, float] = _ZeroReach,
            mask: int = OCC_PUNCH, comps: tuple[_Comp, ...] = ()) -> None:
        """Occupy ``mask``'s face(s) with the main rect plus each zone-local
        ``comps`` sub-rect on ITS OWN mask (the opposite-face content box and
        the THT punch boxes of a placed block) — the both-side truth of a
        2-sided zone, so a later opposite-face placement is separated from
        the content that really penetrates, not from the whole block."""
        self._add_one(x, y, w, h, reach, inset, mask, mask, True)
        for dx, dy, cw, ch, cm in comps:
            self._add_one(round(x + dx, 4), round(y + dy, 4), cw, ch,
                          _ZeroReach, _ZeroReach, cm, mask, False)

    def _remove_one(self, x: float, y: float, w: float, h: float,
                    reach: tuple, inset: tuple, mask: int, pmask: int,
                    main: bool) -> None:
        rect = (x, y, w, h, reach, inset, mask, pmask, main)
        try:
            self.rects.remove(rect)
        except ValueError:
            return
        b = self._bucket
        rw_, re_, rn_, rs_ = _halo4(reach, inset)
        iy0 = int((y - rn_ - CLEAR) // b)
        iy1 = int((y + h + rs_ + CLEAR) // b)
        for ix in range(int((x - rw_ - CLEAR) // b),
                        int((x + w + re_ + CLEAR) // b) + 1):
            for iy in range(iy0, iy1 + 1):
                lst = self._cells.get((ix, iy))
                if lst is not None:
                    lst.remove(rect)

    def remove(self, x: float, y: float, w: float, h: float,
               reach: tuple[float, float, float, float] = _ZeroReach,
               inset: tuple[float, float, float, float] = _ZeroReach,
               mask: int = OCC_PUNCH, comps: tuple[_Comp, ...] = ()) -> None:
        """Drop a previously-added rect (+ its components) for the iterative
        re-placement pass — tuples must match the ``add`` byte-for-byte."""
        self._remove_one(x, y, w, h, reach, inset, mask, mask, True)
        for dx, dy, cw, ch, cm in comps:
            self._remove_one(round(x + dx, 4), round(y + dy, 4), cw, ch,
                             _ZeroReach, _ZeroReach, cm, mask, False)

    def _fits_exhaustive(self, x: float, y: float, w: float, h: float,
                         reach: tuple[float, float, float, float] = _ZeroReach,
                         inset: tuple[float, float, float, float] = _ZeroReach,
                         mask: int = OCC_PUNCH,
                         comps: tuple[_Comp, ...] = ()) -> bool:
        if x < CLEAR or y < CLEAR or x + w > BOARD_W - CLEAR \
                or y + h > BOARD_H - CLEAR:
            return False
        for rx, ry, rw, rh, r_reach, r_inset, r_mask, r_pm, r_main \
                in self.rects:
            # D13 DIRECTIONAL gap: on each axis the required separation is the
            # PAIR-EXACT facing composition (_fanout_sep — MAX of one-sided
            # demands, inset-credited), never below CLEAR. Separated if the gap
            # holds on EITHER axis (blocks don't overlap). _occ_pair_active
            # gates which rect pairs constrain each other at all (face masks
            # + the comp parent-disjoint rule).
            if not _occ_pair_active(mask, mask, True, r_mask, r_pm, r_main):
                continue
            gx = max(CLEAR, _fanout_sep(reach, inset, r_reach, r_inset,
                                        "E" if x <= rx else "W"))
            gy = max(CLEAR, _fanout_sep(reach, inset, r_reach, r_inset,
                                        "S" if y <= ry else "N"))
            if not (x + w + gx <= rx or rx + rw + gx <= x
                    or y + h + gy <= ry or ry + rh + gy <= y):
                return False
        for dx, dy, cw, ch, cm in comps:
            cx0, cy0 = x + dx, y + dy
            for rx, ry, rw, rh, r_reach, r_inset, r_mask, r_pm, r_main \
                    in self.rects:
                if not _occ_pair_active(cm, mask, False,
                                        r_mask, r_pm, r_main):
                    continue
                gx = max(CLEAR, _fanout_sep(
                    _ZeroReach, _ZeroReach, r_reach, r_inset,
                    "E" if cx0 <= rx else "W"))
                gy = max(CLEAR, _fanout_sep(
                    _ZeroReach, _ZeroReach, r_reach, r_inset,
                    "S" if cy0 <= ry else "N"))
                if not (cx0 + cw + gx <= rx or rx + rw + gx <= cx0
                        or cy0 + ch + gy <= ry or ry + rh + gy <= cy0):
                    return False
        return True

    def _fits_hashed(self, x: float, y: float, w: float, h: float,
                     reach: tuple[float, float, float, float] = _ZeroReach,
                     inset: tuple[float, float, float, float] = _ZeroReach,
                     mask: int = OCC_PUNCH,
                     comps: tuple[_Comp, ...] = ()) -> bool:
        if x < CLEAR or y < CLEAR or x + w > BOARD_W - CLEAR \
                or y + h > BOARD_H - CLEAR:
            return False
        b = self._bucket
        cells = self._cells
        cw_, ce_, cn_, cs_ = _halo4(reach, inset)
        iy0 = int((y - cn_) // b)
        iy1 = int((y + h + cs_) // b)
        for ix in range(int((x - cw_) // b), int((x + w + ce_) // b) + 1):
            for iy in range(iy0, iy1 + 1):
                lst = cells.get((ix, iy))
                if not lst:
                    continue
                for rx, ry, rw, rh, r_reach, r_inset, r_mask, r_pm, r_main \
                        in lst:
                    if not _occ_pair_active(mask, mask, True,
                                            r_mask, r_pm, r_main):
                        continue
                    gx = max(CLEAR, _fanout_sep(reach, inset, r_reach, r_inset,
                                                "E" if x <= rx else "W"))
                    gy = max(CLEAR, _fanout_sep(reach, inset, r_reach, r_inset,
                                                "S" if y <= ry else "N"))
                    if not (x + w + gx <= rx or rx + rw + gx <= x
                            or y + h + gy <= ry or ry + rh + gy <= y):
                        return False
        for dx, dy, cw2, ch2, cm in comps:
            # a violating occupant's insertion window (its own halo + CLEAR)
            # always covers the zero-halo component box (required gap
            # max(CLEAR, r_reach) <= r_halo + CLEAR), so scanning the
            # component's own cells is exhaustive-equivalent.
            cx0, cy0 = x + dx, y + dy
            jy0 = int(cy0 // b)
            jy1 = int((cy0 + ch2) // b)
            for jx in range(int(cx0 // b), int((cx0 + cw2) // b) + 1):
                for jy in range(jy0, jy1 + 1):
                    lst = cells.get((jx, jy))
                    if not lst:
                        continue
                    for rx, ry, rw, rh, r_reach, r_inset, r_mask, r_pm, \
                            r_main in lst:
                        if not _occ_pair_active(cm, mask, False,
                                                r_mask, r_pm, r_main):
                            continue
                        gx = max(CLEAR, _fanout_sep(
                            _ZeroReach, _ZeroReach, r_reach, r_inset,
                            "E" if cx0 <= rx else "W"))
                        gy = max(CLEAR, _fanout_sep(
                            _ZeroReach, _ZeroReach, r_reach, r_inset,
                            "S" if cy0 <= ry else "N"))
                        if not (cx0 + cw2 + gx <= rx or rx + rw + gx <= cx0
                                or cy0 + ch2 + gy <= ry
                                or ry + rh + gy <= cy0):
                            return False
        return True

    def _fits_traced(self, x: float, y: float, w: float, h: float,
                     reach: tuple[float, float, float, float] = _ZeroReach,
                     inset: tuple[float, float, float, float] = _ZeroReach,
                     mask: int = OCC_PUNCH,
                     comps: tuple[_Comp, ...] = ()) -> bool:
        ref = self._fits_exhaustive(x, y, w, h, reach, inset, mask, comps)
        new = self._fits_hashed(x, y, w, h, reach, inset, mask, comps)
        if ref is not new:
            raise AssertionError(
                f"spatial index DIVERGENCE: exhaustive={ref} hashed={new} "
                f"for query x={x} y={y} w={w} h={h} reach={reach} "
                f"inset={inset} mask={mask} comps={comps} over "
                f"{len(self.rects)} rects (bucket={self._bucket:.4f}, "
                f"reach bound={self._reach_bound:.4f})")
        return new

    fits = _fits_traced if _SPATIAL_TRACE else _fits_hashed

    def place_near(self, ax: float, ay: float, w: float,
                   h: float, reach: tuple[float, float, float, float] = _ZeroReach,
                   inset: tuple[float, float, float, float] = _ZeroReach,
                   mask: int = OCC_PUNCH, comps: tuple[_Comp, ...] = (),
                   win: tuple[float, float, float, float] | None = None
                   ) -> tuple[float, float, float, float] | None:
        """Deterministic: scan lattice positions sorted by city-block distance
        of the block CENTER from the anchor; first fit wins. The block is placed
        AXIS-ALIGNED (no width/height swap) — the PCB places this same zone box
        un-rotated at this very (x, y), so a rotation here would diverge.

        ``win`` = (x_lo, x_hi, y_lo, y_hi) restricts the lattice to an origin
        window. It is an ACCELERATION, never a policy: the only caller is the
        re-seat retry, which supplies a window its own eviction geometry proves
        contains every cell this candidate can newly occupy, so the first fit
        inside the window IS the first fit over the whole board (every excluded
        cell provably does not fit). The legality predicate is untouched, and
        the equivalence is pinned by a replay test.

        EXPANDING-RING (I2): byte-identical to the historical build-all-cells-
        then-sort scan, but it materialises cells lazily in nondecreasing true
        city-block distance and STOPS at the first fitting bucket instead of
        sorting all ~44k lattice cells on every call. The emitted order is
        exactly ``(round(d, 1), x, y)`` ascending — same first-fit result.

        Correctness rests on two invariants:
          * the per-axis cost uses the SAME sub-expression ``|coord + half - a|``
            as the flat scan, so ``xcost + ycost`` is bit-identical to
            ``|x + w/2 - ax| + |y + h/2 - ay|`` and ``round(,1)`` buckets match
            even on banker's-rounding boundaries (true d = D + 0.05 -> bucket D);
          * a rounded-distance bucket is finalised (sorted by ``(x, y)`` and
            first-fit tested) only once the merge frontier's true distance
            exceeds the bucket value by more than the 0.05 rounding half-width,
            so no later cell can still fall into an already-tested bucket.
        """
        s = self.STEP
        nx = int(BOARD_W / s) + 1
        ny = int(BOARD_H / s) + 1
        hw = w / 2
        hh = h / 2
        # sorted (cost, coord) along each axis; ascending cost, coord tie-break.
        wx0, wx1, wy0, wy1 = win or (-BOARD_W, 2 * BOARD_W,
                                     -BOARD_H, 2 * BOARD_H)
        xs = sorted((abs(ix * s + hw - ax), ix * s) for ix in range(nx)
                    if wx0 <= ix * s <= wx1)
        ys = sorted((abs(iy * s + hh - ay), iy * s) for iy in range(ny)
                    if wy0 <= iy * s <= wy1)
        if not xs or not ys:
            return None
        _HALF = 0.05 + 1e-9    # rounding half-width + float margin
        # merge-frontier heap over the (sorted-x) x (sorted-y) cost matrix; each
        # (i, j) pushed once. Cells stream out in nondecreasing true distance.
        heap = [(xs[0][0] + ys[0][0], 0, 0)]
        seen = {(0, 0)}
        buckets: dict[float, list[tuple[float, float]]] = {}
        bkeys: list[float] = []    # min-heap of DISTINCT pending bucket keys
        while heap:
            _d, i, j = heappop(heap)
            xcost, x = xs[i]
            ycost, y = ys[j]
            key = round(xcost + ycost, 1)
            cell = buckets.get(key)
            if cell is None:
                buckets[key] = [(x, y)]
                heappush(bkeys, key)
            else:
                cell.append((x, y))
            if i + 1 < len(xs) and (i + 1, j) not in seen:
                seen.add((i + 1, j))
                heappush(heap, (xs[i + 1][0] + ys[j][0], i + 1, j))
            if j + 1 < len(ys) and (i, j + 1) not in seen:
                seen.add((i, j + 1))
                heappush(heap, (xs[i][0] + ys[j + 1][0], i, j + 1))
            frontier = heap[0][0] if heap else float("inf")
            # finalise every front bucket that can no longer receive a cell.
            # Cells arrive in nondecreasing true distance, so a bucket only goes
            # final once the frontier clears it by more than the rounding half-
            # width; bkeys keeps those front keys cheap to reach in order.
            thresh = frontier - _HALF
            while bkeys and bkeys[0] <= thresh:
                for x, y in sorted(buckets.pop(heappop(bkeys))):
                    if self.fits(x, y, w, h, reach, inset, mask, comps):
                        return x, y, w, h
        # heap drained: no unfinalised cell remains — sweep the tail in order.
        while bkeys:
            for x, y in sorted(buckets.pop(heappop(bkeys))):
                if self.fits(x, y, w, h, reach, inset, mask, comps):
                    return x, y, w, h
        return None


def _interior_dims(area: float) -> tuple[float, float]:
    h = _q.placeholder_zone_half_mm(min(30.0, max(8.0, (area / 1.6) ** 0.5)))
    w = _q.placeholder_zone_half_mm(max(8.0, area / h))
    return w, h


def _zone_anchor(plan: Plan, zone: str) -> tuple[float, float]:
    sx, sy = plan.som_x, plan.som_y
    sw, sh = plan.som.w, plan.som.h
    return {
        "N": ((sx + sw / 2), sy / 2),
        "S": ((sx + sw / 2), (sy + sh + BOARD_H) / 2),
        "W": (sx / 2, sy + sh / 2),
        "E": ((sx + sw + BOARD_W) / 2, BOARD_H / 2),
    }[zone]


def build_plan(sheets, link_result, regs, spec: FloorplanSpec | None = None
               ) -> Plan:
    som = extract_som()
    # DERIVE the outline FIRST, then rebind the module globals so every
    # consumer downstream (Plan.__init__, the packer, the SVG/MD, the PCB
    # foundation) reads the derived dimensions instead of a hardcoded box.
    global BOARD_W, BOARD_H, OUTLINE_NOTE
    outline = derive_outline(sheets, som)
    BOARD_W, BOARD_H, OUTLINE_NOTE = outline.w, outline.h, outline.note
    plan = Plan(som)
    aff = _j_affinity(sheets, link_result)
    j_edge = _j_edge_map(som)
    reg_sheets = {r.sheet for r in regs}
    by_name = {sc.name: sc for sc in sheets}

    # DECLARATIVE override: carrier/floorplan.json (optional). A subsystem named
    # under an edge is PINNED to that edge in the listed order; an interior entry
    # sets its anchor. Everything else keeps the auto-derivation below. The spec
    # is validated against the real sheet names here, so a typo FAILS the build.
    # ``spec`` may be INJECTED (T1 P4 spec-injection, IM1: the compose driver
    # evaluates candidate SpecEdits without touching the file); the default
    # None path reads carrier/floorplan.json exactly as before (byte-identical).
    valid_names = {sc.name for sc in sheets if not sc.name.startswith("som_j")}
    if spec is None:
        spec = load_floorplan_spec(valid_names=valid_names)
    spec_edge_of = spec.edge_of if spec else {}
    spec_edge_order = spec.edge_order if spec else {}
    spec_interior = spec.interior if spec else {}

    edge_of: dict[str, str] = {}
    interior: list[Block] = []
    for sc in sorted(sheets, key=lambda s: s.name):
        if sc.name.startswith("som_j") or sc.name == "som_decoupling":
            continue            # receptacles ARE the SoM block; som_decoupling is
            #                     placed BOTTOM-side under the SoM core, no block
        c = sc.circuit
        conns = []
        for ref, part in sorted(c.parts.items()):
            fam = next((f for f in _EDGE_FAMILIES if part.value == f), None)
            if fam:
                w, h = part_dims(part.footprint)
                conns.append((ref, part.value, w, h))
        reserved = sorted({m.group(0)
                           for n, pt in sorted(c.port_types.items())
                           if pt.expect
                           for m in _DEFERRED_EDGE.finditer(pt.expect)})
        # spec edge pin forces a sheet onto an edge even if it has no off-board
        # connector family (e.g. a header subsystem the user wants edge-flush);
        # an interior-spec entry keeps it interior. Otherwise auto: a connector/
        # reservation makes it an edge block.
        spec_e = spec_edge_of.get(sc.name)
        auto_edge = bool(conns or reserved)
        is_edge = spec_e is not None or (auto_edge and sc.name not in spec_interior)
        b = Block(name=sc.name, kind="edge" if is_edge else "interior",
                  conns=conns, reserved=reserved,
                  n_parts=len(c.parts), j_aff=aff.get(sc.name, {}))
        if b.kind == "edge":
            if spec_e is not None:
                edge_of[b.name] = spec_e
                b.order_hint = spec_edge_order.get(b.name)
                b.pinned = True
            else:
                dom = _dominant_j(b.j_aff)
                edge_of[b.name] = j_edge.get(dom or "", "N")
            plan.edge_blocks.append(b)
        else:
            interior.append(b)

    # interior zones: the regulator/bringup/power cluster keeps to the
    # SoM-free side (no mezzanine connector faces E in the mirrored view);
    # everything else follows its dominant J edge, with an EXCLUSIVE
    # port-sharing pull toward an edge sheet (usb_pd follows the pd_input
    # inlet via the CC nets — nets shared by exactly those two sheets).
    port_sheets: dict[str, set[str]] = {}
    from schgen.core.model import NetClass
    for sc in sheets:
        if sc.name.startswith("som_j"):
            continue        # the mezzanine carries almost every port
        for net in sc.circuit.nets.values():
            if net.net_class == NetClass.PORT:
                port_sheets.setdefault(net.name, set()).add(sc.name)
    for b in interior:
        # DECLARATIVE override: an interior-spec entry pins the anchor. "near"
        # anchors at the named subsystem's block ("@name", the same form the
        # auto port-pair pull uses); "side" anchors at the N/E/S/W zone.
        sp = spec_interior.get(b.name)
        if sp is not None:
            b.pinned = True
            b.pull = sp.get("pull")
            sv = sp.get("side", "E")
            if sv in _LAYER_SIDES:
                b.layer_pref = sv
                sv = "E"
            if "layer" in sp:
                b.layer_pref = sp["layer"]
            if "near" in sp:
                b.zone = f"@{sp['near']}"
            else:
                b.zone = sv
            continue
        dom = _dominant_j(b.j_aff)
        if (b.name in reg_sheets
                or b.name.startswith(_project_spec().reg_band_prefixes)):
            b.zone = "E"
            continue
        b.zone = j_edge[dom] if dom else "E"
        best, best_n = None, 0
        for eb in plan.edge_blocks:
            n = sum(1 for net, ss in port_sheets.items()
                    if ss == {b.name, eb.name})     # exclusive pair nets
            if n > best_n:
                best, best_n = eb, n
        if best_n >= 2 and best is not None:
            b.zone = f"@{best.name}"     # anchor at that edge block

    # subsystem AFFINITY (placement attraction): for every multi-sheet net, the
    # sheets it touches form a clique; accumulate a pairwise weight inversely
    # proportional to the net's fan-out (a 2-sheet SIGNAL net pulls hard; a
    # board-wide rail/GND barely pulls — it is long no matter where blocks sit).
    # A sheet's pull toward the centered SoM is tracked separately. Interior
    # blocks are then dropped near the weighted centroid of their already-placed
    # net neighbours + the SoM, so cross-subsystem airwires stay short (LAW 5).
    sheets_of_net: dict[str, set[str]] = {}
    for sc in sheets:
        if sc.name.startswith("som_j"):
            continue
        for net in sc.circuit.nets.values():
            sheets_of_net.setdefault(net.name, set()).add(sc.name)
    # SoM membership: a net also touching a som_j sheet pulls toward the SoM.
    som_nets: set[str] = set()
    for sc in sheets:
        if sc.name.startswith("som_j"):
            for net in sc.circuit.nets.values():
                som_nets.add(net.name)
    affinity: dict[str, dict[str, float]] = {}
    som_pull: dict[str, float] = {}
    for nname, ss in sheets_of_net.items():
        k = len(ss)
        if k < 2 and nname not in som_nets:
            continue
        denom = max(1, (k + (1 if nname in som_nets else 0)))
        w = 1.0 / denom
        members = sorted(ss)
        for i, a in enumerate(members):
            if nname in som_nets:
                som_pull[a] = som_pull.get(a, 0.0) + w
            for b in members[i + 1:]:
                affinity.setdefault(a, {})[b] = \
                    affinity.get(a, {}).get(b, 0.0) + w
                affinity.setdefault(b, {})[a] = \
                    affinity.get(b, {}).get(a, 0.0) + w

    # SHARED SIZING: every block's (w, h) is the REAL 2-sided packed zone of its
    # subsystem — the SAME box the PCB places. Importing here (not at module top)
    # keeps the floorplan importable without the PCB module's heavier deps and
    # avoids a circular import (pcb imports floorplan for build_plan).
    from schgen.generate import pcb as _pcb
    zg = _pcb.subsystem_zone_geometry(two_side=True, spec=spec)
    zbox = dict(zg.zone_box)
    # a block with no packed zone (a reservation-only deferred-connector block,
    # or the mounting-holes-only `mechanical` sheet whose holes are corner-forced
    # and never zone-packed) still needs a landing rectangle — size it to its
    # courtyard reservation via the small area estimate; the rest use the packer.
    for b in plan.edge_blocks + interior:
        if b.name not in zbox:
            a = sheet_area(by_name[b.name].circuit, ROUTE_FACTOR)
            zbox[b.name] = (_q.placeholder_zone_half_mm(max(12.0, a ** 0.5)),
                            _q.placeholder_zone_half_mm(max(8.0, a ** 0.5)))

    # D13 FAN-OUT CLEARANCE: each block's fan-out reach (extra clearance a multi-pin
    # subject near the block edge needs beyond a neighbour's zone, not already met by
    # its zone-internal margin). Threaded into the edge-run gaps (_pair_gap) and the
    # interior occupancy lattice so an IC on a block boundary keeps its fan-out floor
    # to the foreign part next door — retiring the cross-block offenders (motor_sense
    # XT60 vs power IC, ethernet magnetics vs a bringup test point) without a flat
    # halo. Zero for a block with no under-margined multi-pin subject -> tight CLEAR.
    for b in plan.edge_blocks + interior:
        b.fanout_reach, b.fanout_inset = _block_fanout_reach(b.name, zg)

    # MULTI-SHAPE candidate sets for the pack search: per INTERIOR block, the
    # (w, h, reach, inset, side, comps) of every legal shape (index 0 == the
    # flat zbox/reach above, so a block without a registered set behaves
    # exactly as before; side + occupancy components are the bottom-side P1
    # degree of freedom). Edge blocks are connector-seated -> FIXED, never
    # shape-searched (LAW 6).
    comps_by_policy: dict[bool, dict[tuple[str, int], tuple]] = {}
    for _pad_punch in (True, False):
        _co: dict[tuple[str, int], tuple] = {}
        for b in plan.edge_blocks + interior:
            if b.name in zg.zone_box:
                flat_refs = (*zg.top_off.get(b.name, {}),
                             *zg.bot_off.get(b.name, {}))
                _co[(b.name, 0)] = _zone_components(
                    zg, zg.top_off.get(b.name, {}),
                    zg.bot_off.get(b.name, {}),
                    {r: zg.zone_extra_rot[r] for r in flat_refs
                     if r in zg.zone_extra_rot}, "top", pad_punch=_pad_punch)
            for k, s in enumerate(zg.shapes.get(b.name, ())):
                if k:
                    _co[(b.name, k)] = _zone_components(
                        zg, s.top_off, s.bot_off, s.extra_rot, s.side,
                        mods=s.mirror, pad_punch=_pad_punch)
        comps_by_policy[_pad_punch] = _co
    from schgen.generate.pcb.footprint import _footprint_bbox as _dec_bbox
    from schgen.generate.pcb.footprint import resolve_mod as _dec_resolve
    _dec_sheet = by_name.get("som_decoupling")
    _dec_boxes = [] if _dec_sheet is None else [
        _dec_bbox(m) for m in
        (_dec_resolve(p.footprint)
         for _r, p in sorted(_dec_sheet.circuit.parts.items()))
        if m is not None]
    plan.dec_bank = (len(_dec_boxes),
                     max((max((bb[0] ** 2 + bb[1] ** 2) ** 0.5,
                              (bb[2] ** 2 + bb[1] ** 2) ** 0.5,
                              (bb[0] ** 2 + bb[3] ** 2) ** 0.5,
                              (bb[2] ** 2 + bb[3] ** 2) ** 0.5)
                          for bb in _dec_boxes), default=0.0))
    sets_by_policy: dict[bool, dict[str, list[tuple]]] = {}
    for _pp, _co in comps_by_policy.items():
        _ss: dict[str, list[tuple]] = {}
        for b in interior:
            variants = zg.shapes.get(b.name)
            if not variants or len(variants) < 2:
                continue
            _ss[b.name] = [(zbox[b.name][0], zbox[b.name][1],
                            b.fanout_reach, b.fanout_inset, "top",
                            _co.get((b.name, 0), ()))] + \
                [(s.w, s.h, *_shape_fanout_reach(s, zg), s.side,
                  _co.get((b.name, k), ()))
                 for k, s in enumerate(variants) if k]
        sets_by_policy[_pp] = _ss
    shape_sets = sets_by_policy[True]
    max_reach = max((max(r, -i) for b in plan.edge_blocks + interior
                     for r, i in zip(b.fanout_reach, b.fanout_inset,
                                     strict=True)), default=0.0)
    max_reach = max(max_reach,
                    max((max(r, -i) for ss in shape_sets.values()
                         for _w, _h, rch, ins, _sd, _cc in ss
                         for r, i in zip(rch, ins, strict=True)), default=0.0))

    # number of placed (non-SoM) subsystems == the gate's n_subsystems, so the
    # grow loop can size the board against the SAME LAW-5 cross-airwire budget.
    # The budget constant is read FROM the gate (lazily, to avoid a circular
    # import: floorplan <- pcb <- ratsnest_gate) so the two can never drift. Match
    # the gate's count EXACTLY: it tallies sheets that have a non-mounting-hole
    # footprint on board (a mounting-hole-only sheet like `mechanical` is excluded
    # there, so it must be excluded here too or the budget would be over-stated).
    from schgen.verify.ratsnest_gate import CROSS_K as CROSS_BUDGET_K
    n_sub = sum(1 for sc in sheets
                if not sc.name.startswith("som_j")
                and any("MountingHole" not in pt.footprint
                        for pt in sc.circuit.parts.values()))

    # ---- T1 P6-wire: composition-legalizer inputs (ONCE per build_plan) ----
    # TermIndex + zone-local metrics + the D13 channel-demand map + T2's
    # escape corridors, threaded into every _attempt_pack call (spec D-3:
    # every candidate board is legalized; the compaction objective runs only
    # at the fixed-outline call + the final re-pack). Channel demand proxy =
    # EXCLUSIVE pair nets (nets whose sheet-set is exactly {a, b} — the
    # pair's private harness): position-independent, deterministic, and it
    # matches the emitted MST pair count on the measured hotspot pairs
    # (pd_input|usb_pd: 8 == the 8 MST cross-airwires measured at P0).
    from schgen.generate import floorplan_compose as _fc
    compose_index = _fc.build_term_index([sc.name for sc in sheets])
    far_ceil = max((t.bound or 0.0 for t in compose_index.terms
                    if t.kind == "far_min"), default=0.0)
    compose = None
    if compose_index.hard:
        _channels: dict[frozenset, int] = {}
        for _ss in sheets_of_net.values():
            if len(_ss) == 2:
                _key = frozenset(_ss)
                _channels[_key] = _channels.get(_key, 0) + 1
        compose = (compose_index, _fc.zone_local_metrics(zg), _channels,
                   _fc.escape_corridors(), _fc.zone_shape_metrics(zg))

    # GROW the derived outline (keeping the SoM centered + the seed aspect) until
    # the edge-pinned + interior-anchored layout (a) fits every REAL packed block
    # AND (b) holds its cross-subsystem airwire under the LAW-5 budget. (b) is the
    # honest routing-headroom criterion the floorplan is sized for: a board too
    # small for the airwire budget is, by the gate's own definition, not a valid
    # layout, so the placer grows it just enough — it does NOT relax the gate. The
    # SAME shared sizing drives both this floorplan and the PCB placement, so
    # FLOORPLAN.svg and the PCB ratsnest cannot diverge. The estimate is the
    # gate's own kernel on the STEP-3 pad population (``_cross_estimator``) —
    # no calibrated constants; the strict gate in `schgen board` still judges.
    est_cross = _cross_estimator(plan, zg, sheets)

    _pristine = {b.name: (b.shape_idx, b.fanout_reach, b.fanout_inset)
                 for b in plan.edge_blocks + interior}
    _SNAP_FIELDS = _SEAT_FIELDS

    def _reset_shapes() -> None:
        """Re-arm every block's pre-search shape state. _choose_conn_shapes
        reads a block's CURRENT reach as the incumbent to restore, so a second
        search must never start from the first search's chosen mirror."""
        for b in plan.edge_blocks + interior:
            b.shape_idx, b.fanout_reach, b.fanout_inset = _pristine[b.name]

    def _plan_snapshot() -> tuple:
        return (BOARD_W, BOARD_H, plan.som_x, plan.som_y, plan.punch_free,
                list(plan.spilled), list(plan.composition),
                {b.name: tuple(getattr(b, f) for f in _SNAP_FIELDS)
                 for b in plan.edge_blocks + interior})

    def _plan_restore(s: tuple) -> None:
        global BOARD_W, BOARD_H
        BOARD_W, BOARD_H = s[0], s[1]
        plan.som_x, plan.som_y, plan.punch_free = s[2], s[3], s[4]
        plan.spilled, plan.composition = s[5], s[6]
        for b in plan.edge_blocks + interior:
            for f, v in zip(_SNAP_FIELDS, s[7][b.name], strict=True):
                setattr(b, f, v)

    def _guarded(run):
        """Run the FREED-reservation pass. RuntimeError is the packer's own
        infeasibility signal (no outline packs / the fixed outline does not
        hold) — the greedy first-fit can fail on a strictly LARGER free set, so
        that outcome means the freed plan simply loses to the conservative one.
        Every other exception propagates: only declared infeasibility is
        absorbed, and even that lands as the registered rejection event."""
        try:
            return run(True)
        except RuntimeError:
            return None

    # DECLARATIVE fixed outline: carrier/floorplan.json {"outline":{"w","h"}}
    # PINS the board dimensions. The placer still packs the same blocks into that
    # exact box and the REAL LAW-5 gate in `schgen board` still judges — a fixed
    # board too small for the airwire budget is reported by that gate, not relaxed
    # here. If the blocks don't even fit the fixed box, FAIL with a clear message.
    if isinstance(spec.outline if spec else "auto", tuple):
        BOARD_W, BOARD_H = spec.outline          # type: ignore[misc]
        plan.som_x = _q.som_pose_half_mm((BOARD_W - som.w) / 2 + SOM_DX)
        plan.som_y = _q.som_pose_half_mm((BOARD_H - som.h) / 2 + SOM_DY)

        def _fixed_pack(pad_punch: bool) -> float:
            plan.punch_free = pad_punch
            if not _attempt_pack(plan, interior, edge_of, zbox, affinity,
                                 som_pull, compose=compose, compact=True,
                                 far_ceil=far_ceil, max_reach=max_reach,
                                 shapes=sets_by_policy[pad_punch],
                                 comps_of=comps_by_policy[pad_punch],
                                 side_est=est_cross):
                raise RuntimeError(
                    "floorplan: the REAL 2-sided packed blocks do not fit the "
                    f"fixed outline {BOARD_W:g}x{BOARD_H:g} declared in "
                    "carrier/floorplan.json — enlarge it or use "
                    "\"outline\":\"auto\"")
            _choose_conn_shapes(plan, interior, edge_of, zbox, affinity,
                                som_pull, compose, True, far_ceil, max_reach,
                                sets_by_policy[pad_punch],
                                comps_by_policy[pad_punch], zg, est_cross)
            return est_cross(plan.edge_blocks + interior)

        _fb_entry = _fb.snapshot()
        _reset_shapes()
        est_real = _fixed_pack(False)
        cons_snap, cons_fb = _plan_snapshot(), _fb.snapshot()
        _fb.restore(_fb_entry)
        _reset_shapes()
        free_er = _guarded(_fixed_pack)
        if free_er is not None and free_er < est_real - 1e-6:
            est_real = free_er
        else:
            _plan_restore(cons_snap)
            _fb.restore(cons_fb)
            _fb.record("punch_free_plan_rejected")
        plan.interior_blocks = interior
        budget = CROSS_BUDGET_K * (BOARD_W * BOARD_H) ** 0.5 * n_sub
        OUTLINE_NOTE = (f"FIXED outline {BOARD_W:g}x{BOARD_H:g} mm declared in "
                        f"carrier/floorplan.json; estimated cross-subsystem "
                        f"airwire {est_real:.0f} mm (LAW-5 budget {budget:.0f} "
                        f"mm — the REAL gate in `schgen board` is the arbiter)")
        return plan

    # SMALLEST-AREA outline search (replaces the single seed-aspect grow line).
    # The old loop locked the seed aspect (~1.08), which forced a near-square
    # ~200x185 even though the dominant edge->SoM airwires are SHORTER on a board
    # whose SHORT axis is the SoM's tall axis. Here the placer GROWS from the seed
    # along a small, fixed family of aspect ratios and keeps the SMALLEST-AREA
    # board that (a) fits every REAL packed block AND (b) holds the estimated
    # cross-subsystem airwire under the LAW-5 budget. The REAL gate in `schgen
    # board` is still the strict arbiter (a mis-estimate could only make the
    # board a touch bigger, never relax the gate). Deterministic: aspects + grow
    # steps are a fixed sorted grid, the smallest area wins, (w, h) breaks ties
    # — no dict-order dependence.
    seed_aspect = round(outline.w / outline.h, 4)
    # landscape aspects only (W >= H): the SoM is wider than tall and the W-edge
    # FMC/camera/LCD stack sets the height floor, so a portrait board buys nothing.
    aspects = sorted({seed_aspect, 1.0, 1.1, 1.2, 1.3, 1.4})
    def _search(pad_punch: bool) -> tuple:
        """ONE full outline search under ONE reservation policy
        (wave-11 monotonicity guard). Leaves ``plan`` holding the
        winning layout and the module outline globals rebound to it;
        returns its ``best`` tuple (area, w, h, est_real, budget).

        DETERMINISM: every input is a pure function of ``pad_punch``
        (the two pre-built comps/shape tables) and the same fixed
        aspect/grow/fine grids the single search always used — no
        state survives a call except the plan the caller keeps."""
        global BOARD_W, BOARD_H
        shape_sets = sets_by_policy[pad_punch]
        comps_of = comps_by_policy[pad_punch]
        plan.punch_free = pad_punch
        best: tuple | None = None             # (area, w, h, est_real, budget)
        fit_seen = False
        # Cheap infeasibility prune for the board-size search: SoM + summed block XY
        # areas are a HARD lower bound (blocks + SoM cannot overlap), so any board below
        # it provably cannot pack — skip the O(board_area) _attempt_pack lattice scan.
        # Sound: never prunes a feasible board (real inter-block gaps only
        # make the true minimum LARGER), so the selected board is unchanged.
        # Keeps the search fast when a larger zone (e.g. a grow knob) inflates
        # the blocks — without it the fine refinement pays a full slow pack on
        # ~1000s of too-small boards (a 30-min+ stall).
        _min_pack_area = som.w * som.h + sum(
            min(w * h for w, h, *_ in shape_sets[name]) if name in shape_sets
            else bw * bh
            for name, (bw, bh) in zbox.items())
        for aspect in aspects:
            for _try in range(80):
                grow = _q.outline_grow(_try)
                w = _q.outline_snap_up(outline.w + grow * (aspect / seed_aspect))
                h = _q.outline_snap_up(outline.h + grow)
                if w < h:                     # keep landscape
                    continue
                if w * h < _min_pack_area:    # provably too small — skip the slow pack
                    continue
                BOARD_W, BOARD_H = w, h
                plan.som_x = _q.som_pose_half_mm((BOARD_W - som.w) / 2 + SOM_DX)
                plan.som_y = _q.som_pose_half_mm((BOARD_H - som.h) / 2 + SOM_DY)
                if not _attempt_pack(plan, interior, edge_of, zbox,
                                     affinity, som_pull, compose=compose,
                                     far_ceil=far_ceil, max_reach=max_reach,
                                     shapes=shape_sets, comps_of=comps_of,
                                     side_est=est_cross):
                    continue
                fit_seen = True
                budget = CROSS_BUDGET_K * (BOARD_W * BOARD_H) ** 0.5 * n_sub
                est_real = est_cross(plan.edge_blocks + interior)
                if est_real <= budget:
                    area = round(BOARD_W * BOARD_H, 1)
                    cand = (area, BOARD_W, BOARD_H, est_real, budget)
                    if best is None or cand < best:
                        best = cand
                    break                     # this aspect's smallest passing board
        if best is None:
            raise RuntimeError(
                "floorplan: could not fit all REAL packed blocks under the LAW-5 "
                f"airwire budget on any searched outline (blocks "
                f"{'did' if fit_seen else 'never'} fit)")

        # INDEPENDENT-AXIS REFINEMENT: the aspect grow above moves W and H TOGETHER
        # along a fixed aspect, so it cannot find a board whose W and H sit at
        # different fractions of the seed (e.g. 165x140, aspect 1.18, off the coarse
        # aspect grid). Starting from the best aspect-grown board, greedily shrink one
        # axis at a time by OUTLINE_SNAP while the blocks still pack AND the estimated
        # cross-airwire still clears the budget — the SAME est_real <= budget
        # criterion the aspect search used (the strict REAL gate in `schgen board`
        # remains the final arbiter; this only lets the SIZING reach the true minimum-
        # area board on the snap grid, never relaxing a gate). Deterministic: a fixed
        # axis order (H then W), fixed snap step, stop at the first non-improving pass.

        def _passes(w: float, h: float) -> tuple[bool, float, float]:
            global BOARD_W, BOARD_H
            BOARD_W, BOARD_H = w, h
            plan.som_x = _q.som_pose_half_mm((BOARD_W - som.w) / 2 + SOM_DX)
            plan.som_y = _q.som_pose_half_mm((BOARD_H - som.h) / 2 + SOM_DY)
            if not _attempt_pack(plan, interior, edge_of, zbox,
                                 affinity, som_pull, compose=compose,
                                 far_ceil=far_ceil, max_reach=max_reach,
                                 shapes=shape_sets, comps_of=comps_of,
                                 side_est=est_cross):
                return False, 0.0, 0.0
            bud = CROSS_BUDGET_K * (w * h) ** 0.5 * n_sub
            er = est_cross(plan.edge_blocks + interior)
            return (er <= bud), er, bud

        _area, bw, bh, best_er, best_bud = best
        # The cross-airwire is NON-MONOTONIC in board size: shrinking by one snap step
        # can momentarily LENGTHEN the airwire (blocks squeezed into worse slots) and
        # then improve again a step later (165x150 -> 145 worsens, -> 140 passes). A
        # greedy single-step descent stalls in that valley, so scan a bounded snap-grid
        # WINDOW at/under the aspect-best (each axis down to REFINE_SPAN below, but not
        # below where blocks can pack) and keep the smallest-area board that packs AND
        # clears the est-airwire budget. The window is small enough to stay fast yet
        # wide enough to step over the non-monotonic valley. Deterministic: fixed grid.

        # FINE step (1 mm, not the 5 mm OUTLINE_SNAP): the REAL packer's shelf quantum
        # makes feasibility JAGGED on the 1 mm scale — at the tight wall 161 and 163
        # pack but 160/162/164 do NOT, and the L4-credited airwire clears the budget at
        # 161x134 (a board the 5 mm grid can never name, so the coarse search fell back
        # to 165x135). Scanning a 1 mm grid lets the search LAND on those narrow packing
        # islands. Each candidate still calls the REAL _attempt_pack (PACK_FAIL sizes
        # are rejected) and the L4-credited proxy vs the LAW-5 budget, so this only
        # finds a smaller board the strict `schgen board` gate then re-proves — it never
        # relaxes a gate. Deterministic: a fixed 1 mm grid, smallest-area wins.
        bw0, bh0 = bw, bh
        nsteps = _q.fine_steps()
        ws = [_q.fine_shrink(bw0, k) for k in range(0, nsteps)]
        hs = [_q.fine_shrink(bh0, k) for k in range(0, nsteps)]
        for w in ws:
            for h in hs:
                if (w <= 0 or h <= 0 or w < h or w * h >= bw * bh - 1e-6
                        or w * h < _min_pack_area):
                    continue                  # strictly-smaller landscape boards, above
                    #                           the hard min-pack-area floor
                ok, er, bud = _passes(w, h)
                if ok:
                    bw, bh, best_er, best_bud = w, h, er, bud
        best = (round(bw * bh, 1), bw, bh, best_er, best_bud)

        _area, BOARD_W, BOARD_H, est_real, budget = best
        plan.som_x = _q.som_pose_half_mm((BOARD_W - som.w) / 2 + SOM_DX)
        plan.som_y = _q.som_pose_half_mm((BOARD_H - som.h) / 2 + SOM_DY)
        # RE-PACK at the chosen winner so plan holds exactly that layout (the search
        # left plan at the last aspect tried). Deterministic: same (w, h) -> same pack.
        if not _attempt_pack(plan, interior, edge_of, zbox, affinity, som_pull,
                             compose=compose, compact=True, far_ceil=far_ceil,
                             max_reach=max_reach, shapes=shape_sets,
                             comps_of=comps_of, side_est=est_cross):
            raise RuntimeError(
                f"floorplan: the winning outline {BOARD_W:g}x{BOARD_H:g} failed "
                "the final compact re-pack — refusing to emit a stale layout")
        _choose_conn_shapes(plan, interior, edge_of, zbox, affinity, som_pull,
                            compose, True, far_ceil, max_reach, shape_sets,
                            comps_of, zg, est_cross)
        return best

    _fb_entry = _fb.snapshot()
    _reset_shapes()
    best = _search(False)
    cons_snap = _plan_snapshot()
    cons_fb = _fb.snapshot()
    _fb.restore(_fb_entry)
    _reset_shapes()
    free_best = _guarded(_search)
    if free_best is not None and (
            free_best[0] < best[0] - 1e-6
            or (free_best[0] <= best[0] + 1e-6
                and free_best[3] < best[3] - 1e-6)):
        best = free_best
    else:
        _plan_restore(cons_snap)
        _fb.restore(cons_fb)
        _fb.record("punch_free_plan_rejected")

    _area, BOARD_W, BOARD_H, est_real, budget = best
    plan.interior_blocks = interior
    OUTLINE_NOTE = (
        f"{outline.note}; then SMALLEST-AREA search over aspects "
        f"{', '.join(f'{a:g}' for a in aspects)} -> {BOARD_W:g}x{BOARD_H:g} mm "
        f"(the smallest board holding the REAL 2-sided packed blocks with the "
        f"estimated cross-subsystem airwire {est_real:.0f} <= LAW-5 budget "
        f"{budget:.0f} mm — honest routing headroom, the gate is not relaxed), "
        f"SoM {som.w:g}x{som.h:g} centered")
    return plan


def _outline_note(som: SomGeom, seed: Outline, w: float, h: float,
                  grow: float, fit_grow: float = 0.0,
                  est_real: float = 0.0, budget: float = 0.0) -> str:
    extra = ""
    if grow > fit_grow + 1e-6:
        extra = (f" (blocks first fit at +{fit_grow:g}mm; GROWN further so the "
                 f"estimated cross-subsystem airwire {est_real:.0f} <= LAW-5 "
                 f"budget {budget:.0f} mm — honest routing headroom, the gate is "
                 f"not relaxed)")
    elif budget:
        extra = (f" (estimated cross-subsystem airwire {est_real:.0f} <= LAW-5 "
                 f"budget {budget:.0f} mm at first fit)")
    return (f"{seed.note}; then GROWN +{grow:g}mm to {w:g}x{h:g} mm to fit the "
            f"REAL 2-sided packed subsystem blocks (the same packed geometry the "
            f"PCB places), SoM {som.w:g}x{som.h:g} centered{extra}")


def _cross_estimator(plan: Plan, zg, sheets):
    """The LAW-5 sizing estimate as a STRUCTURAL measurement, not a calibrated
    proxy: the ratsnest gate's own kernel (``ratsnest._mst_edges`` Manhattan-
    select Prim, Euclidean cross-edge sum, per-net PAD population) evaluated on
    the exact positions the PCB's STEP-3 emission derives from a candidate plan
    — exact zone origins + the shared packer's per-part offsets, the
    centered SoM receptacles + under-SoM decoupling grid, the corner mounting
    holes, and the LAW-6 edge-seated connectors. Replaces the block-centre
    proxy and its two measured constants (PROXY_TO_REAL, L4_PULL_CREDIT): the
    4% block-granularity bias is gone by construction, and the placer's later
    refinements (L4 bottom-pull, breathe, refit) net-SHORTEN the measured
    cross (-2.2% on the shipping board), so the estimate reads as an honest
    upper bound (est 17607 vs real 17192 at 215x161, +2.4%). The strict gate
    in ``schgen board`` remains the only arbiter — a rosy estimate is caught
    there. Deterministic: sorted nets, fixed point order.

    Returns ``evaluate(blocks) -> float`` for the current BOARD_W/H + plan
    pose; ``blocks`` is passed explicitly (edge + freshly-packed interior)
    because inside the grow loop the interior is not yet committed to
    ``plan.interior_blocks``."""
    import json as _json

    from schgen.generate.board import _renamed_ref
    from schgen.generate.pcb.constants import (
        EDGE_PAD_CLEAR,
        MH_INSET,
        ORIGIN_X,
        ORIGIN_Y,
        FootprintInst,
    )
    from schgen.generate.pcb.footprint import _net_classes, resolve_mod
    from schgen.generate.pcb.mating_face import _inst_pad_geom, _rot_pad_bbox
    from schgen.generate.ratsnest import _mst_edges

    idx_path = PROJECT_ROOT / "sheet_index.json"
    sheet_index = (_json.loads(idx_path.read_text())
                   if idx_path.exists() else {})

    rot_of: dict[str, float] = dict(zg.conn_rot)
    for ref, extra in zg.zone_extra_rot.items():
        rot_of[ref] = (rot_of.get(ref, 0.0) + extra) % 360.0
    som_rot = {j.ref: (90.0 if j.w < j.h else 0.0) for j in plan.som.js}
    som_rel = {j.ref: (j.x, j.y) for j in plan.som.js}

    owner_of: dict[str, tuple[str, object]] = {}
    mod_of: dict[str, Path] = dict(zg.resolvable)
    sheet_of: dict[str, str] = {}
    off_of: dict[str, tuple[float, float]] = {}
    for sheet in sorted(zg.zone_box):
        for side_off in (zg.top_off.get(sheet, {}), zg.bot_off.get(sheet, {})):
            for r, o in side_off.items():
                off_of[r] = o
                owner_of[r] = ("zone", sheet)
                sheet_of[r] = sheet
    # MULTI-SHAPE: per (sheet, shape k>=1) offset/rotation views, so a candidate
    # plan whose block chose shape k is estimated with the SAME geometry the PCB
    # will emit for it — never shape 0's. Index 0 stays the flat views above.
    n_shapes = {sheet: len(v) for sheet, v in zg.shapes.items()}
    off_k: dict[tuple[str, int], dict[str, tuple[float, float]]] = {}
    rot_k: dict[tuple[str, int], dict[str, float]] = {}
    mir_k: dict[tuple[str, int], dict[str, Path]] = {}
    for sheet in sorted(zg.shapes):
        for k, shp in enumerate(zg.shapes[sheet]):
            if k == 0:
                continue
            both = dict(shp.top_off)
            both.update(shp.bot_off)
            off_k[(sheet, k)] = both
            rot_k[(sheet, k)] = {
                r: (zg.conn_rot.get(r, 0.0) + e) % 360.0
                for r, e in shp.extra_rot.items()}
            if shp.mirror:
                mir_k[(sheet, k)] = shp.mirror

    dec_refs: list[str] = []
    for i, sc in enumerate(sheets, start=1):
        band = sheet_index.get(sc.name, i)
        if sc.name.startswith("som_j"):
            jn = "J" + sc.name[len("som_j"):]
            for ref, part in sorted(sc.circuit.parts.items()):
                bref = _renamed_ref(ref, band, sheet=sc.name)
                mod = resolve_mod(part.footprint)
                if not bref.startswith("J") or jn not in som_rel or mod is None:
                    continue
                mod_of[bref] = mod
                sheet_of[bref] = sc.name
                owner_of[bref] = ("som_j", jn)
                rot_of[bref] = som_rot[jn]
        elif sc.name == "som_decoupling":
            for ref, part in sorted(sc.circuit.parts.items()):
                bref = _renamed_ref(ref, band, sheet=sc.name)
                mod = resolve_mod(part.footprint)
                if mod is None:
                    continue
                mod_of[bref] = mod
                sheet_of[bref] = sc.name
                dec_refs.append(bref)
        else:
            for ref, part in sorted(sc.circuit.parts.items()):
                if not part.lib_id.startswith("Mechanical:MountingHole"):
                    continue
                bref = _renamed_ref(ref, band, sheet=sc.name)
                mod = resolve_mod(part.footprint)
                if bref not in zg.mh_refs or mod is None:
                    continue
                mod_of[bref] = mod
                sheet_of[bref] = sc.name
                owner_of[bref] = ("mh", zg.mh_refs.index(bref) % 4)
    for k, bref in enumerate(sorted(dec_refs)):
        owner_of[bref] = ("dec", k)

    def _pads_at(bref: str, rot: float, mod: Path | None = None
                 ) -> dict[str, list[tuple[float, float]]]:
        probe = FootprintInst(ref=bref, value="", footprint="", x=0.0, y=0.0,
                              rotation=rot, pad_nets={},
                              mod_path=mod or mod_of[bref],
                              sheet=sheet_of[bref])
        rel: dict[str, list[tuple[float, float]]] = {}
        for name, rx, ry, _n in _inst_pad_geom(probe):
            rel.setdefault(name, []).append((rx, ry))
        return rel

    pad_rel: dict[str, dict[str, list[tuple[float, float]]]] = {}
    pad_rel_k: dict[tuple[str, int], dict[str, list[tuple[float, float]]]] = {}
    for bref in sorted(owner_of):
        pad_rel[bref] = _pads_at(bref, rot_of.get(bref, 0.0))
        sh = sheet_of[bref]
        for k in range(1, n_shapes.get(sh, 1)):
            r_k = rot_k[(sh, k)].get(bref, 0.0)
            mp = mir_k.get((sh, k), {}).get(bref)
            if mp is None and r_k == rot_of.get(bref, 0.0):
                pad_rel_k[(bref, k)] = pad_rel[bref]
            else:
                pad_rel_k[(bref, k)] = _pads_at(bref, r_k, mp)

    # net_pts entry = (bref, sheet, pads_by_shape): pads_by_shape[k] is the
    # pin's pad offsets under that sheet's shape k (a 1-tuple for single-shape
    # owners); ``evaluate`` indexes it with the candidate block's chosen shape.
    net_pts: dict[str, list[tuple[str, str, tuple]]] = {}
    for i, sc in enumerate(sheets, start=1):
        band = sheet_index.get(sc.name, i)
        for nname in sorted(sc.circuit.nets):
            for p in sc.circuit.nets[nname].pins:
                if p.ref.startswith("#"):
                    continue
                bref = _renamed_ref(p.ref, band, sheet=sc.name)
                if bref not in owner_of:
                    continue
                base = tuple(pad_rel[bref].get(p.pin, ()))
                if not base:
                    continue
                sh = sheet_of[bref]
                by_shape = (base,) + tuple(
                    tuple(pad_rel_k[(bref, k)].get(p.pin, ()))
                    for k in range(1, n_shapes.get(sh, 1)))
                net_pts.setdefault(nname, []).append((bref, sh, by_shape))
    net_pts = {n: pts for n, pts in net_pts.items()
               if len({s for _r, s, _p in pts}) >= 2}
    net_names = sorted(net_pts)
    nets_by_sheet = _nets_by_sheet(net_pts)

    # VIA-COST term (registered est_via_cost, NET-CLASS AWARE): emitted side
    # per part under the shape-0 world + per bottom-tagged shape the PRIMARY
    # membership that flips at emission — a cross-sheet MST edge whose ends
    # land on opposite faces because a block chose a bottom shape is charged
    # one layer transition, priced by the net's own routing class. Exactly
    # zero with no bottom choice (inert).
    side0_of = {bref: ("bottom" if kind == "dec"
                       else zg.side_of.get(bref, "top"))
                for bref, (kind, _k) in owner_of.items()}
    shape_side: dict[tuple[str, int], str] = {}
    flip_top: dict[tuple[str, int], frozenset] = {}
    for sheet in sorted(zg.shapes):
        for k, shp in enumerate(zg.shapes[sheet]):
            shape_side[(sheet, k)] = shp.side
            if shp.side == "bottom":
                flip_top[(sheet, k)] = frozenset(shp.top_off)
    _cls_geo, _cls_of = _net_classes(sheets)
    via_of = {n: _q.est_via_cost(_cls_geo.get(_cls_of.get(n, "")) is not None)
              for n in net_names}

    conn_pb = {ref: _rot_pad_bbox(mod_of[ref], rot_of.get(ref, 0.0))
               for ref in sorted(zg.conn_edge) if ref in owner_of}
    n_dec = len(dec_refs)
    dec_cols = max(1, min(n_dec, round(
        (n_dec * max(1.0, plan.som.w - 12.0)
         / max(1.0, plan.som.h - 12.0)) ** 0.5))) if n_dec else 1
    dec_rows = max(1, (n_dec + dec_cols - 1) // dec_cols) if n_dec else 1

    def evaluate(blocks: list[Block], only_sheet: str | None = None) -> float:
        """Full-kernel estimate, or (``only_sheet``) the same kernel summed
        over just the nets touching that sheet — between two candidate poses
        of that sheet's block the full-board difference equals this restricted
        difference exactly (no other net's points move), which is what the
        in-pack side judge consumes."""
        by_name = {b.name: b for b in blocks}
        sel = {b.name: b.shape_idx for b in blocks
               if b.shape_idx and b.name in n_shapes}
        som_x, som_y = plan.som_x, plan.som_y
        zorig: dict[str, tuple[float, float]] = {}
        for sheet in zg.zone_box:
            b = by_name.get(sheet)
            if b is not None:
                zorig[sheet] = (round(ORIGIN_X + b.x, 4),
                                round(ORIGIN_Y + b.y, 4))
        corners = ((MH_INSET, MH_INSET), (BOARD_W - MH_INSET, MH_INSET),
                   (BOARD_W - MH_INSET, BOARD_H - MH_INSET),
                   (MH_INSET, BOARD_H - MH_INSET))
        rw = max(1.0, plan.som.w - 12.0)
        rh = max(1.0, plan.som.h - 12.0)
        part_pos: dict[str, tuple[float, float]] = {}
        for bref, (kind, key) in owner_of.items():
            if kind == "zone":
                zo = zorig.get(key)
                if zo is None:
                    continue
                k = sel.get(key, 0)
                dx, dy = (off_k[(key, k)][bref] if k else off_of[bref])
                part_pos[bref] = (round(zo[0] + dx, 4), round(zo[1] + dy, 4))
            elif kind == "som_j":
                jx, jy = som_rel[key]
                part_pos[bref] = (_q.fixed_part_grid(ORIGIN_X + som_x + jx),
                                  _q.fixed_part_grid(ORIGIN_Y + som_y + jy))
            elif kind == "dec":
                cxi, cyi = key % dec_cols, key // dec_cols
                part_pos[bref] = (
                    round(ORIGIN_X + som_x + 6.0 + rw * (cxi + 0.5) / dec_cols, 4),
                    round(ORIGIN_Y + som_y + 6.0 + rh * (cyi + 0.5) / dec_rows, 4))
            else:
                cx, cy = corners[key]
                part_pos[bref] = (_q.fixed_part_grid(ORIGIN_X + cx),
                                  _q.fixed_part_grid(ORIGIN_Y + cy))
        for ref, edge in sorted(zg.conn_edge.items()):
            pb = conn_pb.get(ref)
            if pb is None or ref not in part_pos:
                continue
            x, y = part_pos[ref]
            if edge == "N":
                y = round(ORIGIN_Y + EDGE_PAD_CLEAR - pb[1], 4)
            elif edge == "S":
                y = round(ORIGIN_Y + BOARD_H - EDGE_PAD_CLEAR - pb[3], 4)
            elif edge == "W":
                x = round(ORIGIN_X + EDGE_PAD_CLEAR - pb[0], 4)
            elif edge == "E":
                x = round(ORIGIN_X + BOARD_W - EDGE_PAD_CLEAR - pb[2], 4)
            part_pos[ref] = (x, y)
        bot_sel = {s: k for s, k in sel.items()
                   if shape_side.get((s, k)) == "bottom"}

        def _pt_side(r: str, s: str) -> str:
            k = bot_sel.get(s)
            if k is None:
                return side0_of.get(r, "top")
            return "bottom" if r in flip_top[(s, k)] else "top"

        cross = 0.0
        for nname in (nets_by_sheet.get(only_sheet, ())
                      if only_sheet else net_names):
            pts = [(round(part_pos[r][0] + rx, 3),
                    round(part_pos[r][1] + ry, 3), r, s)
                   for r, s, byk in net_pts[nname] if r in part_pos
                   for rx, ry in byk[sel.get(s, 0) if len(byk) > 1 else 0]]
            via_mm = via_of[nname]
            for a, b in _mst_edges(pts):
                if pts[a][3] != pts[b][3]:
                    cross += ((pts[a][0] - pts[b][0]) ** 2
                              + (pts[a][1] - pts[b][1]) ** 2) ** 0.5
                    if (via_mm and bot_sel
                            and (pts[a][3] in bot_sel or pts[b][3] in bot_sel)
                            and _pt_side(pts[a][2], pts[a][3])
                            != _pt_side(pts[b][2], pts[b][3])):
                        cross += via_mm
        return cross

    return evaluate


def _nets_by_sheet(net_pts: dict) -> dict[str, tuple[str, ...]]:
    """sheet -> the sorted cross-subsystem nets touching it (the restricted
    iteration set of ``evaluate(only_sheet=...)``). Deterministic: sorted
    nets, sorted sheets."""
    out: dict[str, list[str]] = {}
    for nname in sorted(net_pts):
        for s in sorted({s for _r, s, _p in net_pts[nname]}):
            out.setdefault(s, []).append(nname)
    return {s: tuple(ns) for s, ns in out.items()}


def _pick_sided(finalists: list[tuple], est_of) -> tuple:
    """EST-DRIVEN SIDE CHOICE (bottom-side P2): when a block's fitting shape
    variants span BOTH copper faces, the pick is judged by the sizing
    estimator (cross-airwire + registered est_via_cost), not anchor distance.
    ``finalists`` = the per-face (key, cand) pairs sorted by the greedy
    (distance, index) key, so finalists[0] is the incumbent the distance rule
    would keep; the other face's finalist wins ONLY on a strict estimator
    improvement (> 1e-6 mm). Deterministic: fixed candidate order feeds the
    keys, strict comparison, ties keep the incumbent. A missing judge is a
    HARD error — the side choice never silently degrades to distance."""
    if est_of is None:
        raise AssertionError(
            "floorplan: a block's shape set spans copper faces but no "
            "estimator judge was wired — pass side_est to _attempt_pack; "
            "the side choice may not fall back to anchor distance")
    incumbent, challenger = finalists[0][1], finalists[1][1]
    return challenger if est_of(challenger) < est_of(incumbent) - 1e-6 \
        else incumbent


def _edge_components(b: Block, comps: tuple) -> tuple:
    """Occupancy COMPONENTS of a pinned EDGE block (wave-11 P1). An edge block's
    main rect is its own copper face only — its shell/courtyard/empty zone area
    is top-side body and never blocked B.Cu; what genuinely pierces is its
    through-hole PAD copper, which rides here as PUNCH sub-rects.

    Every PUNCH box is swept OUT to the board edge along the block's edge
    normal: the LAW-6 edge seat slides an off-board connector OUTWARD at
    emission (measured 1.5 mm on every contracted conn sheet, 1.960 on
    rj45_connector), so the piercing copper sweeps that band. Conservative
    direction — the swept box only ever GROWS the reservation, and only into
    the perimeter strip the edge run already owns."""
    out = []
    for dx, dy, cw, ch, cm in comps:
        if cm == OCC_PUNCH:
            if b.edge == "N":
                dy, ch = -b.y, b.y + dy + ch
            elif b.edge == "S":
                ch = BOARD_H - b.y - dy
            elif b.edge == "W":
                dx, cw = -b.x, b.x + dx + cw
            elif b.edge == "E":
                cw = BOARD_W - b.x - dx
        out.append((round(dx, 4), round(dy, 4), round(cw, 4), round(ch, 4), cm))
    return tuple(out)


def _som_components(plan: Plan, som_occ: tuple, bands: list) -> tuple:
    """Occupancy COMPONENTS of the SoM reservation (wave-11 P2). LAW 6 as
    amended 2026-07-09 makes the carrier TOP under the module a FULL keepout and
    leaves the BOTTOM face free, so the main rect is OCC_TOP and the underside
    carries only what is REALLY there:

      * the som_decoupling bank's own grid cells (OCC_BOTTOM), taken from the
        emission oracle ``placement.som_decoupling_cells`` and grown by each
        cap's origin-radius bound so the reservation holds under any rotation;
      * the three DF40 escape/return-stitch seat corridors (OCC_PUNCH) — the
        escape router seats stitch vias and the return ladder there and the
        band must stay clear of FOREIGN parts on BOTH faces. These are the same
        ``_SEAT_BAND`` rects the edge-vs-SoM fit test rejects against, which
        strictly contain escape.corridor_board_rect (R_CONSTRUCT 1.8 and
        CORRIDOR_V_MARGIN 0.15 both well inside the 6 mm band).

    The DF40 receptacles themselves are SMD: they occupy the top face only, and
    the main rect already covers them."""
    from schgen.generate.pcb.placement import som_decoupling_cells
    ox, oy = som_occ[0], som_occ[1]
    n, r = plan.dec_bank
    comps = [(round(cx - r - ox, 4), round(cy - r - oy, 4),
              round(2 * r, 4), round(2 * r, 4), OCC_BOTTOM)
             for cx, cy in som_decoupling_cells(
                 plan.som_x, plan.som_y, plan.som.w, plan.som.h, n)]
    comps += [(round(x0 - ox, 4), round(y0 - oy, 4), round(x1 - x0, 4),
               round(y1 - y0, 4), OCC_PUNCH) for x0, y0, x1, y1 in bands]
    return tuple(comps)


_SEAT_FIELDS = ("x", "y", "w", "h", "area", "shape_idx", "side",
                "fanout_reach", "fanout_inset")

_RESEAT_EVICT_BUDGET = 3


def _attempt_pack(plan: Plan, interior: list[Block],
                  edge_of: dict[str, str],
                  zbox: dict[str, tuple[float, float]],
                  affinity: dict[str, dict[str, float]],
                  som_pull: dict[str, float],
                  compose: tuple | None = None,
                  compact: bool = False,
                  far_ceil: float = 0.0,
                  max_reach: float | None = None,
                  shapes: dict[str, list[tuple]] | None = None,
                  comps_of: dict[tuple[str, int], tuple] | None = None,
                  side_est=None) -> bool:
    plan.spilled = []
    for b in plan.edge_blocks:
        b.w, b.h = zbox[b.name]
        b.area = round(b.w * b.h, 1)
    _pack_edges(plan, edge_of)

    # EDGE-RUN FIT (LAW 0/6): _pack_edges packs a contiguous run and clamps its
    # START to [EDGE_MARGIN, span-EDGE_MARGIN], but when the run (blocks + the
    # REQUIRED cable/overmold gaps) exceeds that band it spills past the FAR end —
    # the last connector then overhangs into the corner M3 mounting-hole keepout
    # and its pad SHORTS to the hole (a real CHASSIS_GND/signal DRC short a reflow
    # can trigger when an added part squares the board). REJECT such a board so the
    # grow loop sizes it WIDE enough — never trimming the cable gaps, never
    # softening the gate (LAW 4). Pre-fit boards are unchanged (byte-stable).
    for b in plan.edge_blocks:
        if b.edge in ("W", "E"):
            near, span_b, dim = b.y, b.h, BOARD_H
        else:
            near, span_b, dim = b.x, b.w, BOARD_W
        if (near < EDGE_MARGIN - _q.run_overflow_tol()
                or near + span_b > dim - EDGE_MARGIN + _q.run_overflow_tol()):
            return False

    # EDGE-vs-SoM FIT (LAW 0/6): the edge runs never consulted the SoM — on a
    # shrunk outline an edge zone's depth reached over the SoM body AND the
    # DF40 return-stitch seat corridors (devkit at 102x70: pd_input's band
    # covered J1's corridor; the escape's redundancy-partner seat then had no
    # feasible cell and the build died). REJECT any candidate where an edge
    # block intersects the SoM occupancy pad or a DF40 6 mm seat-corridor
    # band, so the sizing search grows the board instead (LAW 4).
    _SEAT_BAND = 6.0
    _SOM_OCC_PAD = 1.5
    som_rects = [(plan.som_x - _SOM_OCC_PAD, plan.som_y - _SOM_OCC_PAD,
                  plan.som_x + plan.som.w + _SOM_OCC_PAD,
                  plan.som_y + plan.som.h + _SOM_OCC_PAD)]
    for j in plan.som.js:
        som_rects.append((plan.som_x + j.x - j.w / 2 - _SEAT_BAND,
                          plan.som_y + j.y - j.h / 2 - _SEAT_BAND,
                          plan.som_x + j.x + j.w / 2 + _SEAT_BAND,
                          plan.som_y + j.y + j.h / 2 + _SEAT_BAND))
    for b in plan.edge_blocks:
        for rx0, ry0, rx1, ry1 in som_rects:
            if (min(b.x + b.w, rx1) - max(b.x, rx0) > 1e-6
                    and min(b.y + b.h, ry1) - max(b.y, ry0) > 1e-6):
                return False

    # CROSS-EDGE CORNER FIT (LAW 0/6): _pack_edges packs each edge as an INDEPENDENT
    # 1D run, so a deep block on one edge and a deep block on the ADJACENT edge can
    # occupy the SAME corner rectangle (a W-edge XT60+TVS block vs an S-edge HDMI
    # block at the SW corner) — overlapping courtyards AND a real net short (the
    # motor_sense XT60 GND pad into HDMI_RX_5V) that the per-block, per-edge
    # corner-overhang check above can NOT see (it is 1D along each block's own
    # edge). REJECT any board where two DIFFERENT-edge blocks' rects intersect
    # within the CLEAR gap, so the grow loop sizes the board until the corner
    # clears (or build_plan raises). Same-edge spacing is owned by the run packer's
    # per-pair gaps, so only cross-edge pairs are tested. NEVER trims a block, NEVER
    # softens a gate (LAW 4). Pre-fit boards are unchanged (no clean board trips it).
    eb = plan.edge_blocks
    for i in range(len(eb)):
        a = eb[i]
        for j in range(i + 1, len(eb)):
            b = eb[j]
            if a.edge == b.edge:
                continue
            # D13 DIRECTIONAL corner clearance (same facing-side rule the occupancy
            # lattice uses) so two adjacent-edge blocks meeting at a corner keep the
            # fan-out floor of any exposed multi-pin subject between them.
            cgx = max(CLEAR, _fanout_sep(a.fanout_reach, a.fanout_inset,
                                         b.fanout_reach, b.fanout_inset,
                                         "E" if a.x <= b.x else "W"))
            cgy = max(CLEAR, _fanout_sep(a.fanout_reach, a.fanout_inset,
                                         b.fanout_reach, b.fanout_inset,
                                         "S" if a.y <= b.y else "N"))
            if not (a.x + a.w + cgx <= b.x or b.x + b.w + cgx <= a.x
                    or a.y + a.h + cgy <= b.y or b.y + b.h + cgy <= a.y):
                return False

    free = plan.punch_free
    som_mask = OCC_TOP if free else OCC_PUNCH
    som_occ = (plan.som_x - _SOM_OCC_PAD, plan.som_y - _SOM_OCC_PAD,
               plan.som.w + 2 * _SOM_OCC_PAD, plan.som.h + 2 * _SOM_OCC_PAD)
    som_comps = _som_components(plan, som_occ, som_rects[1:]) if free else ()
    edge_mask = OCC_TOP if free else OCC_PUNCH
    edge_comps = {b.name: _edge_components(
        b, (comps_of or {}).get((b.name, b.shape_idx), ())) if free else ()
        for b in plan.edge_blocks}

    occ = _Occupancy(far_ceil, max_reach)
    # reserve the SoM body PLUS a clearance pad: the placement_mech keepout
    # (som_core) is drawn ~3% larger than the bare body for mating clearance, so a
    # zone packed flush against the body clips that enlarged core (the ethernet
    # magnetics clipped it 0.1mm after the tight-pack). Pad the reservation so
    # packed zones stay clear of the 3% core.
    occ.add(*som_occ, _ZeroReach, _ZeroReach, som_mask, som_comps)
    # reserve the 4 corner mounting-hole keepouts: the PCB corner-forces an M3
    # hole into each corner, so no interior block may occupy a corner square (an
    # overlap was a real CHASSIS_GND/signal DRC short). Edge blocks clear the
    # corners via EDGE_MARGIN; this protects the interior packer.
    for cx, cy in ((0.0, 0.0), (BOARD_W - MH_CORNER_KO, 0.0),
                   (BOARD_W - MH_CORNER_KO, BOARD_H - MH_CORNER_KO),
                   (0.0, BOARD_H - MH_CORNER_KO)):
        occ.add(cx, cy, MH_CORNER_KO, MH_CORNER_KO)
    centers: dict[str, tuple[float, float]] = {}
    for b in plan.edge_blocks:        # edge blocks are pinned anchors already
        occ.add(b.x, b.y, b.w, b.h, b.fanout_reach, b.fanout_inset,
                edge_mask, edge_comps[b.name])
        centers[b.name] = (b.cx, b.cy)

    edge_pos = {b.name: b for b in plan.edge_blocks}
    som_cx = plan.som_x + plan.som.w / 2
    som_cy = plan.som_y + plan.som.h / 2

    def _conn(b: Block) -> float:
        return (sum(affinity.get(b.name, {}).values())
                + 3.0 * som_pull.get(b.name, 0.0))

    # ZONE_W: weight of the E/N/S/W zone bias in the anchor. Kept SMALL so the
    # net-affinity centroid dominates — the zone only nudges a block toward its
    # SoM-side when it has no placed neighbour yet, which keeps net-sharing
    # blocks drawing tightly together (the LAW-5 lever). SOM_W amplifies the
    # SoM-membership pull (a net touching a J strip wants the block near the SoM).
    # AFF_POW raises each affinity weight to a power so the DOMINANT net-neighbour
    # decisively wins over a crowd of weak ones: bringup_modules shares ~5 nets
    # with bringup_en_modules but ~1 each with lcd/hdmi_tx/camera — linearly those
    # weak edge pulls (sum ~3.7) drag it to the SW; powered (5^1.6=13.1 vs
    # 1^1.6=1) the real partner wins and the cluster collapses tight.
    ZONE_W = 0.25
    SOM_W = 7.0
    AFF_POW = 1.6

    def _anchor(b: Block) -> tuple[float, float]:
        """Weighted centroid of this block's PLACED net-neighbours + the SoM +
        a small zone bias. The (powered) affinity weights dwarf the zone term, so
        a cluster (bringup_rails <-> bringup_en_modules, power <-> power_mon, ...)
        collapses to a tight group near the SoM strips it shares."""
        # MODULE-FACE ANCHOR (project.json placement.module_face_anchors): a block
        # declared {name: face} hard-anchors just outside the module's escape halo
        # on that face, centred (its true electrical seat — the carrier declares
        # power_som:E, the SoM power input). This keeps it clear of edge crowding
        # so downstream FACING holds under ANY module offset (measured: without it
        # the E-side crowding drifts power_som ~100 mm and breaks the flow gate).
        # No-op at the centred default pose (byte-identity).
        _mfa = _project_spec().module_face_anchors
        if b.name in _mfa and (SOM_DX or SOM_DY):
            _face = _mfa[b.name]
            _fx = {"E": plan.som_x + plan.som.w + SOM_HALO + b.w / 2,
                   "W": plan.som_x - SOM_HALO - b.w / 2,
                   "N": plan.som_x + plan.som.w / 2,
                   "S": plan.som_x + plan.som.w / 2}[_face]
            _fy = {"E": plan.som_y + plan.som.h / 2,
                   "W": plan.som_y + plan.som.h / 2,
                   "N": plan.som_y - SOM_HALO - b.h / 2,
                   "S": plan.som_y + plan.som.h + SOM_HALO + b.h / 2}[_face]
            return (_fx, _fy)
        if b.zone.startswith("@") and b.zone[1:] in edge_pos:
            eb = edge_pos[b.zone[1:]]
            zax, zay = eb.cx, eb.cy
        else:
            zax, zay = _zone_anchor(
                plan, b.zone if b.zone in ("N", "E", "S", "W") else "E")
        # ZONE-ANCHOR PULL OVERRIDE (Decision D11 -> T1 P3 spec knob). An
        # EXCLUSIVE pull (validated in load_floorplan_spec: near == pull.to ==
        # an edge block) makes the explicit floorplan anchor WIN over the
        # net-affinity pull: zone weight = pull.weight (dominates the powered
        # affinity sum), the SoM pull is dropped, and with face="inboard" the
        # anchor aims just INBOARD of the pulled connector body so the block
        # tucks against the receptacle's inner face, toward the board interior
        # (usb_pd: the FUSB302 PD PHY seats at its Type-C inlet — its CITED
        # CC-run near_max + the flow budget). The old code-constant hack
        # (_EDGE_SEAT_BLOCKS/_EDGE_SEAT_ZONE_W) is GONE — the seat authority
        # is the reviewed carrier/floorplan.json (D-1); geometry unchanged.
        pull = b.pull
        exclusive = bool(pull and pull.get("exclusive", False))
        if exclusive and b.zone.startswith("@") and b.zone[1:] in edge_pos:
            zw, sp = float(pull["weight"]), 0.0
            eb2 = edge_pos[b.zone[1:]]
            edge = getattr(eb2, "edge", "")
            if pull.get("face", "center") == "inboard":
                # aim just INBOARD of the connector body (interior direction)
                if edge == "N":
                    zax, zay = eb2.cx, eb2.y + eb2.h + b.h / 2
                elif edge == "S":
                    zax, zay = eb2.cx, eb2.y - b.h / 2
                elif edge == "W":
                    zax, zay = eb2.x + eb2.w + b.w / 2, eb2.cy
                elif edge == "E":
                    zax, zay = eb2.x - b.w / 2, eb2.cy
                # else: keep the centroid (zax, zay already set above)
            # face == "center": keep the block centroid (zax, zay already set)
        else:
            zw = ZONE_W
            sp = SOM_W * max(som_pull.get(b.name, 0.0), 0.0)
        wsum = zw + sp
        ax = zw * zax + sp * som_cx
        ay = zw * zay + sp * som_cy
        # NON-exclusive pull: ONE weighted point at the pull target's centre
        # joins the accumulation (a tuning nudge, not a seat override). The
        # target must already be placed (edge blocks always are; an interior
        # target placed later this pass contributes nothing yet — documented,
        # deterministic).
        if pull and not exclusive:
            pt = centers.get(pull["to"])
            if pt is not None:
                pw = float(pull["weight"])
                ax += pw * pt[0]
                ay += pw * pt[1]
                wsum += pw
        for nb, w in affinity.get(b.name, {}).items():
            if nb in centers:
                ncx, ncy = centers[nb]
                pw = w ** AFF_POW
                ax += pw * ncx
                ay += pw * ncy
                wsum += pw
        return ax / wsum, ay / wsum

    # place the most-connected (and, as a tiebreak, the largest) interior block
    # first, so the hub subsystems anchor near the SoM and pull the rest in —
    # this is what keeps the cross-subsystem airwire under the LAW-5 budget.
    # EXCLUSIVE-pull blocks (usb_pd, D11 — the spec knob, T1 P3) are placed
    # FIRST — before the big interior blocks (fmc, ...) fill the area behind
    # their connector — so they can claim the cell snug against their
    # receptacle (the near_max/flow requirement). Then the rest in
    # connectivity order (most-connected first, the LAW-5 lever).
    _mfa_prio = _project_spec().module_face_anchors
    order = sorted(
        interior,
        key=lambda b: (0 if b.name in _mfa_prio else
                       1 if (b.pull and b.pull.get("exclusive", False)) else 2,
                       -_conn(b),
                       -(zbox[b.name][0] * zbox[b.name][1]), b.name))
    # MULTI-SHAPE choice — greedy best-local-fit, DETERMINISTIC: each block's
    # shapes are tried in their FIXED registered order; every shape gets its own
    # place_near (nearest fitting cell for that (w, h, reach)); WITHIN a copper
    # face the shape whose placed CENTER lands city-block-closest to the anchor
    # wins, index breaks ties. BETWEEN faces (a block whose fitting variants
    # span top AND bottom) the per-face finalists are judged by the sizing
    # estimator restricted to this sheet's nets — cross-airwire + est_via_cost
    # on the partial board (edge blocks + blocks placed so far), the same
    # kernel the outline search budgets with (_pick_sided; P1 measured the
    # distance rule side-blind: top/bottom tie at 0.403 and the tie-break
    # keeps top even when the estimator prefers the flip). On a tight board
    # an unfittable shape scores infinity, so the search adopts whatever
    # tessellates — the lever that lets the outline shrink. The choice is made
    # ONCE here; the refinement passes below keep it (re-choosing every pass
    # would triple their cost for a second-order gain). No search tree, no
    # cross-candidate state: cost is <= |shapes| place_near calls + at most
    # TWO restricted-estimator calls for the (rare) cross-face blocks.
    chosen_comps: dict[str, tuple] = {}

    def _bcomps(bb: Block) -> tuple:
        return chosen_comps.get(bb.name, ())

    placed: list[Block] = []

    def _occ_put(bb: Block) -> None:
        occ.add(bb.x, bb.y, bb.w, bb.h, bb.fanout_reach, bb.fanout_inset,
                _side_mask(bb.side), _bcomps(bb))

    def _occ_pull(bb: Block) -> None:
        occ.remove(bb.x, bb.y, bb.w, bb.h, bb.fanout_reach, bb.fanout_inset,
                   _side_mask(bb.side), _bcomps(bb))

    def _evict_window(e: Block, w: float, h: float, rch: tuple,
                      ins: tuple, cc: tuple) -> tuple:
        """Origin window that provably contains EVERY lattice cell a
        (w, h, rch, ins, cc) candidate can newly occupy once ``e`` is evicted.

        The retry only ever runs after the SAME candidate's unwindowed
        place_near returned None under the pre-eviction occupancy, so a cell
        that fits now was blocked then by e's own rects ALONE — the candidate's
        box, or one of its comps, must violate one of them. A violation on the
        x axis pins the origin inside (r.x - ext_lo - g, r.x + r.w + g -
        ext_hi), where ext_lo/ext_hi span the candidate's boxes about its
        origin and g bounds the pair-exact required gap (max over e's rects and
        all four facings of _fanout_sep, floored at CLEAR — the very terms
        ``fits`` applies). The bbox of that union over e's rects is returned:
        a SUPERSET window is equally sound, since the extra cells provably do
        not fit either. Pure acceleration — same first-fit cell as the full
        scan, at ~1/6 of the lattice."""
        erects = [(e.x, e.y, e.w, e.h, e.fanout_reach, e.fanout_inset)]
        erects += [(e.x + dx, e.y + dy, cw, ch, _ZeroReach, _ZeroReach)
                   for dx, dy, cw, ch, _cm in _bcomps(e)]
        g = max([CLEAR] + [_fanout_sep(a_r, a_i, r[4], r[5], axis)
                           for r in erects
                           for a_r, a_i in ((rch, ins),
                                            (_ZeroReach, _ZeroReach))
                           for axis in ("E", "W", "N", "S")])
        ex_lo = max([w] + [dx + cw for dx, _dy, cw, _ch, _cm in cc])
        ex_hi = min([0.0] + [dx for dx, _dy, _cw, _ch, _cm in cc])
        ey_lo = max([h] + [dy + ch for _dx, dy, _cw, ch, _cm in cc])
        ey_hi = min([0.0] + [dy for _dx, dy, _cw, _ch, _cm in cc])
        return (min(r[0] for r in erects) - ex_lo - g,
                max(r[0] + r[2] for r in erects) + g - ex_hi,
                min(r[1] for r in erects) - ey_lo - g,
                max(r[1] + r[3] for r in erects) + g - ey_hi)

    def _seat_shape(b: Block, ax: float, ay: float,
                    evicted: Block | None = None) -> bool:
        """Choose b's shape + cell at anchor (ax, ay) and WRITE it onto b.
        Returns False leaving b (and ``chosen_comps``) byte-untouched when no
        registered shape fits — the caller owns what happens next. Verbatim
        the historical loop body, hoisted so the retry below can re-run it;
        ``evicted`` only narrows each place_near to that block's proven
        window."""
        cands = shapes.get(b.name) if shapes else None
        if cands is None:
            cc0 = comps_of.get((b.name, 0), ()) if comps_of else ()
            pos = occ.place_near(ax, ay, b.w, b.h, b.fanout_reach,
                                 b.fanout_inset, OCC_TOP, cc0,
                                 None if evicted is None else _evict_window(
                                     evicted, b.w, b.h, b.fanout_reach,
                                     b.fanout_inset, cc0))
            if pos is None:
                return False
            b.shape_idx = 0
            b.side = "top"
            chosen_comps[b.name] = cc0
            b.x, b.y, b.w, b.h = pos
            return True
        by_side: dict[str, tuple] = {}
        for k, (w, h, rch, ins, sd, cc) in enumerate(cands):
            if w > BOARD_W - 2 * CLEAR or h > BOARD_H - 2 * CLEAR:
                continue
            p = occ.place_near(ax, ay, w, h, rch, ins, _side_mask(sd), cc,
                               None if evicted is None else _evict_window(
                                   evicted, w, h, rch, ins, cc))
            if p is None:
                continue
            d = abs(p[0] + w / 2 - ax) + abs(p[1] + h / 2 - ay)
            key = (round(d, 4), k)
            if sd not in by_side or key < by_side[sd][0]:
                by_side[sd] = (key, (k, p, rch, ins, sd, cc))
        if not by_side:
            return False
        if len(by_side) == 1:
            best = next(iter(by_side.values()))[1]
        else:
            def _est_of(cand, _b=b):
                k2, p2, _r2, _i2, sd2, _c2 = cand
                saved = (_b.x, _b.y, _b.w, _b.h, _b.shape_idx, _b.side)
                _b.x, _b.y, _b.w, _b.h = p2
                _b.shape_idx, _b.side = k2, sd2
                v = side_est(plan.edge_blocks + placed + [_b], _b.name)
                (_b.x, _b.y, _b.w, _b.h,
                 _b.shape_idx, _b.side) = saved
                return v

            best = _pick_sided(sorted(by_side.values()),
                               None if side_est is None else _est_of)
        k, p, rch, ins, sd, cc = best
        b.x, b.y, b.w, b.h = p
        b.shape_idx = k
        b.side = sd
        chosen_comps[b.name] = cc
        b.fanout_reach = rch
        b.fanout_inset = ins
        b.area = round(b.w * b.h, 1)
        return True

    def _blk_snap(bb: Block) -> tuple:
        return (tuple(getattr(bb, f) for f in _SEAT_FIELDS),
                chosen_comps.get(bb.name), centers.get(bb.name))

    def _blk_restore(bb: Block, s: tuple) -> None:
        for f, v in zip(_SEAT_FIELDS, s[0], strict=True):
            setattr(bb, f, v)
        for store, val in ((chosen_comps, s[1]), (centers, s[2])):
            if val is None:
                store.pop(bb.name, None)
            else:
                store[bb.name] = val

    evict_budget = [_RESEAT_EVICT_BUDGET]

    def _reseat_retry(b: Block, ax: float, ay: float) -> bool:
        """BOUNDED RE-SEAT RETRY (wave-17). The greedy first-fit above has no
        backtracking: when one block's every registered shape returns None the
        whole candidate outline dies, and that — not any block's geometry — is
        what walled the carrier at W = 172. Measured (wave-17 spec §3.1): at
        W in [168, 171] one block is fatal in 48/48 interior rejects, yet
        shrinking THAT block is worthless and non-monotone, while freeing 5 mm
        at a NEIGHBOURING seat packs all four widths. A first-fit ordering
        artefact, so the fix is search, not geometry.

        On a seat failure, EVICT ONE already-placed block and re-seat it:
        every ``placed`` block is a candidate, tried in ascending city-block
        distance from its centre to b's anchor, ties by placement index then
        name — a total order over a list, never a set/dict iteration over
        geometry. A trial seats b with the full shape chooser and then re-seats
        the evicted block AT ITS ALREADY-CHOSEN shape (the same
        remove/place_near/add step the Lloyd passes below use, so the re-seat
        cannot flip a copper face behind the estimator's back). A trial that
        fails at either step restores the pre-trial occupancy and block state
        exactly, and the next candidate is tried.

        DEPTH 1 IS THE MEASURED SUFFICIENT DEPTH: evicting up to TWO blocks
        per trial, and raising the budget to 6, were both measured to change
        NOTHING (identical pack verdict, identical est, at W = 171/170/169/168
        x 163) while costing ~10x the trials — so the pair search is not
        shipped. What the cap-4 obstructor shortlist of the original design
        DID cost was the whole win: with only the 4 nearest candidates the
        pack still failed at all four widths.

        Softens NOTHING: _Occupancy.fits is untouched, so every seat a retry
        produces was always legal — the retry only reaches arrangements the
        placement ORDER could not. Bounded and terminating: each success
        consumes one unit of a per-_attempt_pack budget of
        _RESEAT_EVICT_BUDGET, and a FAILED episode returns False from
        _attempt_pack, so at most _RESEAT_EVICT_BUDGET + 1 episodes run per
        call, each of at most |placed| < |interior| trials of at most
        |shapes(b)| + 1 place_near calls. No recursion, no cross-call state,
        no memoization."""
        if evict_budget[0] < 1:
            return False
        pool = [p for _d, _i, _n, p in sorted(
            (abs(p.x + p.w / 2 - ax) + abs(p.y + p.h / 2 - ay), i, p.name, p)
            for i, p in enumerate(placed))]
        for e in pool:
            esnap, bsnap = _blk_snap(e), _blk_snap(b)
            _occ_pull(e)
            ok = _seat_shape(b, ax, ay, e)
            if ok:
                _occ_put(b)
                centers[b.name] = (b.x + b.w / 2, b.y + b.h / 2)
                eax, eay = _anchor(e)
                epos = occ.place_near(eax, eay, e.w, e.h, e.fanout_reach,
                                      e.fanout_inset, _side_mask(e.side),
                                      _bcomps(e))
                if epos is None:
                    ok = False
                    _occ_pull(b)
                else:
                    e.x, e.y = epos[0], epos[1]
                    _occ_put(e)
                    centers[e.name] = (e.x + e.w / 2, e.y + e.h / 2)
            if ok:
                evict_budget[0] -= 1
                _fb.record("interior_reseat_retry")
                return True
            _blk_restore(b, bsnap)
            _blk_restore(e, esnap)
            _occ_put(e)
        return False

    for b in order:
        b.w, b.h = zbox[b.name]
        b.area = round(b.w * b.h, 1)
        ax, ay = _anchor(b)
        if _seat_shape(b, ax, ay):
            _occ_put(b)
            centers[b.name] = (b.x + b.w / 2, b.y + b.h / 2)
        elif not _reseat_retry(b, ax, ay):
            return False
        placed.append(b)

    # ITERATIVE REFINEMENT: the first pass anchored blocks on whatever neighbours
    # happened to be placed already, so a cluster's first member landed at its
    # zone seed with no pull. Now that EVERY interior block has a position, lift
    # each one out and re-drop it at the centroid of ALL its (now-placed)
    # neighbours + SoM — repeatedly, until positions settle. This is a
    # deterministic Lloyd-style relaxation that pulls scattered cluster members
    # (bringup_*, power*) together, directly shortening the cross airwire. Order
    # is fixed (most-connected first) so the result is reproducible. PASSES RAISED
    # 6 -> 16: more relaxation rounds let the cluster settle tighter (lower, more
    # monotonic cross-airwire across board sizes), so the grow loop can stop at a
    # smaller board instead of relying on a lucky packing only the big board found.
    for _pass in range(16):
        moved = False
        for b in order:
            occ.remove(b.x, b.y, b.w, b.h, b.fanout_reach, b.fanout_inset,
                       _side_mask(b.side), _bcomps(b))
            ax, ay = _anchor(b)
            pos = occ.place_near(ax, ay, b.w, b.h, b.fanout_reach,
                                 b.fanout_inset, _side_mask(b.side),
                                 _bcomps(b))
            if pos is None:                 # re-place where it was (always fits)
                occ.add(b.x, b.y, b.w, b.h, b.fanout_reach, b.fanout_inset,
                        _side_mask(b.side), _bcomps(b))
                continue
            nx, ny, _w, _h = pos
            if (nx, ny) != (b.x, b.y):
                moved = True
            b.x, b.y = nx, ny
            occ.add(b.x, b.y, b.w, b.h, b.fanout_reach, b.fanout_inset,
                    _side_mask(b.side), _bcomps(b))
            centers[b.name] = (b.x + b.w / 2, b.y + b.h / 2)
        if not moved:
            break

    # ---- T1 P6-wire: LEGALIZE(+COMPACT) the wired composition terms --------
    # (spec §6 P6 / D-3): every candidate board is legalized against the HARD
    # terms + the D13 channel corridors + T2's escape-lane rects; an
    # infeasible candidate is REJECTED so the outer smallest-area scan grows
    # (LAW 4 — nothing waived). Green-seed candidates come back UNTOUCHED
    # (seed-first short-circuit inside legalize_compact — the timing story);
    # the compaction objective (wired hop pulls) runs only when
    # ``compact=True`` (the fixed-outline call + the final re-pack).
    if compose is not None:
        c_index, c_metrics, c_channels, c_corridors, c_shape_metrics = compose
        chosen_m = {}
        for b in interior:
            if not b.shape_idx:
                continue
            sm = c_shape_metrics.get((b.name, b.shape_idx))
            if sm is None:
                raise AssertionError(
                    f"floorplan: {b.name} chose shape {b.shape_idx} but no "
                    f"per-shape zone metrics were registered — the legalizer "
                    f"would judge shape-0 geometry (silent breakage)")
            chosen_m[b.name] = sm
        if chosen_m:
            c_metrics = {**c_metrics, **chosen_m}
        if c_index.hard:
            from schgen.generate import floorplan_compose as fc_
            from schgen.generate.pcb.placement import som_core_rect
            parts_: set[str] = set()
            for t in c_index.hard:
                if t.kind in ("flow_hop", "near_max", "facing"):
                    parts_.add(t.subject)
                    parts_.add(t.target)
            inames = {b.name for b in interior}
            # movable = hard participants that are POSE-PREDICTABLE (the
            # l4_exempt partition). An L4-GUARDED participant (power_som
            # pre-P7) stays a FIXED rect: moving its pose re-rolls its L4
            # bottom slide — measured at the P6-wire gate: a 3.65mm
            # power_som compaction move flipped one intra-zone proximity
            # 34->35, REJECTED by the banded no-worsen rule. Guarded sheets
            # gain their solver DOF at their own wave (template + exempt).
            from schgen.verify.placement_contract_gate import (
                wired_term_participants,
            )
            _exempt, _ = wired_term_participants()
            movable_names = sorted(parts_ & inames & set(_exempt))
            if movable_names:
                fixed_rects: list[tuple[str, float, float, float, float]] = [
                    ("som", plan.som_x - _SOM_OCC_PAD,
                     plan.som_y - _SOM_OCC_PAD,
                     plan.som_x + plan.som.w + _SOM_OCC_PAD,
                     plan.som_y + plan.som.h + _SOM_OCC_PAD)]
                for kx, ky in ((0.0, 0.0), (BOARD_W - MH_CORNER_KO, 0.0),
                               (BOARD_W - MH_CORNER_KO,
                                BOARD_H - MH_CORNER_KO),
                               (0.0, BOARD_H - MH_CORNER_KO)):
                    fixed_rects.append((f"corner@{kx:g},{ky:g}", kx, ky,
                                        kx + MH_CORNER_KO,
                                        ky + MH_CORNER_KO))
                for b in plan.edge_blocks:
                    fixed_rects.append((b.name, b.x, b.y,
                                        b.x + b.w, b.y + b.h))
                for b in interior:
                    if b.name not in movable_names:
                        fixed_rects.append((b.name, b.x, b.y,
                                            b.x + b.w, b.y + b.h))
                fixed_rects.extend(c_corridors)
                fixed_poses = {b.name: (b.x, b.y)
                               for b in plan.edge_blocks}
                for b in interior:
                    if b.name not in movable_names:
                        fixed_poses[b.name] = (b.x, b.y)
                som_page = som_core_rect(plan.som_x, plan.som_y,
                                         plan.som.w, plan.som.h)
                _j_rects = {
                    f"som_j{j.ref[1:].lower()}": (
                        plan.som_x + j.x - j.w / 2, plan.som_y + j.y - j.h / 2,
                        plan.som_x + j.x + j.w / 2, plan.som_y + j.y + j.h / 2)
                    for j in plan.som.js}
                byn = {b.name: b for b in interior}
                orig = {b.name: (b.x, b.y) for b in interior}

                def _pairs_hold() -> bool:
                    # same predicate + same constraint SET as the occupancy
                    # lattice: every INTERIOR block vs everything (interior,
                    # edge, SoM pad, corner keepouts) — edge-vs-edge/corner
                    # belongs to the run packer (EDGE_MARGIN abuts the KO).
                    # Entities are component LISTS (main rect on its face
                    # mask + opposite-face/THT sub-rects), the same both-side
                    # truth + _occ_pair_active rule the lattice enforces.
                    zz = (_ZeroReach, _ZeroReach)

                    def _entity(bb: Block, mask: int, cc: tuple
                                ) -> list[tuple]:
                        ent = [(bb.x, bb.y, bb.w, bb.h,
                                bb.fanout_reach, bb.fanout_inset,
                                mask, mask, True)]
                        for dx, dy, cw, ch, cm in cc:
                            ent.append((round(bb.x + dx, 4),
                                        round(bb.y + dy, 4),
                                        cw, ch, *zz, cm, mask, False))
                        return ent

                    ents = ([_entity(b, _side_mask(b.side), _bcomps(b))
                             for b in interior]
                            + [_entity(b, edge_mask, edge_comps[b.name])
                               for b in plan.edge_blocks]
                            + [[(*som_occ, *zz, som_mask, som_mask, True)]
                               + [(round(som_occ[0] + dx, 4),
                                   round(som_occ[1] + dy, 4), cw, ch, *zz,
                                   cm, som_mask, False)
                                  for dx, dy, cw, ch, cm in som_comps]]
                            + [[(kx, ky, MH_CORNER_KO, MH_CORNER_KO, *zz,
                                 OCC_PUNCH, OCC_PUNCH, True)]
                               for kx, ky in
                               ((0.0, 0.0), (BOARD_W - MH_CORNER_KO, 0.0),
                                (BOARD_W - MH_CORNER_KO,
                                 BOARD_H - MH_CORNER_KO),
                                (0.0, BOARD_H - MH_CORNER_KO))])
                    for i in range(len(interior)):
                        for j in range(i + 1, len(ents)):
                            for (ax, ay, aw, ah, ar, ai, am, apm,
                                 amn) in ents[i]:
                                for (bx, by, bw, bh, br, bi, bm, bpm,
                                     bmn) in ents[j]:
                                    if not _occ_pair_active(
                                            am, apm, amn, bm, bpm, bmn):
                                        continue
                                    gx = max(CLEAR, _fanout_sep(
                                        ar, ai, br, bi,
                                        "E" if ax <= bx else "W"))
                                    gy = max(CLEAR, _fanout_sep(
                                        ar, ai, br, bi,
                                        "S" if ay <= by else "N"))
                                    if not (ax + aw + gx <= bx
                                            or bx + bw + gx <= ax
                                            or ay + ah + gy <= by
                                            or by + bh + gy <= ay):
                                        return False
                    return True

                def _legalize(do_compact: bool) -> bool:
                    # a result whose rects overlap OR violate a D13 pair gap
                    # is REJECTED, not emitted — the legalizer moves interior
                    # blocks at flat CLEAR, blind to reach/inset (measured:
                    # power compacted to 0.30 of user_io against a 1.15 pair
                    # requirement, Q20001 emitted 0.938 < 1.50; power_mon to
                    # 0.30 of usb_jtag against 0.90, U21002 1.450 < 2.00).
                    for b in interior:
                        b.x, b.y = orig[b.name]
                    mv = [fc_.LegalizeVar(b.name, b.w, b.h, (b.x, b.y),
                                          b.x, b.y)
                          for b in interior if b.name in movable_names]
                    lg: list[str] = []
                    if not fc_.legalize_compact(
                            BOARD_W, BOARD_H, som_page, fixed_rects, mv,
                            c_index, c_metrics, fixed_poses, c_channels,
                            CLEAR, compact=do_compact, log=lg,
                            som_j_rects=_j_rects):
                        return False
                    for v in mv:
                        byn[v.name].x = v.x
                        byn[v.name].y = v.y
                    if not _pairs_hold():
                        return False
                    plan.composition = lg
                    return True

                # COMPACTION may only land when it keeps every D13 pair gap;
                # otherwise fall back to the legalize-only form the outline
                # scan accepted (fresh deterministic pack, nothing stale).
                if not _legalize(compact):
                    if not (compact and _legalize(False)):
                        return False
                    _fb.record("legalize_only_compaction")
    return True


def _choose_conn_shapes(plan: Plan, interior: list[Block],
                        edge_of: dict[str, str],
                        zbox: dict[str, tuple[float, float]],
                        affinity: dict[str, dict[str, float]],
                        som_pull: dict[str, float], compose, compact: bool,
                        far_ceil: float, max_reach: float | None,
                        shape_sets, comps_of, zg, est_cross) -> None:
    """MEMBER-FIELD MIRROR choice for connector-seated zones (wave-8 U3): a
    conn-seated block never enters the interior shape search (LAW 6 pins it to
    its edge run), so its registered mirror variant is chosen HERE, on the
    final board — re-pack the WHOLE board with the mirror's reach/inset bound
    in (the same legality path every candidate board takes) and keep the
    mirror iff the pack stays legal AND the airwire kernel (the LAW-5 gate's
    _mst_edges) strictly improves. Deterministic: sorted blocks, strict <; on
    reject the incumbent pack is restored by re-running the identical
    deterministic pack."""

    def _repack() -> bool:
        return _attempt_pack(plan, interior, edge_of, zbox, affinity,
                             som_pull, compose=compose, compact=compact,
                             far_ceil=far_ceil, max_reach=max_reach,
                             shapes=shape_sets, comps_of=comps_of,
                             side_est=est_cross)

    for b in sorted(plan.edge_blocks, key=lambda x: x.name):
        variants = zg.shapes.get(b.name)
        if not variants or len(variants) < 2:
            continue
        base_cross = est_cross(plan.edge_blocks + interior)
        base_ri = (b.fanout_reach, b.fanout_inset)
        b.fanout_reach, b.fanout_inset = _shape_fanout_reach(variants[1], zg)
        b.shape_idx = 1
        if _repack() and est_cross(plan.edge_blocks + interior) \
                < base_cross - 1e-6:
            continue
        b.fanout_reach, b.fanout_inset = base_ri
        b.shape_idx = 0
        if not _repack():
            raise RuntimeError(
                f"floorplan: restoring the incumbent pack after rejecting "
                f"{b.name}'s mirror shape failed — the deterministic re-pack "
                f"must reproduce the accepted board")


# ---- notes ------------------------------------------------------------------------

@dataclass(frozen=True)
class Note:
    n: int
    block: str       # sheet name ("" = board-level, MD only)
    short: str       # SVG legend line
    long: str        # MD bullet


def _has_value(c, prefix: str) -> bool:
    return any(p.value.startswith(prefix) for p in c.parts.values())


def _pair_count(c, kind: str) -> int:
    return sum(1 for pt in c.port_types.values() if pt.kind == kind) // 2


def build_notes(plan: Plan, sheets, regs) -> list[Note]:
    from schgen.verify.powertree import rail_volts
    by_name = {sc.name: sc.circuit for sc in sheets}
    notes: list[Note] = []

    def add(block: str, short: str, long: str = "") -> None:
        notes.append(Note(len(notes) + 1, block, short, long or short))

    edge_order = {"N": 0, "W": 1, "E": 2, "S": 3}
    ordered = sorted(plan.edge_blocks,
                     key=lambda b: (edge_order[b.edge], b.x, b.y)) \
        + sorted(plan.interior_blocks, key=lambda b: b.name)
    for b in ordered:
        c = by_name[b.name]
        nets = set(c.nets)
        conn_vals = {v for _r, v, _w, _h in b.conns}
        if "TYPE-C-31-M-12" in conn_vals and "+VIN" in nets:
            efuse = _has_value(c, "TPS2594")
            add(b.name,
                "power inlet: VBUS->TVS->bulk->+VIN; CC pair to FUSB302",
                "PD power inlet: keep the VBUS path (receptacle -> "
                + ("eFuse soft-start -> " if efuse else "")
                + "TVS -> bulk -> +VIN) in one corner so the +VIN plane "
                "spreads from a single point; CC1/CC2 route to the FUSB302 "
                "(usb_pd block, anchored next to this inlet)."
                + ("" if efuse else " PLAN.md round 5: a TPS25940-class "
                   "eFuse lands between receptacle and bulk — reserve "
                   "space for it here."))
        elif "TYPE-C-31-M-12" in conn_vals:
            esd = next((p.value for p in c.parts.values()
                        if p.value.startswith(("USBLC", "TPD"))), "")
            add(b.name,
                "USB-C OTG: 90R HS pair short + matched; ESD at conn",
                "USB-C OTG: the 90R D+/D- pair wants the shortest matched "
                "run to its SoM pins; "
                + (f"{esd} ESD array within ~10 mm of the receptacle; "
                   if esd else "")
                + "VBUS source switch beside the connector.")
        if "HDMI-019S" in conn_vals:
            np = _pair_count(c, "tmds_pair")
            shifter = next((p.value for p in c.parts.values()
                            if p.value.startswith(("TPD12S", "M24C"))),
                           "the companion IC")
            add(b.name,
                f"{np} TMDS pairs 100R; companion IC at connector",
                f"{np} TMDS pairs at 100R differential, intra-pair skew "
                f"<= 0.15 mm (constraints.py); place {shifter} directly "
                "behind the receptacle so all pairs pass straight "
                "through.")
        if b.name in ("ethernet",) or _has_value(c, "HX5008"):
            add(b.name,
                "magnetics keep-out: no planes line-side; 100R MDI",
                "Magnetics isolation: void ALL planes under the HX5008 "
                "line side + Bob-Smith network (CHASSIS_GND moat to the "
                "RJ45); MDI pairs are 100R differential. RJ45 itself is "
                "an author-declared deferral (expect rj45_connector) — "
                "the dashed reservation is its landing zone.")
        if "TF-01A" in conn_vals:
            add(b.name,
                "SDIO 1.8V island: TXS02612 splits 1.8V / 3.3V sides",
                "microSD: SDIO runs at 1.8 V on the SoM side (typed "
                "sd_bus level in the netlist) — keep the TXS02612 "
                "translator mid-block: 1.8V side faces the SoM, 3.3V card "
                "side faces the slot; bus length match <= 2.5 mm to CLK.")
        if "AFC07-S40FCA-00" in conn_vals:
            boost = next((p.value for p in c.parts.values()
                          if p.value.startswith("SY7201")), "")
            add(b.name,
                "LCD FFC exit; backlight boost loop tight",
                "40-pin LCD FFC: cable exits over the board edge; "
                + (f"keep the {boost} backlight boost loop (L/D/C) tight "
                   "and away from the FFC signal rows; " if boost else "")
                + "RGB888 bus is single-ended bank-34 3V3 — bus-route "
                "together.")
        if "SFW15R-1STE1LF" in conn_vals:
            np = _pair_count(c, "diff_pair")
            add(b.name,
                f"camera FFC: {np} CSI-2 pairs 100R to J3 side",
                f"RPi camera FFC: {np} MIPI CSI-2 pairs at 100R "
                "differential to the J3 side of the SoM (bank 35, 2.5 V "
                "VCCO per the expect= notes) — keep the run to the J3 "
                "strip short.")
        if "DS1024-2x6R2" in conn_vals:
            add(b.name,
                "PMOD pair on gated +3V3_PMOD rail",
                "Two PMOD sockets side by side; both fed from the gated "
                "+3V3_PMOD rail (SY6280 cell in bringup_modules) — route "
                "the gated rail once, star at the sockets.")
        if "TLV75725PDYDR" in conn_vals or any(
                r.sheet == b.name and "TLV75725" in r.value for r in regs):
            ldo = next((r for r in regs if r.sheet == b.name), None)
            if ldo is not None:
                vi = rail_volts(ldo.vin) or 0.0
                vo = rail_volts(ldo.vout) or 0.0
                add(b.name,
                    "bank-35 IO header: VADJ LDO copper",
                    f"{ldo.value} VADJ LDO dissipates ~"
                    f"{(vi - vo) * ldo.i_out:.2f} W at the declared "
                    f"{ldo.i_out:g} A — give its EP pad a ground pour.")
        if "usb_uart_connector" in b.reserved:
            add(b.name,
                "USB-UART conn deferred; TPs on TX/RX",
                "CP2102N UART bridge: its USB connector is an "
                "author-declared deferral (expect usb_uart_connector) — "
                "the block reserves edge space for it; TX/RX test points "
                "stay probe-able.")
        if b.name == "power":
            bucks = [r for r in regs if r.sheet == b.name
                     and r.kind == "buck"]
            diss = []
            for r in bucks:
                vo = rail_volts(r.vout) or 0.0
                diss.append(f"{r.value} {r.vout} ~"
                            f"{(1 / r.eff - 1) * vo * r.i_out:.2f} W")
            add(b.name,
                "2 bucks: thermal copper + vias; keep SW loops tight",
                "Buck thermal (worst-case declared draws): "
                + "; ".join(diss)
                + ". Pour copper on the SW/PGND side, stitch vias under "
                "the packages, keep each SW node loop minimal.")
        if b.name == "bringup_modules":
            gated = sorted(r.vout for r in regs if r.sheet == b.name)
            add(b.name,
                f"{len(gated)} load switches: gated-rail star points",
                f"{len(gated)} SY6280 load-switch cells; each gated rail "
                "(" + ", ".join(gated) + ") stars from its switch — place "
                "this block centrally so every gated rail leaves toward "
                "its module without crossing the others.")
        if b.name == "bringup_rails":
            add(b.name,
                "rail-EN DIPs + PG LEDs: human access",
                "Rail-enable DIP switches + power-good LEDs: face them "
                "where fingers and eyes reach them with the mezzanine "
                "mounted — keep clear of the SoM shadow.")
        if b.name == "power_mon":
            add(b.name,
                "INA3221 shunts sit IN the rail path",
                "Power monitor: the shunt resistors are in series with "
                "the rails — the rails must physically route through this "
                "block; place it between the regulators and the loads, "
                "Kelvin-connect the sense pairs.")
        if b.name == "debug_boot":
            add(b.name,
                "JTAG/SWD headers vertical: probe clearance",
                "JTAG (2x7 2 mm) + SWD (2x5 1.27 mm) headers mate "
                "vertically — any top-side spot works; keep cable/probe "
                "clearance and the boot DIP reachable.")
        if b.name == "usb_pd":
            add(b.name,
                "FUSB302 beside inlet: short CC stubs",
                "FUSB302 PD controller: anchored beside the pd_input "
                "receptacle so CC1/CC2 stay short stubs; I2C runs to the "
                "SoM J1 side.")
        if b.name == "user_io":
            add(b.name,
                "LEDs + buttons human-facing",
                "User LEDs + buttons: human-facing — keep at the "
                "accessible S side, clear of the PMOD cable shadow.")
    # board-level (MD-only) notes
    n_tp = sum(1 for sc in sheets for r in sc.circuit.parts
               if r.startswith("TP"))
    notes.append(Note(0, "",
                      f"{n_tp} test points board-wide",
                      f"{n_tp} test points board-wide (test-point gate): "
                      "spread them with probe clearance as the blocks "
                      "settle; none may end up under the SoM."))
    return notes


# ---- SVG --------------------------------------------------------------------------

OX, OY = 46.0, 64.0


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _px(x: float) -> float:
    return round(OX + x * SCALE, 1)


def _py(y: float) -> float:
    return round(OY + y * SCALE, 1)


def render_svg(plan: Plan, notes: list[Note], out: Path) -> Path:
    note_of: dict[str, list[int]] = {}
    for nt in notes:
        if nt.block:
            note_of.setdefault(nt.block, []).append(nt.n)
    legend = [nt for nt in notes if nt.n]

    W = int(OX + BOARD_W * SCALE + 30 + 400)
    H = int(max(OY + BOARD_H * SCALE + 56, 130 + len(legend) * 22 + 20))
    e: list[str] = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {W} {H}" font-family="{FONT}" font-size="11">')
    e.append('<defs><pattern id="keepout" width="6" height="6" '
             'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<line x1="0" y1="0" x2="0" y2="6" stroke="#dc2626" '
             'stroke-width="1.2"/></pattern></defs>')
    e.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    e.append(f'<text x="{OX}" y="26" font-size="16" font-weight="bold">'
             f'carrier floorplan — SUGGESTION, not constraint</text>')
    e.append(f'<text x="{OX}" y="44" fill="#6b7280">to scale; derived from '
             f'the netlists + {_esc(plan.som.source)} — regenerate with '
             f'`schgen floorplan`; the user owns the outline (PLAN.md '
             f'round 2)</text>')

    # board outline (suggested -> dashed) + 10 mm grid
    bx, by = _px(0), _py(0)
    bw, bh = BOARD_W * SCALE, BOARD_H * SCALE
    e.append(f'<rect x="{bx}" y="{by}" width="{bw:g}" height="{bh:g}" '
             f'fill="#fcfcfd" stroke="#111827" stroke-width="2" '
             f'stroke-dasharray="9,5"/>')
    for gx in range(10, int(BOARD_W), 10):
        e.append(f'<line x1="{_px(gx)}" y1="{by}" x2="{_px(gx)}" '
                 f'y2="{_py(BOARD_H)}" stroke="#eceef1" stroke-width="1"/>')
        e.append(f'<text x="{_px(gx)}" y="{by - 4}" fill="#9ca3af" '
                 f'font-size="8" text-anchor="middle">{gx}</text>')
    for gy in range(10, int(BOARD_H), 10):
        e.append(f'<line x1="{bx}" y1="{_py(gy)}" x2="{_px(BOARD_W)}" '
                 f'y2="{_py(gy)}" stroke="#eceef1" stroke-width="1"/>')
        e.append(f'<text x="{bx - 6}" y="{_py(gy) + 3}" fill="#9ca3af" '
                 f'font-size="8" text-anchor="end">{gy}</text>')
    e.append(f'<text x="{bx}" y="{_py(BOARD_H) + 16}" fill="#6b7280">'
             f'derived outline {BOARD_W:g} x {BOARD_H:g} mm '
             f'(SoM + connector bands + component area + perimeter keepout)'
             f'</text>')

    # blocks under the SoM so the SoM reads on top
    for b in sorted(plan.blocks, key=lambda b: b.name):
        x, y = _px(b.x), _py(b.y)
        w, h = b.w * SCALE, b.h * SCALE
        if b.kind == "edge":
            fill, stroke = "#eff6ff", "#1e3a8a"
        elif b.name.startswith(("power", "bringup")):
            fill, stroke = "#ecfdf5", "#047857"
        else:
            fill, stroke = "#f9fafb", "#374151"
        dash = ' stroke-dasharray="5,4"' if (b.reserved and not b.conns) \
            else ""
        e.append(f'<rect x="{x}" y="{y}" width="{w:g}" height="{h:g}" '
                 f'rx="3" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.4"{dash}/>')
        # physical connector strips, flush at the block's board edge,
        # equal gaps between multiple connectors (to scale)
        n_c = len(b.conns)
        run = sum(c[2] for c in b.conns)
        for k, (_ref, _val, cw, cd) in enumerate(b.conns):
            if b.edge in ("N", "S", ""):
                gap = (b.w - run) / (n_c + 1)
                cx0 = b.x + gap * (k + 1) + sum(c[2] for c in b.conns[:k])
                cw_, ch_ = cw, cd
                cy0 = b.y + b.h - cd if b.edge == "S" else b.y
            else:
                gap = (b.h - run) / (n_c + 1)
                cy0 = b.y + gap * (k + 1) + sum(c[2] for c in b.conns[:k])
                cw_, ch_ = cd, cw
                cx0 = b.x if b.edge == "W" else b.x + b.w - cd
            e.append(f'<rect x="{_px(cx0)}" y="{_py(cy0)}" '
                     f'width="{cw_ * SCALE:g}" height="{ch_ * SCALE:g}" '
                     f'fill="#bfdbfe" stroke="#1e3a8a" '
                     f'stroke-width="1.2"/>')
        if b.name == "ethernet":      # magnetics line-side keep-out wash,
            kx, ky, kw, kh = x, y, w, h / 2      # on the connector side
            if b.edge == "S":
                ky = y + h / 2
            elif b.edge == "E":
                kx, kw, kh = x + w / 2, w / 2, h
            elif b.edge == "W":
                kw, kh = w / 2, h
            e.append(f'<rect x="{kx:g}" y="{ky:g}" width="{kw:g}" '
                     f'height="{kh:g}" fill="url(#keepout)" '
                     f'opacity="0.5"/>')
        # label (rotated on W/E edges), part count below
        cx, cy = _px(b.cx), _py(b.cy)
        if b.edge in ("W", "E") and h > w:      # vertical: two columns
            fs = min(11.0, max(7.0, (h - 6) / (0.62 * max(1, len(b.name)))))
            e.append(f'<text x="{cx - 3:g}" y="{cy}" text-anchor="middle" '
                     f'font-size="{fs:.1f}" font-weight="bold" '
                     f'transform="rotate(-90 {cx - 3:g} {cy})">'
                     f'{_esc(b.name)}</text>')
            e.append(f'<text x="{cx + 8:g}" y="{cy}" text-anchor="middle" '
                     f'font-size="7.5" fill="#6b7280" '
                     f'transform="rotate(-90 {cx + 8:g} {cy})">'
                     f'{b.n_parts}p</text>')
        else:
            fs = min(11.0, max(7.0, (w - 6) / (0.62 * max(1, len(b.name)))))
            e.append(f'<text x="{cx}" y="{cy}" text-anchor="middle" '
                     f'font-size="{fs:.1f}" font-weight="bold">'
                     f'{_esc(b.name)}</text>')
            e.append(f'<text x="{cx}" y="{cy + 10}" text-anchor="middle" '
                     f'font-size="7.5" fill="#6b7280">{b.n_parts}p</text>')
        for k, nn in enumerate(note_of.get(b.name, [])):
            bcx, bcy = x + 16 * k, y      # on the block's top-left corner
            e.append(f'<circle cx="{bcx:g}" cy="{bcy:g}" r="7" '
                     f'fill="white" stroke="#111827" stroke-width="1.2"/>')
            e.append(f'<text x="{bcx:g}" y="{bcy + 3:g}" '
                     f'text-anchor="middle" font-size="9" '
                     f'font-weight="bold">{nn}</text>')

    # SoM on top
    sx, sy = _px(plan.som_x), _py(plan.som_y)
    sw, sh = plan.som.w * SCALE, plan.som.h * SCALE
    e.append(f'<rect x="{sx}" y="{sy}" width="{sw:g}" height="{sh:g}" '
             f'rx="8" fill="#fef3c7" stroke="#92400e" stroke-width="2" '
             f'opacity="0.95"/>')
    e.append(f'<text x="{sx + sw / 2:g}" y="{sy + sh / 2 - 6:g}" '
             f'text-anchor="middle" font-size="13" font-weight="bold" '
             f'fill="#92400e">Zynq SoM {plan.som.w:g} x {plan.som.h:g}</text>')
    e.append(f'<text x="{sx + sw / 2:g}" y="{sy + sh / 2 + 10:g}" '
             f'text-anchor="middle" font-size="8.5" fill="#92400e">'
             f'(bottom view: DF40 positions mirrored from the SoM PCB)'
             f'</text>')
    for j in plan.som.js:
        jx = _px(plan.som_x + j.x - j.w / 2)
        jy = _py(plan.som_y + j.y - j.h / 2)
        e.append(f'<rect x="{jx}" y="{jy}" width="{j.w * SCALE:g}" '
                 f'height="{j.h * SCALE:g}" fill="#92400e"/>')
        lx = _px(plan.som_x + j.x)
        ly = _py(plan.som_y + j.y)
        rot = (f' transform="rotate(-90 {lx} {ly + 3.5:g})"'
               if j.w < j.h else "")        # vertical strip: rotated label
        e.append(f'<text x="{lx}" y="{ly + 3.5:g}" text-anchor="middle" '
                 f'font-size="10" font-weight="bold" fill="white"{rot}>'
                 f'{j.ref}</text>')

    # scale bar
    sb_y = _py(BOARD_H) + 30
    e.append(f'<line x1="{bx}" y1="{sb_y}" x2="{_px(20)}" y2="{sb_y}" '
             f'stroke="#111827" stroke-width="3"/>')
    e.append(f'<text x="{_px(10)}" y="{sb_y + 14}" text-anchor="middle" '
             f'fill="#6b7280">20 mm</text>')

    # legend
    lx = OX + BOARD_W * SCALE + 30
    e.append(f'<text x="{lx:g}" y="{OY + 4:g}" font-size="13" '
             f'font-weight="bold">placement notes (derived)</text>')
    for i, nt in enumerate(legend):
        yy = OY + 26 + i * 22
        e.append(f'<circle cx="{lx + 8:g}" cy="{yy - 4:g}" r="8" '
                 f'fill="white" stroke="#111827" stroke-width="1.2"/>')
        e.append(f'<text x="{lx + 8:g}" y="{yy - 1:g}" text-anchor="middle"'
                 f' font-size="9" font-weight="bold">{nt.n}</text>')
        e.append(f'<text x="{lx + 24:g}" y="{yy:g}">'
                 f'{_esc(nt.short)}</text>')
    foot = OY + 26 + len(legend) * 22 + 12
    e.append(f'<text x="{lx:g}" y="{foot:g}" fill="#6b7280" font-size="10">'
             f'block area = courtyards (big parts raw, small x'
             f'{plan.factor:g}) — see FLOORPLAN.md</text>')
    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


# ---- markdown ---------------------------------------------------------------------

def render_md(plan: Plan, notes: list[Note], sheets, regs,
              out: Path) -> Path:
    from schgen.generate import constraints as cst
    from schgen.verify.powertree import rail_volts

    note_of: dict[str, list[int]] = {}
    for nt in notes:
        if nt.block:
            note_of.setdefault(nt.block, []).append(nt.n)

    L: list[str] = []
    L.append("# Carrier floorplan — SUGGESTION, not constraint")
    L.append("")
    L.append("Generated by `schgen floorplan` (also by `schgen board`). "
             "**The user owns the outline and the placement** — PLAN.md "
             "round 2 leaves the form factor free (\"connector-driven "
             "~120x100 class expected\"). This document is one "
             "self-consistent, to-scale starting point whose every number "
             "is derived from the design data, so each suggestion can be "
             "kept or overruled deliberately. Shuffle blocks freely; the "
             "WHY notes say what each move costs.")
    L.append("")
    L.append("![floorplan](FLOORPLAN.svg)")
    L.append("")
    L.append("## Sources (everything derived, nothing invented)")
    L.append("")
    L.append(f"- SoM outline + DF40 positions: `{plan.som.source}` "
             "(Edge.Cuts bbox + J1/J2/J3 footprints, parsed live)")
    L.append("- block sizes: per-part courtyards (`parts/<MPN>/"
             "<MPN>.kicad_mod` F.CrtYd; KiCad-standard footprints from "
             "the dims in their names), big parts raw + small parts x"
             f"{plan.factor:g} routing factor")
    L.append("- edge pinning + zones: connector parts in each sheet "
             "netlist + linker J1/J2/J3 bindings (incl. `expect=` "
             "deferrals)")
    L.append("- electrical notes: `schgen/constraints.py` "
             "(JLC04161H-7628), `schgen/powertree.py` analysis, typed "
             "ports (1.8V SDIO)")
    L.append("")
    L.append("## Extracted SoM geometry")
    L.append("")
    L.append(f"SoM outline: **{plan.som.w:g} x {plan.som.h:g} mm**. The "
             "DF40 mezzanine connectors sit on the SoM's bottom copper; "
             "the carrier-top view below mirrors their X coordinate "
             "(bottom view). Verify mate orientation against the DF40 "
             "datasheet before committing footprints.")
    L.append("")
    L.append("| conn | SoM PCB `(at)` | carrier-top view (SoM-rel) | "
             "pad extent |")
    L.append("|---|---|---|---|")
    for j in plan.som.js:
        L.append(f"| {j.ref} | ({j.pcb_x:g}, {j.pcb_y:g}) rot {j.rot:g} | "
                 f"({j.x:g}, {j.y:g}) | {j.w:g} x {j.h:g} mm |")
    L.append("")
    L.append(f"Derived board: **{BOARD_W:g} x {BOARD_H:g} mm**; SoM "
             f"origin at **({plan.som_x:g}, {plan.som_y:g})** "
             "(centered). All coordinates below are board-frame mm, "
             "origin top-left, +y down (KiCad convention).")
    L.append("")
    L.append(f"Outline derivation: {OUTLINE_NOTE}.")
    L.append("")
    L.append("## Edge connectors (pinned to edges by their mating "
             "direction)")
    L.append("")
    L.append("| edge | sheet | block (x, y, w x h) | connector(s) | "
             "notes |")
    L.append("|---|---|---|---|---|")
    edge_order = {"N": 0, "W": 1, "E": 2, "S": 3}
    for b in sorted(plan.edge_blocks,
                    key=lambda b: (edge_order[b.edge], b.x, b.y)):
        conns = ", ".join(f"{v} ({_EDGE_FAMILIES.get(v, '?')})"
                          for _r, v, _w, _h in b.conns)
        if b.reserved:
            conns = (conns + "; " if conns else "") + ", ".join(
                f"RESERVED: {r} (deferred)" for r in b.reserved)
        nn = " ".join(f"({k})" for k in note_of.get(b.name, []))
        L.append(f"| {b.edge} | {b.name} | ({b.x:g}, {b.y:g}, "
                 f"{b.w:g} x {b.h:g}) | {conns} | {nn} |")
    if plan.spilled:
        L.append("")
        L.append("Edge spills (preferred edge full — honest, not "
                 "hidden):")
        for s in plan.spilled:
            L.append(f"- {s}")
    L.append("")
    L.append("## Interior blocks (zone = dominant SoM connector side, "
             "or the power cluster)")
    L.append("")
    L.append("| sheet | anchor | block (x, y, w x h) | parts | est mm2 | "
             "notes |")
    L.append("|---|---|---|---|---|---|")
    for b in sorted(plan.interior_blocks, key=lambda b: b.name):
        nn = " ".join(f"({k})" for k in note_of.get(b.name, []))
        L.append(f"| {b.name} | {b.zone} | ({b.x:g}, {b.y:g}, {b.w:g} x "
                 f"{b.h:g}) | {b.n_parts} | {b.area:g} | {nn} |")
    L.append("")
    L.append("## Routing constraint classes (JLC04161H-7628 — from "
             "constraints.py)")
    L.append("")
    classes: dict[str, dict] = {}
    for sc in sorted(sheets, key=lambda s: s.name):
        for name, pt in sorted(sc.circuit.port_types.items()):
            if pt.kind == "single":
                continue
            ncls = cst._net_class(pt.kind, pt.impedance, pt.level_v)
            d = classes.setdefault(ncls, {"nets": set(), "kind": pt.kind,
                                          "imp": pt.impedance})
            d["nets"].add(name)
    L.append("| class | nets | geometry (track/gap mm) | match budget |")
    L.append("|---|---|---|---|")
    for ncls, d in sorted(classes.items()):
        geo = cst.GEOMETRY.get(d["imp"]) if d["imp"] else None
        gtxt = (f"{geo.width_mm:g} / {geo.gap_mm:g}" if geo else "-")
        if d["kind"] in cst.INTRA_PAIR_SKEW_MM:
            match = (f"intra-pair <= "
                     f"{cst.INTRA_PAIR_SKEW_MM[d['kind']]:g} mm")
            if d["kind"] == "tmds_pair":
                match += "; inter-pair <= 5 mm (policy)"
        elif d["kind"] == "sd_bus":
            match = f"bus to CLK <= {cst.SD_BUS_MATCH_MM:g} mm"
        else:
            match = "-"
        L.append(f"| {ncls} | {len(d['nets'])} | {gtxt} | {match} |")
    L.append("")
    L.append("Full per-net table: "
             "`carrier/manufacturing/layout_constraints.csv` (+ the "
             "`.kicad_dru` rules).")
    L.append("")
    L.append("## Power and thermal (worst-case declared draws — "
             "powertree analysis)")
    L.append("")
    L.append("| regulator | sheet | rail | I out (A) | est dissipation |")
    L.append("|---|---|---|---|---|")
    for r in regs:
        vo = rail_volts(r.vout) or 0.0
        vi = rail_volts(r.vin) or 0.0
        if r.kind == "buck":
            p = (1 / r.eff - 1) * vo * r.i_out
        elif r.kind == "ldo":
            p = max(0.0, vi - vo) * r.i_out
        else:
            p = 0.0
        ptxt = f"~{p:.2f} W" if p >= 0.05 else "negligible"
        L.append(f"| {r.value} ({r.ref}) | {r.sheet} | {r.vin} -> "
                 f"{r.vout} | {r.i_out:.3f} | {ptxt} |")
    L.append("")
    L.append("Numbers are the power-tree gate's worst-case declared "
             "draws (`carrier/reports/power_tree.txt`); regulators above "
             "~0.3 W want copper pours + stitching vias.")
    L.append("")
    L.append("## Placement notes (the WHYs)")
    L.append("")
    for nt in notes:
        tag = f"**({nt.n}) {nt.block}**" if nt.n else "**(board)**"
        L.append(f"- {tag}: {nt.long}")
    L.append("")
    L.append("## Honest limits")
    L.append("")
    L.append("- Block rectangles are AREA estimates (courtyards + "
             "routing factor), not layouts; their order along an edge "
             "is alphabetical, not optimized — shuffle freely.")
    L.append("- The outline is DERIVED (SoM body + connector bands + total "
             "component area + perimeter keepout), sized generously for "
             "routing headroom; the user still owns it (drawn dashed).")
    L.append("- The mirror convention (bottom view) must be checked "
             "against the DF40 mating datasheet before any footprint is "
             "placed.")
    L.append("- som_j1/j2/j3 sheets are not blocks: they ARE the three "
             "DF40 strips drawn inside the SoM footprint.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    return out


# ---- entry points -----------------------------------------------------------------

def generate(sheets=None, link_result=None) -> list[Path]:
    from schgen.core.link import (
        all_subsystem_paths,
        link,
        load_som_contract,
        load_subsystem,
    )
    from schgen.verify import powertree
    if sheets is None:
        sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    if link_result is None:
        link_result = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    plan = build_plan(sheets, link_result, regs)
    notes = build_notes(plan, sheets, regs)
    svg = render_svg(plan, notes, OUT_SVG)
    md = render_md(plan, notes, sheets, regs, OUT_MD)
    return [svg, md]


def cmd_floorplan(args: argparse.Namespace) -> int:
    if getattr(args, "export", False):
        # Round-trip seed: build the CURRENT plan and write it out as the
        # editable carrier/floorplan.json. Built WITHOUT the spec influencing the
        # result on a clean export (so the seed reflects the pure auto layout);
        # if a spec already exists it still validates against the sheet names.
        from schgen.core.link import (
            all_subsystem_paths,
            link,
            load_som_contract,
            load_subsystem,
        )
        from schgen.verify import powertree
        sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
        link_result = link(sheets, load_som_contract())
        regs = powertree.analyze(sheets).regs
        plan = build_plan(sheets, link_result, regs)
        out = export_floorplan_spec(plan)
        print(f"floorplan spec: {out.relative_to(REPO_ROOT)} "
              f"({len(plan.edge_blocks)} edge + {len(plan.interior_blocks)} "
              f"interior subsystems)")
        print("FLOORPLAN: declarative spec exported — edit it then re-run "
              "`schgen board` to drive the placement")
        return 0
    paths = generate()
    for p in paths:
        print(f"floorplan: {p.relative_to(REPO_ROOT)}")
    print("FLOORPLAN: suggestion written (derived from netlists — "
          "see the honest-limits section)")
    return 0
