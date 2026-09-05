from __future__ import annotations

import re
from pathlib import Path

from schgen.core import fallbacks as _fb
from schgen.core import ledger as _led
from schgen.core import native as _nat
from schgen.core import quantize as _q

from .constants import (
    _INT_DESC,
    _TOP_ALWAYS_LIBS,
    BOARD_EDGE_MARGIN,
    BUTTON_GAP,
    CARRIER,
    CONN_MATING_FACE,
    EDGE_FLUSH_MM,
    EDGE_FLUSH_RELIEF,
    EDGE_PAD_CLEAR,
    EDGE_ZONE_ASPECT,
    FID_INSET,
    FIDUCIAL_FOOTPRINT,
    GND_PLANE_LAYER,
    INTERIOR_SHAPE_ASPECTS,
    INTERIOR_ZONE_ASPECT,
    INTERIOR_ZONE_BAND_TARGET,
    MH_INSET,
    MICROSTRIP_REFERENCE,
    ORIGIN_X,
    ORIGIN_Y,
    PLACE_CLEAR,
    PLACE_CLEAR_BASELINE,
    SOM_CORE_CLEARANCE,
    TEMPLATE_CLEAR,
    THERMAL_VIA_H2H,
    TOP_AREA_MM2,
    ZONE_PACK_FILL,
    ZONE_PAD,
    FootprintInst,
    PcbModel,
    ZoneGeom,
    ZoneShape,
)
from .footprint import (
    _footprint_bbox,
    _net_classes,
    board_netlist,
    board_parts,
    has_thru_pads,
    pad_names,  # noqa: F401
    resolve_mod,
)
from .mating_face import (
    _inst_pad_geom,
    _rot_pad_bbox,
    connector_edge_rotation,
)
from .stages import StageTracker
from .turn import turn_box

_BREATHE_PHASES: tuple[str, ...] = ("A", "B")


def _fanout_meta(refs: list[str], resolvable: dict[str, Path]
                 ) -> dict[str, tuple[float, bool]]:
    from schgen.verify.fanout_gate import (
        MIN_SUBJECT_PINS,
        _is_cluster_passive,
        intelligent_need,
        is_testpoint_ref,
    )
    out: dict[str, tuple[float, bool]] = {}
    for ref in refs:
        mod = resolvable.get(ref)
        if mod is None:
            continue
        pins = len(pad_names(mod))
        is_cp = _is_cluster_passive(ref, pins) or is_testpoint_ref(ref)
        if pins >= MIN_SUBJECT_PINS:
            need = intelligent_need(pins)[0]
        else:
            need = PLACE_CLEAR
        out[ref] = (need, is_cp)
    return out


def _shelf_meta(items: list[tuple[str, tuple, float]],
                fanout: dict[str, tuple[float, bool]] | None
                ) -> tuple[dict[str, tuple[float, float, float, float]],
                           dict[str, float], dict[str, bool]]:
    fanout = fanout or {}
    halo: dict[str, tuple[float, float, float, float]] = {}
    extra_of: dict[str, float] = {}
    iscp_of: dict[str, bool] = {}
    for ref, bbox, rot in items:
        rb = turn_box(bbox, rot)
        halo[ref] = (rb[0] - PLACE_CLEAR / 2, rb[1] - PLACE_CLEAR / 2,
                     rb[2] + PLACE_CLEAR / 2, rb[3] + PLACE_CLEAR / 2)
        need, is_cp = fanout.get(ref, (PLACE_CLEAR, False))
        extra_of[ref] = (max(0.0, _q.quant_credit(need) - PLACE_CLEAR)
                         if need > PLACE_CLEAR else 0.0)
        iscp_of[ref] = is_cp
    return halo, extra_of, iscp_of


def _shelf_blockers(blockers: list | None
                    ) -> list[tuple[float, float, float, float, float, bool]]:
    return [(b[0], b[1], b[2], b[3],
             b[4] if len(b) > 4 else 0.0,
             b[5] if len(b) > 5 else False) for b in (blockers or [])]


def _shelf_pack_py(items: list[tuple[str, tuple, float]], target_w: float,
                   blockers: list[tuple[float, float, float, float]] | None = None,
                   fanout: dict[str, tuple[float, bool]] | None = None
                   ) -> tuple[dict[str, tuple[float, float]], float, float]:
    placed: dict[str, tuple[float, float]] = {}
    occ = _shelf_blockers(blockers)
    halo, extra_of, iscp_of = _shelf_meta(items, fanout)
    order = sorted(items, key=lambda it: (
        -(halo[it[0]][3] - halo[it[0]][1]),
        -(halo[it[0]][2] - halo[it[0]][0]), it[0]))

    def _free(x0, y0, x1, y1, w_lim, extra, is_cp) -> bool:
        if x1 > ZONE_PAD + w_lim + 1e-6:
            return False
        for rx0, ry0, rx1, ry1, r_extra, r_cp in occ:
            g = max(0.0 if is_cp else r_extra, 0.0 if r_cp else extra)
            if not (x1 + g <= rx0 or rx1 + g <= x0
                    or y1 + g <= ry0 or ry1 + g <= y0):
                return False
        return True

    used_w = ZONE_PAD
    used_h = ZONE_PAD
    for ref, _bbox, _rot in order:
        hx0, hy0, hx1, hy1 = halo[ref]
        hw, hh = hx1 - hx0, hy1 - hy0
        extra, is_cp = extra_of[ref], iscp_of[ref]
        w_lim = max(target_w, hw)
        xs = {ZONE_PAD}
        ys = {ZONE_PAD}
        for _rx0, _ry0, rx1, ry1, r_extra, r_cp in occ:
            g = max(0.0 if is_cp else r_extra, 0.0 if r_cp else extra)
            xs.add(rx1 + g)
            ys.add(ry1 + g)
        xcand = sorted(x for x in xs if x + hw <= ZONE_PAD + w_lim + 1e-6)
        slot = None
        for y in sorted(ys):
            for x in xcand:
                if _free(x, y, x + hw, y + hh, w_lim, extra, is_cp):
                    slot = (x, y)
                    break
            if slot is not None:
                break
        sx, sy = slot
        occ.append((sx, sy, sx + hw, sy + hh, extra, is_cp))
        placed[ref] = (round(sx - hx0, 4), round(sy - hy0, 4))
        used_w = max(used_w, sx + hw)
        used_h = max(used_h, sy + hh)
    packed_w = round(max(used_w, ZONE_PAD) + ZONE_PAD, 4)
    packed_h = round(max(used_h, ZONE_PAD) + ZONE_PAD, 4)
    return placed, packed_w, packed_h


