from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_13K = "C22797"
LCSC_6K8 = "C23212"
LCSC_330R = "C23138"
LCSC_1K = "C21190"
LCSC_100N = "C14663"
LCSC_RED = "C2286"
LCSC_YEL = "C157740"

EXPECT_EN = "bringup_en (EN AND-gate cells, dossier section 3.2)"
J12_MAP = "som_j1_j2 bank-33 PL pin assignment (P3 linker)"

ISET_523MA = register(
    "bringup_modules.iset_523ma", "13k", "ohm",
    "SY6280 ILIM = 6800/RSET, so 13k -> 523 mA for the lighter module rails. "
    "LCSC C22797.",
    "datasheet")

ISET_1A = register(
    "bringup_modules.iset_1a", "6.8k", "ohm",
    "SY6280 ILIM = 6800/RSET, so 6.8k -> 1.0 A for the heavier rails (LCD, SD, "
    "USB, LCD_5V). LCSC C23212.",
    "datasheet")

LED_R_3V3 = register("bringup_modules.led_r_3v3", "330R", "ohm",
                     "Status LED on a 3.3 V gated rail: (3.3-2.0)/330R ~= "
                     "3.9 mA (dossier 3.3). LCSC C23138.",
                     "datasheet")

LED_R_5V = register("bringup_modules.led_r_5v", "1k", "ohm",
                    "Status LED on a 5 V gated rail: (5-2)/1k = 3 mA "
                    "(dossier 3.3). LCSC C21190.",
                    "datasheet")

SWITCH_DECAP = register("bringup_modules.switch_decap", "100n", "F",
                        "Local bypass on each SY6280 IN and OUT (dossier 3.2 "
                        "wiring note). LCSC C14663.",
                        "datasheet")

SD_BLEED_R = register(
    "bringup_modules.sd_bleed", "10k", "ohm",
    "ONLY the SD rail gets this. A microSD power-cycle re-init needs VDD below "
    "~0.5 V, but the SY6280 has no quick-output-discharge, so +3V3_SD would "
    "decay only through a possibly-high-Z card and could strand above 0.5 V. "
    "0.33 mA static is far under the 1 A limit and cannot mis-trip (research "
    "R5; audit 2026-06-20). LCSC C25804.",
    "datasheet")

LED_DRAW_3V3_A = register("bringup_modules.led_draw_3v3", 0.004, "A",
                          "Status LED on a 3V3 gated rail, ~3.9 mA rounded up.",
                          "datasheet")

LED_DRAW_5V_A = register("bringup_modules.led_draw_5v", 0.003, "A",
                         "Status LED on the +5V_USB-class gated rail, 3 mA.",
                         "datasheet")

# (module, IN rail, OUT rail, RSET value, RSET LCSC, LED series R, R LCSC)
MODULES = (
    ("HDMI_TX", "+3V3", "+3V3_HDMI_TX", ISET_523MA, LCSC_13K, LED_R_3V3, LCSC_330R),
    ("HDMI_RX", "+3V3", "+3V3_HDMI_RX", ISET_523MA, LCSC_13K, LED_R_3V3, LCSC_330R),
    ("LCD", "+3V3", "+3V3_LCD", ISET_1A, LCSC_6K8, LED_R_3V3, LCSC_330R),
    ("CAM", "+3V3", "+3V3_CAM", ISET_523MA, LCSC_13K, LED_R_3V3, LCSC_330R),
    ("SD", "+3V3", "+3V3_SD", ISET_1A, LCSC_6K8, LED_R_3V3, LCSC_330R),
    ("USB", "+5V", "+5V_USB", ISET_1A, LCSC_6K8, LED_R_5V, LCSC_1K),
    ("PMOD", "+3V3", "+3V3_PMOD", ISET_523MA, LCSC_13K, LED_R_3V3, LCSC_330R),
    ("USER_LED", "+3V3", "+3V3_USER_LED", ISET_523MA, LCSC_13K, LED_R_3V3, LCSC_330R),
    ("HDMI_TX_5V", "+5V", "+5V_HDMI_TX", ISET_523MA, LCSC_13K, LED_R_5V, LCSC_1K),
    ("LCD_5V", "+5V", "+5V_LCD", ISET_1A, LCSC_6K8, LED_R_5V, LCSC_1K),
)


def circuit() -> Circuit:
    c = Circuit("bringup_modules",
                "Bring-up module gates: 10x SY6280 + status/user LEDs")
    for k, (mod, in_rail, out_rail, rset, rset_id, led_r, led_r_id) \
            in enumerate(MODULES):
        u = c.use_part("SY6280AAC", ref=f"U{k + 1}")
        c.net(in_rail, f"{u.ref}.IN")
        c.net(out_rail, f"{u.ref}.OUT")
        c.net("GND", f"{u.ref}.GND")
        c.port(f"EN_{mod}", f"{u.ref}.EN", expect=EXPECT_EN)
        rs = c.part(c.auto_ref("R"), "Device:R", rset, R_FP, LCSC=rset_id)
        c.net(f"BU_ISET_{mod}", f"{u.ref}.ISET", f"{rs.ref}.1")
        c.net("GND", f"{rs.ref}.2")
        for cap in c.decouple(f"{u.ref}.IN", SWITCH_DECAP, footprint=C_FP):
            cap.fields["LCSC"] = LCSC_100N
        for cap in c.decouple(f"{u.ref}.OUT", SWITCH_DECAP, footprint=C_FP):
            cap.fields["LCSC"] = LCSC_100N
        d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP,
                   LCSC=LCSC_RED)
        rl = c.part(c.auto_ref("R"), "Device:R", led_r, R_FP, LCSC=led_r_id)
        c.net(out_rail, f"{d.ref}.2")
        c.net(f"BU_PG_{mod}", f"{d.ref}.1", f"{rl.ref}.1")
        c.net("GND", f"{rl.ref}.2")

    rbleed = c.part(c.auto_ref("R"), "Device:R", SD_BLEED_R, R_FP,
                    LCSC="C25804")
    c.net("+3V3_SD", f"{rbleed.ref}.1")
    c.net("GND", f"{rbleed.ref}.2")

    # Probe each gated rail at its SOURCE: rail-by-rail bring-up needs the meter
    # on this side of the module connector.
    for _mod, _in, out_rail, _rs, _ri, _lr, _li in MODULES:
        c.testpoint(out_rail)

    for _mod, _in, out_rail, _rs, _ri, led_r, _li in MODULES:
        amps = LED_DRAW_3V3_A if led_r == LED_R_3V3 else LED_DRAW_5V_A
        c.draws(out_rail, amps, f"status LED ({led_r}) on the gated output")
    return c
