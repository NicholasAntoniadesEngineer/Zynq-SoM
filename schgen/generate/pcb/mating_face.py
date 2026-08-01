from __future__ import annotations

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
from .turn import pad_half_extent, turn_box, turn_point

PAD_DECIMALS = 3
COURTYARD_DECIMALS = 4
DEFAULT_FACE = "+Y"


def connector_edge_rotation(mating_face: str, edge: str) -> float:
    return _ROT_TABLES.get(mating_face, _ROT_FACE_POS_Y).get(edge, 0.0)


def _mating_face_out_dir(mating_face: str, rot: float) -> tuple[int, int]:
    fx, fy = _FACE_VEC.get(mating_face, _FACE_VEC[DEFAULT_FACE])
    ox, oy = turn_point(float(fx), float(fy), rot)
    return (int(round(ox)), int(round(oy)))


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


def _pad_boxes_local(mod_path: Path, rotation: float
                     ) -> list[tuple[str, float, float, float, float]]:
    rot = rotation or 0.0
    out: list[tuple[str, float, float, float, float]] = []
    for ptype, px, py, prot_deg, sw, sh in _pad_rows(mod_path):
        cx, cy = turn_point(px, py, rot)
        hx, hy = pad_half_extent(sw, sh, rot + prot_deg)
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
    rot = inst.rotation or 0.0
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        name = str(node[1]) if len(node) > 1 else ""
        at = sexpr.find(node, "at")
        if not (at and len(at) >= 3):
            continue
        rx, ry = turn_point(float(at[1]), float(at[2]), rot)
        _num, nname = inst.pad_nets.get(name, (0, ""))
        out.append((name, round(inst.x + rx, PAD_DECIMALS),
                    round(inst.y + ry, PAD_DECIMALS), nname))
    return out


def _inst_courtyard(inst: FootprintInst) -> tuple[float, float, float, float]:
    rb = turn_box(_footprint_bbox(inst.mod_path), inst.rotation or 0.0)
    return (round(inst.x + rb[0], COURTYARD_DECIMALS),
            round(inst.y + rb[1], COURTYARD_DECIMALS),
            round(inst.x + rb[2], COURTYARD_DECIMALS),
            round(inst.y + rb[3], COURTYARD_DECIMALS))


def _inst_pad_bbox(inst: FootprintInst) -> tuple[float, float, float, float]:
    pb = _rot_pad_bbox(inst.mod_path, inst.rotation or 0.0)
    if pb is None:
        return _inst_courtyard(inst)
    return (round(inst.x + pb[0], PAD_DECIMALS),
            round(inst.y + pb[1], PAD_DECIMALS),
            round(inst.x + pb[2], PAD_DECIMALS),
            round(inst.y + pb[3], PAD_DECIMALS))


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
