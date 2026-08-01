from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    OTG_CC_RP,
    OTG_ENABLE_PULLDOWN,
    OTG_FAULT_PULLUP,
    OTG_ID_STRAP,
    OTG_INPUT_BYPASS,
    OTG_VBUS_BULK,
    OTG_VBUS_MLCC,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100K = "C25803"
LCSC_BYPASS = "C14663"
LCSC_VBUS_MLCC = "C45783"
LCSC_CC_RP = "C23206"
LCSC_ID_STRAP = "C21190"

RAILS = ("+VBUS_SUPPLY", "+VDD_LOGIC", "GND", "CHASSIS_GND")
PORTS = ("USB_DP", "USB_DM", "VBUS", "VBUS_EN", "FLT_N", "USB_ID")
INTERFACE = RAILS + PORTS

DRAWS_VBUS_A = 0.500
DRAWS_VBUS_NOTE = ("downstream USB device budget, TPS2051C current-limited")
DRAWS_FLT_A = 0.0005
DRAWS_FLT_NOTE = ("FLT# 100k pull-up on the logic rail")

RAIL_WORST_V = {"+VBUS_SUPPLY": 5.0, "+VDD_LOGIC": 3.3, "GND": 0.0,
                "CHASSIS_GND": 0.0, "VBUS": 5.0}

CC_PINS = (("R1", "J2.CC1"), ("R2", "J2.CC2"))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    c = Circuit("usbc_otg", "USB 2.0 HS OTG port (Type-C, host)")
    c.use_part("TYPE-C-31-M-12", ref="J2")
    c.use_part("TPS2051CDBVR", ref="U1")
    c.use_part("USBLC6-2SC6", ref="U2")

    c.net("+VBUS_SUPPLY", "U1.IN")
    c.port("VBUS", "U1.OUT", "J2.VBUS")
    c.part("R5", "Device:R", OTG_ENABLE_PULLDOWN, R0603, LCSC=LCSC_100K)
    c.port("VBUS_EN", "U1.EN(EN#)", "R5.1", **meta.expect_kw("VBUS_EN"))
    c.net("GND", "U1.GND", "R5.2")
    c.part("R3", "Device:R", OTG_FAULT_PULLUP, R0603, LCSC=LCSC_100K)
    c.port("FLT_N", "U1.FLT#", "R3.2", **meta.expect_kw("FLT_N"))
    c.net("+VDD_LOGIC", "R3.1")
    for cap in c.decouple("U1.IN", OTG_INPUT_BYPASS):
        cap.fields["LCSC"] = LCSC_BYPASS
    c.part("C2", "Device:C", OTG_VBUS_MLCC, C0805, LCSC=LCSC_VBUS_MLCC)
    c.net("VBUS", "C2.1")
    c.net("GND", "C2.2")
    # Pad 1 = + (silk marker by the left pad), pad 2 = -.
    cblk = c.use_part("RVT1C101M0605_100UF_16V", ref="C3",
                      value=OTG_VBUS_BULK)
    c.net("VBUS", f"{cblk.ref}.1")
    c.net("GND", f"{cblk.ref}.2")

    c.net("USBC_DP_CONN", "J2.DP1", "J2.DP2", "U2.1")
    c.net("USBC_DM_CONN", "J2.DN1", "J2.DN2", "U2.3")
    c.port("USB_DP", "U2.6", **meta.expect_kw("USB_DP"))
    c.port("USB_DM", "U2.4", **meta.expect_kw("USB_DM"))
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM")
    c.net("VBUS", "U2.5")
    c.net("GND", "U2.2")

    for ref, cc in CC_PINS:
        c.part(ref, "Device:R", OTG_CC_RP, R0603, LCSC=LCSC_CC_RP)
        c.net("VBUS", f"{ref}.1")
        c.net(f"USBC_{ref}_CC", f"{ref}.2", cc)

    c.part("R4", "Device:R", OTG_ID_STRAP, R0603, LCSC=LCSC_ID_STRAP)
    c.port("USB_ID", "R4.1", **meta.expect_kw("USB_ID"))
    c.net("GND", "R4.2")

    c.net("CHASSIS_GND", "J2.EH")
    c.net("GND", "J2.GND")
    c.nc("J2.SBU1", "J2.SBU2")

    c.testpoint("VBUS_EN")

    c.draws("+VBUS_SUPPLY", DRAWS_VBUS_A, meta.note("draws_vbus", DRAWS_VBUS_NOTE))
    c.draws("+VDD_LOGIC", DRAWS_FLT_A, meta.note("draws_flt", DRAWS_FLT_NOTE))

    return meta.finish(c)
