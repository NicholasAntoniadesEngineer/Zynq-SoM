"""power — carrier rail tree: +VIN(20V) -> +5V buck -> +3V3 buck -> +1V8 LDO.

PLAN round-2 locked: USB-C PD supplies +VIN (20 V); the carrier generates
+5V (buck from VIN), +3V3 (buck from +5V) and +1V8 (LDO from +3V3). Every
rail has an EN port (driven by the bringup subsystem's DIP-AND-STM32 enable
cells, ports EN_5V0 / EN_3V3 / EN_1V8 per the bringup dossier contract) and
a power-good LED.

Parts (ALL live-verified on JLCPCB 2026-06-10, stock figures that day):
- 2x TPS54302DDCR (LCSC C311983, stock 33,368, Extended): TI 4.5-28 V, 3 A
  SYNCHRONOUS buck, internally compensated, TSOT-23-6 — the TPS54331-class
  part the plan names, minus the catch diode + external compensation (the
  20 V PD input rules out the 24 V-max MP2315S; verified C3031493 had only
  2,163 in stock anyway). EN VIH 1.21 V typ -> driven rail-to-rail by the
  bringup cell's 3.3 V CMOS gate output. Datasheet ref circuit: 100n BOOT
  cap, 10 uH inductor, FB divider to VREF = 0.596 V.
- 2x SWPA8040S100MT (C37429, 9,267, Ext): Sunlord 10 uH / Isat ~4 A shielded
  power inductor. 5 V stage ripple 0.94 A p-p (Ipk 3.5 A < Isat); 3V3 stage
  0.28 A p-p.
- AP2112K-1.8TRG1 (C176944, 4,385, Ext): 600 mA LDO with EN, SOT-23-5,
  Vdrop 250 mV @ 600 mA from +3V3 (the dossier's +1V8 budget is SD level
  translator + 1.8 V peripherals, well under 600 mA). Symbol: the KiCad
  AP2112K-* drawings all derive from Regulator_Linear:AP2204K-1.5
  (identical SOT-23-5 pin map 1=VIN 2=GND 3=EN 4=NC 5=VOUT, confirmed
  against the EasyEDA pin table in parts/AP2112K-1.8TRG1/part.py).
- FB dividers: +5V = 73.2k/10k -> 4.96 V (C14890 Ext 28,920 + C25804 Basic);
  +3V3 = 100k/22k -> 3.30 V (C25803 + C31850, both Basic).
- PG LEDs (bringup dossier section 3.3): KT-0603R red (C2286 Basic) + 1k
  (C21190) on +5V, + 330R (C23138) on +3V3. +1V8 cannot light a red LED
  (Vf ~2.0 V > rail), so an AO3400A (C20917 Basic, Vgs(th) <= 1.45 V max)
  senses the rail (10k gate series + 100k pulldown) and sinks a 330R+LED
  chain from +3V3 — which is necessarily up before +1V8 exists.
- Input caps: 2x 10u/1206 (C13585) + 100n (C1591) on +VIN; 22u/0805
  (C45783) + 100n on the +5V input of the second buck; outputs 2x 22u each;
  LDO 1u in / 1u out (C15849). All Basic except C1591 (reclassified
  Extended per today's API — kept: 50 V rating covers the 20 V input).

Pin maps cross-checked: parts/<MPN>/part.py (EasyEDA) == KiCad stock
symbols used here (TPS54302: 1 GND 2 SW 3 VIN 4 FB 5 EN 6 BOOT;
Q_NMOS_GSD == AO3400A SOT-23 1 G 2 S 3 D).
"""

from __future__ import annotations

from schgen import place
from schgen import textmetrics as tm
from schgen.emit import PlacedPart
from schgen.model import Circuit
from schgen.place import Placement, Spacing, _Builder, _pin, body_box_page
from schgen.symbols import Library, pin_page_position
from schgen.verify.visual_gate import Box

