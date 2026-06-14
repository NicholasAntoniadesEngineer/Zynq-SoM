"""power — carrier rail tree: +VIN(20V) -> +5V buck -> +3V3 buck -> +1V8 LDO,
plus the always-on +5V_SOM buck (P0 fix) that feeds the SoM module's VIN.

PLAN round-2 locked: USB-C PD supplies +VIN (20 V); the carrier generates
+5V (buck from VIN), +3V3 (buck from +5V) and +1V8 (LDO from +3V3). Every
rail has an EN port (driven by the bringup subsystem's DIP-AND-STM32 enable
cells, ports EN_5V0 / EN_3V3 / EN_1V8 per the bringup dossier contract) and
a power-good LED.

P0 — SoM VIN OVERVOLTAGE FIX (wave3_function_map.md, PLAN "P0 + wave-3
decisions", user-signed-off 2026-06-12). The SoM is a 4.2-5 V-input module:
its on-module regulators (TPS7A20 -> +3V3_SC, 2x MPM3834 -> +3V3/+1V8,
MPM3822 -> +1V35, TPSM82864 -> +1V0) are ALL 6 V-class, and the SoM's own
power_architecture sheet annotates the input "4.2-5V". The carrier binds
J1.1-14 (SoM net VIN) to a power rail; binding that to the 20 V PD rail
+VIN destroys the SoM at the first PD contract. RESOLUTION: a THIRD
TPS54302 buck (U4) drops +VIN -> +5V_SOM (5.0 V class), and som_conn_gen
rebinds J1 VIN -> +5V_SOM (UNIT 2). +5V_SOM is ALWAYS-ON (no bring-up
gate cell): the PD negotiation chain is FUSB302 (carrier, on +3V3_SC) +
the SoM SC (U9), and +3V3_SC is generated ON the SoM from its VIN — so if
SoM VIN waited for a DIP the SC would be dead, nobody would negotiate PD,
and 20 V would never arrive (circular). At the 5 V default-USB contract the
buck runs near 100% duty and passes ~4.7-4.8 V (inside the SoM 4.2-5 V
window); after the 20 V contract it regulates 4.96 V. This preserves the
"switches-only stage 1 with a blank SC" bring-up contract: +5V_SOM behaves
exactly like +3V3_SC — alive pre-DIP by design. EN is strapped on via a
SERIES-R + ZENER CLAMP (NO EN port); see the EN clamp section below.

PWR-1 FIX — U4 EN OVER-STRESS (deep-audit 2026-06-12, LIVE TI SLVSDG6C).
The earlier always-on strap was a plain R12/R13 = 22k/10k divider from
+VIN; at the 20 V (21 V at +5%) PD contract that presents 21 x 10/32 =
6.56 V on the TPS54302 EN. The datasheet recommended-max EN is 5.5 V and
absolute-max 7 V, and — verified against the LIVE SLVSDG6C — there is NO
internal EN clamp: EN has only a 1.55 uA hysteresis current source, so the
old "internal EN clamp holds the divider voltage" claim was FALSE and is
removed. A plain re-ratio cannot fix it: turn-on at the 4.75 V default
contract wants a HIGH bottom/top ratio, but <= 5.5 V at 21 V wants a LOW
ratio — mutually exclusive. RESOLUTION (clamp, this file's stage 4):
  R12 = 10k SERIES from +VIN -> EN ; D5 = MMSZ5231B 5.1 V zener EN -> GND ;
  C20 = 100 nF EN bypass to GND.
At low VIN the zener is off and the 1.55 uA I_hys through 10k drops < 16 uV,
so EN ~= VIN -> sure enable (threshold 1.21 V typ, <= ~1.3 V worst). At
high VIN the zener clamps EN to ~Vz, R12 absorbing (VIN - Vz). EN stays
inside [enable-threshold + margin, 5.5 V] across the whole 4.75-21 V range.

EN voltage table (worst case over Vz = 4.845/5.1/5.355 V at Izt=20 mA,
Zzt 17 ohm, I_hys 1.55 uA, R12 10k 1%; SLVSDG6C + MMSZ5231B datasheet):
  VIN = 4.75 V (5V contract low) : EN ~= 4.50 .. 4.73 V  (>> 1.3 V -> ON)
  VIN = 5.00 V (5V contract nom) : EN ~= 4.51 .. 4.98 V
  VIN = 21.0 V (20V + 5%)        : EN ~= 4.53 .. 5.04 V  (<= 5.5 V, margin
                                    ~0.46 V; zener I 1.6 mA -> 8 mW << the
                                    MMSZ5231B 500 mW rating).
The schgen spice/analytic gate (schgen/spice.py, "EN clamp") re-derives
this table from the netlist and FAILS if EN ever leaves [1.5 V, 5.5 V]
across VIN 4.75-21 V — so PWR-1 can never silently regress.

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
- FB dividers: +5V = 73.2k/10k -> 4.96 V (C14890 Ext + C25804 Basic);
  +3V3 = 100k/22k -> 3.30 V (C25803 + C31850, both Basic);
  +5V_SOM = 68.1k/10k -> 4.65 V nom (PWR-5; C844583 Vishay 0603 1%, LIVE
  2026-06-13: Ext, stock 10,869, min-qty 1 + C25804). PWR-5 RE-CENTER: the
  old 73.2k/10k gave 4.96 V nom / ~5.17 V worst-case-high, poking above the
  SoM's 5.0 V input rec-max; 68.1k/10k re-centers to 4.65 V nom, WC-hi
  ~4.81 V (1% R + 1% Vref) so the WHOLE band stays inside the SoM 4.2-5.0 V
  window with the EN zener clamp (PWR-1) untouched.
- FB feedforward caps (PWR-4, TI all-ceramic-output reference): 75 pF C0G
  ACROSS each buck's FB TOP resistor — C22 (U1 R1), C23 (U2 R4), C21 (U4
  R14) — to add phase boost / improve transient response on the internally
  compensated TPS54302 with low-ESR ceramic output caps. Part: CGA0603-
  C0G750J500JT, TDK 0603 C0G 50 V (LCSC C22399620, LIVE 2026-06-13: Ext,
  stock 8,020, min-qty 1).
- +5V_SOM EN clamp (always-on strap, NO bring-up port; PWR-1 FIX — see the
  header "EN voltage table"): R12 = 10k SERIES from +VIN to EN (C25804,
  reused 10k); D5 = MMSZ5231B 5.1 V / 500 mW zener EN -> GND (LIVE-verified
  on the JLC parts API 2026-06-13: C85181, Diodes Inc, SOD-123, stock
  180,887, Extended, min-qty 1, $0.0162 @ qty 1 — the canonical 5.1 V
  zener; alternates same query: C2117 BZT52C5V1 Jiangsu Changjin 92,425,
  C66198 MMSZ5231BT1G onsemi 81,989); C20 = 100 nF EN bypass to GND (C1591,
  reused). No JLC Basic 5.1 V zener exists (all 5.1 V zeners are Extended);
  C85181's 180 k stock + min-qty 1 makes it the lowest-risk pick. Replaces
  the old over-stressing 22k/10k divider (the FALSE "internal EN clamp"
  claim is gone). EN clamped to ~5.0 V worst-case at 21 V (<= 5.5 V).
- PG LEDs (bringup dossier section 3.3): KT-0603R red (C2286 Basic) + 1k
  (C21190) on +5V, + 330R (C23138) on +3V3. +1V8 cannot light a red LED
  (Vf ~2.0 V > rail), so an AO3400A (C20917 Basic, Vgs(th) <= 1.45 V max)
  senses the rail (1k gate-stop + 100k pulldown) and sinks a 330R+LED chain
  from +3V3 — which is necessarily up before +1V8 exists. PWR-6: the gate
  series was 10k, which with the 100k pulldown only presented +1V8 *
  100/110 = 1.64 V on Vgs — barely above the 1.45 V max Vth, no guaranteed
  turn-on. Dropping it to 1k (a pure RC gate-stop now, not a divider) lets
  Vgs see +1V8 * 100/101 = 1.78 V, a solid margin over Vth-max.
- Input caps: 2x 10u/1206 (C13585) + 100n (C1591) on +VIN; 22u/0805
  (C45783) + 100n on the +5V input of the second buck; outputs 2x 22u each;
  LDO 1u in / 1u out (C15849). All Basic except C1591 (reclassified
  Extended per today's API — kept: 50 V rating covers the 20 V input).

Pin maps cross-checked: parts/<MPN>/<MPN>.py (EasyEDA) == KiCad stock
symbols used here (TPS54302: 1 GND 2 SW 3 VIN 4 FB 5 EN 6 BOOT;
Q_NMOS_GSD == AO3400A SOT-23 1 G 2 S 3 D).
"""

