from __future__ import annotations

import math

from schgen.core import fallbacks as _fbk
from schgen.core import native as _nat
from schgen.core import sexpr
from schgen.core.sexpr import Sym, _from_tagged

from .constants import (
    _FOOTPRINT_ALIASES,
    _FOUR_LAYER,
    _INT_DESC,
    _SW_DESC,
    CLR_HOLE_SAMENET_PAD,
    CONN_MATING_FACE,
    GND_PLANE_CLEARANCE,
    GND_PLANE_EDGE_BACK,
    GND_PLANE_LAYER,
    ISO_VOID_MARGIN,
    ISO_VOID_VALUES,
    ORIGIN_X,
    ORIGIN_Y,
    POUR_CLEARANCE,
    THERMAL_COPPER,
    THERMAL_VIA_CLEAR,
    THERMAL_VIA_DRILL,
    THERMAL_VIA_EDGE,
    THERMAL_VIA_H2H,
    THERMAL_VIA_LATTICE_PITCH,
    THERMAL_VIA_SIZE,
    THERMAL_VIA_SPACING,
    ZONE_MIN_THICKNESS,
    PcbModel,
)
from .footprint import pad_half_size
from .turn import pad_half_extent, turn_point

COPPER_DECIMALS = 4
CORNER_DECIMALS = 3
VIA_DECIMALS = 3


def _flip_layer_token(name: str) -> str:
    if name.startswith("F."):
        return "B." + name[2:]
    if name.startswith("B."):
        return name
    return name


def _flip_to_bottom(node: list) -> None:
    for sub in node:
        if not isinstance(sub, list) or not sub:
            continue
        head = sub[0]
        if head in (Sym("layer"), Sym("layers")):
            for i in range(1, len(sub)):
                if isinstance(sub[i], str):
                    sub[i] = _flip_layer_token(sub[i])
        elif head == Sym("effects"):
            just = next((x for x in sub if isinstance(x, list) and x
                         and x[0] == Sym("justify")), None)
            if just is None:
                sub.append([Sym("justify"), Sym("mirror")])
            elif Sym("mirror") not in just:
                just.append(Sym("mirror"))
            _flip_to_bottom(sub)
        else:
            _flip_to_bottom(sub)


def _embed_footprint(inst, uid) -> list:
    mod = sexpr.loads(inst.mod_path.read_text())
    assert isinstance(mod, list) and mod and mod[0] == Sym("footprint")

    mod[1] = _FOOTPRINT_ALIASES.get(inst.footprint, inst.footprint)

    body = [x for x in mod
            if not (isinstance(x, list) and x and x[0] == Sym("at"))]
    at_node = [Sym("at"), inst.x, inst.y] + (
        [inst.rotation] if inst.rotation else [])
    out: list = []
    inserted = False
    for x in body:
        out.append(x)
        if (not inserted and isinstance(x, list) and x and x[0] == Sym("layer")):
            out.append(at_node)
            inserted = True
    if not inserted:
        out.insert(1, at_node)

    if inst.mirror:
        from .mirror import is_mirrored_path
        assert inst.side == "bottom" and is_mirrored_path(inst.mod_path), (
            f"{inst.ref}: mirror=True demands side=bottom + a .mirrored_fp "
            f"document (got side={inst.side!r}, mod={inst.mod_path}) — a "
            f"mirrored instance emitted any other way is chiral-wrong copper")
    if inst.side == "bottom":
        _flip_to_bottom(out)

    _set_or_add(out, [Sym("uuid"), uid(f"fp:{inst.ref}")])

    inherit = _thermal_via_nets(out, inst.pad_nets)

    pad_seq = 0
    prop_seq = 0
    for node in out:
        if not isinstance(node, list) or not node:
            continue
        head = node[0]
        if head == Sym("property") and len(node) > 2:
            if node[1] == "Reference":
                node[2] = inst.ref
                if (inst.value in CONN_MATING_FACE or inst.ref in _INT_DESC
                        or inst.ref in _SW_DESC or "TestPoint" in inst.footprint):
                    hb = next((x for x in node if isinstance(x, list) and x
                               and x[0] == Sym("hide")), None)
                    if hb is None:
                        node.insert(3, [Sym("hide"), Sym("yes")])
                    else:
                        hb[1] = Sym("yes")
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
            if inst.rotation:
                _rotate_pad(node, inst.rotation)
            _restamp_uuid(node, uid(f"fp:{inst.ref}:pad:{pad_seq}"))
            pad_seq += 1
        elif head in (Sym("fp_text"), Sym("fp_line"), Sym("fp_rect"),
                      Sym("fp_circle"), Sym("fp_arc"), Sym("fp_poly")):
            _restamp_uuid(node, uid(f"fp:{inst.ref}:gfx:{pad_seq}:{prop_seq}"))
    return out


