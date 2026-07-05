"""DF40 mezzanine ESCAPE copper — carrier-side return-path stitching (T2).

WHAT THIS BUILDS (Tier-1, emitted locked copper):
  * banded GND STITCH VIAS in the DF40 inter-row channels, one band per
    contiguous group of return-path-v1-failing contacts (triage-ordered:
    GENUINE bands seat first);
  * an F.Cu GND LADDER per remediated connector — a channel SPINE plus
    GND-pad STUBS (pair-gap / single-column / single-pad variants) — so every
    stitch via has file-visible copper connectivity (never fill-dependent);
  * NO zone: the In1.Cu GND plane the vias land on is GAP1's canonical
    board-interior zone (embed._gnd_plane_zone @ 28f8e15, unfilled-on-disk +
    ``--refill-zones``); this module VERIFIES the plane covers the escape
    region and that no ethernet ISO void perforates it.

WHAT THIS DOES NOT CLAIM: the SoM pinout is FIXED, so the contact-level
return-path gate (schgen/verify/return_path_gate.py, K=2) stays RED by module
design.  The deliverable is *carrier escape-fanout return stitching*, judged
by schgen/verify/return_stitch_gate.py (contact -> nearest stitch via <= 2.0
mm).  Nothing here softens, waives or reinterprets v1 (LAW 4).

STALE-SCALAR LAW: every coordinate here is derived from the live model —
the v1 failing set, the placed DP pad geometry (CW transform, identical to
placement_contract_gate._pad_boxes) and the measured F.Cu/B.Cu obstacle set.
Nothing is hard-coded to today's board.

P0 TOOLCHAIN PROBE (kicad-cli 10.0.2, 2026-07-02, scratchpad):
  * ``(locked yes)`` on segment/via parses clean (DRC rc=0, no stderr);
  * a segment on In1.Cu (power-TYPE layer) parses, DRCs and SVG-renders;
  * an UNFILLED zone adds zero violations; ``--refill-zones`` fills in
    kicad-cli MEMORY (a dangling In1 segment becomes connected, -1
    track_dangling) and the input file hash is UNCHANGED both ways;
  * the effective clearance authority is the PROJECT NETCLASS table
    (Default 0.15 / POWER 0.2) from the adjacent .kicad_pro — the
    manufacturing .kicad_dru is NOT auto-loaded by kicad-cli.

RECONCILED with GAP1 (28f8e15): this module only COMPUTES copper as plain
dicts on ``model.copper`` (kinds: via / segment, board-frame mm,
group="som_escape").  Serialisation: the unified embed._via_node (general,
dict-driven, optional locked — GAP1's thermal vias route through it too) +
embed._segment_node + one append block in emit.emit_pcb.  Zones are GAP1's
(_fill_zone/_gnd_plane_zone/_iso_void_zones) — T2 emits none.

The heavy imports (return_path_gate / si_triage / placement_contract_gate)
are FUNCTION-LEVEL: a module-level verify-import would deadlock the
schgen.generate.pcb package init (emit.py imports placement at module level;
the gates import schgen.generate.pcb symbols).  House pattern: emit.generate().
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

# ---- constants (fixed, basis-carrying, non-configurable — LAW 4) ------------------

#: HARD gate admission radius (mm) — owned by return_stitch_gate (2.0); the
#: generator CONSTRUCTS tighter so the gate never sits on a boundary.
#: Basis: construct tighter than gate; judgment:1.8.
R_CONSTRUCT = 1.8

#: DF40 row half-spacing (mm): pad centers at local v = +/-1.355 (measured from
#: parts/DF40C-100DP-0.4V_51.kicad_mod; re-derived live each build).
#: Used only for the banding reach; coverage uses live pad centers.

#: via ladder, larger first (thermal/inductance preference; judgment).  The
#: 0.3/0.2 rung is FORBIDDEN: its annular width equals the emitted
#: min_via_annular_width 0.05 exactly (zero margin at a boundary equality);
#: 0.35/0.2 keeps 0.075 and satisfies min_via_diameter 0.3.
VIA_LADDER: tuple[tuple[float, float], ...] = ((0.45, 0.3), (0.4, 0.25),
                                               (0.35, 0.2))

#: candidate lattice pitch (mm) along/across the channel. Basis: 1/8 of the
#: 0.4 contact pitch — fine enough to find every corner-distance window the
#: obstacle set leaves open; judgment.
LATTICE_MM = 0.05

#: clearance constructs = emitted DRC minimum + build margin (judgment):
CLR_MARGIN = 0.10            # build margin over the per-netclass rule clearance
#   (annulus -> foreign copper uses the FOREIGN net's netclass rule — 0.15
#   Default / 0.2 POWER — plus this margin; kicad-cli enforces max(netclass)
#   per pair, P0-probe-verified)
CLR_HOLE_FOREIGN = 0.30      # hole edge -> foreign copper (hole rule 0.2 + 0.10)
CLR_HOLE_HOLE = 0.50         # hole edge -> hole edge (min_hole_to_hole 0.25 + 0.25)
# CLR_HOLE_SAMENET_PAD (hole edge -> SAME-NET pad copper, 0.10) now lives in
# constants.py — GAP1 adopted the T2 DFM rule board-wide (a drill in/at a
# solder pad wicks the joint even on the same net); ONE source of truth.
from .constants import CLR_HOLE_SAMENET_PAD  # noqa: E402  (single source)

CLR_TRACK_FOREIGN = 0.15     # ladder segment -> foreign DEFAULT-class copper.
#   Per-box the foreign net's netclass rule replaces it when higher (POWER
#   0.2).  Track margins are measured + reported, not padded: the single-pad
#   stub flank is 0.175 by geometry (0.025 over the rule — thin but measured).
CLR_EDGE = 0.30              # copper -> Edge.Cuts (min_copper_edge_clearance)

#: ladder widths (mm), all >= dru minimum_track 0.2032:
SPINE_W = 0.30
STUB_W_PAIR = 0.30           # pair-gap stub (centered in the 0.2 same-net gap)
STUB_W_SINGLE = 0.25         # single-column / single-pad stub (flank 0.175)

#: ESCAPE REGION = SoM keepout grown by this margin (mm): the rectangle the
#: canonical In1 plane must cover void-free + barrel-free (the return
#: current's landing zone under the DF40 field).  Basis: covers all three
#: channels + escape lines + via slots with >= 0.5 mm to spare.
ZONE_GROW = 2.0

#: minimum stitch vias per remediated connector (a lone via is a single point
#: of failure for that connector's only remediation). Basis: judgment:2.
MIN_VIAS_PER_CONN = 2
#: redundancy-partner offset along the channel for single-via connectors (mm).
REDUNDANCY_OFFSET = 1.0

#: escape-line distance from the connector axis (Tier-2 lane plan): pad outer
#: tip 1.685 + LANE_HANDLE 1.0 router handle. Basis: T2 spec section 4.
LANE_HANDLE = 1.0

_SHEET2REF = {"som_j1": "J1", "som_j2": "J2", "som_j3": "J3"}


class EscapeError(RuntimeError):
    """A stitch via could not be constructed (full candidate audit attached).

    LAW 7: a dropped via is never an outcome — this red build carries the
    audit; the named remedy for an obstacle-closed window is the queued
    bottom-channel-keepout unit (never a threshold relax, never a silent
    nudge of a neighbour)."""


def _canonical_plane(model) -> tuple[tuple, list[tuple]]:
    """(plane_rect, [(void_rect, label), ...]) of the CANONICAL In1 GND plane
    (GAP1 @ 28f8e15: embed._gnd_plane_zone board-interior zone, inset
    GND_PLANE_EDGE_BACK from Edge.Cuts) + the ethernet ISO-void rects punched
    in it (embed._iso_void_zones geometry, derived from the same constants +
    courtyards so the two can never drift)."""
    from .constants import (
        GND_PLANE_EDGE_BACK,
        ISO_VOID_MARGIN,
        ISO_VOID_VALUES,
        ORIGIN_X,
        ORIGIN_Y,
    )
    from .mating_face import _inst_courtyard
    b = GND_PLANE_EDGE_BACK
    plane = (round(ORIGIN_X + b, 3), round(ORIGIN_Y + b, 3),
             round(ORIGIN_X + model.board_w - b, 3),
             round(ORIGIN_Y + model.board_h - b, 3))
    voids: list[tuple] = []
    for inst in model.insts:
        if not inst.value.startswith(ISO_VOID_VALUES):
            continue
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        m = ISO_VOID_MARGIN
        voids.append(((round(cx0 - m, 3), round(cy0 - m, 3),
                       round(cx1 + m, 3), round(cy1 + m, 3)),
                      f"ethernet_isolation_void_{inst.ref}"))
    return plane, voids


# ---- geometry helpers --------------------------------------------------------------

def _frame(inst):
    """(cos, sin) of the inst's CW placement rotation (+y-down page frame)."""
    r = math.radians(inst.rotation or 0.0)
    return math.cos(r), math.sin(r)


