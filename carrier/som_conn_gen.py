"""SoM mezzanine connector sheets (J1/J2/J3) — GENERATED, never hand-typed.

The pin→net map is loaded from ``carrier/som_interface.json`` (itself
extracted from the SoM KiCad project by ``schgen som-interface``); each
``circuit()`` instantiates the mating DF40C-100DS-0.4V(51) receptacle
(parts/DF40C-100DS-0.4V_51/, LCSC C597931) and binds EVERY pin to its
contract net VERBATIM:

- power pins  -> POWER nets (carrier spelling: the SoM writes ``VIN``, the
  carrier writes ``+VIN`` — the ONLY rail alias, mirrored from
  schgen.link.RAIL_ALIASES; all other rails are identity spellings),
- GND pins    -> the GROUND net,
- signal pins -> PORT nets. No ``expect=`` deferrals here BY DESIGN: these
  sheets ARE the SoM side of the contract, so every port resolves against
  ``som_interface.json`` by construction; consumers (ethernet, usb_pd, …)
  bind to the same names from their own sheets.

Typed ports (only applied to nets present on the connector): the four
ethernet MDI pairs (100R diff, matching the ethernet sheet), the two USB 2.0
pairs (90R), and the SDIO bus typed ``sd_bus(level_v=1.8)`` — the SoM runs
SDIO at 1.8 V straight into the Zynq (carrier/PLAN.md round 2: the carrier
microSD subsystem must level-translate).

Layout (shared placer): connector body centered; signals fan straight out to
global labels in TWO alternating columns (adjacent 2.54 mm rows can never
collide); each rail collects on a vertical trunk — top/bottom rails get an
upright/inverted power symbol just past the column end, mid-column rails run
past the label field to a trunk with a SIDEWAYS power symbol (the strip stays
inside its own row, so nothing protrudes into neighbouring rows), and GND
takes the outermost trunk down to a single GND symbol below the sheet. One
PWR_FLAG pair per rail in the corner row (board linker dedups board-wide).
"""

from __future__ import annotations

import json
from pathlib import Path

from schgen import place
from schgen import textmetrics as tm
from schgen.emit import PlacedPart, PlacedPower
from schgen.model import Circuit, NetClass, PinRef
from schgen.place import (Placement, Spacing, _Builder, body_box_page, gceil,
                          gsnap)
from schgen.symbols import Library, pin_page_position
from schgen.verify.visual_gate import Box

CONTRACT = Path(__file__).resolve().parent / "som_interface.json"

LIB_ID = "DF40C-100DS-0.4V_51:DF40C-100DS-0.4V_51"
FOOTPRINT = "DF40C-100DS-0.4V_51:DF40C-100DS-0.4V_51"
VALUE = "DF40C-100DS-0.4V(51)"
LCSC = "C597931"

# Carrier house spelling for SoM rail names (inverse of link.RAIL_ALIASES —
# the single enumerated rail alias; signals are NEVER respelled).
RAIL_SPELLING = {"VIN": "+VIN"}

# Differential pairs on the contract (applied only when both nets are on the
# connector being generated). Impedances per the JLC04161H-7628 stackup plan.
PAIR_TYPES = [
    ("ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N", "diff_pair", 100),
    ("ETH_PHY_MDI1_P", "ETH_PHY_MDI1_N", "diff_pair", 100),
    ("ETH_PHY_MDI2_P", "ETH_PHY_MDI2_N", "diff_pair", 100),
    ("ETH_PHY_MDI3_P", "ETH_PHY_MDI3_N", "diff_pair", 100),
    ("STM32_USB_D_P", "STM32_USB_D_N", "usb_hs_pair", None),
    ("USB_D+", "USB_D-", "usb_hs_pair", None),
]
# SoM-side SDIO runs at 1.8 V (verified against the SoM netlist 2026-06-10).
SD_BUS = ["SDIO_CLK", "SDIO_CMD", "SDIO_D0", "SDIO_D1", "SDIO_D2", "SDIO_D3"]


def contract_pins(jref: str) -> dict[str, str]:
    data = json.loads(CONTRACT.read_text())
    return data["connectors"][jref]["pins"]