def _rotate_pad(pad: list, fp_rot: float) -> None:
    at = next((x for x in pad
               if isinstance(x, list) and x and x[0] == Sym("at")), None)
    if at is None:
        return
    cur = float(at[3]) if len(at) > 3 else 0.0
    new = round((cur + fp_rot) % 360.0, 4)
    if len(at) > 3:
        at[3] = new
    else:
        at.append(new)


def _pad_geom(node: list) -> tuple[float, float, float, float] | None:
    at = sexpr.find(node, "at")
    size = sexpr.find(node, "size")
    if not (at and len(at) >= 3 and size and len(size) >= 3):
        return None
    hw, hh = pad_half_size(at, size)
    return float(at[1]), float(at[2]), hw, hh


def _thermal_via_nets(out: list, pad_nets: dict) -> dict[int, tuple[int, str]]:
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
            continue
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
    pad[:] = [x for x in pad
              if not (isinstance(x, list) and x and x[0] == Sym("net"))]
    if num <= 0:
        return
    net_node = [Sym("net"), num, name]
    for i, x in enumerate(pad):
        if isinstance(x, list) and x and x[0] == Sym("uuid"):
            pad.insert(i, net_node)
            return
    pad.append(net_node)


def _layers_node() -> list:
    node: list = [Sym("layers")]
    for idx, name, ltype, user in _FOUR_LAYER:
        entry = [idx, name, Sym(ltype)]
        if user is not None:
            entry.append(user)
        node.append(entry)
    return node


def _stackup_node() -> list:
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
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    if _nat.loaded():
        geom = _nat.module()
        return [_from_tagged(geom.emit_edge_line(
            pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
            uid(f"edge:{i}")))
                for i in range(4)]
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


def _som_body_silk(box: tuple[float, float, float, float], uid) -> list:
    x0, y0, x1, y1 = box
    out: list = []
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    geom = _nat.module() if _nat.loaded() else None
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        if geom is not None:
            out.append(_from_tagged(geom.emit_gr_line(
                round(ax, 3), round(ay, 3), round(bx, 3), round(by, 3),
                0.15, "F.SilkS", uid(f"som-silk:{i}"))))
            continue
        out.append([Sym("gr_line"),
                    [Sym("start"), round(ax, 3), round(ay, 3)],
                    [Sym("end"), round(bx, 3), round(by, 3)],
                    [Sym("stroke"), [Sym("width"), 0.15],
                     [Sym("type"), Sym("default")]],
                    [Sym("layer"), "F.SilkS"],
                    [Sym("uuid"), uid(f"som-silk:{i}")]])
    ch = 3.0
    if geom is not None:
        out.append(_from_tagged(geom.emit_gr_line(
            round(x0, 3), round(y0 + ch, 3), round(x0 + ch, 3), round(y0, 3),
            0.15, "F.SilkS", uid("som-silk:ch"))))
        out.append(_from_tagged(geom.emit_gr_text(
            "Zynq SoM", round(x0 + 1.0, 3), round(y0 - 1.2, 3), 0.0,
            "F.SilkS", uid("som-silk:label"), 1.4, 0.25, "left bottom")))
        return out
    out.append([Sym("gr_line"),
                [Sym("start"), round(x0, 3), round(y0 + ch, 3)],
                [Sym("end"), round(x0 + ch, 3), round(y0, 3)],
                [Sym("stroke"), [Sym("width"), 0.15],
                 [Sym("type"), Sym("default")]],
                [Sym("layer"), "F.SilkS"],
                [Sym("uuid"), uid("som-silk:ch")]])
    out.append([Sym("gr_text"), "Zynq SoM",
                [Sym("at"), round(x0 + 1.0, 3), round(y0 - 1.2, 3), 0],
                [Sym("layer"), "F.SilkS"],
                [Sym("uuid"), uid("som-silk:label")],
                [Sym("effects"),
                 [Sym("font"), [Sym("size"), 1.4, 1.4], [Sym("thickness"), 0.25]],
                 [Sym("justify"), Sym("left"), Sym("bottom")]]])
    return out


