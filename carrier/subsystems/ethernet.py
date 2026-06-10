"""ethernet — HX5008NLT 1000BASE-T magnetics + Bob-Smith termination.

The wire-heavy stress test: the PHY-side MDI pairs (SoM PHY) and line-side
MDI pairs (RJ45) are PORT nets; the four line-side centre taps each carry a
75R || 1n/2kV pair down to a single BS_COMMON trunk (IEEE 802.3 Sec 40.7.1),
which bypasses to CHASSIS_GND through one shared 1n/2kV safety cap. Chassis
ground stays a separate net from signal GND (star-bonded elsewhere).

Pin->net intent follows the carrier's hand-audited ethernet block
(zynq_eda/projects/carrier/blocks/ethernet.py + hx5008nlt/refcircuit.py):
pins 1-8 PHY pairs, 19-26 line (TD) pairs, 9-12 line-side centre taps,
13 the magjack's own BS tap, 14 shield/odd-tap GND. The HX5008NLT symbol
is a schgen-local re-pin (shared/symbols/schgen.kicad_sym): centre taps on
the bottom edge so the Bob-Smith ladder drops straight onto a horizontal
trunk — junction dots only where the SAME net taps in (LAW 0).

Internal nets (CT0..CT3, BS_COMMON) are fully DRAWN; each carries one local
net-name label on its wire because kicad-cli's netlist export omits unnamed
nets (the netlist gate could not otherwise see a purely-drawn net). That is
naming, not label-bussing — connectivity is 100% copper.

PHY-side centre taps are not exposed (RTL8211F drives its own common-mode
bias — refcircuit.py "no_external_required"), so per the old block there
are no PHY-side 100n caps on this sheet. C1..C5 are 1 nF 2 kV X7R safety
parts (IEC 60950 hi-pot), value drawn "1n" for schematic economy.
"""

from __future__ import annotations

from schgen import place
from schgen import textmetrics as tm
from schgen.emit import PlacedPart
from schgen.model import Circuit
from schgen.place import Placement, Spacing, _Builder, _pin, body_box_page
from schgen.symbols import Library, pin_page_position
from schgen.verify.visual_gate import Box

LIB_ID = "schgen:HX5008NLT"
FOOTPRINT = "Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

# pin number -> PORT net. PHY side uses the SoM contract spellings VERBATIM
# (carrier/som_interface.json: ETH_PHY_MDI0_P .. ETH_PHY_MDI3_N) — the linker
# binds by exact name; the old ZYNQ_ETH_MDI_0_P spelling was name drift.
# Line side goes to the RJ45 connector subsystem (wave 2).
PHY_PORTS = {
    1: "ETH_PHY_MDI0_P", 2: "ETH_PHY_MDI0_N",
    3: "ETH_PHY_MDI1_P", 4: "ETH_PHY_MDI1_N",
    5: "ETH_PHY_MDI2_P", 6: "ETH_PHY_MDI2_N",
    7: "ETH_PHY_MDI3_P", 8: "ETH_PHY_MDI3_N",
}
LINE_PORTS = {
    19: "ETH_LINE_MDI_0_P", 20: "ETH_LINE_MDI_0_N",
    21: "ETH_LINE_MDI_1_P", 22: "ETH_LINE_MDI_1_N",
    23: "ETH_LINE_MDI_2_P", 24: "ETH_LINE_MDI_2_N",
    25: "ETH_LINE_MDI_3_P", 26: "ETH_LINE_MDI_3_N",
}


def circuit() -> Circuit:
    c = Circuit("ethernet", "Ethernet: HX5008NLT magnetics + Bob-Smith")
    c.part("T1", LIB_ID, "HX5008NLT", FOOTPRINT)

    for pin, net in PHY_PORTS.items():
        c.port(net, f"T1.{pin}")
    for pin, net in LINE_PORTS.items():
        c.port(net, f"T1.{pin}")

    # typed ports: every MDI pair is 100R differential (1000BASE-T).
    # PHY side binds to the SoM contract; line side awaits the RJ45 subsystem.
    for n in range(4):
        c.port_type(f"ETH_PHY_MDI{n}_P", kind="diff_pair",
                    pair_with=f"ETH_PHY_MDI{n}_N", impedance=100)
        c.port_type(f"ETH_LINE_MDI_{n}_P", kind="diff_pair",
                    pair_with=f"ETH_LINE_MDI_{n}_N", impedance=100,
                    expect="rj45_connector (wave 2)")

    # Bob-Smith: per line-side centre tap, 75R || 1n(2kV) into BS_COMMON
    for n in range(4):
        c.part(f"R{n + 1}", "Device:R", "75R", R_FP)
        c.part(f"C{n + 1}", "Device:C", "1n", C_FP)
        c.net(f"CT{n}", f"T1.{9 + n}", f"R{n + 1}.1", f"C{n + 1}.1")
        c.net("BS_COMMON", f"R{n + 1}.2", f"C{n + 1}.2")

    # single shared 1n/2kV from the BS trunk to the chassis island;
    # the magjack's own BS tap (pin 13) rides the same trunk
    c.part("C5", "Device:C", "1n", C_FP)
    c.net("BS_COMMON", "T1.13", "C5.1")
    c.net("CHASSIS_GND", "C5.2")
    c.net("GND", "T1.14")
    return c