def _to_board(inst, u: float, v: float) -> tuple[float, float]:
    """Connector-local (u along the row axis, v across) -> board page mm.
    The CW form (cx = u*c + v*s, cy = -u*s + v*c) — the SAME transform
    placement_contract_gate._pad_boxes uses; never the CCW form."""
    c, s = _frame(inst)
    return (inst.x + u * c + v * s, inst.y - u * s + v * c)


def _to_local(inst, bx: float, by: float) -> tuple[float, float]:
    """Board page mm -> connector-local (u, v); exact inverse of _to_board."""
    c, s = _frame(inst)
    qx, qy = bx - inst.x, by - inst.y
    return (qx * c - qy * s, qx * s + qy * c)


def _box_dist(x: float, y: float, box: tuple[float, float, float, float]) -> float:
    """Euclidean distance from a point to an axis-aligned box (0 inside)."""
    dx = max(box[0] - x, x - box[2], 0.0)
    dy = max(box[1] - y, y - box[3], 0.0)
    return math.hypot(dx, dy)


# ---- ESCAPE / RETURN-STITCH CORRIDOR (placement keepout) --------------------------
#
# The escape router seats its stitch vias + return ladder in a thin band along each
# DF40's pad-row axis (v~0), reaching R_CONSTRUCT past the outermost failing pad in
# u.  A FOREIGN part (esp. a B.Cu passive under the SoM, dragged in by the L4 bottom-
# pull when the board grows and re-packs) that lands in that band displaces a via
# seat -> the seat shifts -> the redundant/stub geometry grazes a DF40 pad (0.300 <
# 0.325) OR the return_stitch gate fails.  This corridor is the region the placer
# must keep FOREIGN parts out of, on BOTH sides, so the escape geometry stays fixed.
# It is a PLACEMENT keepout only — it never touches escape.py's router logic, the
# DF40 mezzanine, or the return copper (LAW 0).
#
# CORRIDOR_V_MARGIN: clearance added past the pad-tip v so the band covers the via
# annulus + ladder stub the router puts at the pad tips.  In u the corridor grows
# by R_CONSTRUCT (the reach past the outermost pad), so a part just off the pad end
# can still displace the reach-limited seat window.
CORRIDOR_V_MARGIN = 0.15


def df40_corridor_local(mod_path) -> tuple[float, float, float, float]:
    """The escape/return-stitch seat corridor for ONE DF40, in its LOCAL (u, v)
    frame: (u0, v0, u1, v1).  Derived LIVE from the connector's own pad centres
    (re-measured each build — it follows the part), so it is exact for any DF40
    pose.  u spans the pad row + R_CONSTRUCT reach; v spans the pad rows + the
    annulus/stub margin.  A pure function of the footprint geometry."""
    from schgen.verify import return_path_gate as rpg
    pads = rpg._parse_pad_positions(mod_path)
    us = [p[0] for p in pads.values()]
    vs = [p[1] for p in pads.values()]
    u_half = max(abs(min(us)), abs(max(us))) + R_CONSTRUCT
    v_half = max(abs(min(vs)), abs(max(vs))) + CORRIDOR_V_MARGIN
    return (-u_half, -v_half, u_half, v_half)


def corridor_board_rect(mod_path, cx: float, cy: float, rot: float
                        ) -> tuple[float, float, float, float]:
    """Axis-aligned board-frame keepout rect (x0, y0, x1, y1) for a DF40 seated
    at centre (``cx``, ``cy``) with placement rotation ``rot`` (CW degrees, the
    KiCad/placer sign).  Transforms the LOCAL corridor's four corners through the
    connector pose and takes their bbox.  Frame-agnostic: (cx, cy) may be page mm
    OR ORIGIN-relative packer coords — the caller supplies matching centres, and
    the returned rect lands in that same frame (used by both the emitted-model
    escape check and the ORIGIN-relative placer passes)."""
    cu0, cv0, cu1, cv1 = df40_corridor_local(mod_path)
    c = math.cos(math.radians(rot or 0.0))
    s = math.sin(math.radians(rot or 0.0))
    # CW transform (matches _to_board): bx = cx + u*c + v*s, by = cy - u*s + v*c
    xs = [cx + u * c + v * s for u in (cu0, cu1) for v in (cv0, cv1)]
    ys = [cy - u * s + v * c for u in (cu0, cu1) for v in (cv0, cv1)]
    return (round(min(xs), 4), round(min(ys), 4),
            round(max(xs), 4), round(max(ys), 4))


def _seg_box_dist(a: tuple[float, float], b: tuple[float, float],
                  box: tuple[float, float, float, float]) -> float:
    """Min distance from segment a-b to a box (axis-aligned segments only —
    every ladder segment is axis-aligned in its connector frame)."""
    (x1, y1), (x2, y2) = a, b
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    # treat the axis-aligned segment as a degenerate box
    dx = max(box[0] - hi_x, lo_x - box[2], 0.0)
    dy = max(box[1] - hi_y, lo_y - box[3], 0.0)
    return math.hypot(dx, dy)


# ---- obstacle model ---------------------------------------------------------------

@dataclass
class _Obstacles:
    """Local-frame obstacle boxes around ONE connector's channel.

    Box tuples are (u0, v0, u1, v1, rule_clearance, label): the box carries
    ITS net's DRC rule clearance (0.2 for POWER-class nets, else the 0.15
    Default — kicad-cli enforces max(netclass) per pair, P0-probe-verified)."""
    f_cu: list[tuple] = field(default_factory=list)
    b_cu: list[tuple] = field(default_factory=list)
    samenet_pads: list[tuple] = field(default_factory=list)
    # the CONNECTOR's own GND pads (annulus may touch; the drill may not)
    holes: list[tuple[float, float, float, str]] = field(default_factory=list)
    # (u, v, radius, label) — existing drills (thru pads + accepted vias)


