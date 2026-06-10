"""usb_pd — FUSB302B USB Type-C / Power-Delivery PHY subsystem.

Reference circuit per the onsemi FUSB302B datasheet (and the carrier's
hand-audited usb_pd sheet): VDD bypassed 100n + 10u, VBUS (fed from +VIN)
bypassed 100n, 200p filter caps on each CC line, 4k7 pull-ups to +3V3 on
SDA / SCL / INT_N (INT_N is open-drain). VCONN sourcing is unused by design
-> both VCONN pins are explicit author no-connects.

Stock symbol Interface_USB:FUSB302BMPX (WQFN-14 + EP): stacked duplicate
pins 4 (VDD), 9/15 (GND/EP), 11 (CC1), 14 (CC2) are declared on the same
nets as their visible twins — the netlist gate proves KiCad sees all of them.
"""

from __future__ import annotations

from schgen.model import Circuit

LIB_ID = "Interface_USB:FUSB302BMPX"
FOOTPRINT = "Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm"


def circuit() -> Circuit:
    c = Circuit("usb_pd", "USB-PD: FUSB302B Type-C controller")
    c.part("U1", LIB_ID, "FUSB302BMPX", FOOTPRINT)

    # power
    c.net("+3V3", "U1.3", "U1.4")                 # VDD (+ stacked pin 4)
    c.net("+VIN", "U1.2")                         # VBUS sense, fed from +VIN
    c.net("GND", "U1.8", "U1.9", "U1.15")         # GND + stacked + EP
    c.decouple("U1.3", "100n", "10u")             # C1, C2 on +3V3
    c.decouple("U1.2", "100n")                    # C3 on +VIN

    # Type-C CC lines to the connector (external interface) + 200p filters
    cc1 = c.port("STM32_USB_CC1", "U1.10", "U1.11")
    cc2 = c.port("STM32_USB_CC2", "U1.1", "U1.14")
    for net in (cc1, cc2):
        ref = c.auto_ref("C")
        c.part(ref, "Device:C", "200p")
        c.net(net.name, f"{ref}.1")
        c.net("GND", f"{ref}.2")

    # I2C + interrupt to the STM32, pulled to +3V3. The SoM contract exposes
    # raw STM32_GPIO* names; the generated J1 sheet (wave 3) carries the
    # GPIO->I2C2/INT function map, so these ports are explicitly deferred.
    J1_MAP = "som_j1_connector (wave 3 STM32 GPIO function map)"
    c.port("STM32_I2C2_SDA", "U1.7",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U1.6",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("STM32_FUSB302_INT", "U1.5", expect=J1_MAP)
    c.pullup("U1.7", "4k7", "+3V3")               # R1
    c.pullup("U1.6", "4k7", "+3V3")               # R2
    c.pullup("U1.5", "4k7", "+3V3")               # R3

    # VCONN sourcing unused by design
    c.nc("U1.12", "U1.13")
    return c
