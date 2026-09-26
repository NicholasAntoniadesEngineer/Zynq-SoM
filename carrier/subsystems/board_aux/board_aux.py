from __future__ import annotations

from carrier.basis import PROJECT, register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_100N = "C14663"
LCSC_4K7 = "C23162"
LCSC_100K = "C25803"
LCSC_13K = "C22797"
LCSC_330R = "C23138"
LCSC_RED = "C2286"

SC_I2C = "STM32_I2C2 management bus (bringup_rails / usb_pd / power_mon)"
AUX_BUS = "board_services (the gated peripherals on the isolated AUX bus)"

ISET_R = register("board_aux.iset", "13k", "ohm",
                  "SY6280 current limit ILIM = 6800/13k = 523 mA, over the "
                  "200 mA QWIIC budget. LCSC C22797.",
                  "datasheet")

EN_PULLDOWN = register(
    "board_aux.en_pulldown", "100k", "ohm",
    "Holds EN_AUX low so the gate is OFF at power-up until a human closes SW1 "
    "pos 1 (constraint C1). LCSC C25803.",
    "datasheet")

DECAP = register("board_aux.decap", "100n", "F",
                 "SY6280 and PCA9306 per-pin bypass. LCSC C14663.", "datasheet")

OUT_BULK = register(
    "board_aux.out_bulk", "10u", "F",
    "Hold-up on the gated +3V3_AUX rail for the 200 mA QWIIC load. The SY6280 "
    "datasheet recommends an output cap and only the 100n was fitted (audit "
    "2026-06-19); its soft-start tolerates 10u. 0805 25 V, LCSC C15850.",
    "datasheet")

LED_BALLAST = register("board_aux.led_ballast", "330R", "ohm",
                       "KT-0603R status LED ballast, ~3.9 mA from +3V3_AUX. "
                       "LCSC C23138.", "datasheet")

ISO_EN_PULLUP = register(
    "board_aux.iso_en_pullup", "100k", "ohm",
    "Ties the PCA9306 EN to +3V3_AUX so the switch OPENS whenever the gated "
    "rail is down — that isolation is what stops the powered-down peripherals "
    "back-powering the always-on trunk through their ESD diodes (LAW 0). "
    "LCSC C25803.",
    "datasheet")

AUX_BUS_PULLUP = register(
    "board_aux.bus_pullup", "4k7", "ohm",
    "AUX-side I2C pulls to the gated rail; the PCA9306 requires pulls on BOTH "
    "sides. LCSC C23162.",
    "datasheet")

I2C_SPEED_HZ = register("board_aux.i2c_speed", 400_000, "Hz",
                        "Fast-mode on both sides of the isolator.", "datasheet")

AUX_DRAW_A = register(
    "board_aux.aux_draw", 0.006, "A",
    "This sheet's own +3V3_AUX load: status LED 3.9 mA + the two 4k7 bus "
    "pull-ups. The peripherals declare their own on board_services.",
    "datasheet")


def circuit() -> Circuit:
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'board_aux', __file__)