def connector_circuit(jref: str, name: str, title: str) -> Circuit:
    c = Circuit(name, title)
    c.part(jref, LIB_ID, VALUE, FOOTPRINT, LCSC=LCSC)
    seen_ports: set[str] = set()
    for pin, som_net in sorted(contract_pins(jref).items(), key=lambda kv: int(kv[0])):
        net = RAIL_SPELLING.get(som_net, som_net)
        cls = Circuit.classify(net)
        if cls in (NetClass.POWER, NetClass.GROUND):
            c.net(net, f"{jref}.{pin}")
        else:
            if net in seen_ports:
                raise ValueError(
                    f"{jref}: contract net {net!r} repeats on this connector "
                    f"— placer assumes one row per signal; extend it")
            seen_ports.add(net)
            c.port(net, f"{jref}.{pin}")
    for p, n, kind, imp in PAIR_TYPES:
        if p in c.nets and n in c.nets:
            c.port_type(p, kind=kind, pair_with=n, impedance=imp)
    if all(s in c.nets for s in SD_BUS):
        for s in SD_BUS:
            c.port_type(s, kind="sd_bus", bus="SDIO", level_v=1.8)
    return c


# ---- layout constants (page coords, connector anchored at (0,0)) -------------

RUN = 10.16          # pin tip -> inner label column
COL_GAP = 1.27       # inner label text edge -> outer label anchor
MID_GAP = 2.54       # outer label text edge -> mid-rail trunk
STRIP_STUB = 2.54    # mid-rail trunk -> sideways symbol pin
STRIP_BAR = 2.54     # sideways symbol glyph length
EXT = 2.54           # trunk end -> upright/inverted symbol pin
ROW = 2.54           # connector pin pitch
FLAG_Y = 83.82       # PWR_FLAG corner row (below everything)


def _glabel_len(net: str) -> float:
    return tm.text_wh(net)[0] + tm.GLABEL_PAD_LEN * tm.SIZE


def _out(sgn: int, mag: float) -> float:
    """Grid-snap a magnitude outward (away from the body) on side ``sgn``."""
    return sgn * gceil(mag)


def _power_at(b: _Builder, net: str, x: float, y: float, rot: int,
              val_pos: tuple[float, float] | None) -> None:
    """A power symbol with a placer-owned value position (b.power computes
    the value anchor from the symbol def, which only suits upright text).

    KiCad renders a symbol property at (property angle + symbol angle), so a
    sideways (rot 90/270) rail symbol needs property rot 90 for the value to
    READ horizontally — 90+270=0 and 90+90=180, which KiCad normalises to
    readable 0. The registered box is the horizontal text extent.
    """
    lib_id = place.POWER_LIBS[net]
    sdef = b.lib.get(lib_id)
    b._pwr += 1
    ref = f"#PWR{b._pwr:02d}"
    show = val_pos is not None
    vrot = 90 if rot in (90, 270) else 0
    pw = PlacedPower(lib_id, net, ref, x, y, rot, net=net,
                     val_pos=(val_pos[0], val_pos[1], vrot) if show else None,
                     show_value=show)
    b.pl.powers.append(pw)
    b.pl.boxes.append(body_box_page(sdef, x, y, rot, "body", ref))
    if show:
        b.pl.boxes.append(Box(*tm.centered_box(net, val_pos[0], val_pos[1]),
                              "value", ref))


