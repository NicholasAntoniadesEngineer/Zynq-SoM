"""power_som — the always-on +VIN(20V) -> +5V_SOM buck that feeds the SoM VIN.

SPLIT FROM power.py (2026-06-14, sheet-density): power.py's U1 +5V buck was
reselected to the larger LMR33630 (HSOIC-8 PowerPAD, a real exposed pad for
the heat path), which pushed the 4-converter power sheet past one A3 page. The
+5V_SOM stage (U4) is the cleanly-separable unit — only the +VIN / +5V_SOM /
GND rails cross to power.py (they merge by name across sheets), every signal
net (EN_5V_SOM / SW_5V_SOM / BOOT_5V_SOM / FB_5V_SOM / PG_5V_SOM) is internal —
so it moves here as its own sheet. (A power sheet's regulators chain-share
input/output rails, so this split is authored, not auto-paginated: the human
assigns each decoupling cap to its stage, which the netlist alone cannot.)

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

PWR-1 — U4 EN clamp (deep-audit 2026-06-12, LIVE TI SLVSDG6C). The earlier
22k/10k divider presented 6.56 V on EN at the 21 V contract (TPS54302 EN
rec-max 5.5 V, abs-max 7 V; there is NO internal EN clamp — only a 1.55 uA
hysteresis source). A plain re-ratio can't satisfy turn-on-at-4.75 V AND
<=5.5 V-at-21 V. RESOLUTION: R12 = 10k SERIES +VIN->EN ; D5 = MMSZ5231B 5.1 V
zener EN->GND ; C20 = 100 nF EN bypass. At low VIN the zener is off and the
1.55 uA through 10k is < 16 uV (EN ~= VIN -> sure enable, threshold 1.21 V
typ); at high VIN the zener clamps EN to ~5.0 V (R12 absorbs VIN - Vz). EN
stays inside [~1.3, 5.5] V across 4.75-21 V. The schgen spice gate
(schgen/spice.py "EN clamp") re-derives this from the netlist and FAILS if EN
ever leaves [1.5, 5.5] V — PWR-1 can never silently regress.

Parts (live-verified on JLCPCB 2026-06-10): TPS54302DDCR (C311983, 4.5-28 V 3 A
sync buck, TSOT-23-6); SWPA8040S100MT (C37429, 10 uH/~4 A); R12 10k (C25804) +
D5 MMSZ5231B (C85181, 5.1 V/500 mW SOD-123) + C20 100n (C1591) EN clamp; FB
68.1k/10k (C844583 + C25804) -> 4.65 V nom (PWR-5: WC-hi ~4.81 V, inside the
SoM 4.2-5.0 V window) + 75 pF C0G feedforward (C22399620); KT-0603R PG LED
(C2286) + 1k (C21190). Symbol/footprint stay the KiCad stock TPS54302 drawing
(pin map 1 GND 2 SW 3 VIN 4 FB 5 EN 6 BOOT), same as power.py's U2.
"""

from __future__ import annotations

from schgen.model import Circuit

