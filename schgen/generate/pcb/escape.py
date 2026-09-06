from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import native as _nat

R_CONSTRUCT = 1.8


# Largest rung first. 0.3/0.2 is FORBIDDEN: annular 0.05 equals the emitted
# min_via_annular_width exactly (boundary equality); 0.35/0.2 keeps 0.075.
VIA_LADDER: tuple[tuple[float, float], ...] = ((0.45, 0.3), (0.4, 0.25),
                                               (0.35, 0.2))

LATTICE_MM = 0.05

CLR_MARGIN = 0.10
CLR_HOLE_FOREIGN = 0.30
from .constants import (  # noqa: E402
    CLR_HOLE_SAMENET_PAD,
    SOM_ZONE_GROW,
    THERMAL_VIA_H2H,
)

CLR_HOLE_HOLE_RELIEF = 0.05
CLR_HOLE_HOLE = round(THERMAL_VIA_H2H + CLR_HOLE_HOLE_RELIEF, 4)

CLR_TRACK_FOREIGN = 0.15
CLR_EDGE = 0.30
CLR_VIA_ROW = 0.15
COEX_MARGIN = 0.50

# EasyEDA exports on a 1e-4 grid: measured DF40 column gaps stray 2e-4 from pitch
PITCH_TOL_MM = 0.001

SPINE_W = 0.30
STUB_W_PAIR = 0.30
STUB_W_SINGLE = 0.25

MIN_VIAS_PER_CONN = 2
REDUNDANCY_OFFSET = 1.0

LANE_HANDLE = 1.0
OBSTACLE_MARGIN = 6.0

_SHEET2REF = {"som_j1": "J1", "som_j2": "J2", "som_j3": "J3"}


class EscapeError(RuntimeError):
    pass


@dataclass(frozen=True)
class _Contacts:
    row_v: float
    half_w: float
    half_h: float
    span_u: float
    pitch: float


def _contact_geometry(mod_path: Path) -> _Contacts:
    from schgen.core import sexpr
    from schgen.core.sexpr import Sym

    pads: list[tuple[float, float, float, float]] = []
    for node in sexpr.loads(mod_path.read_text()):
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        body = {str(s[0]): s[1:] for s in node[3:] if isinstance(s, list) and s}
        at, size = body.get("at"), body.get("size")
        if at is None or size is None:
            raise EscapeError(f"{mod_path.name} pad {node[1]}: no at/size — "
                              f"contact geometry underivable")
        pads.append((float(at[0]), float(at[1]),
                     float(size[0]), float(size[1])))
    if not pads:
        raise EscapeError(f"{mod_path.name}: no pads — contact geometry "
                          f"underivable")
    try:
        row_v, half_w, half_h, span_u, pitch = _nat.module().contact_geometry(
            pads)
    except RuntimeError as exc:
        raise EscapeError(f"{mod_path.name}: {exc}") from exc
    return _Contacts(row_v=float(row_v), half_w=float(half_w),
                     half_h=float(half_h), span_u=float(span_u),
                     pitch=float(pitch))


def _canonical_plane(model) -> tuple[tuple, list[tuple]]:
    from .constants import (
        GND_PLANE_EDGE_BACK,
        ISO_VOID_MARGIN,
        ISO_VOID_VALUES,
        ORIGIN_X,
        ORIGIN_Y,
    )
    from .mating_face import _inst_courtyard
    geom = _nat.module()
    plane = tuple(geom.canonical_plane_rect(
        ORIGIN_X, ORIGIN_Y, model.board_w, model.board_h, GND_PLANE_EDGE_BACK))
    voids: list[tuple] = []
    for inst in model.insts:
        if not inst.value.startswith(ISO_VOID_VALUES):
            continue
        voids.append((tuple(geom.isolation_void_rect(
            _inst_courtyard(inst), ISO_VOID_MARGIN)),
                      f"ethernet_isolation_void_{inst.ref}"))
    return plane, voids


def _frame(inst):
    r = math.radians(inst.rotation or 0.0)
    return math.cos(r), math.sin(r)


def _to_board_py(inst, u: float, v: float) -> tuple[float, float]:
    c, s = _frame(inst)
    return (inst.x + u * c + v * s, inst.y - u * s + v * c)


