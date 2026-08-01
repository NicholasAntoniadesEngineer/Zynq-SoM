from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"
DZ_FP = "Diode_SMD:D_SOD-123"
L_FP = "SWPA8040S100MT:SWPA8040S100MT"

BUCK_PART = register(
    "power_som.buck", "LM61460AANRJRR", "part",
    "TI SNVSBD5D 3-42 V / 6 A synchronous buck, VQFN-HR RJR, LCSC C2864505 — "
    "the same EP-equivalent part as power.py U1/U2, its PGND1/PGND2 + SW pads "
    "soldered to the GND pour forming the heat path. Re-spec 2026-06-16: the "
    "prior TPS54302DDCR (SOT-23-6, no exposed pad) ran Tj 245 C JESD51-7 / "
    "144 C EVM at the 2.004 A load against a 125 C rec-op max (SLVSDG6C 5.3, "
    "5.4). At the gate's pour-aware 30 C/W (DS 7.3: 25 C/W 4-layer, 58.7 bare) "
    "this part sits at Tj = 50 + (1/0.85-1)*4.65*2.004*30 = 99 C, no waiver.",
    "datasheet")

EN_SERIES_R = register(
    "power_som.en_series_r", "10k", "ohm",
    "PWR-1 EN clamp, series +VIN_SYS -> EN. At low VIN the zener is off and the "
    "1.55 uA hysteresis through 10k is under 16 uV, so EN tracks VIN and the "
    "buck surely enables at the 4.75 V default-USB contract; at high VIN this "
    "resistor absorbs VIN - Vz. LCSC C25804.",
    "datasheet")

EN_ZENER = register(
    "power_som.en_zener", "MMSZ5231B", "part",
    "PWR-1 EN clamp, 5.1 V / 500 mW SOD-123 (LCSC C85181), holding EN at ~5.0 V "
    "at the 21 V contract. EN stays inside [~1.3, 5.5] V across 4.75-21 V. The "
    "LM61460 EN/SYNC pin has no internal clamp and abs max 42 V (SNVSBD5D), so "
    "the clamp is more than sufficient and stays inside the 5.5 V envelope the "
    "spice gate enforces.",
    "datasheet")

INPUT_BULK = register(
    "power_som.input_bulk", "10u", "F",
    "SNVSBD5D 9.2.2.5 input bulk, 50 V-class 1206 for the 21 V worst-case "
    "+VIN_SYS rail. LCSC C13585.",
    "datasheet")

INPUT_HF = register(
    "power_som.input_hf", "100n", "F",
    "SNVSBD5D 9.2.2.5 MANDATORY per-VIN-pin HF cap — one at VIN1/PGND1 and one "
    "at VIN2/PGND2, not one shared. LCSC C14663.",
    "datasheet")

VCC_BYPASS = register("power_som.vcc_bypass", "1u", "F",
                      "VCC internal-LDO bypass (SNVSBD5D). LCSC C15849.",
                      "datasheet")

BIAS_SERIES_R = register(
    "power_som.bias_series_r", "10R", "ohm",
    "SNVSBD5D 9.2.2.9 BIAS series element. BIAS is tied to VOUT because 4.65 V "
    "clears the 3.1 V BIAS-active threshold and sits far under the 16 V BIAS "
    "max; identical idiom to U1/U2. LCSC C22859.",
    "datasheet")

BIAS_BYPASS = register("power_som.bias_bypass", "1u", "F",
                       "BIAS bypass (SNVSBD5D 9.2.2.9). LCSC C15849.",
                       "datasheet")

RT_R = register("power_som.rt", "22k", "ohm",
                "SNVSBD5D Eq 2 -> fSW ~600 kHz, matching U1/U2. LCSC C31850.",
                "datasheet")

BOOT_CAP = register("power_som.boot_cap", "100n", "F",
                    "CBOOT (SNVSBD5D). RBOOT(13) shorts to CBOOT(14) as one "
                    "node — a 0R wire per the DS EC table, no resistor fitted. "
                    "LCSC C14663.",
                    "datasheet")

INDUCTOR = register("power_som.inductor", "10uH", "H",
                    "SWPA8040S100MT, Isat 4.1 A over the 2.004 A load. "
                    "LCSC C37429.",
                    "datasheet")

OUTPUT_BULK = register("power_som.output_bulk", "22u", "F",
                       "+5V_SOM output bulk, 2 x 0805. LCSC C45783.",
                       "datasheet")

FB_TOP = register(
    "power_som.fb_top", "47.5k", "ohm",
    "FB divider top. LM61460 Vref = 1.0 V (SNVSBD5D 8.3.11), so Vout = "
    "1.0*(1+Rtop/Rbot); 47.5k/13k -> 4.654 V nom, worst-case corner "
    "[4.582, 4.728] V, inside the SoM 4.2-5.0 V input window (PWR-5 re-centred "
    "BELOW 5 V). LCSC C23061.",
    "datasheet")

FB_BOTTOM = register("power_som.fb_bottom", "13k", "ohm",
                     "FB divider bottom — see power_som.fb_top for the "
                     "derivation. LCSC C22797.",
                     "datasheet")