BUCK_LIB = "Regulator_Switching:TPS54302"
BUCK_FP = "Package_TO_SOT_SMD:TSOT-23-6"
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

    # +VIN (20 V) -> +5V_SOM buck (U4, TPS54302, ALWAYS-ON). Identical cell to
    # power.py's TPS54302 stages EXCEPT the EN is strapped on by a SERIES-R +
    # ZENER CLAMP (PWR-1), not a bring-up port: this rail must be alive pre-DIP/
    # pre-PD so the SoM SC can boot and master the FUSB302 PD negotiation.
    c.use_part("TPS54302DDCR", ref="U4", lib_id=BUCK_LIB, footprint=BUCK_FP)
    # DEF-D: U4's VIN is the POST-shunt rail +VIN_SYS (RS1 in power_mon.py sits
    # between the eFuse +VIN and ALL buck inputs), so U4's draw flows through
    # RS1 and is counted on the +VIN_SYS telemetry channel alongside U1. The
    # input bulk caps move with the pin. The EN-clamp series R12 ALSO references
    # +VIN_SYS (the buck's own input rail): the ~tens-of-uA bias then flows
    # through RS1 too, and EN tracks the actual buck input. RS1 is a 10 mR short
    # (+VIN ~= +VIN_SYS) so the PWR-1 EN-clamp voltage table is unchanged. This
    # also keeps the always-on EN-UVLO strap on the input rail, which the
    # placer's regulator template requires (UVLO-top must sit on the VIN rail).
    c.net("+VIN_SYS", "U4.3")                                      # VIN, post-RS1
    c.net("GND", "U4.1")
    c.part("R12", "Device:R", "10k", R_FP, LCSC="C25804")          # EN series
    c.part("D5", "Device:D_Zener", "MMSZ5231B", DZ_FP, LCSC="C85181")  # 5.1V clamp
    c.part("C20", "Device:C", "100n", C0603, LCSC="C1591")         # EN bypass
    c.net("+VIN_SYS", "R12.1")                                     # EN-clamp ref: buck input rail
    c.net("EN_5V_SOM", "U4.5", "R12.2", "D5.1", "C20.1")           # D5.1 = K
    c.net("GND", "D5.2", "C20.2")                                  # D5.2 = A
    for ref, val, fp, lcsc in (("C14", "100n", C0603, "C1591"),
                               ("C15", "10u", C1206, "C13585"),
                               ("C16", "10u", C1206, "C13585")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN_SYS", f"{ref}.1")                             # buck-input filter, post-RS1
        c.net("GND", f"{ref}.2")
    c.part("C17", "Device:C", "100n", C0603, LCSC="C1591")         # BOOT
    c.net("BOOT_5V_SOM", "U4.6", "C17.1")
    c.part("L3", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_5V_SOM", "U4.2", "C17.2", "L3.1")
    c.net("+5V_SOM", "L3.2")
    for ref in ("C18", "C19"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+5V_SOM", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("R14", "Device:R", "68.1k", R_FP, LCSC="C844583")       # FB top
    c.part("R15", "Device:R", "10k", R_FP, LCSC="C25804")          # FB bottom
    c.part("C21", "Device:C", "75p", C0603, LCSC="C22399620")      # FB feedfwd
    c.net("+5V_SOM", "R14.1", "C21.1")
    c.net("FB_5V_SOM", "U4.4", "R14.2", "R15.1", "C21.2")          # -> 4.65 V
    c.net("GND", "R15.2")
    c.part("D4", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +5V_SOM
    c.part("R16", "Device:R", "1k", R_FP, LCSC="C21190")
    c.net("+5V_SOM", "D4.2")
    c.net("PG_5V_SOM", "D4.1", "R16.1")
    c.net("GND", "R16.2")

    # test point on this stage's generated rail (round-4 coverage gate)
    c.testpoint("+5V_SOM")

    # power-tree budget: this sheet owns only U4's OWN local load (PG LED + FB
    # divider). The SoM MODULE draw (~2 A) is declared by som_conn_gen on J1
    # where the module consumes +5V_SOM — the gate sums draws across all sheets.
    c.draws("+5V_SOM", 0.004, "PG LED (KT-0603R + 1k, ~3 mA) + FB divider 60 uA "
                              "(SoM module load declared on som_j1)")

    # THERMAL WAIVER (verification P2) — TPS54302 SOT-23-6 has no exposed pad;
    # the bare-package 2s2p RthJA overstates Tj. Layout-critical (power copper
    # pour + thermal vias -> ~45-55 C/W). REVIEW: confirm by thermal sim/bench
    # at bring-up; else move to an EP buck (carrier/research/thermal_bucks.md).
    c.waive_thermal("U4",
                    "TPS54302 SOT-23-6, no EP: bare 2s2p RthJA 70.6 C/W "
                    "overstates Tj; layout-critical (power copper pour + "
                    "thermal vias -> ~45-55 C/W) — VERIFY by thermal sim/bench "
                    "at bring-up else move to an EP buck "
                    "(see carrier/research/thermal_bucks.md)")
    return c
