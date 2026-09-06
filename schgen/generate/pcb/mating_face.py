from __future__ import annotations

from pathlib import Path

from schgen.core import native as _nat
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


def _mating_face_out_dir_py(mating_face: str, rot: float) -> tuple[int, int]:
    fx, fy = _FACE_VEC.get(mating_face, _FACE_VEC[DEFAULT_FACE])
    ox, oy = turn_point(float(fx), float(fy), rot)
    return (int(round(ox)), int(round(oy)))


def _mating_face_out_dir(mating_face: str, rot: float) -> tuple[int, int]:
    fx, fy = _FACE_VEC.get(mating_face, _FACE_VEC[DEFAULT_FACE])
    if _nat.loaded():
        ox, oy = _nat.module().turn_point(float(fx), float(fy), rot)
        got = (int(round(ox)), int(round(oy)))
        if _nat.trace():
            ref = _mating_face_out_dir_py(mating_face, rot)
            if got != ref:
                raise AssertionError(
                    "native mating_face_out_dir DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _mating_face_out_dir_py(mating_face, rot)


_PAD_ROW_CACHE: dict[str, tuple[tuple[str, float, float, float,
                                      float, float], ...]] = {}


def _pad_rows(mod_path: Path) -> tuple[tuple[str, float, float, float,
                                             float, float], ...]:
    key = str(mod_path)
    cached = _PAD_ROW_CACHE.get(key)
    if cached is not None:
        return cached
    text = mod_path.read_text()
    if _nat.loaded():
        rows = [(_ptype, px, py, prot, sw, sh)
                for _name, _ptype, px, py, prot, sw, sh in
                _nat.module().scan_pad_nodes(text)]
        if _nat.trace():
            ref = _pad_rows_py(text)
            if tuple(rows) != ref:
                raise AssertionError(
                    "native scan_pad_nodes DIVERGENCE: "
                    f"cpp={rows} python={ref} path={mod_path}")
        _PAD_ROW_CACHE[key] = tuple(rows)
        return _PAD_ROW_CACHE[key]
    rows = list(_pad_rows_py(text))
    _PAD_ROW_CACHE[key] = tuple(rows)
    return _PAD_ROW_CACHE[key]


def _pad_rows_py(text: str) -> tuple[tuple[str, float, float, float,
                                           float, float], ...]:
    rows: list[tuple[str, float, float, float, float, float]] = []
    for node in sexpr.loads(text):
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
    return tuple(rows)


def _pad_boxes_local_py(mod_path: Path, rotation: float
                        ) -> list[tuple[str, float, float, float, float]]:
    rot = rotation or 0.0
    out: list[tuple[str, float, float, float, float]] = []
    for ptype, px, py, prot_deg, sw, sh in _pad_rows(mod_path):
        cx, cy = turn_point(px, py, rot)
        hx, hy = pad_half_extent(sw, sh, rot + prot_deg)
        out.append((ptype, cx - hx, cy - hy, cx + hx, cy + hy))
    return out


def _pad_boxes_local(mod_path: Path, rotation: float
                     ) -> list[tuple[str, float, float, float, float]]:
    rot = rotation or 0.0
    if _nat.loaded():
        rows = list(_pad_rows(mod_path))
        got = [tuple(r) for r in _nat.module().pad_boxes_local(rows, rot)]
        if _nat.trace():
            ref = _pad_boxes_local_py(mod_path, rotation)
            if got != ref:
                raise AssertionError(
                    "native pad_boxes_local DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _pad_boxes_local_py(mod_path, rotation)


def thru_pad_boxes(mod_path: Path, rotation: float
                   ) -> list[tuple[float, float, float, float]]:
    return [(x0, y0, x1, y1)
            for ptype, x0, y0, x1, y1 in _pad_boxes_local(mod_path, rotation)
            if ptype in ("thru_hole", "np_thru_hole")]


def _rot_pad_bbox_py(boxes) -> tuple[float, float, float, float] | None:
    if not boxes:
        return None
    return (min(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), max(b[4] for b in boxes))


def _rot_pad_bbox(mod_path: Path,
                  rotation: float) -> tuple[float, float, float, float] | None:
    boxes = _pad_boxes_local(mod_path, rotation)
    if _nat.loaded():
        hit = _nat.module().pad_union_hull(boxes)
        got = None if hit is None else tuple(hit)
        if _nat.trace():
            ref = _rot_pad_bbox_py(boxes)
            if got != ref:
                raise AssertionError(
                    "native pad_union_hull DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _rot_pad_bbox_py(boxes)


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


def _inst_courtyard_py(inst: FootprintInst) -> tuple[float, float, float, float]:
    rb = turn_box(_footprint_bbox(inst.mod_path), inst.rotation or 0.0)
    return (round(inst.x + rb[0], COURTYARD_DECIMALS),
            round(inst.y + rb[1], COURTYARD_DECIMALS),
            round(inst.x + rb[2], COURTYARD_DECIMALS),
            round(inst.y + rb[3], COURTYARD_DECIMALS))


def _inst_courtyard(inst: FootprintInst) -> tuple[float, float, float, float]:
    if _nat.loaded():
        got = tuple(_nat.module().inst_placed_box(
            _footprint_bbox(inst.mod_path), inst.x, inst.y,
            inst.rotation or 0.0, COURTYARD_DECIMALS))
        if _nat.trace():
            ref = _inst_courtyard_py(inst)
            if got != ref:
                raise AssertionError(
                    "native inst_placed_box DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _inst_courtyard_py(inst)


def _inst_pad_bbox(inst: FootprintInst) -> tuple[float, float, float, float]:
    pb = _rot_pad_bbox(inst.mod_path, inst.rotation or 0.0)
    if pb is None:
        return _inst_courtyard(inst)
    if _nat.loaded():
        got = tuple(_nat.module().inst_placed_box(
            pb, inst.x, inst.y, 0.0, PAD_DECIMALS))
        if _nat.trace():
            ref = (round(inst.x + pb[0], PAD_DECIMALS),
                   round(inst.y + pb[1], PAD_DECIMALS),
                   round(inst.x + pb[2], PAD_DECIMALS),
                   round(inst.y + pb[3], PAD_DECIMALS))
            if got != ref:
                raise AssertionError(
                    "native inst_placed_box pad DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
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
