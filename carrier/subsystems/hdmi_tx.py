"""hdmi_tx — HDMI source port: Zynq -> TPD12S016 -> HDMI Type-A receptacle.

Reference circuit per TI TPD12S016 (SLLSE96F) Figure 15, "HDMI source using
one GPIO", with CT_HPD and LS_OE strapped HIGH (10k to V_CCA) so the level
shifters and the on-chip 55 mA +5V load switch are always on:

  * The 8 TMDS lines flow THROUGH the TPD's clamp pads to the receptacle.
    The schgen:TPD12S016 symbol draws them flow-through: each TMDS pad is a
    DUPLICATE pin number on both body edges (duplicate_pin_numbers_are_
    jumpers — KiCad nets the two edges as ONE pad; proven against kicad-cli
    netlist export, and the netlist gate re-proves it on every build).
  * DDC (SCL/SDA), CEC and HPD pass through the TPD's level shifters:
    A-side nets (ZYNQ_HDMI_TX_*) are V_CCA-domain ports to the Zynq PL;
    B-side nets (HDMI_TX_CON_*) run at the cable's 5 V to the receptacle.
    All DDC/CEC/HPD pull-ups are integrated (DS Sec 7.3.9/7.3.15) — no
    external resistors, and no EDID EEPROM (a SOURCE reads the sink's EDID).
  * 5V_OUT (the current-limited switch output) sources receptacle pin 18;
    100n HF + 1u bulk at the connector per HDMI 1.4 Sec 4.2.7.
  * Rails are the bring-up dossier's GATED module rails: +3V3_HDMI_TX on
    V_CCA (controller side) and +5V_HDMI_TX on V_CC5V (cable side), each
    decoupled 100n (DS Fig 15). The SY6280 gates live on the bringup sheet.
  * Receptacle: SOFNG HDMI-019S; shield/CK..D2 ground pins to GND, the four
    shell legs to CHASSIS_GND (star-bonded elsewhere). Pin 14 (HEC/Utility)
    is reserved -> author no-connect (HDMI 1.4: N.C. on non-HEAC devices).

Pin maps are the LCSC/EasyEDA tables fetched by `schgen part add C201665` /
`add C111617` (parts/TPD12S016PWR, parts/HDMI-019S) — the schgen symbols are
asserted against them at generation time, and `c.validate` + the netlist
gate re-check every pin on every build.
"""

from __future__ import annotations

from schgen import place
from schgen import textmetrics as tm
from schgen.emit import NoConnect, PlacedPart
from schgen.model import Circuit
from schgen.place import Placement, Spacing, _Builder, _pin, body_box_page
from schgen.symbols import Library, pin_page_position
from schgen.verify.visual_gate import Box

LIB_U = "schgen:TPD12S016"
LIB_J = "schgen:HDMI_A_019S"
FP_U = "TPD12S016PWR:TPD12S016PWR"      # faithful EasyEDA->KiCad conversion
FP_J = "HDMI-019S:HDMI-019S"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_U = "C201665"      # TPD12S016PWR, TSSOP-24
LCSC_J = "C111617"      # SOFNG HDMI-019S receptacle
LCSC_100N = "C1591"     # CL10B104KB8NNNC 100n 0603 X7R 50V (JLC Basic)
LCSC_1U = "C15849"      # CL10A105KB8NNNC 1u 0603 X5R 25V (JLC Basic)
LCSC_10K = "C25804"     # 0603WAF1002T5E 10k 1% (JLC Basic)

J2_MAP = "som_j2_connector (wave 3 PL function map)"

# TMDS lane -> (TPD flow-through pad, receptacle pin). Sources: TI SLLSE96F
# Sec 5 pin map; HDMI 1.4 Sec 4.2.2 connector pinout (both re-checked against
# the parts/<MPN>/part.py LCSC tables).
TMDS_LANES = (
    ("2_P", "23", "1"), ("2_N", "22", "3"),
    ("1_P", "21", "4"), ("1_N", "20", "6"),
    ("0_P", "18", "7"), ("0_N", "17", "9"),
    ("CLK_P", "16", "10"), ("CLK_N", "15", "12"),
)
# level-shifted lines: port name suffix -> (TPD A pin, TPD B pin, recept. pin)
SHIFTED = (
    ("CEC", "1", "7", "13"),
    ("SCL", "2", "8", "15"),
    ("SDA", "3", "9", "16"),
    ("HPD", "4", "10", "19"),
)