def _via_node(c: dict, uid, uid_key: str = "stitch-via") -> list:
    if _nat.loaded():
        return _from_tagged(_nat.module().emit_via(
            float(c["x"]), float(c["y"]), float(c["size"]), float(c["drill"]),
            float(c["net"]), uid(uid_key), bool(c.get("locked", True))))
    node = [Sym("via"),
            [Sym("at"), c["x"], c["y"]],
            [Sym("size"), c["size"]],
            [Sym("drill"), c["drill"]],
            [Sym("layers"), "F.Cu", "B.Cu"]]
    if c.get("locked", True):
        node.append([Sym("locked"), Sym("yes")])
    node.append([Sym("net"), c["net"]])
    node.append([Sym("uuid"), uid(uid_key)])
    return node


def _segment_node(c: dict, uid) -> list:
    if _nat.loaded():
        return _from_tagged(_nat.module().emit_segment(
            float(c["x1"]), float(c["y1"]), float(c["x2"]), float(c["y2"]),
            float(c["width"]), str(c["layer"]), float(c["net"]),
            uid("stitch-seg")))
    return [Sym("segment"),
            [Sym("start"), c["x1"], c["y1"]],
            [Sym("end"), c["x2"], c["y2"]],
            [Sym("width"), c["width"]],
            [Sym("layer"), c["layer"]],
            [Sym("locked"), Sym("yes")],
            [Sym("net"), c["net"]],
            [Sym("uuid"), uid("stitch-seg")]]


# Marker only — planes + fanout vias right beneath the connector stay legal.
def _som_keepout_zone(box: tuple[float, float, float, float], uid) -> list:
    x0, y0, x1, y1 = box
    corners = [(round(x0, 3), round(y0, 3)),
               (round(x1, 3), round(y0, 3)),
               (round(x1, 3), round(y1, 3)),
               (round(x0, 3), round(y1, 3))]
    if _nat.loaded():
        return _from_tagged(_nat.module().emit_keepout_zone(
            corners, uid("som-keepout"), "SoM_body_keepout"))
    pts = [Sym("pts")] + [[Sym("xy"), px, py] for px, py in corners]
    return [Sym("zone"),
            [Sym("net"), 0], [Sym("net_name"), ""],
            [Sym("layers"), "F.Cu", "B.Cu"],
            [Sym("uuid"), uid("som-keepout")],
            [Sym("name"), "SoM_body_keepout"],
            [Sym("hatch"), Sym("edge"), 0.5],
            [Sym("connect_pads"), [Sym("clearance"), 0]],
            [Sym("min_thickness"), 0.25],
            [Sym("keepout"),
             [Sym("tracks"), Sym("allowed")],
             [Sym("vias"), Sym("allowed")],
             [Sym("pads"), Sym("allowed")],
             [Sym("copperpour"), Sym("allowed")],
             [Sym("footprints"), Sym("allowed")]],
            [Sym("fill"), [Sym("thermal_gap"), 0.5],
             [Sym("thermal_bridge_width"), 0.5]],
            [Sym("polygon"), pts]]


