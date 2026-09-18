from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.core import sexpr
from schgen.core.config import CHAR_W, GRID
from schgen.core.model import Circuit
from schgen.core.symbols import Library, SymbolDef, pin_page_position
from schgen.layout import route
from schgen.layout import textmetrics as tm
from schgen.output.emit import HierLabel, LocalLabel, NoConnect, PlacedPart, PlacedPower
from schgen.verify import visual_gate
from schgen.verify.visual_gate import Box, Junction, SheetGeometry

U = GRID
NC_MARKER = 1.27
A4_CENTER = (148.59, 100.33)
A3_CENTER = (210.82, 148.59)
A3_TITLEBLOCK_LEFT = 300.0
A3_TITLEBLOCK_TOP = 252.9
TITLEBLOCK_MARGIN = 4.0
PAPER_H_BUDGET = 240.0
PAPER_W_BUDGET = 330.0

POWER_LIBS = {
    "+3V3": "power:+3V3",
    "+5V": "power:+5V",
    "+1V8": "power:+1V8",
    "GND": "power:GND",
    "VBUS": "power:VBUS",
    "+VIN": "schgen:+VIN",
    "CHASSIS_GND": "schgen:CHASSIS_GND",
    "+3V3_HDMI_TX": "schgen:+3V3_HDMI_TX",
    "+5V_HDMI_TX": "schgen:+5V_HDMI_TX",
    "+3V3_HDMI_RX": "schgen:+3V3_HDMI_RX",
    "+5V_USB": "schgen:+5V_USB",
    "+3V3_SD": "schgen:+3V3_SD",
    "+3V3_LCD": "schgen:+3V3_LCD",
    "+5V_LCD": "schgen:+5V_LCD",
    "+3V3_SC": "schgen:+3V3_SC",
    "+VCCO_13": "schgen:+VCCO_13",
    "+VCCO_33": "schgen:+VCCO_33",
    "+VCCO_34": "schgen:+VCCO_34",
    "+VCCO_35": "schgen:+VCCO_35",
}

_FLAG_DRIVER_ETYPES = {"power_out", "output"}


class PlaceError(ValueError):
    pass


def gsnap(v: float) -> float:
    if _nat.loaded():
        return _nat.module().gsnap(v, U)
    return round(round(v / U) * U, 3)


def gfloor(v: float) -> float:
    if _nat.loaded():
        return _nat.module().gfloor(v, U)
    return round(math.floor(v / U + 1e-6) * U, 3)


def gceil(v: float) -> float:
    if _nat.loaded():
        return _nat.module().gceil(v, U)
    return round(math.ceil(v / U - 1e-6) * U, 3)


def _farm_row_right_bound_py(ex0: float, ex1_flow: float, a3_center_x: float,
                             titleblock_left: float, titleblock_margin: float,
                             cap_pitch: float) -> float:
    flow_centre = (ex0 + ex1_flow) / 2.0
    dx = a3_center_x - flow_centre
    local_limit = (titleblock_left - titleblock_margin) - dx
    return local_limit - cap_pitch / 2.0


def _conn_port_columns_py(ys: list[float], row_pitch: float,
                          eps: float) -> list[str]:
    cols: list[str] = []
    prev_y = prev_col = None
    for y in ys:
        col = ("outer" if prev_y is not None
               and abs(y - prev_y - row_pitch) < eps
               and prev_col == "inner"
               else "inner")
        cols.append(col)
        prev_y, prev_col = y, col
    return cols


def _conn_cluster_groups_py(ys: list[float], row_pitch: float,
                            eps: float) -> list[list[int]]:
    groups: list[list[int]] = []
    for i, y in enumerate(ys):
        if groups and abs(y - ys[groups[-1][-1]] - row_pitch) < eps:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


@dataclass
class Spacing:
    port_run: float = 10.16
    label_tap_gap: float = 2.54
    hang_stub: float = 2.54
    stagger_extra: float = 1.27
    cap_pitch: float = 10.16
    cluster_dx: float = 38.10
    cluster_dy: float = 20.32
    flags_dy: float = 16.51
    flag_pitch: float = 10.16

    def expanded(self) -> Spacing:
        def up(v: float) -> float:
            return gceil(v * 1.25)
        return Spacing(port_run=up(self.port_run),
                       label_tap_gap=self.label_tap_gap,
                       hang_stub=self.hang_stub,
                       stagger_extra=up(self.stagger_extra),
                       cap_pitch=up(self.cap_pitch),
                       cluster_dx=up(self.cluster_dx),
                       cluster_dy=up(self.cluster_dy),
                       flags_dy=up(self.flags_dy),
                       flag_pitch=up(self.flag_pitch))


