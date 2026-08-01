from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

AUX_BUS = "board_aux / board_services (the isolated AUX I2C bus)"

RECEPTACLE = register(
    "board_qwiic.receptacle", "ZX-SH1.0-4PWT", "part",
    "Standard 4-pin JST-SH QWIIC / STEMMA-QT receptacle. Pads 1..4 are the "
    "QWIIC standard GND / +3V3 / SDA / SCL looking into the shell; pads 5/6 are "
    "the mounting tabs. Pad-1 location is a pre-fab layout check — see "
    "carrier/README.md.",
    "datasheet")

ESD_ARRAY = register(
    "board_qwiic.esd_array", "USBLC6-2SC6", "part",
    "Low-capacitance ESD array (~3.5 pF/line, fine at 400 kHz) on the "
    "hand-hot-plugged SDA/SCL, using the 1<->6 / 3<->4 passthrough idiom shared "
    "with usbc_otg and usb_uart.",
    "datasheet")

CLAMP_RAIL = register(
    "board_qwiic.clamp_rail", "+3V3", "net",
    "The clamp reference is the ALWAYS-ON +3V3, not the gated +3V3_AUX. The "
    "USBLC6 is passive (I/O diodes reverse-biased normally), so referencing "
    "+3V3 draws ~0 and never back-feeds the gated rail, and the clamp stays "
    "valid in the most ESD-exposed state: a module hot-plugged while the "
    "connector rail is OFF. Connector POWER (J1.2) stays gated (C1).",
    "policy")

I2C_SPEED_HZ = register("board_qwiic.i2c_speed", 400_000, "Hz",
                        "Fast-mode AUX_I2C.", "datasheet")

MODULE_DRAW_A = register("board_qwiic.module_draw", 0.200, "A",
                         "External QWIIC module headroom on the gated rail, "
                         "under the board_aux SY6280 523 mA limit.",
                         "policy")


def circuit() -> Circuit:
    c = Circuit("board_qwiic",
                "QWIIC / STEMMA-QT expansion connector + USBLC6 ESD array")

    c.use_part(RECEPTACLE, ref="J1")
    c.net("GND", "J1.1")
    c.net("+3V3_AUX", "J1.2")
    c.net("GND", "J1.5", "J1.6")

    c.use_part(ESD_ARRAY, ref="U1")
    c.net("QWIIC_SDA", "J1.3", "U1.1")
    c.net("QWIIC_SCL", "J1.4", "U1.3")
    c.port("AUX_I2C_SDA", "U1.6", kind="i2c", role="sda", bus="AUX_I2C",
           speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.port("AUX_I2C_SCL", "U1.4", kind="i2c", role="scl", bus="AUX_I2C",
           speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.net(CLAMP_RAIL, "U1.5")
    c.net("GND", "U1.2")

    c.draws("+3V3_AUX", MODULE_DRAW_A, "QWIIC external module budget (200 mA)")
    return c