def _corners_rot(rect: tuple[float, float, float, float], inst,
                 model: PcbModel) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = rect
    rot = inst.rotation or 0.0
    lo_x = ORIGIN_X + GND_PLANE_EDGE_BACK
    lo_y = ORIGIN_Y + GND_PLANE_EDGE_BACK
    hi_x = ORIGIN_X + model.board_w - GND_PLANE_EDGE_BACK
    hi_y = ORIGIN_Y + model.board_h - GND_PLANE_EDGE_BACK
    out: list[tuple[float, float]] = []
    for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        tx, ty = turn_point(px, py, rot)
        bx, by = inst.x + tx, inst.y + ty
        out.append((round(min(max(bx, lo_x), hi_x), CORNER_DECIMALS),
                    round(min(max(by, lo_y), hi_y), CORNER_DECIMALS)))
    return out


def _fill_zone(net_num: int, net_name: str, zname: str, layer: str,
               corners: list[tuple[float, float]], uid_key: str, uid,
               clearance: float, solid: bool) -> list:
    if _nat.loaded():
        return _from_tagged(_nat.module().emit_fill_zone(
            float(net_num), net_name, zname, layer, corners, uid(uid_key),
            clearance, solid, ZONE_MIN_THICKNESS))
    pts = [Sym("pts")] + [[Sym("xy"), px, py] for px, py in corners]
    connect = ([Sym("connect_pads"), Sym("yes"), [Sym("clearance"), clearance]]
               if solid else
               [Sym("connect_pads"), [Sym("clearance"), clearance]])
    return [Sym("zone"),
            [Sym("net"), net_num], [Sym("net_name"), net_name],
            [Sym("layer"), layer],
            [Sym("uuid"), uid(uid_key)],
            [Sym("name"), zname],
            [Sym("hatch"), Sym("edge"), 0.5],
            connect,
            [Sym("min_thickness"), ZONE_MIN_THICKNESS],
            [Sym("filled_areas_thickness"), Sym("no")],
            [Sym("fill"), Sym("yes"), [Sym("thermal_gap"), 0.5],
             [Sym("thermal_bridge_width"), 0.5]],
            [Sym("polygon"), pts]]


def _gnd_plane_zone(model: PcbModel, uid) -> list | None:
    num = model.net_numbers.get("GND")
    if not num:
        return None
    b = GND_PLANE_EDGE_BACK
    x0, y0 = round(ORIGIN_X + b, 3), round(ORIGIN_Y + b, 3)
    x1 = round(ORIGIN_X + model.board_w - b, 3)
    y1 = round(ORIGIN_Y + model.board_h - b, 3)
    return _fill_zone(num, "GND", "GND_plane_In1", GND_PLANE_LAYER,
                      [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                      "gnd-plane", uid, GND_PLANE_CLEARANCE, solid=False)


def _iso_void_zones(model: PcbModel, uid) -> list[list]:
    from .mating_face import _inst_courtyard
    out: list[list] = []
    for inst in model.insts:
        if not inst.value.startswith(ISO_VOID_VALUES):
            continue
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        m = ISO_VOID_MARGIN
        corners = [(round(cx0 - m, 3), round(cy0 - m, 3)),
                   (round(cx1 + m, 3), round(cy0 - m, 3)),
                   (round(cx1 + m, 3), round(cy1 + m, 3)),
                   (round(cx0 - m, 3), round(cy1 + m, 3))]
        pts = [Sym("pts")] + [[Sym("xy"), px, py] for px, py in corners]
        out.append([Sym("zone"),
                    [Sym("net"), 0], [Sym("net_name"), ""],
                    [Sym("layers"), GND_PLANE_LAYER],
                    [Sym("uuid"), uid(f"iso-void:{inst.ref}")],
                    [Sym("name"), f"ethernet_isolation_void_{inst.ref}"],
                    [Sym("hatch"), Sym("edge"), 0.5],
                    [Sym("connect_pads"), [Sym("clearance"), 0]],
                    [Sym("min_thickness"), ZONE_MIN_THICKNESS],
                    [Sym("keepout"),
                     [Sym("tracks"), Sym("allowed")],
                     [Sym("vias"), Sym("allowed")],
                     [Sym("pads"), Sym("allowed")],
                     [Sym("copperpour"), Sym("not_allowed")],
                     [Sym("footprints"), Sym("allowed")]],
                    [Sym("fill"), [Sym("thermal_gap"), 0.5],
                     [Sym("thermal_bridge_width"), 0.5]],
                    [Sym("polygon"), pts]])
    return out


_MOD_PAD_CACHE: dict[str, list[tuple[float, float, float, float, float, float]]] = {}


def _mod_pads(mod_path) -> list[tuple[str, float, float, float, float, float, float]]:
    key = str(mod_path)
    cached = _MOD_PAD_CACHE.get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    rows: list = []
    doc = sexpr.loads(mod_path.read_text())
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        name = str(node[1]) if len(node) > 1 else ""
        at = sexpr.find(node, "at")
        sz = sexpr.find(node, "size")
        if not (at and len(at) >= 3 and sz and len(sz) >= 3):
            continue
        prot = float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float)) \
            else 0.0
        dr = sexpr.find(node, "drill")
        drill = float(dr[1]) if dr and len(dr) > 1 and \
            isinstance(dr[1], (int, float)) else 0.0
        rows.append((name, float(at[1]), float(at[2]), prot,
                     float(sz[1]), float(sz[2]), drill))
    _MOD_PAD_CACHE[key] = rows
    return rows