@dataclass
class Placement:
    parts: list[PlacedPart] = field(default_factory=list)
    powers: list[PlacedPower] = field(default_factory=list)
    hlabels: list[HierLabel] = field(default_factory=list)
    llabels: list[LocalLabel] = field(default_factory=list)
    no_connects: list[NoConnect] = field(default_factory=list)
    plans: dict[str, list[list[tuple[float, float]]]] = field(default_factory=dict)
    boxes: list[Box] = field(default_factory=list)
    label_bridged: set[str] = field(default_factory=set)
    paper: str = "A4"

    def plan(self, net: str, *pts: tuple[float, float]) -> None:
        self.plans.setdefault(net, []).append(
            [(round(p[0], 3), round(p[1], 3)) for p in pts])


def _xform_py(x: float, y: float, ax: float, ay: float,
              rot: int) -> tuple[float, float]:
    r = math.radians(rot % 360)
    c, s = round(math.cos(r)), round(math.sin(r))
    return (round(ax + x * c - y * s, 3), round(ay - x * s - y * c, 3))


def _xform(x: float, y: float, ax: float, ay: float,
           rot: int) -> tuple[float, float]:
    if _nat.loaded():
        got = tuple(_nat.module().sch_xform(x, y, ax, ay, rot))
        if _nat.trace():
            ref = _xform_py(x, y, ax, ay, rot)
            if got != ref:
                raise AssertionError(
                    f"native sch_xform DIVERGENCE: cpp={got} python={ref}")
        return got
    return _xform_py(x, y, ax, ay, rot)


