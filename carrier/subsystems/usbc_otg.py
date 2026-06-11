"""usbc_otg — USB 2.0 High-Speed OTG port (USB-C receptacle, host-capable).

Reference circuit: TYPE-C-31-M-12 receptacle -> USBLC6-2SC6 ESD array on the
data pair -> SoM USB HS PHY (contract nets USB_D+ / USB_D-). VBUS is sourced
by a TPS2051C power switch from the bring-up-gated +5V_USB rail, enabled by
the SoM's VBUS_OUT_EN (contract J1.38) with the fault flag pulled up and
ported. CC1/CC2 carry 56k Rp pull-ups to VBUS advertising default-USB host
power; USB_ID (contract J1.20) is strapped low through 1k = host role for
this port (the FS+PD Type-C is the device/dual-role port).

AUTHORING V2 reference sheet: actives come from parts/ via use_part() (no
inline lib ids / footprints / LCSC for generated parts) and connect by pin
NAME — "J2.VBUS" nets BOTH stacked VBUS pads, exactly like the symbol.
"""

from __future__ import annotations

from schgen.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

J1_MAP = "som_j1_connector (STM32 GPIO function map)"


def circuit() -> Circuit:
    c = Circuit("usbc_otg", "USB 2.0 HS OTG port (Type-C, host)")
    j2 = c.use_part("TYPE-C-31-M-12", ref="J2")
    u1 = c.use_part("TPS2051CDBVR", ref="U1")
    u2 = c.use_part("USBLC6-2SC6", ref="U2")

    # ---- VBUS: +5V_USB -> TPS2051 -> connector VBUS (= SoM sense USB_VBUS)
    # +5V_USB is the bring-up-gated module rail (SY6280 on the bringup
    # sheet): a POWER net with its own power symbol, like +3V3_HDMI_TX.
    c.net("+5V_USB", "U1.IN")
    c.port("USB_VBUS", "U1.OUT", "J2.VBUS")     # OUT + sense (both pads)
    c.port("VBUS_OUT_EN", "U1.EN(EN#)", expect=J1_MAP)
    c.net("GND", "U1.GND")
    # fault flag: open-drain, pulled to the gated rail, reported to the SoM
    c.part("R3", "Device:R", "100k", R0603, LCSC="C25803")
    c.port("USBOTG_FLT_N", "U1.FLT#", "R3.2", expect=J1_MAP)
    c.net("+5V_USB", "R3.1")
    # input bypass + VBUS bulk per TPS2051 datasheet
    for cap in c.decouple("U1.IN", "100n"):     # C14663 Basic, 20.6M stock
        cap.fields["LCSC"] = "C14663"
    c.part("C2", "Device:C", "22u", C0805, LCSC="C45783")
    c.net("USB_VBUS", "C2.1")
    c.net("GND", "C2.2")

    # ---- data pair through the ESD array (pass-through 1<->6, 3<->4)
    c.net("USBC_DP_CONN", "J2.DP1", "J2.DP2", "U2.1")
    c.net("USBC_DM_CONN", "J2.DN1", "J2.DN2", "U2.3")
    c.port("USB_D+", "U2.6")
    c.port("USB_D-", "U2.4")
    c.port_type("USB_D+", kind="usb_hs_pair", pair_with="USB_D-")
    c.net("USB_VBUS", "U2.5")
    c.net("GND", "U2.2")

    # ---- CC host advertising: 56k Rp to VBUS (default USB power)
    for ref, cc in (("R1", "J2.CC1"), ("R2", "J2.CC2")):
        # 56k 1% 0603 = 0603WAF5602T5E, C23206 — live-verified 2026-06-11:
        # Basic, stock 289,495
        c.part(ref, "Device:R", "56k", R0603, LCSC="C23206")
        c.net("USB_VBUS", f"{ref}.1")
        c.net(f"USBC_{ref}_CC", f"{ref}.2", cc)

    # ---- OTG ID strap: USB_ID (contract J1.20) through 1k to GND = HOST
    # role for this port (the FS+PD Type-C is the device/dual-role port).
    c.part("R4", "Device:R", "1k", R0603, LCSC="C21190")
    c.port("USB_ID", "R4.1", expect=J1_MAP)
    c.net("GND", "R4.2")

    # ---- shield / unused
    c.net("CHASSIS_GND", "J2.EH")               # all four shell pads by NAME
    c.net("GND", "J2.GND")                      # both stacked GND pads
    c.nc("J2.SBU1", "J2.SBU2")                  # SBU unused on USB2 port
    return c
