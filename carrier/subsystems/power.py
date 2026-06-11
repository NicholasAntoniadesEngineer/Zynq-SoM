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
  against the EasyEDA pin table in parts/AP2112K-1.8TRG1/AP2112K-1.8TRG1.py).
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

Pin maps cross-checked: parts/<MPN>/<MPN>.py (EasyEDA) == KiCad stock
symbols used here (TPS54302: 1 GND 2 SW 3 VIN 4 FB 5 EN 6 BOOT;
Q_NMOS_GSD == AO3400A SOT-23 1 G 2 S 3 D).
"""

from __future__ import annotations

from schgen.model import Circuit

# DELIBERATE symbol+footprint overrides (use_part lib_id=/footprint=): the
# stock KiCad regulator/FET drawings stay (pin maps cross-checked above);
# MPN/LCSC/datasheet come from parts/TPS54302DDCR/, parts/AP2112K-1.8TRG1/,
# parts/AO3400A/ and can never drift from the library folders.
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
    c.use_part("TPS54302DDCR", ref="U1", lib_id=BUCK_LIB, footprint=BUCK_FP)
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
    c.use_part("TPS54302DDCR", ref="U2", lib_id=BUCK_LIB, footprint=BUCK_FP)
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
    c.use_part("AP2112K-1.8TRG1", ref="U3", value="AP2112K-1.8",
               lib_id=LDO_LIB, footprint=LDO_FP)
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
    c.use_part("AO3400A", ref="Q1", lib_id=FET_LIB, footprint=FET_FP)
    c.net("+1V8", "R7.1")
    c.net("PG_1V8_G", "R7.2", "R8.1", "Q1.1")
    c.net("GND", "R8.2", "Q1.2")
    c.part("R9", "Device:R", "330R", R_FP, LCSC="C23138")
    c.part("D3", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +1V8
    c.net("PG_1V8_D", "Q1.3", "R9.2")
    c.net("PG_1V8_K", "R9.1", "D3.1")
    c.net("+3V3", "D3.2")
    return c
