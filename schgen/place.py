"""Placement ENGINE v2: ALL geometry derived from circuit TOPOLOGY.

A subsystem ``.py`` contains the NETLIST (plus optional declarative hints —
net names and style keywords, never coordinates). This engine derives every
anchor, wire plan and text position from the circuit structure:

- SIGNAL-FLOW CHAIN: multi-pin parts ordered left->right by flow (the part
  with the most PORT pins leftmost, connector-class sinks rightmost, middle
  parts by shared-net adjacency); nets shared between adjacent parts route
  straight across the channel as drawn wires.
- TRUNK BUS / LADDER: a net with many same-structure taps (R||C legs onto a
  common net, multi-part pins, a terminating safety cap) renders as one
  trunk + vertical taps + junction dots — detected, not scripted.
- REGULATOR STAGES: buck IC + L + FB divider + in/out caps (and LDO rows)
  recognised from part roles and stacked as datasheet stage rows.
- CONNECTOR FAN: a lone >=40-pin connector renders as the two-column label
  fan with per-rail trunks (the SoM mezzanine sheets).
- Per-side machinery shared by all templates: port fans, pull-up/filter
  attachments, divider stacks, rail buses, decoupling clusters, PWR_FLAG
  corner rows, collision-aware reference/value text placement.

Feasibility loop: if routing fails or the visual gate objects, spacing is
EXPANDED and the template re-runs. Rules never relax; whitespace grows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from schgen import route, sexpr
from schgen import textmetrics as tm
from schgen.emit import (HierLabel, LocalLabel, NoConnect, PlacedPart,
                         PlacedPower)
from schgen.model import Circuit, NetClass, PinRef
from schgen.symbols import GRID, Library, Pin, SymbolDef, pin_page_position
from schgen.verify import visual_gate
from schgen.verify.visual_gate import Box, SheetGeometry

U = GRID
A4_CENTER = (148.59, 100.33)

POWER_LIBS = {
    "+3V3": "power:+3V3",
    "+5V": "power:+5V",
    "+1V8": "power:+1V8",
    "GND": "power:GND",
    "VBUS": "power:VBUS",
    "+VIN": "schgen:+VIN",
    "CHASSIS_GND": "schgen:CHASSIS_GND",
    # gated module rails (bringup_power_gating dossier: SY6280 outputs)
    "+3V3_HDMI_TX": "schgen:+3V3_HDMI_TX",
    "+5V_HDMI_TX": "schgen:+5V_HDMI_TX",
    "+3V3_HDMI_RX": "schgen:+3V3_HDMI_RX",
    # SoM-provided rails (J-sheets / system controller)
    "+3V3_SC": "schgen:+3V3_SC",
    "+VCCO_13": "schgen:+VCCO_13",
    "+VCCO_33": "schgen:+VCCO_33",
    "+VCCO_34": "schgen:+VCCO_34",
    "+VCCO_35": "schgen:+VCCO_35",
}

# KiCad ERC: a power_in pin needs a power_out / PWR_FLAG driver on its net.
_DRIVER_ETYPES = {"power_out", "output"}


class PlaceError(ValueError):
    pass


def gsnap(v: float) -> float:
    return round(round(v / U) * U, 3)


def gfloor(v: float) -> float:
    return round(math.floor(v / U + 1e-6) * U, 3)


def gceil(v: float) -> float:
    return round(math.ceil(v / U - 1e-6) * U, 3)


@dataclass
class Spacing:
    port_run: float = 10.16       # pin tip -> first (innermost) label anchor
    label_tap_gap: float = 2.54   # label anchor -> attachment tap point
    hang_stub: float = 2.54       # line -> first attachment pin
    stagger_extra: float = 1.27   # clearance past the previous label's text
    cap_pitch: float = 10.16      # decoupling-cluster column pitch
    cluster_dx: float = 38.10     # IC anchor -> leftmost cluster column
    cluster_dy: float = 20.32     # IC anchor -> cluster cap-anchor row
    flags_dy: float = 16.51       # cluster row -> power-flag row
    flag_pitch: float = 10.16

    def expanded(self) -> "Spacing":
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

    def plan(self, net: str, *pts: tuple[float, float]) -> None:
        self.plans.setdefault(net, []).append(
            [(round(p[0], 3), round(p[1], 3)) for p in pts])


# ---- geometry helpers --------------------------------------------------------

def _xform(x: float, y: float, ax: float, ay: float,
           rot: int) -> tuple[float, float]:
    r = math.radians(rot % 360)
    c, s = round(math.cos(r)), round(math.sin(r))
    return (round(ax + x * c - y * s, 3), round(ay - x * s - y * c, 3))


def body_box_page(sdef: SymbolDef, ax: float, ay: float, rot: int,
                  kind: str, owner: str) -> Box:
    x0, y0, x1, y1 = sdef.body
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


def _pin_text_boxes(sdef: SymbolDef, part: PlacedPart) -> list[Box]:
    """Conservative boxes for the rendered pin-number and pin-name texts."""
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
            if horiz:   # number above the stem
                out.append(Box(mid[0] - w / 2, tip[1] - 0.2 - h,
                               mid[0] + w / 2, tip[1] - 0.2,
                               "pin_number", part.ref))
            else:       # number left of the stem, text rotated
                out.append(Box(tip[0] - 0.2 - h, mid[1] - w / 2,
                               tip[0] - 0.2, mid[1] + w / 2,
                               "pin_number", part.ref))
        if not sdef.pin_names_hidden and pin.name not in ("", "~"):
            w, h = tm.text_wh(pin.name)
            w += 0.5
            if dx > 0:      # left-side pin, name runs right into the body
                out.append(Box(root[0] + 0.2, tip[1] - h / 2,
                               root[0] + 0.2 + w, tip[1] + h / 2,
                               "pin_name", part.ref))
            elif dx < 0:    # right-side pin
                out.append(Box(root[0] - 0.2 - w, tip[1] - h / 2,
                               root[0] - 0.2, tip[1] + h / 2,
                               "pin_name", part.ref))
            elif dy > 0:    # top-side pin, name runs down into the body
                out.append(Box(tip[0] - h / 2, root[1] + 0.2,
                               tip[0] + h / 2, root[1] + 0.2 + w,
                               "pin_name", part.ref))
            else:           # bottom-side pin
                out.append(Box(tip[0] - h / 2, root[1] - 0.2 - w,
                               tip[0] + h / 2, root[1] - 0.2,
                               "pin_name", part.ref))
    return out


def _pin(sdef: SymbolDef, number: str) -> Pin:
    for p in sdef.pins:
        if p.number == number:
            return p
    raise PlaceError(f"pin {number} not in {sdef.lib_id}")


_SIDE_OF_ROT = {0: "left", 180: "right", 270: "top", 90: "bottom"}


# ---- topology records ----------------------------------------------------------

@dataclass
class _Line:
    """One fanned-out interface line on a part's left or right side."""
    net: str
    pin_pt: tuple[float, float]
    attach: str | None        # ref of pull-up R / filter C tapping this line
    attach_div: tuple[str, str] | None = None
    net_class: NetClass = NetClass.PORT
    pin_etype: str = ""


@dataclass
class _FloatChain:
    """A series chain through passive-only nets, linearised top->bottom.

    kind: 'rail'  — POWER rail at the top, GROUND at the bottom (LED columns,
                    standalone dividers);
          'trunk' — rooted on a trunk net at the top;
          'pin'   — rooted on a multi-part pin (rendered as a pin stack).
    """
    kind: str
    root: str                                   # rail / trunk net / multi net
    legs: list[tuple[str, str, str]]            # (ref, upper_net, lower_net)
    hangs: dict[str, list[str]] = field(default_factory=dict)  # net -> caps


