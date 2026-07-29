"""LAW-6 connector ORIENTATION maths (rotation tables -> placement rotation,
mating-face direction, rotated pad/courtyard bboxes) + the placed-geometry
queries the ratsnest renderer / LAW-5 gate use. PURE MOVE out of the old
monolithic ``schgen/generate/pcb.py`` — no behaviour change.
"""

from __future__ import annotations

import math
from pathlib import Path

from schgen.core import sexpr
from schgen.core.sexpr import Sym

from .constants import (
    _FACE_VEC,
    _ROT_FACE_POS_Y,
    _ROT_TABLES,
    FootprintInst,
    PcbModel,
)
from .footprint import _footprint_bbox


def connector_edge_rotation(mating_face: str, edge: str) -> float:
    """Placement rotation (deg) so a connector whose 0-deg mouth points
    ``mating_face`` (-Y/+Y/+X/-X) faces OFF-BOARD on ``edge`` (N/E/S/W)."""
    return _ROT_TABLES.get(mating_face, _ROT_FACE_POS_Y).get(edge, 0.0)


def _mating_face_out_dir(mating_face: str, rot: float) -> tuple[int, int]:
    """The board-frame unit vector the mating mouth points after a placement
    rotation ``rot`` (deg, KiCad CCW about origin, page +y DOWN). Used by the
    gate to confirm the mouth faces off-board, and by the placer to seat the
    connector flush. Returns one of (0,-1)=N, (0,1)=S, (1,0)=E, (-1,0)=W."""
    fx, fy = _FACE_VEC.get(mating_face, (0, 1))
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


def _rot_bbox_cw(bbox: tuple[float, float, float, float],
                 rot: float) -> tuple[float, float, float, float]:
    """The footprint's local bbox after a 0/90/180/270 placement rotation in
    KiCad's TRUE convention (CLOCKWISE on the +y-DOWN page — the same sign
    _rot_pad_bbox uses, verified against kicad-cli DRC). Equals _rot_bbox of the
    NEGATED angle, so it agrees with _rot_bbox for the symmetric edge connectors
    (CW==CCW there) but is correct for an asymmetric rotated part (the LEVER-L1
    fmc 2x40 header) whose CW and CCW boxes genuinely differ."""
    return _rot_bbox(bbox, (360.0 - (int(round(rot)) % 360)) % 360)


def _rot_pad_bbox(mod_path: Path,
                  rotation: float) -> tuple[float, float, float, float] | None:
    """The COPPER (pad) bounding box of a footprint after its placement rotation,
    in the footprint-local frame — includes each pad's real size (and the 90/270
    size swap of a rotated pad). SIDE-INDEPENDENT: emission keeps a bottom
    footprint's local coordinates unchanged (embed._flip_to_bottom) and KiCad
    loads a B.Cu footprint by applying ONLY the rotation (pcbnew-verified on
    C22025 + the 4D03 network) — the historical F->B X-mirror here was the
    bottom-convention split, measured wrong on all 319 bottom parts.
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


# ---- placed-geometry queries (for the ratsnest renderer + LAW-5 gate) ------------

def _inst_pad_geom(inst: FootprintInst) -> list[tuple[str, float, float, str]]:
    """Every pad of a placed footprint as (pad_name, x, y, net_name) in the
    BOARD page frame: at + R_cw(rot)·(px, py), BOTH sides. NO bottom X-mirror —
    the emitted board keeps a B.Cu footprint's local coordinates unchanged and
    KiCad applies only the rotation at load (pcbnew-verified; the old mirror
    here put every bottom airwire endpoint on the WRONG pad, 0.8–3.0 mm off)."""
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
        # rotate about origin in KiCad's TRUE (CLOCKWISE, +y-DOWN page) sign — the
        # SAME matrix _rot_pad_bbox uses (cx = px·cos + py·sin, cy = -px·sin +
        # py·cos). For the symmetric parts this equals the old math-CCW form, but
        # for an asymmetric rotated part (the LEVER-L1 fmc header) the CCW form
        # mirrored the pads ~tens of mm and mis-placed the airwire endpoints.
        rx = px * cs + py * sn
        ry = -px * sn + py * cs
        _num, nname = inst.pad_nets.get(name, (0, ""))
        out.append((name, round(inst.x + rx, 3), round(inst.y + ry, 3), nname))
    return out


def _inst_courtyard(inst: FootprintInst) -> tuple[float, float, float, float]:
    """The placed footprint's courtyard bbox in the BOARD page frame, with the
    placement rotation applied — SAME transform both sides (a B.Cu footprint's
    stored local frame IS the final front-view frame; see _inst_pad_geom). This
    is the box the LAW-5 off-board + grouping gate reasons about. 4dp: the
    measurement quantum (5e-5/corner) sits BELOW the D13 gate's documented
    _TOUCH_EPS (1e-4) — at 3dp the quantum dominated the tolerance 5x."""
    rb = _rot_bbox_cw(_footprint_bbox(inst.mod_path), inst.rotation or 0.0)
    return (round(inst.x + rb[0], 4), round(inst.y + rb[1], 4),
            round(inst.x + rb[2], 4), round(inst.y + rb[3], 4))


def _inst_pad_bbox(inst: FootprintInst) -> tuple[float, float, float, float]:
    """The placed footprint's COPPER (pad) bbox in the board page frame. Unlike
    _inst_courtyard (which includes an off-board mating area — a USB-C shell, an
    SD-card slot, a PMOD module outline — that legitimately overhangs the edge on
    an edge connector), this is the copper that MUST sit on the board. The LAW-5
    off-board check uses THIS so a correctly-seated edge connector (pads on-board,
    mouth overhanging) is not false-flagged, while a genuinely off-board part
    (copper outside Edge.Cuts) still fails."""
    pb = _rot_pad_bbox(inst.mod_path, inst.rotation or 0.0)
    if pb is None:
        return _inst_courtyard(inst)        # pad-less fab-art: fall back
    return (round(inst.x + pb[0], 3), round(inst.y + pb[1], 3),
            round(inst.x + pb[2], 3), round(inst.y + pb[3], 3))


def net_pad_positions(
    model: PcbModel,
) -> dict[str, list[tuple[float, float, str, str]]]:
    """net name -> [(x, y, ref, sheet), ...] pad centers in the board page
    frame, for every REAL net (skips no-net + the unconnected- placeholders).
    Used to draw the unrouted airwires and to budget cross-subsystem nets.
    Pure but ~0.2 s per call: board-flow consumers compute it ONCE
    (emit.generate) and thread it through as ``npp=``."""
    out: dict[str, list[tuple[float, float, str, str]]] = {}
    for inst in model.insts:
        for _pad, x, y, nname in _inst_pad_geom(inst):
            if not nname or nname.startswith("unconnected-"):
                continue
            out.setdefault(nname, []).append((x, y, inst.ref, inst.sheet))
    return out