def _to_board(inst, u: float, v: float) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native uv_to_board required")
    got = tuple(_nat.module().uv_to_board(
        inst.x, inst.y, u, v, inst.rotation or 0.0))
    if _nat.trace():
        ref = _to_board_py(inst, u, v)
        if got != ref:
            raise AssertionError(
                "native uv_to_board DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _to_local_py(inst, bx: float, by: float) -> tuple[float, float]:
    c, s = _frame(inst)
    qx, qy = bx - inst.x, by - inst.y
    return (qx * c - qy * s, qx * s + qy * c)


def _to_local(inst, bx: float, by: float) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native board_to_uv required")
    got = tuple(_nat.module().board_to_uv(
        inst.x, inst.y, bx, by, inst.rotation or 0.0))
    if _nat.trace():
        ref = _to_local_py(inst, bx, by)
        if got != ref:
            raise AssertionError(
                "native board_to_uv DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _box_dist_py(x: float, y: float, box: tuple[float, float, float, float]
                 ) -> float:
    dx = max(box[0] - x, x - box[2], 0.0)
    dy = max(box[1] - y, y - box[3], 0.0)
    return math.hypot(dx, dy)


def _box_dist(x: float, y: float, box: tuple[float, float, float, float]) -> float:
    if not _nat.loaded():
        raise RuntimeError("native point_box_dist required")
    got = _nat.module().point_box_dist(x, y, box)
    if _nat.trace():
        ref = _box_dist_py(x, y, box)
        if got != ref:
            raise AssertionError(
                "native point_box_dist DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def grow_rect_py(box: tuple[float, float, float, float], margin: float
                 ) -> tuple[float, float, float, float]:
    return (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)


def grow_rect(box: tuple[float, float, float, float], margin: float
              ) -> tuple[float, float, float, float]:
    if not _nat.loaded():
        raise RuntimeError("native grow_rect required")
    got = tuple(_nat.module().grow_rect(box, margin))
    if _nat.trace():
        ref = grow_rect_py(box, margin)
        if got != ref:
            raise AssertionError(
                "native grow_rect DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def offset_rect_py(box: tuple[float, float, float, float], dx: float, dy: float
                   ) -> tuple[float, float, float, float]:
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def offset_rect(box: tuple[float, float, float, float], dx: float, dy: float
                ) -> tuple[float, float, float, float]:
    if not _nat.loaded():
        raise RuntimeError("native offset_rect required")
    got = tuple(_nat.module().offset_rect(box, dx, dy))
    if _nat.trace():
        ref = offset_rect_py(box, dx, dy)
        if got != ref:
            raise AssertionError(
                "native offset_rect DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def rect_covers_py(outer: tuple[float, float, float, float],
                   inner: tuple[float, float, float, float]) -> bool:
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def rect_covers(outer: tuple[float, float, float, float],
                inner: tuple[float, float, float, float]) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native rect_covers required")
    got = bool(_nat.module().rect_covers(outer, inner))
    if _nat.trace():
        ref = rect_covers_py(outer, inner)
        if got is not ref:
            raise AssertionError(
                "native rect_covers DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def rects_intersect_open_py(a: tuple[float, float, float, float],
                            b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def rects_intersect_open(a: tuple[float, float, float, float],
                         b: tuple[float, float, float, float]) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native rects_intersect_open required")
    got = bool(_nat.module().rects_intersect_open(a, b))
    if _nat.trace():
        ref = rects_intersect_open_py(a, b)
        if got is not ref:
            raise AssertionError(
                "native rects_intersect_open DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def point_in_rect_py(x: float, y: float,
                     box: tuple[float, float, float, float]) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def point_in_rect(x: float, y: float,
                  box: tuple[float, float, float, float]) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native point_in_rect required")
    got = bool(_nat.module().point_in_rect(x, y, box))
    if _nat.trace():
        ref = point_in_rect_py(x, y, box)
        if got is not ref:
            raise AssertionError(
                "native point_in_rect DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def rect_center_py(box: tuple[float, float, float, float]
                   ) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def rect_center(box: tuple[float, float, float, float]
                ) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native rect_center required")
    got = tuple(_nat.module().rect_center(box))
    if _nat.trace():
        ref = rect_center_py(box)
        if got != ref:
            raise AssertionError(
                "native rect_center DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def coexistence_region_py(span_u: float, row_v: float, half_h: float,
                          lane_handle: float, margin: float
                          ) -> tuple[float, float]:
    return (span_u + margin, row_v + half_h + lane_handle + margin)


def coexistence_region(span_u: float, row_v: float, half_h: float,
                       lane_handle: float, margin: float
                       ) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native coexistence_region required")
    got = tuple(_nat.module().coexistence_region(
        span_u, row_v, half_h, lane_handle, margin))
    if _nat.trace():
        ref = coexistence_region_py(span_u, row_v, half_h, lane_handle, margin)
        if got != ref:
            raise AssertionError(
                "native coexistence_region DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def construct_reach_py(r_construct: float, row_v: float) -> float:
    return math.sqrt(max(r_construct ** 2 - row_v ** 2, 0.0))


def construct_reach(r_construct: float, row_v: float) -> float:
    if not _nat.loaded():
        raise RuntimeError("native construct_reach required")
    got = float(_nat.module().construct_reach(r_construct, row_v))
    if _nat.trace():
        ref = construct_reach_py(r_construct, row_v)
        if got != ref:
            raise AssertionError(
                "native construct_reach DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def obstacle_scan_region_py(us: list[float], margin: float
                            ) -> tuple[float, float, float, float]:
    if not us:
        raise RuntimeError("obstacle_scan_region: us required")
    return (min(us) - margin, -margin, max(us) + margin, margin)


def obstacle_scan_region(us: list[float], margin: float
                         ) -> tuple[float, float, float, float]:
    if not _nat.loaded():
        raise RuntimeError("native obstacle_scan_region required")
    got = tuple(_nat.module().obstacle_scan_region(us, margin))
    if _nat.trace():
        ref = obstacle_scan_region_py(us, margin)
        if got != ref:
            raise AssertionError(
                "native obstacle_scan_region DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def escape_lane_extents_py(row_v: float, half_h: float, lane_handle: float
                           ) -> tuple[float, float]:
    pad_outer_tip = row_v + half_h
    return (pad_outer_tip, pad_outer_tip + lane_handle)


def escape_lane_extents(row_v: float, half_h: float, lane_handle: float
                        ) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native escape_lane_extents required")
    got = tuple(_nat.module().escape_lane_extents(row_v, half_h, lane_handle))
    if _nat.trace():
        ref = escape_lane_extents_py(row_v, half_h, lane_handle)
        if got != ref:
            raise AssertionError(
                "native escape_lane_extents DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def aabb_from_corners_py(x0: float, y0: float, x1: float, y1: float,
                         digits: int) -> tuple[float, float, float, float]:
    return (round(min(x0, x1), digits), round(min(y0, y1), digits),
            round(max(x0, x1), digits), round(max(y0, y1), digits))


def aabb_from_corners(x0: float, y0: float, x1: float, y1: float,
                      digits: int) -> tuple[float, float, float, float]:
    if not _nat.loaded():
        raise RuntimeError("native aabb_from_corners required")
    got = tuple(_nat.module().aabb_from_corners(x0, y0, x1, y1, digits))
    if _nat.trace():
        ref = aabb_from_corners_py(x0, y0, x1, y1, digits)
        if got != ref:
            raise AssertionError(
                "native aabb_from_corners DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def min_hypot_to_points_py(u: float, v: float,
                           pts: list[tuple[float, float]]) -> float:
    if not pts:
        raise RuntimeError("min_hypot_to_points: pts required")
    return min(math.hypot(p[0] - u, p[1] - v) for p in pts)


def min_hypot_to_points(u: float, v: float,
                        pts: list[tuple[float, float]]) -> float:
    if not _nat.loaded():
        raise RuntimeError("native min_hypot_to_points required")
    got = float(_nat.module().min_hypot_to_points(u, v, pts))
    if _nat.trace():
        ref = min_hypot_to_points_py(u, v, pts)
        if got != ref:
            raise AssertionError(
                "native min_hypot_to_points DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def pair_convergence_py(same_row: bool, delta_lane: int) -> str:
    if same_row and delta_lane == 1:
        return "immediate"
    if same_row and delta_lane == 2:
        return "quad"
    if same_row:
        return "split"
    return "row_wrap"


def pair_convergence(same_row: bool, delta_lane: int) -> str:
    if not _nat.loaded():
        raise RuntimeError("native pair_convergence required")
    got = str(_nat.module().pair_convergence(same_row, delta_lane))
    if _nat.trace():
        ref = pair_convergence_py(same_row, delta_lane)
        if got != ref:
            raise AssertionError(
                "native pair_convergence DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def signed_mag_py(magnitude: float, sign: float) -> float:
    return math.copysign(magnitude, sign)


def signed_mag(magnitude: float, sign: float) -> float:
    if not _nat.loaded():
        raise RuntimeError("native signed_mag required")
    got = float(_nat.module().signed_mag(magnitude, sign))
    if _nat.trace():
        ref = signed_mag_py(magnitude, sign)
        if got != ref:
            raise AssertionError(
                "native signed_mag DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


CORRIDOR_V_MARGIN = 0.15
CORRIDOR_LIP = 0.3


def df40_corridor_local_py(pads: dict) -> tuple[float, float, float, float]:
    us = [p[0] for p in pads.values()]
    vs = [p[1] for p in pads.values()]
    u_half = max(abs(min(us)), abs(max(us))) + R_CONSTRUCT
    v_half = max(abs(min(vs)), abs(max(vs))) + CORRIDOR_V_MARGIN
    return (-u_half, -v_half, u_half, v_half)


def df40_corridor_local(mod_path) -> tuple[float, float, float, float]:
    from schgen.verify import return_path_gate as rpg
    pads = rpg._parse_pad_positions(mod_path)
    uv = list(pads.values())
    if not _nat.loaded():
        raise RuntimeError("native corridor_local_from_uv required")
    got = tuple(_nat.module().corridor_local_from_uv(
        uv, R_CONSTRUCT, CORRIDOR_V_MARGIN))
    if _nat.trace():
        ref = df40_corridor_local_py(pads)
        if got != ref:
            raise AssertionError(
                "native corridor_local_from_uv DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def corridor_board_rect_py(local, cx: float, cy: float, rot: float
                           ) -> tuple[float, float, float, float]:
    cu0, cv0, cu1, cv1 = local
    c = math.cos(math.radians(rot or 0.0))
    s = math.sin(math.radians(rot or 0.0))
    xs = [cx + u * c + v * s for u in (cu0, cu1) for v in (cv0, cv1)]
    ys = [cy - u * s + v * c for u in (cu0, cu1) for v in (cv0, cv1)]
    return (round(min(xs), 4), round(min(ys), 4),
            round(max(xs), 4), round(max(ys), 4))


def corridor_board_rect(mod_path, cx: float, cy: float, rot: float
                        ) -> tuple[float, float, float, float]:
    local = df40_corridor_local(mod_path)
    if not _nat.loaded():
        raise RuntimeError("native corridor_board_rect required")
    got = tuple(_nat.module().corridor_board_rect(
        local, cx, cy, rot or 0.0))
    if _nat.trace():
        ref = corridor_board_rect_py(local, cx, cy, rot)
        if got != ref:
            raise AssertionError(
                "native corridor_board_rect DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _seg_box_dist_py(a: tuple[float, float], b: tuple[float, float],
                     box: tuple[float, float, float, float]) -> float:
    (x1, y1), (x2, y2) = a, b
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    dx = max(box[0] - hi_x, lo_x - box[2], 0.0)
    dy = max(box[1] - hi_y, lo_y - box[3], 0.0)
    return math.hypot(dx, dy)


def _seg_box_dist(a: tuple[float, float], b: tuple[float, float],
                  box: tuple[float, float, float, float]) -> float:
    if not _nat.loaded():
        raise RuntimeError("native seg_box_dist required")
    got = _nat.module().seg_box_dist(a[0], a[1], b[0], b[1], box)
    if _nat.trace():
        ref = _seg_box_dist_py(a, b, box)
        if got != ref:
            raise AssertionError(
                "native seg_box_dist DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


@dataclass
class _Obstacles:
    f_cu: list[tuple] = field(default_factory=list)
    b_cu: list[tuple] = field(default_factory=list)
    samenet_pads: list[tuple] = field(default_factory=list)
    holes: list[tuple[float, float, float, str]] = field(default_factory=list)


def _net_rule(model, net: str) -> float:
    if not _nat.loaded():
        raise RuntimeError("native net_clearance_rule required")
    power = model.netclass_of.get(net) == "POWER"
    got = float(_nat.module().net_clearance_rule(power))
    if _nat.trace():
        ref = 0.2 if power else 0.15
        if got != ref:
            raise AssertionError(
                "native net_clearance_rule DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _collect_obstacles(model, inst, pad_boxes_fn, region: tuple[float, float,
                                                                float, float],
                       ) -> _Obstacles:
    from schgen.core import sexpr
    from schgen.core.sexpr import Sym

    obs = _Obstacles()
    u0, v0, u1, v1 = region

    def _local_box(bx):
        return tuple(_nat.module().board_box_to_uv(
            inst.x, inst.y, inst.rotation or 0.0, bx))

    for oi in sorted(model.insts, key=lambda i: i.ref):
        boxes = pad_boxes_fn(oi)
        thru: set[str] = set()
        try:
            doc = sexpr.loads(oi.mod_path.read_text())
            for node in doc:
                if (isinstance(node, list) and node and node[0] == Sym("pad")
                        and len(node) > 2
                        and node[2] in (Sym("thru_hole"), Sym("np_thru_hole"))):
                    thru.add(str(node[1]))
        except Exception:  # noqa: BLE001
            pass
        for pad, bb in sorted(boxes.items()):
            net = oi.pad_nets.get(pad, (0, ""))[1]
            label = f"{oi.ref}({oi.sheet}).{pad}"
            rule = _net_rule(model, net)
            lb = _local_box(bb)
            if not _nat.loaded():
                raise RuntimeError("native obstacle_bucket required")
            bucket = int(_nat.module().obstacle_bucket(
                u0, v0, u1, v1, lb[0], lb[1], lb[2], lb[3],
                oi.ref == inst.ref, net == "GND", oi.side == "top"))
            if _nat.trace():
                if lb[2] < u0 or lb[0] > u1 or lb[3] < v0 or lb[1] > v1:
                    ref = 0
                elif oi.ref == inst.ref and net == "GND":
                    ref = 1
                elif oi.side == "top" or oi.ref == inst.ref:
                    ref = 2
                else:
                    ref = 3
                if bucket != ref:
                    raise AssertionError(
                        "native obstacle_bucket DIVERGENCE: "
                        f"cpp={bucket} python={ref}")
            if bucket == 0:
                continue
            if bucket == 1:
                obs.samenet_pads.append((*lb, rule, label))
            elif bucket == 2:
                obs.f_cu.append((*lb, rule, label))
            else:
                obs.b_cu.append((*lb, rule, label))
            if pad in thru:
                cu, cv, r = _nat.module().obstacle_hole(
                    lb[0], lb[1], lb[2], lb[3])
                if _nat.trace():
                    ref_h = ((lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2,
                             max(lb[2] - lb[0], lb[3] - lb[1]) / 2)
                    if (cu, cv, r) != ref_h:
                        raise AssertionError(
                            "native obstacle_hole DIVERGENCE: "
                            f"cpp={(cu, cv, r)} python={ref_h}")
                obs.holes.append((cu, cv, r, label))
    return obs


def band_cover_py(points: list[tuple[float, str]], reach: float,
                  ) -> list[list[tuple[float, str]]]:
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


def band_cover(points: list[tuple[float, str]], reach: float,
               ) -> list[list[tuple[float, str]]]:
    if not _nat.loaded():
        raise RuntimeError("native band_cover required")
    got = [[(float(u), p) for u, p in band]
           for band in _nat.module().band_cover(points, reach)]
    if _nat.trace():
        ref = band_cover_py(points, reach)
        if got != ref:
            raise AssertionError(
                f"native band_cover DIVERGENCE: cpp={got} python={ref}")
    return got


@dataclass
class _Member:
    pad: str
    net: str
    u: float
    v: float
    klass: str


def _coverage_ok_py(u: float, v: float, members: list[_Member],
                    bound: float) -> tuple[bool, float]:
    worst = 0.0
    for m in members:
        d = math.hypot(u - m.u, v - m.v)
        worst = max(worst, d)
        if d > bound:
            return False, worst
    return True, worst


def escape_ladder_plan_py(gnd_pads: list, vias: list, pitch: float,
                          pitch_tol: float, row_v: float, stub_w_pair: float,
                          stub_w_single: float, spine_w: float) -> list:
    pads = sorted((round(u, 4), round(v, 4), p) for u, v, p in gnd_pads)
    cols: dict[float, set[float]] = {}
    for pad_u, pad_v, _pad in pads:
        cols.setdefault(pad_u, set()).add(pad_v)
    both_rows = sorted(col_u for col_u, vs in cols.items() if len(vs) >= 2)
    attaches: list[tuple] = []
    used_cols: set[float] = set()
    for left_u, right_u in zip(both_rows, both_rows[1:], strict=False):
        if abs(right_u - left_u - pitch) < pitch_tol:
            attaches.append((round((left_u + right_u) / 2, 4), "pair",
                             (left_u, right_u)))
            used_cols.update((left_u, right_u))
    for col_u in both_rows:
        if col_u not in used_cols:
            attaches.append((col_u, "column", col_u))
    for pad_u, pad_v, pad in pads:
        if pad_u not in both_rows:
            attaches.append((pad_u, "pad", (pad_u, pad_v, pad)))
    attaches.sort()
    if not attaches:
        raise EscapeError("no GND attach options on the connector")
    needed: list[tuple] = []
    for via_u, _via_v in sorted(vias, key=lambda row: row[0]):
        left = [row for row in attaches if row[0] <= via_u]
        right = [row for row in attaches if row[0] >= via_u]
        picks = []
        if left:
            picks.append(left[-1])
        if right:
            picks.append(right[0])
        if len(picks) < 2:
            picks = sorted(attaches,
                           key=lambda row: (abs(row[0] - via_u), row[0]))[:2]
        for pick in picks:
            if pick not in needed:
                needed.append(pick)
    needed.sort()
    stub_segs: list[tuple] = []
    for attach_u, kind, payload in needed:
        if kind == "pair":
            stub_segs.append((attach_u, -row_v, attach_u, row_v, stub_w_pair,
                              "stub_pair"))
        elif kind == "column":
            stub_segs.append((attach_u, -row_v, attach_u, row_v,
                              stub_w_single, "stub_column"))
        else:
            pad_u, pad_v, _pad = payload
            stub_segs.append((pad_u, math.copysign(row_v, pad_v), pad_u, 0.0,
                              stub_w_single, "stub_pad"))
    for via_u, via_v in vias:
        if abs(via_v) > 1e-9:
            stub_segs.append((via_u, 0.0, via_u, via_v, stub_w_single,
                              "stub_via"))
    attach_us = [row[0] for row in needed] + [via_u for via_u, _via_v in vias]
    spine = (min(attach_us), 0.0, max(attach_us), 0.0, spine_w, "spine")
    return [spine] + stub_segs


def escape_ladder_plan(gnd_pads: list, vias: list, pitch: float,
                       pitch_tol: float, row_v: float, stub_w_pair: float,
                       stub_w_single: float, spine_w: float) -> list:
    if not _nat.loaded():
        raise RuntimeError("native escape_ladder_plan required")
    try:
        got = [tuple(row) for row in _nat.module().escape_ladder_plan(
            [(float(u), float(v), str(p)) for u, v, p in gnd_pads],
            [(float(u), float(v)) for u, v in vias],
            pitch, pitch_tol, row_v, stub_w_pair, stub_w_single, spine_w)]
    except RuntimeError as exc:
        raise EscapeError(str(exc)) from exc
    if _nat.trace():
        ref = escape_ladder_plan_py(
            gnd_pads, vias, pitch, pitch_tol, row_v, stub_w_pair,
            stub_w_single, spine_w)
        if got != ref:
            raise AssertionError(
                "native escape_ladder_plan DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def escape_ladder_connected_py(vias: list, segs: list, pads: list,
                               half_w: float, half_h: float) -> tuple[int, int]:
    nodes: list[tuple[str, object]] = (
        [("via", via) for via in vias] + [("seg", seg) for seg in segs]
        + [("pad", pad) for pad in pads])
    parent = list(range(len(nodes)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        parent[find(left)] = find(right)

    def pad_box(pad) -> tuple[float, float, float, float]:
        pad_u, pad_v = pad[0], pad[1]
        return (pad_u - half_w, pad_v - half_h, pad_u + half_w, pad_v + half_h)

    def touches(left, right) -> bool:
        left_kind, left_val = left
        right_kind, right_val = right
        if left_kind == "seg" and right_kind == "seg":
            box = (min(right_val["a"][0], right_val["b"][0]) - right_val["w"] / 2,
                   min(right_val["a"][1], right_val["b"][1]) - right_val["w"] / 2,
                   max(right_val["a"][0], right_val["b"][0]) + right_val["w"] / 2,
                   max(right_val["a"][1], right_val["b"][1]) + right_val["w"] / 2)
            return _seg_box_dist(left_val["a"], left_val["b"], box) <= (
                left_val["w"] / 2 + 1e-9)
        if left_kind == "seg" and right_kind == "via":
            return (_seg_box_dist(left_val["a"], left_val["b"],
                                  (right_val["u"], right_val["v"],
                                   right_val["u"], right_val["v"]))
                    <= left_val["w"] / 2 + right_val["dia"] / 2 + 1e-9)
        if left_kind == "seg" and right_kind == "pad":
            return (_seg_box_dist(left_val["a"], left_val["b"], pad_box(right_val))
                    <= left_val["w"] / 2 + 1e-9)
        if left_kind == "via" and right_kind == "pad":
            return (_box_dist(left_val["u"], left_val["v"], pad_box(right_val))
                    <= left_val["dia"] / 2 + 1e-9)
        if left_kind == "via" and right_kind == "via":
            return (math.hypot(left_val["u"] - right_val["u"],
                               left_val["v"] - right_val["v"])
                    <= (left_val["dia"] + right_val["dia"]) / 2 + 1e-9)
        if left_kind == "pad" and right_kind == "pad":
            return False
        return touches(right, left)

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if touches(nodes[i], nodes[j]):
                union(i, j)
    via_roots = {find(i) for i, node in enumerate(nodes) if node[0] == "via"}
    seg_roots = {find(i) for i, node in enumerate(nodes) if node[0] == "seg"}
    pad_stubs = sum(1 for seg in segs
                    if seg["role"] in ("stub_pair", "stub_column", "stub_pad"))
    return len(via_roots | seg_roots), pad_stubs


def escape_ladder_connected(vias: list, segs: list, pads: list,
                            half_w: float, half_h: float) -> tuple[int, int]:
    if not _nat.loaded():
        raise RuntimeError("native escape_ladder_connected required")
    via_rows = [(float(via["u"]), float(via["v"]), float(via["dia"]))
                for via in vias]
    seg_rows = [(float(seg["a"][0]), float(seg["a"][1]), float(seg["b"][0]),
                 float(seg["b"][1]), float(seg["w"]), str(seg["role"]))
                for seg in segs]
    pad_rows = [(float(pad[0]), float(pad[1])) for pad in pads]
    got = tuple(_nat.module().escape_ladder_connected(
        via_rows, seg_rows, pad_rows, half_w, half_h))
    if _nat.trace():
        ref = escape_ladder_connected_py(vias, segs, pads, half_w, half_h)
        if got != ref:
            raise AssertionError(
                "native escape_ladder_connected DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def escape_redundancy_u_py(base_u: float, base_v: float, dia: float,
                           drill: float, obs: _Obstacles,
                           redundancy_offset: float, lattice: float,
                           max_steps: int) -> float | None:
    for offset in (redundancy_offset, -redundancy_offset):
        for step in range(0, max_steps):
            for sign in (1, -1):
                candidate = round(base_u + offset + sign * step * lattice, 6)
                if _via_feasible(candidate, base_v, dia, drill, obs):
                    return candidate
    return None


def escape_redundancy_u(base_u: float, base_v: float, dia: float, drill: float,
                        obs: _Obstacles, redundancy_offset: float,
                        lattice: float, max_steps: int) -> float | None:
    if not _nat.loaded():
        raise RuntimeError("native escape_redundancy_u required")
    got = _nat.module().escape_redundancy_u(
        base_u, base_v, dia, drill, obs.f_cu, obs.b_cu, obs.samenet_pads,
        obs.holes, _via_clear(), redundancy_offset, lattice, max_steps)
    if got is not None:
        got = float(got)
    if _nat.trace():
        ref = escape_redundancy_u_py(
            base_u, base_v, dia, drill, obs, redundancy_offset, lattice,
            max_steps)
        if got != ref:
            raise AssertionError(
                "native escape_redundancy_u DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _coverage_ok(u: float, v: float, members: list[_Member],
                 bound: float) -> tuple[bool, float]:
    if not _nat.loaded():
        raise RuntimeError("native coverage_ok required")
    got = tuple(_nat.module().coverage_ok(
        u, v, [(m.u, m.v) for m in members], bound))
    if _nat.trace():
        ref = _coverage_ok_py(u, v, members, bound)
        if got != ref:
            raise AssertionError(
                "native coverage_ok DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _via_clear() -> tuple[float, float, float, float]:
    return (CLR_MARGIN, CLR_HOLE_FOREIGN, CLR_HOLE_SAMENET_PAD, CLR_HOLE_HOLE)


def _via_feasible(u: float, v: float, dia: float, drill: float,
                  obs: _Obstacles, audit: list[str] | None = None) -> bool:
    ok, msg = _nat.module().via_feasible(
        u, v, dia, drill, obs.f_cu, obs.b_cu, obs.samenet_pads, obs.holes,
        _via_clear(), audit is not None)
    if not ok and audit is not None and msg:
        audit.append(msg)
    return bool(ok)


def _seat_band(members: list[_Member], obs: _Obstacles, contacts: _Contacts,
               ledger: list[dict], conn: str, depth: int = 0,
               ) -> list[dict]:
    by_pad = {m.pad: m for m in members}
    vias, led_rows, audit = _nat.module().seat_band(
        [(m.pad, m.u, m.v) for m in members],
        obs.f_cu, obs.b_cu, obs.samenet_pads, obs.holes,
        contacts.row_v, contacts.half_h, list(VIA_LADDER), _via_clear(),
        CLR_VIA_ROW, R_CONSTRUCT, LATTICE_MM, conn, depth)
    for kind, led_conn, u, v, dia, drill, worst, at, dep, pads in led_rows:
        if kind == "seat":
            ledger.append({
                "conn": led_conn, "kind": "seat", "members": list(pads),
                "u": u, "v": v, "dia": dia, "drill": drill,
                "worst_cover_mm": worst, "depth": int(dep)})
        elif kind == "split_u":
            ledger.append({"conn": led_conn, "kind": "split_u",
                           "at": at, "members": list(pads),
                           "depth": int(dep)})
        elif kind == "split_row":
            ledger.append({"conn": led_conn, "kind": "split_row",
                           "members": list(pads), "depth": int(dep)})
    if not vias:
        raise EscapeError(
            f"{conn}: no feasible stitch-via seat for contacts "
            f"{[m.pad for m in members]} (nets {[m.net for m in members]}) at "
            f"R_CONSTRUCT={R_CONSTRUCT}; candidate audit (last 40): "
            f"{list(audit)[-40:]} — remedy is the queued bottom-channel-keepout "
            f"unit (move the blocking B.Cu strays in a reviewed byte-diff "
            f"wave), never a threshold relax")
    out: list[dict] = []
    for u, v, dia, drill, worst, pads in vias:
        out.append({"u": u, "v": v, "dia": dia, "drill": drill,
                    "members": [by_pad[p] for p in pads if p in by_pad],
                    "worst": worst})
    return out


def build_escape_copper(model) -> tuple[list[dict], dict]:
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

    if model.som_keepout is None:
        raise EscapeError("model has no SoM keepout — escape region underivable")
    zone = grow_rect(tuple(model.som_keepout), SOM_ZONE_GROW)
    plane_rect, void_rects = _canonical_plane(model)
    if not rect_covers(plane_rect, zone):
        raise EscapeError(
            f"the canonical In1 GND plane {plane_rect} does not cover the "
            f"escape region {zone} — the return stitching has no plane to "
            f"land on (GAP1 geometry changed; re-derive deliberately)")
    for vr, label in void_rects:
        if rects_intersect_open(vr, zone):
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
                continue
            bb = boxes.get(pad)
            if bb is None:
                continue
            cx, cy = rect_center(bb)
            if point_in_rect(cx, cy, zone):
                foreign_barrels.append(f"{oi.ref}.{pad} ({net or 'no-net'}) "
                                       f"at ({cx:.2f},{cy:.2f})")
    if foreign_barrels:
        raise EscapeError(
            f"foreign thru/NPTH barrel(s) inside the ESCAPE REGION "
            f"{zone}: {foreign_barrels} — the documented future path is an "
            f"octagonal carve-out (r = hole/2 + 0.2 + 0.1); it is NOT "
            f"implemented because the precondition holds on every measured "
            f"build; fail loud instead of silently emitting an unproven fill")

    band_jobs: list[tuple[int, str, float, list[_Member]]] = []
    obstacles: dict[str, _Obstacles] = {}
    contacts_by_conn: dict[str, _Contacts] = {}
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
        contacts = _contact_geometry(inst.mod_path)
        contacts_by_conn[ref] = contacts
        reach = construct_reach(R_CONSTRUCT, contacts.row_v)
        pts = [(m.u, m.pad) for m in members]
        by_pad = {m.pad: m for m in members}
        us = sorted({round(x, 3) for x, _ in pts})
        region = obstacle_scan_region(us, OBSTACLE_MARGIN)
        obstacles[ref] = _collect_obstacles(model, inst, _inst_pad_boxes,
                                            region)
        for band in band_cover(pts, reach):
            bm = [by_pad[p] for _, p in band]
            rank = min(si_triage.RANK[m.klass] for m in bm)
            band_jobs.append((rank, ref, band[0][0], bm))

    for _rank, ref, _u_first, bm in sorted(
            band_jobs, key=lambda j: (j[0], j[1], j[2])):
        seats = _seat_band(bm, obstacles[ref], contacts_by_conn[ref], ledger,
                           ref)
        for s in seats:
            s["conn"] = ref
            vias_by_conn.setdefault(ref, []).append(s)
            obstacles[ref].holes.append(
                (s["u"], s["v"], s["drill"] / 2, f"escape-via {ref}"))
        for m in bm:
            best = min_hypot_to_points(
                m.u, m.v, [(s["u"], s["v"]) for s in seats])
            coverage.setdefault(ref, {})[m.pad] = best

    for ref, vias in sorted(vias_by_conn.items()):
        if len(vias) >= MIN_VIAS_PER_CONN:
            continue
        base = vias[0]
        dia, drill = base["dia"], base["drill"]
        partner_u = escape_redundancy_u(
            base["u"], base["v"], dia, drill, obstacles[ref],
            REDUNDANCY_OFFSET, LATTICE_MM, 21)
        if partner_u is None:
            raise EscapeError(f"{ref}: no feasible redundancy-partner seat "
                              f"(judgment:2 — a lone stitch via is a SPOF)")
        vias.append({"u": partner_u, "v": base["v"], "dia": dia,
                     "drill": drill, "conn": ref, "members": [], "worst": 0.0,
                     "role": "redundant"})
        obstacles[ref].holes.append(
            (partner_u, base["v"], drill / 2, f"escape-via {ref}"))
        ledger.append({"conn": ref, "kind": "redundant_via",
                       "u": partner_u, "v": base["v"]})

    ladder_segs: list[dict] = []
    for ref, vias in sorted(vias_by_conn.items()):
        inst = conns[ref]
        pads_local = rpg._parse_pad_positions(inst.mod_path)
        contacts = _contact_geometry(inst.mod_path)
        gnd_pads = sorted(
            (round(pads_local[p][0], 4), round(pads_local[p][1], 4), p)
            for p, (num, name) in inst.pad_nets.items()
            if num > 0 and name == "GND" and p in pads_local)
        via_uv = [(s["u"], s["v"]) for s in vias]
        try:
            planned = escape_ladder_plan(
                gnd_pads, via_uv, contacts.pitch, PITCH_TOL_MM,
                contacts.row_v, STUB_W_PAIR, STUB_W_SINGLE, SPINE_W)
        except EscapeError as exc:
            raise EscapeError(f"{ref}: {exc}") from exc
        segs = [{"a": (ax, ay), "b": (bx, by), "w": width, "role": role}
                for ax, ay, bx, by, width, role in planned]

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

    _self_check(conns, vias_by_conn, ladder_segs, zone, gnd_num)

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
            "zone_grow": SOM_ZONE_GROW},
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
    from schgen.verify import return_path_gate as rpg

    for ref in sorted(vias_by_conn):
        inst = conns[ref]
        pads_local = rpg._parse_pad_positions(inst.mod_path)
        contacts = _contact_geometry(inst.mod_path)
        gnd_pads = [(round(pads_local[p][0], 4), round(pads_local[p][1], 4), p)
                    for p, (num, name) in inst.pad_nets.items()
                    if num > 0 and name == "GND" and p in pads_local]
        segs = [s for s in ladder_segs if s["conn"] == ref]
        vias = vias_by_conn[ref]
        pad_uv = [(u, v) for u, v, _p in gnd_pads]
        components, pad_stubs = escape_ladder_connected(
            vias, segs, pad_uv, contacts.half_w, contacts.half_h)
        if components != 1:
            raise EscapeError(
                f"{ref}: LAW-0 self-check FAILED — ladder+vias form "
                f"{components} components, expected 1")
        inst_zone = zone
        for s in vias:
            bx, by = _to_board(conns[ref], s["u"], s["v"])
            if not _nat.loaded():
                raise RuntimeError("native via_in_escape_region required")
            ok = bool(_nat.module().via_in_escape_region(bx, by, inst_zone, 0.5))
            if _nat.trace():
                ref_ok = (inst_zone[0] + 0.5 <= bx <= inst_zone[2] - 0.5
                          and inst_zone[1] + 0.5 <= by <= inst_zone[3] - 0.5)
                if ok is not ref_ok:
                    raise AssertionError(
                        "native via_in_escape_region DIVERGENCE: "
                        f"cpp={ok} python={ref_ok}")
            if not ok:
                raise EscapeError(f"{ref}: via at ({bx:.2f},{by:.2f}) outside "
                                  f"the escape region {inst_zone} (+0.5 margin)")
        if pad_stubs < 2:
            raise EscapeError(f"{ref}: only {pad_stubs} GND-pad stub(s) — "
                              f"rule is >= 2 per remediated connector")


def _coexistence(model, conns, ledger) -> list[dict]:
    from schgen.verify.placement_contract_gate import _inst_pad_boxes

    interface_sheets = {"som_decoupling", "hdmi_rx_term", "power_som"}
    out: list[dict] = []
    escal_conns = {e["conn"] for e in ledger
                   if e["kind"] in ("split_u", "split_row")}
    for ref, inst in sorted(conns.items()):
        contacts = _contact_geometry(inst.mod_path)
        region_u, region_v = coexistence_region(
            contacts.span_u, contacts.row_v, contacts.half_h, LANE_HANDLE,
            COEX_MARGIN)
        for oi in sorted(model.insts, key=lambda i: i.ref):
            if oi.side != "bottom" or oi.ref == inst.ref:
                continue
            boxes = _inst_pad_boxes(oi)
            hit = False
            for bb in boxes.values():
                if not _nat.loaded():
                    raise RuntimeError("native coexistence_box_hit required")
                got = bool(_nat.module().coexistence_box_hit(
                    inst.x, inst.y, inst.rotation or 0.0, bb, region_u,
                    region_v))
                if _nat.trace():
                    cs = [_to_local_py(inst, x, y) for x in (bb[0], bb[2])
                          for y in (bb[1], bb[3])]
                    xs = [p[0] for p in cs]
                    ys = [p[1] for p in cs]
                    ref = (max(xs) >= -region_u and min(xs) <= region_u
                           and max(ys) >= -region_v and min(ys) <= region_v)
                    if got is not ref:
                        raise AssertionError(
                            "native coexistence_box_hit DIVERGENCE: "
                            f"cpp={got} python={ref}")
                if got:
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


def build_escape_plan(model) -> dict:
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
        contacts = _contact_geometry(inst.mod_path)
        pad_outer_tip, escape_v = escape_lane_extents(
            contacts.row_v, contacts.half_h, LANE_HANDLE)
        rows: dict[int, list] = {}
        n_netted = 0
        for pad, (num, name) in sorted(inst.pad_nets.items(),
                                       key=lambda kv: kv[0]):
            if num <= 0 or pad not in pads_local:
                continue
            n_netted += 1
            u, v = pads_local[pad]
            if abs(v) < 0.5:
                continue
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
                    direction = "plane"
                    port_v = signed_mag(pad_outer_tip + 0.5, sgn)
                    width, si = 0.4, "POWER"
                else:
                    direction, port_v = "outward", signed_mag(escape_v, sgn)
                    cls = model.netclass_of.get(name, "Default")
                    geo = model.classes.get(cls)
                    if geo is None and cls.startswith("DP"):
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
        for sgn in sorted(rows):
            us = [u for u, _p, _n in rows[sgn]]
            c0 = _to_board(conns[ref], min(us) - 0.5,
                           signed_mag(pad_outer_tip, sgn))
            c1 = _to_board(conns[ref], max(us) + 0.5,
                           signed_mag(escape_v + CORRIDOR_LIP, sgn))
            corridors[f"{ref}:{'S' if sgn > 0 else 'N'}"] = {
                "rect": aabb_from_corners(c0[0], c0[1], c1[0], c1[1], 4),
                "purpose": "DF40 escape-lane corridor (T2) — composition "
                           "legalizer must keep parts + zones out"}

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
            conv = pair_convergence(same_row, dlane)
            rec = {"base": base, "conn": ref, "halves": halves,
                   "si_class": klass, "same_row": same_row,
                   "delta_lane": dlane, "convergence": conv}
            pair_recs.append(rec)
            if klass == si_triage.GENUINE:
                genuine_bases.add(base)
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
