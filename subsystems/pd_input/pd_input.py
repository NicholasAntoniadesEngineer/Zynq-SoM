from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    PD_INPUT_DVDT_CAP,
    PD_INPUT_FAULT_PULL,
    PD_INPUT_FUSED_BULK,
    PD_INPUT_ILIM_SET,
    PD_INPUT_INLET_BYPASS,
    PD_INPUT_OVP_BOTTOM,
    PD_INPUT_OVP_TOP,
)

C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
TVS_FP = "Diode_SMD:D_SMB"

LCSC_INLET_BYPASS = "C14663"
LCSC_TVS = "C10214"
LCSC_100K = "C25803"
LCSC_OVP_BOTTOM = "C188263"
LCSC_ILIM = "C23186"
LCSC_DVDT = "C1622"
LCSC_FUSED_BULK = "C596319"

RAILS = ("+VBUS_CONN", "+VBUS_OUT", "+VDD_LOGIC", "GND", "CHASSIS_GND")
PORTS = ("CC1", "CC2", "USB_D_P", "USB_D_N", "FLT_N")
INTERFACE = RAILS + PORTS

DRAWS_NOTE = ("USB-C PD inlet: sources +VBUS_OUT through the eFuse; the FLT# "
              "pull-up + USBLC6 clamp draw is <0.5 mA off +VDD_LOGIC")

RAIL_WORST_V = {
    "+VBUS_CONN": 21.0, "+VBUS_OUT": 21.0, "+VDD_LOGIC": 3.3,
    "GND": 0.0, "CHASSIS_GND": 0.0,
}


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    c = Circuit("pd_input", "Power inlet: USB-C PD 20V/3A + TPS26631 eFuse")
    c.use_part("TYPE-C-31-M-12", ref="J1")
    c.use_part("TPS26631PWPR", ref="U1")
    c.use_part("USBLC6-2SC6", ref="U2")

    c.part("C1", "Device:C", PD_INPUT_INLET_BYPASS, C0603,
           LCSC=LCSC_INLET_BYPASS)
    c.part("D1", "Device:D_Zener", "SMBJ22A", TVS_FP, LCSC=LCSC_TVS)
    c.net("+VBUS_CONN", "J1.VBUS", "C1.1", "D1.1",
          "U1.IN", "U1.IN_SYS", "U1.UVLO")
    c.net("GND", "J1.GND", "C1.2", "D1.2")
    c.nc("U1.B_GATE", "U1.DRV")

    c.part("R3", "Device:R", PD_INPUT_OVP_TOP, R0603, LCSC=LCSC_100K)
    c.part("R4", "Device:R", PD_INPUT_OVP_BOTTOM, R0603, LCSC=LCSC_OVP_BOTTOM)
    c.net("PD_OVP_SET", "U1.OVP", "R3.2", "R4.1")
    c.net("+VBUS_CONN", "R3.1")
    c.part("R5", "Device:R", PD_INPUT_ILIM_SET, R0603, LCSC=LCSC_ILIM)
    c.net("PD_ILIM_SET", "U1.ILIM", "R5.1")
    c.part("C3", "Device:C", PD_INPUT_DVDT_CAP, C0603, LCSC=LCSC_DVDT)
    c.net("PD_DVDT", "U1.dVdT", "C3.1")
    c.net("GND", "U1.GND", "U1.EP", "U1.MODE",
          "U1.PGTH",
          "R4.2", "R5.2", "C3.2")
    c.nc("U1.SHDN#", "U1.IMON", "U1.PGOOD")
    c.part("R6", "Device:R", PD_INPUT_FAULT_PULL, R0603, LCSC=LCSC_100K)
    c.port("FLT_N", "U1.FLT#", "R6.2", **meta.expect_kw("FLT_N"))
    c.net("+VDD_LOGIC", "R6.1")

    c.part("C2", "Device:C", PD_INPUT_FUSED_BULK, C1210, LCSC=LCSC_FUSED_BULK)
    c.net("+VBUS_OUT", "U1.OUT", "C2.1")
    c.net("GND", "C2.2")

    c.port("CC1", "J1.CC1")
    c.port("CC2", "J1.CC2")

    c.net("PD_USB_DP_CONN", "J1.DP1", "J1.DP2", "U2.1")
    c.net("PD_USB_DN_CONN", "J1.DN1", "J1.DN2", "U2.3")
    c.port("USB_D_P", "U2.6")
    c.port("USB_D_N", "U2.4")
    c.port_type("USB_D_P", kind="usb_hs_pair", pair_with="USB_D_N")
    # The USBLC6 clamp ref MUST be +VDD_LOGIC: on the 20 V inlet VBUS its
    # internal TVS (~5.25 V standoff) sits in continuous avalanche.
    c.net("+VDD_LOGIC", "U2.5")
    c.net("GND", "U2.2")

    c.nc("J1.SBU1", "J1.SBU2")
    c.net("CHASSIS_GND", "J1.EH")

    c.testpoint("+VBUS_CONN")
    c.testpoint("+VBUS_OUT")
    c.waive_tp("CHASSIS_GND", "chassis island is probeable at every "
               "connector shell tab (USB-C/HDMI/magjack); no pad needed")

    _ = meta.note("draws", DRAWS_NOTE)
    return meta.finish(c)