def _shelf_pack(items: list[tuple[str, tuple, float]], target_w: float,
                blockers: list[tuple[float, float, float, float]] | None = None,
                fanout: dict[str, tuple[float, bool]] | None = None
                ) -> tuple[dict[str, tuple[float, float]], float, float]:
    if _nat.loaded():
        halo, extra_of, iscp_of = _shelf_meta(items, fanout)
        rows = [(ref, halo[ref][0], halo[ref][1], halo[ref][2], halo[ref][3],
                 extra_of[ref], iscp_of[ref]) for ref, _bbox, _rot in items]
        placed_rows, packed_w, packed_h = _nat.module().shelf_pack(
            rows, target_w, _shelf_blockers(blockers), ZONE_PAD)
        got = ({ref: (ox, oy) for ref, ox, oy in placed_rows},
               packed_w, packed_h)
        if _nat.trace():
            ref = _shelf_pack_py(items, target_w, blockers, fanout)
            if got != ref:
                raise AssertionError(
                    "native shelf_pack DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _shelf_pack_py(items, target_w, blockers, fanout)


def _is_button(mod_path: Path) -> bool:
    return "TS-1187A" in mod_path.stem


def _grid_controls(refs: list[str], bbox_of: dict, resolvable: dict,
                   target_w: float
                   ) -> tuple[dict[str, tuple[float, float]],
                              list[tuple[float, float, float, float]],
                              float, float]:
    cell = 0.0
    bb: dict[str, tuple[float, float, float, float]] = {}
    for r in refs:
        bx0, by0, bx1, by1 = bbox_of[r]
        bb[r] = (bx0, by0, bx1, by1)
        cell = max(cell, (bx1 - bx0) + BUTTON_GAP, (by1 - by0) + BUTTON_GAP)
    cols = max(1, min(len(refs), int((target_w) // cell) or 1))
    off: dict[str, tuple[float, float]] = {}
    occ: list[tuple[float, float, float, float]] = []
    order = sorted(refs)
    for i, r in enumerate(order):
        cx, cy = i % cols, i // cols
        x0 = ZONE_PAD + cx * cell
        y0 = ZONE_PAD + cy * cell
        bx0, by0, bx1, by1 = bb[r]
        fw, fh = (bx1 - bx0) + PLACE_CLEAR, (by1 - by0) + PLACE_CLEAR
        ox = x0 + (cell - fw) / 2 - bx0 + PLACE_CLEAR / 2
        oy = y0 + (cell - fh) / 2 - by0 + PLACE_CLEAR / 2
        off[r] = (round(ox, 4), round(oy, 4))
        occ.append((x0, y0, x0 + cell, y0 + cell))
    rows = (len(refs) + cols - 1) // cols
    return off, occ, ZONE_PAD + cols * cell, ZONE_PAD + rows * cell


def _is_passive_ref(ref: str) -> bool:
    return ref[:1] in ("R", "C", "L") and not ref.startswith(("RJ", "LED"))


def _decoupling_caps(nets: dict[str, list]) -> set[str]:
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
    if not two_side:
        return "top"
    if any(tok in lib for tok in _TOP_ALWAYS_LIBS):
        return "top"
    bx0, by0, bx1, by1 = bbox
    area = (bx1 - bx0) * (by1 - by0)
    if area >= TOP_AREA_MM2:
        return "top"
    if ref in decoupling:
        return "bottom"
    if _is_passive_ref(ref):
        return "bottom"
    return "top"


def _pack_one_zone(sheet_refs: list[str], side_of: dict[str, str],
                   bbox_of: dict, resolvable: dict, aspect: float = 1.0,
                   conn_rot: dict[str, float] | None = None,
                   outer_dir: str | None = None,
                   face_top: frozenset[str] | set[str] | None = None
                   ) -> tuple[dict[str, tuple[float, float]],
                              dict[str, tuple[float, float]],
                              float, float]:
    ft = face_top or frozenset()
    sr = {"top": [], "bottom": []}
    for r in sheet_refs:
        sr["bottom" if r in ft else side_of[r]].append(r)
    conn_rot = conn_rot or {}

    def items(refs, _side):
        return [(r, bbox_of[r], conn_rot.get(r, 0.0)) for r in refs]

    if conn_rot and outer_dir:
        return _pack_connector_zone(sr, items, bbox_of, resolvable,
                                    conn_rot, outer_dir, aspect)

    tot_area = sum((bbox_of[r][2] - bbox_of[r][0] + PLACE_CLEAR) *
                   (bbox_of[r][3] - bbox_of[r][1] + PLACE_CLEAR)
                   for r in sheet_refs)
    target_w = max(8.0, (tot_area * ZONE_PACK_FILL) ** 0.5) * aspect
    fmeta = _fanout_meta(sheet_refs, resolvable)
    top_btns = [r for r in sr["top"] if _is_button(resolvable[r])]
    if len(top_btns) >= 2:
        g_off, g_occ, g_w, g_h = _grid_controls(top_btns, bbox_of, resolvable,
                                                target_w)
        rest_top = [r for r in sr["top"] if r not in set(top_btns)]
        btn_blk = []
        for r in top_btns:
            ox, oy = g_off[r]
            bx0, by0, bx1, by1 = bbox_of[r]
            need, is_cp = fmeta.get(r, (PLACE_CLEAR, False))
            btn_blk.append((ox + bx0 - PLACE_CLEAR / 2,
                            oy + by0 - PLACE_CLEAR / 2,
                            ox + bx1 + PLACE_CLEAR / 2,
                            oy + by1 + PLACE_CLEAR / 2,
                            max(0.0, _q.quant_credit(need) - PLACE_CLEAR),
                            is_cp))
        r_off, rw, rh = _shelf_pack(items(rest_top, "top"), target_w,
                                    list(g_occ) + btn_blk, fanout=fmeta)
        t_off = {**g_off, **r_off}
        tw, th = max(g_w, rw), max(g_h, rh)
    else:
        t_off, tw, th = _shelf_pack(items(sr["top"], "top"), target_w,
                                    fanout=fmeta)
    blockers: list[tuple[float, float, float, float]] = []
    for r in sr["top"]:
        if not has_thru_pads(resolvable[r]):
            continue
        ox, oy = t_off[r]
        bx0, by0, bx1, by1 = bbox_of[r]
        blockers.append((ox + bx0 - PLACE_CLEAR / 2,
                         oy + by0 - PLACE_CLEAR / 2,
                         ox + bx1 + PLACE_CLEAR / 2,
                         oy + by1 + PLACE_CLEAR / 2))
    b_off, bw, bh = _shelf_pack(items(sr["bottom"], "bottom"),
                                target_w, blockers, fanout=fmeta)
    return t_off, b_off, round(max(tw, bw), 4), round(max(th, bh), 4)


def _rotate_zone_90(t_off: dict[str, tuple[float, float]],
                    b_off: dict[str, tuple[float, float]],
                    bbox_of: dict, side_of: dict[str, str],
                    base_rot: dict[str, float],
                    zw: float, zh: float
                    ) -> tuple[dict[str, tuple[float, float]],
                               dict[str, tuple[float, float]],
                               dict[str, float], float, float]:
    extra_rot: dict[str, float] = {}
    new_t: dict[str, tuple[float, float]] = {}
    new_b: dict[str, tuple[float, float]] = {}
    for off_in, off_out in ((t_off, new_t), (b_off, new_b)):
        for ref, (dx, dy) in off_in.items():
            off_out[ref] = (round(dy, 4), round(zw - dx, 4))
            extra_rot[ref] = 90.0
    return new_t, new_b, extra_rot, round(zh, 4), round(zw, 4)


def _member_mirror_shape(sheet: str, t_off: dict[str, tuple[float, float]],
                         b_off: dict[str, tuple[float, float]],
                         zw: float, zh: float, conn_refs: set[str],
                         bbox_of: dict, base_rot: dict[str, float],
                         conn_rot_map: dict[str, float],
                         resolvable: dict[str, Path]
                         ) -> ZoneShape | None:
    members = ([(r, o, 0) for r, o in t_off.items() if r not in conn_refs]
               + [(r, o, 1) for r, o in b_off.items() if r not in conn_refs])
    if not members:
        return None

    def _box(r: str, o: tuple[float, float], rot: float
             ) -> tuple[float, float, float, float]:
        bb = turn_box(bbox_of[r], rot)
        return (o[0] + bb[0], o[1] + bb[1], o[0] + bb[2], o[1] + bb[3])

    mboxes = [_box(r, o, base_rot.get(r, 0.0)) for r, o, _s in members]
    cx = (min(b[0] for b in mboxes) + max(b[2] for b in mboxes)) / 2.0
    cy = (min(b[1] for b in mboxes) + max(b[3] for b in mboxes)) / 2.0
    conn_boxes = []
    for r in sorted(conn_refs):
        o = t_off.get(r) or b_off.get(r)
        if o is not None and r in bbox_of:
            conn_boxes.append(_box(r, o, conn_rot_map.get(r, 0.0)))
    new_t = dict(t_off)
    new_b = dict(b_off)
    extra: dict[str, float] = {r: 0.0 for r in conn_refs}
    eps = 1e-6
    for (r, (ox, oy), side), bb in zip(members, mboxes, strict=True):
        nb = (round(2 * cx - bb[2], 4), round(2 * cy - bb[3], 4),
              round(2 * cx - bb[0], 4), round(2 * cy - bb[1], 4))
        if nb[0] < -eps or nb[1] < -eps or nb[2] > zw + eps or nb[3] > zh + eps:
            return None
        if any(nb[0] - PLACE_CLEAR < c[2] and nb[2] + PLACE_CLEAR > c[0]
               and nb[1] - PLACE_CLEAR < c[3] and nb[3] + PLACE_CLEAR > c[1]
               for c in conn_boxes):
            return None
        (new_b if side else new_t)[r] = (round(2 * cx - ox, 4),
                                         round(2 * cy - oy, 4))
        extra[r] = (base_rot.get(r, 0.0) + 180.0) % 360.0
    if not _mirror_contract_holds(sheet, new_t, new_b, conn_refs, extra,
                                  conn_rot_map, resolvable):
        return None
    return ZoneShape(w=round(zw, 4), h=round(zh, 4), top_off=new_t,
                     bot_off=new_b, extra_rot=extra, tag="mirror")


def _mirror_contract_holds(sheet: str, t_off: dict, b_off: dict,
                           conn_refs: set[str], extra: dict[str, float],
                           conn_rot_map: dict[str, float],
                           resolvable: dict[str, Path],
                           mods: dict[str, Path] | None = None) -> bool:
    from schgen.verify import placement_contract_gate as _pcg
    c = _pcg.discover_contract(sheet)
    if c is None:
        return True
    lib2board = _pcg._board_refs_by_sheet(sheet)
    off = dict(t_off)
    off.update(b_off)

    def _padb(bref: str) -> dict[str, tuple] | None:
        mod = (mods or {}).get(bref) or resolvable.get(bref)
        o = off.get(bref)
        if mod is None or o is None:
            return None
        rot = (conn_rot_map.get(bref, 0.0)
               + extra.get(bref, 0.0)) % 360.0
        return {pn: (b[0] + o[0], b[1] + o[1], b[2] + o[0], b[3] + o[1])
                for pn, b in _pcg._pad_boxes(mod, rot).items()}

    for st in c.get("structures", []):
        if st.get("type") != "proximity":
            continue
        ab = _padb(lib2board.get(st.get("anchor", ""), ""))
        if ab is None:
            continue
        pins = st.get("anchor_pins")
        for mlib in st.get("members", []):
            mb = _padb(lib2board.get(mlib, ""))
            if mb is None:
                continue
            d = (_pcg._pins_to_part(ab, mb, pins) if pins
                 else _pcg._part_to_part(ab, mb))
            if d is None or d > float(st["max_mm"]):
                return False
            for mf in st.get("min_from", []):
                ob = _padb(lib2board.get(mf.get("part", ""), ""))
                if ob is None:
                    continue
                opin = mf.get("pin")
                fd = (_pcg._pins_to_part(ob, mb, [opin]) if opin
                      else _pcg._part_to_part(ob, mb))
                if fd is not None and fd < float(mf.get("min_mm", 0.0)):
                    return False
    return True


_FACE_TOP_PREFIXES = ("TP", "LED", "SW")


def _is_face_top_part(bref: str, lib_id: str, footprint: str) -> bool:
    m = re.match(r"[A-Za-z]+", bref)
    if m and m.group(0) in _FACE_TOP_PREFIXES:
        return True
    return ("TestPoint" in footprint or "TestPoint" in lib_id
            or footprint.startswith("LED_") or lib_id.startswith("Switch:"))


_CONN_CLASS_TOKENS = ("PinHeader", "PinSocket", "Conn", "DF40")


def _unreferenced_imp_sheets(sheets) -> dict[str, set[str]]:
    if MICROSTRIP_REFERENCE["B.Cu"] in (GND_PLANE_LAYER,):
        return {}
    geo, cls_of = _net_classes(sheets)
    out: dict[str, set[str]] = {}
    for sc in sheets:
        for nname in sc.circuit.nets:
            k = cls_of.get(nname)
            if k and geo.get(k) is not None:
                out.setdefault(sc.name, set()).add(k)
    return out


def _mirror_offsets_x(off: dict[str, tuple[float, float]], bbox_of: dict,
                      rot_of: dict[str, float], zw: float
                      ) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for r, (ox, oy) in off.items():
        cb = turn_box(bbox_of[r], rot_of.get(r, 0.0))
        out[r] = (round(zw - ox - cb[0] - cb[2], 4), oy)
    return out


def _mirror_pack(t_off: dict[str, tuple[float, float]],
                 b_off: dict[str, tuple[float, float]], zw: float,
                 rot_of: dict[str, float], bbox_of: dict, resolvable: dict
                 ) -> tuple[dict, dict, dict, dict]:
    from .mirror import mirrored_mod
    mt = {r: (round(zw - ox, 4), oy) for r, (ox, oy) in t_off.items()}
    mods = {r: mirrored_mod(resolvable[r]) for r in sorted(t_off)}
    extra = {r: (180.0 - rot_of.get(r, 0.0)) % 360.0 for r in t_off}
    extra.update({r: rot_of[r] for r in b_off if r in rot_of})
    mb = _mirror_offsets_x(b_off, bbox_of,
                           {r: rot_of.get(r, 0.0) for r in b_off}, zw)
    return mt, mb, extra, mods


def _lift_face_top(t_off: dict[str, tuple[float, float]],
                   b_off: dict[str, tuple[float, float]], zw: float,
                   zh: float, lifted: list[str], bbox_of: dict,
                   resolvable: dict, rot_of: dict[str, float]
                   ) -> tuple[dict[str, tuple[float, float]],
                              dict[str, tuple[float, float]], float, float]:
    keep = {r: o for r, o in t_off.items() if r not in set(lifted)}
    fmeta = _fanout_meta([*keep, *b_off, *lifted], resolvable)

    def _cbox(r: str, off: tuple[float, float]
              ) -> tuple[float, float, float, float]:
        cb = turn_box(bbox_of[r], rot_of.get(r, 0.0))
        return (off[0] + cb[0] - PLACE_CLEAR / 2,
                off[1] + cb[1] - PLACE_CLEAR / 2,
                off[0] + cb[2] + PLACE_CLEAR / 2,
                off[1] + cb[3] + PLACE_CLEAR / 2)

    def _demand(r: str) -> tuple[float, bool]:
        need, is_cp = fmeta.get(r, (PLACE_CLEAR, False))
        return ((max(0.0, _q.quant_credit(need) - PLACE_CLEAR)
                 if need > PLACE_CLEAR else 0.0), is_cp)

    blk: list[tuple] = [_cbox(r, o) for r, o in sorted(keep.items())
                        if has_thru_pads(resolvable[r])]
    blk += [(*_cbox(r, o), *_demand(r)) for r, o in sorted(b_off.items())]
    items = [(r, turn_box(bbox_of[r], rot_of.get(r, 0.0)), 0.0)
             for r in lifted]
    add, _pw, _ph = _shelf_pack(items, max(0.0, zw - 2 * ZONE_PAD), blk,
                                fanout=fmeta)
    sec = {**b_off, **add}
    ext = [_cbox(r, o) for r, o in sorted(sec.items())]
    return (keep, sec,
            round(max(zw, max((b[2] for b in ext), default=0.0) + ZONE_PAD), 4),
            round(max(zh, max((b[3] for b in ext), default=0.0) + ZONE_PAD), 4))


def _bottom_zone_shapes(sheet: str, refs: list[str], side_of: dict[str, str],
                        bbox_of: dict, resolvable: dict,
                        face_top: frozenset[str],
                        tmpl: tuple | None, tmpl_rot: dict[str, float],
                        tmpl_members: frozenset[str] = frozenset()
                        ) -> list[ZoneShape]:
    out: list[ZoneShape] = []
    if tmpl is not None:
        t_off, b_off, zw, zh = tmpl
        lifted = sorted(r for r in t_off if r in face_top)
        if set(lifted) & tmpl_members:
            _fb.record("bottom_variant_contract_reject")
            return out
        if lifted:
            t_off, b_off, zw, zh = _lift_face_top(
                t_off, b_off, zw, zh, lifted, bbox_of, resolvable, tmpl_rot)
        mt, mb, extra, mods = _mirror_pack(t_off, b_off, zw, dict(tmpl_rot),
                                           bbox_of, resolvable)
        if set(mt) & face_top:
            raise AssertionError(
                f"bottom-side eligibility: {sheet} kept face=top part(s) "
                f"{', '.join(sorted(set(mt) & face_top))} in the PRIMARY pack "
                f"of its bottom variant (would emit B.Cu) — the lift did not "
                f"run; a user-facing part never emits face-down")
        if _mirror_contract_holds(sheet, mt, mb, set(), extra, {},
                                  resolvable, mods=mods):
            out.append(ZoneShape(w=round(zw, 4), h=round(zh, 4), top_off=mt,
                                 bot_off=mb, extra_rot=extra,
                                 tag="bottom", side="bottom", mirror=mods))
        else:
            _fb.record("bottom_variant_contract_reject")
        return out
    seen: set[tuple[float, float]] = set()
    role_split = (("bottom-a{}", {r: "top" for r in refs}),
                  ("bottom-split-a{}", side_of))
    for tag_fmt, so in role_split:
        for asp in (1.0, *INTERIOR_SHAPE_ASPECTS):
            vt, vb, vw, vh = _pack_one_zone(refs, so, bbox_of, resolvable,
                                            asp, face_top=face_top)
            key = (round(vw, 4), round(vh, 4))
            if key in seen:
                continue
            seen.add(key)
            mt, mb, extra, mods = _mirror_pack(vt, vb, vw, {}, bbox_of,
                                               resolvable)
            if set(mt) & face_top:
                raise AssertionError(
                    f"bottom-side eligibility: {sheet} packed face=top "
                    f"part(s) {', '.join(sorted(set(mt) & face_top))} into "
                    f"the PRIMARY pack of its bottom variant (would emit "
                    f"B.Cu) — a user-facing part never emits face-down")
            out.append(ZoneShape(
                w=vw, h=vh, top_off=mt, bot_off=mb, extra_rot=extra,
                tag=tag_fmt.format(f"{asp:g}"), side="bottom", mirror=mods))
    return out


def _pack_connector_zone(sr: dict[str, list[str]], items, bbox_of: dict,
                         resolvable: dict, conn_rot: dict[str, float],
                         outer_dir: str, aspect: float
                         ) -> tuple[dict[str, tuple[float, float]],
                                    dict[str, tuple[float, float]],
                                    float, float]:
    conn_refs_top = [r for r in sr["top"] if r in conn_rot]
    conn_refs_bot = [r for r in sr["bottom"] if r in conn_rot]
    rest_top = [r for r in sr["top"] if r not in conn_rot]
    rest_bot = [r for r in sr["bottom"] if r not in conn_rot]

    horiz = outer_dir in ("N", "S")
    def hbox(r, _side):
        rb = turn_box(bbox_of[r], conn_rot.get(r, 0.0))
        return (rb[0] - PLACE_CLEAR / 2, rb[1] - PLACE_CLEAR / 2,
                rb[2] + PLACE_CLEAR / 2, rb[3] + PLACE_CLEAR / 2)

    conn_all = [(r, "top") for r in conn_refs_top] + \
               [(r, "bottom") for r in conn_refs_bot]
    if horiz:
        conn_all.sort(key=lambda rs: (-(hbox(*rs)[2] - hbox(*rs)[0]), rs[0]))
    else:
        conn_all.sort(key=lambda rs: (-(hbox(*rs)[3] - hbox(*rs)[1]), rs[0]))

    placed: dict[str, dict[str, tuple[float, float]]] = {"top": {}, "bottom": {}}
    occ: list[tuple[float, float, float, float]] = []
    conn_depth = 0.0
    cursor = ZONE_PAD
    for r, side in conn_all:
        hx0, hy0, hx1, hy1 = hbox(r, side)
        hw, hh = hx1 - hx0, hy1 - hy0
        if horiz:
            ox = cursor - hx0
            oy = ZONE_PAD - hy0
            occ.append((cursor, ZONE_PAD, cursor + hw, ZONE_PAD + hh))
            cursor += hw + PLACE_CLEAR
            conn_depth = max(conn_depth, ZONE_PAD + hh)
        else:
            ox = ZONE_PAD - hx0
            oy = cursor - hy0
            occ.append((ZONE_PAD, cursor, ZONE_PAD + hw, cursor + hh))
            cursor += hh + PLACE_CLEAR
            conn_depth = max(conn_depth, ZONE_PAD + hw)
        placed[side][r] = (round(ox, 4), round(oy, 4))

    behind = conn_depth + CONN_REST_GAP
    tot_area = sum((bbox_of[r][2] - bbox_of[r][0] + PLACE_CLEAR) *
                   (bbox_of[r][3] - bbox_of[r][1] + PLACE_CLEAR)
                   for r in rest_top + rest_bot)
    row_span = max(cursor, 8.0)
    target_w = max(row_span - ZONE_PAD,
                   (tot_area * ZONE_PACK_FILL) ** 0.5 * aspect)

    fmeta = _fanout_meta(rest_top + rest_bot, resolvable)
    rt = [(r, bbox_of[r], 0.0) for r in rest_top]
    t_rest, _tw, _th = _shelf_pack(rt, target_w, fanout=fmeta)
    blockers: list[tuple[float, float, float, float]] = []
    for r in rest_top:
        if not has_thru_pads(resolvable[r]):
            continue
        ox, oy = t_rest[r]
        bx0, by0, bx1, by1 = bbox_of[r]
        blockers.append((ox + bx0 - PLACE_CLEAR / 2 + (0 if horiz else behind),
                         oy + by0 - PLACE_CLEAR / 2 + (behind if horiz else 0),
                         ox + bx1 + PLACE_CLEAR / 2 + (0 if horiz else behind),
                         oy + by1 + PLACE_CLEAR / 2 + (behind if horiz else 0)))
    rb = [(r, bbox_of[r], 0.0) for r in rest_bot]
    b_rest, _bw, _bh = _shelf_pack(rb, target_w, blockers, fanout=fmeta)

    for r, (dx, dy) in t_rest.items():
        placed["top"][r] = (round(dx + (0 if horiz else behind), 4),
                            round(dy + (behind if horiz else 0), 4))
    for r, (dx, dy) in b_rest.items():
        placed["bottom"][r] = (round(dx + (0 if horiz else behind), 4),
                               round(dy + (behind if horiz else 0), 4))

    zw = zh = ZONE_PAD
    for side in ("top", "bottom"):
        for r, (ox, oy) in placed[side].items():
            if r in conn_rot:
                rb2 = turn_box(bbox_of[r], conn_rot.get(r, 0.0))
            else:
                rb2 = bbox_of[r]
            zw = max(zw, ox + rb2[2] + PLACE_CLEAR / 2)
            zh = max(zh, oy + rb2[3] + PLACE_CLEAR / 2)
    zw = round(zw + ZONE_PAD, 4)
    zh = round(zh + ZONE_PAD, 4)

    if outer_dir in ("S", "E"):
        flip_y = (outer_dir == "S")
        out: dict[str, dict[str, tuple[float, float]]] = {"top": {}, "bottom": {}}
        for side in ("top", "bottom"):
            for r, (ox, oy) in placed[side].items():
                if r in conn_rot:
                    rb2 = turn_box(bbox_of[r], conn_rot.get(r, 0.0))
                else:
                    rb2 = bbox_of[r]
                if flip_y:
                    noy = zh - (oy + rb2[3]) - rb2[1]
                    out[side][r] = (round(ox, 4), round(noy, 4))
                else:
                    nox = zw - (ox + rb2[2]) - rb2[0]
                    out[side][r] = (round(nox, 4), round(oy, 4))
        placed = out

    return placed["top"], placed["bottom"], zw, zh


def _connector_sheet_edges(spec=None) -> dict[str, str]:
    out: dict[str, str] = {}
    if spec is None:
        from schgen.generate.floorplan import FLOORPLAN_SPEC, load_floorplan_spec
        if not FLOORPLAN_SPEC.exists():
            return out
        try:
            spec = load_floorplan_spec()
        except Exception:  # noqa: BLE001
            return out
    if spec is None:
        return out
    return dict(spec.edge_of)


def _downstream_facing(sheet: str, contract: dict, spec=None) -> str | None:
    ext = contract.get("external") or {}
    if not ext.get("downstream"):
        return None
    if spec is None:
        from schgen.generate.floorplan import FLOORPLAN_SPEC, load_floorplan_spec
        if not FLOORPLAN_SPEC.exists():
            return None
        try:
            spec = load_floorplan_spec()
        except Exception:  # noqa: BLE001
            return None
    if spec is None:
        return None
    _OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
    side = None
    cfg = spec.interior.get(sheet)
    if isinstance(cfg, dict):
        side = cfg.get("side")
    if side is None:
        side = spec.edge_of.get(sheet)
    if side not in _OPP:
        return None
    return _OPP[side]


def _media_facing(sheet: str, contract: dict, spec=None) -> str | None:
    ext = contract.get("external") or {}
    if not ext.get("media_faces_near_max"):
        return None
    nm = ext.get("near_max") or []
    if not nm:
        return None
    target = str(nm[0].get("other", "")).split(".", 1)[0]
    if not target:
        return None
    if spec is None:
        from schgen.generate.floorplan import FLOORPLAN_SPEC, load_floorplan_spec
        if not FLOORPLAN_SPEC.exists():
            return None
        try:
            spec = load_floorplan_spec()
        except Exception:  # noqa: BLE001
            return None
    if spec is None:
        return None
    edge = spec.edge_of.get(target)
    return edge if edge in ("N", "E", "S", "W") else None


def subsystem_zone_geometry(two_side: bool = True, spec=None) -> ZoneGeom:
    import json as _json

    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.model import PinRef
    from schgen.generate.board import _renamed_ref

    idx_path = CARRIER / "sheet_index.json"
    sheet_index = (_json.loads(idx_path.read_text())
                   if idx_path.exists() else {})
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]

    from schgen.generate.floorplan import _EDGE_FAMILIES

    refs_by_sheet: dict[str, list[str]] = {}
    bbox_of: dict[str, tuple[float, float, float, float]] = {}
    resolvable: dict[str, Path] = {}
    side_of: dict[str, str] = {}
    mh_refs: list[str] = []
    deferred: list[str] = []
    edge_sheets: set[str] = set()
    conn_mpn_of: dict[str, str] = {}

    if spec is None:
        from schgen.generate.floorplan import FLOORPLAN_SPEC, load_floorplan_spec
        if FLOORPLAN_SPEC.exists():
            try:
                spec = load_floorplan_spec()
            except Exception:  # noqa: BLE001
                spec = None
    sheet_edge = _connector_sheet_edges(spec)
    layer_pref: dict[str, str] = dict(spec.layer_of) if spec else {}
    face_top_of: dict[str, set[str]] = {}
    conn_class_of: dict[str, str] = {}

    for i, sc in enumerate(sheets, start=1):
        if sc.name.startswith("som_j") or sc.name == "som_decoupling":
            continue
        band = sheet_index.get(sc.name, i)
        c = sc.circuit
        snets: dict[str, list[PinRef]] = {}
        for nname, net in c.nets.items():
            snets[nname] = [
                PinRef(_renamed_ref(p.ref, band, sheet=sc.name)
                       if not p.ref.startswith("#") else p.ref, p.pin)
                for p in net.pins]
        sdec = _decoupling_caps(snets)
        for ref, part in c.parts.items():
            bref = _renamed_ref(ref, band, sheet=sc.name)
            if part.value in _EDGE_FAMILIES:
                edge_sheets.add(sc.name)
            if part.value in CONN_MATING_FACE:
                conn_mpn_of[bref] = part.value
            if part.lib_id.startswith("Mechanical:MountingHole"):
                mh_refs.append(bref)
                continue
            mod = resolve_mod(part.footprint)
            if mod is None:
                deferred.append(f"{bref} ({sc.name}): footprint "
                                f"{part.footprint!r} not found")
                continue
            resolvable[bref] = mod
            bbox_of[bref] = _footprint_bbox(mod)
            side_of[bref] = _classify_side(bref, part.lib_id, bbox_of[bref],
                                           sdec, two_side)
            refs_by_sheet.setdefault(sc.name, []).append(bref)
            if _is_face_top_part(bref, part.lib_id, part.footprint):
                face_top_of.setdefault(sc.name, set()).add(bref)
            elif (sc.name not in conn_class_of
                  and (any(t in part.lib_id or t in part.footprint
                           for t in _CONN_CLASS_TOKENS)
                       or bref in _INT_DESC
                       or part.value in CONN_MATING_FACE)):
                conn_class_of[sc.name] = bref

    conn_rot: dict[str, float] = {}
    conn_edge: dict[str, str] = {}
    sheet_conn_rot: dict[str, dict[str, float]] = {}
    sheet_outer: dict[str, str] = {}
    for sheet, brefs in refs_by_sheet.items():
        edge = sheet_edge.get(sheet)
        for bref in brefs:
            mpn = conn_mpn_of.get(bref)
            if mpn is None or bref not in bbox_of:
                continue
            if edge is None:
                continue
            rot = connector_edge_rotation(CONN_MATING_FACE[mpn], edge)
            conn_rot[bref] = rot
            conn_edge[bref] = edge
            sheet_conn_rot.setdefault(sheet, {})[bref] = rot
            sheet_outer[sheet] = edge

    imp_of = _unreferenced_imp_sheets(sheets)
    for sheet in sorted(s for s, p in layer_pref.items()
                        if p in ("bottom", "either")):
        why = None
        if sheet not in refs_by_sheet:
            why = "it has no packable zone (reservation/mounting-hole only)"
        elif (sheet in edge_sheets or sheet in sheet_conn_rot
                or sheet in sheet_edge):
            why = "it carries a seated off-board connector (LAW 6 pins it top)"
        elif sheet in conn_class_of:
            why = (f"it contains connector-class part {conn_class_of[sheet]} "
                   f"(blocks with seated connectors stay top-pinned, user "
                   f"decision 2026-07-29)")
        elif sheet in imp_of:
            why = (f"it carries impedance-controlled net class(es) "
                   f"{', '.join(sorted(imp_of[sheet]))} and B.Cu's microstrip "
                   f"reference plane {MICROSTRIP_REFERENCE['B.Cu']} carries no "
                   f"emitted copper (only {GND_PLANE_LAYER} is filled) — a "
                   f"controlled-impedance pair placed face-down has NO "
                   f"reference and its geometry is unmodelled, not merely "
                   f"unrouted")
        if why:
            raise ValueError(
                f"floorplan.json: {sheet} declares copper-face "
                f"\"{layer_pref[sheet]}\" but {why} — remove the declaration "
                f"or pin the sheet top")

    zone_box: dict[str, tuple[float, float]] = {}
    top_off: dict[str, dict[str, tuple[float, float]]] = {}
    bot_off: dict[str, dict[str, tuple[float, float]]] = {}
    zone_extra_rot: dict[str, float] = {}
    zone_shapes: dict[str, tuple[ZoneShape, ...]] = {}
    for sheet in sorted(refs_by_sheet):
        is_edge = sheet in edge_sheets
        aspect = EDGE_ZONE_ASPECT if is_edge else 1.0
        eligible = layer_pref.get(sheet) in ("bottom", "either")
        face_top = frozenset(face_top_of.get(sheet, ()))

        from schgen.verify.placement_contract_gate import load_contract

        from . import stage_templates
        _contract = load_contract(sheet)
        _tmpl = None
        _tmpl_members: frozenset[str] = frozenset()
        if _contract is not None:
            _members = stage_templates.contract_member_brefs(sheet, _contract,
                                                             resolvable)
            _tmpl_members = frozenset(_members)
            for _m in _members:
                side_of[_m] = "top"
            tmpl_rot: dict[str, float] = {}
            _facing = (_downstream_facing(sheet, _contract, spec)
                       or _media_facing(sheet, _contract, spec))
            _tmpl = stage_templates.build_zone(
                sheet, _contract, refs_by_sheet[sheet], side_of, bbox_of,
                resolvable, tmpl_rot, facing=_facing,
                outer_dir=sheet_outer.get(sheet))
        if _tmpl is not None:
            t_off, b_off, zw, zh = _tmpl
            rt, rb, er, rw, rh = _rotate_zone_90(
                t_off, b_off, bbox_of, side_of, {}, zw, zh)
            r_rot = {r: (tmpl_rot.get(r, 0.0) + er[r]) % 360.0 for r in er}
            rt2, rb2, _e2, rw2, rh2 = _rotate_zone_90(
                rt, rb, bbox_of, side_of, {}, rw, rh)
            rt3, rb3, _e3, rw3, rh3 = _rotate_zone_90(
                rt2, rb2, bbox_of, side_of, {}, rw2, rh2)
            turned_now = ((not is_edge) and zh > INTERIOR_ZONE_BAND_TARGET
                          and zw <= INTERIOR_ZONE_BAND_TARGET and zw < zh)
            ab = ZoneShape(w=zw, h=zh, top_off=t_off, bot_off=b_off,
                           extra_rot=dict(tmpl_rot), tag="asbuilt")
            tn = ZoneShape(w=rw, h=rh, top_off=rt, bot_off=rb,
                           extra_rot=r_rot, tag="turned")
            t2 = ZoneShape(w=rw2, h=rh2, top_off=rt2, bot_off=rb2,
                           extra_rot={r: (tmpl_rot.get(r, 0.0) + 180.0)
                                      % 360.0 for r in er}, tag="t180")
            t3 = ZoneShape(w=rw3, h=rh3, top_off=rt3, bot_off=rb3,
                           extra_rot={r: (tmpl_rot.get(r, 0.0) + 270.0)
                                      % 360.0 for r in er}, tag="t270")
            if turned_now:
                t_off, b_off, zw, zh = rt, rb, rw, rh
                tmpl_rot = r_rot
            if (not is_edge) and sheet not in sheet_conn_rot:
                ordered = (tn, ab, t2, t3) if turned_now else (ab, tn, t2, t3)
                uniq: list[ZoneShape] = []
                seen_geo: set[tuple] = set()
                for s_ in ordered:
                    key_ = (round(s_.w, 4), round(s_.h, 4),
                            tuple(sorted(s_.top_off.items())),
                            tuple(sorted(s_.bot_off.items())),
                            tuple(sorted(s_.extra_rot.items())))
                    if key_ in seen_geo:
                        continue
                    seen_geo.add(key_)
                    uniq.append(s_)
                if eligible:
                    uniq.extend(_bottom_zone_shapes(
                        sheet, refs_by_sheet[sheet], side_of, bbox_of,
                        resolvable, face_top, (t_off, b_off, zw, zh),
                        tmpl_rot, _tmpl_members))
                if len(uniq) >= 2:
                    zone_shapes[sheet] = tuple(uniq)
            elif sheet in sheet_conn_rot:
                mir = _member_mirror_shape(
                    sheet, t_off, b_off, zw, zh, set(sheet_conn_rot[sheet]),
                    bbox_of, dict(tmpl_rot), sheet_conn_rot[sheet],
                    resolvable)
                if mir is not None:
                    zone_shapes[sheet] = (
                        ZoneShape(w=zw, h=zh, top_off=t_off, bot_off=b_off,
                                  extra_rot=dict(tmpl_rot), tag="asbuilt"),
                        mir)
            zone_extra_rot.update(tmpl_rot)
            top_off[sheet] = t_off
            bot_off[sheet] = b_off
            zone_box[sheet] = (zw, zh)
            continue

        t_off, b_off, zw, zh = _pack_one_zone(
            refs_by_sheet[sheet], side_of, bbox_of, resolvable, aspect,
            conn_rot=sheet_conn_rot.get(sheet),
            outer_dir=sheet_outer.get(sheet))

        sheet_rot: dict[str, float] = {}
        if (not is_edge) and zh > INTERIOR_ZONE_BAND_TARGET:
            rt_off, rb_off, rzw, rzh = _pack_one_zone(
                refs_by_sheet[sheet], side_of, bbox_of, resolvable,
                INTERIOR_ZONE_ASPECT)
            if rzh <= INTERIOR_ZONE_BAND_TARGET and rzh < zh:
                t_off, b_off, zw, zh = rt_off, rb_off, rzw, rzh
            elif zw <= INTERIOR_ZONE_BAND_TARGET and zw < zh:
                t_off, b_off, er, zw, zh = _rotate_zone_90(
                    t_off, b_off, bbox_of, side_of, {}, zw, zh)
                zone_extra_rot.update(er)
                sheet_rot = er

        if (not is_edge) and sheet not in sheet_conn_rot:
            seen = {(round(zw, 4), round(zh, 4))}
            var: list[ZoneShape] = []
            for asp in INTERIOR_SHAPE_ASPECTS:
                vt, vb, vw, vh = _pack_one_zone(
                    refs_by_sheet[sheet], side_of, bbox_of, resolvable, asp)
                key = (round(vw, 4), round(vh, 4))
                if key in seen:
                    continue
                seen.add(key)
                var.append(ZoneShape(w=vw, h=vh, top_off=vt, bot_off=vb,
                                     extra_rot={}, tag=f"a{asp:g}"))
            if eligible:
                var.extend(_bottom_zone_shapes(
                    sheet, refs_by_sheet[sheet], side_of, bbox_of,
                    resolvable, face_top, None, {}))
            if var:
                zone_shapes[sheet] = (
                    ZoneShape(w=zw, h=zh, top_off=t_off, bot_off=b_off,
                              extra_rot=sheet_rot, tag="base"), *var)
        elif sheet in sheet_conn_rot:
            mir = _member_mirror_shape(
                sheet, t_off, b_off, zw, zh, set(sheet_conn_rot[sheet]),
                bbox_of, dict(sheet_rot), sheet_conn_rot[sheet], resolvable)
            if mir is not None:
                zone_shapes[sheet] = (
                    ZoneShape(w=zw, h=zh, top_off=t_off, bot_off=b_off,
                              extra_rot=dict(sheet_rot), tag="asbuilt"), mir)

        top_off[sheet] = t_off
        bot_off[sheet] = b_off
        zone_box[sheet] = (zw, zh)

    return ZoneGeom(zone_box=zone_box, top_off=top_off, bot_off=bot_off,
                    side_of=side_of, bbox_of=bbox_of, resolvable=resolvable,
                    refs_by_sheet=refs_by_sheet, mh_refs=sorted(mh_refs),
                    deferred=deferred, conn_rot=conn_rot, conn_edge=conn_edge,
                    zone_extra_rot=zone_extra_rot, shapes=zone_shapes)


def apply_chosen_shapes(zg: ZoneGeom, chosen: dict[str, int]) -> ZoneGeom:
    from dataclasses import replace as _dc_replace
    sel: dict[str, int] = {}
    for s, k in chosen.items():
        if not k:
            continue
        shp = zg.shapes.get(s)
        if shp is None or k >= len(shp):
            raise AssertionError(
                f"apply_chosen_shapes: {s} chose shape {k} but the zone "
                f"geometry registered {0 if shp is None else len(shp)} shapes")
        sel[s] = k
    if not sel:
        return zg
    zone_box = dict(zg.zone_box)
    top_off = dict(zg.top_off)
    bot_off = dict(zg.bot_off)
    extra = dict(zg.zone_extra_rot)
    side_of = dict(zg.side_of)
    resolvable = dict(zg.resolvable)
    bbox_of = dict(zg.bbox_of)
    mirror_refs = set(zg.mirror_refs)
    for s in sorted(sel):
        shp = zg.shapes[s][sel[s]]
        for r in (*zg.top_off.get(s, {}), *zg.bot_off.get(s, {})):
            extra.pop(r, None)
        zone_box[s] = (shp.w, shp.h)
        top_off[s] = dict(shp.top_off)
        bot_off[s] = dict(shp.bot_off)
        extra.update(shp.extra_rot)
        if shp.side == "bottom":
            for r in shp.top_off:
                side_of[r] = "bottom"
            for r in shp.bot_off:
                side_of[r] = "top"
            assert set(shp.mirror) == set(shp.top_off), (
                f"apply_chosen_shapes: {s} bottom shape {sel[s]} primary "
                f"pack and mirror map disagree — a primary member without "
                f"its mirrored document would emit the chiral-wrong pattern")
            for r, mp in sorted(shp.mirror.items()):
                resolvable[r] = mp
                bbox_of[r] = _footprint_bbox(mp)
                mirror_refs.add(r)
    return _dc_replace(zg, zone_box=zone_box, top_off=top_off,
                       bot_off=bot_off, zone_extra_rot=extra,
                       side_of=side_of, resolvable=resolvable,
                       bbox_of=bbox_of, mirror_refs=frozenset(mirror_refs))


def _segments_cross_py(s1: tuple, s2: tuple) -> bool:
    (p1, p2), (p3, p4) = s1, s2
    eps = 1e-9
    if {(p1[0], p1[1]), (p2[0], p2[1])} & {(p3[0], p3[1]), (p4[0], p4[1])}:
        return False

    def d(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1, d2 = d(p3, p4, p1), d(p3, p4, p2)
    d3, d4 = d(p1, p2, p3), d(p1, p2, p4)
    return (((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps))
            and ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps)))


def _segments_cross(s1: tuple, s2: tuple) -> bool:
    if _nat.loaded():
        (p1, p2), (p3, p4) = s1, s2
        got = _nat.module().segments_cross(
            p1[0], p1[1], p2[0], p2[1], p3[0], p3[1], p4[0], p4[1])
        if _nat.trace():
            ref = _segments_cross_py(s1, s2)
            if got is not ref:
                raise AssertionError(
                    "native segments_cross DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _segments_cross_py(s1, s2)


def _reorder_interchangeable(pos: dict[str, tuple[float, float]],
                             refs_by_sheet: dict[str, list[str]],
                             side_of: dict[str, str],
                             resolvable: dict[str, Path],
                             fixed_rot: dict[str, float],
                             bbox_of: dict,
                             nets: dict,
                             pin_net: dict[tuple[str, str], tuple[int, str]],
                             conn_seated: set[str],
                             skip_sheets: set[str]
                             ) -> dict[str, list[tuple[str, int, int]]]:
    from schgen.verify.fanout_gate import _is_cluster_passive

    rotpads: dict[tuple[str, float], dict[str, tuple[float, float]]] = {}
    pad_cache: dict[tuple[str, float, float], dict[str, tuple[float, float]]] = {}

    def pad_xy(ref: str) -> dict[str, tuple[float, float]]:
        ck = (ref, pos[ref][0], pos[ref][1])
        got = pad_cache.get(ck)
        if got is None:
            rk = (str(resolvable[ref]), fixed_rot.get(ref, 0.0))
            base = rotpads.get(rk)
            if base is None:
                stub = FootprintInst(
                    ref=ref, value="", footprint="", x=0.0, y=0.0,
                    rotation=rk[1], pad_nets={}, mod_path=resolvable[ref],
                    sheet="", side="top")
                base = {n: (x, y) for n, x, y, _nn in _inst_pad_geom(stub)}
                rotpads[rk] = base
            x, y = pos[ref]
            got = {n: (px + x, py + y) for n, (px, py) in base.items()}
            pad_cache[ck] = got
        return got

    report: dict[str, list[tuple[str, int, int]]] = {}
    for sheet in sorted(refs_by_sheet):
        if sheet in skip_sheets:
            continue
        groups: dict[tuple, list[str]] = {}
        for r in refs_by_sheet[sheet]:
            if r not in pos or r not in resolvable or r in conn_seated:
                continue
            pins = len(pad_names(resolvable[r]))
            gk = (side_of.get(r, "top"), str(resolvable[r]),
                  round(fixed_rot.get(r, 0.0), 1) % 360.0,
                  _is_cluster_passive(r, pins))
            groups.setdefault(gk, []).append(r)
        for gk in sorted(groups):
            members = sorted(groups[gk])
            if len(members) < 2:
                continue
            gset = set(members)
            eb = turn_box(bbox_of[members[0]], gk[2])
            tol_x = max(0.6, (eb[2] - eb[0]) / 2)
            tol_y = max(0.6, (eb[3] - eb[1]) / 2)
            clusters: list[tuple[str, list[str]]] = []
            rest: list[str] = []
            row: list[str] = []
            for m in sorted(members, key=lambda m: (pos[m][1], pos[m][0], m)):
                if row and abs(pos[m][1] - pos[row[0]][1]) > tol_y:
                    if len(row) > 1:
                        clusters.append(("x", row))
                    else:
                        rest.extend(row)
                    row = []
                row.append(m)
            if len(row) > 1:
                clusters.append(("x", row))
            elif row:
                rest.extend(row)
            col: list[str] = []
            for m in sorted(rest, key=lambda m: (pos[m][0], pos[m][1], m)):
                if col and abs(pos[m][0] - pos[col[0]][0]) > tol_x:
                    if len(col) > 1:
                        clusters.append(("y", col))
                    col = []
                col.append(m)
            if len(col) > 1:
                clusters.append(("y", col))
            for axis, cluster in clusters:
                ai = 0 if axis == "x" else 1
                mlist = sorted(cluster)
                slots = sorted((pos[m] for m in cluster),
                               key=lambda p: (p[ai], p[1 - ai]))
                static_pts: dict[str, list[tuple[float, float]]] = {}
                for m in mlist:
                    for pad in pad_names(resolvable[m]):
                        _num, n = pin_net.get((m, pad), (0, ""))
                        if not n or n in static_pts or n not in nets:
                            continue
                        pts = []
                        for pr in nets[n]:
                            if (pr.ref in gset or pr.ref.startswith("#")
                                    or pr.ref not in pos
                                    or pr.ref not in resolvable):
                                continue
                            xy = pad_xy(pr.ref).get(pr.pin)
                            if xy is not None:
                                pts.append(xy)
                        static_pts[n] = pts
                seg_of: dict[tuple[str, int], list[tuple]] = {}
                for m in mlist:
                    offs = {p: (x - pos[m][0], y - pos[m][1])
                            for p, (x, y) in pad_xy(m).items()}
                    for si, sp in enumerate(slots):
                        segs = []
                        for pad in sorted(offs):
                            _num, n = pin_net.get((m, pad), (0, ""))
                            pts = static_pts.get(n) if n else None
                            if not pts:
                                continue
                            dx, dy = offs[pad]
                            px, py = sp[0] + dx, sp[1] + dy
                            tgt = min(pts, key=lambda q: (abs(q[0] - px)
                                                          + abs(q[1] - py),
                                                          q[0], q[1]))
                            segs.append(((px, py), (tgt[0], tgt[1])))
                        seg_of[(m, si)] = segs

                def fan(assign: dict[str, int],
                        _seg=seg_of, _ml=mlist) -> int:
                    segs = [s for m in _ml for s in _seg[(m, assign[m])]]
                    return sum(1 for a in range(len(segs))
                               for b in range(a + 1, len(segs))
                               if _segments_cross(segs[a], segs[b]))

                order0 = sorted(cluster, key=lambda m: (pos[m][ai], m))
                assign = {m: i for i, m in enumerate(order0)}
                before = fan(assign)
                if before == 0:
                    continue
                best = before
                for _sweep in range(6):
                    improved = False
                    for a in range(len(mlist)):
                        for b in range(a + 1, len(mlist)):
                            ma, mb = mlist[a], mlist[b]
                            assign[ma], assign[mb] = assign[mb], assign[ma]
                            trial = fan(assign)
                            if trial < best:
                                best = trial
                                improved = True
                            else:
                                assign[ma], assign[mb] = \
                                    assign[mb], assign[ma]
                    if not improved:
                        break
                if best == before:
                    continue
                for m in mlist:
                    pos[m] = slots[assign[m]]
                report.setdefault(sheet, []).append(
                    (f"{axis}-{len(cluster)}", before, best))
    return report


def som_core_rect(som_x: float, som_y: float, som_w: float, som_h: float
                  ) -> tuple[float, float, float, float]:
    ccx = som_w * SOM_CORE_CLEARANCE / 2
    ccy = som_h * SOM_CORE_CLEARANCE / 2
    return (ORIGIN_X + som_x - ccx, ORIGIN_Y + som_y - ccy,
            ORIGIN_X + som_x + som_w + ccx,
            ORIGIN_Y + som_y + som_h + ccy)


SOM_DECOUPLING_INSET = 6.0
CONN_REST_GAP = 2.0
DISP_CAP_L4 = 5.0
L4_PULL_STEP = 1.0
L4_PULL_SPAN = 40.0


def som_decoupling_grid(som_w: float, som_h: float, n: int
                        ) -> tuple[float, float, int, int]:
    rw = max(1.0, som_w - 2 * SOM_DECOUPLING_INSET)
    rh = max(1.0, som_h - 2 * SOM_DECOUPLING_INSET)
    cols = max(1, min(n, round((n * rw / rh) ** 0.5))) if n else 1
    rows = max(1, (n + cols - 1) // cols) if n else 1
    return rw, rh, cols, rows


def som_decoupling_cells(som_x: float, som_y: float, som_w: float,
                         som_h: float, n: int
                         ) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    rx0 = som_x + SOM_DECOUPLING_INSET
    ry0 = som_y + SOM_DECOUPLING_INSET
    rw, rh, cols, rows = som_decoupling_grid(som_w, som_h, n)
    return [(round(rx0 + rw * (i % cols + 0.5) / cols, 4),
             round(ry0 + rh * (i // cols + 0.5) / rows, 4))
            for i in range(n)]


def build_model(two_side: bool = True, spec=None) -> PcbModel:
    from schgen.core.link import (
        all_subsystem_paths,
        link,
        load_som_contract,
        load_subsystem,
    )
    from schgen.generate import floorplan as fp
    from schgen.verify import powertree

    _fb.reset()
    _trk = StageTracker()

    nets = board_netlist()
    parts = board_parts()

    real_nets = sorted(n for n in nets if n and not n.startswith("unconnected-"))
    net_numbers: dict[str, int] = {"": 0}
    for i, name in enumerate(real_nets, start=1):
        net_numbers[name] = i
    pin_net: dict[tuple[str, str], tuple[int, str]] = {}
    for name, pins in nets.items():
        if name.startswith("unconnected-"):
            continue
        num = net_numbers.get(name, 0)
        for pr in pins:
            if not pr.ref.startswith("#"):
                pin_net[(pr.ref, pr.pin)] = (num, name)

    from schgen.core import timing as _tim
    with _tim.span("pcb.zone_pack"):
        zg = subsystem_zone_geometry(two_side=two_side, spec=spec)
    _trk.checkpoint("zone_pack", {})
    zone_box = zg.zone_box
    top_off = zg.top_off
    bot_off = zg.bot_off
    side_of = dict(zg.side_of)
    bbox_of = dict(zg.bbox_of)
    resolvable = dict(zg.resolvable)
    deferred = list(zg.deferred)
    mh_refs = list(zg.mh_refs)
    mh_set = set(mh_refs)

    for ref, (sheet, footprint, _value, _lib) in parts.items():
        if ref in resolvable:
            continue
        if not (ref in mh_set or sheet.startswith("som_j")
                or sheet == "som_decoupling"):
            continue
        mod = resolve_mod(footprint)
        if mod is None:
            deferred.append(f"{ref} ({sheet}): footprint {footprint!r} "
                            f"not found in parts/ or the KiCad std libs")
            continue
        resolvable[ref] = mod
        bbox_of[ref] = _footprint_bbox(mod)
        side_of[ref] = "top"

    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    link_result = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    with _tim.span("pcb.build_plan"):
        plan = fp.build_plan(sheets, link_result, regs, spec=spec)
    _led.open_step("pcb.placement")
    _led.calc("edge_flush", EDGE_FLUSH_MM, edge_pad_clear=EDGE_PAD_CLEAR,
              flush_relief=EDGE_FLUSH_RELIEF)
    _led.calc("template_clear", TEMPLATE_CLEAR,
              place_clear_baseline=PLACE_CLEAR_BASELINE)
    from .stage_templates import _NONSW_RELIEF, _NONSW_STAGE_GAP
    _led.calc("nonsw_stage_gap", _NONSW_STAGE_GAP,
              template_clear=TEMPLATE_CLEAR, nonsw_relief=_NONSW_RELIEF)
    _trk.checkpoint("plan_lattice", {})
    zg = apply_chosen_shapes(zg, {b.name: b.shape_idx for b in plan.blocks})
    _trk.checkpoint("shape_bind", {})
    zone_box = zg.zone_box
    top_off = zg.top_off
    bot_off = zg.bot_off
    side_of.update(zg.side_of)
    resolvable.update(zg.resolvable)
    bbox_of.update(zg.bbox_of)
    classes, netclass_of = _net_classes(sheets)
    board_w, board_h = fp.BOARD_W, fp.BOARD_H

    som = plan.som
    som_rot = {j.ref: (90.0 if j.w < j.h else 0.0) for j in som.js}
    som_rel = {j.ref: (j.x, j.y) for j in som.js}
    som_j_refs: dict[str, str] = {}
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

    for ref, rot in zg.conn_rot.items():
        if ref in resolvable:
            fixed_rot[ref] = rot

    for ref, extra in zg.zone_extra_rot.items():
        if ref in resolvable:
            fixed_rot[ref] = (fixed_rot.get(ref, 0.0) + extra) % 360.0

    block_of = {b.name: b for b in plan.blocks}
    zorigin: dict[str, tuple[float, float]] = {}
    for sheet in zone_box:
        b = block_of.get(sheet)
        if b is None:
            continue
        zorigin[sheet] = (b.x, b.y)

    halo = 1.0
    keepout = (plan.som_x - halo, plan.som_y - halo,
               plan.som_x + som.w + halo, plan.som_y + som.h + halo)
    som_view = {jn: (plan.som_x + sx, plan.som_y + sy)
                for jn, (sx, sy) in som_rel.items()}

    pos: dict[str, tuple[float, float]] = {}
    corners = [(MH_INSET, MH_INSET),
               (board_w - MH_INSET, MH_INSET),
               (board_w - MH_INSET, board_h - MH_INSET),
               (MH_INSET, board_h - MH_INSET)]
    for i, ref in enumerate(mh_refs):
        pos[ref] = corners[i % 4]
    for ref, jname in som_j_refs.items():
        pos[ref] = som_view[jname]
    grid_placed: set[str] = set()
    for sheet in zorigin:
        zx, zy = zorigin[sheet]
        for r, (dx, dy) in top_off[sheet].items():
            pos[r] = (zx + dx, zy + dy)
            grid_placed.add(r)
        for r, (dx, dy) in bot_off[sheet].items():
            pos[r] = (zx + dx, zy + dy)
            grid_placed.add(r)

    udec = sorted(r for r, (sh, _f, _v, _l) in parts.items()
                  if sh == "som_decoupling" and r in resolvable)
    for ref, cell in zip(udec, som_decoupling_cells(
            plan.som_x, plan.som_y, som.w, som.h, plan.dec_bank[0]),
            strict=True):
        pos[ref] = cell
        side_of[ref] = "bottom"
        grid_placed.add(ref)

    def _pose_snap() -> dict[str, tuple]:
        return {r: (p[0], p[1], fixed_rot.get(r, 0.0))
                for r, p in pos.items()}

    _trk.checkpoint("step3_emission", _pose_snap())

    if two_side:
        som_cx = plan.som_x + som.w / 2.0
        som_cy = plan.som_y + som.h / 2.0

        def _eff_box(ref: str, px: float, py: float
                     ) -> tuple[float, float, float, float]:
            ex0, ey0, ex1, ey1 = turn_box(bbox_of[ref],
                                              fixed_rot.get(ref, 0.0))
            return (px + ex0, py + ey0, px + ex1, py + ey1)

        def _halo(b: tuple[float, float, float, float], m: float
                  ) -> tuple[float, float, float, float]:
            return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)

        def _hit(b: tuple[float, float, float, float],
                 boxes: list[tuple[float, float, float, float]]) -> bool:
            for o in boxes:
                if (b[0] < o[2] and b[2] > o[0]
                        and b[1] < o[3] and b[3] > o[1]):
                    return True
            return False

        tht_boxes: list[tuple[float, float, float, float]] = [
            _halo(_eff_box(r, pos[r][0], pos[r][1]), PLACE_CLEAR)
            for r in pos
            if side_of.get(r) == "top" and r in resolvable
            and has_thru_pads(resolvable[r])]

        bot_box: dict[str, tuple[float, float, float, float]] = {
            r: _halo(_eff_box(r, pos[r][0], pos[r][1]), PLACE_CLEAR / 2)
            for r in pos
            if side_of.get(r) == "bottom" and r in bbox_of}

        _escape_corridors: list[tuple[float, float, float, float]] = []
        from schgen.generate import floorplan as _fp
        from schgen.generate.pcb import constants as _const
        if (_const.PLACE_CLEAR > _const.PLACE_CLEAR_BASELINE
                or _fp.SOM_DX or _fp.SOM_DY):
            from schgen.generate.pcb.escape import corridor_board_rect
            _escape_corridors = [
                corridor_board_rect(resolvable[r], pos[r][0], pos[r][1],
                                    fixed_rot.get(r, 0.0))
                for r in sorted(som_j_refs)
                if r in resolvable and r in pos]

        from schgen.verify.fanout_gate import (
            MIN_SUBJECT_PINS,
            intelligent_need,
        )
        d13_bot: dict[str, tuple[str, tuple[float, float, float, float]]] = {}
        for r in sorted(pos):
            if (side_of.get(r) == "bottom" and r in resolvable
                    and r in bbox_of and r in parts):
                npins = len(pad_names(resolvable[r]))
                if npins < MIN_SUBJECT_PINS:
                    continue
                need = _q.quant_credit(intelligent_need(npins)[0])
                d13_bot[r] = (parts[r][0], _halo(
                    _eff_box(r, pos[r][0], pos[r][1]),
                    max(0.0, need - PLACE_CLEAR / 2)))
        from schgen.verify.placement_contract_gate import (
            wired_term_participants,
        )
        _l4_exempt, _far_only = wired_term_participants()
        for sheet in sorted(zorigin):
            if sheet in _l4_exempt:
                continue
            movers = [r for r in bot_off.get(sheet, {})
                      if side_of.get(r) == "bottom" and r in pos
                      and r[:1] in ("R", "C", "L")
                      and not r.startswith(("RJ", "LED"))]
            if len(movers) < 2:
                continue
            gcx = sum(pos[r][0] for r in movers) / len(movers)
            gcy = sum(pos[r][1] for r in movers) / len(movers)
            vx, vy = som_cx - gcx, som_cy - gcy
            dist = (vx * vx + vy * vy) ** 0.5
            if dist < 1.0:
                continue
            ux, uy = vx / dist, vy / dist
            mset = set(movers)
            others = ([bot_box[r] for r in bot_box if r not in mset]
                      + _escape_corridors
                      + [b for rr, (sh, b) in sorted(d13_bot.items())
                         if sh != sheet and rr not in mset])
            allr = [r for r in (list(top_off.get(sheet, {}))
                                + list(bot_off.get(sheet, {})))
                    if r in pos and r in bbox_of]
            sum_area = sum((_eff_box(r, 0.0, 0.0)[2] - _eff_box(r, 0.0, 0.0)[0])
                           * (_eff_box(r, 0.0, 0.0)[3] - _eff_box(r, 0.0, 0.0)[1])
                           for r in allr) or 1.0
            chosen = 0.0
            for k in range(int(min(dist, L4_PULL_SPAN) / L4_PULL_STEP), 0, -1):
                shift = k * L4_PULL_STEP
                ok = True
                shifted: dict[str, tuple[float, float]] = {}
                for r in movers:
                    nx, ny = pos[r][0] + ux * shift, pos[r][1] + uy * shift
                    bb = _eff_box(r, nx, ny)
                    if (bb[0] < BOARD_EDGE_MARGIN
                            or bb[1] < BOARD_EDGE_MARGIN
                            or bb[2] > board_w - BOARD_EDGE_MARGIN
                            or bb[3] > board_h - BOARD_EDGE_MARGIN):
                        ok = False
                        break
                    hb = _halo(bb, PLACE_CLEAR / 2)
                    if _hit(hb, others) or _hit(hb, tht_boxes):
                        ok = False
                        break
                    shifted[r] = (nx, ny)
                if not ok:
                    continue
                xs0 = []
                ys0 = []
                xs1 = []
                ys1 = []
                for r in allr:
                    px, py = shifted.get(r, pos[r])
                    bb = _eff_box(r, px, py)
                    xs0.append(bb[0])
                    ys0.append(bb[1])
                    xs1.append(bb[2])
                    ys1.append(bb[3])
                if ((max(xs1) - min(xs0)) * (max(ys1) - min(ys0))
                        / sum_area) > DISP_CAP_L4:
                    continue
                chosen = shift
                break
            if chosen > 0.0:
                for r in movers:
                    nx, ny = (round(pos[r][0] + ux * chosen, 4),
                              round(pos[r][1] + uy * chosen, 4))
                    pos[r] = (nx, ny)
                    bot_box[r] = _halo(_eff_box(r, nx, ny), PLACE_CLEAR / 2)
                    if r in d13_bot:
                        sh, b = d13_bot[r]
                        grow = (b[2] - b[0]
                                - (_eff_box(r, 0.0, 0.0)[2]
                                   - _eff_box(r, 0.0, 0.0)[0])) / 2.0
                        d13_bot[r] = (sh, _halo(_eff_box(r, nx, ny), grow))

    _trk.checkpoint("l4_pull", _pose_snap())

    for ref, edge in zg.conn_edge.items():
        if ref not in resolvable or ref not in pos:
            continue
        pb = _rot_pad_bbox(resolvable[ref], fixed_rot.get(ref, 0.0))
        if pb is None:
            continue
        px0, py0, px1, py1 = pb
        x, y = pos[ref]
        if edge == "N":
            y = EDGE_PAD_CLEAR - py0
        elif edge == "S":
            y = board_h - EDGE_PAD_CLEAR - py1
        elif edge == "W":
            x = EDGE_PAD_CLEAR - px0
        elif edge == "E":
            x = board_w - EDGE_PAD_CLEAR - px1
        pos[ref] = (round(x, 4), round(y, 4))
        grid_placed.add(ref)

    _trk.checkpoint("edge_seat", _pose_snap())

    fixed = set(mh_refs) | set(som_j_refs)

    if two_side:
        from schgen.generate.pcb.breathe import _eff_box as _bz_eff
        from schgen.generate.pcb.breathe import _halo as _bz_halo
        from schgen.generate.pcb.breathe import breathe_fanout
        _page_keepout = (ORIGIN_X + keepout[0], ORIGIN_Y + keepout[1],
                         ORIGIN_X + keepout[2], ORIGIN_Y + keepout[3])
        _df40_bands = [
            _bz_halo(_bz_eff(bbox_of[r], fixed_rot.get(r, 0.0),
                             pos[r][0], pos[r][1]), 6.0)
            for r in som_j_refs if r in bbox_of and r in pos]
        for _ph in _BREATHE_PHASES:
            breathe_fanout(
                pos, resolvable=resolvable, parts=parts, bbox_of=bbox_of,
                fixed_rot=fixed_rot, side_of=side_of, zorigin=zorigin,
                board_w=board_w, board_h=board_h,
                som_keepout=_page_keepout, conn_edge=zg.conn_edge,
                mh_refs=set(mh_refs), som_j_refs=set(som_j_refs),
                df40_pad_boxes=_df40_bands, phase=_ph)

    _trk.checkpoint("breathe", _pose_snap())

    from schgen.verify.placement_contract_gate import _pad_boxes as _gpb
    from schgen.verify.placement_contract_gate import load_contract as _lc_refit

    from . import stage_templates as _st_refit
    _net_pins_all: dict[str, list[tuple[str, str]]] = {}
    for (_r, _p), (_num, _nm) in pin_net.items():
        if _nm and not _nm.startswith("unconnected-"):
            _net_pins_all.setdefault(_nm, []).append((_r, _p))
    for _nm in _net_pins_all:
        _net_pins_all[_nm].sort()
    for sheet in sorted(zorigin):
        _c = _lc_refit(sheet)
        ds = ((_c or {}).get("external") or {}).get("downstream")
        if not ds:
            continue
        srefs = sorted(r for r in zg.refs_by_sheet.get(sheet, []) if r in pos)
        drefs = [r for r in zg.refs_by_sheet.get(ds, []) if r in pos]
        if not srefs or not drefs or any(r in zg.conn_rot for r in srefs):
            continue
        cds = (sum(pos[r][0] for r in drefs) / len(drefs),
               sum(pos[r][1] for r in drefs) / len(drefs))
        _sset = set(srefs)
        _npins: dict[str, list[tuple[str, str]]] = {}
        _fpts: dict[str, list[tuple[float, float, str]]] = {}
        for _nm, _pl in _net_pins_all.items():
            own = [(r, p) for r, p in _pl if r in _sset]
            if not own:
                continue
            _npins[_nm] = own
            ext: list[tuple[float, float, str]] = []
            for r, p in _pl:
                if r in _sset or r not in pos or r not in resolvable:
                    continue
                bb = _gpb(resolvable[r], fixed_rot.get(r, 0.0) % 360.0).get(p)
                if bb is None:
                    continue
                ext.append((round(pos[r][0] + (bb[0] + bb[2]) / 2.0, 3),
                            round(pos[r][1] + (bb[1] + bb[3]) / 2.0, 3),
                            parts[r][0]))
            _fpts[_nm] = ext
        _turn = _st_refit.refit_facing(sheet, _c, {r: pos[r] for r in srefs},
                                       fixed_rot, resolvable, cds,
                                       _npins, _fpts)
        if _turn:
            for r, (x, y, rot) in _turn.items():
                pos[r] = (x, y)
                fixed_rot[r] = rot

    _trk.checkpoint("refit_facing", _pose_snap())

    _reorder_interchangeable(
        pos, zg.refs_by_sheet, side_of, resolvable, fixed_rot, bbox_of,
        nets, pin_net, set(zg.conn_rot),
        {s for s in zorigin if _lc_refit(s) is not None})

    _trk.checkpoint("reorder", _pose_snap())

    if two_side:
        from schgen.generate.pcb.escape import corridor_board_rect
        _corr0 = [corridor_board_rect(
                      resolvable[r],
                      _q.evict_corridor_grid(ORIGIN_X, pos[r][0]),
                      _q.evict_corridor_grid(ORIGIN_Y, pos[r][1]),
                      fixed_rot.get(r, 0.0))
                  for r in sorted(som_j_refs)
                  if r in resolvable and r in pos]

        def _ebox(ref: str, px: float, py: float
                  ) -> tuple[float, float, float, float]:
            eb = turn_box(bbox_of[ref], fixed_rot.get(ref, 0.0))
            return (px + eb[0], py + eb[1], px + eb[2], py + eb[3])

        def _collide(bb, boxes) -> bool:
            return any(bb[0] < o[2] and bb[2] > o[0]
                       and bb[1] < o[3] and bb[3] > o[1] for o in boxes)

        _bot = {r: _ebox(r, pos[r][0], pos[r][1]) for r in pos
                if side_of.get(r) == "bottom" and r in bbox_of}
        _tht = [_ebox(r, pos[r][0], pos[r][1]) for r in pos
                if side_of.get(r) == "top" and r in resolvable
                and r in bbox_of and has_thru_pads(resolvable[r])]
        from schgen.verify.fanout_gate import (
            MIN_SUBJECT_PINS as _MSP,
        )
        from schgen.verify.fanout_gate import (
            intelligent_need as _ineed,
        )
        _d13ev: dict[str, tuple[str, tuple[float, float, float, float]]] = {}
        for r in sorted(_bot):
            if r in resolvable and r in parts:
                np_ = len(pad_names(resolvable[r]))
                if np_ >= _MSP:
                    g = max(0.0, _q.quant_credit(_ineed(np_)[0]) - PLACE_CLEAR)
                    bb = _ebox(r, pos[r][0], pos[r][1])
                    _d13ev[r] = (parts[r][0], (bb[0] - g, bb[1] - g,
                                               bb[2] + g, bb[3] + g))
        for ref in sorted(_bot):
            b = _bot[ref]
            if not _collide(b, _corr0):
                continue
            exits: list[tuple[float, float, float]] = []
            m = PLACE_CLEAR / 2
            for cr in _corr0:
                if not _collide(b, [cr]):
                    continue
                exits += [(cr[2] - b[0] + m, cr[2] - b[0] + m, 0.0),
                          (b[2] - cr[0] + m, -(b[2] - cr[0] + m), 0.0),
                          (cr[3] - b[1] + m, 0.0, cr[3] - b[1] + m),
                          (b[3] - cr[1] + m, 0.0, -(b[3] - cr[1] + m))]
            moved = False
            for _d, ex, ey in sorted(exits):
                for k in range(0, 9):
                    sx = ex + (k if ex > 0 else -k if ex < 0 else 0.0)
                    sy = ey + (k if ey > 0 else -k if ey < 0 else 0.0)
                    nx = round(pos[ref][0] + sx, 4)
                    ny = round(pos[ref][1] + sy, 4)
                    nb = _ebox(ref, nx, ny)
                    if (nb[0] < BOARD_EDGE_MARGIN
                            or nb[1] < BOARD_EDGE_MARGIN
                            or nb[2] > board_w - BOARD_EDGE_MARGIN
                            or nb[3] > board_h - BOARD_EDGE_MARGIN):
                        continue
                    if _collide(nb, _corr0):
                        continue
                    grown = (nb[0] - PLACE_CLEAR, nb[1] - PLACE_CLEAR,
                             nb[2] + PLACE_CLEAR, nb[3] + PLACE_CLEAR)
                    if _collide(grown, [_bot[r] for r in _bot if r != ref]):
                        continue
                    if _collide(grown, _tht):
                        continue
                    if _collide(grown, [b for rr, (sh, b) in
                                        sorted(_d13ev.items())
                                        if rr != ref
                                        and sh != parts[ref][0]]):
                        continue
                    pos[ref] = (nx, ny)
                    _bot[ref] = nb
                    moved = True
                    break
                if moved:
                    break
            if moved:
                _fb.record("corridor_evict_moved")
            else:
                _fb.record("corridor_stray_unmovable")

    _trk.checkpoint("corridor_eviction", _pose_snap())
    _led.calc("stage_movement", sum(_trk.moves.values()),
              l4_pull=_trk.moves.get("l4_pull", 0),
              edge_seat=_trk.moves.get("edge_seat", 0),
              breathe=_trk.moves.get("breathe", 0),
              refit_facing=_trk.moves.get("refit_facing", 0),
              reorder=_trk.moves.get("reorder", 0),
              corridor_eviction=_trk.moves.get("corridor_eviction", 0))

    insts: list[FootprintInst] = []
    placed = 0
    n_top = n_bottom = 0
    for ref in sorted(resolvable):
        sheet, footprint, value, lib = parts[ref]
        mod = resolvable[ref]
        bx, by = pos[ref]
        side = "top" if ref in fixed else side_of[ref]
        if side == "bottom" and _is_face_top_part(ref, lib, footprint):
            raise AssertionError(
                f"EMISSION: user-facing part {ref} ({sheet}, {footprint}) is "
                f"about to emit on B.Cu — a TP/LED/SW must present on the "
                f"board TOP face (the secondary pack of a bottom-assigned "
                f"block); a bottom shape leaked it into the primary pack")
        pad_nets: dict[str, tuple[int, str]] = {}
        for pad in pad_names(mod):
            pad_nets[pad] = pin_net.get((ref, pad), (0, ""))
        if ref in grid_placed:
            fx, fy = round(ORIGIN_X + bx, 4), round(ORIGIN_Y + by, 4)
        else:
            fx, fy = (_q.fixed_part_grid(ORIGIN_X + bx),
                      _q.fixed_part_grid(ORIGIN_Y + by))
        insts.append(FootprintInst(
            ref=ref, value=value, footprint=footprint,
            x=fx, y=fy,
            rotation=fixed_rot.get(ref, 0.0), pad_nets=pad_nets,
            mod_path=mod, sheet=sheet, side=side,
            mirror=ref in zg.mirror_refs))
        placed += 1
        if side == "bottom":
            n_bottom += 1
        else:
            n_top += 1

    fid_mod = resolve_mod(FIDUCIAL_FOOTPRINT)
    fid_insts: list[FootprintInst] = []
    if fid_mod is not None:
        x0, y0 = ORIGIN_X, ORIGIN_Y
        x1, y1 = ORIGIN_X + board_w, ORIGIN_Y + board_h
        fid_pos: list[tuple[str, float, float]] = [
            ("FID1", x0 + FID_INSET, y0 + FID_INSET),
            ("FID2", x1 - FID_INSET, y0 + FID_INSET),
            ("FID3", x0 + FID_INSET, y1 - FID_INSET),
        ]
        kx0, ky0, kx1, ky1 = keepout
        ins = 3.0
        fid_pos += [
            ("FID4", ORIGIN_X + kx0 + ins, ORIGIN_Y + ky0 + ins),
            ("FID5", ORIGIN_X + kx1 - ins, ORIGIN_Y + ky1 - ins),
        ]
        for ref, fx, fy in fid_pos:
            fid_insts.append(FootprintInst(
                ref=ref, value="Fiducial", footprint=FIDUCIAL_FOOTPRINT,
                x=round(fx, 4), y=round(fy, 4), rotation=0.0,
                pad_nets={}, mod_path=fid_mod, sheet="mechanical", side="top"))
        insts.extend(fid_insts)
        placed += len(fid_insts)
        n_top += len(fid_insts)

    _trk.checkpoint("instantiate", _pose_snap())

    def _page_snap() -> dict[str, tuple]:
        return {i.ref: (i.x, i.y, i.rotation, i.side) for i in insts}

    _trk.checkpoint("emission_frame", _page_snap())

    kx0, ky0, kx1, ky1 = keepout
    som_core = som_core_rect(plan.som_x, plan.som_y, som.w, som.h)
    model = PcbModel(
        board_w=board_w, board_h=board_h, insts=insts,
        net_numbers=net_numbers, netclass_of=netclass_of, classes=classes,
        placed=placed, deferred=deferred,
        som_keepout=(ORIGIN_X + kx0, ORIGIN_Y + ky0,
                     ORIGIN_X + kx1, ORIGIN_Y + ky1),
        n_top=n_top, n_bottom=n_bottom, two_side=two_side,
        som_core=som_core)
    _led.close_step("pcb.placement")
    from .escape import build_escape_copper, build_escape_plan
    with _led.step("pcb.escape"):
        from .escape import CLR_HOLE_HOLE, CLR_HOLE_HOLE_RELIEF
        _led.calc("clr_hole_hole", CLR_HOLE_HOLE,
                  thermal_via_h2h=THERMAL_VIA_H2H,
                  relief=CLR_HOLE_HOLE_RELIEF)
        model.copper, model.escape_meta = build_escape_copper(model)
        model.escape_plan = build_escape_plan(model)
        _meta = model.escape_meta
        _led.calc("escape_coverage", _meta.get("worst_cover_mm", 0.0),
                  contacts=sum(len(v) for v
                               in _meta.get("coverage_mm", {}).values()),
                  worst_cover=_meta.get("worst_cover_mm", 0.0),
                  vias=sum(_meta.get("vias", {}).values()),
                  coverage=len(_meta.get("coverage_mm", {})))
    _trk.checkpoint("escape_copper", _page_snap())
    model.stage_moves = dict(_trk.moves)
    return model