def _net_rule(model, net: str) -> float:
    """The DRC rule clearance a foreign net's copper demands: POWER-class
    nets carry 0.2 (the .kicad_pro POWER netclass), everything else the 0.15
    Default.  kicad-cli applies max(netclass) per item pair (P0 probe)."""
    return 0.2 if model.netclass_of.get(net) == "POWER" else 0.15


def _collect_obstacles(model, inst, pad_boxes_fn, region: tuple[float, float,
                                                                float, float],
                       ) -> _Obstacles:
    """Pad-accurate obstacle boxes (LOCAL frame) within ``region`` around one
    DF40 connector.  F.Cu = the connector's own non-GND pads (signal + power +
    the no-net mech pads) + every other top-side inst's pads; B.Cu = every
    bottom-side inst's netted pads (ALL nets — foreign parts stay obstacles
    regardless of net, exactly as on the top side); holes = every thru/NPTH
    pad (conservative: the full pad box radius).  Only the CONNECTOR's own GND
    pads are same-net-exempt (annulus may touch; the drill may not —
    CLR_HOLE_SAMENET_PAD).  Pad geometry is the ONE unified convention
    (``pad_boxes_fn`` == the contract gate's boxes == the emitted board — the
    historical bottom-mirror split and its union-of-conventions workaround
    were removed when the conventions were reconciled; DRC on C22025 had
    proven emission unmirrored)."""
    from schgen.core import sexpr
    from schgen.core.sexpr import Sym

    obs = _Obstacles()
    u0, v0, u1, v1 = region

    def _local_box(bx):
        cs = [_to_local(inst, x, y) for x in (bx[0], bx[2])
              for y in (bx[1], bx[3])]
        xs = [p[0] for p in cs]
        ys = [p[1] for p in cs]
        return (min(xs), min(ys), max(xs), max(ys))

    for oi in sorted(model.insts, key=lambda i: i.ref):
        boxes = pad_boxes_fn(oi)
        thru: set[str] = set()
        # thru/NPTH pads of this footprint (their barrels are on every layer)
        try:
            doc = sexpr.loads(oi.mod_path.read_text())
            for node in doc:
                if (isinstance(node, list) and node and node[0] == Sym("pad")
                        and len(node) > 2
                        and node[2] in (Sym("thru_hole"), Sym("np_thru_hole"))):
                    thru.add(str(node[1]))
        except Exception:  # noqa: BLE001 — unreadable mod = no thru info
            pass
        for pad, bb in sorted(boxes.items()):
            net = oi.pad_nets.get(pad, (0, ""))[1]
            label = f"{oi.ref}({oi.sheet}).{pad}"
            rule = _net_rule(model, net)
            lb = _local_box(bb)
            if lb[2] < u0 or lb[0] > u1 or lb[3] < v0 or lb[1] > v1:
                continue
            if oi.ref == inst.ref and net == "GND":
                obs.samenet_pads.append((*lb, rule, label))
            elif oi.side == "top" or oi.ref == inst.ref:
                obs.f_cu.append((*lb, rule, label))
            else:
                # bottom part: every netted pad is foreign B.Cu copper
                # (incl. its GND pads — same conservatism as the top side,
                # where every other part's pad is an obstacle regardless
                # of net; the gate applies the same-net exemption)
                obs.b_cu.append((*lb, rule, label))
            if pad in thru:
                cu, cv = (lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2
                r = max(lb[2] - lb[0], lb[3] - lb[1]) / 2
                obs.holes.append((cu, cv, r, label))
    return obs


# ---- banding: the corrected 1-D covering greedy ------------------------------------

def band_cover(points: list[tuple[float, str]], reach: float,
               ) -> list[list[tuple[float, str]]]:
    """Optimal left-to-right covering of sorted 1-D points with radius
    ``reach`` intervals: a band absorbs every point within ``2*reach`` of its
    FIRST point; the per-band via feasibility window (the intersection of the
    members' reach intervals) is nonempty by construction.  Points are
    (u, pad) sorted by (round(u,4), int(pad)) — the explicit tie-break for
    facing-row pads that share u exactly."""
    pts = sorted(points, key=lambda t: (round(t[0], 4), int(t[1])))
    bands: list[list[tuple[float, str]]] = []
    i = 0
    while i < len(pts):
        u0 = pts[i][0]
        j = i
        while j < len(pts) and pts[j][0] <= u0 + 2 * reach:
            j += 1
        bands.append(pts[i:j])
        i = j
    return bands


# ---- the via seat search -----------------------------------------------------------

@dataclass
class _Member:
    pad: str
    net: str
    u: float
    v: float          # +/-1.355 (live row v)
    klass: str        # si_triage class


def _coverage_ok(u: float, v: float, members: list[_Member],
                 bound: float) -> tuple[bool, float]:
    """Per-row Euclidean coverage of EVERY member, UNROUNDED compares."""
    worst = 0.0
    for m in members:
        d = math.hypot(u - m.u, v - m.v)
        worst = max(worst, d)
        if d > bound:
            return False, worst
    return True, worst


def _via_feasible(u: float, v: float, dia: float, drill: float,
                  obs: _Obstacles, audit: list[str] | None = None) -> bool:
    """ALL feasibility terms for a stitch-via candidate (LOCAL frame)."""
    rv, rh = dia / 2, drill / 2

    def fail(msg: str) -> bool:
        if audit is not None:
            audit.append(msg)
        return False

    for layer, boxes in (("F.Cu", obs.f_cu), ("B.Cu", obs.b_cu)):
        for bx in boxes:
            d = _box_dist(u, v, bx[:4])
            need = rv + bx[4] + CLR_MARGIN     # netclass rule + build margin
            if d < need:
                return fail(f"{layer} {bx[5]} annulus {d:.4f} < {need:.4f}")
            if d < rh + CLR_HOLE_FOREIGN:
                return fail(f"{layer} {bx[5]} hole {d:.4f}")
    for bx in obs.samenet_pads:
        d = _box_dist(u, v, bx[:4])
        if d < rh + CLR_HOLE_SAMENET_PAD:
            return fail(f"same-net {bx[5]} drill {d:.4f} < "
                        f"{rh + CLR_HOLE_SAMENET_PAD:.4f} (via-in-pad DFM)")
    for hu, hv, hr, lbl in obs.holes:
        d = math.hypot(u - hu, v - hv)
        if d < hr + rh + CLR_HOLE_HOLE:
            return fail(f"hole-hole {lbl} {d:.4f}")
    return True


def _seat_band(members: list[_Member], obs: _Obstacles, v_rows: float,
               ledger: list[dict], conn: str, depth: int = 0,
               ) -> list[dict]:
    """Seat stitch via(s) covering ``members``; returns via dicts (LOCAL u/v).

    Candidate enumeration per via size, ordered (|v| asc, |u - window_center|
    asc, + before -): on-axis preferred — v moves toward the clearance-critical
    pad tips, u slides the free channel.  This lexicographic key IS the
    realized optimum (do not describe it as an L1 argmin).

    Escalation ladder (LAW 7 — a dropped via is never an outcome):
      1..3  the full 2D lattice at 0.45/0.3 -> 0.4/0.25 -> 0.35/0.2;
      4     SPLIT the band at its widest internal u-gap (midpoint on tie),
            recurse per sub-band;
      5     SPLIT BY ROW (a band whose two rows cannot share any feasible
            seat — e.g. an obstacle wall over the channel axis), recurse;
      6     EscapeError carrying the full candidate audit — a red build,
            never a squeezed threshold, never a silently perturbed neighbour.
    """
    us = sorted({m.u for m in members})
    u_first, u_last = us[0], us[-1]
    center = (u_first + u_last) / 2
    audit: list[str] = []

    for dia, drill in VIA_LADDER:
        rv = dia / 2
        v_max = 1.025 - rv - 0.15   # pad inner tip - annulus - clearance
        # u window: the intersection of the members' reach intervals at the
        # row-projected reach; enumerate the lattice inside it.
        reach = math.sqrt(max(R_CONSTRUCT ** 2 - v_rows ** 2, 0.0))
        lo = u_last - reach
        hi = u_first + reach
        # the lattice sits on ABSOLUTE multiples of LATTICE_MM in the local
        # frame (pads are 0.4-pitch multiples, so seats land on clean
        # coordinates); coverage still compares unrounded.
        i0 = math.ceil(lo / LATTICE_MM - 1e-9)
        i1 = math.floor(hi / LATTICE_MM + 1e-9)
        u_cands = sorted(
            (round(i * LATTICE_MM, 6) for i in range(i0, i1 + 1)),
            key=lambda x: (abs(x - center), -x))
        v_cands = sorted(
            (round(k * LATTICE_MM, 6)
             for k in range(-int(v_max / LATTICE_MM),
                            int(v_max / LATTICE_MM) + 1)),
            key=lambda x: (abs(x), -x))
        for v in v_cands:
            for u in u_cands:
                ok_cov, worst = _coverage_ok(u, v, members, R_CONSTRUCT)
                if not ok_cov:
                    continue
                if _via_feasible(u, v, dia, drill, obs, audit):
                    ledger.append({
                        "conn": conn, "kind": "seat",
                        "members": [m.pad for m in members],
                        "u": u, "v": v, "dia": dia, "drill": drill,
                        "worst_cover_mm": round(worst, 4), "depth": depth})
                    return [{"u": u, "v": v, "dia": dia, "drill": drill,
                             "members": members, "worst": worst}]

    # escalation 4: split at the widest internal u-gap (midpoint on tie)
    if len(us) > 1:
        gaps = [(us[i + 1] - us[i], i) for i in range(len(us) - 1)]
        gaps.sort(key=lambda g: (-g[0], abs(us[g[1]] - center)))
        cut = (us[gaps[0][1]] + us[gaps[0][1] + 1]) / 2
        ledger.append({"conn": conn, "kind": "split_u", "at": round(cut, 4),
                       "members": [m.pad for m in members], "depth": depth})
        left = [m for m in members if m.u < cut]
        right = [m for m in members if m.u > cut]
        return (_seat_band(left, obs, v_rows, ledger, conn, depth + 1)
                + _seat_band(right, obs, v_rows, ledger, conn, depth + 1))

    # escalation 5: split by row (single-u band, both rows walled apart)
    rows = sorted({m.v for m in members})
    if len(rows) > 1:
        ledger.append({"conn": conn, "kind": "split_row",
                       "members": [m.pad for m in members], "depth": depth})
        out: list[dict] = []
        for rv_ in rows:
            sub = [m for m in members if m.v == rv_]
            out += _seat_band(sub, obs, abs(rv_), ledger, conn, depth + 1)
        return out

    raise EscapeError(
        f"{conn}: no feasible stitch-via seat for contacts "
        f"{[m.pad for m in members]} (nets {[m.net for m in members]}) at "
        f"R_CONSTRUCT={R_CONSTRUCT}; candidate audit (last 40): "
        f"{audit[-40:]} — remedy is the queued bottom-channel-keepout unit "
        f"(move the blocking B.Cu strays in a reviewed byte-diff wave), "
        f"never a threshold relax")


# ---- the Tier-1 builder ------------------------------------------------------------

def build_escape_copper(model) -> tuple[list[dict], dict]:
    """Compute the Tier-1 escape copper for ``model`` (pure function of the
    placed model + module constants).  Returns (copper, escape_meta):
    ``copper`` is a list of plain dicts (kind: via/segment/zone, board-frame
    mm, group="som_escape") ready for embed/emit serialisation."""
    # function-level imports — see module docstring (package-init deadlock)
    from schgen.verify import return_path_gate as rpg
    from schgen.verify import si_triage
    from schgen.verify.placement_contract_gate import _inst_pad_boxes

    gnd_num = model.net_numbers.get("GND")
    if not gnd_num:
        raise EscapeError("net 'GND' absent from the model net table — "
                          "refusing to emit net-0 copper (LAW 0)")

    conns = {}
    for inst in model.insts:
        ref = _SHEET2REF.get(inst.sheet)
        if ref:
            conns[ref] = inst
    if set(conns) != {"J1", "J2", "J3"}:
        raise EscapeError(f"expected the 3 DF40 receptacles (som_j1/2/3), "
                          f"found {sorted(conns)}")

    v1 = rpg.check()
    v1_text = v1.summary()
    failing: dict[str, list] = {}
    for viol in v1.violations:
        failing.setdefault(viol.ref, []).append(viol)

    ledger: list[dict] = []
    copper: list[dict] = []
    vias_by_conn: dict[str, list[dict]] = {}
    coverage: dict[str, dict[str, float]] = {}
    triage_table: dict[str, dict] = {}

    # ---- escape REGION + the canonical In1 plane (GAP1 @ 28f8e15) -----------------
    # RECONCILED: the In1.Cu GND plane is GAP1's board-interior zone
    # (embed._gnd_plane_zone, inset GND_PLANE_EDGE_BACK from Edge.Cuts) — this
    # generator emits NO zone; the stitch vias LAND ON that plane.  What T2
    # still owns is the ESCAPE REGION (SoM keepout + ZONE_GROW): (a) the plane
    # must fully cover it, (b) no ethernet ISO void may intersect it, (c) no
    # foreign thru barrel may perforate it (LOCAL plane continuity under the
    # mated DF40 field — the return current's landing zone).
    if model.som_keepout is None:
        raise EscapeError("model has no SoM keepout — escape region underivable")
    kx0, ky0, kx1, ky1 = model.som_keepout
    zone = (kx0 - ZONE_GROW, ky0 - ZONE_GROW, kx1 + ZONE_GROW, ky1 + ZONE_GROW)
    plane_rect, void_rects = _canonical_plane(model)
    if not (plane_rect[0] <= zone[0] and plane_rect[1] <= zone[1]
            and plane_rect[2] >= zone[2] and plane_rect[3] >= zone[3]):
        raise EscapeError(
            f"the canonical In1 GND plane {plane_rect} does not cover the "
            f"escape region {zone} — the return stitching has no plane to "
            f"land on (GAP1 geometry changed; re-derive deliberately)")
    for vr, label in void_rects:
        if (vr[0] < zone[2] and vr[2] > zone[0]
                and vr[1] < zone[3] and vr[3] > zone[1]):
            raise EscapeError(
                f"In1 plane VOID {label} {vr} intersects the escape region "
                f"{zone} — the return plane under the DF40 field would be "
                f"perforated (a placement wave moved the ethernet media "
                f"parts under the SoM?); fail loud")
    from schgen.core import sexpr
    from schgen.core.sexpr import Sym
    foreign_barrels: list[str] = []
    for oi in sorted(model.insts, key=lambda i: i.ref):
        try:
            doc = sexpr.loads(oi.mod_path.read_text())
        except Exception:  # noqa: BLE001
            continue
        boxes = None
        for node in doc:
            if not (isinstance(node, list) and node and node[0] == Sym("pad")
                    and len(node) > 2
                    and node[2] in (Sym("thru_hole"), Sym("np_thru_hole"))):
                continue
            if boxes is None:
                boxes = _inst_pad_boxes(oi)
            pad = str(node[1])
            net = oi.pad_nets.get(pad, (0, ""))[1]
            if net == "GND":
                continue                      # a GND barrel is plane-friendly
            bb = boxes.get(pad)
            if bb is None:
                continue
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            if zone[0] <= cx <= zone[2] and zone[1] <= cy <= zone[3]:
                foreign_barrels.append(f"{oi.ref}.{pad} ({net or 'no-net'}) "
                                       f"at ({cx:.2f},{cy:.2f})")
    if foreign_barrels:
        raise EscapeError(
            f"foreign thru/NPTH barrel(s) inside the ESCAPE REGION "
            f"{zone}: {foreign_barrels} — the documented future path is an "
            f"octagonal carve-out (r = hole/2 + 0.2 + 0.1); it is NOT "
            f"implemented because the precondition holds on every measured "
            f"build; fail loud instead of silently emitting an unproven fill")

    # ---- per-connector seating (triage-ordered bands) ----------------------------
    # Build every band first, then seat bands GENUINE-first (LAW: any
    # escalation-forced degradation lands on LOW bands).
    band_jobs: list[tuple[int, str, float, list[_Member]]] = []
    obstacles: dict[str, _Obstacles] = {}
    v_rows_by_conn: dict[str, float] = {}
    for ref in sorted(failing):
        inst = conns[ref]
        pads_local = rpg._parse_pad_positions(inst.mod_path)
        members: list[_Member] = []
        for viol in failing[ref]:
            u, v = pads_local[viol.pad]
            kl = si_triage.classify(viol.net)
            members.append(_Member(pad=viol.pad, net=viol.net, u=u, v=v,
                                   klass=kl.klass))
            triage_table[f"{ref}.{viol.pad}"] = {
                "net": viol.net, "function": kl.function, "class": kl.klass,
                "basis": kl.basis}
        v_rows = max(abs(m.v) for m in members)
        v_rows_by_conn[ref] = v_rows
        reach = math.sqrt(max(R_CONSTRUCT ** 2 - v_rows ** 2, 0.0))
        pts = [(m.u, m.pad) for m in members]
        by_pad = {m.pad: m for m in members}
        us = sorted({round(x, 3) for x, _ in pts})
        region = (min(us) - 6.0, -6.0, max(us) + 6.0, 6.0)
        obstacles[ref] = _collect_obstacles(model, inst, _inst_pad_boxes,
                                            region)
        for band in band_cover(pts, reach):
            bm = [by_pad[p] for _, p in band]
            rank = min(si_triage.RANK[m.klass] for m in bm)
            band_jobs.append((rank, ref, band[0][0], bm))

    for _rank, ref, _u_first, bm in sorted(
            band_jobs, key=lambda j: (j[0], j[1], j[2])):
        seats = _seat_band(bm, obstacles[ref], v_rows_by_conn[ref], ledger,
                           ref)
        for s in seats:
            s["conn"] = ref
            vias_by_conn.setdefault(ref, []).append(s)
            # accepted vias join the obstacle set (hole-to-hole is real)
            obstacles[ref].holes.append(
                (s["u"], s["v"], s["drill"] / 2, f"escape-via {ref}"))
        for m in bm:
            best = min(math.hypot(s["u"] - m.u, s["v"] - m.v) for s in seats)
            coverage.setdefault(ref, {})[m.pad] = best

    # redundancy partner for single-via connectors (judgment:2 — SPOF)
    for ref, vias in sorted(vias_by_conn.items()):
        if len(vias) >= MIN_VIAS_PER_CONN:
            continue
        base = vias[0]
        dia, drill = base["dia"], base["drill"]
        seated = False
        for du in (REDUNDANCY_OFFSET, -REDUNDANCY_OFFSET):
            for step in range(0, 21):
                for sgn in (1, -1):
                    u = round(base["u"] + du + sgn * step * LATTICE_MM, 6)
                    if _via_feasible(u, base["v"], dia, drill,
                                     obstacles[ref]):
                        vias.append({"u": u, "v": base["v"], "dia": dia,
                                     "drill": drill, "conn": ref,
                                     "members": [], "worst": 0.0,
                                     "role": "redundant"})
                        obstacles[ref].holes.append(
                            (u, base["v"], drill / 2, f"escape-via {ref}"))
                        ledger.append({"conn": ref, "kind": "redundant_via",
                                       "u": u, "v": base["v"]})
                        seated = True
                        break
                if seated:
                    break
            if seated:
                break
        if not seated:
            raise EscapeError(f"{ref}: no feasible redundancy-partner seat "
                              f"(judgment:2 — a lone stitch via is a SPOF)")

    # ---- ladder copper (F.Cu) -----------------------------------------------------
    ladder_segs: list[dict] = []       # local-frame segments per connector
    for ref, vias in sorted(vias_by_conn.items()):
        inst = conns[ref]
        pads_local = rpg._parse_pad_positions(inst.mod_path)
        gnd_pads = sorted(
            (round(pads_local[p][0], 4), round(pads_local[p][1], 4), p)
            for p, (num, name) in inst.pad_nets.items()
            if num > 0 and name == "GND" and p in pads_local)
        cols: dict[float, set[float]] = {}
        for u, v, _p in gnd_pads:
            cols.setdefault(u, set()).add(v)
        both_rows = sorted(u for u, vs in cols.items() if len(vs) >= 2)
        pair_gaps = [round((a + b) / 2, 4)
                     for a, b in zip(both_rows, both_rows[1:], strict=False)
                     if abs(b - a - 0.4) < 1e-6]
        # attach options: (u, kind, payload)
        attaches: list[tuple[float, str, object]] = []
        used_cols: set[float] = set()
        for g in pair_gaps:
            attaches.append((g, "pair", g))
            used_cols.update({round(g - 0.2, 4), round(g + 0.2, 4)})
        for u in both_rows:
            if u not in used_cols:
                attaches.append((u, "column", u))
        for u, v, p in gnd_pads:
            if u not in both_rows:
                attaches.append((u, "pad", (u, v, p)))
        attaches.sort()
        if not attaches:
            raise EscapeError(f"{ref}: no GND attach options on the connector")

        needed: list[tuple[float, str, object]] = []
        for s in sorted(vias, key=lambda x: x["u"]):
            left = [a for a in attaches if a[0] <= s["u"]]
            right = [a for a in attaches if a[0] >= s["u"]]
            picks = []
            if left:
                picks.append(left[-1])
            if right:
                picks.append(right[0])
            if len(picks) < 2:      # one-sided connector: two nearest overall
                picks = sorted(attaches,
                               key=lambda a: (abs(a[0] - s["u"]), a[0]))[:2]
            for pk in picks:
                if pk not in needed:
                    needed.append(pk)
        needed.sort()

        stub_segs: list[dict] = []
        for u, kind, payload in needed:
            if kind == "pair":
                stub_segs.append({"a": (u, -1.355), "b": (u, 1.355),
                                  "w": STUB_W_PAIR, "role": "stub_pair"})
            elif kind == "column":
                stub_segs.append({"a": (u, -1.355), "b": (u, 1.355),
                                  "w": STUB_W_SINGLE, "role": "stub_column"})
            else:
                pu, pv, _p = payload
                stub_segs.append({"a": (pu, pv), "b": (pu, 0.0),
                                  "w": STUB_W_SINGLE, "role": "stub_pad"})
        # live row v for stub endpoints (derive, don't assume 1.355)
        row_v = max(abs(v) for _u, v, _p in gnd_pads) if gnd_pads else 1.355
        for sseg in stub_segs:
            sseg["a"] = (sseg["a"][0], math.copysign(row_v, sseg["a"][1])
                         if sseg["a"][1] else 0.0)
            sseg["b"] = (sseg["b"][0], math.copysign(row_v, sseg["b"][1])
                         if sseg["b"][1] else 0.0)
        # via stubs for off-axis vias
        for s in vias:
            if abs(s["v"]) > 1e-9:
                stub_segs.append({"a": (s["u"], 0.0), "b": (s["u"], s["v"]),
                                  "w": STUB_W_SINGLE, "role": "stub_via"})
        attach_us = ([a[0] for a in needed] + [s["u"] for s in vias])
        spine = {"a": (min(attach_us), 0.0), "b": (max(attach_us), 0.0),
                 "w": SPINE_W, "role": "spine"}
        segs = [spine] + stub_segs

        # clearance re-check of every ladder segment vs foreign copper (F.Cu)
        for sseg in segs:
            for bx in obstacles[ref].f_cu:
                d = _seg_box_dist(sseg["a"], sseg["b"], bx[:4])
                need = sseg["w"] / 2 + max(CLR_TRACK_FOREIGN, bx[4])
                if d < need:
                    raise EscapeError(
                        f"{ref}: ladder {sseg['role']} {sseg['a']}-{sseg['b']}"
                        f" vs foreign {bx[5]}: {d:.4f} < {need:.4f}")
            sseg["conn"] = ref
        ladder_segs += segs

    # ---- LAW-0 generator self-check (first proof) ---------------------------------
    _self_check(conns, vias_by_conn, ladder_segs, zone, gnd_num)

    # ---- serialise to board-frame copper dicts -------------------------------------
    for ref in sorted(vias_by_conn):
        inst = conns[ref]
        for s in sorted(vias_by_conn[ref], key=lambda x: (x["u"], x["v"])):
            bx, by = _to_board(inst, s["u"], s["v"])
            copper.append({
                "kind": "via", "x": round(bx, 4), "y": round(by, 4),
                "size": s["dia"], "drill": s["drill"], "net": gnd_num,
                "net_name": "GND", "group": "som_escape", "conn": ref,
                "role": s.get("role", "stitch")})
    for sseg in sorted(ladder_segs,
                       key=lambda x: (x["conn"], x["role"], x["a"], x["b"])):
        inst = conns[sseg["conn"]]
        ax, ay = _to_board(inst, *sseg["a"])
        bx, by = _to_board(inst, *sseg["b"])
        copper.append({
            "kind": "segment", "x1": round(ax, 4), "y1": round(ay, 4),
            "x2": round(bx, 4), "y2": round(by, 4), "width": sseg["w"],
            "layer": "F.Cu", "net": gnd_num, "net_name": "GND",
            "group": "som_escape", "conn": sseg["conn"], "role": sseg["role"]})

    # ---- F5 coexistence verdicts (never silent deletion) --------------------------
    coexistence = _coexistence(model, conns, ledger)

    worst_cover = max((d for per in coverage.values() for d in per.values()),
                      default=0.0)
    meta = {
        "version": "escape/v1",
        "constants": {
            "R_CONSTRUCT": R_CONSTRUCT, "VIA_LADDER": list(VIA_LADDER),
            "LATTICE_MM": LATTICE_MM,
            "CLR": {"margin_over_netclass_rule": CLR_MARGIN,
                    "hole_foreign": CLR_HOLE_FOREIGN,
                    "hole_hole": CLR_HOLE_HOLE,
                    "hole_samenet_pad": CLR_HOLE_SAMENET_PAD,
                    "track_foreign": CLR_TRACK_FOREIGN, "edge": CLR_EDGE},
            "widths": {"spine": SPINE_W, "stub_pair": STUB_W_PAIR,
                       "stub_single": STUB_W_SINGLE},
            "zone_grow": ZONE_GROW},
        "v1_verdict": v1_text,
        "v1_scalars": {"n_pairs": v1.n_pairs,
                       "n_pair_contacts": v1.n_pair_contacts,
                       "n_fail": v1.n_fail,
                       "worst_distance": v1.worst_distance},
        "triage": triage_table,
        "coverage_mm": {k: {p: round(d, 4) for p, d in sorted(vs.items())}
                        for k, vs in sorted(coverage.items())},
        "worst_cover_mm": round(worst_cover, 4),
        "vias": {ref: len(v) for ref, v in sorted(vias_by_conn.items())},
        "ledger": ledger,
        "escape_region": tuple(round(c, 4) for c in zone),
        "plane": {"layer": "In1.Cu", "rect": plane_rect,
                  "source": "GAP1 embed._gnd_plane_zone (canonical; T2 emits "
                            "no zone)",
                  "voids_checked": [label for _r, label in void_rects]},
        "coexistence": coexistence,
        "som_interface_sha256": _som_interface_sha256(),
    }
    return copper, meta


def _self_check(conns, vias_by_conn, ladder_segs, zone, gnd_num) -> None:
    """LAW-0 first proof: per remediated connector, {spine + stubs + vias +
    GND pads} form ONE connected component containing ONLY GND-net items;
    every via touches the spine (file-visible F.Cu copper) and lies inside
    the In1 zone rect.  Any breach raises (a red build)."""
    from schgen.verify import return_path_gate as rpg

    for ref in sorted(vias_by_conn):
        inst = conns[ref]
        pads_local = rpg._parse_pad_positions(inst.mod_path)
        gnd_pads = [(round(pads_local[p][0], 4), round(pads_local[p][1], 4), p)
                    for p, (num, name) in inst.pad_nets.items()
                    if num > 0 and name == "GND" and p in pads_local]
        segs = [s for s in ladder_segs if s["conn"] == ref]
        vias = vias_by_conn[ref]
        nodes: list[tuple[str, object]] = (
            [("via", s) for s in vias] + [("seg", s) for s in segs]
            + [("pad", p) for p in gnd_pads])
        parent = list(range(len(nodes)))

        def find(i, parent=parent):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j, parent=parent):
            parent[find(i)] = find(j)

        def touches(a, b) -> bool:
            ka, va = a
            kb, vb = b
            if ka == "seg" and kb == "seg":
                # both axis-aligned: capsule overlap via box distance
                bx = (min(vb["a"][0], vb["b"][0]) - vb["w"] / 2,
                      min(vb["a"][1], vb["b"][1]) - vb["w"] / 2,
                      max(vb["a"][0], vb["b"][0]) + vb["w"] / 2,
                      max(vb["a"][1], vb["b"][1]) + vb["w"] / 2)
                return _seg_box_dist(va["a"], va["b"], bx) <= va["w"] / 2 + 1e-9
            if ka == "seg" and kb == "via":
                return (_seg_box_dist(va["a"], va["b"],
                                      (vb["u"], vb["v"], vb["u"], vb["v"]))
                        <= va["w"] / 2 + vb["dia"] / 2 + 1e-9)
            if ka == "seg" and kb == "pad":
                pu, pv, _ = vb
                # pad copper is 0.2 x 0.66 around its center (measured DP pad)
                box = (pu - 0.1, pv - 0.33, pu + 0.1, pv + 0.33)
                return _seg_box_dist(va["a"], va["b"], box) <= va["w"] / 2 + 1e-9
            if ka == "via" and kb == "pad":
                pu, pv, _ = vb
                box = (pu - 0.1, pv - 0.33, pu + 0.1, pv + 0.33)
                return _box_dist(va["u"], va["v"], box) <= va["dia"] / 2 + 1e-9
            if ka == "via" and kb == "via":
                return (math.hypot(va["u"] - vb["u"], va["v"] - vb["v"])
                        <= (va["dia"] + vb["dia"]) / 2 + 1e-9)
            if ka == "pad" and kb == "pad":
                return False        # pads connect only THROUGH ladder copper
            return touches(b, a)

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if touches(nodes[i], nodes[j]):
                    union(i, j)
        via_roots = {find(i) for i, n in enumerate(nodes) if n[0] == "via"}
        seg_roots = {find(i) for i, n in enumerate(nodes) if n[0] == "seg"}
        if len(via_roots | seg_roots) != 1:
            raise EscapeError(
                f"{ref}: LAW-0 self-check FAILED — ladder+vias form "
                f"{len(via_roots | seg_roots)} components, expected 1")
        # every via inside the zone rect (In1 plane connection)
        inst_zone = zone
        for s in vias:
            bx, by = _to_board(conns[ref], s["u"], s["v"])
            if not (inst_zone[0] + 0.5 <= bx <= inst_zone[2] - 0.5
                    and inst_zone[1] + 0.5 <= by <= inst_zone[3] - 0.5):
                raise EscapeError(f"{ref}: via at ({bx:.2f},{by:.2f}) outside "
                                  f"the escape region {inst_zone} (+0.5 margin)")
        # >= 2 GND-pad stubs per connector
        n_pad_stubs = sum(1 for s in segs
                          if s["role"] in ("stub_pair", "stub_column",
                                           "stub_pad"))
        if n_pad_stubs < 2:
            raise EscapeError(f"{ref}: only {n_pad_stubs} GND-pad stub(s) — "
                              f"rule is >= 2 per remediated connector")


