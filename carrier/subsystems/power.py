"""power — carrier rail tree: +VIN(20V) -> +5V buck -> +3V3 buck -> +1V8 LDO,
plus the always-on +5V_SOM buck (P0 fix) that feeds the SoM module's VIN.

WT/BUCK RE-SPEC (2026-06-14): the +5V buck U1 — the board's heaviest converter
(2.95 A @ 5 V) — was the LMR33630ADDA (3 A), running at 98% of rating with no
headroom and a Tj over the gate guard band (waived). U1 is RE-SPEC'd to the
LM61460AANRJRR: TI 3-42 V / 6-A low-EMI SYNCHRONOUS buck (SNVSBD5D), VQFN-HR
(RJR "HotRod"), LCSC C2864505 (JLC 2026-06-14: Extended, stock 3,761). 6 A ->
~2x current margin over 2.95 A; Vin op-max 36 V (abs 42 V) covers the 21 V
+VIN_SYS rail. The thermal gate now credits a CONSERVATIVE pour-aware effective
RthJA (30 C/W vs 58.7 bare; DS 7.3 4-layer = 25 C/W) so U1 PASSES on real
thermal margin (Tj ~128 C < 140 C guard) — NO waiver. See the stage-1 block +
thermal.py pour-aware-RthJA docs. (TPS54302 U2/U4 keep their no-EP waivers.)

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
- FB dividers: +5V = 40.2k/10k -> 5.02 V (C12447 40.2k 0603 1% + C25804 Basic; LM61460
  Vref 1.0 V -> Vout = 1.0*(1+40.2/10));
  +3V3 = 100k/22k -> 3.30 V (C25803 + C31850, both Basic);
  +5V_SOM = 68.1k/10k -> 4.65 V nom (PWR-5; C844583 Vishay 0603 1%, LIVE
  2026-06-13: Ext, stock 10,869, min-qty 1 + C25804). PWR-5 RE-CENTER: the
  old 73.2k/10k gave 4.96 V nom / ~5.17 V worst-case-high, poking above the
  SoM's 5.0 V input rec-max; 68.1k/10k re-centers to 4.65 V nom, WC-hi
  ~4.81 V (1% R + 1% Vref) so the WHOLE band stays inside the SoM 4.2-5.0 V
  window with the EN zener clamp (PWR-1) untouched.
- FB feedforward caps (PWR-4, TI all-ceramic-output reference): 75 pF C0G
  ACROSS the TPS54302 bucks' FB TOP resistor — C23 (U2 R4), C21 (U4 R14) —
  to add phase boost / improve transient response on the internally
  compensated TPS54302 with low-ESR ceramic output caps. Part: CGA0603-
  C0G750J500JT, TDK 0603 C0G 50 V (LCSC C22399620, LIVE 2026-06-13: Ext,
  stock 8,020, min-qty 1). U1 (LM61460) follows the SAME idiom per its OWN
  datasheet (SNVSBD5D 9.2.2.10 + Table 9-2/9-5): a 22 pF C0G CFF (C27, C1653)
  ACROSS the FB-top R1, with a 1-k RFF (R12, C21190) in series into FB to damp
  the noise path — see the stage-1 FB feedforward block.
- +5V_SOM EN clamp (always-on strap, NO bring-up port; PWR-1 FIX — see the
  header "EN voltage table"): R12 = 10k SERIES from +VIN to EN (C25804,
  reused 10k); D5 = MMSZ5231B 5.1 V / 500 mW zener EN -> GND (LIVE-verified
  on the JLC parts API 2026-06-13: C85181, Diodes Inc, SOD-123, stock
  180,887, Extended, min-qty 1, $0.0162 @ qty 1 — the canonical 5.1 V
  zener; alternates same query: C2117 BZT52C5V1 Jiangsu Changjin 92,425,
  C66198 MMSZ5231BT1G onsemi 81,989); C20 = 100 nF EN bypass to GND (C14663,
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
- Input caps: U1 (LM61460, DS 9.2.2.5) = 2x 10u/1206 bulk (C13585) + 2x 100n
  50 V X7R HF (C1/C25, C14663), ONE 100 nF per VIN/PGND pin pair as the DS
  mandates; the second buck (TPS54302) keeps 22u/0805 (C45783) + 100n on its
  +5V input. Outputs: U1 = 3x 22u (DS 9.2.2.4 Table 9-5 5 V); the +3V3 buck
  keeps 2x 22u. LDO 1u in / 1u out (C15849). U1 BIAS bypass 1u (C28, C15849).
  All Basic, incl. the 100 nF (C14663, YAGEO CC0603KRX7R9BB104, JLC Basic):
  its 50 V X7R rating is exactly the 9.2.2.5 requirement and covers 21 V input).

Pin maps cross-checked: parts/<MPN>/<MPN>.py (EasyEDA) == KiCad stock
symbols used here (TPS54302: 1 GND 2 SW 3 VIN 4 FB 5 EN 6 BOOT;
Q_NMOS_GSD == AO3400A SOT-23 1 G 2 S 3 D). U1 LM61460 uses the generator-
owned symbol schgen:LM61460 (lib_id= OVERRIDE), which re-draws the SAME
14 pins (TI SNVSBD5D Table 6-1: 1 BIAS 2 VCC 3 AGND 4 FB 5 PGOOD 6 RT
7 EN/SYNC 8 VIN1 9 PGND1 10 SW 11 PGND2 12 VIN2 13 RBOOT 14 CBOOT) with
stock-buck geometry + etypes for the placer — NO footprint change. With the
override, U1 pins are authored BY NUMBER (model.use_part contract).
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

    # ---- stage 1: +VIN (20 V) -> +5V buck (LM61460, VQFN-HR, 6 A SYNC) -------
    # U1 RE-SPEC (wt/buck, 2026-06-14): the +5V buck carries the board's heaviest
    # converter load (2.95 A @ 5 V). The prior LMR33630ADDA (3 A) ran at 98% of
    # rating with no headroom, and its bare-JEDEC Tj sat over the guard band
    # (waived). RESELECTED to the LM61460AANRJRR (LCSC C2864505, JLC 2026-06-14:
    # Extended, stock 3,761): TI 3-42 V / 6-A LOW-EMI SYNCHRONOUS step-down
    # (SNVSBD5D), peak-current-mode, adjustable fSW, in the 14-pin VQFN-HR (RJR
    # "HotRod") package. 6 A rating -> ~2x margin over 2.95 A (>>40% target);
    # Vin op-max 36 V (abs 42 V) covers the 21 V +VIN_SYS rail with wide margin.
    #   Vref = 1.0 V (DS 8.3.11) -> FB divider Vout = 1.0*(1 + Rtop/Rbot);
    #     R1/R2 = 40.2k/10k -> 5.02 V (same Vref + divider RATIO as the old
    #     LMR33630). FB-top LCSC is C12447 (UNI-ROYAL 0603WAF4022T5E, 40.2k 0603
    #     1%); C25804 (10k) bottom unchanged. (The old C25750 LCSC was a mis-key
    #     -> 120k 0402; corrected here, see R1 below.)
    #   fSW = 600 kHz set by RT = 22k (DS Eq 2: RRT(kohm) = (1/fSW(kHz) -
    #     3.3e-5)*1.346e4 -> 600 kHz => 21.99k ~= 22.0k; 22k C31850 already in
    #     this sheet's BOM). 600 kHz keeps the existing 10 uH SWPA8040S: ripple
    #     dIL = Vout*(Vin-Vout)/(Vin*L*fSW) = 5*16/(21*10u*600k) = 0.63 A p-p,
    #     Ipk = 2.95 + 0.32 = 3.27 A < the 4 A Isat.
    #   L = 10 uH (DS 9.2.2.3): the Eq-11 (D<50%) MINIMUM is L >= 0.2*Vout/fSW =
    #     0.2*5/600k = 1.67 uH; 10 uH is well above min, so the part runs stable
    #     with no subharmonic oscillation (inductance must not be LESS than the
    #     minimum). 9.2.2.3 note: a larger-than-min inductor "results in less
    #     output cap being needed to limit ripple but more output cap to manage
    #     large load transients" -> the 3x22 uF COUT (above the 2x22 uF min)
    #     covers that. KEEP the existing 10 uH SWPA8040S (no churn).
    #   CBOOT = 100 nF SW->CBOOT (DS 9.2.2.6, X7R >=10 V); RBOOT short to CBOOT
    #     (DS 9.2.2.7 "RBOOT can be shorted") -> fastest SW edge, lowest HS loss:
    #     RBOOT(13) and CBOOT(14) are the SAME node (BOOT_5V0), a 0R wire, NO
    #     component.
    #   BIAS (pin 1): TIED to +5V_REG via R11 (10 ohm series) + C28 (1 uF bypass)
    #     per DS 9.2.2.9 — the BIAS->VOUT tie reduces internal-LDO power loss
    #     I_LDO*(VIN-VOUT) at VOUT = 5 V (efficiency improvement; see the BIAS
    #     block below). BIAS max voltage 16 V >> 5 V.
    #   VCC (pin 2): 1 uF to AGND (DS 9.2.2.8 internal-LDO bypass, 16 V ceramic).
    #   RT (pin 6): 22k to GND (fSW set). PGOOD (pin 5): NC (unused open-drain;
    #     D1 rail-up LED is the PG indicator).
    #   AGND (3) ties to PGND1/PGND2 (DS pin 3 layout note).
    # THERMAL: VQFN-HR has NO center EP; its die-attach heat path is the bond-
    # frame PGND1 (9) + PGND2 (11) power-ground pads (and the wide SW pad 10),
    # all soldered to the GND copper pour — the package's exposed-pad-equivalent.
    # DS RthJA = 58.7 C/W bare JESD51-7, 25 C/W on a 4-layer board (DS 7.3 +
    # note: "with a 4-layer PCB, a RthJA = 25 C/W can be"). The thermal gate now
    # credits a CONSERVATIVE pour-aware RthJA (see thermal.py) so U1 PASSES on
    # real margin, not a waiver.
    # use_part with a lib_id= OVERRIDE to the generator-owned schematic symbol
    # schgen:LM61460 (parts/LM61460AANRJRR/ keeps the faithful EP-bearing
    # footprint + orderable identity). The override is the LMR33630/TPS54302
    # idiom: the EasyEDA-generated symbol types every pin 'passive' and lays them
    # out for a QFN, which the placer's regulator template cannot read; the local
    # symbol re-draws the SAME 14 pins (NO footprint change) with stock-buck
    # geometry + electrical types (VIN power_in left, SW power_out/output right,
    # PGND/AGND GND bottom, VCC/BIAS/RT/PGOOD aux-left, FB/CBOOT right) so the
    # template places it. With lib_id overridden, pins are authored BY NUMBER
    # (model.use_part contract) — 1 BIAS 2 VCC 3 AGND 4 FB 5 PGOOD 6 RT
    # 7 EN/SYNC 8 VIN1 9 PGND1 10 SW 11 PGND2 12 VIN2 13 RBOOT 14 CBOOT.
    c.use_part("LM61460AANRJRR", ref="U1", lib_id="schgen:LM61460",
               footprint="LM61460AANRJRR:LM61460AANRJRR")
    # DEF-D: U1 input is the POST-shunt rail +VIN_SYS (RS1 series-inserts
    # between the eFuse +VIN and the buck inputs in power_mon.py), so the buck
    # input current — including the input-cap ripple/inrush — flows through RS1
    # and is counted on the U1 ch1 (+VIN) channel. The input caps move with it.
    c.net("+VIN_SYS", "U1.8", "U1.12")                            # VIN1(8)+VIN2(12), post-RS1
    c.net("GND", "U1.9", "U1.11", "U1.3")                         # PGND1(9)+PGND2(11)+AGND(3): heat path
    c.port("EN_5V0", "U1.7", expect=EXPECT_BRINGUP)              # EN/SYNC (pin 7)
    # INPUT CAPS (DS SNVSBD5D 9.2.2.5): bulk + the MANDATORY per-VIN-pin HF caps.
    #   - 2x 10 uF bulk (C2/C3, 1206): satisfies the ">=10 uF ceramic at the input"
    #     minimum (9.2.2.5); 50 V-class 1206 covers the 21 V +VIN_SYS rail.
    #   - 2x 100 nF HF (C1/C25, 50 V X7R): 9.2.2.5 REQUIRES a "small case size
    #     100-nF ceramic ... at EACH input/ground pin pair, VIN1/PGND1 and
    #     VIN2/PGND2, immediately adjacent to the device ... The two 100 nF must
    #     also be rated at 50 V with an X7R or better dielectric." The VQFN-HR
    #     (RJR) splits VIN/PGND across opposite package sides, so ONE 100 nF goes
    #     at each VIN/PGND location (DS example: "two 4.7-uF and two 100-nF, one
    #     at each VIN/PGND"). C14663 = YAGEO CC0603KRX7R9BB104, 100 nF 50 V X7R
    #     0603 (live JLC 2026-06-15: Basic, stock 17,789,417) — meets the
    #     50 V/X7R rule. The netlist puts both on +VIN_SYS->GND (the placer/PCB
    #     fans one to each VIN pad); the split is a layout/footprint property.
    for ref, val, fp, lcsc in (("C1", "100n", C0603, "C14663"),  # HF, VIN1/PGND1
                               ("C25", "100n", C0603, "C14663"), # HF, VIN2/PGND2
                               ("C2", "10u", C1206, "C13585"),  # bulk (>=10 uF)
                               ("C3", "10u", C1206, "C13585")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN_SYS", f"{ref}.1")                              # buck-input filter, post-RS1
        c.net("GND", f"{ref}.2")
    c.part("C24", "Device:C", "1u", C0603, LCSC="C15849")          # VCC int-LDO bypass
    c.net("U1_VCC", "U1.2", "C24.1")                              # VCC (pin 2), local bias
    c.net("GND", "C24.2")
    # BIAS (pin 1) TIED TO VOUT (DS SNVSBD5D 9.2.2.9): "Because VOUT = 5 V in
    # this design, the BIAS pin is tied to VOUT to reduce LDO power loss. The
    # output voltage is supplying the LDO current instead of the input voltage.
    # The power saving is I_LDO*(VIN - VOUT)." With VIN ~21 V this is the larger
    # saving (9.2.2.9 / 8.3.14). 9.2.2.9 adds: "a series resistor, 1 ohm to
    # 10 ohm, can be added between VOUT and BIAS" to keep VOUT noise/transients
    # off BIAS, and "a bypass capacitor of 1 uF or higher can be added close to
    # the BIAS pin." Max allowed BIAS voltage is 16 V (>> 5 V) — safe.
    #   R11 = 10 ohm series +5V_REG -> BIAS (top of the 1-10 ohm band: max noise
    #     filtering; the BIAS LDO sink current is tiny so the IR drop is
    #     negligible). C22859 = UNI-ROYAL 0603WAF100JT5E 10R 0603 (live JLC
    #     2026-06-15: Basic, stock 3,513,381).
    #   C28 = 1 uF BIAS bypass -> GND, close to pin 1. C15849 = Samsung
    #     CL10A105KB8NNNC 1 uF 50 V X5R 0603 (Basic, stock 6,321,848).
    c.part("R11", "Device:R", "10R", R_FP, LCSC="C22859")          # BIAS series (1-10 ohm)
    c.net("+5V_REG", "R11.1")                                      # tie BIAS to VOUT
    c.part("C28", "Device:C", "1u", C0603, LCSC="C15849")          # BIAS bypass
    c.net("BIAS_5V0", "U1.1", "R11.2", "C28.1")                   # BIAS (pin 1)
    c.net("GND", "C28.2")
    c.part("R10", "Device:R", "22k", R_FP, LCSC="C31850")          # RT: fSW=600kHz (DS Eq 2)
    c.net("RT_5V0", "U1.6", "R10.1")                             # RT (pin 6)
    c.net("GND", "R10.2")
    c.part("C4", "Device:C", "100n", C0603, LCSC="C14663")          # BOOT (CBOOT) cap
    # RBOOT(13) short to CBOOT(14): SAME node, a 0R wire (DS EC table) — no R.
    c.net("BOOT_5V0", "U1.14", "U1.13", "C4.1")                  # CBOOT(14)+RBOOT(13)
    c.part("L1", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_5V0", "U1.10", "C4.2", "L1.1")                      # SW(10) + CBOOT-cap + L
    # DEF-D: buck-1 OUTPUT cluster is +5V_REG (reg-side of RS2). The inductor
    # node, output bulk caps, FB sense and the PG LED stay on the regulator
    # side; the board +5V rail (post-RS2) carries the measured consumers (U2
    # input, C7/C8). RS2 bridges +5V_REG -> +5V so consumer draw is measured.
    c.net("+5V_REG", "L1.2")
    # OUTPUT CAPS (DS SNVSBD5D 9.2.2.4 + Table 9-3/9-5): 3x 22 uF ceramic for the
    # 5 V output. Table 9-5 (the 5 V application BOM) lists 3x22 uF COUT at 400 k,
    # 1000 k and 2100 kHz; Table 9-3 5 V "better transient" at 2.1 MHz is also
    # 3x22 uF. This RAISES the previous 2x22 uF (the Table 9-3 5 V *minimum* at
    # 2.1 MHz) by one cap. Justification at this design's L/fSW: 9.2.2.3 notes a
    # larger-than-minimum inductor (here 10 uH >> the ~1.67 uH Eq-11 minimum at
    # 600 kHz) "results in less output capacitance being needed to limit output
    # ripple but more output capacitance being needed to manage large load
    # transients" — so with the big 10 uH the transient term dominates and 3x22 uF
    # gives the datasheet-coherent transient margin at 5 V / 6 A. (A 47 uF/1210 was
    # considered per Table 9-3 400 kHz; the well-stocked Basic 47 uF 1210 parts on
    # JLC are 6.3 V-rated — too low for a 5 V rail with margin — and the 25 V
    # 47 uF/1210 is Extended/low-stock, so 3x22 uF reuses the proven 25 V Basic
    # C45783 and lands on the Table 9-5 5 V value.)
    for ref in ("C5", "C6", "C26"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+5V_REG", f"{ref}.1")                              # output bulk, reg-side
        c.net("GND", f"{ref}.2")
    c.part("R1", "Device:R", "40.2k", R_FP, LCSC="C12447")         # FB top (VFB 1.0 -> 5.02 V); C12447 = UNI-ROYAL 0603WAF4022T5E 40.2k 0603 1%. (Prior LCSC C25750 was a mis-key: it resolves to a 120k 0402 -> the assembled FB divider would set ~13.1 V on the +5V rail and destroy the SoM. BOM-CRITICAL.)
    c.part("R2", "Device:R", "10k", R_FP, LCSC="C25804")           # FB bottom
    c.net("+5V_REG", "R1.1")                                       # FB senses the regulated node
    c.net("FB_5V0", "U1.4", "R1.2", "R2.1")                       # FB (pin 4)
    c.net("GND", "R2.2")
    # FB FEEDFORWARD (DS SNVSBD5D 9.2.2.10 + Tables 9-2/9-3/9-5): a CFF across the
    # FB-top resistor "is used to improve phase margin and transient response of
    # circuits which have output capacitors with low ESR" (the all-ceramic COUT
    # here). The ESR-zero rule passes: ceramic COUT has its ESR zero well above
    # 200 kHz, so 9.2.2.10's "if the ESR zero ... is below 200 kHz, no CFF" does
    # NOT exclude us; and VOUT = 5 V < 14 V, so the "no CFF above 14 V" rule does
    # not apply either. Value = 22 pF C0G: Table 9-2 (5 V rows) and Table 9-5 (5 V
    # BOM) both list CFF = 22 pF. 9.2.2.10 also says: "Since this capacitor can
    # conduct noise from the output of the circuit directly to the FB node of the
    # IC, a 1-kohm resistor, RFF, can be placed in series with CFF" (Table 9-2 5 V
    # RFF = 1 kohm) — so the network is +5V_REG -> C27(CFF) -> RFF(R12) -> FB_5V0,
    # i.e. CFF bridges the FB-top R1 with RFF damping the noise path into FB.
    # (The 3 TPS54302 bucks use the same all-ceramic feedforward idiom, PWR-4.)
    #   C27 = 22 pF 50 V C0G 0603 (CL10C220JB8NNNC, live JLC 2026-06-15: Basic,
    #     stock 1,017,863). R12 = 1 k 0603 (C21190, the sheet's existing 1k).
    c.part("C27", "Device:C", "22p", C0603, LCSC="C1653")          # CFF (DS 9.2.2.10)
    c.part("R12", "Device:R", "1k", R_FP, LCSC="C21190")           # RFF series (DS 9.2.2.10)
    c.net("+5V_REG", "C27.1")                                      # CFF top = VOUT (across R1)
    c.net("CFF_5V0", "C27.2", "R12.1")                            # CFF -> RFF noise damp
    c.net("FB_5V0", "R12.2")                                       # RFF -> FB node
    c.part("D1", "Device:LED", "red", LED_FP, LCSC="C2286")        # +5V present indicator
    c.part("R3", "Device:R", "1k", R_FP, LCSC="C21190")
    c.net("+5V_REG", "D1.2")                                       # LED reg-side (regulator up)
    c.net("PG_5V0", "D1.1", "R3.1")                               # plain rail-up LED (reg-side)
    c.net("GND", "R3.2")
    # PGOOD (pin 5) author NC: open-drain status output (DS pin 5, high=OK via an
    # external pull-up, low=fault). Unused here — the +5V rail-up LED (D1) is the
    # board's PG indicator — so the open-drain output is left unconnected (an
    # un-driven open-drain output floats harmlessly; nothing reads it).
    c.nc("U1.5")                                                  # PGOOD (pin 5) — unused, NC

    # ---- stage 2: +5V -> +3V3 buck ------------------------------------------
    c.use_part("TPS54302DDCR", ref="U2", lib_id=BUCK_LIB, footprint=BUCK_FP)
    c.net("+5V", "U2.3")
    c.net("GND", "U2.1")
    c.port("EN_3V3", "U2.5", expect=EXPECT_BRINGUP)
    for ref, val, fp, lcsc in (("C7", "100n", C0603, "C14663"),
                               ("C8", "22u", C0805, "C45783")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+5V", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("C9", "Device:C", "100n", C0603, LCSC="C14663")          # BOOT
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
    # (power_som.py, 2026-06-14): U1's reselect to a larger exposed-pad buck
    # pushed the 4-converter sheet past A3, and the +5V_SOM stage is the cleanly-
    # separable unit (only +VIN / +5V_SOM / GND rails cross). See power_som.py.

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
    # U1 LM61460 (wt/buck re-spec): NO LONGER WAIVED. The thermal gate now
    # CREDITS a conservative pour-aware effective RthJA (30 C/W vs the 58.7 C/W
    # bare JEDEC) on the strength of the datasheet's own poured-board data
    # (DS 7.3: 25 C/W on a 4-layer PCB; PGND1/PGND2 + SW pads soldered to the GND
    # pour, proven by the netlist). U1 PASSES on real margin: Pd 2.60 W,
    # Tj = 50 + 2.60*30 = 128 C < 140 C guard (~12 C margin). The 6 A rating also
    # gives ~2x current margin over the 2.95 A load. Bench Tj at bring-up remains
    # the final arbiter (see thermal.py pour-aware-RthJA docs + carrier/research/
    # thermal_bucks.md), but the gate no longer needs a waiver to pass it.
    return c                     # U4 +5V_SOM waiver lives on power_som.py
