from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

R_CONSTRUCT = 1.8


# Largest rung first. 0.3/0.2 is FORBIDDEN: annular 0.05 equals the emitted
# min_via_annular_width exactly (boundary equality); 0.35/0.2 keeps 0.075.
VIA_LADDER: tuple[tuple[float, float], ...] = ((0.45, 0.3), (0.4, 0.25),
                                               (0.35, 0.2))

LATTICE_MM = 0.05

CLR_MARGIN = 0.10
CLR_HOLE_FOREIGN = 0.30
CLR_HOLE_HOLE = 0.50
from .constants import CLR_HOLE_SAMENET_PAD  # noqa: E402

CLR_TRACK_FOREIGN = 0.15
CLR_EDGE = 0.30
CLR_VIA_ROW = 0.15
COEX_MARGIN = 0.50

# EasyEDA exports on a 1e-4 grid: measured DF40 column gaps stray 2e-4 from pitch
PITCH_TOL_MM = 0.001

SPINE_W = 0.30
STUB_W_PAIR = 0.30
STUB_W_SINGLE = 0.25

ZONE_GROW = 2.0

MIN_VIAS_PER_CONN = 2
REDUNDANCY_OFFSET = 1.0

LANE_HANDLE = 1.0

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
    tally = Counter((w, h) for _u, _v, w, h in pads)
    w, h = min(tally, key=lambda s: (-tally[s], s))
    contacts = [(u, v) for u, v, pw, ph in pads if (pw, ph) == (w, h)]
    cols = sorted({round(u, 4) for u, _v in contacts})
    gaps = sorted(b - a for a, b in zip(cols, cols[1:], strict=False))
    if not gaps:
        raise EscapeError(f"{mod_path.name}: {len(cols)} contact column(s) — "
                          f"pitch underivable")
    return _Contacts(row_v=max(abs(v) for _u, v in contacts),
                     half_w=w / 2, half_h=h / 2,
                     span_u=max(abs(u) for u, _v, _w, _h in pads),
                     pitch=gaps[len(gaps) // 2])


def _canonical_plane(model) -> tuple[tuple, list[tuple]]:
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


def _frame(inst):
    r = math.radians(inst.rotation or 0.0)
    return math.cos(r), math.sin(r)


def _to_board(inst, u: float, v: float) -> tuple[float, float]:
    c, s = _frame(inst)
    return (inst.x + u * c + v * s, inst.y - u * s + v * c)


def _to_local(inst, bx: float, by: float) -> tuple[float, float]:
    c, s = _frame(inst)
    qx, qy = bx - inst.x, by - inst.y
    return (qx * c - qy * s, qx * s + qy * c)


def _box_dist(x: float, y: float, box: tuple[float, float, float, float]) -> float:
    dx = max(box[0] - x, x - box[2], 0.0)
    dy = max(box[1] - y, y - box[3], 0.0)
    return math.hypot(dx, dy)


CORRIDOR_V_MARGIN = 0.15


def df40_corridor_local(mod_path) -> tuple[float, float, float, float]:
    from schgen.verify import return_path_gate as rpg
    pads = rpg._parse_pad_positions(mod_path)
    us = [p[0] for p in pads.values()]
    vs = [p[1] for p in pads.values()]
    u_half = max(abs(min(us)), abs(max(us))) + R_CONSTRUCT
    v_half = max(abs(min(vs)), abs(max(vs))) + CORRIDOR_V_MARGIN
    return (-u_half, -v_half, u_half, v_half)


def corridor_board_rect(mod_path, cx: float, cy: float, rot: float
                        ) -> tuple[float, float, float, float]:
    cu0, cv0, cu1, cv1 = df40_corridor_local(mod_path)
    c = math.cos(math.radians(rot or 0.0))
    s = math.sin(math.radians(rot or 0.0))
    xs = [cx + u * c + v * s for u in (cu0, cu1) for v in (cv0, cv1)]
    ys = [cy - u * s + v * c for u in (cu0, cu1) for v in (cv0, cv1)]
    return (round(min(xs), 4), round(min(ys), 4),
            round(max(xs), 4), round(max(ys), 4))


def _seg_box_dist(a: tuple[float, float], b: tuple[float, float],
                  box: tuple[float, float, float, float]) -> float:
    (x1, y1), (x2, y2) = a, b
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    dx = max(box[0] - hi_x, lo_x - box[2], 0.0)
    dy = max(box[1] - hi_y, lo_y - box[3], 0.0)
    return math.hypot(dx, dy)


@dataclass
class _Obstacles:
    f_cu: list[tuple] = field(default_factory=list)
    b_cu: list[tuple] = field(default_factory=list)
    samenet_pads: list[tuple] = field(default_factory=list)
    holes: list[tuple[float, float, float, str]] = field(default_factory=list)


def _net_rule(model, net: str) -> float:
    return 0.2 if model.netclass_of.get(net) == "POWER" else 0.15


def _collect_obstacles(model, inst, pad_boxes_fn, region: tuple[float, float,
                                                                float, float],
                       ) -> _Obstacles:
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
            if lb[2] < u0 or lb[0] > u1 or lb[3] < v0 or lb[1] > v1:
                continue
            if oi.ref == inst.ref and net == "GND":
                obs.samenet_pads.append((*lb, rule, label))
            elif oi.side == "top" or oi.ref == inst.ref:
                obs.f_cu.append((*lb, rule, label))
            else:
                obs.b_cu.append((*lb, rule, label))
            if pad in thru:
                cu, cv = (lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2
                r = max(lb[2] - lb[0], lb[3] - lb[1]) / 2
                obs.holes.append((cu, cv, r, label))
    return obs


def band_cover(points: list[tuple[float, str]], reach: float,
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


@dataclass
class _Member:
    pad: str
    net: str
    u: float
    v: float
    klass: str


def _coverage_ok(u: float, v: float, members: list[_Member],
                 bound: float) -> tuple[bool, float]:
    worst = 0.0
    for m in members:
        d = math.hypot(u - m.u, v - m.v)
        worst = max(worst, d)
        if d > bound:
            return False, worst
    return True, worst


def _via_feasible(u: float, v: float, dia: float, drill: float,
                  obs: _Obstacles, audit: list[str] | None = None) -> bool:
    rv, rh = dia / 2, drill / 2

    def fail(msg: str) -> bool:
        if audit is not None:
            audit.append(msg)
        return False

    for layer, boxes in (("F.Cu", obs.f_cu), ("B.Cu", obs.b_cu)):
        for bx in boxes:
            d = _box_dist(u, v, bx[:4])
            need = rv + bx[4] + CLR_MARGIN
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


def _seat_band(members: list[_Member], obs: _Obstacles, contacts: _Contacts,
               ledger: list[dict], conn: str, depth: int = 0,
               ) -> list[dict]:
    us = sorted({m.u for m in members})
    u_first, u_last = us[0], us[-1]
    center = (u_first + u_last) / 2
    audit: list[str] = []

    for dia, drill in VIA_LADDER:
        rv = dia / 2
        v_max = contacts.row_v - contacts.half_h - rv - CLR_VIA_ROW
        reach = math.sqrt(max(R_CONSTRUCT ** 2 - contacts.row_v ** 2, 0.0))
        lo = u_last - reach
        hi = u_first + reach
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

    if len(us) > 1:
        gaps = [(us[i + 1] - us[i], i) for i in range(len(us) - 1)]
        gaps.sort(key=lambda g: (-g[0], abs(us[g[1]] - center)))
        cut = (us[gaps[0][1]] + us[gaps[0][1] + 1]) / 2
        ledger.append({"conn": conn, "kind": "split_u", "at": round(cut, 4),
                       "members": [m.pad for m in members], "depth": depth})
        left = [m for m in members if m.u < cut]
        right = [m for m in members if m.u > cut]
        return (_seat_band(left, obs, contacts, ledger, conn, depth + 1)
                + _seat_band(right, obs, contacts, ledger, conn, depth + 1))

    rows = sorted({m.v for m in members})
    if len(rows) > 1:
        ledger.append({"conn": conn, "kind": "split_row",
                       "members": [m.pad for m in members], "depth": depth})
        out: list[dict] = []
        for rv_ in rows:
            sub = [m for m in members if m.v == rv_]
            out += _seat_band(sub, obs, contacts, ledger, conn, depth + 1)
        return out

    raise EscapeError(
        f"{conn}: no feasible stitch-via seat for contacts "
        f"{[m.pad for m in members]} (nets {[m.net for m in members]}) at "
        f"R_CONSTRUCT={R_CONSTRUCT}; candidate audit (last 40): "
        f"{audit[-40:]} — remedy is the queued bottom-channel-keepout unit "
        f"(move the blocking B.Cu strays in a reviewed byte-diff wave), "
        f"never a threshold relax")


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
                continue
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
        reach = math.sqrt(max(R_CONSTRUCT ** 2 - contacts.row_v ** 2, 0.0))
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
        seats = _seat_band(bm, obstacles[ref], contacts_by_conn[ref], ledger,
                           ref)
        for s in seats:
            s["conn"] = ref
            vias_by_conn.setdefault(ref, []).append(s)
            obstacles[ref].holes.append(
                (s["u"], s["v"], s["drill"] / 2, f"escape-via {ref}"))
        for m in bm:
            best = min(math.hypot(s["u"] - m.u, s["v"] - m.v) for s in seats)
            coverage.setdefault(ref, {})[m.pad] = best

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

    ladder_segs: list[dict] = []
    for ref, vias in sorted(vias_by_conn.items()):
        inst = conns[ref]
        pads_local = rpg._parse_pad_positions(inst.mod_path)
        contacts = _contact_geometry(inst.mod_path)
        gnd_pads = sorted(
            (round(pads_local[p][0], 4), round(pads_local[p][1], 4), p)
            for p, (num, name) in inst.pad_nets.items()
            if num > 0 and name == "GND" and p in pads_local)
        cols: dict[float, set[float]] = {}
        for u, v, _p in gnd_pads:
            cols.setdefault(u, set()).add(v)
        both_rows = sorted(u for u, vs in cols.items() if len(vs) >= 2)
        adjacent = [(a, b)
                    for a, b in zip(both_rows, both_rows[1:], strict=False)
                    if abs(b - a - contacts.pitch) < PITCH_TOL_MM]
        attaches: list[tuple[float, str, object]] = []
        used_cols: set[float] = set()
        for a, b in adjacent:
            attaches.append((round((a + b) / 2, 4), "pair", (a, b)))
            used_cols.update((a, b))
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
            if len(picks) < 2:
                picks = sorted(attaches,
                               key=lambda a: (abs(a[0] - s["u"]), a[0]))[:2]
            for pk in picks:
                if pk not in needed:
                    needed.append(pk)
        needed.sort()

        stub_segs: list[dict] = []
        for u, kind, payload in needed:
            if kind == "pair":
                stub_segs.append({"a": (u, -contacts.row_v),
                                  "b": (u, contacts.row_v),
                                  "w": STUB_W_PAIR, "role": "stub_pair"})
            elif kind == "column":
                stub_segs.append({"a": (u, -contacts.row_v),
                                  "b": (u, contacts.row_v),
                                  "w": STUB_W_SINGLE, "role": "stub_column"})
            else:
                pu, pv, _p = payload
                stub_segs.append({"a": (pu, math.copysign(contacts.row_v, pv)),
                                  "b": (pu, 0.0),
                                  "w": STUB_W_SINGLE, "role": "stub_pad"})
        for s in vias:
            if abs(s["v"]) > 1e-9:
                stub_segs.append({"a": (s["u"], 0.0), "b": (s["u"], s["v"]),
                                  "w": STUB_W_SINGLE, "role": "stub_via"})
        attach_us = ([a[0] for a in needed] + [s["u"] for s in vias])
        spine = {"a": (min(attach_us), 0.0), "b": (max(attach_us), 0.0),
                 "w": SPINE_W, "role": "spine"}
        segs = [spine] + stub_segs

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

        def pad_box(vb, g=contacts):
            pu, pv, _ = vb
            return (pu - g.half_w, pv - g.half_h, pu + g.half_w, pv + g.half_h)

        def touches(a, b) -> bool:
            ka, va = a
            kb, vb = b
            if ka == "seg" and kb == "seg":
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
                return (_seg_box_dist(va["a"], va["b"], pad_box(vb))
                        <= va["w"] / 2 + 1e-9)
            if ka == "via" and kb == "pad":
                return (_box_dist(va["u"], va["v"], pad_box(vb))
                        <= va["dia"] / 2 + 1e-9)
            if ka == "via" and kb == "via":
                return (math.hypot(va["u"] - vb["u"], va["v"] - vb["v"])
                        <= (va["dia"] + vb["dia"]) / 2 + 1e-9)
            if ka == "pad" and kb == "pad":
                return False
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
        inst_zone = zone
        for s in vias:
            bx, by = _to_board(conns[ref], s["u"], s["v"])
            if not (inst_zone[0] + 0.5 <= bx <= inst_zone[2] - 0.5
                    and inst_zone[1] + 0.5 <= by <= inst_zone[3] - 0.5):
                raise EscapeError(f"{ref}: via at ({bx:.2f},{by:.2f}) outside "
                                  f"the escape region {inst_zone} (+0.5 margin)")
        n_pad_stubs = sum(1 for s in segs
                          if s["role"] in ("stub_pair", "stub_column",
                                           "stub_pad"))
        if n_pad_stubs < 2:
            raise EscapeError(f"{ref}: only {n_pad_stubs} GND-pad stub(s) — "
                              f"rule is >= 2 per remediated connector")


def _coexistence(model, conns, ledger) -> list[dict]:
    from schgen.verify.placement_contract_gate import _inst_pad_boxes

    interface_sheets = {"som_decoupling", "hdmi_rx_term", "power_som"}
    out: list[dict] = []
    escal_conns = {e["conn"] for e in ledger
                   if e["kind"] in ("split_u", "split_row")}
    for ref, inst in sorted(conns.items()):
        contacts = _contact_geometry(inst.mod_path)
        region_u = contacts.span_u + COEX_MARGIN
        region_v = (contacts.row_v + contacts.half_h + LANE_HANDLE
                    + COEX_MARGIN)
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
                if (max(xs) >= -region_u and min(xs) <= region_u
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
        pad_outer_tip = contacts.row_v + contacts.half_h
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
                    port_v = math.copysign(pad_outer_tip + 0.5, sgn)
                    width, si = 0.4, "POWER"
                else:
                    direction, port_v = "outward", math.copysign(escape_v, sgn)
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
                           math.copysign(pad_outer_tip, sgn))
            c1 = _to_board(conns[ref], max(us) + 0.5,
                           math.copysign(escape_v + 0.3, sgn))
            corridors[f"{ref}:{'S' if sgn > 0 else 'N'}"] = {
                "rect": tuple(round(c, 4) for c in
                              (min(c0[0], c1[0]), min(c0[1], c1[1]),
                               max(c0[0], c1[0]), max(c0[1], c1[1]))),
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
