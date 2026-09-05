from __future__ import annotations

import itertools
import math
import os
import sys
from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.core import sexpr
from schgen.core.config import CHAR_W, GRID
from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library, Pin, SymbolDef, pin_page_position
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


def _pin(sdef: SymbolDef, number: str) -> Pin:
    for p in sdef.pins:
        if p.number == number:
            return p
    raise PlaceError(f"pin {number} not in {sdef.lib_id}")


_SIDE_OF_ROT = {0: "left", 180: "right", 270: "top", 90: "bottom"}


@dataclass
class _Line:
    net: str
    pin_pt: tuple[float, float]
    attach: str | None
    attach_div: tuple[str, str] | None = None
    net_class: NetClass = NetClass.PORT
    pin_etype: str = ""
    force_label: bool = False


@dataclass
class _FloatChain:
    kind: str
    root: str
    legs: list[tuple[str, str, str]]
    hangs: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class _Trunk:
    net: str
    zone: str = "below"
    direct: list = field(default_factory=list)
    rungs: list = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    chains: list[_FloatChain] = field(default_factory=list)
    nodes: list[float] = field(default_factory=list)
    y: float = 0.0


class _Engine:
    def __init__(self, c: Circuit, lib: Library, sp: Spacing) -> None:
        self.c = c
        self.lib = lib
        self.sp = sp
        self._pin2net: dict = {}
        for _n in self.c.nets.values():
            for _p in _n.pins:
                self._pin2net.setdefault(_p, _n)
        self.pl = Placement()
        self._pwr = 0
        self._flg = 0
        self._n_box_bucks = 0
        self._done: set[str] = set()
        self._pin_islets: set[str] = set()
        self._rung_islets: list[tuple[str, str, str]] = []
        self._sig_rows: list[float] = []
        self._rail_row_net: dict[float, str] = {}
        self._deferred_texts: list[tuple[PlacedPart, Box]] = []
        self.orient: dict[str, int] = {}
        self._classify()

    def _power_lib(self, net: str) -> str:
        try:
            return POWER_LIBS[net]
        except KeyError:
            if net.startswith("+"):
                return f"schgen:{net}"
            raise PlaceError(f"no power symbol mapped for rail {net!r}") from None

    def power(self, net: str, x: float, y: float, rot: int = 0,
              show_value: bool = True) -> PlacedPower:
        self._pwr += 1
        lib_id = self._power_lib(net)
        sdef = self.lib.get(lib_id)
        ref = f"#PWR{self._pwr:02d}"
        vp = _value_anchor(sdef, x, y, rot)
        if show_value:
            vp = self._dodge_value_off_nc(net, vp, x, y)
        pw = PlacedPower(lib_id, net, ref, x, y, rot, net=net,
                         val_pos=(vp[0], vp[1], 0), show_value=show_value)
        self.pl.powers.append(pw)
        self.pl.boxes.append(body_box_page(sdef, x, y, rot, "body", ref))
        if show_value:
            self.pl.boxes.append(Box(*tm.centered_box(net, vp[0], vp[1]),
                                     "value", ref))
        return pw

    def _dodge_value_off_nc(self, text: str, vp: tuple[float, float],
                            ax: float, ay: float) -> tuple[float, float]:
        ncs = list(self._nc_boxes())
        if _nat.loaded():
            got = tuple(_nat.module().dodge_value_off_nc(
                text, vp[0], vp[1], ax, ay, U, CHAR_W, tm.LINE_H, tm.SIZE,
                ncs, 0.2))
            if _nat.trace():
                ref = self._dodge_value_off_nc_py(text, vp, ax, ay, ncs)
                if got != ref:
                    raise AssertionError(
                        "native dodge_value_off_nc DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        return self._dodge_value_off_nc_py(text, vp, ax, ay, ncs)

    def _dodge_value_off_nc_py(self, text: str, vp: tuple[float, float],
                               ax: float, ay: float, ncs) -> tuple[float, float]:
        def hits_nc(px: float, py: float) -> bool:
            bx = tm.centered_box_py(text, px, py)
            for (nx0, ny0, nx1, ny1) in ncs:
                if bx[0] - 0.2 < nx1 and bx[2] + 0.2 > nx0 \
                        and bx[1] - 0.2 < ny1 and bx[3] + 0.2 > ny0:
                    return True
            return False
        if not hits_nc(vp[0], vp[1]):
            return vp
        dx, dy = vp[0] - ax, vp[1] - ay
        if abs(dy) >= abs(dx):
            step = (0.0, U if dy >= 0 else -U)
        else:
            step = (U if dx >= 0 else -U, 0.0)
        px, py = vp
        for _k in range(8):
            px, py = round(px + step[0], 3), round(py + step[1], 3)
            if not hits_nc(px, py):
                return (px, py)
        return vp

    def flag(self, net: str, x: float, y: float, rot: int) -> PlacedPower:
        self._flg += 1
        sdef = self.lib.get("power:PWR_FLAG")
        ref = f"#FLG{self._flg:02d}"
        pw = PlacedPower("power:PWR_FLAG", "PWR_FLAG", ref, x, y, rot, net=net)
        self.pl.powers.append(pw)
        self.pl.boxes.append(body_box_page(sdef, x, y, rot, "body", ref))
        return pw

    def passive(self, ref: str, x: float, y: float, rot: int,
                text_side: str = "right") -> None:
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        body = body_box_page(sdef, x, y, rot, "body", ref)
        w_ref, _ = tm.text_wh(ref)
        w_val, _ = tm.text_wh(part.value)
        if text_side == "right":
            cx_ref = body.x1 + 0.42 + w_ref / 2
            cx_val = body.x1 + 0.42 + w_val / 2
        else:
            cx_ref = body.x0 - 0.42 - w_ref / 2
            cx_val = body.x0 - 0.42 - w_val / 2
        ta = 90 if rot % 180 == 90 else 0
        rp = (cx_ref, y - 1.27, ta)
        vp = (cx_val, y + 1.27, ta)
        self.pl.parts.append(PlacedPart(ref, part.lib_id, part.value, x, y, rot,
                                        part.footprint, ref_pos=rp, val_pos=vp))
        self.pl.boxes.append(body)
        self.pl.boxes.append(Box(*tm.centered_box(ref, rp[0], rp[1]),
                                 "reference", ref))
        self.pl.boxes.append(Box(*tm.centered_box(part.value, vp[0], vp[1]),
                                 "value", ref))
        self._done.add(ref)

    def label(self, net: str, x: float, y: float, rot: int,
              shape: str = "bidirectional") -> None:
        x, y = round(x, 3), round(y, 3)
        self.pl.hlabels.append(HierLabel(net, x, y, rot, shape=shape))
        self.pl.boxes.append(Box(*tm.glabel_box(net, x, y, rot),
                                 "label", f"label:{net}"))

    def llabel(self, net: str, x: float, y: float, rot: int = 0) -> None:
        x, y = round(x, 3), round(y, 3)
        self.pl.llabels.append(LocalLabel(net, x, y, rot))
        self.pl.boxes.append(Box(*tm.llabel_box(net, x, y, rot),
                                 "label", f"label:{net}"))

    def net_of(self, ref: str, pin: str):
        return self._pin2net.get(PinRef(ref, pin))

    def other_pin(self, ref: str, pin: str) -> str:
        pins = sorted(self.lib.pin_numbers(self.c.parts[ref].lib_id))
        others = [p for p in pins if p != pin]
        if len(others) != 1:
            raise PlaceError(f"{ref} is not a 2-pin part")
        return others[0]

    def _pin_of_net(self, ref: str, net: str) -> str:
        for p in sorted(self.lib.pin_numbers(self.c.parts[ref].lib_id)):
            n = self.net_of(ref, p)
            if n is not None and n.name == net:
                return p
        raise PlaceError(f"{ref}: no pin on net {net!r}")

    def _plan_seg_boxes(self):
        for paths in self.pl.plans.values():
            for path in paths:
                for a, b in zip(path, path[1:], strict=False):
                    x0, x1 = sorted((a[0], b[0]))
                    y0, y1 = sorted((a[1], b[1]))
                    yield (x0 - 0.127, y0 - 0.127, x1 + 0.127, y1 + 0.127)

    def _nc_boxes(self):
        h = NC_MARKER / 2
        for nc in self.pl.no_connects:
            yield (nc.x - h, nc.y - h, nc.x + h, nc.y + h)

    def _spot_free(self, bx: tuple[float, float, float, float],
                   pad: float = 0.25) -> bool:
        if _nat.loaded():
            parts = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
            segs = list(self._plan_seg_boxes())
            ncs = list(self._nc_boxes())
            return _nat.module().spot_free(bx, pad, parts, segs, ncs)
        x0, y0, x1, y1 = bx
        for b in self.pl.boxes:
            if x0 - pad < b.x1 and x1 + pad > b.x0 \
                    and y0 - pad < b.y1 and y1 + pad > b.y0:
                return False
        for (sx0, sy0, sx1, sy1) in self._plan_seg_boxes():
            if x0 < sx1 and x1 > sx0 and y0 < sy1 and y1 > sy0:
                return False
        for (nx0, ny0, nx1, ny1) in self._nc_boxes():
            if x0 - pad < nx1 and x1 + pad > nx0 \
                    and y0 - pad < ny1 and y1 + pad > ny0:
                return False
        return True

    def _extent(self) -> tuple[float, float, float, float]:
        boxes = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
        pts = [p for paths in self.pl.plans.values() for path in paths
               for p in path]
        if _nat.loaded():
            got = tuple(_nat.module().boxes_paths_extent(boxes, pts))
            if _nat.trace():
                ref = self._extent_py(boxes, pts)
                if got != ref:
                    raise AssertionError(
                        "native boxes_paths_extent DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        return self._extent_py(boxes, pts)

    def _extent_py(self, boxes, pts) -> tuple[float, float, float, float]:
        xs = [v for b in boxes for v in (b[0], b[2])]
        ys = [v for b in boxes for v in (b[1], b[3])]
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def _band_edge(self, y0: float, y1: float, side: int,
                   default: float) -> float:
        boxes = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
        segs = list(self._plan_seg_boxes())
        if _nat.loaded():
            got = _nat.module().band_edge(y0, y1, side, default, boxes, segs)
            if _nat.trace():
                ref = self._band_edge_py(y0, y1, side, default, boxes, segs)
                if got != ref:
                    raise AssertionError(
                        "native band_edge DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        return self._band_edge_py(y0, y1, side, default, boxes, segs)

    def _band_edge_py(self, y0: float, y1: float, side: int, default: float,
                      boxes, segs) -> float:
        edge = default
        for b in boxes:
            if b[1] < y1 and b[3] > y0:
                edge = min(edge, b[0]) if side < 0 else max(edge, b[2])
        for (sx0, sy0, sx1, sy1) in segs:
            if sy0 < y1 and sy1 > y0:
                edge = min(edge, sx0) if side < 0 else max(edge, sx1)
        return edge

    def _classify(self) -> None:
        c, lib = self.c, self.lib
        self.multi = [r for r, p in c.parts.items()
                      if len(lib.pin_numbers(p.lib_id)) > 2]
        mset = set(self.multi)
        self.multi_nets = {n.name for n in c.nets.values()
                           if any(pr.ref in mset for pr in n.pins)}
        self.cluster: dict[str, list[str]] = {}
        self.pull: dict[str, list[tuple[str, str]]] = {}
        self.hang: dict[str, list[str]] = {}
        self.series: list[tuple[str, str, str]] = []
        for ref, part in c.parts.items():
            if ref in mset:
                continue
            pins = sorted(lib.pin_numbers(part.lib_id))
            if len(pins) != 2:
                raise PlaceError(f"{ref}: {len(pins)}-pin part is neither a "
                                 f"multi-pin part nor a 2-pin passive")
            n1, n2 = self.net_of(ref, pins[0]), self.net_of(ref, pins[1])
            if n1 is None or n2 is None:
                raise PlaceError(f"{ref}: unnetted passive")
            cls = {n1.net_class, n2.net_class}
            if cls == {NetClass.POWER, NetClass.GROUND}:
                rail = n1.name if n1.net_class == NetClass.POWER else n2.name
                self.cluster.setdefault(rail, []).append(ref)
            elif NetClass.POWER in cls:
                sig = n1 if n2.net_class == NetClass.POWER else n2
                rail = n2 if n2.net_class == NetClass.POWER else n1
                self.pull.setdefault(sig.name, []).append((ref, rail.name))
            elif NetClass.GROUND in cls:
                sig = n1 if n2.net_class == NetClass.GROUND else n2
                self.hang.setdefault(sig.name, []).append(ref)
            else:
                self.series.append((ref, n1.name, n2.name))
        self.trunks: dict[str, _Trunk] = {}
        for n in c.nets.values():
            mp = {pr.ref for pr in n.pins if pr.ref in mset}
            if n.net_class is NetClass.SIGNAL:
                if len(n.pins) >= 4 or c.hints.get(n.name) == "trunk" \
                        or (len(n.pins) >= 3 and len(mp) >= 2):
                    self.trunks[n.name] = _Trunk(net=n.name)
            elif n.net_class is NetClass.PORT:
                if len(n.pins) >= 4 and len(mp) >= 2:
                    self.trunks[n.name] = _Trunk(net=n.name)
        self.shunts: list[str] = []
        for ref in self.multi:
            sdef = lib.get(c.parts[ref].lib_id)
            pin_nets = [self.net_of(ref, p.number) for p in sdef.pins]
            sig_pins = [p for p, n in zip(sdef.pins, pin_nets, strict=False)
                        if n is not None
                        and n.net_class in (NetClass.SIGNAL, NetClass.PORT)]
            has_gnd = any(n is not None and n.net_class is NetClass.GROUND
                          for n in pin_nets)
            has_power = any(n is not None and n.net_class is NetClass.POWER
                            for n in pin_nets)
            is_clamp = (ref[0] != "J"
                        and bool(sig_pins)
                        and all(p.etype == "passive" for p in sig_pins)
                        and has_gnd
                        and not has_power)
            thresh = 1 if is_clamp else 2
            sig = [n for n in c.nets.values()
                   if n.net_class in (NetClass.SIGNAL, NetClass.PORT)
                   and any(pr.ref == ref for pr in n.pins)]
            if sig and all(
                    len({pr.ref for pr in n.pins
                         if pr.ref in mset and pr.ref != ref}) >= thresh
                    for n in sig):
                self.shunts.append(ref)
        self._extract_float_chains()

    def _extract_float_chains(self) -> None:
        c = self.c
        floating = {n.name for n in c.nets.values()
                    if n.net_class in (NetClass.SIGNAL, NetClass.PORT)
                    and n.name not in self.multi_nets
                    and n.name not in self.trunks}
        legs: dict[str, list[tuple[str, str, str]]] = {f: [] for f in floating}

        def kind_of(net: str) -> str:
            cls = c.nets[net].net_class
            if cls is NetClass.POWER:
                return "rail"
            if cls is NetClass.GROUND:
                return "gnd"
            if net in self.trunks:
                return "trunk"
            if net in floating:
                return "float"
            return "pin"

        for sig, pulls in self.pull.items():
            if sig in floating:
                for ref, rail in pulls:
                    legs[sig].append((ref, rail, "rail"))
        for sig, hangs in self.hang.items():
            if sig in floating:
                for ref in hangs:
                    pins = sorted(self.lib.pin_numbers(c.parts[ref].lib_id))
                    far = next(n.name for p in pins
                               if (n := self.net_of(ref, p)) is not None
                               and n.name != sig)
                    legs[sig].append((ref, far, "gnd"))
        for ref, a, b in self.series:
            if a in floating:
                legs[a].append((ref, b, kind_of(b)))
            if b in floating:
                legs[b].append((ref, a, kind_of(a)))

        self.float_chains: list[_FloatChain] = []
        seen: set[str] = set()
        for f in sorted(floating):
            if f in seen or not legs[f]:
                continue
            comp = {f}
            todo = [f]
            while todo:
                cur = todo.pop()
                for _, far, fk in legs[cur]:
                    if fk == "float" and far not in comp:
                        comp.add(far)
                        todo.append(far)
            seen |= comp
            if (len(comp) == 1
                    and self.c.nets[f].net_class is NetClass.PORT
                    and len(legs[f]) == 1 and legs[f][0][2] == "pin"):
                continue
            self.float_chains.append(self._linearise(comp, legs))
        used_refs = {ref for ch in self.float_chains
                     for ref, _u, _l in ch.legs} | \
                    {r for ch in self.float_chains
                     for refs in ch.hangs.values() for r in refs}
        for k in list(self.pull):
            self.pull[k] = [t for t in self.pull[k] if t[0] not in used_refs]
            if not self.pull[k]:
                del self.pull[k]
        for k in list(self.hang):
            self.hang[k] = [r for r in self.hang[k] if r not in used_refs]
            if not self.hang[k]:
                del self.hang[k]
        self.series = [s for s in self.series if s[0] not in used_refs]

    def _linearise(self, comp: set[str],
                   legs: dict[str, list[tuple[str, str, str]]]) -> _FloatChain:
        ends: list[tuple[str, str, str, str]] = []
        for n in sorted(comp):
            for ref, far, fk in legs[n]:
                if fk != "float":
                    ends.append((ref, n, far, fk))
        order = {"trunk": 0, "pin": 1, "rail": 2, "gnd": 3}
        ends.sort(key=lambda e: order[e[3]])
        if not ends:
            raise PlaceError(f"floating nets {sorted(comp)}: no rail/pin end")
        top = ends[0]
        def is_cap(ref: str) -> bool:
            return self.c.parts[ref].lib_id.endswith(":C")
        bottoms = [e for e in ends[1:]]
        bottoms.sort(key=lambda e: (order[e[3]] != 3, is_cap(e[0])))
        if not bottoms:
            return self._linearise_port_strap(comp, legs, ends)
        used = {top[0]}
        chain_legs: list[tuple[str, str, str]] = [(top[0], top[2], top[1])]
        cur = top[1]
        hangs: dict[str, list[str]] = {}
        while True:
            nxt = [(ref, far, fk) for ref, far, fk in legs[cur]
                   if ref not in used and fk == "float"]
            if nxt:
                ref, far, _ = nxt[0]
                used.add(ref)
                chain_legs.append((ref, cur, far))
                cur = far
                continue
            tails = [e for e in bottoms if e[1] == cur and e[0] not in used]
            if not tails:
                raise PlaceError(f"floating nets {sorted(comp)}: cannot close "
                                 f"chain at {cur!r}")
            ref, n, far, fk = tails[0]
            used.add(ref)
            chain_legs.append((ref, cur, far))
            break
        for n in sorted(comp):
            for ref, _far, fk in legs[n]:
                if ref in used:
                    continue
                if fk == "gnd":
                    hangs.setdefault(n, []).append(ref)
                    used.add(ref)
                else:
                    raise PlaceError(f"{ref}: unsupported extra leg on "
                                     f"floating net {n!r} ({fk})")
        kind = {"trunk": "trunk", "pin": "pin", "rail": "rail"}[top[3]]
        ch = _FloatChain(kind=kind, root=top[2], legs=chain_legs, hangs=hangs)
        if kind == "trunk":
            self.trunks[top[2]].chains.append(ch)
        return ch

    def _linearise_port_strap(self, comp: set[str],
                              legs: dict[str, list[tuple[str, str, str]]],
                              ends: list[tuple[str, str, str, str]]
                              ) -> _FloatChain:
        if len(ends) != 1 or ends[0][3] not in ("rail", "gnd"):
            raise PlaceError(f"floating nets {sorted(comp)}: single-ended "
                             f"chain without a rail/GND end")
        end_ref, end_net, end_far, _end_kind = ends[0]
        used = {end_ref}
        rev: list[tuple[str, str, str]] = [(end_ref, end_net, end_far)]
        cur = end_net
        while True:
            nxt = [(ref, far) for ref, far, fk in legs[cur]
                   if ref not in used and fk == "float"]
            if not nxt:
                break
            ref, far = nxt[0]
            used.add(ref)
            rev.append((ref, far, cur))
            cur = far
        root = cur
        if self.c.nets[root].net_class is not NetClass.PORT:
            raise PlaceError(f"floating nets {sorted(comp)}: single-ended "
                             f"chain tops out on non-PORT net {root!r} — "
                             f"dangling internal net")
        hangs: dict[str, list[str]] = {}
        for n in sorted(comp):
            for ref, _far, fk in legs[n]:
                if ref in used:
                    continue
                if fk == "gnd":
                    hangs.setdefault(n, []).append(ref)
                    used.add(ref)
                else:
                    raise PlaceError(f"{ref}: unsupported extra leg on "
                                     f"floating net {n!r} ({fk})")
        return _FloatChain(kind="port", root=root,
                           legs=list(reversed(rev)), hangs=hangs)

    def _vertical_2pin(self, ref: str, x: float, y_attach: float,
                       attach_net: str, downward: bool,
                       text_side: str = "right") -> tuple[tuple[float, float], str]:
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        att_no = self._pin_of_net(ref, attach_net)
        far_no = self.other_pin(ref, att_no)
        far_net = self.net_of(ref, far_no)
        assert far_net is not None
        p_att = _pin(sdef, att_no)
        if abs(p_att.y) > 1e-6:
            off = abs(p_att.y)
            up = p_att.y > 0
            rot = (0 if up else 180) if downward else (180 if up else 0)
        else:
            off = abs(p_att.x)
            right = p_att.x > 0
            rot = (90 if right else 270) if downward else (270 if right else 90)
        anchor_y = y_attach + off if downward else y_attach - off
        self.passive(ref, x, anchor_y, rot, text_side=text_side)
        far_y = anchor_y + off if downward else anchor_y - off
        return (x, round(far_y, 3)), far_net.name

    def _horizontal_2pin(self, ref: str, x: float, y: float,
                         left_net: str, text_side: str = "right") -> None:
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        left_no = self._pin_of_net(ref, left_net)
        p_left = _pin(sdef, left_no)
        if abs(p_left.y) > 1e-6:
            rot = 90 if p_left.y > 0 else 270
        else:
            rot = 0 if p_left.x < 0 else 180
        self.passive(ref, x, y, rot, text_side=text_side)

    def _place_body(self, ref: str, ax: float, ay: float):
        part = self.c.parts[ref]
        rot = self.orient.get(ref, 0)
        sdef = self.lib.get(part.lib_id)
        body = body_box_page(sdef, ax, ay, rot, "body", ref)
        pp = PlacedPart(ref, part.lib_id, part.value, ax, ay, rot,
                        part.footprint, ref_pos=None, val_pos=None)
        self.pl.parts.append(pp)
        self.pl.boxes.append(body)
        self.pl.boxes.extend(_pin_text_boxes(sdef, pp))
        sides: dict[str, list[tuple[Pin, tuple[float, float]]]] = {
            "left": [], "right": [], "top": [], "bottom": []}
        seen_pts: set[tuple[float, float]] = set()
        for pin in sdef.pins:
            if pin.hidden:
                continue
            pt = pin_page_position(pin, ax, ay, rot)
            if pt in seen_pts:
                continue
            seen_pts.add(pt)
            sides[_SIDE_OF_ROT[(pin.rotation + rot) % 360]].append((pin, pt))
        self._done.add(ref)
        return pp, sdef, body, sides

    def _part_texts(self, pp: PlacedPart, body: Box) -> None:
        for kind, text in (("reference", pp.ref), ("value", pp.value)):
            w, h = tm.text_wh(text)
            above = body.y0 - 1.905
            below = body.y1 + 2.03
            ax = pp.x
            cands: list[tuple[float, float]] = []
            xs = (body.x1 - 2.54, ax + 7.62, body.x0 + 2.54, ax,
                  ax - 7.62, ax + 12.7, ax - 12.7)
            rows = range(6)
            if kind == "reference":
                for j in rows:
                    cands += [(cx, above - j * 2.54) for cx in xs]
                for j in rows:
                    cands += [(cx, below + j * 2.54) for cx in xs]
            else:
                for j in rows:
                    cands += [(cx, below + j * 2.54) for cx in xs]
                for j in rows:
                    cands += [(cx, above - j * 2.54) for cx in xs]
            for j in (0, 1, 2):
                cands.append((body.x1 + 0.8 + w / 2, pp.y + j * 2.54))
                cands.append((body.x0 - 0.8 - w / 2, pp.y + j * 2.54))
            pos = None
            for cx, cy in cands:
                bx = tm.centered_box(text, cx, cy)
                if self._spot_free(bx):
                    pos = (cx, cy, 0)
                    break
            if pos is None:
                pos = (ax, below + 18 * 2.54, 0)
            if kind == "reference":
                pp.ref_pos = pos
            else:
                pp.val_pos = pos
            self.pl.boxes.append(Box(*tm.centered_box(text, pos[0], pos[1]),
                                     kind, pp.ref))

    def _fan_side(self, ref: str, side: str,
                  items: list[tuple[Pin, tuple[float, float]]],
                  handled: set[tuple[str, str, str]]) -> None:
        sp = self.sp
        sgn = -1 if side == "left" else 1
        boxes_mark = len(self.pl.boxes)
        plans_mark = {n: len(ps) for n, ps in self.pl.plans.items()}
        rows_all = [pt for _pin, pt in items]
        items_all = list(items)
        handled_rows = [pt[1] for pin, pt in items
                        if (ref, pin.number, side) in handled]
        items = [(pin, pt) for pin, pt in items
                 if (ref, pin.number, side) not in handled]
        lines: list[_Line] = []
        runs: list[list[tuple[Pin, tuple[float, float], object]]] = []
        for pin, pt in sorted(items, key=lambda t: t[1][1]):
            net = self.net_of(ref, pin.number)
            is_rail = net is not None and net.net_class in (
                NetClass.POWER, NetClass.GROUND)
            prev = runs[-1][-1][2] if runs else None
            prev_pt = runs[-1][-1][1] if runs else None
            adjacent = (prev_pt is not None
                        and abs(pt[1] - prev_pt[1] - 2.54) < 1e-6)
            if (net is not None and prev is not None
                    and getattr(prev, "name", None) == net.name
                    and (is_rail or adjacent)):
                runs[-1].append((pin, pt, net))
            else:
                runs.append([(pin, pt, net)])
        rail_run_count: dict[str, int] = {}
        for run in runs:
            n0 = run[0][2]
            if n0 is not None and n0.net_class in (NetClass.POWER,
                                                   NetClass.GROUND):
                rail_run_count[n0.name] = rail_run_count.get(n0.name, 0) + 1
        comb_net: str | None = None
        if rail_run_count:
            best = max(sorted(rail_run_count),
                       key=lambda n: rail_run_count[n])
            if rail_run_count[best] >= 6:
                comb_net = best
        handled_sig_rows = {round(pt[1], 3) for pin, pt in items_all
                            if (ref, pin.number, side) in handled
                            and (n := self.net_of(ref, pin.number)) is not None
                            and n.net_class in (NetClass.SIGNAL, NetClass.PORT)}
        self._sig_rows = sorted({round(pt[1], 3) for run in runs
                                 for _p, pt, n in run if n is not None
                                 and n.net_class in (NetClass.SIGNAL,
                                                     NetClass.PORT)}
                                | handled_sig_rows)
        self._rail_row_net = {round(pt[1], 3): n.name
                              for run in runs
                              for _p, pt, n in run if n is not None
                              and n.net_class in (NetClass.POWER,
                                                  NetClass.GROUND)}
        comb_pts: list[tuple[float, float]] = []
        rail_jobs: list[list] = []
        for run in runs:
            net0 = run[0][2]
            if net0 is None:
                for _, pt, _ in run:
                    self.pl.no_connects.append(NoConnect(*pt))
                continue
            if net0.net_class in (NetClass.POWER, NetClass.GROUND):
                if net0.name == comb_net:
                    comb_pts.extend(pt for _, pt, _ in run)
                elif comb_net is not None:
                    rail_jobs.append(run)
                else:
                    self._fan_rail_run(run, sgn, rows_all)
                continue
            for (_pa, pa, _na), (_pb, pb, _nb) in zip(run, run[1:], strict=False):
                self.pl.plan(net0.name, pa, pb)
            pin0, pt0, _ = run[0]
            if net0.net_class is NetClass.SIGNAL and len(run) > 1 \
                    and {(pr.ref, pr.pin) for pr in net0.pins} <= {
                        (ref, p.number) for p, _pt, _n in run}:
                continue
            attach = attach_div = None
            force_label = False
            pulls = self.pull.get(net0.name, [])
            hangs = self.hang.get(net0.name, [])
            if (net0.net_class is NetClass.SIGNAL
                    and self._net_shared(net0.name, ref)
                    and (net0.name not in self.trunks
                         or ref in self.shunts)):
                pulls = []
            if comb_net is not None and (pulls or hangs):
                pulls, hangs = [], []
                force_label = True
            if pulls and hangs:
                if len(pulls) > 1 or len(hangs) > 1:
                    raise PlaceError(f"net {net0.name}: multi-element "
                                     f"divider — extend the engine")
                attach_div = (pulls[0][0], hangs[0])
                del self.pull[net0.name]
                del self.hang[net0.name]
            elif pulls:
                if len(pulls) > 1:
                    raise PlaceError(f"net {net0.name}: multiple pull-ups "
                                     f"— extend the engine")
                attach = pulls[0][0]
                del self.pull[net0.name]
            elif hangs:
                if len(hangs) > 1:
                    raise PlaceError(f"net {net0.name}: multiple filter "
                                     f"caps — extend the engine")
                attach = hangs[0]
                del self.hang[net0.name]
            lines.append(_Line(net0.name, pt0, attach, attach_div,
                               net0.net_class, pin0.etype, force_label))
        if not lines:
            for run in rail_jobs:
                self._fan_rail_run(run, sgn, rows_all)
            if comb_pts:
                self._fan_rail_comb(comb_net, comb_pts, sgn,
                                    boxes_mark, plans_mark)
            return
        hang_sgn = -1 if side == "left" else 1
        attach_rows = [ln.pin_pt[1] for ln in lines if ln.attach]
        side_rows = [pt[1] for pt in rows_all]
        if attach_rows and len(side_rows) > 1:
            veto_up = any(r < min(attach_rows) - 1e-6 for r in handled_rows)
            veto_dn = any(r > max(attach_rows) + 1e-6 for r in handled_rows)
            d_top = min(attach_rows) - min(side_rows)
            d_bot = max(side_rows) - max(attach_rows)
            cands_h = sorted(((veto_up, d_top, -1), (veto_dn, d_bot, 1)))
            hang_sgn = cands_h[0][2]
        lines.sort(key=lambda ln: ln.pin_pt[1], reverse=(hang_sgn > 0))
        if attach_rows:
            rank_row = min(attach_rows) if hang_sgn < 0 else max(attach_rows)
            rank_pin_y = rank_row + hang_sgn * sp.hang_stub
        else:
            rank_pin_y = lines[0].pin_pt[1] + hang_sgn * sp.hang_stub
        def label_len(ln: _Line) -> float:
            if ln.net_class is NetClass.PORT:
                return self._glabel_len(ln.net)
            return tm.text_wh(ln.net)[0] + 0.7

        def is_labeled(ln: _Line) -> bool:
            if ln.force_label or ln.net_class is NetClass.PORT:
                return True
            return (ln.net_class is NetClass.SIGNAL
                    and self._net_shared(ln.net, ref)
                    and (ln.net not in self.trunks or ref in self.shunts)
                    and self._series_of(ln.net) is None)

        label_clash_dy = tm.GLABEL_H * tm.SIZE + 0.5
        cols: dict[int, str] = {}
        prev_cy = prev_col = None
        for idx, ln in enumerate(lines):
            if not is_labeled(ln) or ln.attach or ln.attach_div:
                prev_cy = prev_col = None
                continue
            col = ("outer" if prev_cy is not None
                   and abs(ln.pin_pt[1] - prev_cy) < label_clash_dy
                   and prev_col == "inner" else "inner")
            cols[idx] = col
            prev_cy, prev_col = ln.pin_pt[1], col
        inner_len = max((label_len(ln) for i, ln in enumerate(lines)
                         if cols.get(i) == "inner"), default=0.0)

        prev_gb: tuple[float, float, float, float] | None = None
        lane_edge: float | None = None

        def approx_box(ln: _Line, ax: float):
            ll = label_len(ln)
            x0, x1 = (ax - ll, ax) if sgn < 0 else (ax, ax + ll)
            return (x0, ln.pin_pt[1] - 1.45, x1, ln.pin_pt[1] + 1.45)

        for idx, ln in enumerate(lines):
            px, py = ln.pin_pt
            lx = px + sgn * sp.port_run
            if cols.get(idx) == "outer":
                lx += sgn * gceil(inner_len + 1.27)
            if prev_gb is not None:
                bx = approx_box(ln, lx)
                if (bx[0] - 0.5 < prev_gb[2] and bx[2] + 0.5 > prev_gb[0]
                        and bx[1] - 0.5 < prev_gb[3]
                        and bx[3] + 0.5 > prev_gb[1]):
                    want = (prev_gb[0] if sgn < 0 else prev_gb[2]) \
                        + sgn * (sp.stagger_extra + sp.label_tap_gap)
                    lx = min(lx, gfloor(want)) if sgn < 0 \
                        else max(lx, gceil(want))
            labeled = is_labeled(ln)
            rot = 180 if side == "left" else 0
            if ln.attach or ln.attach_div:
                depth = 12 * U
                band_l, band_r = self._attach_band(ln)
                if ln.attach_div:
                    b0, b1 = py - depth, py + depth
                elif hang_sgn < 0:
                    b0, b1 = rank_pin_y - depth, max(py, rank_pin_y)
                else:
                    b0, b1 = min(py, rank_pin_y), rank_pin_y + depth
                tx = lx - sgn * sp.label_tap_gap if labeled else lx
                for _k in range(60):
                    if self._spot_free((tx - band_l, b0, tx + band_r, b1),
                                       pad=0.0) \
                            and self._vband_stem_free(tx, b0, b1, {ln.net}) \
                            and self._corridor_free(py, px + sgn * 0.01, tx,
                                                    {ln.net}):
                        break
                    tx = round(tx + sgn * 2 * U, 3)
                tap = (tx, py)
                if labeled:
                    lx = tx + sgn * sp.label_tap_gap
            else:
                tap = (lx, py)
            for a, b in self._escape_run_legs(ln.net, px, py, tap[0]):
                self.pl.plan(ln.net, a, b)
            edge = None
            if ln.attach_div:
                self._divider(ln, tap)
                edge = band_l if sgn < 0 else band_r
            elif ln.attach:
                self._attach_column(ln, tap, rank_pin_y, hang_sgn > 0)
                edge = band_l if sgn < 0 else band_r
            if edge is not None:
                out = tap[0] + sgn * edge
                lane_edge = (out if lane_edge is None else
                             min(lane_edge, out) if sgn < 0 else
                             max(lane_edge, out))
            if not labeled:
                ser = (self._series_of(ln.net)
                       if ln.net_class is NetClass.SIGNAL else None)
                if ser is not None:
                    out, gb2 = self._series_inline(ser, ln.net, tap, sgn,
                                                   prev_gb)
                    prev_gb = gb2
                    lane_edge = (out if lane_edge is None else
                                 min(lane_edge, out) if sgn < 0 else
                                 max(lane_edge, out))
                continue
            if tap != (lx, py):
                self.pl.plan(ln.net, tap, (lx, py))
            if ln.net_class is NetClass.PORT:
                shape = {"input": "input", "output": "output",
                         "tri_state": "tri_state", "open_collector": "output",
                         "open_emitter": "output"}.get(ln.pin_etype,
                                                       "bidirectional")
                self.label(ln.net, lx, py, rot, shape=shape)
                gb = tm.glabel_box(ln.net, lx, py, rot)
            else:
                self.llabel(ln.net, lx, py, rot)
                self._bridge(ln.net)
                gb = tm.llabel_box(ln.net, lx, py, rot)
            prev_gb = gb
            edge = gb[0] if sgn < 0 else gb[2]
            lane_edge = (min(lane_edge, edge) if lane_edge is not None
                         and sgn < 0 else
                         max(lane_edge, edge) if lane_edge is not None
                         else edge)
        for run in rail_jobs:
            self._fan_rail_run(run, sgn, rows_all)
        if comb_pts:
            self._fan_rail_comb(comb_net, comb_pts, sgn,
                                boxes_mark, plans_mark)

    def _foreign_rows_clear(self, box: tuple[float, float, float, float],
                            net: str, own_ys: set[float]) -> bool:
        foreign = [r for r, rnet in self._rail_row_net.items()
                   if rnet != net and r not in own_ys]
        foreign += [r for r in self._sig_rows if r not in own_ys]
        if _nat.loaded():
            got = _nat.module().foreign_rows_clear(box, foreign, 1e-6)
            if _nat.trace():
                ref = self._foreign_rows_clear_py(box, foreign)
                if got is not ref:
                    raise AssertionError(
                        "native foreign_rows_clear DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        return self._foreign_rows_clear_py(box, foreign)

    def _foreign_rows_clear_py(self, box: tuple[float, float, float, float],
                               foreign: list[float]) -> bool:
        y0, y1 = box[1], box[3]
        for r in foreign:
            if y0 - 1e-6 < r < y1 + 1e-6:
                return False
        return True

    def _fan_rail_run(self, run: list, sgn: int,
                      rows_all: list[tuple[float, float]]) -> None:
        net0 = run[0][2]
        w_val = tm.text_wh(net0.name)[0]
        jx_off = max(3.81, gceil(w_val / 2 + 0.7
                                 - run[0][0].length))
        jx = run[0][1][0] + sgn * jx_off
        if len(run) == 1:
            pt = run[0][1]
            rows_other = [q[1] for q in rows_all if q != pt]
            up = net0.net_class is NetClass.POWER
            above = any(y < pt[1] - 1e-6 for y in rows_other)
            below = any(y > pt[1] + 1e-6 for y in rows_other)
            if above and below:
                rot = 90 if sgn < 0 else 270
                sdef_p = self.lib.get(self._power_lib(net0.name))
                bb = body_box_page(sdef_p, jx, pt[1], rot, "body", "?")
                if (sgn < 0 and bb.x1 > jx + 0.01) or \
                        (sgn > 0 and bb.x0 < jx - 0.01):
                    rot = (rot + 180) % 360
                w_v = tm.text_wh(net0.name)[0]
                for k in range(40):
                    jxc = round(jx + sgn * k * 2 * U, 3)
                    bb = body_box_page(sdef_p, jxc, pt[1], rot,
                                       "body", "?")
                    vx = (bb.x0 - 0.42 - w_v / 2 if sgn < 0
                          else bb.x1 + 0.42 + w_v / 2)
                    vbox = tm.centered_box(net0.name, vx, pt[1])
                    if self._spot_free((bb.x0, bb.y0, bb.x1, bb.y1)) \
                            and self._spot_free(vbox) \
                            and self._corridor_free(
                                pt[1], pt[0] + sgn * 0.01, jxc,
                                {net0.name}):
                        break
                self.pl.plan(net0.name, pt, (jxc, pt[1]))
                self._power_at(net0.name, jxc, pt[1], rot,
                               (vx, pt[1]))
                return
            if up and above and not below:
                up = False
            elif not up and below and not above:
                up = True
            dy = -5.08 if up else 5.08
            is_gnd = net0.net_class is NetClass.GROUND
            rot = 0 if (is_gnd != up) else 180
            sdef_p = self.lib.get(self._power_lib(net0.name))
            for k in range(40):
                jxc = round(jx + sgn * k * 2 * U, 3)
                end = (jxc, pt[1] + dy)
                vp = _value_anchor(sdef_p, end[0], end[1], rot)
                vbox = tm.centered_box(net0.name, vp[0], vp[1])
                sbox = body_box_page(sdef_p, end[0], end[1], rot,
                                     "body", "?")
                ylo, yhi = sorted((pt[1], end[1]))
                if self._spot_free(vbox) \
                        and self._spot_free((sbox.x0, sbox.y0,
                                             sbox.x1, sbox.y1)) \
                        and self._spot_free((jxc - 0.1, ylo + 0.2,
                                             jxc + 0.1, yhi - 0.2),
                                            pad=0.0) \
                        and self._corridor_free(
                            pt[1], pt[0] + sgn * 0.01, jxc,
                            {net0.name}):
                    break
            self.pl.plan(net0.name, pt, (jxc, pt[1]), end)
            self.power(net0.name, *end, rot)
            return
        ys = [pt[1] for _, pt, _ in run]
        sdef_p = self.lib.get(self._power_lib(net0.name))
        px0 = run[0][1][0]
        is_gnd = net0.net_class is NetClass.GROUND
        own_ys = {round(y, 3) for y in ys}
        best = None
        fallback = None
        for want_top in (not is_gnd, is_gnd):
            end_y = ys[0] if want_top else ys[-1]
            rot = 0 if (is_gnd != want_top) else 180
            seated = False
            for k in range(40):
                jxc = round(jx + sgn * k * 2 * U, 3)
                vp = _value_anchor(sdef_p, jxc, end_y, rot)
                vbox = tm.centered_box(net0.name, vp[0], vp[1])
                sbox = body_box_page(sdef_p, jxc, end_y, rot, "body", "?")
                sbb = (sbox.x0, sbox.y0, sbox.x1, sbox.y1)
                rows_clear = not any(
                    r not in own_ys
                    and (vbox[1] - 1e-6 < r < vbox[3] + 1e-6
                         or sbb[1] - 1e-6 < r < sbb[3] + 1e-6)
                    for r in self._sig_rows)
                ok2 = self._spot_free(vbox) and self._spot_free(sbb) \
                    and rows_clear \
                    and self._spot_free((jxc - 0.1, ys[0] + 0.1,
                                         jxc + 0.1, ys[-1] - 0.1),
                                        pad=0.0) \
                    and all(self._corridor_free(
                        yy, px0 + sgn * 0.01, jxc, {net0.name})
                        for yy in ys)
                if ok2:
                    fclear = self._foreign_rows_clear(
                        sbb, net0.name, own_ys) and self._foreign_rows_clear(
                        vbox, net0.name, own_ys)
                    cand = (fclear, want_top, end_y, rot, jxc)
                    if best is None or (fclear and not best[0]):
                        best = cand
                    seated = True
                    break
            if not seated:
                fallback = (False, want_top, end_y, rot, jxc)
            if best is not None and best[0]:
                break
        if best is None:
            best = fallback
        _f, _wt, end_y, rot, jxc = best
        jx = jxc
        for _, pt, _ in run:
            self.pl.plan(net0.name, pt, (jx, pt[1]))
        for y0, y1 in zip(ys, ys[1:], strict=False):
            self.pl.plan(net0.name, (jx, y0), (jx, y1))
        self.power(net0.name, jx, end_y, rot)

    def _fan_rail_comb(self, net: str, pts: list[tuple[float, float]],
                       sgn: int, boxes_mark: int,
                       plans_mark: dict[str, int]) -> None:
        pts = sorted(pts, key=lambda p: p[1])
        ys = sorted({p[1] for p in pts})
        y0, y1 = ys[0] - 2 * U, ys[-1] + 2 * U
        edge = pts[0][0] + sgn * 4 * U
        for b in self.pl.boxes[boxes_mark:]:
            if b.y0 < y1 and b.y1 > y0:
                edge = min(edge, b.x0) if sgn < 0 else max(edge, b.x1)
        for net2, paths in self.pl.plans.items():
            for path in paths[plans_mark.get(net2, 0):]:
                for a, b in zip(path, path[1:], strict=False):
                    if min(a[1], b[1]) < y1 and max(a[1], b[1]) > y0:
                        edge = (min(edge, a[0], b[0]) if sgn < 0
                                else max(edge, a[0], b[0]))
        bar_x = gfloor(edge - 2 * U) if sgn < 0 else gceil(edge + 2 * U)
        for px, py in pts:
            self.pl.plan(net, (px, py), (bar_x, py))
        for ya, yb in zip(ys, ys[1:], strict=False):
            self.pl.plan(net, (bar_x, ya), (bar_x, yb))
        if self.c.nets[net].net_class is NetClass.GROUND:
            end = (bar_x, round(ys[-1] + 2 * U, 3))
            self.pl.plan(net, (bar_x, ys[-1]), end)
        else:
            end = (bar_x, round(ys[0] - 2 * U, 3))
            self.pl.plan(net, (bar_x, ys[0]), end)
        self.power(net, *end, 0)

    def _bridge(self, net: str) -> None:
        self.pl.label_bridged.add(net)

    def _net_shared(self, net: str, ref: str) -> bool:
        mset = set(self.multi)
        return any(pr.ref in mset and pr.ref != ref
                   for pr in self.c.nets[net].pins)

    def _series_of(self, net: str):
        cand = [s for s in self.series if net in (s[1], s[2])]
        if len(cand) != 1:
            return None
        s = cand[0]
        far = s[2] if s[1] == net else s[1]
        if far in self.trunks:
            return None
        if far not in self.multi_nets and \
                self.c.nets[far].net_class is not NetClass.PORT:
            return None
        return s

    def _series_inline(self, ser: tuple[str, str, str], net: str,
                       tap: tuple[float, float], sgn: int,
                       avoid_gb: tuple | None = None):
        sref = ser[0]
        far = ser[2] if ser[1] == net else ser[1]
        part = self.c.parts[sref]
        sdef = self.lib.get(part.lib_id)
        near_no = self._pin_of_net(sref, net)
        p_near = _pin(sdef, near_no)
        off = abs(p_near.y) if abs(p_near.y) > 1e-6 else abs(p_near.x)
        shift = 0.0
        if avoid_gb is not None and abs(tap[1] - (avoid_gb[1] + avoid_gb[3])
                                        / 2) < tm.GLABEL_H * tm.SIZE + 1.0:
            ll = self._glabel_len(far) \
                if self.c.nets[far].net_class is NetClass.PORT \
                else tm.text_wh(far)[0] + 0.7
            lx0 = tap[0] + sgn * (2 * U + 2 * off + 2 * U)
            b0, b1 = (lx0 - ll, lx0) if sgn < 0 else (lx0, lx0 + ll)
            if b0 - 0.5 < avoid_gb[2] and b1 + 0.5 > avoid_gb[0]:
                want = (avoid_gb[0] if sgn < 0 else avoid_gb[2]) \
                    + sgn * (self.sp.stagger_extra + self.sp.label_tap_gap)
                shift = gceil(max(0.0, (want - lx0) * sgn))
        ax = tap[0] + sgn * (2 * U + shift + off)
        self._horizontal_2pin(sref, ax, tap[1],
                              far if sgn < 0 else net,
                              text_side="right" if sgn < 0 else "left")
        near_tip = (round(tap[0] + sgn * 2 * U, 3), tap[1])
        far_tip = (round(ax + sgn * off, 3), tap[1])
        self.pl.plan(net, tap, near_tip)
        lx = round(far_tip[0] + sgn * 2 * U, 3)
        self.pl.plan(far, far_tip, (lx, tap[1]))
        rot = 180 if sgn < 0 else 0
        if self.c.nets[far].net_class is NetClass.PORT:
            self.label(far, lx, tap[1], rot)
            lb = tm.glabel_box(far, lx, tap[1], rot)
        else:
            self.llabel(far, lx, tap[1], rot)
            self._bridge(far)
            lb = tm.llabel_box(far, lx, tap[1], rot)
        self.series.remove(ser)
        return (lb[0] if sgn < 0 else lb[2]), lb

    def _attach_halfw(self, ln: _Line) -> float:
        refs = [ln.attach] if ln.attach else list(ln.attach_div or ())
        w = 0.0
        for ref in refs:
            if ref is None:
                continue
            sig_pin = self._pin_of_net(ref, ln.net)
            far_net = self.net_of(ref, self.other_pin(ref, sig_pin))
            if far_net is not None:
                w = max(w, tm.text_wh(far_net.name)[0])
        return w / 2 + 0.7

    def _attach_band(self, ln: _Line) -> tuple[float, float]:
        base = self._attach_halfw(ln)
        refs = [ln.attach] if ln.attach else list(ln.attach_div or ())
        text_w = 0.0
        body_half = 0.0
        for ref in refs:
            if ref is None:
                continue
            part = self.c.parts[ref]
            sdef = self.lib.get(part.lib_id)
            x0, y0, x1, y1 = sdef.body
            body_half = max(body_half, abs(x0), abs(x1), abs(y0), abs(y1))
            text_w = max(text_w, tm.text_wh(ref)[0],
                         tm.text_wh(part.value)[0])
        return (max(base, body_half),
                max(base, body_half + 0.42 + text_w))

    def _attach_column(self, ln: _Line, tap: tuple[float, float],
                       rank_pin_y: float, down: bool) -> float:
        ref = ln.attach
        assert ref is not None
        self.pl.plan(ln.net, tap, (tap[0], rank_pin_y))
        far_pt, far = self._vertical_2pin(ref, tap[0], rank_pin_y, ln.net,
                                          downward=down)
        self.power(far, *far_pt, self._power_rot(far, down))
        return self._attach_halfw(ln)

    def _power_rot(self, net: str, downward: bool) -> int:
        is_gnd = self.c.nets[net].net_class is NetClass.GROUND
        return 0 if (is_gnd == downward) else 180

    def _divider(self, ln: _Line, tap: tuple[float, float]) -> float:
        assert ln.attach_div is not None
        top_ref, bot_ref = ln.attach_div
        for ref, below in ((top_ref, False), (bot_ref, True)):
            far_pt, far = self._vertical_2pin(ref, tap[0], tap[1], ln.net,
                                              downward=below)
            self.power(far, *far_pt, self._power_rot(far, below))
        return self._attach_halfw(ln)

    def _rail_rot(self, net: str, side: str) -> int:
        is_gnd = self.c.nets[net].net_class is NetClass.GROUND
        return 0 if (is_gnd == (side == "bottom")) else 180

    def _rail_stub(self, net: str, pt: tuple[float, float], side: str) -> None:
        up = side == "top"
        dy = -2.54 if up else 2.54
        sdef = self.lib.get(self._power_lib(net))
        rot = self._rail_rot(net, side)
        for k in (1, 2, 3, 4, 5, 6, 8):
            for dx in (0.0, 5.08, -5.08, 10.16, -10.16, 15.24, -15.24,
                       20.32, -20.32, 25.4, -25.4):
                end = (round(pt[0] + dx, 3), round(pt[1] + dy * k, 3))
                vp = _value_anchor(sdef, end[0], end[1], rot)
                vbox = tm.centered_box(net, vp[0], vp[1])
                sbox = body_box_page(sdef, end[0], end[1], rot, "body", "?")
                ylo, yhi = sorted((pt[1], end[1]))
                ok = self._spot_free(vbox) and self._spot_free(
                    (sbox.x0, sbox.y0, sbox.x1, sbox.y1)) \
                    and self._vband_stem_free(pt[0], ylo + 0.2, yhi - 0.2,
                                              {net}) \
                    and self._spot_free((pt[0] - 0.15, ylo + 0.2,
                                         pt[0] + 0.15, yhi - 0.2), pad=0.0)
                if ok and dx:
                    xa, xb = sorted((pt[0], end[0]))
                    ok = self._spot_free((xa, end[1] - 0.5, xb, end[1] + 0.5),
                                         pad=0.0)
                if ok:
                    if dx == 0:
                        self.pl.plan(net, pt, end)
                    else:
                        self.pl.plan(net, pt, (pt[0], end[1]), end)
                    self.power(net, end[0], end[1], rot)
                    return
        raise PlaceError(f"{net}: no clear rail-stub spot off {pt}")

    def _rail_bus(self, net: str, pts: list[tuple[float, float]],
                  side: str) -> None:
        dy = -2.54 if side == "top" else 2.54
        rot = self._rail_rot(net, side)
        bar_y = round(pts[0][1] + dy, 3)
        xs = sorted(p[0] for p in pts)
        for x, y in pts:
            self.pl.plan(net, (x, y), (x, bar_y))
        for xa, xb in zip(xs, xs[1:], strict=False):
            self.pl.plan(net, (xa, bar_y), (xb, bar_y))
        mid = xs[len(xs) // 2]
        self.power(net, mid, bar_y, rot)

    def _local_drop_chain(self, net_name: str, this_ref: str):
        n = self.c.nets[net_name]
        mset = set(self.multi)
        multi_pins = [pr for pr in n.pins if pr.ref in mset]
        if len(multi_pins) != 1 or multi_pins[0].ref != this_ref:
            return None
        locals_ = list(self.hang.get(net_name, [])) + \
            [r for r, _rail in self.pull.get(net_name, [])]
        passive_refs = {pr.ref for pr in n.pins if pr.ref not in mset}
        if len(locals_) != 1 or passive_refs != set(locals_):
            return None
        ref = locals_[0]
        far = self.net_of(ref, self.other_pin(ref, self._pin_of_net(ref, net_name)))
        assert far is not None
        return _FloatChain(kind="pin", root=net_name,
                           legs=[(ref, net_name, far.name)], hangs={})

    def _signal_islet_drop(self, net: str, pt: tuple[float, float],
                           side: str) -> None:
        sgn = -1 if side == "top" else 1
        end = (pt[0], round(pt[1] + sgn * self.sp.port_run, 3))
        self.pl.plan(net, pt, end)
        self.llabel(net, *end, 0)
        self._bridge(net)
        ser = [s for s in self.series if net in (s[1], s[2])]
        n_arms = len(self.hang.get(net, [])) + len(self.pull.get(net, []))
        if len(ser) == 1 and n_arms == 1:
            self._pin_islets.add(net)

    def _stack_from_pin(self, chain: _FloatChain, pt: tuple[float, float],
                        side: str, text_side: str = "right") -> None:
        downward = side == "bottom"
        cur_net = chain.root
        cur = pt
        for ref, upper, lower in chain.legs:
            near = upper if upper == cur_net else lower
            far_pt, far = self._vertical_2pin(ref, pt[0], cur[1], near,
                                              downward, text_side=text_side)
            cur = far_pt
            cur_net = far
            self._chain_mid_features(chain, cur_net, cur)
        ncls = self.c.nets[cur_net].net_class
        if ncls in (NetClass.POWER, NetClass.GROUND):
            rot = 0 if ((ncls is NetClass.POWER) != downward) else 180
            self.power(cur_net, *cur, rot)

    def _chain_mid_features(self, chain: _FloatChain, net: str,
                            at: tuple[float, float]) -> None:
        nclass = self.c.nets[net].net_class
        if nclass in (NetClass.POWER, NetClass.GROUND):
            return
        x, y = at
        nodes = [x]
        for i, ref in enumerate(chain.hangs.get(net, [])):
            xc = gceil(x + self.sp.cap_pitch * (i + 1))
            nodes.append(xc)
            far_pt, far = self._vertical_2pin(ref, xc, y, net, downward=True)
            self.power(far, *far_pt)
        if nclass is NetClass.PORT:
            lx = gceil(nodes[-1] + (5.08 if len(nodes) > 1 else 2.54))
            nodes.append(lx)
            self.label(net, lx, y, 0)
        elif len(nodes) == 1:
            return
        for xa, xb in zip(nodes, nodes[1:], strict=False):
            self.pl.plan(net, (xa, y), (xb, y))

    def _cell(self, ref: str, ax: float, ay: float,
              handled: set[tuple[str, str, str]],
              trunk_jobs: dict[str, _Trunk],
              defer_texts: bool = False, drop_dir: int = -1) -> None:
        pp, sdef, body, sides = self._place_body(ref, ax, ay)
        pin_stacks = {ch.root: ch for ch in self.float_chains
                      if ch.kind == "pin"}

        for side in ("left", "right"):
            self._fan_side(ref, side, sides[side], handled)

        port_drops: list[tuple[Pin, tuple[float, float]]] = []
        rung_drops: list[tuple[Pin, tuple[float, float], _Trunk]] = []
        for side in ("top", "bottom"):
            rail_groups: list[tuple[str, list[tuple[float, float]]]] = []
            for pin, pt in sorted(sides[side], key=lambda t: t[1][0]):
                if (ref, pin.number, side) in handled:
                    continue
                net = self.net_of(ref, pin.number)
                if net is None:
                    self.pl.no_connects.append(NoConnect(*pt))
                    continue
                if net.name in trunk_jobs:
                    trunk_jobs[net.name].direct.append((pt, side))
                    continue
                rung = self._rung_of(net.name, trunk_jobs)
                if rung is not None:
                    rung_drops.append((pin, pt, rung))
                    continue
                if net.net_class in (NetClass.POWER, NetClass.GROUND):
                    if rail_groups and rail_groups[-1][0] == net.name:
                        rail_groups[-1][1].append(pt)
                    else:
                        rail_groups.append((net.name, [pt]))
                    continue
                if net.name in pin_stacks:
                    self._stack_from_pin(pin_stacks.pop(net.name), pt, side)
                    continue
                if net.net_class is NetClass.PORT:
                    port_drops.append((pin, pt))
                    continue
                local = self._local_drop_chain(net.name, ref)
                if local is not None:
                    self._stack_from_pin(local, pt, side)
                    continue
                if net.net_class is NetClass.SIGNAL:
                    self._signal_islet_drop(net.name, pt, side)
                    continue
                raise PlaceError(f"{ref}.{pin.number} ({net.name}) on the "
                                 f"{side} edge: no engine pattern applies")
            for net, pts in rail_groups:
                if len(pts) > 1:
                    self._rail_bus(net, pts, side)
            for net, pts in rail_groups:
                if len(pts) == 1:
                    self._rail_stub(net, pts[0], side)

        if port_drops or rung_drops:
            x0, x1 = body.x0 - 15.0, body.x1 + 15.0
            base = self._cell_floor(x0, x1)
            row = gceil(base + 4 * U)
            for pin, pt in port_drops:
                self._bottom_port_drop(ref, pin, pt, row, drop_dir)
                row = gceil(row + 4 * U)
            for pin, pt, trunk in rung_drops:
                net = self.net_of(ref, pin.number)
                legs = [r for r, a, b in self.series
                        if trunk.net in (a, b) and net.name in (a, b)]
                trunk.rungs.append((net.name, pt, "bottom_far", legs, row))
                row = gceil(row + 4 * U)

        if defer_texts:
            self._deferred_texts.append((pp, body))
        else:
            self._part_texts(pp, body)

    def _rung_of(self, net: str, trunk_jobs: dict[str, _Trunk]):
        for t in trunk_jobs.values():
            for _r, a, b in self.series:
                if {a, b} == {net, t.net}:
                    return t
        return None

    def _cell_floor(self, x0: float, x1: float) -> float:
        boxes = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
        segs = list(self._plan_seg_boxes())
        if _nat.loaded():
            got = _nat.module().cell_floor(x0, x1, boxes, segs)
            if _nat.trace():
                ref = self._cell_floor_py(x0, x1, boxes, segs)
                if got != ref:
                    raise AssertionError(
                        "native cell_floor DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        return self._cell_floor_py(x0, x1, boxes, segs)

    def _cell_floor_py(self, x0: float, x1: float, boxes, segs) -> float:
        floor = 0.0
        for b in boxes:
            if b[0] < x1 and b[2] > x0:
                floor = max(floor, b[3])
        for (sx0, _sy0, sx1, sy1) in segs:
            if sx0 < x1 and sx1 > x0:
                floor = max(floor, sy1)
        return floor

    def _bottom_port_drop(self, ref: str, pin: Pin, pt: tuple[float, float],
                          row: float, direction: int) -> None:
        net = self.net_of(ref, pin.number)
        assert net is not None
        name = net.name
        ex0, _, ex1, _ = self._extent()
        lx = gfloor(ex0 - 2 * U) if direction < 0 else gceil(ex1 + 2 * U)
        self.pl.plan(name, pt, (pt[0], row))
        pulls = self.pull.pop(name, [])
        hangs = self.hang.pop(name, [])
        if len(pulls) > 1 or hangs:
            raise PlaceError(f"net {name}: bottom-drop attachments beyond "
                             f"one pull-up — extend the engine")
        if pulls:
            start = lx if direction < 0 else max(lx, pt[0] + 2 * U)
            tap_x = self._lane_x(direction, row - 12 * U, row - 0.1,
                                 start=start)
            tap = (tap_x, row)
            lx = tap_x + direction * self.sp.label_tap_gap
            self.pl.plan(name, (pt[0], row), tap)
            self.pl.plan(name, tap, (lx, row))
            pref, prail = pulls[0]
            knee = (tap_x, row - self.sp.hang_stub)
            self.pl.plan(name, tap, knee)
            far_pt, far = self._vertical_2pin(pref, tap_x, knee[1],
                                              name, downward=False)
            self.power(far, *far_pt)
        else:
            self.pl.plan(name, (pt[0], row), (lx, row))
        shape = {"input": "input", "output": "output"}.get(pin.etype,
                                                           "bidirectional")
        self.label(name, lx, row, 180 if direction < 0 else 0, shape=shape)

    def _build_trunk(self, t: _Trunk) -> None:
        votes = 0
        for _pt, side in t.direct:
            votes += 1 if side == "top" else -1 if side == "bottom" else 0
        for (_n, _pt, k, _legs, _row) in t.rungs:
            if k == "bottom_far":
                votes -= 1
        t.zone = "above" if votes > 0 else "below"
        ex0, ey0, ex1, ey1 = self._extent()
        if t.zone == "above":
            ty = gfloor(ey0 - 4 * U)
        else:
            ty = gceil(ey1 + 4 * U)
        if t.zone == "below" and t.rungs:
            max_legs = max(len(legs) for (_n, _pt, _k, legs, _r) in t.rungs)
            bar = gceil(max(pt[1] for (_n, pt, _k, _l, _r) in t.rungs) + 4 * U)
            ty = max(ty, round(bar + 7.62 * max_legs, 3))
        t.y = ty
        nodes: list[float] = []

        side_jobs: list[tuple[str, tuple[float, float], int, object]] = []
        for pt, side in t.direct:
            if side in ("top", "bottom"):
                if self._corridor_clear_vert(pt[0], pt[1], ty, t.net):
                    self.pl.plan(t.net, pt, (pt[0], ty))
                    nodes.append(pt[0])
                else:
                    way = self._escape_path(1, pt, ty, t.net)
                    self.pl.plan(t.net, *way)
                    nodes.append(way[-1][0])
            else:
                side_jobs.append(("direct", pt, -1 if side == "left" else 1,
                                  None))
        for far_net, pt, kind, legs, row in t.rungs:
            if kind in ("left", "right"):
                sgn = -1 if kind == "left" else 1
                if len(legs) == 1:
                    side_jobs.append(("rung", pt, sgn, (far_net, legs[0])))
                else:
                    side_jobs.append(("ladder", pt, sgn, (far_net, legs)))
            elif t.zone == "below":
                bar = gceil(self._rung_bar_y(t))
                nodes += self._ladder_rung(t, far_net, pt, legs, bar)
            else:
                fx = self._lane_x(-1, ty, row + 2 * U, start=pt[0] - 3 * U)
                self.pl.plan(far_net, pt, (pt[0], row))
                self.pl.plan(far_net, (pt[0], row), (fx, row))
                if len(legs) != 1:
                    raise PlaceError(f"{t.net}: flank rung with {len(legs)} "
                                     f"legs — extend the engine")
                if far_net in self.pl.label_bridged:
                    self.llabel(far_net, round(pt[0] - 2 * U, 3), row, 180)
                far_pt, far = self._vertical_2pin(legs[0], fx, row,
                                                  far_net, downward=False,
                                                  text_side="left")
                assert far == t.net
                self.pl.plan(t.net, far_pt, (fx, ty))
                nodes.append(fx)

        side_jobs.sort(key=lambda j: abs(j[1][1] - ty))
        for kind, pt, sgn, payload in side_jobs:
            own = t.net if kind == "direct" else payload[0]
            if kind == "direct":
                way = self._escape_path(sgn, pt, ty, own)
                self.pl.plan(t.net, *way)
                nodes.append(way[-1][0])
            elif kind == "ladder":
                far_net, legs = payload
                nodes += self._side_ladder_rung(t, far_net, pt, sgn, legs, ty)
            else:
                far_net, leg = payload
                try:
                    fx = self._escape_lane(sgn, pt, ty, own)
                except PlaceError:
                    self._rung_islet_drop(far_net, pt, sgn)
                    self._rung_islets.append((t.net, far_net, leg))
                    continue
                toward_top = ty < pt[1]
                self.pl.plan(far_net, pt, (fx, pt[1]))
                far_pt, far = self._vertical_2pin(
                    leg, fx, pt[1], far_net, downward=not toward_top,
                    text_side="left" if sgn < 0 else "right")
                assert far == t.net
                self.pl.plan(t.net, far_pt, (fx, ty))
                nodes.append(fx)

        for ch in t.chains:
            ex0b, _, _, _ = self._extent()
            band0, band1 = (ty, ty + 24.0)
            edge = self._band_edge(band0 - 2, band1, -1, default=ex0b)
            x = gfloor(edge - 4 * U)
            nodes.append(x)
            cur = (x, ty)
            cur_net = t.net
            for ref, upper, lower in ch.legs:
                near = upper if upper == cur_net else lower
                far_pt, far = self._vertical_2pin(ref, x, cur[1], near,
                                                  downward=True,
                                                  text_side="right")
                cur, cur_net = far_pt, far
                self._chain_mid_features_left(ch, cur_net, cur)
            if self.c.nets[cur_net].net_class in (NetClass.POWER,
                                                  NetClass.GROUND):
                end_c = (cur[0], round(cur[1] + 2 * U, 3))
                self.pl.plan(cur_net, cur, end_c)
                self.power(cur_net, *end_c, self._power_rot(cur_net, True))

        for _i, ref in enumerate(self.hang.pop(t.net, [])):
            ex0c, _, ex1c, _ = self._extent()
            edge_r = gceil(self._band_edge(ty - 2 * U, ty + 10 * U, +1,
                                           default=max(nodes) if nodes
                                           else 0.0) + 4 * U)
            edge_l = gfloor(self._band_edge(ty - 2 * U, ty + 10 * U, -1,
                                            default=min(nodes) if nodes
                                            else 0.0) - 4 * U)
            grow_r = max(0.0, edge_r + 2 * U - ex1c)
            grow_l = max(0.0, ex0c - (edge_l - 2 * U))
            x = edge_l if grow_l < grow_r else edge_r
            nodes.append(x)
            far_pt, far = self._vertical_2pin(ref, x, ty, t.net,
                                              downward=True)
            self.power(far, *far_pt)

        nodes = sorted(set(round(n, 3) for n in nodes))
        if len(nodes) < 2:
            raise PlaceError(f"trunk {t.net}: fewer than 2 taps after build")

        if self._needs_flag(t.net):
            gaps = sorted(zip(nodes, nodes[1:], strict=False),
                          key=lambda ab: ab[1] - ab[0])
            xa, xb = gaps[-1]
            fx = gsnap((xa + xb) / 2)
            dy = -2.54 if t.zone == "above" else 2.54
            self.pl.plan(t.net, (fx, ty), (fx, ty + dy))
            self.flag(t.net, fx, ty + dy, 0 if t.zone == "above" else 180)
            nodes = sorted(set(nodes + [fx]))

        for xa, xb in zip(nodes, nodes[1:], strict=False):
            self.pl.plan(t.net, (xa, ty), (xb, ty))
        if self.c.nets[t.net].net_class is NetClass.PORT:
            ex0c, _, ex1c, _ = self._extent()
            w_lab = self._glabel_len(t.net)
            grow_r = max(0.0, nodes[-1] + 2 * U + w_lab - ex1c)
            grow_l = max(0.0, ex0c - (nodes[0] - 2 * U - w_lab))
            ends = [(nodes[-1], 0), (nodes[0], 180)]
            if grow_l < grow_r:
                ends.reverse()
            cands = [(nx, rot, k) for k in range(1, 12)
                     for nx, rot in ends]
            for nx, rot, k in cands:
                lx = round(nx + (2 * U * k if rot == 0 else -2 * U * k), 3)
                sgn_l = 1 if rot == 0 else -1
                if self._spot_free(tm.glabel_box(t.net, lx, ty, rot),
                                   pad=0.25) \
                        and self._corridor_free(ty, nx + sgn_l * 0.01, lx,
                                                {t.net}):
                    break
            self.pl.plan(t.net, (nx, ty), (lx, ty))
            self.label(t.net, lx, ty, rot)
            return
        for lx, rot in ((nodes[-1], 0), (nodes[0], 180),
                        (nodes[0] + 1.27, 0)):
            if self._spot_free(tm.llabel_box(t.net, lx, ty, rot), pad=0.1):
                self.llabel(t.net, lx, ty, rot)
                break
        else:
            self.llabel(t.net, nodes[-1], ty, 0)

    def _chain_mid_features_left(self, chain: _FloatChain, net: str,
                                 at: tuple[float, float]) -> None:
        nclass = self.c.nets[net].net_class
        if nclass in (NetClass.POWER, NetClass.GROUND):
            return
        x, y = at
        nodes = [x]
        for i, ref in enumerate(chain.hangs.get(net, [])):
            xc = gfloor(x - self.sp.cap_pitch * (i + 1))
            nodes.append(xc)
            far_pt, far = self._vertical_2pin(ref, xc, y, net, downward=True)
            self.power(far, *far_pt)
        if nclass is NetClass.PORT:
            lx = gfloor(min(nodes) - 2.54)
            nodes.append(lx)
            self.label(net, lx, y, 180)
        elif len(nodes) == 1:
            return
        nodes = sorted(nodes)
        for xa, xb in zip(nodes, nodes[1:], strict=False):
            self.pl.plan(net, (xa, y), (xb, y))

    def _rung_bar_y(self, t: _Trunk) -> float:
        return gceil(max(pt[1] for (_n, pt, k, _l, _r) in t.rungs
                         if k == "bottom_far") + 4 * U)

    def _ladder_rung(self, t: _Trunk, far_net: str, pt: tuple[float, float],
                     legs: list[str], bar: float) -> list[float]:
        legs = sorted(legs, key=lambda r: self.c.parts[r].lib_id.endswith(":C"))
        x0 = pt[0]
        cols = [round(x0 + i * 6 * U, 3) for i in range(len(legs))]
        self.pl.plan(far_net, pt, (x0, bar))
        for xa, xb in zip(cols, cols[1:], strict=False):
            self.pl.plan(far_net, (xa, bar), (xb, bar))
        self.llabel(far_net, x0 + 1.27, bar)
        for i, (ref, xc) in enumerate(zip(legs, cols, strict=False)):
            att_y = round(bar + i * 6 * U, 3)
            if att_y != bar:
                self.pl.plan(far_net, (xc, bar), (xc, att_y))
            far_pt, far = self._vertical_2pin(
                ref, xc, att_y, far_net, downward=True,
                text_side="left" if i % 2 == 0 else "right")
            assert far == t.net
            self.pl.plan(t.net, far_pt, (xc, t.y))
        return cols

    def _side_ladder_rung(self, t: _Trunk, far_net: str,
                          pt: tuple[float, float], sgn: int,
                          legs: list[str], ty: float) -> list[float]:
        legs = sorted(legs,
                      key=lambda r: self.c.parts[r].lib_id.endswith(":C"))
        bar_y = pt[1]
        pitch = gceil(self.sp.cap_pitch)
        text_side = "right" if sgn > 0 else "left"
        cols: list[float] = []
        bar_from = pt
        for i, ref in enumerate(legs):
            att_y = round(bar_y + i * pitch, 3)
            start = bar_from[0] + sgn * (pitch if cols else 3 * U)
            fx = self._free_drop_col(sgn, start, att_y, ty, ref, far_net,
                                     text_side)
            self.pl.plan(far_net, bar_from, (fx, bar_y))
            if att_y != bar_y:
                self.pl.plan(far_net, (fx, bar_y), (fx, att_y))
            far_pt, far = self._vertical_2pin(
                ref, fx, att_y, far_net, downward=True, text_side=text_side)
            assert far == t.net
            self.pl.plan(t.net, far_pt, (fx, ty))
            cols.append(fx)
            bar_from = (fx, bar_y)
        self.llabel(far_net, round(pt[0] + sgn * 2 * U, 3), bar_y,
                    0 if sgn > 0 else 180)
        return cols

    def _free_drop_col(self, sgn: int, start: float, att_y: float, ty: float,
                       ref: str, attach_net: str, text_side: str) -> float:
        sdef = self.lib.get(self.c.parts[ref].lib_id)
        att_no = self._pin_of_net(ref, attach_net)
        off = abs(_pin(sdef, att_no).y) or abs(_pin(sdef, att_no).x)
        anchor_y = att_y + off
        x = gceil(start) if sgn > 0 else gfloor(start)
        for _ in range(160):
            pp = PlacedPart(ref, self.c.parts[ref].lib_id,
                            self.c.parts[ref].value, x, anchor_y, 0,
                            self.c.parts[ref].footprint)
            body = body_box_page(sdef, x, anchor_y, 0, "body", ref)
            boxes = [body, *_pin_text_boxes(sdef, pp)]
            tw, th = tm.text_wh(self.c.parts[ref].value)
            vx = (x + 0.7, anchor_y - th / 2, x + 0.7 + tw, anchor_y + th / 2) \
                if text_side == "right" else \
                (x - 0.7 - tw, anchor_y - th / 2, x - 0.7, anchor_y + th / 2)
            boxes.append(Box(*vx, "value", ref))
            drop = (x - 0.4, att_y, x + 0.4, ty)
            if all(self._spot_free((b.x0, b.y0, b.x1, b.y1), pad=0.3)
                   for b in boxes) \
                    and self._spot_free(drop, pad=0.0) \
                    and self._corridor_free(att_y, x + sgn * 0.01,
                                            x - sgn * 0.4, {attach_net}):
                return x
            x = round(x + sgn * 2 * U, 3)
        raise PlaceError(f"{attach_net}: no free ladder column from {start}")

    def _lane_x(self, sgn: int, y0: float, y1: float, start: float) -> float:
        if _nat.loaded():
            parts = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
            segs = list(self._plan_seg_boxes())
            ncs = list(self._nc_boxes())
            got = _nat.module().lane_x(int(sgn), y0, y1, start, U, 0.7, 0.3,
                                       0.0, parts, segs, ncs)
            if _nat.trace():
                ref = self._lane_x_py(sgn, y0, y1, start)
                if got != ref and not (got is None and ref is None):
                    raise AssertionError(
                        f"native lane_x DIVERGENCE: cpp={got} python={ref}")
            if got is None:
                raise PlaceError("no free lane found")
            return got
        hit = self._lane_x_py(sgn, y0, y1, start)
        if hit is None:
            raise PlaceError("no free lane found")
        return hit

    def _lane_x_py(self, sgn: int, y0: float, y1: float, start: float):
        x = gfloor(start) if sgn < 0 else gceil(start)
        for _ in range(120):
            band = (x - 0.7, y0 - 0.3, x + 0.7, y1 + 0.3)
            if self._spot_free(band, pad=0.0):
                return x
            x = round(x + sgn * 2 * U, 3)
        return None

    def _escape_run_legs(self, net: str, px: float, py: float,
                         tx: float) -> list[tuple[tuple[float, float],
                                                  tuple[float, float]]]:
        if _nat.loaded():
            owned = [(b.x0, b.y0, b.x1, b.y1, b.owner, b.kind)
                     for b in self.pl.boxes]
            parts = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
            spot_segs = list(self._plan_seg_boxes())
            ncs = list(self._nc_boxes())
            skip = {net}
            corr_segs = (list(self._plan_raw_segs(skip))
                         + list(self._stem_segs(skip)))
            stems = list(self._stem_segs(skip))
            raw = _nat.module().escape_run_legs(
                px, py, tx, U, 0.127, owned, parts, spot_segs, ncs, parts,
                corr_segs, stems, 0.0, 0.3, 0.3)
            got = [((a, b), (c, d)) for a, b, c, d in raw]
            if _nat.trace():
                ref = self._escape_run_legs_py(net, px, py, tx)
                if got != ref:
                    raise AssertionError(
                        "native escape_run_legs DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        return self._escape_run_legs_py(net, px, py, tx)

    def _escape_run_legs_py(self, net: str, px: float, py: float,
                            tx: float) -> list[tuple[tuple[float, float],
                                                     tuple[float, float]]]:
        sgn = 1.0 if tx >= px else -1.0
        ec = 0.127
        bx0r, bx1r = min(px, tx), max(px, tx)
        blockers: list[tuple[float, float, float, float]] = []
        for b in self.pl.boxes:
            if b.kind != "body" or not (b.y0 - ec < py < b.y1 + ec):
                continue
            if not (b.x0 < bx1r and b.x1 > bx0r):
                continue
            ox0, oy0, ox1, oy1 = b.x0, b.y0, b.x1, b.y1
            for t in self.pl.boxes:
                if t.owner == b.owner and t is not b:
                    ox0, oy0 = min(ox0, t.x0), min(oy0, t.y0)
                    ox1, oy1 = max(ox1, t.x1), max(oy1, t.y1)
            blockers.append((ox0, oy0, ox1, oy1))
        if not blockers:
            return [((px, py), (tx, py))]
        spans = sorted(((bx0, bx1, by0, by1) for bx0, by0, bx1, by1 in blockers))
        clusters: list[tuple[float, float, float, float]] = []
        for x0, x1, y0, y1 in spans:
            if clusters and x0 <= clusters[-1][1] + 2 * U:
                cx0, cx1, cy0, cy1 = clusters[-1]
                clusters[-1] = (min(cx0, x0), max(cx1, x1),
                                min(cy0, y0), max(cy1, y1))
            else:
                clusters.append((x0, x1, y0, y1))
        ordered = sorted(clusters, key=lambda c: c[0], reverse=(sgn < 0))
        legs: list[tuple[tuple[float, float], tuple[float, float]]] = []
        cur_x = px
        for cx0, cx1, cy0, cy1 in ordered:
            enter = gfloor(cx0 - U) if sgn > 0 else gceil(cx1 + U)
            exitx = gceil(cx1 + U) if sgn > 0 else gfloor(cx0 - U)
            lo, hi = sorted((enter, exitx))
            dy = None
            for direction in (1, -1):
                base = (gceil(cy1 + 2 * U) if direction > 0
                        else gfloor(cy0 - 2 * U))
                for k in range(0, 14):
                    cand = round(base + direction * k * U, 3)
                    ry0, ry1 = sorted((py, cand))
                    if self._corridor_free(cand, lo, hi, {net}) \
                            and self._spot_free(
                                (enter - 0.1, ry0, enter + 0.1, ry1),
                                pad=0.0) \
                            and self._spot_free(
                                (exitx - 0.1, ry0, exitx + 0.1, ry1),
                                pad=0.0) \
                            and self._vband_stem_free(enter, ry0, ry1, {net}) \
                            and self._vband_stem_free(exitx, ry0, ry1, {net}):
                        dy = cand
                        break
                if dy is not None:
                    break
            if dy is None:
                continue
            legs.append(((cur_x, py), (enter, py)))
            legs.append(((enter, py), (enter, dy)))
            legs.append(((enter, dy), (exitx, dy)))
            legs.append(((exitx, dy), (exitx, py)))
            cur_x = exitx
        legs.append(((cur_x, py), (tx, py)))
        return legs

    def _plan_raw_segs(self, skip: set[str]):
        for net, paths in self.pl.plans.items():
            if net in skip:
                continue
            for path in paths:
                for a, bb in zip(path, path[1:], strict=False):
                    yield (a[0], a[1], bb[0], bb[1])

    def _stem_segs(self, skip: set[str]):
        for part in self.pl.parts:
            sdef = self.lib.get(part.lib_id)
            for pin in sdef.pins:
                if pin.hidden:
                    continue
                n = self.net_of(part.ref, pin.number)
                if n is not None and n.name in skip:
                    continue
                tip = pin_page_position(pin, part.x, part.y, part.rotation)
                dxn, dyn = route._stem_dir(pin.rotation, part.rotation)
                root = (round(tip[0] + dxn * pin.length, 3),
                        round(tip[1] + dyn * pin.length, 3))
                yield (tip[0], tip[1], root[0], root[1])

    def _corridor_free(self, y: float, xa: float, xb: float,
                       skip: set[str]) -> bool:
        if _nat.loaded():
            boxes = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
            segs = list(self._plan_raw_segs(skip)) + list(self._stem_segs(skip))
            return _nat.module().corridor_free(y, xa, xb, boxes, segs, 0.3)
        x0, x1 = sorted((xa, xb))
        for b in self.pl.boxes:
            if b.y0 + 1e-6 < y < b.y1 - 1e-6 and b.x0 < x1 and b.x1 > x0:
                return False
        for net, paths in self.pl.plans.items():
            if net in skip:
                continue
            for path in paths:
                for a, bb in zip(path, path[1:], strict=False):
                    sx0, sx1 = sorted((a[0], bb[0]))
                    sy0, sy1 = sorted((a[1], bb[1]))
                    if sy0 - 0.3 <= y <= sy1 + 0.3 \
                            and sx0 - 0.3 <= x1 and sx1 + 0.3 >= x0:
                        return False
        for part in self.pl.parts:
            sdef = self.lib.get(part.lib_id)
            for pin in sdef.pins:
                if pin.hidden:
                    continue
                n = self.net_of(part.ref, pin.number)
                if n is not None and n.name in skip:
                    continue
                tip = pin_page_position(pin, part.x, part.y, part.rotation)
                dxn, dyn = route._stem_dir(pin.rotation, part.rotation)
                root = (round(tip[0] + dxn * pin.length, 3),
                        round(tip[1] + dyn * pin.length, 3))
                sx0, sx1 = sorted((tip[0], root[0]))
                sy0, sy1 = sorted((tip[1], root[1]))
                if sy0 - 0.3 <= y <= sy1 + 0.3 \
                        and sx0 - 0.3 <= x1 and sx1 + 0.3 >= x0:
                    return False
        return True

    def _vband_stem_free(self, x: float, y0: float, y1: float,
                         skip: set[str]) -> bool:
        if _nat.loaded():
            segs = list(self._stem_segs(skip))
            got = _nat.module().vband_stem_free(x, y0, y1, segs, 0.3)
            if _nat.trace():
                ref = True
                for sx0, sy0, sx1, sy1 in segs:
                    a, b = sorted((sx0, sx1))
                    c, d = sorted((sy0, sy1))
                    if (a - 0.3 <= x <= b + 0.3
                            and c - 0.3 <= y1 and d + 0.3 >= y0):
                        ref = False
                        break
                if got is not ref:
                    raise AssertionError(
                        "native vband_stem_free DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        for part in self.pl.parts:
            sdef = self.lib.get(part.lib_id)
            for pin in sdef.pins:
                if pin.hidden:
                    continue
                n = self.net_of(part.ref, pin.number)
                if n is not None and n.name in skip:
                    continue
                tip = pin_page_position(pin, part.x, part.y, part.rotation)
                dxn, dyn = route._stem_dir(pin.rotation, part.rotation)
                root = (round(tip[0] + dxn * pin.length, 3),
                        round(tip[1] + dyn * pin.length, 3))
                sx0, sx1 = sorted((tip[0], root[0]))
                sy0, sy1 = sorted((tip[1], root[1]))
                if sx0 - 0.3 <= x <= sx1 + 0.3 \
                        and sy0 - 0.3 <= y1 and sy1 + 0.3 >= y0:
                    return False
        return True

    def _lane_in_dir(self, sgn: int, pt: tuple[float, float], ty: float,
                     net: str) -> float | None:
        if _nat.loaded():
            parts = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
            spot_segs = list(self._plan_seg_boxes())
            ncs = list(self._nc_boxes())
            corr_boxes = parts
            corr_segs = (list(self._plan_raw_segs({net}))
                         + list(self._stem_segs({net})))
            got = _nat.module().lane_in_dir(
                int(sgn), pt[0], pt[1], ty, U, 0.7, 0.3, 0.0, 0.3, 0.01,
                parts, spot_segs, ncs, corr_boxes, corr_segs)
            if _nat.trace():
                ref = self._lane_in_dir_py(sgn, pt, ty, net)
                if got != ref:
                    raise AssertionError(
                        "native lane_in_dir DIVERGENCE: "
                        f"cpp={got} python={ref}")
            return got
        return self._lane_in_dir_py(sgn, pt, ty, net)

    def _lane_in_dir_py(self, sgn: int, pt: tuple[float, float], ty: float,
                        net: str) -> float | None:
        y0, y1 = sorted((pt[1], ty))
        x = gfloor(pt[0] + sgn * 3 * U) if sgn < 0 \
            else gceil(pt[0] + sgn * 3 * U)
        for _ in range(120):
            band = (x - 0.7, y0 - 0.3, x + 0.7, y1 + 0.3)
            if self._spot_free(band, pad=0.0) and self._corridor_free(
                    pt[1], pt[0] + sgn * 0.01, x, {net}):
                return x
            x = round(x + sgn * 2 * U, 3)
        return None

    def _corridor_clear_vert(self, x: float, y_pin: float, ty: float,
                             net: str) -> bool:
        if _nat.loaded():
            boxes = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
            segs = list(self._plan_raw_segs({net}))
            return _nat.module().corridor_clear_vert(
                x, y_pin, ty, boxes, segs, 0.2)
        y0, y1 = sorted((y_pin, ty))
        for b in self.pl.boxes:
            if b.x0 - 0.2 < x < b.x1 + 0.2 \
                    and b.y0 < y1 - 1e-6 and b.y1 > y0 + 1e-6 \
                    and not (abs(b.y0 - y_pin) < 1e-6 or abs(b.y1 - y_pin)
                             < 1e-6):
                return False
        for n2, paths in self.pl.plans.items():
            if n2 == net:
                continue
            for path in paths:
                for a, bb in zip(path, path[1:], strict=False):
                    sx0, sx1 = sorted((a[0], bb[0]))
                    sy0, sy1 = sorted((a[1], bb[1]))
                    if sx0 - 0.2 <= x <= sx1 + 0.2 \
                            and sy0 - 0.2 <= y1 and sy1 + 0.2 >= y0 \
                            and not (sy0 == sy1 and abs(sy0 - y_pin) < 1e-6):
                        return False
        return True

    def _escape_lane(self, sgn: int, pt: tuple[float, float], ty: float,
                     net: str) -> float:
        for s in (sgn, -sgn):
            fx = self._lane_in_dir(s, pt, ty, net)
            if fx is not None:
                return fx
        raise PlaceError(f"{net}: no free escape lane from {pt}")

    def _cell_free(self, x: float, y: float, net: str) -> bool:
        if _nat.loaded():
            boxes = [(b.x0, b.y0, b.x1, b.y1) for b in self.pl.boxes]
            segs = list(self._plan_raw_segs({net})) + list(self._stem_segs({net}))
            return _nat.module().cell_free_point(x, y, boxes, segs, 0.3)
        for b in self.pl.boxes:
            if b.x0 + 1e-6 < x < b.x1 - 1e-6 and b.y0 + 1e-6 < y < b.y1 - 1e-6:
                return False
        for n, paths in self.pl.plans.items():
            if n == net:
                continue
            for path in paths:
                for a, bb in zip(path, path[1:], strict=False):
                    sx0, sx1 = sorted((a[0], bb[0]))
                    sy0, sy1 = sorted((a[1], bb[1]))
                    if sx0 - 0.3 <= x <= sx1 + 0.3 \
                            and sy0 - 0.3 <= y <= sy1 + 0.3:
                        return False
        for part in self.pl.parts:
            sdef = self.lib.get(part.lib_id)
            for pin in sdef.pins:
                if pin.hidden:
                    continue
                n = self.net_of(part.ref, pin.number)
                if n is not None and n.name == net:
                    continue
                tip = pin_page_position(pin, part.x, part.y, part.rotation)
                dxn, dyn = route._stem_dir(pin.rotation, part.rotation)
                root = (round(tip[0] + dxn * pin.length, 3),
                        round(tip[1] + dyn * pin.length, 3))
                sx0, sx1 = sorted((tip[0], root[0]))
                sy0, sy1 = sorted((tip[1], root[1]))
                if sx0 - 0.3 <= x <= sx1 + 0.3 \
                        and sy0 - 0.3 <= y <= sy1 + 0.3:
                    return False
        return True

    def _escape_path(self, sgn: int, pt: tuple[float, float], ty: float,
                     net: str) -> list[tuple[float, float]]:
        for s in (sgn, -sgn):
            fx = self._lane_in_dir(s, pt, ty, net)
            if fx is not None:
                return [pt, (fx, pt[1]), (fx, ty)]
        return self._bfs_escape(pt, ty, net)

    def _bfs_escape(self, pt: tuple[float, float], ty: float,
                    net: str) -> list[tuple[float, float]]:
        ex0, ey0, ex1, ey1 = self._extent()
        margin = 16 * U
        i0 = int(gfloor(min(ex0, pt[0]) - margin) / U)
        i1 = int(gceil(max(ex1, pt[0]) + margin) / U)
        j0 = int(gfloor(min(ey0, pt[1], ty) - margin) / U)
        j1 = int(gceil(max(ey1, pt[1], ty) + margin) / U)
        start = (int(round(pt[0] / U)), int(round(pt[1] / U)))
        jty = int(round(ty / U))
        DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
        TURN = 1000

        import heapq
        dist: dict[tuple[tuple[int, int], int], int] = {(start, -1): 0}
        prev: dict[tuple[tuple[int, int], int],
                   tuple[tuple[int, int], int] | None] = {(start, -1): None}
        pq: list[tuple[int, tuple[int, int], int]] = [(0, start, -1)]
        hit: tuple[tuple[int, int], int] | None = None
        while pq:
            cost, cell, came = heapq.heappop(pq)
            if dist.get((cell, came), 1 << 60) < cost:
                continue
            if cell[1] == jty and cell != start:
                hit = (cell, came)
                break
            for di, d in enumerate(DIRS):
                n = (cell[0] + d[0], cell[1] + d[1])
                if not (i0 <= n[0] <= i1 and j0 <= n[1] <= j1):
                    continue
                if not self._cell_free(round(n[0] * U, 3), round(n[1] * U, 3),
                                       net):
                    continue
                nc = cost + 1 + (TURN if came != -1 and came != di else 0)
                st = (n, di)
                if nc < dist.get(st, 1 << 60):
                    dist[st] = nc
                    prev[st] = (cell, came)
                    heapq.heappush(pq, (nc, n, di))
        if hit is None:
            raise PlaceError(f"{net}: no free escape lane from {pt}")
        chain: list[tuple[int, int]] = []
        st: tuple[tuple[int, int], int] | None = hit
        while st is not None:
            chain.append(st[0])
            st = prev[st]
        chain.reverse()
        pts = [(round(c[0] * U, 3), round(c[1] * U, 3)) for c in chain]
        way = [pts[0]]
        for k in range(1, len(pts) - 1):
            (x0, y0), (x1, y1), (x2, y2) = pts[k - 1], pts[k], pts[k + 1]
            if not ((x0 == x1 == x2) or (y0 == y1 == y2)):
                way.append(pts[k])
        way.append(pts[-1])
        return way

    def _needs_flag(self, net: str) -> bool:
        etype_of = {}
        for ref, part in self.c.parts.items():
            for p in self.lib.get(part.lib_id).pins:
                etype_of[(ref, p.number)] = p.etype
        pins = self.c.nets[net].pins
        ets = {etype_of.get((pr.ref, pr.pin), "?") for pr in pins}
        return "power_in" in ets and not (ets & _FLAG_DRIVER_ETYPES)

    def _farm_row_right_bound(self, ex0: float, ex1_flow: float) -> float:
        flow_centre = (ex0 + ex1_flow) / 2.0
        dx = A3_CENTER[0] - flow_centre
        local_limit = (A3_TITLEBLOCK_LEFT - TITLEBLOCK_MARGIN) - dx
        return local_limit - self.sp.cap_pitch / 2.0

    def _decoupling_cluster(self, ax: float, ay: float, body: Box) -> None:
        sp = self.sp
        col_x = ax - sp.cluster_dx
        n_caps = sum(len(v) for v in self.cluster.values())
        if not n_caps:
            return
        span = (n_caps - 1) * sp.cap_pitch
        if n_caps > 5:
            ex0, _, ex1_flow, ey1 = self._extent()
            col_x = gsnap(ex0 + 4 * U)
            farm_left = col_x
            row_step = gceil(8 * U)
            max_right = self._farm_row_right_bound(ex0, ex1_flow)
            cy = gceil(ey1 + (12 if self._n_box_bucks >= 2 else 8) * U)
        else:
            col_x = min(col_x, gfloor(body.x0 - span - 4 * sp.hang_stub))
            cy = max(ay + sp.cluster_dy, gceil(body.y1 + 3 * sp.hang_stub))
            floor = self._cell_floor(col_x - 2 * sp.cap_pitch,
                                     col_x + span + 2 * sp.cap_pitch)
            cy = max(cy, gceil(floor + 4 * sp.hang_stub))
            farm_left = col_x
            row_step = 0.0
            max_right = float("inf")
        prev_rail_w: float | None = None
        for rail, caps in self.cluster.items():
            if prev_rail_w is not None:
                col_x = gceil(col_x - sp.cap_pitch
                              + max(sp.cap_pitch,
                                    prev_rail_w / 2
                                    + tm.text_wh(rail)[0] / 2 + 1.27))
            prev_rail_w = tm.text_wh(rail)[0]
            runs: list[tuple[float, list[float]]] = []
            cur: list[float] = []
            for ref in caps:
                if col_x > max_right and cur:
                    runs.append((cy, cur))
                    cur = []
                    col_x = farm_left
                    cy = gceil(cy + row_step)
                self._cluster_cap(ref, col_x, cy)
                cur.append(col_x)
                col_x += sp.cap_pitch
            if cur:
                runs.append((cy, cur))
            for run_cy, tops in runs:
                ry = run_cy - 3.81
                if len(tops) == 1:
                    self.power(rail, tops[0], ry)
                else:
                    xm = gsnap((tops[0] + tops[-1]) / 2)
                    nodes = sorted(set(tops + [xm]))
                    for a, b in zip(nodes, nodes[1:], strict=False):
                        self.pl.plan(rail, (a, ry), (b, ry))
                    self.pl.plan(rail, (xm, ry), (xm, ry - 2.54))
                    self.power(rail, xm, ry - 2.54)
        self.cluster = {}

    def _cluster_cap(self, ref: str, x: float, cy: float) -> None:
        part = self.c.parts[ref]
        pins = sorted(self.lib.pin_numbers(part.lib_id))
        n_by_pin = {p: self.net_of(ref, p) for p in pins}
        rail_pin = [p for p in pins
                    if n_by_pin[p] and n_by_pin[p].net_class == NetClass.POWER][0]
        rail_net = n_by_pin[rail_pin]
        assert rail_net is not None
        far_pt, far = self._vertical_2pin(ref, x, cy - 3.81, rail_net.name,
                                          downward=True)
        self.power(far, *far_pt, self._power_rot(far, True))

    def _flags_row(self) -> None:
        etype_of = {}
        for ref, part in self.c.parts.items():
            for p in self.lib.get(part.lib_id).pins:
                etype_of[(ref, p.number)] = p.etype
        rails = []
        for n in self.c.nets.values():
            if n.net_class not in (NetClass.POWER, NetClass.GROUND):
                continue
            ets = {etype_of.get((pr.ref, pr.pin), "?") for pr in n.pins}
            if ets & _FLAG_DRIVER_ETYPES:
                continue
            rails.append(n)
        if not rails:
            return
        ex0, _, _, ey1 = self._extent()
        fy = gceil(ey1 + 6 * U)
        fx = gsnap(ex0 + 4 * U)
        prev_w = None
        for net in rails:
            w = tm.text_wh(net.name)[0]
            if prev_w is not None:
                fx = gceil(fx + max(self.sp.flag_pitch,
                                    prev_w / 2 + w / 2 + 2.54))
            if net.net_class == NetClass.GROUND:
                self.power(net.name, fx, fy)
                self.pl.plan(net.name, (fx, fy), (fx, fy - 2.54))
                self.flag(net.name, fx, fy - 2.54, 0)
            else:
                self.power(net.name, fx, fy)
                self.pl.plan(net.name, (fx, fy), (fx, fy + 2.54))
                self.flag(net.name, fx, fy + 2.54, 180)
            prev_w = w

    def _stack_columns_template(self) -> Placement:
        x = 0.0
        for ch in self.float_chains:
            if ch.kind not in ("rail", "port"):
                raise PlaceError(f"passive-only sheet: chain rooted on "
                                 f"{ch.root!r} is not rail- or port-rooted")
            if ch.kind == "port":
                self.label(ch.root, x, 0.0, 90)
                cur = (x, gceil(2 * U))
                self.pl.plan(ch.root, (x, 0.0), cur)
            else:
                self.power(ch.root, x, 0.0)
                cur = (x, 0.0)
            cur_net = ch.root
            for ref, upper, lower in ch.legs:
                near = upper if upper == cur_net else lower
                far_pt, far = self._vertical_2pin(ref, x, cur[1], near,
                                                  downward=True)
                cur, cur_net = far_pt, far
                self._chain_mid_features(ch, cur_net, cur)
            if self.c.nets[cur_net].net_class in (NetClass.POWER,
                                                  NetClass.GROUND):
                end_c = (cur[0], round(cur[1] + 2 * U, 3))
                self.pl.plan(cur_net, cur, end_c)
                self.power(cur_net, *end_c, self._power_rot(cur_net, True))
            _, _, ex1, _ = self._extent()
            x = gceil(ex1 + 2 * self.sp.cap_pitch)
        self._rail_decoupling_columns()
        self._flags_row()
        return self.pl

    def _rail_decoupling_columns(self) -> None:
        if not self.cluster:
            return
        ex0, _, _, ey1 = self._extent()
        x = gsnap(ex0 + 8 * U)
        y0 = gceil(ey1 + 8 * U)
        for rail in sorted(self.cluster):
            for ref in self.cluster[rail]:
                self.power(rail, x, y0)
                far_pt, far = self._vertical_2pin(ref, x, y0, rail,
                                                  downward=True)
                assert self.c.nets[far].net_class is NetClass.GROUND, (
                    f"{ref}: rail-decoupling cap far pin on {far!r} is not "
                    f"GROUND (a true rail-to-rail cap has no GND foot)")
                self.power(far, *far_pt, self._power_rot(far, True))
                x = gceil(x + 2 * self.sp.cap_pitch)
        self.cluster = {}

    CONN_RUN = 10.16
    CONN_COL_GAP = 1.27
    CONN_MID_GAP = 2.54
    CONN_STRIP_STUB = 2.54
    CONN_STRIP_BAR = 2.54
    CONN_EXT = 2.54
    CONN_ROW = 2.54

    @staticmethod
    def _glabel_len(net: str) -> float:
        return tm.text_wh(net)[0] + tm.GLABEL_PAD_LEN * tm.SIZE

    def _power_at(self, net: str, x: float, y: float, rot: int,
                  val_pos: tuple[float, float] | None) -> None:
        lib_id = self._power_lib(net)
        sdef = self.lib.get(lib_id)
        self._pwr += 1
        ref = f"#PWR{self._pwr:02d}"
        show = val_pos is not None
        vrot = 90 if rot in (90, 270) else 0
        pw = PlacedPower(lib_id, net, ref, x, y, rot, net=net,
                         val_pos=(val_pos[0], val_pos[1], vrot) if show else None,
                         show_value=show)
        self.pl.powers.append(pw)
        self.pl.boxes.append(body_box_page(sdef, x, y, rot, "body", ref))
        if show:
            self.pl.boxes.append(Box(*tm.centered_box(net, val_pos[0],
                                                      val_pos[1]),
                                     "value", ref))

    def _connector_template(self, jref: str) -> Placement:
        c, lib, sp = self.c, self.lib, self.sp
        pl = self.pl
        part = c.parts[jref]
        sdef = lib.get(part.lib_id)
        ax, ay = 0.0, 0.0

        def out(sgn: int, mag: float) -> float:
            return sgn * gceil(mag)

        body = body_box_page(sdef, ax, ay, 0, "body", jref)
        ref_pos = (ax, body.y0 - 1.27, 0)
        val_pos = (ax, ay, 90)
        pl.parts.append(PlacedPart(jref, part.lib_id, part.value, ax, ay, 0,
                                   part.footprint, ref_pos=ref_pos,
                                   val_pos=val_pos))
        pl.boxes.append(body)
        pl.boxes.append(Box(*tm.centered_box(jref, ref_pos[0], ref_pos[1]),
                            "reference", jref))
        pl.boxes.append(Box(*tm.centered_box(part.value, val_pos[0], val_pos[1],
                                             vertical=True), "value", jref))
        pl.boxes.extend(_pin_text_boxes(sdef, pl.parts[-1]))
        self._done.add(jref)

        for side_rot, sgn in ((0, -1), (180, +1)):
            rows = sorted(((pin_page_position(p, ax, ay, 0), p)
                           for p in sdef.pins if p.rotation == side_rot),
                          key=lambda t: t[0][1])
            ports: list[tuple[float, float, str]] = []
            rails: dict[str, list[tuple[float, float]]] = {}
            for (px, py), pin in rows:
                net = c.net_of(PinRef(jref, pin.number))
                if net is None:
                    pl.no_connects.append(NoConnect(px, py))
                    continue
                if net.net_class is NetClass.PORT:
                    ports.append((py, px, net.name))
                else:
                    rails.setdefault(net.name, []).append((py, px))

            lx_inner = sgn * (5.08 + self.CONN_RUN)
            cols: list[str] = []
            prev_y = prev_col = None
            for y, _, _ in ports:
                col = ("outer" if prev_y is not None
                       and abs(y - prev_y - self.CONN_ROW) < 1e-6
                       and prev_col == "inner"
                       else "inner")
                cols.append(col)
                prev_y, prev_col = y, col
            inner_len = max((self._glabel_len(n)
                             for (y, x, n), cl in zip(ports, cols, strict=False)
                             if cl == "inner"), default=0.0)
            lx_outer = out(sgn, abs(lx_inner) + inner_len + self.CONN_COL_GAP)
            outer_len = max((self._glabel_len(n)
                             for (y, x, n), cl in zip(ports, cols, strict=False)
                             if cl == "outer"), default=0.0)
            for (y, px, net), col in zip(ports, cols, strict=False):
                lx = lx_inner if col == "inner" else lx_outer
                pl.plan(net, (px, y), (lx, y))
                self.label(net, lx, y, 180 if sgn < 0 else 0)
            label_edge = max(abs(lx_outer) + outer_len,
                             abs(lx_inner) + inner_len)

            port_ys = [y for y, _, _ in ports]
            y_lo = min(port_ys) if port_ys else float("inf")
            y_hi = max(port_ys) if port_ys else float("-inf")
            mid_x = out(sgn, label_edge + self.CONN_MID_GAP)
            strip_reach = 0.0
            gnd_items = []

            def trunk(net: str, taps: list[tuple[float, float]],
                      x_r: float) -> None:
                for y, px in taps:
                    pl.plan(net, (px, y), (x_r, y))
                ys = [y for y, _ in taps]
                for y0, y1 in zip(ys, ys[1:], strict=False):
                    pl.plan(net, (x_r, y0), (x_r, y1))

            def cluster_taps(taps: list[tuple[float, float]]
                             ) -> list[list[tuple[float, float]]]:
                groups: list[list[tuple[float, float]]] = []
                for t in taps:
                    if groups and abs(t[0] - groups[-1][-1][0]
                                      - self.CONN_ROW) < 1e-6:
                        groups[-1].append(t)
                    else:
                        groups.append([t])
                return groups

            def place_power_cluster(net: str,
                                    taps: list[tuple[float, float]],
                                    rails=rails, sgn=sgn, y_lo=y_lo,
                                    lx_inner=lx_inner, y_hi=y_hi,
                                    mid_x=mid_x) -> None:
                ys = [y for y, _ in taps]
                foreign = [y for rn, rt in rails.items() if rn != net
                           for y, _ in rt if ys[0] < y < ys[-1]]
                assert not foreign, (f"{net}: foreign rail row inside cluster "
                                     f"span on side {sgn} — extend the engine")
                if ys[-1] < y_lo:
                    trunk(net, taps, lx_inner)
                    pl.plan(net, (lx_inner, ys[0]),
                            (lx_inner, ys[0] - self.CONN_EXT))
                    self.power(net, lx_inner, ys[0] - self.CONN_EXT, 0)
                elif ys[0] > y_hi:
                    trunk(net, taps, lx_inner)
                    pl.plan(net, (lx_inner, ys[-1]),
                            (lx_inner, ys[-1] + self.CONN_EXT))
                    self.power(net, lx_inner, ys[-1] + self.CONN_EXT, 180)
                else:
                    nonlocal strip_reach
                    trunk(net, taps, mid_x)
                    y_end = ys[0]
                    anchor = (mid_x + sgn * self.CONN_STRIP_STUB, y_end)
                    pl.plan(net, (mid_x, y_end), anchor)
                    w = tm.text_wh(net)[0]
                    vx = anchor[0] + sgn * (self.CONN_STRIP_BAR + 0.42 + w / 2)
                    self._power_at(net, anchor[0], anchor[1],
                                   90 if sgn < 0 else 270, (vx, y_end))
                    strip_reach = max(strip_reach,
                                      self.CONN_STRIP_STUB
                                      + self.CONN_STRIP_BAR + 0.42 + w + 0.5)

            for net, taps in rails.items():
                if c.nets[net].net_class is NetClass.GROUND:
                    gnd_items.append((net, taps))
                    continue
                for cl in cluster_taps(taps):
                    place_power_cluster(net, cl)

            inner_limit = max(label_edge, abs(mid_x) + strip_reach)
            x_g = out(sgn, inner_limit + 5.08)
            for net, taps in gnd_items:
                trunk(net, taps, x_g)
                y_bot = taps[-1][0]
                pl.plan(net, (x_g, y_bot), (x_g, y_bot + self.CONN_EXT))
                self.power(net, x_g, y_bot + self.CONN_EXT, 0)

        rail_nets = sorted(n.name for n in c.nets.values()
                           if n.net_class in (NetClass.POWER, NetClass.GROUND))
        flag_y = gceil(self._extent()[3] + 8 * U)
        fx = gsnap(-sp.flag_pitch * (len(rail_nets) - 1) / 2)
        for net in rail_nets:
            if c.nets[net].net_class is NetClass.GROUND:
                self.power(net, fx, flag_y)
                pl.plan(net, (fx, flag_y), (fx, flag_y - 2.54))
                self.flag(net, fx, flag_y - 2.54, 0)
            else:
                self.power(net, fx, flag_y)
                pl.plan(net, (fx, flag_y), (fx, flag_y + 2.54))
                self.flag(net, fx, flag_y + 2.54, 180)
            fx += sp.flag_pitch
        return pl

    def _detect_stages(self) -> dict[str, dict]:
        stages: dict[str, dict] = {}
        for ref in self.multi:
            part = self.c.parts[ref]
            sdef = self.lib.get(part.lib_id)
            for p in sdef.pins:
                if p.etype not in ("power_out", "output"):
                    continue
                net = self.net_of(ref, p.number)
                if net is None:
                    continue
                if net.net_class is NetClass.POWER and p.etype == "power_out":
                    stages[ref] = {"kind": "ldo", "out": net.name}
                    break
                if net.net_class is NetClass.SIGNAL:
                    pl_ind = [(r, rl) for sig, lst in self.pull.items()
                              if sig == net.name for r, rl in lst
                              if self.c.parts[r].lib_id == "Device:L"]
                    if pl_ind:
                        r, out_rail = pl_ind[0]
                        stages[ref] = {"kind": "buck", "sw": net.name,
                                       "l": r, "out": out_rail}
                        break
            if ref not in stages:
                st = self._detect_buck_topology(ref, sdef)
                if st is not None:
                    stages[ref] = st
        return stages

    def _detect_buck_topology(self, ref: str, sdef: SymbolDef) -> dict | None:
        for p in sdef.pins:
            net = self.net_of(ref, p.number)
            if net is None or net.net_class is not NetClass.SIGNAL:
                continue
            for r, out_rail in self.pull.get(net.name, []):
                if self.c.parts[r].lib_id == "Device:L":
                    return {"kind": "buck", "sw": net.name,
                            "l": r, "out": out_rail}
            for r, a, b in self.series:
                if net.name not in (a, b) \
                        or self.c.parts[r].lib_id != "Device:L":
                    continue
                far = b if a == net.name else a
                if self.c.nets[far].net_class is NetClass.POWER:
                    return {"kind": "buck", "sw": net.name,
                            "l": r, "out": far}
        return None

    def _regulator_template(self, stages: dict[str, dict]) -> Placement:
        c = self.c
        produced = {st["out"]: ref for ref, st in stages.items()}
        consumed: dict[str, str] = {}
        for ref in self.multi:
            if ref not in stages:
                continue
            sdef = self.lib.get(c.parts[ref].lib_id)
            out_rail = stages[ref]["out"]
            for p in sdef.pins:
                n = self.net_of(ref, p.number)
                if n is not None and n.net_class is NetClass.POWER \
                        and not n.name.startswith("GND") and n.name != out_rail:
                    consumed.setdefault(n.name, ref)
        out_caps: dict[str, list[str]] = {}
        in_caps: dict[str, list[str]] = {}
        for rail, caps in list(self.cluster.items()):
            prod = produced.get(rail)
            cons = consumed.get(rail)
            if prod and cons:
                k = (len(caps) + 1) // 2
                out_caps[rail] = caps[:k]
                in_caps[rail] = caps[k:]
            elif prod:
                out_caps[rail] = caps
            elif cons:
                in_caps[rail] = caps
            else:
                continue
            del self.cluster[rail]
        order: list[str] = []
        avail = {r for r in consumed if r not in produced}
        pool = [r for r in self.multi if r in stages]
        while pool:
            for ref in pool:
                in_rail = self._stage_in_rail(ref)
                if in_rail in avail or in_rail is None:
                    order.append(ref)
                    avail.add(stages[ref]["out"])
                    pool.remove(ref)
                    break
            else:
                order.append(pool.pop(0))
        aux = [r for r in self.multi if r not in stages]
        box_buck = {r for r, s in stages.items()
                    if s.get("kind") == "buck"
                    and not self._stage_has_left_input(r)}
        self._n_box_bucks = len(box_buck)
        ay = 0.0
        for i, ref in enumerate(order):
            st = stages[ref]
            self._stage_row(ref, st, ay, in_caps, out_caps)
            has_next = i + 1 < len(order)
            gap = 28 * U if (ref in box_buck and has_next) else 10 * U
            ay = gceil(self._extent()[3] + gap)
        handled: set = set()
        for ref in aux:
            reach = 0.0
            sdef = self.lib.get(c.parts[ref].lib_id)
            for p in sdef.pins:
                if p.rotation != 270:
                    continue
                n = self.net_of(ref, p.number)
                if n is None:
                    continue
                for ch in self.float_chains:
                    if ch.kind == "pin" and ch.root == n.name:
                        reach = max(reach, len(ch.legs) * 7.62 + 10 * U
                                    - p.y - sdef.body[3])
            rot = self.orient.get(ref, 0)
            bb = body_box_page(sdef, 0.0, 0.0, rot, "body", ref)
            ex0, ey0, ex1, ey1 = self._extent()
            ay_ref = gceil(max(ay + reach, ey1 + 4 * U - bb.y0))
            pending = 0.0
            if self.pull or self.hang:
                pending += 24 * U
            if self.float_chains:
                pending += 24 * U
            if ay_ref + bb.y1 - ey0 > PAPER_H_BUDGET - pending and ex1 > ex0:
                ax = gceil(ex1 + self._side_reach(ref, "left") + 4 * U)
                self._cell(ref, ax, gceil(ey0 - bb.y0), handled, {})
            else:
                self._cell(ref, 0.0, ay_ref, handled, {})
            ay = gceil(self._extent()[3] + 10 * U)
        self._leftover_chains_columns()
        self._port_strap_columns()
        self._pull_rank_columns()
        if self.cluster:
            first = next((r for r in self.multi if r in stages), None)
            if first is not None:
                pp0 = next(p for p in self.pl.parts if p.ref == first)
                sdef0 = self.lib.get(pp0.lib_id)
                body0 = body_box_page(sdef0, pp0.x, pp0.y, pp0.rotation,
                                      "body", first)
                self._decoupling_cluster(pp0.x, pp0.y, body0)
        if self.cluster:
            raise PlaceError(f"regulator template: unassigned decoupling caps "
                             f"{self.cluster}")
        self._flags_row()
        return self.pl

    def _stage_in_rail(self, ref: str) -> str | None:
        sdef = self.lib.get(self.c.parts[ref].lib_id)
        for p in sdef.pins:
            if p.etype == "power_in" and p.rotation == 0:
                n = self.net_of(ref, p.number)
                if n is not None and n.net_class is NetClass.POWER:
                    return n.name
        return None

    def _is_fb_pin(self, pin: Pin, net: str, out_rail: str) -> bool:
        nm = (pin.name or "").upper().replace("/", "").replace("_", "")
        named_fb = nm in ("FB", "FEEDBACK", "VFB", "VSENSE", "FBVSENSE")
        named_other = nm in ("BIAS", "VCC", "RT", "PGOOD", "SS", "COMP",
                             "ENSYNC", "EN")
        if named_other:
            return False
        pulls = self.pull.get(net, [])
        top_to_out = any(rl == out_rail
                         and self.c.parts[r].lib_id == "Device:R"
                         for r, rl in pulls)
        return named_fb or top_to_out

    def _stage_fb_net(self, ref: str, st: dict) -> str | None:
        out_rail = st.get("out")
        for p in self.lib.get(self.c.parts[ref].lib_id).pins:
            n = self.net_of(ref, p.number)
            if n is None or n.net_class is not NetClass.SIGNAL:
                continue
            if (n.name in self.pull or n.name in self.hang) \
                    and self._is_fb_pin(p, n.name, out_rail):
                return n.name
        return None

    def _stage_has_left_input(self, ref: str) -> bool:
        in_rail = self._stage_in_rail(ref)
        if in_rail is None:
            return False
        sdef = self.lib.get(self.c.parts[ref].lib_id)
        for p in sdef.pins:
            if p.rotation != 0:
                continue
            n = self.net_of(ref, p.number)
            if n is not None and n.name == in_rail:
                return True
        return False

    def _buck_box_stage(self, ref: str, st: dict, ay: float,
                        in_caps: dict[str, list[str]],
                        out_caps: dict[str, list[str]]) -> None:
        sp = self.sp
        in_rail = self._stage_in_rail_box(ref)
        pp, sdef, body, sides = self._place_body(ref, 0.0, ay)
        pins = {p.number: pin_page_position(p, 0.0, ay, 0) for p in sdef.pins}

        top_pins = sorted(((pins[p.number], p) for p in sdef.pins
                           if p.rotation == 270), key=lambda t: t[0][0])
        in_pts = [pt for pt, p in top_pins
                  if (n := self.net_of(ref, p.number)) is not None
                  and n.name == in_rail]
        if len(in_pts) > 1:
            self._rail_bus(in_rail, in_pts, "top")
        elif in_pts:
            self._rail_stub(in_rail, in_pts[0], "top")
        in_xs = [pt[0] for pt in in_pts]
        for pt, p in top_pins:
            n = self.net_of(ref, p.number)
            if n is None:
                self.pl.no_connects.append(NoConnect(*pt))
                continue
            if n.name == in_rail or n.net_class in (NetClass.POWER,
                                                    NetClass.GROUND):
                continue
            chain = self._local_drop_chain(n.name, ref)
            if chain is not None:
                tside = "left" if (in_xs and pt[0] < min(in_xs)) else "right"
                self._stack_from_pin(chain, pt, "top", text_side=tside)
                for _cref, _u, _l in chain.legs:
                    self.hang.pop(n.name, None)
                    self.pull.pop(n.name, None)
            else:
                self._signal_islet_drop(n.name, pt, "top")
        for refc in in_caps.pop(in_rail, []):
            self.cluster.setdefault(in_rail, []).append(refc)

        gnd_groups: dict[str, list] = {}
        for p in sdef.pins:
            if p.rotation != 90:
                continue
            n = self.net_of(ref, p.number)
            if n is None:
                self.pl.no_connects.append(NoConnect(*pins[p.number]))
            elif n.net_class is NetClass.GROUND:
                gnd_groups.setdefault(n.name, []).append(pins[p.number])
        for gnet, gpts in gnd_groups.items():
            gpts = sorted(gpts, key=lambda t: t[0])
            if len(gpts) > 1:
                self._rail_bus(gnet, gpts, "bottom")
            else:
                self._rail_stub(gnet, gpts[0], "bottom")

        fb_net_name = self._stage_fb_net(ref, st)
        self._buck_right(ref, st, ay, pins, sdef, out_caps)
        for p in sdef.pins:
            if p.rotation != 180:
                continue
            n = self.net_of(ref, p.number)
            if n is None:
                continue
            if n.name == fb_net_name:
                continue
            if n.net_class is NetClass.PORT:
                pe = pins[p.number]
                lx = round(pe[0] + sp.port_run, 3)
                self.pl.plan(n.name, pe, (lx, pe[1]))
                shape = {"input": "input", "output": "output"}.get(
                    p.etype, "bidirectional")
                self.label(n.name, lx, pe[1], 0, shape=shape)
            elif n.net_class is NetClass.SIGNAL and (
                    n.name in self.pull or n.name in self.hang):
                self._box_right_pin_islet(n.name, pins[p.number])

        left_pins = sorted(((pins[p.number], p) for p in sdef.pins
                            if p.rotation == 0), key=lambda t: -t[0][1])
        for pt, p in left_pins:
            n = self.net_of(ref, p.number)
            if n is None:
                self.pl.no_connects.append(NoConnect(*pt))
                continue
            name = n.name
            if name == fb_net_name:
                continue
            self._box_left_pin_islet(name, pt, body)
        self._part_texts(pp, body)

    def _box_right_pin_islet(self, name: str, pt: tuple[float, float]) -> None:
        sp = self.sp
        rx = round(pt[0] + sp.port_run, 3)
        for _k in range(8):
            lb = tm.llabel_box(name, rx, pt[1], 0)
            if self._spot_free(lb) and self._corridor_free(
                    pt[1], pt[0] + 0.01, rx, {name}):
                self.pl.plan(name, pt, (rx, pt[1]))
                self.llabel(name, rx, pt[1], 0)
                self._bridge(name)
                return
            rx = gceil(rx + 2 * U)
        raise PlaceError(f"box-buck right pin {name}: no clear islet escape")

    def _box_left_pin_islet(self, name: str, pt: tuple[float, float],
                            body: Box) -> None:
        sp = self.sp
        lx = round(pt[0] - sp.port_run, 3)
        for _k in range(6):
            lb = tm.llabel_box(name, lx, pt[1], 180)
            if self._spot_free(lb) and self._corridor_free(
                    pt[1], pt[0] - 0.01, lx, {name}):
                self.pl.plan(name, pt, (lx, pt[1]))
                self.llabel(name, lx, pt[1], 180)
                self._bridge(name)
                return
            lx = gfloor(lx - 2 * U)
        xv = pt[0]
        for down in (True, False):
            edge = body.y1 if down else body.y0
            far = gceil(edge + 28 * U) if down else gfloor(edge - 28 * U)
            step = 2 * U if down else -2 * U
            if not self._vband_stem_free(xv, *sorted((pt[1], far)), {name}):
                continue
            dy = gceil(edge + 4 * U) if down else gfloor(edge - 4 * U)
            for _kd in range(28):
                lbl = (round(xv + sp.port_run, 3), dy)
                lb = tm.llabel_box(name, lbl[0], lbl[1], 0)
                ylo, yhi = sorted((pt[1], dy))
                if self._spot_free(lb) \
                        and self._spot_free((xv - 0.15, ylo + 0.2,
                                             xv + 0.15, yhi - 0.2), pad=0.0) \
                        and self._corridor_free(dy, xv - 0.01, lbl[0], {name}):
                    self.pl.plan(name, pt, (xv, dy), lbl)
                    self.llabel(name, *lbl, 0)
                    self._bridge(name)
                    return
                dy = round(dy + step, 3)
        body_mid = (body.y0 + body.y1) / 2
        prefer_up = pt[1] < body_mid
        for up in (prefer_up, not prefer_up):
            xv = gfloor(pt[0] - 2 * U)
            edge = body.y0 if up else body.y1
            b0 = (edge - 24 * U, edge - U) if up else (edge + U, edge + 24 * U)
            for _kx in range(8):
                if self._vband_stem_free(xv, b0[0], b0[1], {name}) \
                        and self._corridor_free(pt[1], pt[0] - 0.01, xv, {name}):
                    break
                xv = gfloor(xv - 2 * U)
            step = -2 * U if up else 2 * U
            dy = gfloor(edge - 4 * U) if up else gceil(edge + 4 * U)
            for _ky in range(24):
                lbl = (round(xv + sp.port_run, 3), dy)
                lb = tm.llabel_box(name, lbl[0], lbl[1], 0)
                ylo, yhi = sorted((pt[1], dy))
                if self._spot_free(lb) \
                        and self._spot_free((xv - 0.15, ylo + 0.2,
                                             xv + 0.15, yhi - 0.2), pad=0.0) \
                        and self._corridor_free(dy, xv - 0.01, lbl[0], {name}):
                    self.pl.plan(name, pt, (xv, pt[1]), (xv, dy), lbl)
                    self.llabel(name, *lbl, 0)
                    self._bridge(name)
                    return
                dy = round(dy + step, 3)
        raise PlaceError(f"box-buck left pin {name}: no clear islet escape")

    def _stage_in_rail_box(self, ref: str) -> str:
        out_rail = self._stages_out(ref)
        for p in self.lib.get(self.c.parts[ref].lib_id).pins:
            n = self.net_of(ref, p.number)
            if n is not None and n.net_class is NetClass.POWER \
                    and not n.name.startswith("GND") and n.name != out_rail:
                return n.name
        raise PlaceError(f"{ref}: box buck stage with no input rail")

    def _stages_out(self, ref: str) -> str | None:
        st = self._detect_buck_topology(ref, self.lib.get(
            self.c.parts[ref].lib_id))
        return st["out"] if st else None

    def _stage_row(self, ref: str, st: dict, ay: float,
                   in_caps: dict[str, list[str]],
                   out_caps: dict[str, list[str]]) -> None:
        if st["kind"] == "buck" and not self._stage_has_left_input(ref):
            self._buck_box_stage(ref, st, ay, in_caps, out_caps)
            return
        sp = self.sp
        pp, sdef, body, sides = self._place_body(ref, 0.0, ay)
        pins = {p.number: pin_page_position(p, 0.0, ay, 0)
                for p in sdef.pins}
        p_in = p_en = p_gnd = p_en_uvlo = None
        p_aux: list = []
        p_biased: list = []
        gnd_pts: list = []
        in_rail_name = self._stage_in_rail(ref)
        for p in sdef.pins:
            net = self.net_of(ref, p.number)
            if net is None:
                continue
            if p.rotation == 0 and p.etype == "power_in" \
                    and net.net_class is NetClass.POWER:
                p_in = (pins[p.number], net.name)
            elif p.rotation == 0 and net.net_class is NetClass.PORT:
                p_en = (pins[p.number], net.name, p.etype)
            elif p.rotation == 0 and p.etype == "power_out" \
                    and net.net_class is NetClass.SIGNAL \
                    and self._local_drop_chain(net.name, ref) is not None:
                p_aux.append((pins[p.number], net.name))
            elif p.rotation == 0 and net.net_class is NetClass.SIGNAL \
                    and len(self.pull.get(net.name, [])) == 1 \
                    and len(self.hang.get(net.name, [])) == 1 \
                    and self.pull[net.name][0][1] != in_rail_name:
                p_biased.append((pins[p.number], net.name))
            elif p.rotation == 0 and net.net_class is NetClass.SIGNAL \
                    and net.name in self.pull and net.name in self.hang:
                p_en_uvlo = (pins[p.number], net.name)
            elif p.rotation == 90 and net.net_class is NetClass.GROUND:
                p_gnd = (pins[p.number], net.name)
                gnd_pts.append(pins[p.number])
        if p_in is None or p_gnd is None:
            raise PlaceError(f"{ref}: regulator stage without VIN/GND pins")

        if p_en is not None:
            (pe, en_net, etype) = p_en
            lx = pe[0] - sp.port_run
            self.pl.plan(en_net, pe, (lx, pe[1]))
            self.label(en_net, lx, pe[1], 180,
                       shape="input" if etype == "input" else "bidirectional")
        (pv, in_rail) = p_in
        straps: list[tuple[float, float]] = []
        for p in sdef.pins:
            net = self.net_of(ref, p.number)
            if net is None or net.name != in_rail or p.rotation != 0:
                continue
            if pins[p.number] != pv:
                straps.append(pins[p.number])
        strap_taps = [(round(pv[0] - 2 * U * (k + 1), 3), spt)
                      for k, spt in enumerate(straps)]
        cin = in_caps.pop(in_rail, [])
        cols = [gfloor(pv[0] - sp.cluster_dx + i * -sp.cap_pitch)
                for i in range(len(cin))]
        uvlo_col = None
        uvlo_gnd = []
        if p_en_uvlo is not None:
            (_pe_u, uvlo_net) = p_en_uvlo
            (uvlo_rt, uvlo_top_rail) = self.pull[uvlo_net][0]
            if uvlo_top_rail != in_rail:
                raise PlaceError(
                    f"{ref}: EN-UVLO top {uvlo_rt} sits on "
                    f"{uvlo_top_rail!r}, not the input rail {in_rail!r} — "
                    f"unhandled topology, extend the engine")
            uvlo_gnd = sorted(self.hang[uvlo_net])
            base = gfloor(pv[0] - sp.cluster_dx + len(cin) * -sp.cap_pitch)
            uvlo_col = base
            cols = cols + [uvlo_col]
        nodes = [pv[0]] + cols + [tx for tx, _ in strap_taps]
        nodes_sorted = sorted(set(nodes))
        for xa, xb in zip(nodes_sorted, nodes_sorted[1:], strict=False):
            self.pl.plan(in_rail, (xa, pv[1]), (xb, pv[1]))
        for tx, spt in strap_taps:
            self.pl.plan(in_rail, (tx, pv[1]), (tx, spt[1]), spt)
        rail_x = cols[-1] if cols else pv[0]
        self.pl.plan(in_rail, (rail_x, pv[1]), (rail_x, pv[1] - 5.08))
        self.power(in_rail, rail_x, pv[1] - 5.08)
        cap_cols = cols[:len(cin)]
        for refc, x in zip(cin, cap_cols, strict=False):
            far_pt, far = self._vertical_2pin(refc, x, pv[1],
                                              in_rail, downward=True)
            self.power(far, *far_pt)
        if p_en_uvlo is not None and uvlo_col is not None:
            (pe_u, uvlo_net) = p_en_uvlo
            (uvlo_rt, _rail) = self.pull.pop(uvlo_net)[0]
            mid_pt, _ = self._vertical_2pin(uvlo_rt, uvlo_col, pv[1],
                                            in_rail, downward=True)
            y_mid = mid_pt[1]
            self.hang.pop(uvlo_net)
            xv = round(pe_u[0] - 2.54, 3)
            cap_floor = max([y_mid] + [b.y1 for b in self.pl.boxes
                                       if b.kind == "body" and b.owner
                                       and b.owner.startswith("#PWR")
                                       and uvlo_col < b.x0 and b.x1 < xv
                                       and b.y0 > pv[1]])
            y_tie = y_mid if cap_floor <= y_mid else gceil(cap_floor + 2 * U)
            if y_tie > y_mid:
                self.pl.plan(uvlo_net, (uvlo_col, y_mid), (uvlo_col, y_tie))
            mid_xs = [uvlo_col]
            for k, gref in enumerate(uvlo_gnd):
                gcol = uvlo_col if k == 0 else gfloor(
                    uvlo_col - (k * sp.cap_pitch))
                if k > 0:
                    mid_xs.append(gcol)
                far_pt2, far2 = self._vertical_2pin(gref, gcol, y_tie,
                                                    uvlo_net, downward=True)
                self.power(far2, *far_pt2)
            mid_xs_sorted = sorted(set(mid_xs + [xv]))
            for xa, xb in zip(mid_xs_sorted, mid_xs_sorted[1:], strict=False):
                self.pl.plan(uvlo_net, (xa, y_tie), (xb, y_tie))
            self.pl.plan(uvlo_net, pe_u, (xv, pe_u[1]), (xv, y_tie))
        (_pg, gnd_net) = p_gnd
        for gpt in sorted(set(gnd_pts)):
            self.power(gnd_net, *gpt)
        _aux_sorted = sorted(p_aux, key=lambda pn: pn[0][1])
        _naux = len(_aux_sorted)
        for _rank, (pa, aux_net) in enumerate(_aux_sorted):
            ia = _naux - 1 - _rank
            if aux_net in self.hang:
                rcref = self.hang[aux_net][0]
            else:
                rcref = self.pull[aux_net][0][0]
            xcol = gfloor(pa[0] - sp.cluster_dx - ia * sp.cap_pitch)
            far_pt, far = self._vertical_2pin(rcref, xcol, pa[1], aux_net,
                                              downward=True)
            self.power(far, *far_pt)
            self.hang.pop(aux_net, None)
            self.pull.pop(aux_net, None)
            self.pl.plan(aux_net, pa, (xcol, pa[1]))
        for (pb, bias_net) in sorted(p_biased, key=lambda pn: pn[0][1]):
            lx = round(pb[0] - sp.port_run, 3)
            for b in self.pl.boxes:
                if b.kind == "label" and b.x1 <= pb[0] \
                        and b.y0 - 2 * U <= pb[1] <= b.y1 + 2 * U:
                    lx = min(lx, gfloor(b.x0 - 2 * U))
            self.pl.plan(bias_net, pb, (lx, pb[1]))
            self.llabel(bias_net, lx, pb[1], 180)
        for p in sdef.pins:
            if self.net_of(ref, p.number) is None and p.etype != "no_connect":
                self.pl.no_connects.append(NoConnect(*pins[p.number]))

        if st["kind"] == "buck":
            self._buck_right(ref, st, ay, pins, sdef, out_caps)
        else:
            self._ldo_right(ref, st, ay, pins, sdef, out_caps)
        self._part_texts(pp, body)

    def _fb_left_network(self, ref: str, st: dict, p_fb: tuple[float, float],
                         fb_net: str, out_rail: str) -> None:
        sp = self.sp
        x = gfloor(p_fb[0] - sp.port_run - 4 * U)
        y_top = round(p_fb[1] - 4 * U, 3)
        self.power(out_rail, x, y_top, self._power_rot(out_rail, False))
        fb_pulls = self.pull.pop(fb_net)
        (rt, _rail) = fb_pulls[0]
        plain_ff = [r for r, _ra in fb_pulls[1:]]
        far_pt, _ = self._vertical_2pin(rt, x, y_top, out_rail, downward=True)
        y_mid = far_pt[1]
        rb = self.hang.pop(fb_net)[0]
        far_pt2, far2 = self._vertical_2pin(rb, x, y_mid, fb_net, downward=True)
        self.power(far2, *far_pt2, self._power_rot(far2, True))
        xv = round(p_fb[0] - 2 * U, 3)
        self.pl.plan(fb_net, p_fb, (xv, p_fb[1]), (xv, y_mid), (x, y_mid))
        xcol = gfloor(x - sp.cap_pitch)
        for cff in plain_ff:
            self.power(out_rail, xcol, y_top, self._power_rot(out_rail, False))
            ff_far, _ = self._vertical_2pin(cff, xcol, y_top, out_rail,
                                            downward=True)
            self.pl.plan(fb_net, (x, y_mid), (xcol, y_mid), (xcol, ff_far[1]))
            xcol = gfloor(xcol - sp.cap_pitch)
        ff_chains = [ch for ch in self.float_chains
                     if ch.kind == "trunk" and ch.root == fb_net
                     and len(ch.legs) == 2 and ch.legs[-1][2] == out_rail]
        for ch in ff_chains:
            (rff_ref, _a0, mid_net) = ch.legs[0]
            (cff_ref, _a1, _rail) = ch.legs[1]
            rhl = 3.81
            x_rff = xcol
            self._horizontal_2pin(rff_ref, x_rff, y_mid, mid_net)
            self.pl.plan(fb_net, (x, y_mid), (x_rff + rhl, y_mid))
            x_ff = gfloor(x_rff - sp.cap_pitch)
            self.power(out_rail, x_ff, y_top, self._power_rot(out_rail, False))
            cff_far, _ = self._vertical_2pin(cff_ref, x_ff, y_top, out_rail,
                                             downward=True)
            x_jog = gsnap((x_rff - rhl + x_ff) / 2)
            self.pl.plan(mid_net, (x_rff - rhl, y_mid), (x_jog, y_mid),
                         (x_jog, cff_far[1]), (x_ff, cff_far[1]))
            self.float_chains.remove(ch)
            xcol = gfloor(x_ff - sp.cap_pitch)

    def _buck_right(self, ref: str, st: dict, ay: float, pins, sdef,
                    out_caps: dict[str, list[str]]) -> None:
        sp = self.sp
        c = self.c
        sw_net, out_rail, l_ref = st["sw"], st["out"], st["l"]
        p_sw = p_boot = p_fb = None
        boot_net = fb_net = None
        boot_cap = None
        fb_left = False
        for p in sdef.pins:
            if p.rotation not in (0, 180):
                continue
            net = self.net_of(ref, p.number)
            if net is None:
                continue
            if net.name == sw_net and p.rotation == 180:
                p_sw = pin_page_position(p, 0.0, ay, 0)
            elif net.net_class is NetClass.SIGNAL:
                caps = [(r, a, b) for r, a, b in self.series
                        if net.name in (a, b) and sw_net in (a, b)]
                if caps and p.rotation == 180:
                    p_boot = pin_page_position(p, 0.0, ay, 0)
                    boot_net = net.name
                    boot_cap = caps[0][0]
                elif (net.name in self.pull or net.name in self.hang) \
                        and net.name != boot_net \
                        and self._is_fb_pin(p, net.name, out_rail) \
                        and p_fb is None:
                    p_fb = pin_page_position(p, 0.0, ay, 0)
                    fb_net = net.name
                    fb_left = p.rotation == 0
        if p_sw is None:
            raise PlaceError(f"{ref}: buck stage without SW pin")
        x0 = p_sw[0]
        y_sw = p_sw[1]
        x_l = round(x0 + 26.67, 3)
        slot = gceil(x_l + 9 * U)
        boot_extra = [pin_page_position(p, 0.0, ay, 0) for p in sdef.pins
                      if p.rotation == 180 and p_boot is not None
                      and (n2 := self.net_of(ref, p.number)) is not None
                      and n2.name == boot_net
                      and pin_page_position(p, 0.0, ay, 0) != p_boot]
        if p_boot is not None and boot_cap is not None:
            xv = round(x0 + 2.54, 3)
            xc = round(x0 + 10.16, 3)
            xj = round(x0 + 20.32, 3)
            boot_ys = [p_boot[1], *(pt[1] for pt in boot_extra)]
            boot_above = min(boot_ys) > y_sw + 1e-6
            if boot_above:
                yb = round(max(boot_ys) + 5.08, 3)
                riser_from = min(boot_ys)
            else:
                yb = round(min(boot_ys) - 5.08, 3)
                riser_from = max(boot_ys)
            for pt in [p_boot, *boot_extra]:
                self.pl.plan(boot_net, pt, (xv, pt[1]))
            self.pl.plan(boot_net, (xv, riser_from), (xv, yb),
                         (xc - 3.81, yb))
            self._horizontal_2pin(boot_cap, xc, yb, boot_net)
            self.pl.plan(sw_net, (xc + 3.81, yb), (xj, yb), (xj, y_sw))
            self.series = [s for s in self.series if s[0] != boot_cap]
            self.pl.plan(sw_net, p_sw, (xj, y_sw))
            self.pl.plan(sw_net, (xj, y_sw), (x0 + 26.67 - 3.81, y_sw))
        else:
            self.pl.plan(sw_net, p_sw, (x0 + 26.67 - 3.81, y_sw))
        self._horizontal_2pin(l_ref, x_l, y_sw, sw_net)
        self.pull.get(sw_net) and self.pull[sw_net].remove(
            (l_ref, out_rail))
        if self.pull.get(sw_net) == []:
            del self.pull[sw_net]
        nodes = [round(x_l + 3.81, 3)]
        for refc in out_caps.pop(out_rail, []):
            nodes.append(slot)
            far_pt, far = self._vertical_2pin(refc, slot, y_sw,
                                              out_rail, downward=True)
            self.power(far, *far_pt)
            slot = gceil(slot + sp.cap_pitch)
        if p_fb is not None and fb_net is not None and fb_left:
            self._fb_left_network(ref, st, p_fb, fb_net, out_rail)
            p_fb = None
        if p_fb is not None and fb_net is not None:
            x_div = slot
            slot = gceil(slot + sp.cap_pitch)
            nodes.append(x_div)
            self.pl.plan(out_rail, (x_div, y_sw), (x_div, y_sw + 5.08))
            fb_pulls = self.pull.pop(fb_net)
            (rt, _rail) = fb_pulls[0]
            feedfwd = [r for r, _ra in fb_pulls[1:]]
            far_pt, _ = self._vertical_2pin(rt, x_div, y_sw + 5.08,
                                            out_rail, downward=True)
            y_mid = far_pt[1]
            rb = self.hang.pop(fb_net)[0]
            far_pt2, far2 = self._vertical_2pin(rb, x_div, y_mid,
                                                fb_net, downward=True)
            self.power(far2, *far_pt2)
            xv = round(x0 + 2.54, 3)
            self.pl.plan(fb_net, p_fb, (xv, p_fb[1]), (xv, y_mid),
                         (x_div, y_mid))
            for cff in feedfwd:
                x_ff = slot
                nodes.append(x_ff)
                slot = gceil(slot + sp.cap_pitch)
                self.pl.plan(out_rail, (x_ff, y_sw), (x_ff, y_sw + 5.08))
                far_ff, _ = self._vertical_2pin(cff, x_ff, y_sw + 5.08,
                                                out_rail, downward=True)
                self.pl.plan(fb_net, (x_div, y_mid), (x_ff, y_mid),
                             (x_ff, far_ff[1]))
            ff_chains = [ch for ch in self.float_chains
                         if ch.kind == "trunk" and ch.root == fb_net
                         and len(ch.legs) == 2
                         and ch.legs[-1][2] == out_rail]
            for ch in ff_chains:
                (rff_ref, _a0, mid_net) = ch.legs[0]
                (cff_ref, _a1, _rail) = ch.legs[1]
                rhl = 3.81
                x_rff = slot
                nodes.append(x_rff)
                self._horizontal_2pin(rff_ref, x_rff, y_mid, fb_net)
                self.pl.plan(fb_net, (x_div, y_mid), (x_rff - rhl, y_mid))
                x_ff = gceil(x_rff + sp.cap_pitch)
                nodes.append(x_ff)
                slot = gceil(x_ff + sp.cap_pitch)
                self.pl.plan(out_rail, (x_ff, y_sw), (x_ff, y_sw + 5.08))
                cff_far, _ = self._vertical_2pin(cff_ref, x_ff, y_sw + 5.08,
                                                 out_rail, downward=True)
                x_jog = gsnap((x_rff + rhl + x_ff) / 2)
                self.pl.plan(mid_net, (x_rff + rhl, y_mid), (x_jog, y_mid),
                             (x_jog, cff_far[1]), (x_ff, cff_far[1]))
                self.float_chains.remove(ch)
        for ch in [ch for ch in self.float_chains
                   if ch.kind == "rail" and ch.root == out_rail]:
            nodes.append(slot)
            cur = (slot, y_sw)
            cur_net = out_rail
            for cref, upper, lower in ch.legs:
                near = upper if upper == cur_net else lower
                far_pt, far = self._vertical_2pin(cref, slot, cur[1], near,
                                                  downward=True)
                cur, cur_net = far_pt, far
            if c.nets[cur_net].net_class in (NetClass.POWER, NetClass.GROUND):
                self.power(cur_net, *cur)
            self.float_chains.remove(ch)
            slot = gceil(slot + sp.cap_pitch)
        x_r = gsnap(slot - sp.cap_pitch / 2)
        nodes.append(x_r)
        nodes = sorted(set(nodes))
        for xa, xb in zip(nodes, nodes[1:], strict=False):
            self.pl.plan(out_rail, (xa, y_sw), (xb, y_sw))
        self.pl.plan(out_rail, (x_r, y_sw), (x_r, y_sw - 5.08))
        self.power(out_rail, x_r, y_sw - 5.08)

    def _ldo_right(self, ref: str, st: dict, ay: float, pins, sdef,
                   out_caps: dict[str, list[str]]) -> None:
        sp = self.sp
        out_rail = st["out"]
        p_out = None
        for p in sdef.pins:
            if p.rotation == 180 and p.etype == "power_out":
                p_out = pin_page_position(p, 0.0, ay, 0)
        assert p_out is not None
        y_r = p_out[1]
        slot = gceil(p_out[0] + 2 * U + 5.08)
        nodes = [p_out[0]]
        for refc in out_caps.pop(out_rail, []):
            nodes.append(slot)
            far_pt, far = self._vertical_2pin(refc, slot, y_r,
                                              out_rail, downward=True)
            self.power(far, *far_pt)
            slot = gceil(slot + sp.cap_pitch)
        x_r = gsnap(slot - sp.cap_pitch / 2)
        nodes.append(x_r)
        nodes = sorted(set(nodes))
        for xa, xb in zip(nodes, nodes[1:], strict=False):
            self.pl.plan(out_rail, (xa, y_r), (xb, y_r))
        self.pl.plan(out_rail, (x_r, y_r), (x_r, y_r - 5.08))
        self.power(out_rail, x_r, y_r - 5.08)

    def _leftover_chains_columns(self) -> None:
        chains = [c for c in self.float_chains if c.kind == "rail"]
        if not chains:
            return
        below = len(chains) > 2
        if below:
            ex0, _, _, ey1 = self._extent()
            x = gsnap(ex0 + 4 * U)
            y0 = gceil(ey1 + 8 * U)
            pitch = gceil(max(tm.text_wh(ch.root)[0] for ch in chains) / 2
                          + 2 * self.sp.cap_pitch)
        for ch in chains:
            if not below:
                _, _, ex1, _ = self._extent()
                x = gceil(ex1 + 2 * self.sp.cap_pitch)
                y0 = 0.0
            self.power(ch.root, x, y0)
            cur = (x, y0)
            cur_net = ch.root
            for ref, upper, lower in ch.legs:
                near = upper if upper == cur_net else lower
                far_pt, far = self._vertical_2pin(ref, x, cur[1], near,
                                                  downward=True)
                cur, cur_net = far_pt, far
                self._chain_mid_features(ch, cur_net, cur)
            if self.c.nets[cur_net].net_class in (NetClass.POWER,
                                                  NetClass.GROUND):
                end_c = (cur[0], round(cur[1] + 2 * U, 3))
                self.pl.plan(cur_net, cur, end_c)
                self.power(cur_net, *end_c, self._power_rot(cur_net, True))
            self.float_chains.remove(ch)
            if below:
                x = round(x + pitch, 3)

    def _port_strap_columns(self) -> None:
        straps = [c for c in self.float_chains if c.kind == "port"]
        if not straps:
            return
        ex0, _, _, ey1 = self._extent()
        pitch = gceil(max(tm.text_wh(ch.root)[1] for ch in straps)
                      + 2 * self.sp.cap_pitch)
        x = gsnap(ex0 + 8 * U)
        y0 = gceil(ey1 + 12 * U)
        for ch in straps:
            self.label(ch.root, x, y0, 90)
            cur = (x, gceil(y0 + 2 * U))
            self.pl.plan(ch.root, (x, y0), cur)
            cur_net = ch.root
            for ref, upper, lower in ch.legs:
                near = upper if upper == cur_net else lower
                far_pt, far = self._vertical_2pin(ref, x, cur[1], near,
                                                  downward=True)
                cur, cur_net = far_pt, far
                self._chain_mid_features(ch, cur_net, cur)
            if self.c.nets[cur_net].net_class in (NetClass.POWER,
                                                  NetClass.GROUND):
                end_c = (cur[0], round(cur[1] + 2 * U, 3))
                self.pl.plan(cur_net, cur, end_c)
                self.power(cur_net, *end_c, self._power_rot(cur_net, True))
            self.float_chains.remove(ch)
            x = round(x + pitch, 3)

    def _collect_trunk_pins(self, ref: str, ax: float, ay: float,
                            trunk_jobs: dict[str, _Trunk],
                            srung_keys: set[tuple[str, str, str]]) -> None:
        for t in trunk_jobs.values():
            for (_r, num, side, tip) in self._side_tips(ref):
                if self._on_net(ref, num, t.net):
                    t.direct.append(((round(ax + tip[0], 3),
                                      round(ay + tip[1], 3)), side))
        for (_r, num, side, tip) in self._side_tips(ref):
            if (ref, num, side) not in srung_keys:
                continue
            n = self.net_of(ref, num)
            assert n is not None
            t = self._rung_of(n.name, trunk_jobs)
            assert t is not None
            legs = [rr for rr, a, b in self.series
                    if t.net in (a, b) and n.name in (a, b)]
            t.rungs.append((n.name, (round(ax + tip[0], 3),
                                     round(ay + tip[1], 3)),
                            side, legs, 0.0))

    def _shunt_cells(self, handled: set[tuple[str, str, str]]) -> None:
        for ref in self.shunts:
            if ref in self._done:
                continue
            ex0, _, _, ey1 = self._extent()
            sdef = self.lib.get(self.c.parts[ref].lib_id)
            ay = gceil(ey1 + 8 * U - sdef.body[1])
            ax = gsnap(ex0 - sdef.body[0] + 16 * U)
            for n in self.c.nets.values():
                if n.net_class in (NetClass.SIGNAL, NetClass.PORT) \
                        and any(pr.ref == ref for pr in n.pins):
                    self._bridge(n.name)
            self._cell(ref, ax, ay, handled, {})

    def _pull_rank_columns(self) -> None:
        if not (self.pull or self.hang):
            return
        by_rail: dict[str, list[tuple[str, str]]] = {}
        for sig in sorted(self.pull):
            for pref, rail in self.pull[sig]:
                by_rail.setdefault(rail, []).append((pref, sig))
        for sig in sorted(self.hang):
            for pref in self.hang[sig]:
                sig_pin = self._pin_of_net(pref, sig)
                far = self.net_of(pref, self.other_pin(pref, sig_pin))
                assert far is not None
                by_rail.setdefault(far.name, []).append((pref, sig))
        self.pull = {}
        self.hang = {}
        ex0, _, _, ey1 = self._extent()
        x = gsnap(ex0 + 8 * U)
        bar_y = gceil(ey1 + 10 * U)
        for rail, cols in sorted(by_rail.items()):
            pitch = gceil(max(tm.text_wh(s)[0] for _p, s in cols) + 4 * U)
            is_gnd = self.c.nets[rail].net_class is NetClass.GROUND
            xs: list[float] = []
            for pref, sig in cols:
                xs.append(x)
                if is_gnd:
                    knee = (x, round(bar_y - 2 * U, 3))
                    elbow = (round(x + 2 * U, 3), knee[1])
                    self.pl.plan(sig, knee, (x, bar_y))
                    self.pl.plan(sig, knee, elbow)
                    self.llabel(sig, *elbow, 0)
                    self._bridge(sig)
                    far_pt, far = self._vertical_2pin(pref, x, bar_y, sig,
                                                      downward=True)
                    assert far == rail
                    self.power(rail, *far_pt, self._power_rot(rail, True))
                    x = round(x + pitch, 3)
                    continue
                far_pt, far = self._vertical_2pin(pref, x, bar_y, rail,
                                                  downward=True)
                assert far == sig
                if self.c.nets[sig].net_class in (NetClass.POWER,
                                                  NetClass.GROUND):
                    self.power(sig, *far_pt, self._power_rot(sig, True))
                else:
                    elbow = (round(far_pt[0] + 2 * U, 3),
                             round(far_pt[1] + 2 * U, 3))
                    self.pl.plan(sig, far_pt, (far_pt[0], elbow[1]))
                    self.pl.plan(sig, (far_pt[0], elbow[1]), elbow)
                    self.llabel(sig, *elbow, 0)
                    self._bridge(sig)
                x = round(x + pitch, 3)
            if is_gnd:
                pass
            elif len(xs) == 1:
                self.power(rail, xs[0], bar_y)
            else:
                xm = gsnap((xs[0] + xs[-1]) / 2)
                nodes = sorted(set(xs + [xm]))
                for a, b in zip(nodes, nodes[1:], strict=False):
                    self.pl.plan(rail, (a, bar_y), (b, bar_y))
                self.pl.plan(rail, (xm, bar_y), (xm, bar_y - 2 * U))
                self.power(rail, xm, bar_y - 2 * U)
            x = round(x + 2 * U, 3)

    def _series_port_columns(self) -> None:
        left = [s for s in self.series
                if self.c.nets[s[1]].net_class is NetClass.PORT
                and self.c.nets[s[2]].net_class is NetClass.PORT]
        if not left:
            return
        ex0, _, _, ey1 = self._extent()
        x = gsnap(ex0 + 8 * U)
        y0 = gceil(ey1 + 12 * U)
        pitch = gceil(2 * self.sp.cap_pitch)
        for s in left:
            ref, a, b = s
            self.label(a, x, y0, 90)
            cur = (x, round(y0 + 2 * U, 3))
            self.pl.plan(a, (x, y0), cur)
            far_pt, far = self._vertical_2pin(ref, x, cur[1], a,
                                              downward=True)
            assert far == b
            end = (x, round(far_pt[1] + 2 * U, 3))
            self.pl.plan(b, far_pt, end)
            self.label(b, *end, 270)
            self.series.remove(s)
            x = round(x + pitch, 3)

    def _trunk_series_columns(self) -> None:
        c = self.c

        def named_sig(net: str) -> bool:
            if c.nets[net].net_class is not NetClass.SIGNAL:
                return False
            return (net in self.trunks or net in self.pl.label_bridged
                    or any(ll.name == net for ll in self.pl.llabels)
                    or any(h.name == net for h in self.pl.hlabels))

        left = [s for s in self.series
                if s[0] not in self._done
                and named_sig(s[1]) and named_sig(s[2])]
        if not left:
            return
        ex0, _, _, ey1 = self._extent()
        x = gsnap(ex0 + 8 * U)
        y0 = gceil(ey1 + 12 * U)
        pitch = gceil(2 * self.sp.cap_pitch)
        for s in left:
            ref, a, b = s
            self.llabel(a, round(x - 2 * U, 3), y0, 180)
            self._bridge(a)
            self.pl.plan(a, (round(x - 2 * U, 3), y0), (x, y0))
            cur = (x, round(y0 + 2 * U, 3))
            self.pl.plan(a, (x, y0), cur)
            far_pt, far = self._vertical_2pin(ref, x, cur[1], a, downward=True)
            assert far == b
            end = (round(x - 2 * U, 3), far_pt[1])
            self.pl.plan(b, far_pt, end)
            self.llabel(b, *end, 180)
            self._bridge(b)
            self.series.remove(s)
            x = round(x + pitch, 3)

    def _rung_islet_drop(self, far_net: str, pt: tuple[float, float],
                         sgn: int) -> None:
        lx = round(pt[0] + sgn * self.sp.port_run, 3)
        self.pl.plan(far_net, pt, (lx, pt[1]))
        self.llabel(far_net, lx, pt[1], 0 if sgn > 0 else 180)
        self._bridge(far_net)

    def _rung_islet_columns(self) -> None:
        if not self._rung_islets:
            return
        ex0, _, _, ey1 = self._extent()
        x = gsnap(ex0 + 8 * U)
        y0 = gceil(ey1 + 12 * U)
        pitch = gceil(3 * self.sp.cap_pitch)
        for trunk_net, far_net, leg in self._rung_islets:
            self.llabel(trunk_net, round(x - 2 * U, 3), y0, 180)
            self._bridge(trunk_net)
            cur = (x, round(y0 + 2 * U, 3))
            self.pl.plan(trunk_net, (round(x - 2 * U, 3), y0), (x, y0))
            self.pl.plan(trunk_net, (x, y0), cur)
            far_pt, far = self._vertical_2pin(leg, x, cur[1], trunk_net,
                                              downward=True)
            assert far == far_net
            end = (round(x - 2 * U, 3), far_pt[1])
            self.pl.plan(far_net, far_pt, end)
            self.llabel(far_net, *end, 180)
            self._bridge(far_net)
            x = round(x + pitch, 3)
        self._rung_islets = []

    def _pin_divider_columns(self) -> None:
        if not self._pin_islets:
            return
        ex0, _, _, ey1 = self._extent()
        x = gsnap(ex0 + 8 * U)
        y0 = gceil(ey1 + 12 * U)
        pitch = gceil(3 * self.sp.cap_pitch)
        for mid in sorted(self._pin_islets):
            ser = [s for s in self.series if mid in (s[1], s[2])]
            hangs = list(self.hang.get(mid, []))
            pulls = list(self.pull.get(mid, []))
            if len(ser) != 1 or (len(hangs) + len(pulls)) != 1:
                continue
            top_ref, na, nb = ser[0]
            top_net = nb if na == mid else na
            if self.c.nets[top_net].net_class is NetClass.PORT:
                self.label(top_net, x, y0, 90)
            else:
                self.power(top_net, x, y0)
            cur = (x, round(y0 + 2 * U, 3))
            self.pl.plan(top_net, (x, y0), cur)
            far_pt, far = self._vertical_2pin(top_ref, x, cur[1], top_net,
                                              downward=True)
            assert far == mid
            self.series.remove(ser[0])
            lx = round(far_pt[0] - 2 * U, 3)
            self.pl.plan(mid, far_pt, (lx, far_pt[1]))
            self.llabel(mid, lx, far_pt[1], 180)
            self._bridge(mid)
            bot_ref = hangs[0] if hangs else pulls[0][0]
            fp2, far2 = self._vertical_2pin(bot_ref, x, far_pt[1], mid,
                                            downward=True)
            end = (x, round(fp2[1] + 2 * U, 3))
            self.pl.plan(far2, fp2, end)
            self.power(far2, *end, self._power_rot(far2, True))
            self.hang.pop(mid, None)
            self.pull.pop(mid, None)
            x = round(x + pitch, 3)
        self._pin_islets = set()

    def _chain_order(self) -> list[str]:
        chain = [r for r in self.multi if r not in self.shunts]
        conns = [r for r in chain if r[0] == "J"]
        others = [r for r in chain if r[0] != "J"]

        def port_pins(r: str) -> int:
            return sum(1 for p in self.lib.pin_numbers(self.c.parts[r].lib_id)
                       if (n := self.net_of(r, p)) is not None
                       and n.net_class is NetClass.PORT)

        def nets_of(r: str) -> set[str]:
            return {n.name for n in self.c.nets.values()
                    if any(pr.ref == r for pr in n.pins)}

        def sig_nets_of(r: str) -> set[str]:
            return {n.name for n in self.c.nets.values()
                    if n.net_class in (NetClass.SIGNAL, NetClass.PORT)
                    and any(pr.ref == r for pr in n.pins)}

        pool = sorted(others, key=lambda r: -port_pins(r)) + conns
        if not pool:
            return []
        comp_of: dict[str, int] = {}
        for ref in pool:
            comp_of[ref] = pool.index(ref)
        changed = True
        while changed:
            changed = False
            for a in pool:
                for b in pool:
                    if comp_of[a] != comp_of[b] \
                            and sig_nets_of(a) & sig_nets_of(b):
                        tgt = min(comp_of[a], comp_of[b])
                        if comp_of[a] != tgt or comp_of[b] != tgt:
                            comp_of[a] = comp_of[b] = tgt
                            changed = True
        order: list[str] = []
        self._comp_starts: set[str] = set()
        for cid in sorted(set(comp_of.values())):
            sub = [r for r in pool if comp_of[r] == cid]
            sub_order = [sub.pop(0)]
            while sub:
                last = nets_of(sub_order[-1])
                sub.sort(key=lambda r: -len(last & nets_of(r)))
                sub_order.append(sub.pop(0))
            fwd, o_fwd = self._eval_chain(sub_order)
            rev, o_rev = self._eval_chain(list(reversed(sub_order)))
            if rev > fwd:
                sub_order = list(reversed(sub_order))
                self.orient.update(o_rev)
            else:
                self.orient.update(o_fwd)
            self._comp_starts.add(sub_order[0])
            order += sub_order
        return order

    def _eval_chain(self, order: list[str]):
        saved = dict(self.orient)
        best = ((-1, 0, 0), {})
        for combo in itertools.product((0, 180), repeat=len(order)):
            for ref, rot in zip(order, combo, strict=False):
                if rot:
                    self.orient[ref] = rot
                else:
                    self.orient.pop(ref, None)
            pairs = 0
            chan_rows: dict[tuple[str, str], list[float]] = {}
            for i in range(1, len(order)):
                ps = self._facing_pairs(order[i - 1], order[i])
                pairs += len(ps)
                for _n, ta, tb, _ea, _eb in ps:
                    chan_rows.setdefault((order[i - 1], "right"),
                                         []).append(ta[1])
                    chan_rows.setdefault((order[i], "left"),
                                         []).append(tb[1])
            blocked = 0
            for tname, _t in self.trunks.items():
                votes = 0
                for ref in order:
                    for (_r, _num, s2, _t2) in [
                            sd for sd in self._side_tips(ref)
                            if self._on_net(ref, sd[1], tname)]:
                        votes += 1 if s2 == "top" else \
                            -1 if s2 == "bottom" else 0
                zone_up = votes > 0
                rung_nets = {a if b == tname else b
                             for _r2, a, b in self.series
                             if tname in (a, b)}
                for ref in order:
                    for (_r, num, s2, tip) in self._side_tips(ref):
                        if s2 not in ("left", "right"):
                            continue
                        n = self.net_of(ref, num)
                        if n is None or n.name not in rung_nets:
                            continue
                        rows = chan_rows.get((ref, s2), [])
                        if zone_up and any(r2 < tip[1] - 1e-6
                                           for r2 in rows):
                            blocked += 1
                        elif not zone_up and any(r2 > tip[1] + 1e-6
                                                 for r2 in rows):
                            blocked += 1
            inward = 0
            for i, ref in enumerate(order):
                sides = (["right"] if i < len(order) - 1 else []) + \
                        (["left"] if i > 0 else [])
                for (_r, num, s, _t) in self._side_tips(ref):
                    if s not in sides:
                        continue
                    n = self.net_of(ref, num)
                    if n is None:
                        continue
                    if n.net_class is NetClass.PORT or (
                            n.net_class is NetClass.SIGNAL
                            and self._net_shared(n.name, ref)):
                        inward += 1
            score = (pairs, -blocked, -inward)
            if score > best[0]:
                best = (score, dict(zip(order, combo, strict=False)))
        self.orient = saved
        return best

    @staticmethod
    def _tip_group(tips: list[tuple[float, float]]):
        tips = sorted(tips, key=lambda t: t[1])
        if len(tips) == 1:
            return tips[0], []
        if any(abs(b[1] - a[1] - 2.54) > 1e-6
               for a, b in zip(tips, tips[1:], strict=False)):
            return None
        return tips[0], tips[1:]

    def _facing_pairs(self, a_ref: str, b_ref: str):
        out = []
        a_sides = self._side_tips(a_ref)
        b_sides = self._side_tips(b_ref)
        mset = set(self.multi)
        sset = set(self.shunts)
        for net in self.c.nets.values():
            if net.net_class in (NetClass.POWER, NetClass.GROUND):
                continue
            others = {pr.ref for pr in net.pins
                      if pr.ref in mset and pr.ref not in sset} \
                - {a_ref, b_ref}
            if others:
                continue
            a_tips = [t for (r, num, side, t) in a_sides
                      if r == a_ref and side == "right"
                      and self._on_net(a_ref, num, net.name)]
            b_tips = [t for (r, num, side, t) in b_sides
                      if r == b_ref and side == "left"
                      and self._on_net(b_ref, num, net.name)]
            if not a_tips or not b_tips:
                continue
            ga = self._tip_group(a_tips)
            gb = self._tip_group(b_tips)
            if ga is None or gb is None:
                continue
            out.append((net.name, ga[0], gb[0], ga[1], gb[1]))
        return out

    def _side_tips(self, ref: str):
        part = self.c.parts[ref]
        rot = self.orient.get(ref, 0)
        sdef = self.lib.get(part.lib_id)
        out = []
        seen = set()
        for p in sdef.pins:
            if p.hidden:
                continue
            t = pin_page_position(p, 0.0, 0.0, rot)
            if (t, p.rotation) in seen:
                continue
            seen.add((t, p.rotation))
            out.append((ref, p.number,
                        _SIDE_OF_ROT[(p.rotation + rot) % 360], t))
        return out

    def _on_net(self, ref: str, num: str, net: str) -> bool:
        n = self.net_of(ref, num)
        return n is not None and n.name == net

    def _chain_template(self) -> Placement:
        c, sp = self.c, self.sp
        order = self._chain_order()
        anchors: dict[str, tuple[float, float]] = {}
        handled: set[tuple[str, str, str]] = set()
        channels: list[tuple[str, str, str]] = []
        chan_tips: dict[str, tuple] = {}
        ays: dict[str, float] = {order[0]: 0.0}
        binfo: dict[str, list] = {order[0]: []}

        for i in range(1, len(order)):
            a_ref, b_ref = order[i - 1], order[i]
            pairs = self._facing_pairs(a_ref, b_ref)
            ay_a = ays[a_ref]
            if not pairs:
                ays[b_ref] = ay_a
                binfo[b_ref] = []
                continue
            dys = [round((ay_a + ta[1]) - tb[1], 3)
                   for _n, ta, tb, _ea, _eb in pairs]
            dy = max(sorted(set(dys)), key=lambda d: (dys.count(d), -abs(d)))
            aligned = [p for p, d in zip(pairs, dys, strict=False) if d == dy]
            aligned_rows = {round(ay_a + p[1][1], 3) for p in aligned}
            spans: dict[str, tuple[float, float]] = {}
            cand: list = []
            demoted: list = []
            for p, d in zip(pairs, dys, strict=False):
                if d == dy:
                    continue
                ya = round(ay_a + p[1][1], 3)
                yb = round(dy + p[2][1], 3)
                lo, hi = sorted((ya, yb))
                if any(lo + 1e-6 < r < hi - 1e-6 for r in aligned_rows):
                    demoted.append(p)
                else:
                    spans[p[0]] = (ya, yb)
                    cand.append(p)
            jogged: list = []
            if cand:
                after: dict[str, set[str]] = {p[0]: set() for p in cand}
                for pi in cand:
                    for pj in cand:
                        if pi is pj:
                            continue
                        (ya_i, yb_i) = spans[pi[0]]
                        lo, hi = sorted(spans[pi[0]])
                        ya_j, yb_j = spans[pj[0]]
                        if lo + 1e-6 < ya_j < hi - 1e-6:
                            after[pi[0]].add(pj[0])
                        if lo + 1e-6 < yb_j < hi - 1e-6:
                            after[pj[0]].add(pi[0])
                names = {p[0]: p for p in cand}
                placed: list[str] = []
                pending = dict(after)
                while pending:
                    ready = [n2 for n2, deps in pending.items()
                             if not (deps - set(placed))]
                    if not ready:
                        worst = sorted(pending)[-1]
                        demoted.append(names[worst])
                        del pending[worst]
                        for deps in pending.values():
                            deps.discard(worst)
                        continue
                    for n2 in sorted(ready):
                        placed.append(n2)
                        del pending[n2]
                jogged = [names[n2] for n2 in placed]
            for n, _ta, _tb, _ea, _eb in demoted:
                self.trunks.pop(n, None)
                self._bridge(n)
            for p in aligned + jogged:
                n, ta, tb, ea, eb = p
                for tip in [ta] + ea:
                    handled.add((a_ref, self._pin_num_at(a_ref, tip, "right"),
                                 "right"))
                for tip in [tb] + eb:
                    handled.add((b_ref, self._pin_num_at(b_ref, tip, "left"),
                                 "left"))
                self.trunks.pop(n, None)
            ays[b_ref] = gsnap(dy)
            binfo[b_ref] = [(p, p in jogged) for p in aligned + jogged]

        mset = set(self.multi)
        sset = set(self.shunts)
        for tname in list(self.trunks):
            nobj = c.nets[tname]
            if nobj.net_class is not NetClass.SIGNAL:
                continue
            mp = {pr.ref for pr in nobj.pins if pr.ref in mset}
            if len(mp) < 2:
                continue
            if mp & sset and len(mp - sset) <= 2:
                self.trunks.pop(tname)
                self._bridge(tname)
                continue
            sides = [side for ref in mp - sset
                     for (_r, num, side, _t) in self._side_tips(ref)
                     if self._on_net(ref, num, tname)]
            has_legs = (self.trunks[tname].chains
                        or any(tname in (a, b) for _r2, a, b in self.series))
            if len(mp - sset) >= 2 and not has_legs \
                    and all(s in ("left", "right") for s in sides):
                self.trunks.pop(tname)
                self._bridge(tname)

        trunk_jobs = dict(self.trunks)
        for t in trunk_jobs.values():
            for ref in order:
                for (_r, num, side, _tip) in self._side_tips(ref):
                    if self._on_net(ref, num, t.net):
                        handled.add((ref, num, side))
        srung_keys: set[tuple[str, str, str]] = set()
        for ref in order:
            for (_r, num, side, _tip) in self._side_tips(ref):
                if side not in ("left", "right") or (ref, num, side) in handled:
                    continue
                n = self.net_of(ref, num)
                if n is None or n.net_class is not NetClass.SIGNAL:
                    continue
                if self._rung_of(n.name, trunk_jobs) is not None:
                    handled.add((ref, num, side))
                    srung_keys.add((ref, num, side))
        comp_dy = 0.0
        row_y0 = -1e9
        for i, ref in enumerate(order):
            new_row = False
            if i and ref in self._comp_starts:
                row_edge = self._band_edge(row_y0, 1e9, +1, default=0.0) \
                    if row_y0 > -1e8 else self._extent()[2]
                row_left = self._band_edge(row_y0, 1e9, -1, default=0.0) \
                    if row_y0 > -1e8 else self._extent()[0]
                if row_edge - row_left > 170.0:
                    _, _, _, ey1c = self._extent()
                    comp_dy = gceil(ey1c + 14 * U) - ays[ref]
                    row_y0 = gceil(ey1c + 2 * U)
                    new_row = True
            ay = round(ays[ref] + comp_dy, 3)
            if i == 0 or new_row:
                ax = 0.0
                anchors[ref] = (ax, ay)
                self._collect_trunk_pins(ref, ax, ay, trunk_jobs, srung_keys)
                self._cell(ref, ax, ay, handled, trunk_jobs, defer_texts=True,
                           drop_dir=+1 if (len(order) > 1
                                           and ref == order[-1]) else -1)
                continue
            if True:
                a_ref = order[i - 1]
                ax_a, ay_a = anchors[a_ref]
                pairs = binfo[ref]
                meas = self._band_edge(row_y0, 1e9, +1,
                                       default=self._extent()[2]
                                       if row_y0 < -1e8 else 0.0)
                jog_base = gceil(meas + 2 * U)
                n_jogs = sum(1 for _p, j in pairs if j)
                b_tips = [t[0] for (_r, _n, s, t) in self._side_tips(ref)
                          if s == "left"]
                b_left = min(b_tips, default=self.lib.get(
                    c.parts[ref].lib_id).body[0])
                reach_b = self._side_reach(ref, "left", trunk_jobs,
                                           exclude={p[0] for p, _j in pairs})
                margin = (4 * U) if pairs else (10 * U)
                ax = gsnap(gceil(jog_base + n_jogs * 2 * U + reach_b + margin)
                           - b_left)
                if pairs:
                    ll = max((tm.llabel_box(p[0], 0, 0, 0)[2]
                              for p, _j in pairs
                              if c.nets[p[0]].net_class is NetClass.SIGNAL),
                             default=0.0)
                    a_right = max(t[0] for (p, _j) in pairs
                                  for t in [p[1]]) + ax_a
                    ax = max(ax, gsnap(a_right
                                       + gceil(max(2 * sp.port_run, ll + 8 * U))
                                       - min(p[2][0] for p, _j in pairs)))
                row_left = self._band_edge(row_y0, 1e9, -1, default=0.0) \
                    if row_y0 > -1e8 else self._extent()[0]
                if os.environ.get("SCHGEN_WRAP_INSTR"):
                    print(f"[wrap-instr] {c.name} step {i} {ref}: "
                          f"ax-rl={ax - row_left:.1f}", file=sys.stderr)
                if pairs and (ax - row_left) > PAPER_W_BUDGET:
                    for p, _j in pairs:
                        n, ta, tb, ea, eb = p
                        for tip in [ta] + ea:
                            handled.discard(
                                (a_ref, self._pin_num_at(a_ref, tip, "right"),
                                 "right"))
                            tx = round(ax_a + tip[0], 3)
                            ty = round(ay_a + tip[1], 3)
                            ex = round(tx + sp.port_run, 3)
                            self.pl.plan(n, (tx, ty), (ex, ty))
                            self.llabel(n, ex, ty, 0)
                        for tip in [tb] + eb:
                            handled.discard(
                                (ref, self._pin_num_at(ref, tip, "left"),
                                 "left"))
                        self._bridge(n)
                    binfo[ref] = []
                    _, _, _, ey1c = self._extent()
                    comp_dy = gceil(ey1c + 14 * U) - ays[ref]
                    row_y0 = gceil(ey1c + 2 * U)
                    ay = round(ays[ref] + comp_dy, 3)
                    ax = 0.0
                    anchors[ref] = (ax, ay)
                    self._collect_trunk_pins(ref, ax, ay, trunk_jobs,
                                             srung_keys)
                    self._cell(ref, ax, ay, handled, trunk_jobs,
                               defer_texts=True,
                               drop_dir=+1 if (len(order) > 1
                                               and ref == order[-1]) else -1)
                    continue
                jog_x = jog_base
                for p, is_jog in pairs:
                    n, ta, tb, ea, eb = p
                    jx = None
                    if is_jog:
                        jx = jog_x
                        jog_x = round(jog_x + 2 * U, 3)
                    for t0, t1 in zip([ta] + ea, ea, strict=False):
                        self.pl.plan(n, (round(ax_a + t0[0], 3),
                                         round(ay_a + t0[1], 3)),
                                     (round(ax_a + t1[0], 3),
                                      round(ay_a + t1[1], 3)))
                    for t0, t1 in zip([tb] + eb, eb, strict=False):
                        self.pl.plan(n, (round(ax + t0[0], 3),
                                         round(ay + t0[1], 3)),
                                     (round(ax + t1[0], 3),
                                      round(ay + t1[1], 3)))
                    channels.append((n, a_ref, ref))
                    chan_tips[n] = ((round(ax_a + ta[0], 3),
                                     round(ay_a + ta[1], 3)),
                                    (round(ax + tb[0], 3),
                                     round(ay + tb[1], 3)), jx)
            anchors[ref] = (ax, ay)
            self._collect_trunk_pins(ref, ax, ay, trunk_jobs, srung_keys)
            self._cell(ref, ax, ay, handled, trunk_jobs, defer_texts=True,
                       drop_dir=+1 if (len(order) > 1 and ref == order[-1])
                       else -1)

        for n, _a_ref, _b_ref in channels:
            (ta, tb, jx) = chan_tips[n]
            if jx is not None:
                self.pl.plan(n, ta, (jx, ta[1]))
                self.pl.plan(n, (jx, ta[1]), (jx, tb[1]))
                y = tb[1]
                start_x = jx
            else:
                assert abs(ta[1] - tb[1]) < 1e-6
                y = ta[1]
                start_x = ta[0]
            nodes = [start_x]
            hangs = self.hang.pop(n, [])
            xs = gfloor(tb[0] - 4 * U)
            for i, refc in enumerate(hangs):
                xc = round(xs - i * sp.cap_pitch, 3)
                nodes.append(xc)
                self.pl.plan(n, (xc, y), (xc, y + 4 * U))
                far_pt, far = self._vertical_2pin(
                    refc, xc, y + 4 * U, n, downward=True,
                    text_side="left" if i % 2 else "right")
                self.power(far, *far_pt)
            nodes.append(tb[0])
            if jx is not None and (jx - ta[0]) > (tb[0] - jx):
                mid, y_lab = gsnap((ta[0] + jx) / 2), ta[1]
            else:
                mid, y_lab = gsnap((start_x + tb[0]) / 2), y
            if c.nets[n].net_class is NetClass.PORT \
                    and not any(h.name == n for h in self.pl.hlabels):
                for k in range(20):
                    lx2 = round(mid + (k // 2 + k % 2) * 2 * U
                                * (1 if k % 2 else -1), 3)
                    if not (start_x + 2 * U <= lx2 <= tb[0] - 2 * U):
                        continue
                    end2 = (lx2, round(y - 2 * U, 3))
                    gb = tm.glabel_box(n, end2[0], end2[1], 90)
                    if self._spot_free(gb) and self._spot_free(
                            (lx2 - 0.1, end2[1], lx2 + 0.1, y - 0.2),
                            pad=0.0):
                        break
                nodes.append(lx2)
                self.pl.plan(n, (lx2, y), end2)
                self.label(n, *end2, 90)
            nodes = sorted(set(nodes))
            for xa, xb in zip(nodes, nodes[1:], strict=False):
                self.pl.plan(n, (xa, y), (xb, y))
            if c.nets[n].net_class is NetClass.SIGNAL:
                self.llabel(n, mid, y_lab)

        for t in trunk_jobs.values():
            self._build_trunk(t)

        for pp, body in self._deferred_texts:
            self._part_texts(pp, body)
        self._deferred_texts = []

        first = order[0]
        pp0 = next(p for p in self.pl.parts if p.ref == first)
        sdef0 = self.lib.get(pp0.lib_id)
        body0 = body_box_page(sdef0, pp0.x, pp0.y, pp0.rotation,
                              "body", first)
        self._decoupling_cluster(pp0.x, pp0.y, body0)
        self._shunt_cells(handled)
        self._rung_islet_columns()
        self._pin_divider_columns()
        self._pull_rank_columns()
        self._series_port_columns()
        self._trunk_series_columns()
        for _ch in [ch for ch in self.float_chains if ch.kind == "rail"]:
            self._leftover_chains_columns()
            break
        self._port_strap_columns()
        self._flags_row()
        return self.pl

    def _pin_num_at(self, ref: str, tip_rel, side: str) -> str:
        for (_r, num, s, t) in self._side_tips(ref):
            if s == side and t == tip_rel:
                return num
        raise PlaceError(f"{ref}: no {side} pin at {tip_rel}")

    def _side_reach(self, ref: str, side: str,
                    trunk_jobs: dict[str, _Trunk] | None = None,
                    exclude: set[str] | None = None) -> float:
        sp = self.sp
        trunk_jobs = self.trunks if trunk_jobs is None else trunk_jobs
        exclude = exclude or set()
        out = 2 * U
        lanes = 0
        rows: list[tuple[float, float]] = []
        for (_r, num, s, t) in self._side_tips(ref):
            if s != side:
                continue
            n = self.net_of(ref, num)
            if n is None or n.name in exclude:
                continue
            if n.name in trunk_jobs:
                lanes += 1
                continue
            if n.net_class is NetClass.SIGNAL \
                    and self._rung_of(n.name, trunk_jobs) is not None:
                lanes += 1
                continue
            ser = self._series_of(n.name) \
                if n.net_class is NetClass.SIGNAL else None
            if ser is not None:
                far = ser[2] if ser[1] == n.name else ser[1]
                ll = self._glabel_len(far) \
                    if self.c.nets[far].net_class is NetClass.PORT \
                    else tm.text_wh(far)[0] + 0.7
                rows.append((t[1], 12 * U + ll + sp.label_tap_gap))
                continue
            if n.net_class in (NetClass.PORT, NetClass.SIGNAL):
                extra = 0.0
                refs = [r for r, _rl in self.pull.get(n.name, [])] \
                    + self.hang.get(n.name, [])
                for r2 in refs:
                    sig_pin = self._pin_of_net(r2, n.name)
                    fn = self.net_of(r2, self.other_pin(r2, sig_pin))
                    if fn is not None:
                        extra = max(extra, sp.label_tap_gap
                                    + tm.text_wh(fn.name)[0] / 2 + 0.7)
            if n.net_class is NetClass.PORT:
                rows.append((t[1], self._glabel_len(n.name) + extra
                             + sp.stagger_extra + sp.label_tap_gap))
            elif n.net_class is NetClass.SIGNAL \
                    and self._net_shared(n.name, ref):
                rows.append((t[1], tm.text_wh(n.name)[0] + 0.7 + extra
                             + sp.stagger_extra + sp.label_tap_gap))
            elif n.net_class in (NetClass.POWER, NetClass.GROUND):
                out = max(out, 3.81 + tm.text_wh(n.name)[0] + 2 * U)
            else:
                out = max(out, sp.port_run + 4 * U)
        if rows:
            clash = tm.GLABEL_H * tm.SIZE + 0.5
            rows.sort()
            inner_len = outer_len = 0.0
            prev_y = prev_col = None
            for y, ln in rows:
                col = ("outer" if prev_y is not None
                       and abs(y - prev_y) < clash
                       and prev_col == "inner" else "inner")
                if col == "inner":
                    inner_len = max(inner_len, ln)
                else:
                    outer_len = max(outer_len, ln)
                prev_y, prev_col = y, col
            two = inner_len + ((1.27 + outer_len) if outer_len else 0.0)
            out = max(out, sp.port_run + two + 2 * U)
        if lanes:
            out += 3 * U + 2 * U * lanes
        return out

    def run(self) -> Placement:
        c = self.c
        if not self.multi:
            pl = self._stack_columns_template()
        elif len(c.parts) == 1 and len(
                self.lib.pin_numbers(c.parts[self.multi[0]].lib_id)) >= 40:
            pl = self._connector_template(self.multi[0])
        else:
            stages = self._detect_stages()
            shared_ok = True
            mset = list(self.multi)
            for i in range(len(mset)):
                for j in range(i + 1, len(mset)):
                    a = {n.name for n in c.nets.values()
                         if n.net_class in (NetClass.SIGNAL, NetClass.PORT)
                         and any(pr.ref == mset[i] for pr in n.pins)
                         and any(pr.ref == mset[j] for pr in n.pins)}
                    if a:
                        shared_ok = False
            if stages and shared_ok:
                pl = self._regulator_template(stages)
            else:
                pl = self._chain_template()
        missing = sorted(set(c.parts) - self._done)
        if missing:
            raise PlaceError(f"engine left parts unplaced: {missing} — "
                             f"no topology pattern matched them")
        return pl


def _translate(pl: Placement, dx: float, dy: float) -> None:
    def mv(t):
        return None if t is None else (round(t[0] + dx, 3),
                                       round(t[1] + dy, 3), t[2])
    for p in pl.parts:
        p.x = round(p.x + dx, 3)
        p.y = round(p.y + dy, 3)
        p.ref_pos = mv(p.ref_pos)
        p.val_pos = mv(p.val_pos)
    for pw in pl.powers:
        pw.x = round(pw.x + dx, 3)
        pw.y = round(pw.y + dy, 3)
        pw.val_pos = mv(pw.val_pos)
    for h in pl.hlabels:
        h.x = round(h.x + dx, 3)
        h.y = round(h.y + dy, 3)
    for ll in pl.llabels:
        ll.x = round(ll.x + dx, 3)
        ll.y = round(ll.y + dy, 3)
    for n in pl.no_connects:
        n.x = round(n.x + dx, 3)
        n.y = round(n.y + dy, 3)
    for net, paths in pl.plans.items():
        pl.plans[net] = [[(round(x + dx, 3), round(y + dy, 3))
                          for x, y in path] for path in paths]
    pl.boxes = [Box(round(b.x0 + dx, 3), round(b.y0 + dy, 3),
                    round(b.x1 + dx, 3), round(b.y1 + dy, 3),
                    b.kind, b.owner)
                for b in pl.boxes]


def center_on_sheet(pl: Placement) -> Placement:
    xs = [v for b in pl.boxes for v in (b.x0, b.x1)]
    ys = [v for b in pl.boxes for v in (b.y0, b.y1)]
    for paths in pl.plans.values():
        for path in paths:
            xs += [p[0] for p in path]
            ys += [p[1] for p in path]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    dx = gsnap(A4_CENTER[0] - cx)
    dy = gsnap(A4_CENTER[1] - cy)
    _translate(pl, dx, dy)
    return pl


def build(c: Circuit, lib: Library, sp: Spacing) -> Placement:
    from schgen.verify import testpoints
    core, tp_refs = testpoints.split(c)
    eng = _Engine(core, lib, sp)
    pl = eng.run()
    testpoints.add_probe_row(eng, c, tp_refs)
    return center_on_sheet(pl)


def place_and_route(c: Circuit, lib: Library, max_attempts: int = 8):
    sp = Spacing()
    last = "?"
    for _ in range(max_attempts):
        try:
            pl = build(c, lib, sp)
            routed = route.route(c, pl, lib)
        except (route.RouteError, PlaceError) as e:
            last = f"route: {e}"
            sp = sp.expanded()
            continue
        geo = SheetGeometry(boxes=list(pl.boxes), wires=list(routed.segs),
                            junctions=[Junction(x, y)
                                       for x, y in routed.junctions])
        vis = visual_gate.check(geo)
        if vis.ok:
            xs = [v for b in pl.boxes for v in (b.x0, b.x1)] + \
                 [v for s in routed.segs for v in (s.x0, s.x1)]
            ys = [v for b in pl.boxes for v in (b.y0, b.y1)] + \
                 [v for s in routed.segs for v in (s.y0, s.y1)]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if w <= 272.0 and h <= 180.0:
                return pl, routed, geo
            if w <= 390.0 and h <= 265.0:
                ddx = gsnap(A3_CENTER[0] - A4_CENTER[0])
                ddy = gsnap(A3_CENTER[1] - A4_CENTER[1])
                _translate(pl, ddx, ddy)
                routed.segs = [type(s)(round(s.x0 + ddx, 3),
                                       round(s.y0 + ddy, 3),
                                       round(s.x1 + ddx, 3),
                                       round(s.y1 + ddy, 3), s.net)
                               for s in routed.segs]
                routed.junctions = [(round(x + ddx, 3), round(y + ddy, 3))
                                    for x, y in routed.junctions]
                geo = SheetGeometry(boxes=list(pl.boxes),
                                    wires=list(routed.segs),
                                    junctions=[Junction(x, y)
                                               for x, y in routed.junctions])
                pl.paper = "A3"
                return pl, routed, geo
            last = f"sheet {w:.0f}x{h:.0f} mm exceeds even A3 (390x265)"
        else:
            last = vis.summary()
        sp = sp.expanded()
    raise PlaceError(f"placement infeasible after {max_attempts} expansions; "
                     f"last failure:\n{last}")


_STRUCTURAL_MARKERS = (
    "no engine pattern applies", "no power symbol mapped",
    "regulator stage without", "multi-element divider",
    "neither a multi-pin part nor", "unsupported extra leg",
    "single-ended chain tops out", "bottom-drop attachments beyond",
)


def _is_congestion(err: PlaceError) -> bool:
    msg = str(err)
    if "placement infeasible after" not in msg:
        return False
    return not any(m in msg for m in _STRUCTURAL_MARKERS)


def _signal_blobs(c: Circuit, lib: Library) -> list[set[str]]:
    parent = {r: r for r in c.parts}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for net in c.nets.values():
        if net.net_class is NetClass.SIGNAL:
            refs = [pr.ref for pr in net.pins if pr.ref in c.parts]
            for r in refs[1:]:
                union(refs[0], r)

    groups: dict[str, set[str]] = {}
    for r in c.parts:
        groups.setdefault(find(r), set()).add(r)

    multi = {r for r in c.parts
             if len(lib.pin_numbers(c.parts[r].lib_id)) > 2}
    group_of = {r: find(r) for r in c.parts}
    rail_groups: dict[str, list[str]] = {}
    for net in c.nets.values():
        if net.net_class in (NetClass.POWER, NetClass.GROUND):
            roots = sorted({group_of[pr.ref] for pr in net.pins
                            if pr.ref in multi})
            if roots:
                rail_groups[net.name] = roots
    for root in list(groups):
        refs = groups.get(root)
        if refs is None or len(refs) != 1:
            continue
        (ref,) = refs
        if ref in multi:
            continue
        rails = sorted(
            (n for n in c.nets.values()
             if n.net_class in (NetClass.POWER, NetClass.GROUND)
             and any(p.ref == ref for p in n.pins)),
            key=lambda n: (n.net_class is NetClass.GROUND, n.name))
        for rail in rails:
            cands = [g for g in rail_groups.get(rail.name, []) if g != root]
            if cands:
                groups[min(cands)] |= groups.pop(root)
                break

    return sorted(groups.values(), key=lambda s: (-len(s), min(s)))


def _fits_a3(c: Circuit, lib: Library) -> bool:
    try:
        place_and_route(c, lib, max_attempts=2)
        return True
    except PlaceError:
        return False


def partition_pages(c: Circuit, lib: Library) -> list[Circuit]:
    blobs = _signal_blobs(c, lib)
    if len(blobs) < 2:
        return [c]
    bins: list[set[str]] = []
    for blob in blobs:
        for b in bins:
            if _fits_a3(c.subset(b | blob, page=0), lib):
                b |= blob
                break
        else:
            bins.append(set(blob))
    if len(bins) < 2:
        return [c]
    return [c.subset(refs, page=k) for k, refs in enumerate(bins, start=1)]


def paginate_and_route(c: Circuit, lib: Library, max_attempts: int = 8):
    try:
        return [(c, *place_and_route(c, lib, max_attempts))]
    except PlaceError as e:
        if not _is_congestion(e):
            raise
        pages = partition_pages(c, lib)
        if len(pages) < 2:
            raise
        return [(pg, *place_and_route(pg, lib, max_attempts)) for pg in pages]