# ---- datasheet template: magjack + Bob-Smith ladder ---------------------------
#
#   PHY ports --- [        T1        ] --- line ports
#                  CT0  CT1  CT2  CT3        |GND stub
#                   |R||C |...               '--GND
#   BS pin13 --.    |  |
#              '----+--+--o--o--o--o---trunk---[C5]--CHASSIS_GND
#
# All geometry in symbol-anchored page coords (T1 at 0,0), 1.27 grid.

RUN = 10.16          # pin tip -> port label anchor
BAR = 7.62           # R column -> C column inside one tap
Y_BAR = 33.02        # CT drop landing / top bar of each R||C pair
Y_R = 36.83          # 75R body center (text LEFT)
Y_RB = 40.64         # 75R bottom pin = top of its trunk drop
Y_C = 44.45          # 1n body center (text RIGHT, offset down: text never piles)
Y_TRUNK = 48.26      # the BS_COMMON trunk
X_RISER = -35.56     # pin-13 stub riser down the left flank
X_C5 = 38.1          # shared chassis cap at the trunk's right end
X_FLAGS = (-44.45, -24.13)   # PWR_FLAG corner row (GND, CHASSIS_GND)
Y_FLAGS = 60.96


def placer(c: Circuit, lib: Library, sp: Spacing) -> Placement:
    b = _Builder(c, lib, sp)
    pl = b.pl
    sdef = lib.get(LIB_ID)
    ax, ay = 0.0, 0.0

    # ---- the magjack -----------------------------------------------------------
    body = body_box_page(sdef, ax, ay, 0, "body", "T1")
    ref_pos = (body.x0 + 2.54, body.y0 - 1.27, 0)
    val_pos = (ax, body.y0 - 1.27, 0)
    part = PlacedPart("T1", LIB_ID, "HX5008NLT", ax, ay, 0, FOOTPRINT,
                      ref_pos=ref_pos, val_pos=val_pos)
    pl.parts.append(part)
    pl.boxes.append(body)
    pl.boxes.append(Box(*tm.centered_box("T1", ref_pos[0], ref_pos[1]),
                        "reference", "T1"))
    pl.boxes.append(Box(*tm.centered_box("HX5008NLT", val_pos[0], val_pos[1]),
                        "value", "T1"))
    pl.boxes.extend(place._pin_text_boxes(sdef, part))

    pins = {p.number: pin_page_position(p, ax, ay, 0) for p in sdef.pins}

    # ---- port fans: tidy aligned ranks, straight runs --------------------------
    for num, net in PHY_PORTS.items():
        px, py = pins[str(num)]
        pl.plan(net, (px, py), (px - RUN, py))
        b.label(net, px - RUN, py, 180)
    for num, net in LINE_PORTS.items():
        px, py = pins[str(num)]
        pl.plan(net, (px, py), (px + RUN, py))
        b.label(net, px + RUN, py, 0)

    # ---- Bob-Smith ladder: drop, bar, R||C, trunk taps --------------------------
    rrot = 0 if _pin(lib.get("Device:R"), "1").y > 0 else 180
    crot = 0 if _pin(lib.get("Device:C"), "1").y > 0 else 180
    trunk_nodes: list[float] = [X_RISER]
    for n in range(4):
        ct = f"CT{n}"
        x, ytip = pins[str(9 + n)]
        xc = x + BAR
        pl.plan(ct, (x, ytip), (x, Y_BAR))            # straight drop
        pl.plan(ct, (x, Y_BAR), (xc, Y_BAR))          # bar to the cap column
        pl.plan(ct, (xc, Y_BAR), (xc, Y_RB))          # cap column
        b.llabel(ct, x + 1.27, Y_BAR)                 # net name ON the bar
        b.passive(f"R{n + 1}", x, Y_R, rrot, text_side="left")
        b.passive(f"C{n + 1}", xc, Y_C, crot, text_side="right")
        pl.plan("BS_COMMON", (x, Y_RB), (x, Y_TRUNK))  # 75R tap onto the trunk
        trunk_nodes += [x, xc]
    trunk_nodes.append(X_C5)

    # the trunk: one horizontal run, split into legs at every tap (junction
    # dots appear exactly at the same-net degree>=3 taps — never elsewhere)
    for xa, xb in zip(trunk_nodes, trunk_nodes[1:]):
        pl.plan("BS_COMMON", (xa, Y_TRUNK), (xb, Y_TRUNK))
    b.llabel("BS_COMMON", X_C5, Y_TRUNK)              # name at the trunk's end

    # magjack's own BS tap (pin 13): stub out, riser down the left flank
    x13, y13 = pins["13"]
    pl.plan("BS_COMMON", (x13, y13), (X_RISER, y13), (X_RISER, Y_TRUNK))

    # shared chassis cap closes the trunk's right end
    b.passive("C5", X_C5, Y_TRUNK + 3.81, crot, text_side="right")
    b.power("CHASSIS_GND", X_C5, Y_TRUNK + 7.62)

    # shield GND stub (pin 14): out, down, GND symbol — clear of the ladder
    x14, y14 = pins["14"]
    pl.plan("GND", (x14, y14), (x14 + 3.81, y14), (x14 + 3.81, y14 + 5.08))
    b.power("GND", x14 + 3.81, y14 + 5.08)

    # ---- PWR_FLAG corner (ERC: ground nets must be driven) ----------------------
    for fx, net in zip(X_FLAGS, ("GND", "CHASSIS_GND")):
        b.power(net, fx, Y_FLAGS)
        pl.plan(net, (fx, Y_FLAGS), (fx, Y_FLAGS - 2.54))
        b.flag(net, fx, Y_FLAGS - 2.54, 0)

    return place.center_on_sheet(pl)