def circuit() -> Circuit:
    c = Circuit("hdmi_tx", "HDMI TX: TPD12S016 + HDMI-A receptacle (source)")
    c.part("U1", LIB_U, "TPD12S016PWR", FP_U, LCSC=LCSC_U)
    c.part("J1", LIB_J, "HDMI-019S", FP_J, LCSC=LCSC_J)

    # gated module rails (bringup_power_gating dossier) + DS Fig 15 decoupling
    c.net("+3V3_HDMI_TX", "U1.24")                 # V_CCA, controller side
    c.net("+5V_HDMI_TX", "U1.11")                  # V_CC5V, load-switch input
    for cap in c.decouple("U1.24", "100n", footprint=C_FP):       # C1
        cap.fields["LCSC"] = LCSC_100N
    for cap in c.decouple("U1.11", "100n", footprint=C_FP):       # C2
        cap.fields["LCSC"] = LCSC_100N

    # TMDS: Zynq port -> TPD clamp pad (flow-through) -> receptacle
    for lane, upin, jpin in TMDS_LANES:
        c.port(f"ZYNQ_HDMI_TX_TMDS_{lane}", f"U1.{upin}", f"J1.{jpin}")
    for lane in ("2", "1", "0", "CLK"):
        c.port_type(f"ZYNQ_HDMI_TX_TMDS_{lane}_P", kind="tmds_pair",
                    pair_with=f"ZYNQ_HDMI_TX_TMDS_{lane}_N", expect=J2_MAP)

    # DDC/CEC/HPD: A-side ports (Zynq), B-side wired nets (receptacle)
    c.port("ZYNQ_HDMI_TX_CEC", "U1.1", expect=J2_MAP)
    c.port("ZYNQ_HDMI_TX_SCL", "U1.2", kind="i2c", role="scl",
           bus="HDMI_TX_DDC", speed_hz=100_000, expect=J2_MAP)
    c.port("ZYNQ_HDMI_TX_SDA", "U1.3", kind="i2c", role="sda",
           bus="HDMI_TX_DDC", speed_hz=100_000, expect=J2_MAP)
    c.port("ZYNQ_HDMI_TX_HPD", "U1.4", expect=J2_MAP)
    for name, _a, bpin, jpin in SHIFTED:
        c.net(f"HDMI_TX_CON_{name}", f"U1.{bpin}", f"J1.{jpin}")

    # switched cable +5V: 5V_OUT -> pin 18, 100n HF + 1u bulk at the connector
    c.net("HDMI_TX_CON_5V0", "U1.13", "J1.18")
    for ref, val, lcsc in (("C3", "100n", LCSC_100N), ("C4", "1u", LCSC_1U)):
        c.part(ref, "Device:C", val, C_FP, LCSC=lcsc)
        c.net("HDMI_TX_CON_5V0", f"{ref}.1")
        c.net("GND", f"{ref}.2")

    # always-on straps: LS_OE + CT_HPD 10k to V_CCA (DS Fig 15 / Sec 8.2.1)
    c.net("HDMI_TX_LS_OE", "U1.5")
    c.net("HDMI_TX_CT_HPD", "U1.12")
    c.pullup("U1.5", "10k", "+3V3_HDMI_TX", footprint=R_FP).fields["LCSC"] = LCSC_10K   # R1
    c.pullup("U1.12", "10k", "+3V3_HDMI_TX", footprint=R_FP).fields["LCSC"] = LCSC_10K  # R2

    # grounds: TPD GND pins + receptacle TMDS shields/DDC ground; the four
    # shell legs bond to the chassis island (separate net, star-bond elsewhere)
    c.net("GND", "U1.6", "U1.14", "U1.19",
          "J1.2", "J1.5", "J1.8", "J1.11", "J1.17")
    c.net("CHASSIS_GND", "J1.20", "J1.21", "J1.22", "J1.23")

    # pin 14 = HEC/Utility, reserved (N.C. on non-HEAC devices, HDMI 1.4)
    c.nc("J1.14")
    return c


# ---- datasheet template: TPD flow-through into the receptacle ----------------
#
#  ZYNQ_..._TMDS_* >――[ U1 TPD12S016 ]――straight rows――[ J1 HDMI-A ]―GND bus
#  ZYNQ_..._CEC/SCL/SDA/HPD >――[ level shift ]――HDMI_TX_CON_*――     ―SHELL bus
#         straps LS_OE/CT_HPD ―10k― +3V3_HDMI_TX        5V row ―100n+1u― GND
#
# All geometry in U1-anchored page coords (U1 at 0,0), 1.27 grid, +Y down.