def _pad_obstacles(inst) -> list[tuple[float, float, float, float, str, float, str]]:
    rot = inst.rotation or 0.0
    out: list[tuple[float, float, float, float, str, float, str]] = []
    for name, px, py, prot, sw, sh, drill in _mod_pads(inst.mod_path):
        tx, ty = turn_point(px, py, rot)
        hx, hy = pad_half_extent(sw, sh, rot + prot)
        nname = inst.pad_nets.get(name, (0, ""))[1]
        out.append((round(inst.x + tx, COPPER_DECIMALS),
                    round(inst.y + ty, COPPER_DECIMALS), hx, hy, nname, drill,
                    f"{inst.ref}.{name}"))
    return out


def _via_obstacles(model: PcbModel, inst, reach: float) \
        -> list[tuple[float, float, float, float, str, float, str]]:
    names = {num: nm for nm, num in model.net_numbers.items()}
    out: list[tuple[float, float, float, float, str, float, str]] = []
    for other in model.insts:
        if math.hypot(other.x - inst.x, other.y - inst.y) <= reach:
            out.extend(_pad_obstacles(other))
    for c in model.copper:
        if c.get("kind") != "via":
            continue
        cx, cy = float(c["x"]), float(c["y"])
        if math.hypot(cx - inst.x, cy - inst.y) > reach:
            continue
        vr = float(c.get("size", THERMAL_VIA_SIZE)) / 2
        out.append((round(cx, 4), round(cy, 4), vr, vr,
                    names.get(int(c.get("net", 0)), ""),
                    float(c.get("drill", THERMAL_VIA_DRILL)),
                    f"escape via @({cx:.3f},{cy:.3f})"))
    return out


def _via_site_blocker(vx: float, vy: float, model: PcbModel,
                      obstacles: list[tuple[float, float, float, float,
                                            str, float, str]],
                      chosen: list[tuple[float, float]]) -> str | None:
    if not (ORIGIN_X + THERMAL_VIA_EDGE <= vx
            <= ORIGIN_X + model.board_w - THERMAL_VIA_EDGE
            and ORIGIN_Y + THERMAL_VIA_EDGE <= vy
            <= ORIGIN_Y + model.board_h - THERMAL_VIA_EDGE):
        return "Edge.Cuts keep-back"
    vr = THERMAL_VIA_SIZE / 2
    hr = THERMAL_VIA_DRILL / 2
    for cx, cy, hx, hy, nname, drill, label in obstacles:
        dx = max(0.0, abs(vx - cx) - hx)
        dy = max(0.0, abs(vy - cy) - hy)
        gap = math.hypot(dx, dy)
        where = f"{label} [{nname or 'no-net'}] @({cx:.3f},{cy:.3f})"
        if nname != "GND" and gap < vr + THERMAL_VIA_CLEAR:
            return where
        if nname == "GND" and gap < hr + CLR_HOLE_SAMENET_PAD:
            return where
        if drill > 0 and math.hypot(vx - cx, vy - cy) < \
                hr + drill / 2 + THERMAL_VIA_H2H:
            return where
    for ox, oy in chosen:
        if math.hypot(vx - ox, vy - oy) < THERMAL_VIA_SPACING:
            return f"thermal via @({ox:.3f},{oy:.3f})"
    return None


