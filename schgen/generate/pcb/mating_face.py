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
    return _ROT_TABLES.get(mating_face, _ROT_FACE_POS_Y).get(edge, 0.0)


def _mating_face_out_dir(mating_face: str, rot: float) -> tuple[int, int]:
    fx, fy = _FACE_VEC.get(mating_face, (0, 1))
    r = int(round(rot)) % 360
    import math as _m
    a = _m.radians(r)
    cs, sn = round(_m.cos(a)), round(_m.sin(a))
    return (fx * cs + fy * sn, -fx * sn + fy * cs)


def _rot_bbox(bbox: tuple[float, float, float, float],
              rot: float) -> tuple[float, float, float, float]:
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
    return _rot_bbox(bbox, (360.0 - (int(round(rot)) % 360)) % 360)


_PAD_ROW_CACHE: dict[str, tuple[tuple[str, float, float, float,
                                      float, float], ...]] = {}


def _pad_rows(mod_path: Path) -> tuple[tuple[str, float, float, float,
                                             float, float], ...]:
    key = str(mod_path)
    cached = _PAD_ROW_CACHE.get(key)
    if cached is not None:
        return cached
    rows: list[tuple[str, float, float, float, float, float]] = []
    for node in sexpr.loads(mod_path.read_text()):
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        at = sexpr.find(node, "at")
        sz = sexpr.find(node, "size")
        if not (at and len(at) >= 3):
            continue
        prot = float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float)) \
            else 0.0
        sw, sh = (float(sz[1]), float(sz[2])) if sz and len(sz) >= 3 \
            else (0.0, 0.0)
        rows.append((str(node[2]) if len(node) > 2 else "",
                     float(at[1]), float(at[2]), prot, sw, sh))
    _PAD_ROW_CACHE[key] = tuple(rows)
    return _PAD_ROW_CACHE[key]


# KiCad rotation is CLOCKWISE on the +y-DOWN page and a B.Cu footprint keeps its
# local pad coords at load — no F->B X-mirror anywhere in this module.
def _pad_boxes_local(mod_path: Path, rotation: float
                     ) -> list[tuple[str, float, float, float, float]]:
    R = math.radians(rotation or 0.0)
    cs, sn = math.cos(R), math.sin(R)
    out: list[tuple[str, float, float, float, float]] = []
    for ptype, px, py, prot_deg, sw, sh in _pad_rows(mod_path):
        prot = math.radians(prot_deg)
        cx = px * cs + py * sn
        cy = -px * sn + py * cs
        tot = R + prot
        ct, st = abs(math.cos(tot)), abs(math.sin(tot))
        hx = ct * sw / 2 + st * sh / 2
        hy = st * sw / 2 + ct * sh / 2
        out.append((ptype, cx - hx, cy - hy, cx + hx, cy + hy))
    return out


def thru_pad_boxes(mod_path: Path, rotation: float
                   ) -> list[tuple[float, float, float, float]]:
    return [(x0, y0, x1, y1)
            for ptype, x0, y0, x1, y1 in _pad_boxes_local(mod_path, rotation)
            if ptype in ("thru_hole", "np_thru_hole")]


def _rot_pad_bbox(mod_path: Path,
                  rotation: float) -> tuple[float, float, float, float] | None:
    boxes = _pad_boxes_local(mod_path, rotation)
    if not boxes:
        return None
    return (min(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), max(b[4] for b in boxes))


def _inst_pad_geom(inst: FootprintInst) -> list[tuple[str, float, float, str]]:
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
        rx = px * cs + py * sn
        ry = -px * sn + py * cs
        _num, nname = inst.pad_nets.get(name, (0, ""))
        out.append((name, round(inst.x + rx, 3), round(inst.y + ry, 3), nname))
    return out


def _inst_courtyard(inst: FootprintInst) -> tuple[float, float, float, float]:
    rb = _rot_bbox_cw(_footprint_bbox(inst.mod_path), inst.rotation or 0.0)
    return (round(inst.x + rb[0], 4), round(inst.y + rb[1], 4),
            round(inst.x + rb[2], 4), round(inst.y + rb[3], 4))


def _inst_pad_bbox(inst: FootprintInst) -> tuple[float, float, float, float]:
    pb = _rot_pad_bbox(inst.mod_path, inst.rotation or 0.0)
    if pb is None:
        return _inst_courtyard(inst)
    return (round(inst.x + pb[0], 3), round(inst.y + pb[1], 3),
            round(inst.x + pb[2], 3), round(inst.y + pb[3], 3))


def net_pad_positions(
    model: PcbModel,
) -> dict[str, list[tuple[float, float, str, str]]]:
    out: dict[str, list[tuple[float, float, str, str]]] = {}
    for inst in model.insts:
        for _pad, x, y, nname in _inst_pad_geom(inst):
            if not nname or nname.startswith("unconnected-"):
                continue
            out.setdefault(nname, []).append((x, y, inst.ref, inst.sheet))
    return out
