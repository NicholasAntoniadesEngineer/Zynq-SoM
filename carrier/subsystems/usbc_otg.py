"""usbc_otg — USB 2.0 High-Speed OTG port (USB-C receptacle, host-capable).

Reference circuit: TYPE-C-31-M-12 receptacle -> USBLC6-2SC6 ESD array on the
data pair -> SoM USB HS PHY (contract nets USB_D+ / USB_D-). VBUS is sourced
by a TPS2051C power switch from the bring-up-gated +5V_USB rail, enabled by
the SoM's VBUS_OUT_EN (contract J1.38) with the fault flag pulled up and
ported. CC1/CC2 carry 56k Rp pull-ups to VBUS advertising default-USB host
power; USB_ID (contract J1.20) is strapped low through 1k = host role for
this port (the FS+PD Type-C is the device/dual-role port).

Parts come from parts/<MPN>/ folders (generated from LCSC).
"""

from __future__ import annotations

from schgen.model import Circuit

TYPEC_LIB = "TYPE-C-31-M-12:TYPE-C-31-M-12"
TYPEC_FP = "TYPE-C-31-M-12:TYPE-C-31-M-12"
TPS_LIB = "TPS2051CDBVR:TPS2051CDBVR"
TPS_FP = "TPS2051CDBVR:TPS2051CDBVR"
ESD_LIB = "USBLC6-2SC6:USBLC6-2SC6"
ESD_FP = "USBLC6-2SC6:USBLC6-2SC6"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

BRINGUP = "bringup (gated +5V_USB rail)"
J1_MAP = "som_j1_connector (STM32 GPIO function map)"


def circuit() -> Circuit:
    c = Circuit("usbc_otg", "USB 2.0 HS OTG port (Type-C, host)")
    c.part("J2", TYPEC_LIB, "TYPE-C-31-M-12", TYPEC_FP, LCSC="C165948")
    c.part("U1", TPS_LIB, "TPS2051CDBVR", TPS_FP, LCSC="C129581")
    c.part("U2", ESD_LIB, "USBLC6-2SC6", ESD_FP, LCSC="C7519")

    # ---- VBUS: +5V_USB -> TPS2051 -> connector VBUS (= SoM sense USB_VBUS)
    c.port("+5V_USB", "U1.5", expect=BRINGUP)               # IN (gated rail)
    vbus = c.port("USB_VBUS", "U1.1", "J2.A4B9", "J2.B4A9") # OUT + sense
    c.port("VBUS_OUT_EN", "U1.4", expect=J1_MAP)            # EN from SoM
    c.net("GND", "U1.2")
    # fault flag: open-drain, pulled to the gated rail, reported to the SoM
    c.part("R3", "Device:R", "100k", R0603, LCSC="C25803")
    c.port("USBOTG_FLT_N", "U1.3", "R3.2", expect=J1_MAP)
    c.net("+5V_USB", "R3.1")
    # input bypass + VBUS bulk per TPS2051 datasheet
    c.decouple("U1.5", "100n")
    c.part("C2", "Device:C", "22u", C0805, LCSC="C45783")
    c.net("USB_VBUS", "C2.1")
    c.net("GND", "C2.2")

    # ---- data pair through the ESD array (pass-through 1<->6, 3<->4)
    c.net("USBC_DP_CONN", "J2.A6", "J2.B6", "U2.1")
    c.net("USBC_DM_CONN", "J2.A7", "J2.B7", "U2.3")
    dp = c.port("USB_D+", "U2.6")
    dm = c.port("USB_D-", "U2.4")
    c.port_type("USB_D+", kind="usb_hs_pair", pair_with="USB_D-")
    c.net("USB_VBUS", "U2.5")
    c.net("GND", "U2.2")

    # ---- CC host advertising: 56k Rp to VBUS (default USB power)
    for ref, cc in (("R1", "J2.A5"), ("R2", "J2.B5")):
        c.part(ref, "Device:R", "56k", R0603)   # TODO LCSC: verify 56k 0603
        c.net("USB_VBUS", f"{ref}.1")
        c.net(f"USBC_{ref}_CC", f"{ref}.2", cc)

    # OTG ID strap (host role) lives SoM-side / on the J1 sheet; the contract
    # net USB_ID binds there. (Engine TODO queued: generic port-strap chain.)

    # ---- shield / unused
    c.net("CHASSIS_GND", "J2.1", "J2.2", "J2.3", "J2.4")
    c.net("GND", "J2.A1B12", "J2.B1A12")
    c.nc("J2.A8", "J2.B8")                       # SBU unused on USB2 port
    return c
