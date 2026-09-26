from __future__ import annotations

from carrier.basis import PROJECT, register
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
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'user_io', __file__)