@dataclass
class _Trunk:
    net: str
    zone: str = "below"                          # 'above' | 'below'
    direct: list = field(default_factory=list)   # (tip, side) multi-part pins
    rungs: list = field(default_factory=list)    # (far_net, tip, side, [refs])
    terms: list[str] = field(default_factory=list)   # hangcaps to GROUND-class
    chains: list[_FloatChain] = field(default_factory=list)
    nodes: list[float] = field(default_factory=list)
    y: float = 0.0


# ---- the engine -----------------------------------------------------------------

class _Engine:
    def __init__(self, c: Circuit, lib: Library, sp: Spacing) -> None:
        self.c = c
        self.lib = lib
        self.sp = sp
        self.pl = Placement()
        self._pwr = 0
        self._flg = 0
        self._done: set[str] = set()             # placed part refs
        self._deferred_texts: list[tuple[PlacedPart, Box]] = []
        self._classify()

    # -- small factories ------------------------------------------------------
    def _power_lib(self, net: str) -> str:
        try:
            return POWER_LIBS[net]
        except KeyError:
            raise PlaceError(f"no power symbol mapped for rail {net!r}") from None

    def power(self, net: str, x: float, y: float, rot: int = 0,
              show_value: bool = True) -> PlacedPower:
        self._pwr += 1
        lib_id = self._power_lib(net)
        sdef = self.lib.get(lib_id)
        ref = f"#PWR{self._pwr:02d}"
        vp = _value_anchor(sdef, x, y, rot)
        pw = PlacedPower(lib_id, net, ref, x, y, rot, net=net,
                         val_pos=(vp[0], vp[1], 0), show_value=show_value)
        self.pl.powers.append(pw)
        self.pl.boxes.append(body_box_page(sdef, x, y, rot, "body", ref))
        if show_value:
            self.pl.boxes.append(Box(*tm.centered_box(net, vp[0], vp[1]),
                                     "value", ref))
        return pw

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
        """Place a 2-pin passive; ref above value beside the body."""
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
        self.pl.hlabels.append(HierLabel(net, x, y, rot, shape=shape))
        self.pl.boxes.append(Box(*tm.glabel_box(net, x, y, rot),
                                 "label", f"label:{net}"))

    def llabel(self, net: str, x: float, y: float, rot: int = 0) -> None:
        self.pl.llabels.append(LocalLabel(net, x, y, rot))
        self.pl.boxes.append(Box(*tm.llabel_box(net, x, y, rot),
                                 "label", f"label:{net}"))

    # -- net query helpers ------------------------------------------------------
    def net_of(self, ref: str, pin: str):
        return self.c.net_of(PinRef(ref, pin))

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

    # -- free-space probes --------------------------------------------------------
    def _plan_seg_boxes(self):
        for paths in self.pl.plans.values():
            for path in paths:
                for a, b in zip(path, path[1:]):
                    x0, x1 = sorted((a[0], b[0]))
                    y0, y1 = sorted((a[1], b[1]))
                    yield (x0 - 0.127, y0 - 0.127, x1 + 0.127, y1 + 0.127)

    def _spot_free(self, bx: tuple[float, float, float, float],
                   pad: float = 0.25) -> bool:
        x0, y0, x1, y1 = bx
        for b in self.pl.boxes:
            if x0 - pad < b.x1 and x1 + pad > b.x0 \
                    and y0 - pad < b.y1 and y1 + pad > b.y0:
                return False
        for (sx0, sy0, sx1, sy1) in self._plan_seg_boxes():
            if x0 < sx1 and x1 > sx0 and y0 < sy1 and y1 > sy0:
                return False
        return True

    def _extent(self) -> tuple[float, float, float, float]:
        xs = [v for b in self.pl.boxes for v in (b.x0, b.x1)]
        ys = [v for b in self.pl.boxes for v in (b.y0, b.y1)]
        for paths in self.pl.plans.values():
            for path in paths:
                xs += [p[0] for p in path]
                ys += [p[1] for p in path]
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def _band_edge(self, y0: float, y1: float, side: int,
                   default: float) -> float:
        """Outermost x edge of geometry intersecting the y band [y0, y1]."""
        edge = default
        for b in self.pl.boxes:
            if b.y0 < y1 and b.y1 > y0:
                edge = min(edge, b.x0) if side < 0 else max(edge, b.x1)
        for (sx0, sy0, sx1, sy1) in self._plan_seg_boxes():
            if sy0 < y1 and sy1 > y0:
                edge = min(edge, sx0) if side < 0 else max(edge, sx1)
        return edge

    # ---- classification --------------------------------------------------------
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
        # trunks: SIGNAL nets with many taps (or hinted); channel nets are
        # subtracted later by the chain template.
        self.trunks: dict[str, _Trunk] = {}
        for n in c.nets.values():
            if n.net_class is not NetClass.SIGNAL:
                continue
            if len(n.pins) >= 4 or c.hints.get(n.name) == "trunk":
                self.trunks[n.name] = _Trunk(net=n.name)
        self._extract_float_chains()

    def _extract_float_chains(self) -> None:
        """Linearise passive-only net components into _FloatChains."""
        c = self.c
        floating = {n.name for n in c.nets.values()
                    if n.net_class in (NetClass.SIGNAL, NetClass.PORT)
                    and n.name not in self.multi_nets
                    and n.name not in self.trunks}
        # legs touching each floating net: (ref, far_net, far_kind)
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
        for f in floating:
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
            self.float_chains.append(self._linearise(comp, legs))

    def _linearise(self, comp: set[str],
                   legs: dict[str, list[tuple[str, str, str]]]) -> _FloatChain:
        c = self.c
        ends: list[tuple[str, str, str, str]] = []   # (ref, net, far, kind)
        for n in sorted(comp):
            for ref, far, fk in legs[n]:
                if fk != "float":
                    ends.append((ref, n, far, fk))
        # top end preference: trunk > pin > rail
        order = {"trunk": 0, "pin": 1, "rail": 2, "gnd": 3}
        ends.sort(key=lambda e: order[e[3]])
        if not ends:
            raise PlaceError(f"floating nets {sorted(comp)}: no rail/pin end")
        top = ends[0]
        # bottom end: prefer GROUND through a resistor-ish part, else rail
        def is_cap(ref: str) -> bool:
            return self.c.parts[ref].lib_id.endswith(":C")
        bottoms = [e for e in ends[1:]]
        bottoms.sort(key=lambda e: (order[e[3]] != 3, is_cap(e[0])))
        if not bottoms:
            raise PlaceError(f"floating nets {sorted(comp)}: single-ended chain")
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
        # leftover legs become hangs (caps to GND beside the chain)
        for n in sorted(comp):
            for ref, far, fk in legs[n]:
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

    # ---- vertical / horizontal 2-pin placement helpers ---------------------------
    def _vertical_2pin(self, ref: str, x: float, y_attach: float,
                       attach_net: str, downward: bool,
                       text_side: str = "right") -> tuple[tuple[float, float], str]:
        """Place ``ref`` vertically with its ``attach_net`` pin exactly at
        (x, y_attach); the chain continues at the returned far point."""
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        att_no = self._pin_of_net(ref, attach_net)
        far_no = self.other_pin(ref, att_no)
        far_net = self.net_of(ref, far_no)
        assert far_net is not None
        p_att = _pin(sdef, att_no)
        if abs(p_att.y) > 1e-6:                  # y-axis pin pair (R/C/L)
            off = abs(p_att.y)
            up = p_att.y > 0
            rot = (0 if up else 180) if downward else (180 if up else 0)
        else:                                    # x-axis pin pair (LED)
            off = abs(p_att.x)
            right = p_att.x > 0
            rot = (90 if right else 270) if downward else (270 if right else 90)
        anchor_y = y_attach + off if downward else y_attach - off
        self.passive(ref, x, anchor_y, rot, text_side=text_side)
        far_y = anchor_y + off if downward else anchor_y - off
        return (x, round(far_y, 3)), far_net.name

    def _horizontal_2pin(self, ref: str, x: float, y: float,
                         left_net: str, text_side: str = "right") -> None:
        """Place ``ref`` horizontally at anchor (x, y), the ``left_net`` pin
        landing on the left."""
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        left_no = self._pin_of_net(ref, left_net)
        p_left = _pin(sdef, left_no)
        if abs(p_left.y) > 1e-6:
            rot = 90 if p_left.y > 0 else 270
        else:
            rot = 0 if p_left.x < 0 else 180
        self.passive(ref, x, y, rot, text_side=text_side)

    # ---- part cell: body, texts, fans -------------------------------------------
    def _place_body(self, ref: str, ax: float, ay: float):
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        body = body_box_page(sdef, ax, ay, 0, "body", ref)
        pp = PlacedPart(ref, part.lib_id, part.value, ax, ay, 0, part.footprint,
                        ref_pos=None, val_pos=None)
        self.pl.parts.append(pp)
        self.pl.boxes.append(body)
        self.pl.boxes.extend(_pin_text_boxes(sdef, pp))
        sides: dict[str, list[tuple[Pin, tuple[float, float]]]] = {
            "left": [], "right": [], "top": [], "bottom": []}
        seen_pts: set[tuple[float, float]] = set()
        for pin in sdef.pins:
            if pin.hidden:
                continue
            pt = pin_page_position(pin, ax, ay, 0)
            if pt in seen_pts:
                continue
            seen_pts.add(pt)
            sides[_SIDE_OF_ROT[pin.rotation]].append((pin, pt))
        self._done.add(ref)
        return pp, sdef, body, sides

    def _part_texts(self, pp: PlacedPart, body: Box) -> None:
        """Collision-aware Reference / Value placement (checked against every
        box and wire placed so far)."""
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
            # beside the body (for parts with pinless flanks)
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

    # ---- side fan (left/right) ----------------------------------------------------
    def _fan_side(self, ref: str, side: str,
                  items: list[tuple[Pin, tuple[float, float]]],
                  handled: set[tuple[str, str, str]]) -> None:
        sp = self.sp
        sgn = -1 if side == "left" else 1
        items = [(pin, pt) for pin, pt in items
                 if (ref, pin.number, side) not in handled]
        lines: list[_Line] = []
        runs: list[list[tuple[Pin, tuple[float, float], object]]] = []
        for pin, pt in sorted(items, key=lambda t: t[1][1]):
            net = self.net_of(ref, pin.number)
            is_rail = net is not None and net.net_class in (
                NetClass.POWER, NetClass.GROUND)
            prev = runs[-1][-1][2] if runs else None
            if (is_rail and prev is not None
                    and getattr(prev, "name", None) == net.name):
                runs[-1].append((pin, pt, net))
            else:
                runs.append([(pin, pt, net)])
        for run in runs:
            net0 = run[0][2]
            if net0 is None:
                for _, pt, _ in run:
                    self.pl.no_connects.append(NoConnect(*pt))
                continue
            if net0.net_class in (NetClass.POWER, NetClass.GROUND):
                # the rail symbol's value text must clear the part body
                w_val = tm.text_wh(net0.name)[0]
                jx_off = max(3.81, gceil(w_val / 2 + 0.7
                                         - run[0][0].length))
                jx = run[0][1][0] + sgn * jx_off
                if len(run) == 1:
                    pt = run[0][1]
                    dy = -5.08 if net0.net_class is NetClass.POWER else 5.08
                    end = (jx, pt[1] + dy)
                    self.pl.plan(net0.name, pt, (jx, pt[1]), end)
                else:
                    ys = [pt[1] for _, pt, _ in run]
                    for _, pt, _ in run:
                        self.pl.plan(net0.name, pt, (jx, pt[1]))
                    for y0, y1 in zip(ys, ys[1:]):
                        self.pl.plan(net0.name, (jx, y0), (jx, y1))
                    end = ((jx, ys[0])
                           if net0.net_class is NetClass.POWER
                           else (jx, ys[-1]))
                self.power(net0.name, *end)
                continue
            for pin, pt, net in run:
                attach = attach_div = None
                pulls = self.pull.get(net.name, [])
                hangs = self.hang.get(net.name, [])
                if pulls and hangs:
                    if len(pulls) > 1 or len(hangs) > 1:
                        raise PlaceError(f"net {net.name}: multi-element "
                                         f"divider — extend the engine")
                    attach_div = (pulls[0][0], hangs[0])
                    del self.pull[net.name]
                    del self.hang[net.name]
                elif pulls:
                    if len(pulls) > 1:
                        raise PlaceError(f"net {net.name}: multiple pull-ups "
                                         f"— extend the engine")
                    attach = pulls[0][0]
                    del self.pull[net.name]
                elif hangs:
                    if len(hangs) > 1:
                        raise PlaceError(f"net {net.name}: multiple filter "
                                         f"caps — extend the engine")
                    attach = hangs[0]
                    del self.hang[net.name]
                lines.append(_Line(net.name, pt, attach, attach_div,
                                   net.net_class, pin.etype))
        if not lines:
            return
        lines.sort(key=lambda l: l.pin_pt[1], reverse=(side == "right"))
        hang_sgn = -1 if side == "left" else 1
        attach_rows = [l.pin_pt[1] for l in lines if l.attach]
        if attach_rows:
            rank_row = min(attach_rows) if side == "left" else max(attach_rows)
            rank_pin_y = rank_row + hang_sgn * sp.hang_stub
        else:
            rank_pin_y = lines[0].pin_pt[1] + hang_sgn * sp.hang_stub
        prev_label_edge: float | None = None
        prev_label_y: float | None = None
        lane_edge: float | None = None           # outermost text edge so far
        label_clash_dy = tm.GLABEL_H * tm.SIZE + 0.5
        for ln in lines:
            px, py = ln.pin_pt
            lx = px + sgn * sp.port_run
            if (prev_label_edge is not None and prev_label_y is not None
                    and abs(py - prev_label_y) < label_clash_dy):
                want = prev_label_edge + sgn * (sp.stagger_extra
                                                + sp.label_tap_gap)
                lx = min(lx, gfloor(want)) if sgn < 0 else max(lx, gceil(want))
            if ln.attach and lane_edge is not None:
                # the attachment column must clear every row between this
                # line and the rank row: push past the outermost text edge
                between = [l for l in lines if l is not ln
                           and (l.pin_pt[1] - py) * hang_sgn > 0]
                if between:
                    want = lane_edge + sgn * (sp.stagger_extra
                                              + sp.label_tap_gap
                                              + self._attach_halfw(ln))
                    lx = min(lx, gfloor(want)) if sgn < 0 else max(lx, gceil(want))
            if ln.net_class is not NetClass.PORT:
                tap = (lx, py)
                self.pl.plan(ln.net, (px, py), tap)
                edge = None
                if ln.attach_div:
                    edge = self._divider(ln, tap)
                elif ln.attach:
                    edge = self._attach_column(ln, tap, rank_pin_y, side)
                if edge is not None:
                    out = tap[0] + sgn * edge
                    lane_edge = (out if lane_edge is None else
                                 min(lane_edge, out) if sgn < 0 else
                                 max(lane_edge, out))
                continue
            rot = 180 if side == "left" else 0
            if ln.attach or ln.attach_div:
                tap = (lx - sgn * sp.label_tap_gap, py)
                self.pl.plan(ln.net, (px, py), tap)
                self.pl.plan(ln.net, tap, (lx, py))
                if ln.attach_div:
                    self._divider(ln, tap)
                else:
                    self._attach_column(ln, tap, rank_pin_y, side)
            else:
                self.pl.plan(ln.net, (px, py), (lx, py))
            shape = {"input": "input", "output": "output",
                     "tri_state": "tri_state", "open_collector": "output",
                     "open_emitter": "output"}.get(ln.pin_etype,
                                                   "bidirectional")
            self.label(ln.net, lx, py, rot, shape=shape)
            gb = tm.glabel_box(ln.net, lx, py, rot)
            prev_label_edge = gb[0] if sgn < 0 else gb[2]
            prev_label_y = py
            edge = gb[0] if sgn < 0 else gb[2]
            lane_edge = (min(lane_edge, edge) if lane_edge is not None
                         and sgn < 0 else
                         max(lane_edge, edge) if lane_edge is not None
                         else edge)

    def _attach_halfw(self, ln: _Line) -> float:
        """Outward half-extent of an attachment column's widest text (the
        rail symbol's value is centered on the column)."""
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

    # -- attachment column (pull-up to rail / filter cap to ground) -----------------
    def _attach_column(self, ln: _Line, tap: tuple[float, float],
                       rank_pin_y: float, side: str) -> float:
        ref = ln.attach
        assert ref is not None
        part = self.c.parts[ref]
        pins = sorted(self.lib.pin_numbers(part.lib_id))
        sdef = self.lib.get(part.lib_id)
        sig_pin = [p for p in pins
                   if (n := self.net_of(ref, p)) and n.name == ln.net][0]
        far_pin = self.other_pin(ref, sig_pin)
        far_net = self.net_of(ref, far_pin)
        assert far_net is not None
        pin_off = abs(_pin(sdef, sig_pin).y)
        self.pl.plan(ln.net, tap, (tap[0], rank_pin_y))
        if side == "left":
            anchor_y = rank_pin_y - pin_off
            rot = 180 if _pin(sdef, sig_pin).y > 0 else 0
            far_pt = (tap[0], anchor_y - pin_off)
        else:
            anchor_y = rank_pin_y + pin_off
            rot = 0 if _pin(sdef, sig_pin).y > 0 else 180
            far_pt = (tap[0], anchor_y + pin_off)
        self.passive(ref, tap[0], anchor_y, rot)
        self.power(far_net.name, *far_pt)
        return self._attach_halfw(ln)

    def _divider(self, ln: _Line, tap: tuple[float, float]) -> float:
        assert ln.attach_div is not None
        top_ref, bot_ref = ln.attach_div
        for ref, below in ((top_ref, False), (bot_ref, True)):
            part = self.c.parts[ref]
            sdef = self.lib.get(part.lib_id)
            pins = sorted(self.lib.pin_numbers(part.lib_id))
            sig_pin = [p for p in pins
                       if (n := self.net_of(ref, p)) and n.name == ln.net][0]
            far_pin = self.other_pin(ref, sig_pin)
            far_net = self.net_of(ref, far_pin)
            assert far_net is not None
            sig_y = _pin(sdef, sig_pin).y
            pin_off = abs(sig_y)
            if below:
                anchor_y = tap[1] + pin_off
                rot = 0 if sig_y > 0 else 180
                far_pt = (tap[0], anchor_y + pin_off)
            else:
                anchor_y = tap[1] - pin_off
                rot = 180 if sig_y > 0 else 0
                far_pt = (tap[0], anchor_y - pin_off)
            self.passive(ref, tap[0], anchor_y, rot)
            self.power(far_net.name, *far_pt)
        return self._attach_halfw(ln)

    # ---- top/bottom machinery -------------------------------------------------------
    def _rail_rot(self, net: str, side: str) -> int:
        """Upright (0) when the symbol glyph points away from the body:
        GND-family below a bottom edge, power rails above a top edge."""
        is_gnd = self.c.nets[net].net_class is NetClass.GROUND
        return 0 if (is_gnd == (side == "bottom")) else 180

    def _rail_stub(self, net: str, pt: tuple[float, float], side: str) -> None:
        """Power/GND stub off a top or bottom pin, dodging existing texts."""
        up = side == "top"
        dy = -2.54 if up else 2.54
        sdef = self.lib.get(self._power_lib(net))
        rot = self._rail_rot(net, side)
        for k in (1, 2, 3):
            for dx in (0.0, 5.08, -5.08, 10.16, -10.16, 15.24, -15.24):
                end = (round(pt[0] + dx, 3), round(pt[1] + dy * k, 3))
                vp = _value_anchor(sdef, end[0], end[1], rot)
                vbox = tm.centered_box(net, vp[0], vp[1])
                sbox = body_box_page(sdef, end[0], end[1], rot, "body", "?")
                ok = self._spot_free(vbox) and self._spot_free(
                    (sbox.x0, sbox.y0, sbox.x1, sbox.y1))
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
        end = (pt[0], round(pt[1] + dy * 4, 3))
        self.pl.plan(net, pt, end)
        self.power(net, end[0], end[1], rot)

    def _rail_bus(self, net: str, pts: list[tuple[float, float]],
                  side: str) -> None:
        """Several adjacent same-rail pins on the top/bottom edge: short
        drops onto one bar, a single symbol at the bar's middle node."""
        dy = -2.54 if side == "top" else 2.54
        rot = self._rail_rot(net, side)
        bar_y = round(pts[0][1] + dy, 3)
        xs = sorted(p[0] for p in pts)
        for x, y in pts:
            self.pl.plan(net, (x, y), (x, bar_y))
        for xa, xb in zip(xs, xs[1:]):
            self.pl.plan(net, (xa, bar_y), (xb, bar_y))
        mid = xs[len(xs) // 2]
        self.power(net, mid, bar_y, rot)

    def _stack_from_pin(self, chain: _FloatChain, pt: tuple[float, float],
                        side: str) -> None:
        """Pin-rooted series chain stacked straight off a top/bottom pin."""
        downward = side == "bottom"
        cur_net = chain.root
        cur = pt
        for ref, upper, lower in chain.legs:
            near = upper if upper == cur_net else lower
            far_pt, far = self._vertical_2pin(ref, pt[0], cur[1], near,
                                              downward)
            cur = far_pt
            cur_net = far
            self._chain_mid_features(chain, cur_net, cur)
        ncls = self.c.nets[cur_net].net_class
        if ncls in (NetClass.POWER, NetClass.GROUND):
            rot = 0 if ((ncls is NetClass.POWER) != downward) else 180
            self.power(cur_net, *cur, rot)

    def _chain_mid_features(self, chain: _FloatChain, net: str,
                            at: tuple[float, float]) -> None:
        """Label + hanging caps for a chain's intermediate net."""
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
        for xa, xb in zip(nodes, nodes[1:]):
            self.pl.plan(net, (xa, y), (xb, y))

    # ---- generic part cell ----------------------------------------------------------
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
                raise PlaceError(f"{ref}.{pin.number} ({net.name}) on the "
                                 f"{side} edge: no engine pattern applies")
            for net, pts in rail_groups:
                if len(pts) == 1:
                    self._rail_stub(net, pts[0], side)
                else:
                    self._rail_bus(net, pts, side)

        # bottom PORT drops + trunk-rung drops: rows below the cell
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
            for r, a, b in self.series:
                if {a, b} == {net, t.net}:
                    return t
        return None

    def _cell_floor(self, x0: float, x1: float) -> float:
        floor = 0.0
        for b in self.pl.boxes:
            if b.x0 < x1 and b.x1 > x0:
                floor = max(floor, b.y1)
        for (sx0, sy0, sx1, sy1) in self._plan_seg_boxes():
            if sx0 < x1 and sx1 > x0:
                floor = max(floor, sy1)
        return floor

    def _bottom_port_drop(self, ref: str, pin: Pin, pt: tuple[float, float],
                          row: float, direction: int) -> None:
        """A PORT net on a bottom pin: drop to its own row, run out toward
        the sheet edge (``direction``) to a label; a pull-up attachment taps
        the run just inside the label."""
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
            # the pull-up column needs a clear vertical lane above the row
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

    # ---- trunk builder -----------------------------------------------------------
    def _build_trunk(self, t: _Trunk) -> None:
        sp = self.sp
        votes = 0
        for pt, side in t.direct:
            votes += 1 if side == "top" else -1 if side == "bottom" else 0
        for (_n, _pt, _k, _legs, _row) in t.rungs:
            votes -= 1
        t.zone = "above" if votes > 0 else "below"
        ex0, ey0, ex1, ey1 = self._extent()
        if t.zone == "above":
            ty = gfloor(ey0 - 4 * U)
        else:
            ty = gceil(ey1 + 4 * U)
        # ladder rungs raise the trunk further when below: rung depth
        if t.zone == "below" and t.rungs:
            max_legs = max(len(legs) for (_n, _pt, _k, legs, _r) in t.rungs)
            bar = gceil(max(pt[1] for (_n, pt, _k, _l, _r) in t.rungs) + 4 * U)
            ty = max(ty, round(bar + 7.62 * max_legs, 3))
        t.y = ty
        nodes: list[float] = []

        # direct pins
        for pt, side in t.direct:
            if side in ("top", "bottom"):
                self.pl.plan(t.net, pt, (pt[0], ty))
                nodes.append(pt[0])
            else:
                sgn = -1 if side == "left" else 1
                fx = self._lane_x(sgn, min(pt[1], ty), max(pt[1], ty),
                                  start=pt[0] + sgn * 3 * U)
                self.pl.plan(t.net, pt, (fx, pt[1]), (fx, ty))
                nodes.append(fx)

        # ladder rungs (trunk below) / flank rungs (trunk above)
        for far_net, pt, kind, legs, row in t.rungs:
            if t.zone == "below":
                bar = gceil(self._rung_bar_y(t) )
                nodes += self._ladder_rung(t, far_net, pt, legs, bar)
            else:
                fx = self._lane_x(-1, ty, row + 2 * U, start=pt[0] - 3 * U)
                self.pl.plan(far_net, pt, (pt[0], row))
                self.pl.plan(far_net, (pt[0], row), (fx, row))
                if len(legs) != 1:
                    raise PlaceError(f"{t.net}: flank rung with {len(legs)} "
                                     f"legs — extend the engine")
                far_pt, far = self._vertical_2pin(legs[0], fx, row,
                                                  far_net, downward=False,
                                                  text_side="left")
                assert far == t.net
                self.pl.plan(t.net, far_pt, (fx, ty))
                nodes.append(fx)

        # rooted chains hang below the trunk on free columns
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
                self.power(cur_net, *cur)

        # terminators (caps to a ground-class net) at the outer end
        for i, ref in enumerate(self.hang.pop(t.net, [])):
            edge = self._band_edge(ty - 12 * U, ty + 12 * U, +1,
                                   default=max(nodes) if nodes else 0.0)
            x = gceil(edge + 4 * U)
            nodes.append(x)
            far_pt, far = self._vertical_2pin(ref, x, ty, t.net,
                                              downward=True)
            self.power(far, *far_pt)

        nodes = sorted(set(round(n, 3) for n in nodes))
        if len(nodes) < 2:
            raise PlaceError(f"trunk {t.net}: fewer than 2 taps after build")

        # ERC: a power_in pin on a SIGNAL trunk needs a PWR_FLAG driver.
        # Pick the stub BEFORE drawing legs so it becomes a split node.
        if self._needs_flag(t.net):
            gaps = sorted(zip(nodes, nodes[1:]), key=lambda ab: ab[1] - ab[0])
            xa, xb = gaps[-1]
            fx = gsnap((xa + xb) / 2)
            dy = -2.54 if t.zone == "above" else 2.54
            self.pl.plan(t.net, (fx, ty), (fx, ty + dy))
            self.flag(t.net, fx, ty + dy, 0 if t.zone == "above" else 180)
            nodes = sorted(set(nodes + [fx]))

        for xa, xb in zip(nodes, nodes[1:]):
            self.pl.plan(t.net, (xa, ty), (xb, ty))
        # net name ON the trunk wire, wherever its box is free
        for lx, rot in ((nodes[-1], 0), (nodes[0], 180),
                        (nodes[0] + 1.27, 0)):
            if self._spot_free(tm.llabel_box(t.net, lx, ty, rot), pad=0.1):
                self.llabel(t.net, lx, ty, rot)
                break
        else:
            self.llabel(t.net, nodes[-1], ty, 0)

    def _chain_mid_features_left(self, chain: _FloatChain, net: str,
                                 at: tuple[float, float]) -> None:
        """Chain features for under-trunk columns: label stub runs LEFT."""
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
        for xa, xb in zip(nodes, nodes[1:]):
            self.pl.plan(net, (xa, y), (xb, y))

    def _rung_bar_y(self, t: _Trunk) -> float:
        return gceil(max(pt[1] for (_n, pt, _k, _l, _r) in t.rungs) + 4 * U)

    def _ladder_rung(self, t: _Trunk, far_net: str, pt: tuple[float, float],
                     legs: list[str], bar: float) -> list[float]:
        """One Bob-Smith-style rung: drop, bar, vertical legs, trunk taps."""
        # resistive legs first, caps after (datasheet order)
        legs = sorted(legs, key=lambda r: self.c.parts[r].lib_id.endswith(":C"))
        x0 = pt[0]
        cols = [round(x0 + i * 6 * U, 3) for i in range(len(legs))]
        self.pl.plan(far_net, pt, (x0, bar))
        for xa, xb in zip(cols, cols[1:]):
            self.pl.plan(far_net, (xa, bar), (xb, bar))
        self.llabel(far_net, x0 + 1.27, bar)
        for i, (ref, xc) in enumerate(zip(legs, cols)):
            att_y = round(bar + i * 6 * U, 3)
            if att_y != bar:
                self.pl.plan(far_net, (xc, bar), (xc, att_y))
            far_pt, far = self._vertical_2pin(
                ref, xc, att_y, far_net, downward=True,
                text_side="left" if i % 2 == 0 else "right")
            assert far == t.net
            self.pl.plan(t.net, far_pt, (xc, t.y))
        return cols

    def _lane_x(self, sgn: int, y0: float, y1: float, start: float) -> float:
        """First grid column at/outside ``start`` whose vertical band
        [y0, y1] is free of every box placed so far."""
        x = gfloor(start) if sgn < 0 else gceil(start)
        for _ in range(120):
            band = (x - 0.7, y0 - 0.3, x + 0.7, y1 + 0.3)
            if self._spot_free(band, pad=0.0):
                return x
            x = round(x + sgn * 2 * U, 3)
        raise PlaceError("no free lane found")

    def _needs_flag(self, net: str) -> bool:
        etype_of = {}
        for ref, part in self.c.parts.items():
            for p in self.lib.get(part.lib_id).pins:
                etype_of[(ref, p.number)] = p.etype
        pins = self.c.nets[net].pins
        ets = {etype_of.get((pr.ref, pr.pin), "?") for pr in pins}
        return "power_in" in ets and not (ets & _DRIVER_ETYPES)

    # ---- cluster + flags ------------------------------------------------------------
    def _decoupling_cluster(self, ax: float, ay: float, body: Box) -> None:
        sp = self.sp
        col_x = ax - sp.cluster_dx
        n_caps = sum(len(v) for v in self.cluster.values())
        if not n_caps:
            return
        span = (n_caps - 1) * sp.cap_pitch
        col_x = min(col_x, gfloor(body.x0 - span - 4 * sp.hang_stub))
        cy = max(ay + sp.cluster_dy, gceil(body.y1 + 3 * sp.hang_stub))
        prev_rail_w: float | None = None
        for rail, caps in self.cluster.items():
            if prev_rail_w is not None:
                # adjacent rails' value texts must not collide
                col_x = gceil(col_x - sp.cap_pitch
                              + max(sp.cap_pitch,
                                    prev_rail_w / 2
                                    + tm.text_wh(rail)[0] / 2 + 1.27))
            tops: list[float] = []
            for ref in caps:
                self._cluster_cap(ref, col_x, cy)
                tops.append(col_x)
                col_x += sp.cap_pitch
            prev_rail_w = tm.text_wh(rail)[0]
            ry = cy - 3.81
            if len(tops) == 1:
                self.power(rail, tops[0], ry)
            else:
                xm = gsnap((tops[0] + tops[-1]) / 2)
                nodes = sorted(set(tops + [xm]))
                for a, b in zip(nodes, nodes[1:]):
                    self.pl.plan(rail, (a, ry), (b, ry))
                self.pl.plan(rail, (xm, ry), (xm, ry - 2.54))
                self.power(rail, xm, ry - 2.54)
        self.cluster = {}

    def _cluster_cap(self, ref: str, x: float, cy: float) -> None:
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        pins = sorted(self.lib.pin_numbers(part.lib_id))
        n_by_pin = {p: self.net_of(ref, p) for p in pins}
        rail_pin = [p for p in pins
                    if n_by_pin[p] and n_by_pin[p].net_class == NetClass.POWER][0]
        gnd_pin = self.other_pin(ref, rail_pin)
        rot = 0 if _pin(sdef, rail_pin).y > 0 else 180
        self.passive(ref, x, cy, rot)
        pin_off = abs(_pin(sdef, rail_pin).y)
        gnd_net = n_by_pin[gnd_pin]
        assert gnd_net is not None
        self.power(gnd_net.name, x, cy + pin_off)

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
            if ets & _DRIVER_ETYPES:
                continue                  # a real driver powers this rail
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

    # ---- template: stack columns only (no multi-pin parts) ---------------------------
    def _stack_columns_template(self) -> Placement:
        x = 0.0
        for ch in self.float_chains:
            if ch.kind != "rail":
                raise PlaceError(f"passive-only sheet: chain rooted on "
                                 f"{ch.root!r} is not rail-rooted")
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
                self.power(cur_net, *cur)
            _, _, ex1, _ = self._extent()
            x = gceil(ex1 + 2 * self.sp.cap_pitch)
        self._flags_row()
        return self.pl

    # ---- template: connector fan (SoM mezzanine sheets) -------------------------------
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
        """Power symbol with an engine-owned value position (sideways rails
        need property rot 90 so the text reads horizontally)."""
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
                assert net is not None, f"{jref}.{pin.number} unnetted"
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
                             for (y, x, n), cl in zip(ports, cols)
                             if cl == "inner"), default=0.0)
            lx_outer = out(sgn, abs(lx_inner) + inner_len + self.CONN_COL_GAP)
            outer_len = max((self._glabel_len(n)
                             for (y, x, n), cl in zip(ports, cols)
                             if cl == "outer"), default=0.0)
            for (y, px, net), col in zip(ports, cols):
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
                for y0, y1 in zip(ys, ys[1:]):
                    pl.plan(net, (x_r, y0), (x_r, y1))

            for net, taps in rails.items():
                if c.nets[net].net_class is NetClass.GROUND:
                    gnd_items.append((net, taps))
                    continue
                ys = [y for y, _ in taps]
                foreign = [y for rn, rt in rails.items() if rn != net
                           for y, _ in rt if ys[0] < y < ys[-1]]
                assert not foreign, (f"{net}: foreign rail row inside trunk "
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

    # ---- template: regulator stage rows ------------------------------------------------
    def _detect_stages(self) -> dict[str, dict]:
        stages: dict[str, dict] = {}
        for ref in self.multi:
            part = self.c.parts[ref]
            sdef = self.lib.get(part.lib_id)
            for p in sdef.pins:
                if p.etype != "power_out":
                    continue
                net = self.net_of(ref, p.number)
                if net is None:
                    continue
                if net.net_class is NetClass.POWER:
                    stages[ref] = {"kind": "ldo", "out": net.name}
                    break
                if net.net_class is NetClass.SIGNAL:
                    inds = [(r, a, b) for r, a, b in self.series
                            if net.name in (a, b)
                            and self.c.parts[r].lib_id == "Device:L"]
                    pl_ind = [(r, rl) for sig, lst in self.pull.items()
                              if sig == net.name for r, rl in lst
                              if self.c.parts[r].lib_id == "Device:L"]
                    if pl_ind:
                        r, out_rail = pl_ind[0]
                        stages[ref] = {"kind": "buck", "sw": net.name,
                                       "l": r, "out": out_rail}
                        break
        return stages

    def _regulator_template(self, stages: dict[str, dict]) -> Placement:
        c = self.c
        # cap assignment per rail: producer's output run takes the first
        # ceil(n/2) declared caps when the rail also feeds a later stage.
        produced = {st["out"]: ref for ref, st in stages.items()}
        consumed: dict[str, str] = {}
        for ref in self.multi:
            if ref not in stages:
                continue
            sdef = self.lib.get(c.parts[ref].lib_id)
            for p in sdef.pins:
                if p.etype == "power_in":
                    n = self.net_of(ref, p.number)
                    if n is not None and n.net_class is NetClass.POWER \
                            and not n.name.startswith("GND"):
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
        # stage order: a stage whose input rail no stage produces goes first
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
        ay = 0.0
        for ref in order:
            st = stages[ref]
            self._stage_row(ref, st, ay, in_caps, out_caps)
            ay = gceil(self._extent()[3] + 10 * U)
        handled: set = set()
        for ref in aux:
            # an upward pin-stack off this part's top edge needs headroom
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
            self._cell(ref, 0.0, gceil(ay + reach), handled, {})
            ay = gceil(self._extent()[3] + 10 * U)
        self._leftover_chains_columns()
        if self.cluster:
            raise PlaceError(f"regulator template: unassigned decoupling caps "
                             f"{self.cluster}")
        self._flags_row()
        return self.pl

    def _stage_in_rail(self, ref: str) -> str | None:
        sdef = self.lib.get(self.c.parts[ref].lib_id)
        for p in sdef.pins:
            if p.etype == "power_in" and p.rotation == 0:   # left-side pin
                n = self.net_of(ref, p.number)
                if n is not None and n.net_class is NetClass.POWER:
                    return n.name
        return None

    def _stage_row(self, ref: str, st: dict, ay: float,
                   in_caps: dict[str, list[str]],
                   out_caps: dict[str, list[str]]) -> None:
        sp = self.sp
        pp, sdef, body, sides = self._place_body(ref, 0.0, ay)
        pins = {p.number: pin_page_position(p, 0.0, ay, 0)
                for p in sdef.pins}
        p_in = p_en = p_gnd = None
        for p in sdef.pins:
            net = self.net_of(ref, p.number)
            if net is None:
                continue
            if p.rotation == 0 and p.etype == "power_in" \
                    and net.net_class is NetClass.POWER:
                p_in = (pins[p.number], net.name)
            elif p.rotation == 0 and net.net_class is NetClass.PORT:
                p_en = (pins[p.number], net.name, p.etype)
            elif p.rotation == 90 and net.net_class is NetClass.GROUND:
                p_gnd = (pins[p.number], net.name)
        if p_in is None or p_gnd is None:
            raise PlaceError(f"{ref}: regulator stage without VIN/GND pins")

        # left: EN port + input rail with its cap bank
        if p_en is not None:
            (pe, en_net, etype) = p_en
            lx = pe[0] - sp.port_run
            self.pl.plan(en_net, pe, (lx, pe[1]))
            self.label(en_net, lx, pe[1], 180,
                       shape="input" if etype == "input" else "bidirectional")
        (pv, in_rail) = p_in
        cin = in_caps.pop(in_rail, [])
        cols = [gfloor(pv[0] - sp.cluster_dx + i * -sp.cap_pitch)
                for i in range(len(cin))]
        nodes = [pv[0]] + cols
        nodes_sorted = sorted(set(nodes))
        for xa, xb in zip(nodes_sorted, nodes_sorted[1:]):
            self.pl.plan(in_rail, (xa, pv[1]), (xb, pv[1]))
        rail_x = cols[-1] if cols else pv[0]
        self.pl.plan(in_rail, (rail_x, pv[1]), (rail_x, pv[1] - 5.08))
        self.power(in_rail, rail_x, pv[1] - 5.08)
        for refc, x in zip(cin, cols):
            far_pt, far = self._vertical_2pin(refc, x, pv[1],
                                              in_rail, downward=True)
            self.power(far, *far_pt)
        (pg, gnd_net) = p_gnd
        self.power(gnd_net, *pg)

        if st["kind"] == "buck":
            self._buck_right(ref, st, ay, pins, sdef, out_caps)
        else:
            self._ldo_right(ref, st, ay, pins, sdef, out_caps)
        self._part_texts(pp, body)

    def _buck_right(self, ref: str, st: dict, ay: float, pins, sdef,
                    out_caps: dict[str, list[str]]) -> None:
        sp = self.sp
        c = self.c
        sw_net, out_rail, l_ref = st["sw"], st["out"], st["l"]
        # role pins from topology
        p_sw = p_boot = p_fb = None
        boot_net = fb_net = None
        boot_cap = None
        for p in sdef.pins:
            if p.rotation != 180:
                continue
            net = self.net_of(ref, p.number)
            if net is None:
                continue
            if net.name == sw_net:
                p_sw = pin_page_position(p, 0.0, ay, 0)
            elif net.net_class is NetClass.SIGNAL:
                caps = [(r, a, b) for r, a, b in self.series
                        if net.name in (a, b) and sw_net in (a, b)]
                if caps:
                    p_boot = pin_page_position(p, 0.0, ay, 0)
                    boot_net = net.name
                    boot_cap = caps[0][0]
                elif net.name in self.pull or net.name in self.hang:
                    p_fb = pin_page_position(p, 0.0, ay, 0)
                    fb_net = net.name
        if p_sw is None:
            raise PlaceError(f"{ref}: buck stage without SW pin")
        x0 = p_sw[0]
        y_sw = p_sw[1]
        x_l = round(x0 + 26.67, 3)
        slot = gceil(x_l + 9 * U)                      # first out-run column
        # BOOT loop over the SW run
        if p_boot is not None and boot_cap is not None:
            yb = round(min(p_boot[1], y_sw) - 5.08, 3)
            xv = round(x0 + 2.54, 3)
            xc = round(x0 + 10.16, 3)
            xj = round(x0 + 20.32, 3)
            self.pl.plan(boot_net, p_boot, (xv, p_boot[1]), (xv, yb),
                         (xc - 3.81, yb))
            self._horizontal_2pin(boot_cap, xc, yb, boot_net)
            self.pl.plan(sw_net, (xc + 3.81, yb), (xj, yb), (xj, y_sw))
            self.series = [s for s in self.series if s[0] != boot_cap]
            self.pl.plan(sw_net, p_sw, (xj, y_sw))
            self.pl.plan(sw_net, (xj, y_sw), (x0 + 26.67 - 3.81, y_sw))
        else:
            self.pl.plan(sw_net, p_sw, (x0 + 26.67 - 3.81, y_sw))
        # inductor
        self._horizontal_2pin(l_ref, x_l, y_sw, sw_net)
        self.pull.get(sw_net) and self.pull[sw_net].remove(
            (l_ref, out_rail))
        if self.pull.get(sw_net) == []:
            del self.pull[sw_net]
        # output run
        nodes = [round(x_l + 3.81, 3)]
        for refc in out_caps.pop(out_rail, []):
            nodes.append(slot)
            far_pt, far = self._vertical_2pin(refc, slot, y_sw,
                                              out_rail, downward=True)
            self.power(far, *far_pt)
            slot = gceil(slot + sp.cap_pitch)
        # FB divider column
        if p_fb is not None and fb_net is not None:
            x_div = slot
            nodes.append(x_div)
            slot = gceil(slot + sp.cap_pitch)
            self.pl.plan(out_rail, (x_div, y_sw), (x_div, y_sw + 5.08))
            (rt, _rail) = self.pull.pop(fb_net)[0]
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
        # rail-rooted chains (PG LED columns)
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
        # rail symbol riser at the end of the run
        x_r = round(slot - sp.cap_pitch / 2, 3)
        nodes.append(x_r)
        nodes = sorted(set(nodes))
        for xa, xb in zip(nodes, nodes[1:]):
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
        x_r = round(slot - sp.cap_pitch / 2, 3)
        nodes.append(x_r)
        nodes = sorted(set(nodes))
        for xa, xb in zip(nodes, nodes[1:]):
            self.pl.plan(out_rail, (xa, y_r), (xb, y_r))
        self.pl.plan(out_rail, (x_r, y_r), (x_r, y_r - 5.08))
        self.power(out_rail, x_r, y_r - 5.08)

    def _leftover_chains_columns(self) -> None:
        """Rail-rooted chains not consumed by a stage run: own columns."""
        for ch in [c for c in self.float_chains if c.kind == "rail"]:
            _, _, ex1, _ = self._extent()
            x = gceil(ex1 + 2 * self.sp.cap_pitch)
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
                self.power(cur_net, *cur)
            self.float_chains.remove(ch)

    # ---- template: signal-flow chain ----------------------------------------------------
    def _chain_order(self) -> list[str]:
        conns = [r for r in self.multi if r[0] == "J"]
        others = [r for r in self.multi if r[0] != "J"]

        def port_pins(r: str) -> int:
            return sum(1 for p in self.lib.pin_numbers(self.c.parts[r].lib_id)
                       if (n := self.net_of(r, p)) is not None
                       and n.net_class is NetClass.PORT)

        def nets_of(r: str) -> set[str]:
            return {n.name for n in self.c.nets.values()
                    if any(pr.ref == r for pr in n.pins)}

        pool = sorted(others, key=lambda r: -port_pins(r)) + conns
        if not pool:
            return []
        order = [pool.pop(0)]
        while pool:
            last = nets_of(order[-1])
            pool.sort(key=lambda r: -len(last & nets_of(r)))
            order.append(pool.pop(0))
        return order

    def _facing_pairs(self, a_ref: str, b_ref: str):
        """Shared nets with exactly one tip on A's right and one on B's left
        side -> [(net, a_tip, b_tip_rel)] with B at anchor (0, 0)."""
        out = []
        a_sides = self._side_tips(a_ref)
        b_sides = self._side_tips(b_ref)
        for net in self.c.nets.values():
            if net.net_class in (NetClass.POWER, NetClass.GROUND):
                continue
            a_tips = [t for (r, num, side, t) in a_sides
                      if r == a_ref and side == "right"
                      and self._on_net(a_ref, num, net.name)]
            b_tips = [t for (r, num, side, t) in b_sides
                      if r == b_ref and side == "left"
                      and self._on_net(b_ref, num, net.name)]
            if len(a_tips) == 1 and len(b_tips) == 1:
                out.append((net.name, a_tips[0], b_tips[0]))
        return out

    def _side_tips(self, ref: str):
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        out = []
        seen = set()
        for p in sdef.pins:
            if p.hidden:
                continue
            t = pin_page_position(p, 0.0, 0.0, 0)
            if (t, p.rotation) in seen:
                continue
            seen.add((t, p.rotation))
            out.append((ref, p.number, _SIDE_OF_ROT[p.rotation], t))
        return out

    def _on_net(self, ref: str, num: str, net: str) -> bool:
        n = self.net_of(ref, num)
        return n is not None and n.name == net

    def _chain_template(self) -> Placement:
        c, sp = self.c, self.sp
        order = self._chain_order()
        anchors: dict[str, tuple[float, float]] = {}
        handled: set[tuple[str, str, str]] = set()
        channels: list[tuple[str, str, str]] = []   # (net, a_ref, b_ref)
        chan_tips: dict[str, tuple] = {}
        anchors[order[0]] = (0.0, 0.0)
        for i in range(1, len(order)):
            a_ref, b_ref = order[i - 1], order[i]
            pairs = self._facing_pairs(a_ref, b_ref)
            if not pairs:
                raise PlaceError(f"chain {a_ref}->{b_ref}: no facing shared "
                                 f"nets — extend the engine")
            ax_a, ay_a = anchors[a_ref]
            dys = [round((ay_a + ta[1]) - tb[1], 3) for _, ta, tb in pairs]
            dy = max(set(dys), key=dys.count)
            aligned = [p for p, d in zip(pairs, dys) if d == dy]
            if len(aligned) != len(pairs):
                bad = [p[0] for p, d in zip(pairs, dys) if d != dy]
                raise PlaceError(f"chain {a_ref}->{b_ref}: rows for {bad} do "
                                 f"not align — extend the engine (jogs)")
            # channel width: B's left-fan labels + named shared signals
            b_label = max((self._glabel_len(n.name)
                           for n in c.nets.values()
                           if n.net_class is NetClass.PORT
                           and any(self._on_net(b_ref, num, n.name)
                                   and side == "left"
                                   for (_r, num, side, _t)
                                   in self._side_tips(b_ref))
                           and not any(p[0] == n.name for p in pairs)),
                          default=0.0)
            ll = max((tm.llabel_box(n, 0, 0, 0)[2]
                      for n, _, _ in pairs
                      if c.nets[n].net_class is NetClass.SIGNAL), default=0.0)
            gap = gceil(max(2 * sp.port_run, b_label + sp.port_run + 4 * U,
                            ll + 8 * U))
            a_right = max(t[0] for _, t, _ in pairs) + ax_a
            b_left = min(t[0] for _, _, t in pairs)
            ax_b = gsnap(a_right + gap - b_left)
            anchors[b_ref] = (ax_b, gsnap(dy))
            for n, ta, tb in pairs:
                na = self._pin_num_at(a_ref, ta, "right")
                nb = self._pin_num_at(b_ref, tb, "left")
                handled.add((a_ref, na, "right"))
                handled.add((b_ref, nb, "left"))
                channels.append((n, a_ref, b_ref))
                chan_tips[n] = ((round(ax_a + ta[0], 3),
                                 round(ay_a + ta[1], 3)),
                                (round(ax_b + tb[0], 3),
                                 round(dy + tb[1], 3)))
            # channel nets are not trunks
            for n, _, _ in pairs:
                self.trunks.pop(n, None)

        # trunk jobs: mark their direct pins handled before cells run
        trunk_jobs = dict(self.trunks)
        for t in trunk_jobs.values():
            for ref in order:
                for (r, num, side, tip) in self._side_tips(ref):
                    if self._on_net(ref, num, t.net):
                        handled.add((ref, num, side))
        # cells
        for ref in order:
            ax, ay = anchors[ref]
            # collect trunk direct pins at page coords
            for t in trunk_jobs.values():
                for (r, num, side, tip) in self._side_tips(ref):
                    if self._on_net(ref, num, t.net):
                        t.direct.append(((round(ax + tip[0], 3),
                                          round(ay + tip[1], 3)), side))
            self._cell(ref, ax, ay, handled, trunk_jobs, defer_texts=True,
                       drop_dir=+1 if (len(order) > 1 and ref == order[-1])
                       else -1)

        # channel runs
        for n, a_ref, b_ref in channels:
            (ta, tb) = chan_tips[n]
            assert abs(ta[1] - tb[1]) < 1e-6
            y = ta[1]
            nodes = [ta[0]]
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
            nodes = sorted(set(nodes))
            for xa, xb in zip(nodes, nodes[1:]):
                self.pl.plan(n, (xa, y), (xb, y))
            if c.nets[n].net_class is NetClass.SIGNAL:
                self.llabel(n, ta[0] + 1.27, y)

        # trunks
        for t in trunk_jobs.values():
            self._build_trunk(t)

        # texts last: they dodge every wire/box, never the other way round
        for pp, body in self._deferred_texts:
            self._part_texts(pp, body)
        self._deferred_texts = []

        # leftover rail-rooted chains, decoupling cluster, flags
        for ch in [ch for ch in self.float_chains if ch.kind == "rail"]:
            self._leftover_chains_columns()
            break
        first = order[0]
        pp0 = next(p for p in self.pl.parts if p.ref == first)
        sdef0 = self.lib.get(pp0.lib_id)
        body0 = body_box_page(sdef0, pp0.x, pp0.y, 0, "body", first)
        self._decoupling_cluster(pp0.x, pp0.y, body0)
        self._flags_row()
        return self.pl

    def _pin_num_at(self, ref: str, tip_rel, side: str) -> str:
        for (r, num, s, t) in self._side_tips(ref):
            if s == side and t == tip_rel:
                return num
        raise PlaceError(f"{ref}: no {side} pin at {tip_rel}")

    # ---- dispatch -------------------------------------------------------------------
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


# ---- top level ------------------------------------------------------------------

def _translate(pl: Placement, dx: float, dy: float) -> None:
    def mv(t):
        return None if t is None else (round(t[0] + dx, 3),
                                       round(t[1] + dy, 3), t[2])
    for p in pl.parts:
        p.x = round(p.x + dx, 3); p.y = round(p.y + dy, 3)
        p.ref_pos = mv(p.ref_pos); p.val_pos = mv(p.val_pos)
    for pw in pl.powers:
        pw.x = round(pw.x + dx, 3); pw.y = round(pw.y + dy, 3)
        pw.val_pos = mv(pw.val_pos)
    for h in pl.hlabels:
        h.x = round(h.x + dx, 3); h.y = round(h.y + dy, 3)
    for ll in pl.llabels:
        ll.x = round(ll.x + dx, 3); ll.y = round(ll.y + dy, 3)
    for n in pl.no_connects:
        n.x = round(n.x + dx, 3); n.y = round(n.y + dy, 3)
    for net, paths in pl.plans.items():
        pl.plans[net] = [[(round(x + dx, 3), round(y + dy, 3))
                          for x, y in path] for path in paths]
    pl.boxes = [Box(b.x0 + dx, b.y0 + dy, b.x1 + dx, b.y1 + dy, b.kind, b.owner)
                for b in pl.boxes]


def center_on_sheet(pl: Placement) -> Placement:
    """Translate a placement so its bounding box centers on the A4 sheet."""
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
    return center_on_sheet(_Engine(c, lib, sp).run())


def place_and_route(c: Circuit, lib: Library, max_attempts: int = 8):
    """Feasibility loop: route + visual gate as the oracle; spacing expands,
    rules never relax. Returns (placement, routed, SheetGeometry).

    There is NO per-subsystem builder hook: every sheet's geometry is derived
    from its netlist topology by the engine (purity is a build gate)."""
    sp = Spacing()
    last = "?"
    for _ in range(max_attempts):
        pl = build(c, lib, sp)
        try:
            routed = route.route(c, pl, lib)
        except route.RouteError as e:
            last = f"route: {e}"
            sp = sp.expanded()
            continue
        geo = SheetGeometry(boxes=list(pl.boxes), wires=list(routed.segs))
        vis = visual_gate.check(geo)
        if vis.ok:
            return pl, routed, geo
        last = vis.summary()
        sp = sp.expanded()
    raise PlaceError(f"placement infeasible after {max_attempts} expansions; "
                     f"last failure:\n{last}")