def body_box_page(sdef: SymbolDef, ax: float, ay: float, rot: int,
                  kind: str, owner: str) -> Box:
    x0, y0, x1, y1 = sdef.body
    if _nat.loaded():
        got = tuple(_nat.module().body_box(x0, y0, x1, y1, ax, ay, rot))
        if _nat.trace():
            pts = [_xform_py(px, py, ax, ay, rot)
                   for px in (x0, x1) for py in (y0, y1)]
            ref = (min(p[0] for p in pts), min(p[1] for p in pts),
                   max(p[0] for p in pts), max(p[1] for p in pts))
            if got != ref:
                raise AssertionError(
                    f"native body_box DIVERGENCE: cpp={got} python={ref}")
        return Box(*got, kind, owner)
    pts = [_xform(px, py, ax, ay, rot)
           for px in (x0, x1) for py in (y0, y1)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return Box(min(xs), min(ys), max(xs), max(ys), kind, owner)


def _value_anchor(sdef: SymbolDef, ax: float, ay: float,
                  rot: int) -> tuple[float, float]:
    for prop in sexpr.find_all(sdef.raw, "property"):
        if len(prop) > 2 and prop[1] == "Value":
            at = sexpr.find(prop, "at") or [None, 0, 0]
            return _xform(float(at[1]), float(at[2]), ax, ay, rot)
    return (ax, ay - 3.556)


def _pin_text_boxes_py(sdef: SymbolDef, part: PlacedPart) -> list[Box]:
    out: list[Box] = []
    for pin in sdef.pins:
        if pin.hidden:
            continue
        tip = pin_page_position(pin, part.x, part.y, part.rotation)
        dx, dy = route._stem_dir(pin.rotation, part.rotation)
        root = (round(tip[0] + dx * pin.length, 3),
                round(tip[1] + dy * pin.length, 3))
        mid = ((tip[0] + root[0]) / 2, (tip[1] + root[1]) / 2)
        horiz = dy == 0
        if not sdef.pin_numbers_hidden and pin.number:
            w, h = tm.text_wh(pin.number)
            if horiz:
                out.append(Box(mid[0] - w / 2, tip[1] - 0.2 - h,
                               mid[0] + w / 2, tip[1] - 0.2,
                               "pin_number", part.ref))
            else:
                out.append(Box(tip[0] - 0.2 - h, mid[1] - w / 2,
                               tip[0] - 0.2, mid[1] + w / 2,
                               "pin_number", part.ref))
        if not sdef.pin_names_hidden and pin.name not in ("", "~"):
            w, h = tm.text_wh(pin.name)
            w += 0.5
            if dx > 0:
                out.append(Box(root[0] + 0.2, tip[1] - h / 2,
                               root[0] + 0.2 + w, tip[1] + h / 2,
                               "pin_name", part.ref))
            elif dx < 0:
                out.append(Box(root[0] - 0.2 - w, tip[1] - h / 2,
                               root[0] - 0.2, tip[1] + h / 2,
                               "pin_name", part.ref))
            elif dy > 0:
                out.append(Box(tip[0] - h / 2, root[1] + 0.2,
                               tip[0] + h / 2, root[1] + 0.2 + w,
                               "pin_name", part.ref))
            else:
                out.append(Box(tip[0] - h / 2, root[1] - 0.2 - w,
                               tip[0] + h / 2, root[1] - 0.2,
                               "pin_name", part.ref))
    return out


def _pin_text_boxes(sdef: SymbolDef, part: PlacedPart) -> list[Box]:
    if _nat.loaded():
        pins = [(p.x, p.y, int(p.rotation), p.length, bool(p.hidden),
                 p.number, p.name) for p in sdef.pins]
        got = [Box(x0, y0, x1, y1, kind, part.ref)
               for x0, y0, x1, y1, kind in _nat.module().pin_text_boxes(
                   pins, part.x, part.y, int(part.rotation),
                   bool(sdef.pin_numbers_hidden), bool(sdef.pin_names_hidden),
                   CHAR_W, tm.LINE_H, tm.SIZE)]
        if _nat.trace():
            ref = _pin_text_boxes_py(sdef, part)
            hit = [(b.x0, b.y0, b.x1, b.y1, b.kind, b.owner) for b in got]
            want = [(b.x0, b.y0, b.x1, b.y1, b.kind, b.owner) for b in ref]
            if hit != want:
                raise AssertionError(
                    "native pin_text_boxes DIVERGENCE: "
                    f"cpp={hit} python={want}")
        return got
    return _pin_text_boxes_py(sdef, part)




def _native_pages(c: Circuit, lib: Library, sp: Spacing,
                  max_attempts: int, mode: int):
    native = _nat.module()
    spacing = [sp.port_run, sp.label_tap_gap, sp.hang_stub, sp.stagger_extra,
               sp.cap_pitch, sp.cluster_dx, sp.cluster_dy, sp.flags_dy, sp.flag_pitch]
    try:
        raw = native.schematic_place(c.to_ir(), lib._native, spacing,
                                     max_attempts, mode)
    except native.SchematicPlaceError as exc:
        raise PlaceError(str(exc)) from exc
    except native.SymbolError as exc:
        from schgen.core.symbols import SymbolError
        raise SymbolError(str(exc)) from exc
    out = []
    for name, refs, data, segments, junctions in raw:
        page = c if name == c.name else c.subset(set(refs), page=int(name.rsplit(".", 1)[1]))
        pl = Placement(
            parts=[PlacedPart(*p) for p in data["parts"]],
            powers=[PlacedPower(*p) for p in data["powers"]],
            hlabels=[HierLabel(*p) for p in data["hlabels"]],
            llabels=[LocalLabel(*p) for p in data["llabels"]],
            no_connects=[NoConnect(*p) for p in data["no_connects"]],
            plans={net: [[tuple(p) for p in path] for path in paths]
                   for net, paths in data["plans"].items()},
            boxes=[Box(*b) for b in data["boxes"]],
            label_bridged=set(data["label_bridged"]), paper=data["paper"])
        routed = route.RoutedSheet([visual_gate.Seg(*s) for s in segments],
                                   [tuple(p) for p in junctions])
        geometry = SheetGeometry(boxes=list(pl.boxes), wires=list(routed.segs),
                                 junctions=[Junction(*p) for p in junctions])
        out.append((page, pl, routed, geometry))
    return out


def build(c: Circuit, lib: Library, sp: Spacing) -> Placement:
    return _native_pages(c, lib, sp, 8, 0)[0][1]


def place_and_route(c: Circuit, lib: Library, max_attempts: int = 8):
    return _native_pages(c, lib, Spacing(), max_attempts, 1)[0][1:]


def partition_pages(c: Circuit, lib: Library) -> list[Circuit]:
    pages = _nat.module().schematic_partition(c.to_ir(), lib._native)
    return [c if name == c.name else c.subset(set(refs), page=int(name.rsplit(".", 1)[1]))
            for name, refs in pages]


def paginate_and_route(c: Circuit, lib: Library, max_attempts: int = 8):
    return _native_pages(c, lib, Spacing(), max_attempts, 2)