FF_CAP = register("power_som.ff_cap", "22p", "F",
                  "CFF across the FB top (SNVSBD5D 9.2.2.10). LCSC C1653.",
                  "datasheet")

FF_SERIES_R = register(
    "power_som.ff_series_r", "1k", "ohm",
    "RFF series damp for the feedforward cap (SNVSBD5D 9.2.2.10, applicable "
    "because VOUT 4.65 V < 14 V). LCSC C21190.",
    "datasheet")

PG_LED_R = register("power_som.pg_led_r", "1k", "ohm",
                    "KT-0603R power-good LED ballast, ~3 mA. LCSC C21190.",
                    "datasheet")

EN_BYPASS = register("power_som.en_bypass", "100n", "F",
                     "EN node bypass for the PWR-1 clamp. LCSC C14663.",
                     "datasheet")

LOCAL_DRAW_A = register(
    "power_som.local_draw", 0.004, "A",
    "This sheet owns only U4's OWN local load: PG LED (~3 mA) + FB divider "
    "(60 uA). The ~2 A SoM MODULE draw is declared by som_conn_gen on J1 where "
    "the module consumes +5V_SOM; the gate sums draws across all sheets.",
    "policy")


def circuit() -> Circuit:
    c = Circuit("power_som",
                "Power: +VIN -> +5V_SOM always-on buck")

    # EN/SYNC is strapped on by the PWR-1 series-R + zener clamp, NOT a bring-up
    # port: +5V_SOM must be alive pre-DIP or the SC cannot negotiate PD at all.
    c.use_part(BUCK_PART, ref="U4")
    c.net("+VIN_SYS", "U4.8", "U4.12")
    c.net("GND", "U4.9", "U4.11", "U4.3")
    c.part("R12", "Device:R", EN_SERIES_R, R_FP, LCSC="C25804")
    c.part("D5", "Device:D_Zener", EN_ZENER, DZ_FP, LCSC="C85181")
    c.part("C20", "Device:C", EN_BYPASS, C0603, LCSC="C14663")
    c.net("+VIN_SYS", "R12.1")
    c.net("EN_5V_SOM", "U4.7", "R12.2", "D5.1", "C20.1")
    c.net("GND", "D5.2", "C20.2")
    for ref, val, fp, lcsc in (("C14", INPUT_HF, C0603, "C14663"),
                               ("C25", INPUT_HF, C0603, "C14663"),
                               ("C15", INPUT_BULK, C1206, "C13585"),
                               ("C16", INPUT_BULK, C1206, "C13585")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN_SYS", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("C22", "Device:C", VCC_BYPASS, C0603, LCSC="C15849")
    c.net("U4_VCC", "U4.2", "C22.1")
    c.net("GND", "C22.2")
    c.part("R17", "Device:R", BIAS_SERIES_R, R_FP, LCSC="C22859")
    c.net("+5V_SOM", "R17.1")
    c.part("C23", "Device:C", BIAS_BYPASS, C0603, LCSC="C15849")
    c.net("BIAS_5V_SOM", "U4.1", "R17.2", "C23.1")
    c.net("GND", "C23.2")
    c.part("R18", "Device:R", RT_R, R_FP, LCSC="C31850")
    c.net("RT_5V_SOM", "U4.6", "R18.1")
    c.net("GND", "R18.2")
    c.part("C17", "Device:C", BOOT_CAP, C0603, LCSC="C14663")
    c.net("BOOT_5V_SOM", "U4.14", "U4.13", "C17.1")
    c.part("L3", "Device:L", INDUCTOR, L_FP, LCSC="C37429")
    c.net("SW_5V_SOM", "U4.10", "C17.2", "L3.1")
    c.net("+5V_SOM", "L3.2")
    for ref in ("C18", "C19"):
        c.part(ref, "Device:C", OUTPUT_BULK, C0805, LCSC="C45783")
        c.net("+5V_SOM", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("R14", "Device:R", FB_TOP, R_FP, LCSC="C23061")
    c.part("R15", "Device:R", FB_BOTTOM, R_FP, LCSC="C22797")
    c.net("+5V_SOM", "R14.1")
    c.net("FB_5V_SOM", "U4.4", "R14.2", "R15.1")
    c.net("GND", "R15.2")
    c.part("C21", "Device:C", FF_CAP, C0603, LCSC="C1653")
    c.part("R19", "Device:R", FF_SERIES_R, R_FP, LCSC="C21190")
    c.net("+5V_SOM", "C21.1")
    c.net("CFF_5V_SOM", "C21.2", "R19.1")
    c.net("FB_5V_SOM", "R19.2")
    c.part("D4", "Device:LED", "red", LED_FP, LCSC="C2286")
    c.part("R16", "Device:R", PG_LED_R, R_FP, LCSC="C21190")
    c.net("+5V_SOM", "D4.2")
    c.net("PG_5V_SOM", "D4.1", "R16.1")
    c.net("GND", "R16.2")
    c.nc("U4.5")

    c.testpoint("+5V_SOM")
    c.draws("+5V_SOM", LOCAL_DRAW_A,
            "PG LED (KT-0603R + 1k, ~3 mA) + FB divider 60 uA "
            "(SoM module load declared on som_j1)")
    return c