from __future__ import annotations

from schgen.core.model import Circuit

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
DZ_FP = "Diode_SMD:D_SOD-123"              # MMSZ5231B 5.1 V EN-clamp zener
L_FP = "SWPA8040S100MT:SWPA8040S100MT"     # faithful EasyEDA footprint (parts/)

EXPECT_BRINGUP = "bringup (wave 2 rail-enable cells, dossier section 3.1)"


def circuit() -> Circuit:
    c = Circuit("power", "Power: +VIN->+5V->+3V3 bucks + +1V8 LDO, PG LEDs")

    # ---- stage 1: +VIN (20 V) -> +5V buck (LMR33630, HSOIC-8 PowerPAD, SYNC) -
    # U1 was the bare TSOT-23-6 TPS54302 (no thermal pad) — the board's hottest
    # converter. RESELECTED to the LMR33630ADDAR (LCSC C841384): a TI SIMPLE
    # SWITCHER, SYNCHRONOUS + internally compensated, 3.8-36 V / 3 A, in the DDA
    # HSOIC-8 PowerPAD package — a REAL datasheet-dimensioned exposed pad (pad 9)
    # for the heat path. Uses the KiCad STOCK symbol Regulator_Switching:
    # LMR33640ADDA (same DDA pinout — the 4 A sibling drawing — with proper
    # power_in VIN so the placer's regulator template fits) + the faithful
    # EP-bearing footprint: exactly the TPS54302/AP2112K stock-symbol idiom.
    # Pins: 1 GND  2 VIN  3 EN  4 PG  5 FB  6 VCC  7 BOOT  8 SW  9 EP(GND).
    # VFB 1.0 V -> 40.2k/10k FB divider = 5.02 V. EP (pad 9) bonds to GND.
    c.use_part("LMR33630ADDAR", ref="U1",
               lib_id="Regulator_Switching:LMR33640ADDA",
               footprint="LMR33630ADDAR:LMR33630ADDAR")
    # DEF-D: U1 input is the POST-shunt rail +VIN_SYS (RS1 series-inserts
    # between the eFuse +VIN and the buck inputs in power_mon.py), so the buck
    # input current — including the input-cap ripple/inrush — flows through RS1
    # and is counted on the U1 ch1 (+VIN) channel. The input caps move with it.
    c.net("+VIN_SYS", "U1.2")                                      # VIN (pin 2), post-RS1
    c.net("GND", "U1.1", "U1.9")                                   # GND (1) + EP PowerPAD (9)
    c.port("EN_5V0", "U1.3", expect=EXPECT_BRINGUP)                # EN (pin 3)
    c.nc("U1.4")                                                   # PG open-collector unused
    for ref, val, fp, lcsc in (("C1", "100n", C0603, "C1591"),
                               ("C2", "10u", C1206, "C13585"),
                               ("C3", "10u", C1206, "C13585")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN_SYS", f"{ref}.1")                              # buck-input filter, post-RS1
        c.net("GND", f"{ref}.2")
    c.part("C24", "Device:C", "1u", C0603, LCSC="C15849")          # VCC int-LDO bypass
    c.net("U1_VCC", "U1.6", "C24.1")                               # VCC (pin 6), local bias
    c.net("GND", "C24.2")
    c.part("C4", "Device:C", "100n", C0603, LCSC="C1591")          # BOOT cap
    c.net("BOOT_5V0", "U1.7", "C4.1")                              # BOOT (pin 7)
    c.part("L1", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_5V0", "U1.8", "C4.2", "L1.1")                        # SW (pin 8)
    # DEF-D: buck-1 OUTPUT cluster is +5V_REG (reg-side of RS2). The inductor
    # node, output bulk caps, FB sense and the PG LED stay on the regulator
    # side; the board +5V rail (post-RS2) carries the measured consumers (U2
    # input, C7/C8). RS2 bridges +5V_REG -> +5V so consumer draw is measured.
    c.net("+5V_REG", "L1.2")
    for ref in ("C5", "C6"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+5V_REG", f"{ref}.1")                              # output bulk, reg-side
        c.net("GND", f"{ref}.2")
    c.part("R1", "Device:R", "40.2k", R_FP, LCSC="C25750")         # FB top (VFB 1.0 -> 5.02 V)
    c.part("R2", "Device:R", "10k", R_FP, LCSC="C25804")           # FB bottom
    c.net("+5V_REG", "R1.1")                                       # FB senses the regulated node
    c.net("FB_5V0", "U1.5", "R1.2", "R2.1")                        # FB (pin 5)
    c.net("GND", "R2.2")
    # (no FB feedforward cap on U1: keep FB a clean 2-element divider the router
    #  handles; the LMR33630 is internally compensated, so it is optional.)
    c.part("D1", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +5V indicator
    c.part("R3", "Device:R", "1k", R_FP, LCSC="C21190")
    c.net("+5V_REG", "D1.2")                                       # PG LED reg-side (regulator up)
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
    # DEF-D: buck-2 OUTPUT cluster is +3V3_REG (reg-side of RS3). U2's INPUT
    # stays the board +5V (above) — it is a +5V consumer, measured by RS2.
    c.net("+3V3_REG", "L2.2")
    for ref in ("C10", "C11"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+3V3_REG", f"{ref}.1")                            # output bulk, reg-side
        c.net("GND", f"{ref}.2")
    c.part("R4", "Device:R", "100k", R_FP, LCSC="C25803")          # FB top
    c.part("R5", "Device:R", "22k", R_FP, LCSC="C31850")           # FB bottom
    c.part("C23", "Device:C", "75p", C0603, LCSC="C22399620")      # FB feedfwd
    c.net("+3V3_REG", "R4.1", "C23.1")                            # FB + feedfwd reg-side
    c.net("FB_3V3", "U2.4", "R4.2", "R5.1", "C23.2")
    c.net("GND", "R5.2")
    c.part("D2", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +3V3
    c.part("R6", "Device:R", "330R", R_FP, LCSC="C23138")
    c.net("+3V3_REG", "D2.2")                                     # PG LED reg-side
    c.net("PG_3V3", "D2.1", "R6.1")
    c.net("GND", "R6.2")

    # ---- stage 3: +3V3 -> +1V8 LDO -------------------------------------------
    c.use_part("AP2112K-1.8TRG1", ref="U3", value="AP2112K-1.8",
               lib_id=LDO_LIB, footprint=LDO_FP)
    c.net("+3V3", "U3.1")                                          # LDO input: board +3V3 (RS3)
    c.net("GND", "U3.2")
    c.port("EN_1V8", "U3.3", expect=EXPECT_BRINGUP)
    c.nc("U3.4")                                                   # NC pin
    # DEF-D: LDO OUTPUT is +1V8_REG (reg-side of RS4). The LDO INPUT cap C12
    # stays on the board +3V3 (it is a +3V3 consumer, measured by RS3); only
    # the output node + output cap move to +1V8_REG. RS4 bridges +1V8_REG ->
    # the board +1V8 the loads see.
    c.net("+1V8_REG", "U3.5")
    c.part("C12", "Device:C", "1u", C0603, LCSC="C15849")          # LDO in
    c.net("+3V3", "C12.1")
    c.net("GND", "C12.2")
    c.part("C13", "Device:C", "1u", C0603, LCSC="C15849")          # LDO out
    c.net("+1V8_REG", "C13.1")                                     # output cap reg-side
    c.net("GND", "C13.2")

    # ---- +1V8 PG sense cell (dossier 3.3: red Vf > 1.8 V -> FET sense) -------
    c.part("R7", "Device:R", "1k", R_FP, LCSC="C21190")            # gate-stop
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

    # ---- stage 4: +VIN -> +5V_SOM always-on buck -> SPLIT to power_som.py ----
    # The +5V_SOM buck (U4) + its EN zener clamp moved to its own sheet
    # (power_som.py, 2026-06-14): U1's reselect to the larger LMR33630 pushed the
    # 4-converter sheet past A3, and the +5V_SOM stage is the cleanly-separable
    # unit (only +VIN / +5V_SOM / GND rails cross). See power_som.py.

    # ---- test points (round 4 coverage gate): the generated rails +
    # a ground probe return, at their source sheet ----------------------------
    for net in ("+5V", "+3V3", "+1V8", "GND"):    # +5V_SOM TP on power_som.py
        c.testpoint(net)

    # ---- power-tree budget declarations (round 4 gate) ----------------------
    c.draws("+5V", 0.004, "PG LED (KT-0603R + 1k, ~3 mA) + FB divider 60 uA")
    # (+5V_SOM draw is declared on power_som.py — its source sheet now.)
    c.draws("+3V3", 0.009, "PG LED (330R ~3.9 mA) + 1V8 PG sense LED chain "
                           "(330R ~3.9 mA) + FB divider 27 uA")
    c.draws("+1V8", 0.001, "PG FET gate divider 10k+100k (16 uA), rounded up")
    # THERMAL WAIVERS (verification P2) — see carrier/research/thermal_bucks.md.
    # The TPS54302 is SOT-23-6 (DDC) with NO exposed pad; the thermal gate's
    # bare-package 2s2p RthJA (70.6 C/W) + 0.85 eff floor put Tj over the 140 C
    # guard at the worst-case rail loads (U1 +5V hottest). These three bucks are
    # LAYOUT-CRITICAL: a power-optimised 4-layer layout (large SW/VIN/PGND copper
    # pours + a thermal-via field) plus the part's real ~88-91% efficiency at
    # these points brings the effective RthJA to ~45-55 C/W and Tj under limit.
    # REVIEW-FLAGGED: confirm by thermal sim / bench Tj at bring-up; if the
    # layout cannot hit the target RthJA, switch to an exposed-pad buck.
    _TH = ("TPS54302 SOT-23-6, no EP: bare 2s2p RthJA 70.6 C/W overstates Tj; "
           "layout-critical (power copper pour + thermal vias -> ~45-55 C/W) — "
           "VERIFY by thermal sim/bench at bring-up else move to an EP buck "
           "(see carrier/research/thermal_bucks.md)")
    c.waive_thermal("U2", _TH)
    # U1 LMR33630ADDA: the gate now COMPUTES Tj (bare-JEDEC RthJA 41 C/W at
    # 2.95 A @ 5 V puts Tj over the guard band) instead of silently skipping the
    # board's hottest converter. The real EP->GND pour + thermal-via field
    # drives effective RthJA well below the bare 41 C/W — VERIFY at bring-up.
    _TH_U1 = ("LMR33630ADDA HSOIC-8 PowerPAD: bare-JEDEC RthJA 41 C/W overstates "
              "Tj; the EP->GND pour + thermal-via field is layout-critical "
              "(target effective RthJA <= ~25 C/W to clear the guard band at "
              "eff 0.90) — VERIFY by thermal sim/bench Tj at bring-up "
              "(carrier/research/thermal_bucks.md)")
    c.waive_thermal("U1", _TH_U1)
    return c                     # U4 +5V_SOM waiver lives on power_som.py
