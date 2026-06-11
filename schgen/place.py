"""Datasheet-template placement: deterministic, corridor-reserving, honest.

One template family: an IC centered, its external-interface signals fanned to
the side their pins live on (staircased so pull-up / filter-cap columns never
cross another net's wire OR another label's text), decoupling caps in a tidy
rail cluster below-left, power flags in their own corner row. Every text
position is chosen against :mod:`schgen.textmetrics` boxes, and ALL geometry
(bodies, pin texts, ref/value, labels) is handed both to the router (as
blocked corridors) and to the visual gate (as the boxes it judges).

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
}


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


# ---- the template ------------------------------------------------------------

@dataclass
class _Line:
    """One fanned-out interface line on the IC's left or right side."""
    net: str
    pin_pt: tuple[float, float]
    attach: str | None        # ref of pull-up R / filter C tapping this line
    # (pull-up ref, pull-down ref) when the net is a divider mid-point:
    attach_div: tuple[str, str] | None = None
    net_class: NetClass = NetClass.PORT
    pin_etype: str = ""       # electrical type of the IC pin on this line


class _Builder:
    def __init__(self, c: Circuit, lib: Library, sp: Spacing) -> None:
        self.c = c
        self.lib = lib
        self.sp = sp
        self.pl = Placement()
        self._pwr = 0
        self._flg = 0

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
        # KiCad composes property-text angle with the symbol rotation: a
        # 90/270-rotated passive needs angle 90 so the text renders upright
        # horizontal (the boxes below already assume horizontal text).
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

    def label(self, net: str, x: float, y: float, rot: int,
              shape: str = "bidirectional") -> None:
        self.pl.hlabels.append(HierLabel(net, x, y, rot, shape=shape))
        self.pl.boxes.append(Box(*tm.glabel_box(net, x, y, rot),
                                 "label", f"label:{net}"))

    def llabel(self, net: str, x: float, y: float, rot: int = 0) -> None:
        """Local net-name label ON a drawn wire (names the net for KiCad's
        netlist export; the wiring itself is untouched — never a label-bus)."""
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

    # -- the layout -------------------------------------------------------------
    def build(self) -> Placement:
        c, lib, sp = self.c, self.lib, self.sp
        ic_ref = max(c.parts, key=lambda r: len(lib.get(c.parts[r].lib_id).pins))
        ic = c.parts[ic_ref]
        sdef = lib.get(ic.lib_id)
        ax, ay = 0.0, 0.0

        # ---- classify the passives ------------------------------------------
        def _cls(ref: str, pin: str) -> NetClass | None:
            n = self.net_of(ref, pin)
            return n.net_class if n else None

        pullup_of: dict[str, tuple[str, str]] = {}    # signal net -> (ref, rail)
        hang_cap_of: dict[str, str] = {}              # signal net -> cap ref
        cluster: dict[str, list[str]] = {}            # rail -> [cap refs]
        for ref, part in c.parts.items():
            if ref == ic_ref:
                continue
            pins = sorted(lib.pin_numbers(part.lib_id))
            if len(pins) != 2:
                raise PlaceError(f"{ref}: template only handles 2-pin passives")
            n1, n2 = self.net_of(ref, pins[0]), self.net_of(ref, pins[1])
            if n1 is None or n2 is None:
                raise PlaceError(f"{ref}: unnetted passive")
            cls = {n1.net_class, n2.net_class}
            if cls == {NetClass.POWER, NetClass.GROUND}:
                rail = n1.name if n1.net_class == NetClass.POWER else n2.name
                cluster.setdefault(rail, []).append(ref)
            elif NetClass.POWER in cls:
                sig = n1 if n2.net_class == NetClass.POWER else n2
                rail = n2 if n2.net_class == NetClass.POWER else n1
                pullup_of[sig.name] = (ref, rail.name)
            elif NetClass.GROUND in cls:
                sig = n1 if n2.net_class == NetClass.GROUND else n2
                hang_cap_of[sig.name] = ref
            else:
                raise PlaceError(f"{ref}: unsupported passive role {cls}")

        # ---- the IC -----------------------------------------------------------
        body = body_box_page(sdef, ax, ay, 0, "body", ic_ref)
        u_ref_pos = (body.x1 - 2.54, body.y0 - 1.905, 0)     # above, top-right
        u_val_pos = (ax + 7.62, body.y1 + 2.03, 0)           # below, clear of GND stub
        self.pl.parts.append(PlacedPart(ic_ref, ic.lib_id, ic.value, ax, ay, 0,
                                        ic.footprint, ref_pos=u_ref_pos,
                                        val_pos=u_val_pos))
        self.pl.boxes.append(body)
        self.pl.boxes.append(Box(*tm.centered_box(ic_ref, *u_ref_pos[:2]),
                                 "reference", ic_ref))
        self.pl.boxes.append(Box(*tm.centered_box(ic.value, *u_val_pos[:2]),
                                 "value", ic_ref))
        self.pl.boxes.extend(_pin_text_boxes(sdef, self.pl.parts[-1]))

        # ---- group visible IC pins by side -------------------------------------
        sides: dict[str, list[tuple[Pin, tuple[float, float]]]] = {
            "left": [], "right": [], "top": [], "bottom": []}
        side_of_rot = {0: "left", 180: "right", 270: "top", 90: "bottom"}
        seen_pts: set[tuple[float, float]] = set()
        for pin in sdef.pins:
            if pin.hidden:
                continue
            pt = pin_page_position(pin, ax, ay, 0)
            if pt in seen_pts:
                continue
            seen_pts.add(pt)
            sides[side_of_rot[pin.rotation]].append((pin, pt))

        # ---- left/right interface fans ------------------------------------------
        for side in ("left", "right"):
            sgn = -1 if side == "left" else 1
            lines: list[_Line] = []
            # consecutive same-net POWER/GROUND pins share one rail bus, so
            # group the side's pins into runs first (sorted top-to-bottom)
            runs: list[list[tuple[Pin, tuple[float, float], object]]] = []
            for pin, pt in sorted(sides[side], key=lambda t: t[1][1]):
                net = self.net_of(ic_ref, pin.number)
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
                    jx = run[0][1][0] + sgn * 3.81
                    if len(run) == 1:
                        # short exclusive corner stub up/down to a rail symbol
                        pt = run[0][1]
                        dy = -5.08 if net0.net_class is NetClass.POWER else 5.08
                        end = (jx, pt[1] + dy)
                        self.pl.plan(net0.name, pt, (jx, pt[1]), end)
                    else:
                        # one vertical bus joins the run; the rail symbol sits
                        # directly on the outermost bus corner
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
                    if net.name in pullup_of and net.name in hang_cap_of:
                        attach_div = (pullup_of[net.name][0],
                                      hang_cap_of[net.name])
                    elif net.name in pullup_of:
                        attach = pullup_of[net.name][0]
                    elif net.name in hang_cap_of:
                        attach = hang_cap_of[net.name]
                    lines.append(_Line(net.name, pt, attach, attach_div,
                                       net.net_class, pin.etype))
            if not lines:
                continue
            # left side hangs pull-ups UP -> iterate top line first;
            # right side hangs caps DOWN -> iterate bottom line first.
            lines.sort(key=lambda l: l.pin_pt[1], reverse=(side == "right"))
            hang_sgn = -1 if side == "left" else 1
            rank_pin_y = lines[0].pin_pt[1] + hang_sgn * sp.hang_stub
            prev_label_edge: float | None = None
            prev_label_y: float | None = None
            # two label boxes only contend when their rows are this close:
            label_clash_dy = tm.GLABEL_H * tm.SIZE + 0.5
            for ln in lines:
                px, py = ln.pin_pt
                lx = px + sgn * sp.port_run
                if (prev_label_edge is not None and prev_label_y is not None
                        and abs(py - prev_label_y) < label_clash_dy):
                    want = prev_label_edge + sgn * (sp.stagger_extra
                                                    + sp.label_tap_gap)
                    lx = min(lx, gfloor(want)) if sgn < 0 else max(lx, gceil(want))
                if ln.net_class is not NetClass.PORT:
                    # internal SIGNAL line: drawn wire only — never a label.
                    tap = (lx, py)
                    self.pl.plan(ln.net, (px, py), tap)
                    if ln.attach_div:
                        self._divider(ln, tap)
                    elif ln.attach:
                        self._attach_column(ln, tap, rank_pin_y, side)
                    continue
                rot = 180 if side == "left" else 0
                if ln.attach or ln.attach_div:
                    tap = (lx - sgn * sp.label_tap_gap, py)  # between label & pin
                    self.pl.plan(ln.net, (px, py), tap)
                    self.pl.plan(ln.net, tap, (lx, py))
                    if ln.attach_div:
                        self._divider(ln, tap)
                    else:
                        self._attach_column(ln, tap, rank_pin_y, side)
                else:
                    self.pl.plan(ln.net, (px, py), (lx, py))
                # the label is the sheet's port: its direction mirrors the IC
                # pin (an input pin's port label DRIVES the net — KiCad's ERC
                # driver model — and renders the datasheet-correct chevron)
                shape = {"input": "input", "output": "output",
                         "tri_state": "tri_state", "open_collector": "output",
                         "open_emitter": "output"}.get(ln.pin_etype,
                                                       "bidirectional")
                self.label(ln.net, lx, py, rot, shape=shape)
                gb = tm.glabel_box(ln.net, lx, py, rot)
                prev_label_edge = gb[0] if sgn < 0 else gb[2]
                prev_label_y = py

        # ---- top/bottom power pins ------------------------------------------------
        for pin, pt in sides["top"]:
            net = self.net_of(ic_ref, pin.number)
            if net is None:
                self.pl.no_connects.append(NoConnect(*pt))
            elif net.net_class == NetClass.POWER:
                # short exclusive stub clears the neighbouring pin-number text
                end = (pt[0], pt[1] - 2.54)
                self.pl.plan(net.name, pt, end)
                self.power(net.name, *end)
            elif net.net_class == NetClass.GROUND:
                raise PlaceError(f"GND on top pin {pin.number}: extend template")
            else:
                raise PlaceError(f"signal on top pin {pin.number}: extend template")
        for pin, pt in sides["bottom"]:
            net = self.net_of(ic_ref, pin.number)
            if net is None:
                self.pl.no_connects.append(NoConnect(*pt))
            elif net.net_class in (NetClass.GROUND, NetClass.POWER):
                end = (pt[0], pt[1] + 2.54)
                self.pl.plan(net.name, pt, end)
                self.power(net.name, *end)
            else:
                raise PlaceError(f"signal on bottom pin {pin.number}: extend template")

        # ---- decoupling cluster -----------------------------------------------------
        col_x = ax - sp.cluster_dx
        # a tall IC body pushes the cap row below itself, never beside/inside;
        # a wide cluster shifts left so its columns clear the body's bottom
        # edge apparatus (GND stub/symbol) entirely
        n_caps = sum(len(v) for v in cluster.values())
        if n_caps:
            span = (n_caps - 1) * sp.cap_pitch
            col_x = min(col_x, gfloor(body.x0 - span - 4 * sp.hang_stub))
        col_x_start = col_x
        cy = max(ay + sp.cluster_dy, gceil(body.y1 + 3 * sp.hang_stub))
        for rail, caps in cluster.items():
            tops: list[float] = []
            for ref in caps:
                self._vertical_passive(ref, col_x, cy, rail_on_top=True)
                tops.append(col_x)
                col_x += sp.cap_pitch
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

        # ---- power-flag corner -------------------------------------------------------
        fy = cy + sp.flags_dy
        fx = min(ax - sp.cluster_dx, col_x_start)
        rails = [n for n in c.nets.values()
                 if n.net_class in (NetClass.POWER, NetClass.GROUND)]
        for net in rails:
            if net.net_class == NetClass.GROUND:
                self.power(net.name, fx, fy)                      # symbol down
                self.pl.plan(net.name, (fx, fy), (fx, fy - 2.54))
                self.flag(net.name, fx, fy - 2.54, 0)             # flag up
            else:
                self.power(net.name, fx, fy)                      # symbol up
                self.pl.plan(net.name, (fx, fy), (fx, fy + 2.54))
                self.flag(net.name, fx, fy + 2.54, 180)           # flag down
            fx += sp.flag_pitch

        return self.pl

    # -- attachment column (pull-up to rail / filter cap to ground) -----------------
    def _attach_column(self, ln: _Line, tap: tuple[float, float],
                       rank_pin_y: float, side: str) -> None:
        """Vertical 2-pin part at the tap: signal pin lands EXACTLY at
        (tap.x, rank_pin_y); the far pin gets a pin-exact power symbol."""
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
        pin_off = abs(_pin(sdef, sig_pin).y)                 # 3.81 for R/C
        self.pl.plan(ln.net, tap, (tap[0], rank_pin_y))      # exclusive stub
        if side == "left":
            # pull-up rank rises ABOVE the lines; signal pin at the BOTTOM
            anchor_y = rank_pin_y - pin_off
            rot = 180 if _pin(sdef, sig_pin).y > 0 else 0
            far_pt = (tap[0], anchor_y - pin_off)
        else:
            # filter cap hangs BELOW the lines; signal pin at the TOP
            anchor_y = rank_pin_y + pin_off
            rot = 0 if _pin(sdef, sig_pin).y > 0 else 180
            far_pt = (tap[0], anchor_y + pin_off)
        self.passive(ref, tap[0], anchor_y, rot)
        self.power(far_net.name, *far_pt)

    def _divider(self, ln: _Line, tap: tuple[float, float]) -> None:
        """Divider mid-point sense line (datasheet style): the pull-up R is
        stacked vertically ABOVE the tap up to its rail symbol, the pull-down
        R BELOW it down to its ground symbol; both signal pins land EXACTLY
        on the tap, so the line ends in a clean vertical divider."""
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

    def _vertical_passive(self, ref: str, x: float, cy: float,
                          rail_on_top: bool) -> None:
        part = self.c.parts[ref]
        sdef = self.lib.get(part.lib_id)
        pins = sorted(self.lib.pin_numbers(part.lib_id))
        n_by_pin = {p: self.net_of(ref, p) for p in pins}
        rail_pin = [p for p in pins
                    if n_by_pin[p] and n_by_pin[p].net_class == NetClass.POWER][0]
        gnd_pin = self.other_pin(ref, rail_pin)
        # rot 0 puts symbol pin with +y (symbol space) at page TOP
        rot = 0 if _pin(sdef, rail_pin).y > 0 else 180
        self.passive(ref, x, cy, rot)
        pin_off = abs(_pin(sdef, rail_pin).y)
        gnd_net = n_by_pin[gnd_pin]
        assert gnd_net is not None
        self.power(gnd_net.name, x, cy + pin_off)


def _pin(sdef: SymbolDef, number: str) -> Pin:
    for p in sdef.pins:
        if p.number == number:
            return p
    raise PlaceError(f"pin {number} not in {sdef.lib_id}")


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
    return center_on_sheet(_Builder(c, lib, sp).build())


def place_and_route(c: Circuit, lib: Library, max_attempts: int = 8,
                    builder=None):
    """Feasibility loop: route + visual gate as the oracle; spacing expands,
    rules never relax. Returns (placement, routed, SheetGeometry).

    ``builder`` (default: the generic IC template :func:`build`) is any
    ``(circuit, lib, spacing) -> Placement`` callable — subsystems with a
    datasheet-specific layout (e.g. magnetics + termination ladder) supply
    their own template; gates and router invariants are identical."""
    sp = Spacing()
    last = "?"
    make = builder or build
    for _ in range(max_attempts):
        pl = make(c, lib, sp)
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