DXJ = 49.53          # J1 anchor: straight 25.4 mm runs between the bodies
RUN = 10.16          # TPD left pin tip -> port label anchor
X_STRAP = (-53.34, -58.42)   # LS_OE / CT_HPD pull-up columns (left of labels)
Y_RAIL_BAR = 15.24   # shared +3V3_HDMI_TX bar joining R1/R2 tops
X_GBUS = 66.04       # J1-side GND / shell bus column
Y_CAP = 46.99        # decoupling cluster cap-anchor row
X_CAPS = (-40.64, -22.86)    # C1 (+3V3) / C2 (+5V) columns
X_5VCAPS = (20.32, 27.94)    # C3 / C4 taps on the switched-5V row
Y_FLAGS = 60.96      # PWR_FLAG corner row
FLAG_X = {"GND": -60.96, "CHASSIS_GND": -45.72,
          "+3V3_HDMI_TX": -27.94, "+5V_HDMI_TX": -7.62}


def placer(c: Circuit, lib: Library, sp: Spacing) -> Placement:
    b = _Builder(c, lib, sp)
    pl = b.pl

    # ---- the two bodies --------------------------------------------------------
    def body_part(ref: str, lib_id: str, ax: float,
                  ref_pos, val_pos) -> dict[int, dict[str, tuple[float, float]]]:
        part = c.parts[ref]
        sdef = lib.get(lib_id)
        body = body_box_page(sdef, ax, 0.0, 0, "body", ref)
        pp = PlacedPart(ref, lib_id, part.value, ax, 0.0, 0, part.footprint,
                        ref_pos=ref_pos, val_pos=val_pos)
        pl.parts.append(pp)
        pl.boxes.append(body)
        pl.boxes.append(Box(*tm.centered_box(ref, ref_pos[0], ref_pos[1]),
                            "reference", ref))
        pl.boxes.append(Box(*tm.centered_box(part.value, val_pos[0], val_pos[1]),
                            "value", ref))
        pl.boxes.extend(place._pin_text_boxes(sdef, pp))
        sides: dict[int, dict[str, tuple[float, float]]] = {0: {}, 90: {}, 180: {}, 270: {}}
        for p in sdef.pins:
            sides[p.rotation][p.number] = pin_page_position(p, ax, 0.0, 0)
        return sides

    u = body_part("U1", LIB_U, 0.0,
                  ref_pos=(-8.89, -42.545, 0), val_pos=(-19.05, -42.545, 0))
    j = body_part("J1", LIB_J, DXJ,
                  ref_pos=(DXJ - 6.35, -40.005, 0), val_pos=(DXJ, 35.56, 0))
    ul, ur, ut, ub = u[0], u[180], u[270], u[90]      # left/right/top/bottom
    jl, jr = j[0], j[180]

    # ---- TMDS rows: label -> left pad, right pad -> receptacle (straight) ------
    for lane, upin, jpin in TMDS_LANES:
        net = f"ZYNQ_HDMI_TX_TMDS_{lane}"
        lx, ly = ul[upin]
        pl.plan(net, (lx, ly), (lx - RUN, ly))
        b.label(net, lx - RUN, ly, 180, shape="output")
        rx, ry = ur[upin]
        pl.plan(net, (rx, ry), jl[jpin])

    # ---- level-shifted rows: A-side ports, B-side drawn + named ----------------
    shapes = {"CEC": "bidirectional", "SCL": "output",
              "SDA": "bidirectional", "HPD": "input"}
    for name, apin, bpin, jpin in SHIFTED:
        net = f"ZYNQ_HDMI_TX_{name}"
        lx, ly = ul[apin]
        pl.plan(net, (lx, ly), (lx - RUN, ly))
        b.label(net, lx - RUN, ly, 180, shape=shapes[name])
        con = f"HDMI_TX_CON_{name}"
        rx, ry = ur[bpin]
        pl.plan(con, (rx, ry), jl[jpin])
        b.llabel(con, rx + 1.27, ry)

    # ---- switched 5V row: straight run + 100n/1u hanging at the connector ------
    x13, y13 = ur["13"]
    nodes = [x13, *X_5VCAPS, jl["18"][0]]
    for xa, xb in zip(nodes, nodes[1:]):
        pl.plan("HDMI_TX_CON_5V0", (xa, y13), (xb, y13))
    b.llabel("HDMI_TX_CON_5V0", x13 + 1.27, y13)
    c_off = abs(_pin(lib.get("Device:C"), "1").y)
    crot = 0 if _pin(lib.get("Device:C"), "1").y > 0 else 180
    for x, ref in zip(X_5VCAPS, ("C3", "C4")):
        cy = y13 + 5.08 + c_off                      # cap anchor below the row
        pl.plan("HDMI_TX_CON_5V0", (x, y13), (x, cy - c_off))
        b.passive(ref, x, cy, crot,
                  text_side="left" if ref == "C3" else "right")
        b.power("GND", x, cy + c_off)

    # ---- straps: LS_OE / CT_HPD -> 10k -> shared +3V3_HDMI_TX bar ---------------
    r_off = abs(_pin(lib.get("Device:R"), "1").y)
    rrot = 0 if _pin(lib.get("Device:R"), "1").y > 0 else 180
    for (apin, net, ref, xcol), tside in zip(
            (("5", "HDMI_TX_LS_OE", "R1", X_STRAP[0]),
             ("12", "HDMI_TX_CT_HPD", "R2", X_STRAP[1])),
            ("right", "left")):
        px, py = ul[apin]
        pl.plan(net, (px, py), (xcol, py))
        pl.plan(net, (xcol, py), (xcol, Y_RAIL_BAR + 2 * r_off))
        b.passive(ref, xcol, Y_RAIL_BAR + r_off, rrot, text_side=tside)
        b.llabel(net, px - 17.78, py)
    xm = round((X_STRAP[0] + X_STRAP[1]) / 2, 3)
    pl.plan("+3V3_HDMI_TX", (X_STRAP[1], Y_RAIL_BAR), (xm, Y_RAIL_BAR))
    pl.plan("+3V3_HDMI_TX", (xm, Y_RAIL_BAR), (X_STRAP[0], Y_RAIL_BAR))
    b.power("+3V3_HDMI_TX", xm, Y_RAIL_BAR)

    # ---- rails into the top edge -------------------------------------------------
    x24, y24 = ut["24"]
    pl.plan("+3V3_HDMI_TX", (x24, y24), (x24, y24 - 2.54))
    b.power("+3V3_HDMI_TX", x24, y24 - 2.54)
    x11, y11 = ut["11"]
    pl.plan("+5V_HDMI_TX", (x11, y11), (x11, y11 - 2.54), (12.7, y11 - 2.54))
    b.power("+5V_HDMI_TX", 12.7, y11 - 2.54)

    # ---- TPD ground bus (pins 6/14/19 share one bar + symbol) -------------------
    gxs = sorted(pt[0] for pt in ub.values())
    gy = ub["14"][1]
    for x in gxs:
        pl.plan("GND", (x, gy), (x, gy + 2.54))
    for xa, xb in zip(gxs, gxs[1:]):
        pl.plan("GND", (xa, gy + 2.54), (xb, gy + 2.54))
    b.power("GND", gxs[1], gy + 2.54)

    # ---- decoupling cluster (rail on top, GND below — DS Fig 15) ----------------
    for x, ref, rail in zip(X_CAPS, ("C1", "C2"),
                            ("+3V3_HDMI_TX", "+5V_HDMI_TX")):
        b.passive(ref, x, Y_CAP, crot, text_side="right")
        b.power(rail, x, Y_CAP - c_off)
        b.power("GND", x, Y_CAP + c_off)

    # ---- receptacle ground + shell buses (right side) ----------------------------
    def bus(pins: list[str], side: dict, net: str, sym_dy: float) -> None:
        ys = sorted(side[p][1] for p in pins)
        for p in pins:
            x, y = side[p]
            pl.plan(net, (x, y), (X_GBUS, y))
        for ya, yb in zip(ys, ys[1:]):
            pl.plan(net, (X_GBUS, ya), (X_GBUS, yb))
        pl.plan(net, (X_GBUS, ys[-1]), (X_GBUS, ys[-1] + sym_dy))
        b.power(net, X_GBUS, ys[-1] + sym_dy)

    bus(["2", "5", "8", "11", "17"], jr, "GND", 2.54)
    bus(["20", "21", "22", "23"], jr, "CHASSIS_GND", 2.54)
    pl.no_connects.append(NoConnect(*jr["14"]))

    # ---- PWR_FLAG corner (one per rail; the board linker dedups) -----------------
    for net, fx in FLAG_X.items():
        b.power(net, fx, Y_FLAGS)
        if net.startswith("+"):
            pl.plan(net, (fx, Y_FLAGS), (fx, Y_FLAGS + 2.54))
            b.flag(net, fx, Y_FLAGS + 2.54, 180)
        else:
            pl.plan(net, (fx, Y_FLAGS), (fx, Y_FLAGS - 2.54))
            b.flag(net, fx, Y_FLAGS - 2.54, 0)

    return place.center_on_sheet(pl)
