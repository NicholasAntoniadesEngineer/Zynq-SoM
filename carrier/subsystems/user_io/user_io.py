from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

BRINGUP = "bringup (gated +3V3_USER_LED rail, stage 2)"
J2_MAP = "som_j2_connector"

R_HIGH_VF = register(
    "user_io.led_r_high_vf", "200R", "ohm",
    "Ballast for the three high-Vf colours (green C12624 / blue C2288 / white "
    "C2290, Vf ~3.1 V). The rail is only 3.3 V, so the drop across the ballast "
    "is 3.3 - Vf: on 1k they would draw (3.3-3.1)/1k = 0.2 mA and be invisible. "
    "200R gives ~1 mA at the 3.1 V corner up to 3.5 mA at the white 2.6 V "
    "corner, never over the 5 mA LED rating. LCSC C8218 (audit io_misc-1).",
    "datasheet")

R_RED = register(
    "user_io.led_r_red", "1k", "ohm",
    "Red (Vf ~1.8-2.4 V) has ~1.3 V of headroom, so 1k gives ~1.3 mA. "
    "LCSC C21190.",
    "datasheet")

BUTTON_PULLUP = register(
    "user_io.button_pullup", "10k", "ohm",
    "Pulls the active-low tacts to the UNGATED +3V3 (= the VCCO_13 level) so "
    "they read correctly whenever the PL is alive, independent of the LED rail "
    "gate. LCSC C25804.",
    "datasheet")

LED_RAIL_HF = register("user_io.led_rail_hf", "100n", "F",
                       "Bypass on the gated LED rail. LCSC C14663.",
                       "datasheet")

LED_DRAW_A = register(
    "user_io.led_draw", 0.012, "A",
    "Red ~1.3 mA (1k) + three high-Vf colours up to ~3.5 mA each (200R, "
    "worst-low Vf corner) -> ~12 mA worst case.",
    "datasheet")

BUTTON_DRAW_A = register("user_io.button_draw", 0.002, "A",
                         "Four 10k button pull-ups at ~0.33 mA each when held.",
                         "datasheet")

_R_LO = (R_HIGH_VF, "C8218")
_R_RED = (R_RED, "C21190")

LEDS = [
    ("D1", "red", "C2286", "IO_25_13", _R_RED),
    ("D2", "green", "C12624", "IO_L6_P_13", _R_LO),
    ("D3", "blue", "C2288", "IO_L24_P_13", _R_LO),
    ("D4", "white", "C2290", "IO_L24_N_13", _R_LO),
]
BUTTONS = [
    ("SW1", "IO_L15_P_13"),
    ("SW2", "IO_L19_P_13"),
    ("SW3", "IO_L21_P_13"),
    ("SW4", "IO_L22_P_13"),
]


def circuit() -> Circuit:
    c = Circuit("user_io", "User IO: 4 LEDs (gated rail) + 4 buttons, bank 13")

    # LEDs are active-low sinks: anode on the gated rail, cathode through the
    # ballast to the PL pin, so the gate kills all four whatever the fabric does.
    led_anodes: list[str] = []
    for i, (dref, color, lcsc, net, (rval, rlcsc)) in enumerate(LEDS, start=1):
        rref = f"R{i}"
        c.part(dref, "Device:LED", color, LED_FP, LCSC=lcsc)
        c.part(rref, "Device:R", rval, R0603, LCSC=rlcsc)
        c.net(f"USER_LED{i}_K", f"{dref}.1", f"{rref}.1")
        c.port(net, f"{rref}.2", expect=J2_MAP)
        led_anodes.append(f"{dref}.2")

    c.part("C1", "Device:C", LED_RAIL_HF, C0603, LCSC="C14663")
    c.net("+3V3_USER_LED", *led_anodes, "C1.1")
    c.net("GND", "C1.2")

    for i, (sref, net) in enumerate(BUTTONS, start=5):
        rref = f"R{i}"
        c.use_part("TS-1187A-B-A-B", ref=sref, value="USER")
        c.part(rref, "Device:R", BUTTON_PULLUP, R0603, LCSC="C25804")
        c.port(net, f"{sref}.1", f"{sref}.2", f"{rref}.2", expect=J2_MAP)
        c.net("+3V3", f"{rref}.1")
        c.net("GND", f"{sref}.3", f"{sref}.4")

    c.draws("+3V3_USER_LED", LED_DRAW_A,
            "red ~1.3 mA (1k) + green/blue/white up to ~3.5 mA each (200R)")
    c.draws("+3V3", BUTTON_DRAW_A, "4x button 10k pull-ups when pressed")
    return c
