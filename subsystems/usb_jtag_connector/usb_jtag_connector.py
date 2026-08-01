from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import JTAG_CONN_CC_RD, JTAG_CONN_VBUS_BULK

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_RD = "C23186"
LCSC_10U = "C15850"

RAILS = ("+VBUS", "GND", "CHASSIS_GND")
PORTS = ("USB_DP", "USB_DM")
INTERFACE = RAILS + PORTS

CONSUMER = "usb consumer (downstream device)"

RAIL_WORST_V = {"+VBUS": 5.0, "GND": 0.0, "CHASSIS_GND": 0.0}

CC_PINS = (("R1", "J1.CC1"), ("R2", "J1.CC2"))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    c = Circuit("usb_jtag_connector",
                "USB-C UFP debug port -> CH347T (protected)")
    c.use_part("TYPE-C-31-M-12", ref="J1")
    c.use_part("USBLC6-2SC6", ref="U1")

    c.part("C1", "Device:C", JTAG_CONN_VBUS_BULK, C0805, LCSC=LCSC_10U)
    c.net("+VBUS", "J1.VBUS", "U1.5", "C1.1")
    c.net("GND", "C1.2")

    c.net("DBG_USB_DP_CONN", "J1.DP1", "J1.DP2", "U1.1")
    c.net("DBG_USB_DM_CONN", "J1.DN1", "J1.DN2", "U1.3")
    c.port("USB_DP", "U1.6")
    c.port("USB_DM", "U1.4")
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM",
                expect=meta.expects.get("USB_DP", CONSUMER))
    c.net("GND", "U1.2")

    for ref, cc in CC_PINS:
        c.part(ref, "Device:R", JTAG_CONN_CC_RD, R0603, LCSC=LCSC_RD)
        c.net(f"DBG_{ref}_CC", f"{ref}.1", cc)
        c.net("GND", f"{ref}.2")

    c.net("CHASSIS_GND", "J1.EH")
    c.net("GND", "J1.GND")
    c.nc("J1.SBU1", "J1.SBU2")

    c.testpoint("+VBUS")

    return meta.finish(c)
