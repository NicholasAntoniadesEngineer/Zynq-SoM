"""usb_uart_connector — USB-C UFP receptacle feeding the CP2102N console.

Wave-2 external console port. A USB 2.0 device-role (UFP) USB-C receptacle
that supplies the CP2102N USB-UART bridge (uart_bridge.py) over a protected
data pair. Type-C chosen for consistency with usbc_otg.py and to reuse the
already-stocked TYPE-C-31-M-12 receptacle in parts/.

Binds the bridge's three deferred wave-2 ports (read VERBATIM from
uart_bridge.py):
  - USB_UART_VBUS : the receptacle 5 V VBUS (bridge senses it through its own
                    22k1/47k5 divider — datasheet self-powered cable-attach)
  - USB_UART_DP / USB_UART_DM : the USB 2.0 HS data pair (90R diff)
Declaring these as same-named PORTs here gives the bridge its peer, so its
`expect="usb_uart_connector (wave 2)"` deferrals resolve to BOUND on both
sheets.

DEVICE-role (UFP) Type-C — the CC pins carry 5.1k Rd PULLDOWNS to GND
(NOT the host port's 56k Rp): this is what tells a source to apply VBUS.
Per CC pin one Rd; the source's Rp + our Rd form the attach divider. USB 2.0
on a Type-C device shorts the two flip-orientation contacts of each data
line (DP1=DP2, DN1=DN2) so the cable works either way up. SBU1/SBU2 are
unused on a USB2 console -> author NC. Shell (EH) -> CHASSIS_GND.

ESD — the console port mates an EXTERNAL cable, so the data pair runs through
a USBLC6-2SC6 low-capacitance TGL/diode array (same part + 1<->6 / 3<->4
passthrough idiom as usbc_otg.py): connector side DP/DM on U1.1/U1.3, the
protected pair (-> the bridge ports) on U1.6/U1.4, VBUS clamp ref on U1.5,
GND on U1.2.

Parts — all live-verified on the JLC parts API 2026-06-13:
  - TYPE-C-31-M-12  C165948 (Korean Hroparts) — reused from parts/, the
    carrier's standard USB-C receptacle (Extended).
  - USBLC6-2SC6     C7519 (ST) — reused from parts/, the carrier's standard
    USB data ESD array (Extended), as on usbc_otg.py.
  - 5.1k Rd x2      0603WAF5101T5E C23186 (UNI-ROYAL 0603 5%) — JLC BASIC,
    stock 4,508,866. USB-C Rd spec is 5.1k +/-20%, so 5% Basic is correct.
"""

from __future__ import annotations

from schgen.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_RD = "C23186"   # 0603WAF5101T5E 5.1k, JLC Basic, stock 4.5M (live 2026-06-13)
LCSC_10U = "C15850"  # 10u 0805, the board-standard bulk cap (used board-wide)


def circuit() -> Circuit:
    c = Circuit("usb_uart_connector", "USB-C UFP console port -> CP2102N")
    j1 = c.use_part("TYPE-C-31-M-12", ref="J1")
    u1 = c.use_part("USBLC6-2SC6", ref="U1")

    # ---- VBUS: receptacle 5 V (both stacked VBUS pads) -> ESD array VBUS
    # clamp ref + the bridge's VBUS-sense port + a 10u bulk/bypass (USB-C UFP
    # VBUS decoupling, Cbus per the spec)
    c.part("C1", "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.port("USB_UART_VBUS", "J1.VBUS", "U1.5", "C1.1")  # peer to bridge VBUS sense
    c.net("GND", "C1.2")

    # ---- data pair through the ESD array (1<->6, 3<->4 passthrough), with
    # the Type-C flip pairs shorted for USB 2.0 (works either orientation)
    c.net("USB_UART_DP_CONN", "J1.DP1", "J1.DP2", "U1.1")
    c.net("USB_UART_DM_CONN", "J1.DN1", "J1.DN2", "U1.3")
    c.port("USB_UART_DP", "U1.6")        # protected pair -> the bridge ports
    c.port("USB_UART_DM", "U1.4")
    c.port_type("USB_UART_DP", kind="usb_hs_pair", pair_with="USB_UART_DM")
    c.net("GND", "U1.2")

    # ---- CC: 5.1k Rd pulldowns to GND on BOTH CC pins = USB device/UFP role
    # (a source's Rp + this Rd advertise attach + sink current; NOT the host
    # port's 56k Rp). One Rd per CC pin per the USB Type-C spec.
    for ref, cc in (("R1", "J1.CC1"), ("R2", "J1.CC2")):
        c.part(ref, "Device:R", "5.1k", R0603, LCSC=LCSC_RD)
        c.net(f"USB_UART_{ref}_CC", f"{ref}.1", cc)
        c.net("GND", f"{ref}.2")

    # ---- shield / unused
    c.net("CHASSIS_GND", "J1.EH")        # all four shell pads by NAME
    c.net("GND", "J1.GND")               # both stacked GND pads
    c.nc("J1.SBU1", "J1.SBU2")           # SBU unused on a USB2 console

    # power-tree budget: this is a UFP/device port — it SINKS, it does not
    # source VBUS; the only +3V3/+5V draw on this sheet is none (the Rd's pull
    # the source's CC, the bridge's own divider senses VBUS). No c.draws.
    return c