def _coexistence(model, conns, ledger) -> list[dict]:
    """F5 coexistence verdicts for bottom-side parts inside the escape-critical
    region of each DF40 (channel + escape corridors + margin).  RULE:
      * STAY (function)   — the part serves the mezzanine interface here
                            (som_decoupling bypass, hdmi_rx_term termination,
                            power_som rail entry) — ADD-don't-relocate law;
      * CONSTRAINT        — a STAY part whose pads narrowed/closed a via
                            window this build (named in the seat ledger);
      * EVICT             — would appear ONLY if a required contact became
                            unconstructable because of a non-interface stray;
                            consumer: the queued bottom-channel-keepout unit.
    Verdicts are DATA — nothing is deleted or moved here (never silent)."""
    from schgen.verify.placement_contract_gate import _inst_pad_boxes

    interface_sheets = {"som_decoupling", "hdmi_rx_term", "power_som"}
    out: list[dict] = []
    escal_conns = {e["conn"] for e in ledger
                   if e["kind"] in ("split_u", "split_row")}
    for ref, inst in sorted(conns.items()):
        region_v = 1.685 + LANE_HANDLE + 0.5
        for oi in sorted(model.insts, key=lambda i: i.ref):
            if oi.side != "bottom" or oi.ref == inst.ref:
                continue
            boxes = _inst_pad_boxes(oi)
            hit = False
            for bb in boxes.values():
                cs = [_to_local(inst, x, y) for x in (bb[0], bb[2])
                      for y in (bb[1], bb[3])]
                xs = [p[0] for p in cs]
                ys = [p[1] for p in cs]
                if (max(xs) >= -10.765 and min(xs) <= 10.765
                        and max(ys) >= -region_v and min(ys) <= region_v):
                    hit = True
                    break
            if not hit:
                continue
            if oi.sheet in interface_sheets:
                verdict = ("CONSTRAINT" if (oi.sheet == "hdmi_rx_term"
                                            and ref in escal_conns)
                           else "STAY")
                basis = {
                    "som_decoupling": "SoM rail bypass — function requires "
                                      "under-SoM adjacency (ADD-don't-relocate)",
                    "hdmi_rx_term": "TMDS termination must live at the "
                                    "connector; its pads narrow the channel "
                                    "windows (seat ledger names the splits) — "
                                    "evict only if a failing contact becomes "
                                    "unconstructable; consumer: "
                                    "bottom-channel-keepout unit",
                    "power_som": "SoM rail-entry parts; outside all live "
                                 "windows this build (re-derived every build)",
                }[oi.sheet]
            else:
                verdict = "STAY"
                basis = ("foreign L4 stray inside the escape region but "
                         "outside every live via window this build — "
                         "re-derived every build; becomes EVICT (consumer: "
                         "bottom-channel-keepout unit) only on a proven "
                         "window closure")
            out.append({"conn": ref, "ref": oi.ref, "sheet": oi.sheet,
                        "verdict": verdict, "basis": basis})
    return out