def _fallback_via_sites(spec: dict) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = spec["pour"]
    m = THERMAL_VIA_SIZE / 2
    x0, y0, x1, y1 = x0 + m, y0 + m, x1 - m, y1 - m
    ranked: list[tuple[float, float, float]] = []
    for i in range(int((x1 - x0) / THERMAL_VIA_LATTICE_PITCH) + 1):
        for j in range(int((y1 - y0) / THERMAL_VIA_LATTICE_PITCH) + 1):
            sx = round(x0 + i * THERMAL_VIA_LATTICE_PITCH, 3)
            sy = round(y0 + j * THERMAL_VIA_LATTICE_PITCH, 3)
            ranked.append((round(math.hypot(sx, sy), 4), sy, sx))
    return [(sx, sy) for _r, sy, sx in sorted(ranked)]


def _pour_credit_need(value: str):
    from schgen.verify.thermal import POUR_EVIDENCE
    needs = [n for n in POUR_EVIDENCE.values()
             if value.startswith(n.value_prefix)]
    return max(needs, key=lambda n: (n.min_vias, n.radius_mm)) if needs else None


def _report_via_shortfall(inst, chosen: list[tuple[float, float]],
                          vetoes: dict[str, int], n_cand: int) -> str | None:
    need = _pour_credit_need(inst.value)
    if need is None:
        return None
    n_in = sum(1 for vx, vy in chosen
               if math.hypot(vx - inst.x, vy - inst.y) <= need.radius_mm)
    if n_in >= need.min_vias:
        return None
    top = sorted(vetoes.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
    line = (f"THERMAL VIA SHORTFALL: {inst.ref} ({inst.value}) at "
            f"({inst.x:.3f},{inst.y:.3f}) rot {inst.rotation:g} seated "
            f"{n_in}/{need.min_vias} GND vias within {need.radius_mm:g} mm; "
            f"{n_cand} candidate seats searched (curated + lattice), every "
            "other one blocked. Worst blockers: "
            + "; ".join(f"{obj} x{n}" for obj, n in top)
            + ". MOVE those parts (or this one): the thermal gate WITHHOLDS "
              "the pour credit on a short field.")
    print(line)
    return line


def _mirror_thermal_spec(spec: dict) -> dict:
    p = spec["pour"]
    return {**spec,
            "pour": (p[0], 0.0 - p[3], p[2], 0.0 - p[1]),
            "via_sites": [(sx, 0.0 - sy) for sx, sy in spec["via_sites"]]}


def _side_thermal_spec(spec: dict, side: str) -> dict:
    from schgen.verify.thermal import LAYER_SWAP
    if side != "bottom":
        return spec
    return {**spec, "pour_layers": tuple(LAYER_SWAP[la]
                                         for la in spec["pour_layers"])}


def _thermal_copper_nodes(model: PcbModel, uid) -> tuple[list[list], list[list]]:
    num = model.net_numbers.get("GND")
    if not num:
        return [], []
    zones: list[list] = []
    zone_geom: list[tuple[str, list[tuple[float, float]], list]] = []
    vias: list[list] = []
    placed: list[tuple[float, float]] = []
    for inst in model.insts:
        spec = next((s for pfx, s in THERMAL_COPPER.items()
                     if inst.value.startswith(pfx)), None)
        if spec is None:
            continue
        if inst.mirror:
            spec = _mirror_thermal_spec(spec)
        spec = _side_thermal_spec(spec, inst.side)
        corners = _corners_rot(spec["pour"], inst, model)
        for layer in spec["pour_layers"]:
            z = _fill_zone(
                num, "GND", f"thermal_pour_{inst.ref}_{layer.split('.')[0]}",
                layer, corners, f"thpour:{inst.ref}:{layer}", uid,
                POUR_CLEARANCE, solid=True)
            zones.append(z)
            zone_geom.append((layer, corners, z))
        reach = max(abs(v) for site in spec["via_sites"] for v in site) + 20.0
        obstacles = _via_obstacles(model, inst, reach)
        rot = inst.rotation or 0.0
        chosen: list[tuple[float, float]] = []
        vetoes: dict[str, int] = {}
        n_curated = len(spec["via_sites"])
        candidates = list(spec["via_sites"]) + _fallback_via_sites(spec)
        n_lattice = 0
        for ci, (sx, sy) in enumerate(candidates):
            if len(chosen) >= spec["max_vias"]:
                break
            tx, ty = turn_point(sx, sy, rot)
            vx = round(inst.x + tx, VIA_DECIMALS)
            vy = round(inst.y + ty, VIA_DECIMALS)
            veto = _via_site_blocker(vx, vy, model, obstacles, placed + chosen)
            if veto is None:
                chosen.append((vx, vy))
                if ci >= n_curated:
                    _fbk.record("thermal_via_lattice")
                    n_lattice += 1
            else:
                vetoes[veto] = vetoes.get(veto, 0) + 1
        if n_lattice:
            print(f"THERMAL VIA LATTICE: {inst.ref} ({inst.value}) seated "
                  f"{n_lattice}/{len(chosen)} via(s) from the exhaustive "
                  f"lattice — curated preferred site(s) blocked (registered "
                  f"fallback; drift from datasheet-preferred via geometry)")
        placed.extend(chosen)
        _report_via_shortfall(inst, chosen, vetoes, len(candidates))
        for i, (vx, vy) in enumerate(chosen):
            vias.append(_via_node(
                {"x": vx, "y": vy, "size": THERMAL_VIA_SIZE,
                 "drill": THERMAL_VIA_DRILL, "net": num, "locked": False},
                uid, uid_key=f"thvia:{inst.ref}:{i}"))
    _stagger_overlapping_pours(zone_geom)
    return zones, vias


def _quads_overlap_py(a: list[tuple[float, float]],
                      b: list[tuple[float, float]]) -> bool:
    for poly in (a, b):
        for i in range(len(poly)):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % len(poly)]
            nx, ny = y1 - y0, x0 - x1
            pa = [px * nx + py * ny for px, py in a]
            pb = [px * nx + py * ny for px, py in b]
            if max(pa) <= min(pb) + 1e-9 or max(pb) <= min(pa) + 1e-9:
                return False
    return True


