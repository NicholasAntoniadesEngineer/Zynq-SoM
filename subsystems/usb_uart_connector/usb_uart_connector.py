from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import UART_CONN_CC_RD, UART_CONN_VBUS_BULK

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_RD = "C23186"
LCSC_10U = "C15850"

RAILS = ("GND", "CHASSIS_GND")
PORTS = ("VBUS", "USB_DP", "USB_DM")
INTERFACE = RAILS + PORTS

RAIL_WORST_V = {"GND": 0.0, "CHASSIS_GND": 0.0, "VBUS": 5.25}

CC_PINS = (("R1", "J1.CC1"), ("R2", "J1.CC2"))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    c = Circuit("usb_uart_connector", "USB-C UFP console port -> CP2102N")
    c.use_part("TYPE-C-31-M-12", ref="J1")
    c.use_part("USBLC6-2SC6", ref="U1")

    c.part("C1", "Device:C", UART_CONN_VBUS_BULK, C0805, LCSC=LCSC_10U)
    c.port("VBUS", "J1.VBUS", "U1.5", "C1.1", **meta.expect_kw("VBUS"))
    c.net("GND", "C1.2")

    c.net("USB_UART_DP_CONN", "J1.DP1", "J1.DP2", "U1.1")
    c.net("USB_UART_DM_CONN", "J1.DN1", "J1.DN2", "U1.3")
    c.port("USB_DP", "U1.6", **meta.expect_kw("USB_DP"))
    c.port("USB_DM", "U1.4", **meta.expect_kw("USB_DM"))
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM")
    c.net("GND", "U1.2")

    for ref, cc in CC_PINS:
        c.part(ref, "Device:R", UART_CONN_CC_RD, R0603, LCSC=LCSC_RD)
        c.net(f"USB_UART_{ref}_CC", f"{ref}.1", cc)
        c.net("GND", f"{ref}.2")

    c.net("CHASSIS_GND", "J1.EH")
    c.net("GND", "J1.GND")
    c.nc("J1.SBU1", "J1.SBU2")

    return meta.finish(c)