def connector_placer(c: Circuit, lib: Library, sp: Spacing) -> Placement:
    b = _Builder(c, lib, sp)
    pl = b.pl
    jref = next(iter(c.parts))
    part = c.parts[jref]
    sdef = lib.get(part.lib_id)
    ax, ay = 0.0, 0.0

    # ---- the connector body; value runs vertically inside the tall outline --
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
    pl.boxes.extend(place._pin_text_boxes(sdef, pl.parts[-1]))

    # ---- per-side layout -----------------------------------------------------
    for side_rot, sgn in ((0, -1), (180, +1)):
        rows = sorted(((pin_page_position(p, ax, ay, 0), p)
                       for p in sdef.pins if p.rotation == side_rot),
                      key=lambda t: t[0][1])
        ports: list[tuple[float, float, str]] = []   # (y, tip_x, net)
        rails: dict[str, list[tuple[float, float]]] = {}
        for (px, py), pin in rows:
            net = c.net_of(PinRef(jref, pin.number))
            assert net is not None, f"{jref}.{pin.number} unnetted"
            if net.net_class is NetClass.PORT:
                ports.append((py, px, net.name))
            else:
                rails.setdefault(net.name, []).append((py, px))

        # -- signal labels: two alternating columns ----------------------------
        lx_inner = sgn * (5.08 + RUN)
        cols: list[str] = []
        prev_y = prev_col = None
        for y, _, _ in ports:
            col = ("outer" if prev_y is not None
                   and abs(y - prev_y - ROW) < 1e-6 and prev_col == "inner"
                   else "inner")
            cols.append(col)
            prev_y, prev_col = y, col
        inner_len = max((_glabel_len(n) for (y, x, n), cl in zip(ports, cols)
                         if cl == "inner"), default=0.0)
        lx_outer = _out(sgn, abs(lx_inner) + inner_len + COL_GAP)
        outer_len = max((_glabel_len(n) for (y, x, n), cl in zip(ports, cols)
                         if cl == "outer"), default=0.0)
        for (y, px, net), col in zip(ports, cols):
            lx = lx_inner if col == "inner" else lx_outer
            pl.plan(net, (px, y), (lx, y))
            b.label(net, lx, y, 180 if sgn < 0 else 0)
        label_edge = max(abs(lx_outer) + outer_len, abs(lx_inner) + inner_len)

        # -- rails --------------------------------------------------------------
        port_ys = [y for y, _, _ in ports]
        y_lo = min(port_ys) if port_ys else float("inf")
        y_hi = max(port_ys) if port_ys else float("-inf")
        mid_x = _out(sgn, label_edge + MID_GAP)
        strip_reach = 0.0
        gnd_items = []

        def trunk(net: str, taps: list[tuple[float, float]], x_r: float) -> None:
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
            assert not foreign, (f"{net}: foreign rail row inside trunk span "
                                 f"on side {sgn} — extend the placer")
            if ys[-1] < y_lo:                       # column-top rail
                trunk(net, taps, lx_inner)
                pl.plan(net, (lx_inner, ys[0]), (lx_inner, ys[0] - EXT))
                b.power(net, lx_inner, ys[0] - EXT, 0)
            elif ys[0] > y_hi:                      # column-bottom rail
                trunk(net, taps, lx_inner)
                pl.plan(net, (lx_inner, ys[-1]), (lx_inner, ys[-1] + EXT))
                b.power(net, lx_inner, ys[-1] + EXT, 180)
            else:                                   # mid-column rail: sideways
                trunk(net, taps, mid_x)
                y_end = ys[0]
                anchor = (mid_x + sgn * STRIP_STUB, y_end)
                pl.plan(net, (mid_x, y_end), anchor)
                w = tm.text_wh(net)[0]
                vx = anchor[0] + sgn * (STRIP_BAR + 0.42 + w / 2)
                _power_at(b, net, anchor[0], anchor[1],
                          90 if sgn < 0 else 270, (vx, y_end))
                strip_reach = max(strip_reach,
                                  STRIP_STUB + STRIP_BAR + 0.42 + w + 0.5)

        # -- GND: the outermost trunk, one symbol below -------------------------
        inner_limit = max(label_edge, abs(mid_x) + strip_reach)
        x_g = _out(sgn, inner_limit + 5.08)
        for net, taps in gnd_items:
            trunk(net, taps, x_g)
            y_bot = taps[-1][0]
            pl.plan(net, (x_g, y_bot), (x_g, y_bot + EXT))
            b.power(net, x_g, y_bot + EXT, 0)

    # ---- PWR_FLAG corner row (ERC: rails must be driven; one pair per rail) --
    rail_nets = sorted(n.name for n in c.nets.values()
                       if n.net_class in (NetClass.POWER, NetClass.GROUND))
    fx = gsnap(-sp.flag_pitch * (len(rail_nets) - 1) / 2)
    for net in rail_nets:
        if c.nets[net].net_class is NetClass.GROUND:
            b.power(net, fx, FLAG_Y)
            pl.plan(net, (fx, FLAG_Y), (fx, FLAG_Y - 2.54))
            b.flag(net, fx, FLAG_Y - 2.54, 0)
        else:
            b.power(net, fx, FLAG_Y)
            pl.plan(net, (fx, FLAG_Y), (fx, FLAG_Y + 2.54))
            b.flag(net, fx, FLAG_Y + 2.54, 180)
        fx += sp.flag_pitch

    return place.center_on_sheet(pl)