def _quads_overlap(a: list[tuple[float, float]],
                   b: list[tuple[float, float]]) -> bool:
    if _nat.loaded():
        got = _nat.module().quads_overlap(a, b)
        if _nat.trace():
            ref = _quads_overlap_py(a, b)
            if got is not ref:
                raise AssertionError(
                    f"native quads_overlap DIVERGENCE: cpp={got} python={ref}")
        return got
    return _quads_overlap_py(a, b)


def _stagger_overlapping_pours(
        zone_geom: list[tuple[str, list[tuple[float, float]], list]]) -> None:
    by_layer: dict[str, list[tuple[list[tuple[float, float]], list]]] = {}
    for layer, corners, z in zone_geom:
        by_layer.setdefault(layer, []).append((corners, z))
    for members in by_layer.values():
        comp = list(range(len(members)))

        def find(i: int, comp: list[int] = comp) -> int:
            while comp[i] != i:
                comp[i] = comp[comp[i]]
                i = comp[i]
            return i

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if _quads_overlap(members[i][0], members[j][0]):
                    comp[find(i)] = find(j)
        ranks: dict[int, int] = {}
        for i, (_c, z) in enumerate(members):
            root = find(i)
            k = ranks.get(root, 0)
            ranks[root] = k + 1
            if k:
                hatch_at = next(idx for idx, node in enumerate(z)
                                if isinstance(node, list) and node
                                and node[0] == Sym("hatch"))
                z.insert(hatch_at + 1, [Sym("priority"), k])
