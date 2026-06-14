"""board_qwiic — QWIIC / STEMMA-QT expansion connector + its ESD array.

The carrier exposes its gated +3V3_AUX rail and the isolated AUX I2C bus on a
standard 4-pin JST-SH (QWIIC) connector so daughter sensor/IO modules hang off
the board. Following the carrier's connectors-get-their-own-sheet idiom
(rj45_connector, usb_uart_connector), the connector and its protection live
here; the EEPROM/RTC/watchdog that share the bus are on board_services and the
gate + isolator on board_aux.

ESD (the board protects EVERY external connector).  QWIIC is hot-plugged by
hand, so its SDA/SCL are clamped at the connector by a USBLC6-2SC6 — the
carrier's standard low-capacitance ESD array (~3.5 pF/line, fine for 400 kHz
I2C), using the same 1<->6 / 3<->4 passthrough idiom as usbc_otg / usb_uart:
the external connector lines sit on U1.1/U1.3, the protected pair that reaches
the isolated bus on U1.6/U1.4, the clamp reference on U1.5 (+3V3_AUX), GND on
U1.2. Because the bus is already behind the board_aux PCA9306 isolator, an ESD
strike here is both clamped AND cut off from the always-on management bus.

QWIIC PAD ORDER — VERIFY AT LAYOUT: pads 1..4 are wired to the QWIIC standard
GND / +3V3 / SDA / SCL (looking into the receptacle); confirm pad 1's location
against the J1 footprint silk before fab, since a swapped power pad would
damage external modules. Pads 5/6 are the shell/mounting tabs -> GND.
"""

from __future__ import annotations

from schgen.model import Circuit

AUX_BUS = "board_aux / board_services (the isolated AUX I2C bus)"


def circuit() -> Circuit:
    c = Circuit("board_qwiic",
                "QWIIC / STEMMA-QT expansion connector + USBLC6 ESD array")

    c.use_part("ZX-SH1.0-4PWT", ref="J1")                # QWIIC receptacle
    c.net("GND", "J1.1")
    c.net("+3V3_AUX", "J1.2")
    c.net("GND", "J1.5", "J1.6")                          # shell/mounting tabs

    c.use_part("USBLC6-2SC6", ref="U1")                  # low-cap ESD array
    c.net("QWIIC_SDA", "J1.3", "U1.1")                   # external SDA
    c.net("QWIIC_SCL", "J1.4", "U1.3")                   # external SCL
    c.port("AUX_I2C_SDA", "U1.6", kind="i2c", role="sda", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)              # protected -> bus
    c.port("AUX_I2C_SCL", "U1.4", kind="i2c", role="scl", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)
    c.net("+3V3_AUX", "U1.5")                             # clamp reference rail
    c.net("GND", "U1.2")

    # power-tree budget: external module headroom on the gated rail
    c.draws("+3V3_AUX", 0.200, "QWIIC external module budget (200 mA)")
    return c
