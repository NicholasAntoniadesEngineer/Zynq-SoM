"""power_som — the always-on +VIN(20V) -> +5V_SOM buck that feeds the SoM VIN.

SPLIT FROM power.py (2026-06-14, sheet-density): the multi-converter power sheet
overflowed one A3 page, so the +5V_SOM stage (U4) is the cleanly-separable unit
— only the +VIN / +5V_SOM / GND rails cross to power.py (they merge by name
across sheets), every signal net (EN_5V_SOM / SW_5V_SOM / BOOT_5V_SOM /
FB_5V_SOM / PG_5V_SOM) is internal — so it moves here as its own sheet. (A power
sheet's regulators chain-share input/output rails, so this split is authored,
not auto-paginated: the human assigns each decoupling cap to its stage, which
the netlist alone cannot.)

U4 RE-SPEC (thermal finding, 2026-06-16): U4 WAS a TPS54302DDCR (SOT-23-6, NO
exposed pad, 3 A). At the +5V_SOM 2.004 A load and the HONEST datasheet RthJA
(TI SLVSDG6C 5.4: 118.9 C/W JESD51-7, 57.2 C/W EVM) and the 125 C rec-op Tj-max
(5.3), its Tj was 245 C (JEDEC) / 144 C (even on the EVM) at eff 0.85 — over the
125 C rec-max. The thermal gate had MASKED this with a fabricated 70.6 C/W + a
140 C guard + an author waiver; thermal.py is now re-based to the datasheet
figures. RESELECTED to the LM61460AANRJRR — the SAME EP-equivalent 6 A buck on
power.py U1/U2 (LCSC C2864505, TI SNVSBD5D, VQFN-HR RJR "HotRod"): PGND1/PGND2 +
SW pads soldered to the GND pour are the exposed-pad-equivalent heat path. 6 A
-> 67% headroom over 2.004 A; at the gate's pour-aware 30 C/W (DS 7.3: 25 C/W
4-layer / 58.7 bare) Tj = 50 + (1/0.85-1)*4.65*2.004*30 = 99 C << the 140 C
guard. U4 draws its FAITHFUL parts/LM61460AANRJRR/ dossier symbol (no lib_id
override, the "0 hand-built symbols" idiom).

P0 — SoM VIN OVERVOLTAGE FIX (wave3_function_map.md, user-signed-off
2026-06-12). The SoM is a 4.2-5 V-input module (its on-module regulators are
all 6 V-class). Binding the SoM's J1 VIN to the 20 V PD rail +VIN would destroy
it at the first PD contract. RESOLUTION: this buck (U4) drops +VIN -> +5V_SOM
(5.0 V class) and som_conn_gen rebinds J1 VIN -> +5V_SOM. +5V_SOM is ALWAYS-ON
(NO bring-up gate cell): the PD chain is FUSB302 (on +3V3_SC) + the SoM SC, and
+3V3_SC is generated ON the SoM from its VIN — so if SoM VIN waited for a DIP
the SC would be dead, nobody would negotiate PD, and 20 V would never arrive
(circular). At the 5 V default-USB contract the buck runs near 100% duty and
passes ~4.7-4.8 V (inside the 4.2-5 V window); after the 20 V contract it
regulates ~4.65 V (PWR-5 divider). Alive pre-DIP by design, like +3V3_SC.

PWR-1 — U4 EN clamp (deep-audit 2026-06-12; carried through the 2026-06-16
LM61460 re-spec). The always-on EN strap must enable the buck at the 4.75 V
default-USB contract AND never exceed the EN recommended-max at the 21 V (20 V
+5%) contract. A plain divider can't do both, so: R12 = 10k SERIES +VIN_SYS->EN
; D5 = MMSZ5231B 5.1 V zener EN->GND ; C20 = 100 nF EN bypass. At low VIN the
zener is off and the 1.55 uA hysteresis through 10k is < 16 uV (EN ~= VIN ->
sure enable); at high VIN the zener clamps EN to ~5.0 V (R12 absorbs VIN - Vz).
EN stays inside [~1.3, 5.5] V across 4.75-21 V. The LM61460 EN/SYNC pin (DS
SNVSBD5D) likewise has NO internal clamp and abs-max 42 V (vs the TPS54302's
abs-max 7 V, rec-max 5.5 V), so the clamp is MORE than sufficient for the new
part — keeping EN well inside the LM61460's enable window AND comfortably below
even the old TPS54302 5.5 V rec-max envelope the spice gate enforces. The schgen
spice gate (schgen/verify/spice.py "EN clamp") re-derives EN from the netlist —
finding the EN pin by NAME (EN/SYNC) for the LM61460 — and FAILS if EN ever
leaves [1.5, 5.5] V; PWR-1 can never silently regress.

Parts (live-verified on JLCPCB): LM61460AANRJRR (C2864505, TI 3-42 V / 6 A sync
buck, VQFN-HR RJR; the EP-equivalent part on power.py U1/U2); SWPA8040S100MT
(C37429, 10 uH/Isat 4.1 A); R12 10k (C25804) + D5 MMSZ5231B (C85181, 5.1 V/
500 mW SOD-123) + C20 100n (C14663) EN clamp; VCC 1 uF (C15849) + BIAS 10R
series (C22859) + 1 uF bypass (C15849) + RT 22k (C31850) + CBOOT/RBOOT 100 nF
(C14663); FB 47.5k/13k (C23061 + C22797) -> 4.654 V nom (WC-corner [4.582, 4.728] V,
inside the SoM 4.2-5.0 V window) + 22 pF C0G feedforward
(C1653) + 1k RFF (C21190); KT-0603R PG LED (C2286) + 1k (C21190). U4 draws its
FAITHFUL LM61460 dossier symbol (pin map 1 BIAS 2 VCC 3 AGND 4 FB 5 PGOOD 6 RT
7 EN/SYNC 8 VIN1 9 PGND1 10 SW 11 PGND2 12 VIN2 13 RBOOT 14 CBOOT), same as
power.py's U1/U2.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"
DZ_FP = "Diode_SMD:D_SOD-123"
L_FP = "SWPA8040S100MT:SWPA8040S100MT"


def circuit() -> Circuit:
    c = Circuit("power_som",
                "Power: +VIN -> +5V_SOM always-on buck (SoM VIN, P0 fix)")

    # +VIN (20 V) -> +5V_SOM buck (U4, LM61460, VQFN-HR, 6 A SYNC, ALWAYS-ON).
    # Identical EP-equivalent cell to power.py's U1/U2 LM61460 stages EXCEPT the
    # EN/SYNC is strapped on by a SERIES-R + ZENER CLAMP (PWR-1), not a bring-up
    # port: this rail must be alive pre-DIP/pre-PD so the SoM SC can boot and
    # master the FUSB302 PD negotiation. U4 draws its FAITHFUL parts/ dossier
    # symbol (no lib_id override) — pins BY NUMBER: 1 BIAS 2 VCC 3 AGND 4 FB
    # 5 PGOOD 6 RT 7 EN/SYNC 8 VIN1 9 PGND1 10 SW 11 PGND2 12 VIN2 13 RBOOT
    # 14 CBOOT.
    c.use_part("LM61460AANRJRR", ref="U4")
    # DEF-D: U4's VIN is the POST-shunt rail +VIN_SYS (RS1 in power_mon.py sits
    # between the eFuse +VIN and ALL buck inputs), so U4's draw flows through
    # RS1 and is counted on the +VIN_SYS telemetry channel alongside U1. The
    # input bulk caps move with the pin. The EN-clamp series R12 ALSO references
    # +VIN_SYS (the buck's own input rail): the ~tens-of-uA bias then flows
    # through RS1 too, and EN tracks the actual buck input. RS1 is a 10 mR short
    # (+VIN ~= +VIN_SYS) so the PWR-1 EN-clamp voltage table is unchanged. This
    # also keeps the always-on EN-UVLO strap on the input rail, which the
    # placer's regulator template requires (UVLO-top must sit on the VIN rail).
    c.net("+VIN_SYS", "U4.8", "U4.12")                            # VIN1(8)+VIN2(12), post-RS1
    c.net("GND", "U4.9", "U4.11", "U4.3")                         # PGND1/PGND2/AGND: heat path
    c.part("R12", "Device:R", "10k", R_FP, LCSC="C25804")          # EN series
    c.part("D5", "Device:D_Zener", "MMSZ5231B", DZ_FP, LCSC="C85181")  # 5.1V clamp
    c.part("C20", "Device:C", "100n", C0603, LCSC="C14663")         # EN bypass
    c.net("+VIN_SYS", "R12.1")                                     # EN-clamp ref: buck input rail
    c.net("EN_5V_SOM", "U4.7", "R12.2", "D5.1", "C20.1")           # EN/SYNC(7); D5.1 = K
    c.net("GND", "D5.2", "C20.2")                                  # D5.2 = A
    # INPUT CAPS (DS SNVSBD5D 9.2.2.5): bulk + the MANDATORY per-VIN-pin HF caps.
    # 50 V-class covers the 20 V +VIN_SYS rail (worst-case 21 V) with margin.
    for ref, val, fp, lcsc in (("C14", "100n", C0603, "C14663"),  # HF, VIN1/PGND1
                               ("C25", "100n", C0603, "C14663"),  # HF, VIN2/PGND2
                               ("C15", "10u", C1206, "C13585"),   # bulk
                               ("C16", "10u", C1206, "C13585")):  # bulk
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN_SYS", f"{ref}.1")                             # buck-input filter, post-RS1
        c.net("GND", f"{ref}.2")
    c.part("C22", "Device:C", "1u", C0603, LCSC="C15849")          # VCC int-LDO bypass
    c.net("U4_VCC", "U4.2", "C22.1")                             # VCC (pin 2)
    c.net("GND", "C22.2")
    # BIAS (pin 1) TIED TO VOUT (DS 9.2.2.9): VOUT 4.65 V (> the 3.1 V BIAS-
    # active threshold) supplies the internal LDO; 10 ohm series + 1 uF bypass,
    # identical idiom to U1/U2. BIAS max 16 V >> 4.65 V.
    c.part("R17", "Device:R", "10R", R_FP, LCSC="C22859")          # BIAS series
    c.net("+5V_SOM", "R17.1")                                      # tie BIAS to VOUT
    c.part("C23", "Device:C", "1u", C0603, LCSC="C15849")          # BIAS bypass
    c.net("BIAS_5V_SOM", "U4.1", "R17.2", "C23.1")              # BIAS (pin 1)
    c.net("GND", "C23.2")
    c.part("R18", "Device:R", "22k", R_FP, LCSC="C31850")          # RT: fSW=600kHz
    c.net("RT_5V_SOM", "U4.6", "R18.1")                          # RT (pin 6)
    c.net("GND", "R18.2")
    c.part("C17", "Device:C", "100n", C0603, LCSC="C14663")         # BOOT (CBOOT) cap
    # RBOOT(13) short to CBOOT(14): SAME node, a 0R wire (DS EC) — no R.
    c.net("BOOT_5V_SOM", "U4.14", "U4.13", "C17.1")             # CBOOT(14)+RBOOT(13)
    c.part("L3", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_5V_SOM", "U4.10", "C17.2", "L3.1")                  # SW(10) + CBOOT-cap + L
    c.net("+5V_SOM", "L3.2")
    for ref in ("C18", "C19"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+5V_SOM", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    # FB divider: Vref = 1.0 V (LM61460 DS 8.3.11) -> Vout = 1.0*(1+Rtop/Rbot).
    # R14/R15 = 47.5k/13k -> 4.654 V nom (WC-corner [4.582, 4.728] V, inside the
    # SoM 4.2-5.0 V input window; PWR-5 re-centred BELOW 5 V). C23061 + C22797
    # both already in schgen.verify.ratings.
    c.part("R14", "Device:R", "47.5k", R_FP, LCSC="C23061")        # FB top
    c.part("R15", "Device:R", "13k", R_FP, LCSC="C22797")          # FB bottom
    c.net("+5V_SOM", "R14.1")
    c.net("FB_5V_SOM", "U4.4", "R14.2", "R15.1")                 # FB (pin 4) -> 4.654 V
    c.net("GND", "R15.2")
    # FB FEEDFORWARD (DS 9.2.2.10): 22 pF CFF across FB-top + 1 k RFF series damp
    # (VOUT 4.65 V < 14 V), identical idiom to U1/U2:
    # +5V_SOM -> CFF -> RFF -> FB_5V_SOM.
    c.part("C21", "Device:C", "22p", C0603, LCSC="C1653")          # CFF (DS 9.2.2.10)
    c.part("R19", "Device:R", "1k", R_FP, LCSC="C21190")           # RFF series
    c.net("+5V_SOM", "C21.1")                                      # CFF top = VOUT (across R14)
    c.net("CFF_5V_SOM", "C21.2", "R19.1")                        # CFF -> RFF noise damp
    c.net("FB_5V_SOM", "R19.2")                                    # RFF -> FB node
    c.part("D4", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +5V_SOM
    c.part("R16", "Device:R", "1k", R_FP, LCSC="C21190")
    c.net("+5V_SOM", "D4.2")
    c.net("PG_5V_SOM", "D4.1", "R16.1")
    c.net("GND", "R16.2")
    # PGOOD (pin 5) author NC: unused open-drain (DS pin 5) — D4 is the board PG
    # indicator; an un-driven open-drain output floats harmlessly.
    c.nc("U4.5")                                                  # PGOOD (pin 5) — unused, NC

    # test point on this stage's generated rail (round-4 coverage gate)
    c.testpoint("+5V_SOM")

    # power-tree budget: this sheet owns only U4's OWN local load (PG LED + FB
    # divider). The SoM MODULE draw (~2 A) is declared by som_conn_gen on J1
    # where the module consumes +5V_SOM — the gate sums draws across all sheets.
    c.draws("+5V_SOM", 0.004, "PG LED (KT-0603R + 1k, ~3 mA) + FB divider 60 uA "
                              "(SoM module load declared on som_j1)")

    # THERMAL (verification P2): NO WAIVER. The 2026-06-16 finding re-based the
    # thermal gate to the HONEST datasheet RthJA and proved the old TPS54302 U4
    # ran over its 125 C rec-max at the +5V_SOM 2.004 A load; U4 is now the
    # LM61460 EP buck, which the gate PASSES on real margin (Tj ~99 C << 140 C
    # guard) on the same pour-aware RthJA credit U1/U2 earn.
    return c