def _som_interface_sha256() -> str:
    p = Path(__file__).resolve().parents[3] / "carrier" / "som_interface.json"
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---- Tier-2 lane plan ---------------------------------------------------------------

def build_escape_plan(model) -> dict:
    """The Tier-2 per-contact surface escape-lane PLAN (identity order, both
    rows, all 3 connectors) + perimeter ports + pair records + the T1
    composition-legalizer sidecar constraints.  PLAN ONLY — lane copper lands
    with the routing phase (D13 contract; the ~270 intentionally-dangling
    stubs would couple build health to kicad-cli warning semantics for zero
    measurable gain today)."""
    from schgen.verify import return_path_gate as rpg
    from schgen.verify import si_triage

    conns = {}
    for inst in model.insts:
        ref = _SHEET2REF.get(inst.sheet)
        if ref:
            conns[ref] = inst

    lanes: dict[str, list[dict]] = {}
    netted_counts: dict[str, int] = {}
    corridors: dict[str, dict] = {}
    for ref, inst in sorted(conns.items()):
        pads_local = rpg._parse_pad_positions(inst.mod_path)
        pad_outer_tip = max(abs(v) for _u, v in pads_local.values()) + 0.33
        escape_v = pad_outer_tip + LANE_HANDLE
        rows: dict[int, list] = {}
        n_netted = 0
        for pad, (num, name) in sorted(inst.pad_nets.items(),
                                       key=lambda kv: kv[0]):
            if num <= 0 or pad not in pads_local:
                continue
            n_netted += 1
            u, v = pads_local[pad]
            if abs(v) < 0.5:
                continue                      # mech pads sit on the rows too
            rows.setdefault(1 if v > 0 else -1, []).append((u, pad, name))
        netted_counts[ref] = n_netted
        out: list[dict] = []
        for sgn in sorted(rows):
            entries = sorted(rows[sgn])
            for lane_idx, (u, pad, name) in enumerate(entries):
                klass = rpg.classify_net(name)
                if klass == "GND":
                    direction, port_v = "inward", 0.0
                    width, si = SPINE_W, "GND"
                elif klass == "POWER":
                    # PLANES OWN POWER: the 0.4 POWER class floor cannot fit
                    # the 0.4 pitch as a surface lane — a power contact
                    # escapes VERTICALLY (stub + via into its plane) just
                    # past the pad tip; it never runs to the escape line, so
                    # it is excluded from the surface-lane clearance set.
                    direction = "plane"
                    port_v = math.copysign(pad_outer_tip + 0.5, sgn)
                    width, si = 0.4, "POWER"
                else:
                    direction, port_v = "outward", math.copysign(escape_v, sgn)
                    cls = model.netclass_of.get(name, "Default")
                    geo = model.classes.get(cls)
                    if geo is None and cls.startswith("DP"):
                        # an impedance-controlled DIFF class with no geometry
                        # is a broken width contract (fail loud); single-ended
                        # classes (I2C/SD_1V8/Default) legitimately carry
                        # None -> the JLC default track
                        raise EscapeError(
                            f"{ref}.{pad} net {name}: diff class {cls} "
                            f"has no width geometry (fail loud)")
                    width = geo.width_mm if geo is not None else 0.2032
                    si = si_triage.classify(name).klass
                px, py = _to_board(inst, u, port_v)
                out.append({"pad": pad, "net": name, "lane": lane_idx,
                            "row": sgn, "dir": direction,
                            "port": (round(px, 4), round(py, 4)),
                            "layer": "F.Cu", "width": round(width, 4),
                            "si_class": si, "bus_group": None})
        # contiguous POWER runs group into one bus (VIN's 0.4 class floor
        # cannot fit the 0.4 pitch — planes own power; the bus_group tells the
        # routing phase to escape the run as ONE plane entry, not per-pad)
        for sgn in (-1, 1):
            row_lanes = sorted((ln for ln in out if ln["row"] == sgn
                                and ln["dir"] == "plane"),
                               key=lambda ln: ln["lane"])
            for prev, cur in zip(row_lanes, row_lanes[1:],
                                 strict=False):
                if (cur["net"] == prev["net"]
                        and cur["lane"] - prev["lane"] == 1):
                    grp = prev["bus_group"] or f"{ref}:{prev['net']}:{sgn}"
                    prev["bus_group"] = grp
                    cur["bus_group"] = grp
        lanes[ref] = out
        # T1 sidecar: the escape corridor rectangles (board frame) this block
        # needs kept clear — one per row side, spanning the netted pad columns.
        for sgn in sorted(rows):
            us = [u for u, _p, _n in rows[sgn]]
            c0 = _to_board(conns[ref], min(us) - 0.5,
                           math.copysign(pad_outer_tip, sgn))
            c1 = _to_board(conns[ref], max(us) + 0.5,
                           math.copysign(escape_v + 0.3, sgn))
            corridors[f"{ref}:{'S' if sgn > 0 else 'N'}"] = {
                "rect": tuple(round(c, 4) for c in
                              (min(c0[0], c1[0]), min(c0[1], c1[1]),
                               max(c0[0], c1[0]), max(c0[1], c1[1]))),
                "purpose": "DF40 escape-lane corridor (T2) — composition "
                           "legalizer must keep parts + zones out"}

    # pair records over the v1 pair detection (both halves, same connector)
    pair_recs: list[dict] = []
    genuine_bases: set[str] = set()
    for ref, inst in sorted(conns.items()):
        conn_nets = {name for _n, name in inst.pad_nets.values() if name}
        net2base = rpg.hs_pairs_in(conn_nets)
        lane_of = {ln["net"]: ln for ln in lanes[ref]}
        for base in sorted(set(net2base.values())):
            halves = sorted(n for n, b in net2base.items() if b == base)
            recs = [lane_of[h] for h in halves if h in lane_of]
            if len(recs) != 2:
                continue
            a, b = recs
            klass = max((si_triage.classify(h).klass for h in halves),
                        key=lambda k: -si_triage.RANK[k])
            same_row = a["row"] == b["row"]
            dlane = abs(a["lane"] - b["lane"])
            if same_row and dlane == 1:
                conv = "immediate"
            elif same_row and dlane == 2:
                conv = "quad"
            elif same_row:
                conv = "split"
            else:
                conv = "row_wrap"
            rec = {"base": base, "conn": ref, "halves": halves,
                   "si_class": klass, "same_row": same_row,
                   "delta_lane": dlane, "convergence": conv}
            pair_recs.append(rec)
            if klass == si_triage.GENUINE:
                genuine_bases.add(base)
                # HARD terms for the GENUINE pairs only (basis: measured
                # maximum over the 15 GENUINE pairs = 2)
                if not same_row or dlane > 2:
                    raise EscapeError(
                        f"GENUINE pair {base} on {ref}: same_row={same_row} "
                        f"delta_lane={dlane} violates the hard pair terms "
                        f"(measured max |dlane| over the 15 GENUINE pairs = 2)")

    plan = {
        "schema": "escape/v1",
        "lanes": lanes,
        "netted_counts": netted_counts,
        "pairs": pair_recs,
        "genuine_pairs": sorted(genuine_bases),
        "t1_constraints": {
            "corridors": corridors,
            "consumer": "T1 composition legalizer (D13): treat every corridor "
                        "rect + the som_escape via sites as placement "
                        "constraints",
        },
        "content_key": _content_key(conns),
    }
    return plan


def _content_key(conns) -> str:
    """sha256 over (som_interface.json bytes + DP .kicad_mod bytes + rule
    constants + the three DF40 poses rounded/sorted-by-ref) — a floorplan
    move can never reuse a stale plan."""
    h = hashlib.sha256()
    root = Path(__file__).resolve().parents[3]
    h.update((root / "carrier" / "som_interface.json").read_bytes())
    for ref in sorted(conns):
        h.update(conns[ref].mod_path.read_bytes())
        h.update(f"{ref}:{round(conns[ref].x, 3)}:{round(conns[ref].y, 3)}:"
                 f"{round(conns[ref].rotation or 0.0, 1)}".encode())
    h.update(json.dumps({
        "R_CONSTRUCT": R_CONSTRUCT, "LANE_HANDLE": LANE_HANDLE,
        "VIA_LADDER": list(VIA_LADDER)}, sort_keys=True).encode())
    return h.hexdigest()