BUCK_LIB = "Regulator_Switching:TPS54302"
BUCK_FP = "Package_TO_SOT_SMD:TSOT-23-6"
LDO_LIB = "Regulator_Linear:AP2204K-1.5"   # = AP2112K drawing (see docstring)
LDO_FP = "Package_TO_SOT_SMD:SOT-23-5"
FET_LIB = "Transistor_FET:Q_NMOS_GSD"
FET_FP = "Package_TO_SOT_SMD:SOT-23"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"
L_FP = "SWPA8040S100MT:SWPA8040S100MT"     # faithful EasyEDA footprint (parts/)

EXPECT_BRINGUP = "bringup (wave 2 rail-enable cells, dossier section 3.1)"


def circuit() -> Circuit:
    c = Circuit("power", "Power: +VIN->+5V->+3V3 bucks + +1V8 LDO, PG LEDs")

    # ---- stage 1: +VIN (20 V) -> +5V buck -----------------------------------
    c.part("U1", BUCK_LIB, "TPS54302DDCR", BUCK_FP, LCSC="C311983")
    c.net("+VIN", "U1.3")
    c.net("GND", "U1.1")
    c.port("EN_5V0", "U1.5", expect=EXPECT_BRINGUP)
    for ref, val, fp, lcsc in (("C1", "100n", C0603, "C1591"),
                               ("C2", "10u", C1206, "C13585"),
                               ("C3", "10u", C1206, "C13585")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("C4", "Device:C", "100n", C0603, LCSC="C1591")          # BOOT
    c.net("BOOT_5V0", "U1.6", "C4.1")
    c.part("L1", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_5V0", "U1.2", "C4.2", "L1.1")
    c.net("+5V", "L1.2")
    for ref in ("C5", "C6"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+5V", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("R1", "Device:R", "73.2k", R_FP, LCSC="C14890")         # FB top
    c.part("R2", "Device:R", "10k", R_FP, LCSC="C25804")           # FB bottom
    c.net("+5V", "R1.1")
    c.net("FB_5V0", "U1.4", "R1.2", "R2.1")
    c.net("GND", "R2.2")
    c.part("D1", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +5V
    c.part("R3", "Device:R", "1k", R_FP, LCSC="C21190")
    c.net("+5V", "D1.2")
    c.net("PG_5V0", "D1.1", "R3.1")
    c.net("GND", "R3.2")

    # ---- stage 2: +5V -> +3V3 buck ------------------------------------------
    c.part("U2", BUCK_LIB, "TPS54302DDCR", BUCK_FP, LCSC="C311983")
    c.net("+5V", "U2.3")
    c.net("GND", "U2.1")
    c.port("EN_3V3", "U2.5", expect=EXPECT_BRINGUP)
    for ref, val, fp, lcsc in (("C7", "100n", C0603, "C1591"),
                               ("C8", "22u", C0805, "C45783")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+5V", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("C9", "Device:C", "100n", C0603, LCSC="C1591")          # BOOT
    c.net("BOOT_3V3", "U2.6", "C9.1")
    c.part("L2", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_3V3", "U2.2", "C9.2", "L2.1")
    c.net("+3V3", "L2.2")
    for ref in ("C10", "C11"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+3V3", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("R4", "Device:R", "100k", R_FP, LCSC="C25803")          # FB top
    c.part("R5", "Device:R", "22k", R_FP, LCSC="C31850")           # FB bottom
    c.net("+3V3", "R4.1")
    c.net("FB_3V3", "U2.4", "R4.2", "R5.1")
    c.net("GND", "R5.2")
    c.part("D2", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +3V3
    c.part("R6", "Device:R", "330R", R_FP, LCSC="C23138")
    c.net("+3V3", "D2.2")
    c.net("PG_3V3", "D2.1", "R6.1")
    c.net("GND", "R6.2")

    # ---- stage 3: +3V3 -> +1V8 LDO -------------------------------------------
    c.part("U3", LDO_LIB, "AP2112K-1.8", LDO_FP, LCSC="C176944")
    c.net("+3V3", "U3.1")
    c.net("GND", "U3.2")
    c.port("EN_1V8", "U3.3", expect=EXPECT_BRINGUP)
    c.nc("U3.4")                                                   # NC pin
    c.net("+1V8", "U3.5")
    c.part("C12", "Device:C", "1u", C0603, LCSC="C15849")          # LDO in
    c.net("+3V3", "C12.1")
    c.net("GND", "C12.2")
    c.part("C13", "Device:C", "1u", C0603, LCSC="C15849")          # LDO out
    c.net("+1V8", "C13.1")
    c.net("GND", "C13.2")

    # ---- +1V8 PG sense cell (dossier 3.3: red Vf > 1.8 V -> FET sense) -------
    c.part("R7", "Device:R", "10k", R_FP, LCSC="C25804")           # gate series
    c.part("R8", "Device:R", "100k", R_FP, LCSC="C25803")          # gate pulldown
    c.part("Q1", FET_LIB, "AO3400A", FET_FP, LCSC="C20917")
    c.net("+1V8", "R7.1")
    c.net("PG_1V8_G", "R7.2", "R8.1", "Q1.1")
    c.net("GND", "R8.2", "Q1.2")
    c.part("R9", "Device:R", "330R", R_FP, LCSC="C23138")
    c.part("D3", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +1V8
    c.net("PG_1V8_D", "Q1.3", "R9.2")
    c.net("PG_1V8_K", "R9.1", "D3.1")
    c.net("+3V3", "D3.2")
    return c


# ---- datasheet template: three regulator rows + PWR_FLAG corner ---------------
#
#  +VIN sym                 BOOT cap            +5V sym
#     |    EN_5V0 >--EN [   U1   ] SW--o--L1--o---o---o---o--'
#   |Cin|Cin|Cin|        GND  FB-.     |      |Cout|  Rt  LEDpg
#   GND GND GND               |  '-----+------+----+--o<--.
#  (same row again for U2; LDO row + AO3400A PG cell; flags bottom-left)
#
# All geometry symbol-anchored (U at x=0), 1.27 grid; every line split into
# legs at its taps; junction dots only where the SAME net taps (LAW 0).

Y_PITCH = 43.18                  # buck row pitch
Y_LDO = 90.17                    # LDO row anchor
Y_FLAGS = 115.57                 # PWR_FLAG corner row
X_EN = -17.78                    # EN hier-label anchor
X_CIN = (-38.10, -48.26, -58.42)  # input-cap columns (outermost gets the rail)
X_BOOTV = 12.70                  # BOOT riser column
Y_BOOT = -7.62                   # BOOT cap row (relative to U anchor)
X_CB = 20.32                     # BOOT cap anchor (pins 16.51 / 24.13)
X_SWJ = 30.48                    # BOOT-cap drop onto the SW run
X_L = 36.83                      # inductor anchor (pins 33.02 / 40.64)
X_COUT = (48.26, 58.42)          # output-cap columns
X_DIV = 68.58                    # FB divider column
X_LED = 78.74                    # PG LED column
X_RAIL = 83.82                   # output-rail riser
Y_FB = 12.70                     # FB sense row (relative to U anchor)


def _ic(b: _Builder, lib: Library, ref: str, ax: float, ay: float) -> dict:
    """Place a multi-pin part at (ax, ay): body+texts boxed, pins returned."""
    part = b.c.parts[ref]
    sdef = lib.get(part.lib_id)
    body = body_box_page(sdef, ax, ay, 0, "body", ref)
    w_ref, _ = tm.text_wh(ref)
    w_val, _ = tm.text_wh(part.value)
    rp = (body.x0 + w_ref / 2, body.y0 - 1.905, 0)
    vp = (11.43 + ax - w_val / 2, body.y0 - 1.905, 0)
    pp = PlacedPart(ref, part.lib_id, part.value, ax, ay, 0, part.footprint,
                    ref_pos=rp, val_pos=vp)
    b.pl.parts.append(pp)
    b.pl.boxes.append(body)
    b.pl.boxes.append(Box(*tm.centered_box(ref, rp[0], rp[1]), "reference", ref))
    b.pl.boxes.append(Box(*tm.centered_box(part.value, vp[0], vp[1]),
                          "value", ref))
    b.pl.boxes.extend(place._pin_text_boxes(sdef, pp))
    return {p.number: pin_page_position(p, ax, ay, 0) for p in sdef.pins}


def _vcap(b: _Builder, lib: Library, ref: str, x: float, y_top: float) -> None:
    """Vertical 2-pin shunt: pin1 at (x, y_top), pin2 -> GND symbol below."""
    sdef = lib.get(b.c.parts[ref].lib_id)
    rot = 0 if _pin(sdef, "1").y > 0 else 180
    b.passive(ref, x, y_top + 3.81, rot, text_side="right")
    b.power("GND", x, y_top + 7.62)


def _rail_run(b: _Builder, net: str, y: float, nodes: list[float],
              rail_x: float, rail_y: float) -> None:
    """Split a horizontal run into legs at every tap; riser to a rail symbol."""
    for xa, xb in zip(nodes, nodes[1:]):
        b.pl.plan(net, (xa, y), (xb, y))
    b.pl.plan(net, (rail_x, y), (rail_x, rail_y))
    b.power(net, rail_x, rail_y)


def _buck(b: _Builder, lib: Library, ay: float, u: str, rail_in: str,
          rail_out: str, en: str, cin: tuple[str, ...], cb: str, l: str,
          cout: tuple[str, str], rt: str, rb: str, led: str, rled: str,
          sw: str, fb: str) -> None:
    pins = _ic(b, lib, u, 0.0, ay)
    p_vin, p_en, p_gnd = pins["3"], pins["5"], pins["1"]
    p_boot, p_sw, p_fb = pins["6"], pins["2"], pins["4"]

    # left: EN port + input rail with its cap bank
    b.pl.plan(en, p_en, (X_EN, p_en[1]))
    b.label(en, X_EN, p_en[1], 180, shape="input")
    cols = list(X_CIN[:len(cin)])
    _rail_run(b, rail_in, p_vin[1], [p_vin[0]] + cols,
              cols[-1], p_vin[1] - 5.08)
    for ref, x in zip(cin, cols):
        _vcap(b, lib, ref, x, p_vin[1])
    b.power("GND", *p_gnd)

    # right: BOOT cap over the SW run, inductor, output rail
    crot = 90 if _pin(lib.get("Device:C"), "1").y > 0 else 270
    b.pl.plan("BOOT" + sw[2:], p_boot, (X_BOOTV, p_boot[1]),
              (X_BOOTV, ay + Y_BOOT), (X_CB - 3.81, ay + Y_BOOT))
    b.passive(cb, X_CB, ay + Y_BOOT, crot, text_side="right")
    b.pl.plan(sw, (X_CB + 3.81, ay + Y_BOOT), (X_SWJ, ay + Y_BOOT),
              (X_SWJ, ay))
    b.pl.plan(sw, p_sw, (X_SWJ, ay))
    b.pl.plan(sw, (X_SWJ, ay), (X_L - 3.81, ay))
    lrot = 90 if _pin(lib.get("Device:L"), "1").y > 0 else 270
    b.passive(l, X_L, ay, lrot, text_side="right")
    _rail_run(b, rail_out, ay,
              [X_L + 3.81, X_COUT[0], X_COUT[1], X_DIV, X_LED, X_RAIL],
              X_RAIL, ay - 5.08)
    for ref, x in zip(cout, X_COUT):
        _vcap(b, lib, ref, x, ay)

    # FB divider: tap drops from the rail, sense row returns to the FB pin
    b.pl.plan(rail_out, (X_DIV, ay), (X_DIV, ay + 5.08))
    rrot = 0 if _pin(lib.get("Device:R"), "1").y > 0 else 180
    b.passive(rt, X_DIV, ay + 8.89, rrot, text_side="right")
    b.passive(rb, X_DIV, ay + 16.51, rrot, text_side="right")
    b.power("GND", X_DIV, ay + 20.32)
    b.pl.plan(fb, p_fb, (X_BOOTV, p_fb[1]), (X_BOOTV, ay + Y_FB),
              (X_DIV, ay + Y_FB))

    # PG LED column: rail -> LED(A->K) -> R -> GND
    ledrot = 90  # Device:LED pin1=K at (-3.81,0): rot 90 puts A top, K bottom
    b.passive(led, X_LED, ay + 3.81, ledrot, text_side="right")
    b.passive(rled, X_LED, ay + 11.43, rrot, text_side="right")
    b.power("GND", X_LED, ay + 15.24)


def placer(c: Circuit, lib: Library, sp: Spacing) -> Placement:
    b = _Builder(c, lib, sp)

    _buck(b, lib, 0.0, "U1", "+VIN", "+5V", "EN_5V0",
          ("C1", "C2", "C3"), "C4", "L1", ("C5", "C6"), "R1", "R2",
          "D1", "R3", "SW_5V0", "FB_5V0")
    _buck(b, lib, Y_PITCH, "U2", "+5V", "+3V3", "EN_3V3",
          ("C7", "C8"), "C9", "L2", ("C10", "C11"), "R4", "R5",
          "D2", "R6", "SW_3V3", "FB_3V3")

    # ---- LDO row -------------------------------------------------------------
    ay = Y_LDO
    pins = _ic(b, lib, "U3", 0.0, ay)
    p_vin, p_en, p_gnd, p_out = pins["1"], pins["3"], pins["2"], pins["5"]
    b.pl.plan("EN_1V8", p_en, (X_EN, p_en[1]))
    b.label("EN_1V8", X_EN, p_en[1], 180, shape="input")
    _rail_run(b, "+3V3", p_vin[1], [p_vin[0], X_CIN[0]],
              X_CIN[0], p_vin[1] - 5.08)
    _vcap(b, lib, "C12", X_CIN[0], p_vin[1])
    b.power("GND", *p_gnd)

    # +1V8 output run: out cap, rail symbol, PG-cell gate divider tap
    y_r = p_out[1]
    _rail_run(b, "+1V8", y_r, [p_out[0], 17.78, 25.40, 38.10], 25.40,
              y_r - 5.08)
    _vcap(b, lib, "C13", 17.78, y_r)

    # PG sense cell: 10k from the rail, 100k pulldown, AO3400A sinks the LED
    rrot = 0 if _pin(lib.get("Device:R"), "1").y > 0 else 180
    y_g = ay + 5.08
    b.passive("R7", 38.10, y_r + 3.81, rrot, text_side="right")
    b.passive("R8", 38.10, y_g + 3.81, rrot, text_side="right")
    b.power("GND", 38.10, y_g + 7.62)
    qpins = _ic(b, lib, "Q1", 50.80, y_g)
    b.pl.plan("PG_1V8_G", (38.10, y_g), qpins["1"])
    b.power("GND", *qpins["2"])
    b.passive("R9", 53.34, y_g - 8.89, rrot, text_side="right")
    b.passive("D3", 53.34, y_g - 16.51, 90, text_side="right")
    b.power("+3V3", 53.34, y_g - 20.32)

    # ---- PWR_FLAG corner (ERC: rails with only-passive pins must be driven;
    # +1V8 needs NO flag — U3's VOUT power_out pin is its real driver) ---------
    fx = -53.34
    for net in ("GND", "+VIN", "+5V", "+3V3"):
        if net == "GND":
            b.power(net, fx, Y_FLAGS)
            b.pl.plan(net, (fx, Y_FLAGS), (fx, Y_FLAGS - 2.54))
            b.flag(net, fx, Y_FLAGS - 2.54, 0)
        else:
            b.power(net, fx, Y_FLAGS)
            b.pl.plan(net, (fx, Y_FLAGS), (fx, Y_FLAGS + 2.54))
            b.flag(net, fx, Y_FLAGS + 2.54, 180)
        fx += 12.70

    return place.center_on_sheet(b.pl)
