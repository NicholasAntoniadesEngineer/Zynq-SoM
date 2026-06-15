"""usb_jtag_connector — USB-C UFP receptacle + ESD feeding the CH347T bridge.

Stream-C C1, the connector half (the carrier's "connectors get their own sheet"
idiom — the twin of usb_uart_connector for the CP2102N). A USB 2.0 device-role
(UFP) USB-C receptacle supplies the CH347T USB-JTAG/UART bridge (usb_jtag.py)
over a protected data pair + its own 5 V VBUS. Splitting the receptacle off keeps
neither sheet dense enough to defeat the placer's escape-lane router (the CH347T
+ crystal + LDO + buffer alone is already a busy sheet).

Publishes the bridge's interface as same-named PORTs / a rail:
  - +5V_DBG        : the receptacle 5 V VBUS (the bridge's self-powered island
                     source; a POWER rail so it merges by name onto usb_jtag's
                     AP2112K LDO input — the bridge is alive only with the cable
                     plugged, constraint C1).
  - DBG_USB_DP / DBG_USB_DM : the USB 2.0 HS data pair (90R diff) after ESD.

DEVICE-role (UFP) Type-C — the CC pins carry 5.1k Rd PULLDOWNS to GND (NOT a
host's 56k Rp): this tells the host to apply VBUS. USB 2.0 on a Type-C device
shorts the two flip-orientation contacts of each data line (DP1=DP2, DN1=DN2)
so the cable works either way up. SBU1/2 unused on a USB2 debug link -> NC.
Shell (EH) -> CHASSIS_GND.

ESD — the debug port mates an EXTERNAL cable, so the data pair runs through a
USBLC6-2SC6 low-capacitance array (the carrier-standard part + the 1<->6 / 3<->4
pass-through idiom as usbc_otg / usb_uart_connector): connector-side DP/DM on
U1.1/U1.3, the protected pair (-> the bridge) on U1.6/U1.4, VBUS clamp ref on
U1.5 (<=5.25 V), GND on U1.2. The CH347 UD+/UD- take the bus directly (its DS
forbids a SERIES R on the data lines); the USBLC6 is a SHUNT array, so it adds
no series element — only the ~3.5 pF clamp tap. LAW-0 honoured.

Parts (live-verified on the JLC parts API 2026-06-15):
  - TYPE-C-31-M-12  C165948 (183,962) — the carrier-standard USB-C receptacle.
  - USBLC6-2SC6     C7519   (37,680) — the carrier-standard USB data ESD array.
  - 5.1k Rd x2      C23186  (UNI-ROYAL 0603 5%, JLC Basic) — USB-C Rd spec is
                    5.1k +/-20%, so 5% Basic is correct.
  - 10u bulk        C15850  — VBUS bulk/bypass at the receptacle.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_RD = "C23186"     # 5.1k Rd, JLC Basic
LCSC_10U = "C15850"    # 10u 0805 bulk

BRIDGE = "usb_jtag (CH347T bridge)"


def circuit() -> Circuit:
    c = Circuit("usb_jtag_connector",
                "USB-C UFP debug port -> CH347T (VBUS + protected USB pair)")
    c.use_part("TYPE-C-31-M-12", ref="J1")
    c.use_part("USBLC6-2SC6", ref="U1")

    # ---- VBUS: receptacle 5 V (both stacked pads) -> ESD clamp ref + a 10u
    # bulk; published as +5V_DBG, the bridge's self-powered island source.
    c.part("C1", "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+5V_DBG", "J1.VBUS", "U1.5", "C1.1")    # U1.5 = VBUS clamp ref
    c.net("GND", "C1.2")

    # ---- data pair through the ESD array (1<->6, 3<->4 pass-through), the
    # Type-C flip pairs shorted for USB 2.0 (works either orientation)
    c.net("DBG_USB_DP_CONN", "J1.DP1", "J1.DP2", "U1.1")
    c.net("DBG_USB_DM_CONN", "J1.DN1", "J1.DN2", "U1.3")
    c.port("DBG_USB_DP", "U1.6")                   # protected pair -> the bridge
    c.port("DBG_USB_DM", "U1.4")
    c.port_type("DBG_USB_DP", kind="usb_hs_pair", pair_with="DBG_USB_DM",
                expect=BRIDGE)
    c.net("GND", "U1.2")

    # ---- CC: 5.1k Rd pulldowns on BOTH CC pins = USB device/UFP role
    for ref, cc in (("R1", "J1.CC1"), ("R2", "J1.CC2")):
        c.part(ref, "Device:R", "5.1k", R0603, LCSC=LCSC_RD)
        c.net(f"DBG_{ref}_CC", f"{ref}.1", cc)
        c.net("GND", f"{ref}.2")

    # ---- shield / unused
    c.net("CHASSIS_GND", "J1.EH")                   # all four shell pads
    c.net("GND", "J1.GND")                          # both stacked GND pads
    c.nc("J1.SBU1", "J1.SBU2")                      # SBU unused on a USB2 link

    # power-tree: a UFP/device port — it SINKS, it does not source VBUS. The
    # 5 V it brings in (+5V_DBG) is the debug cable's own supply (an external
    # host source); the bridge's LDO load is declared on usb_jtag.
    c.testpoint("+5V_DBG")                          # the debug-USB VBUS rail
    return c
