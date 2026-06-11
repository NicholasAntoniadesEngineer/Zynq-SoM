"""pd_input — USB-C PD power inlet: the board's ONLY power entry (GAP #1).

PLAN round-2 locked: USB-C PD ONLY, 20 V / 3 A (60 W), no barrel jack. This
sheet is the receptacle itself; the FUSB302B PD PHY lives on usb_pd (same
nets), and power.py consumes +VIN.

Receptacle: TYPE-C-31-M-12 (LCSC C165948 — LIVE-verified 2026-06-11:
stock 191,682, Extended; LCSC detail API attributes: Current Rating 5 A,
Voltage Rating 20 V, 16 contacts) — adequate margin for the 20 V/3 A
contract. Same part as the OTG port (usbc_otg.py), so one connector reel.

Wiring:
- VBUS (A4B9 + B4A9) -> +VIN, the raw input rail (power.py bucks +
  usb_pd's FUSB302 VBUS sense sit on it board-wide).
- CC1/CC2 -> ports STM32_USB_CC1 / STM32_USB_CC2 — names VERBATIM from
  usb_pd.py and som_interface.json (J1.29/31): FUSB302B terminates CC and
  negotiates; the SoM STM32 reads it over I2C.
- D+/D- (A6/B6, A7/B7 paired for cable flip) -> STM32_USB_D_P/_N (J1.19/21,
  usb_hs_pair): this receptacle is the STM32's device/dual-role FS port
  (usbc_otg.py strap note: "the FS+PD Type-C is the device/dual-role port").
- SBU: author NC. Shell EH 1-4 -> CHASSIS_GND (usbc_otg pattern).

Inlet protection + bulk (LIVE-verified on the JLC parts API 2026-06-11):
- D1 SMBJ22A (C10214, RUILON, stock 4,499, Ext): unidirectional 600 W TVS,
  22 V standoff (> 20 V contract), VBR 24.4-26.9 V, clamp 35.5 V @ 16.9 A —
  hot-plug/surge clamp on VBUS. CC-line ESD intentionally omitted: the
  FUSB302B integrates CC ESD protection and usb_pd adds 200p filters; a
  TPD2EUSB30-class array remains a stuffing option if EMC testing demands.
- C2 10u 50 V X7R 1210 (C596319, YAGEO CC1210KKX7R9BB106, stock 13,618,
  Ext) + C1 100n 50 V (C1591): hot-plug bulk right at the inlet. X7R @ 50 V
  rating chosen for DC-bias honesty on a 20 V rail (the 25 V X5R used
  elsewhere would derate badly).

PD sink-capacitance audit (USB PD r3 / Type-C: a Sink shall present at most
~10 uF effective on VBUS BEFORE an explicit contract — cSnkBulk; up to
100 uF after): this sheet contributes 10 u nominal (~5-7 uF effective at
5 V bias after DC derating) — compliant alone. BOARD-LEVEL HONESTY: +VIN
also carries power.py's un-switched buck input caps (2x 10u C13585 25 V
X5R + 100n) and usb_pd's 100n, so the un-gated pre-contract total is ~30 uF
nominal (~15-20 uF effective at 5 V) — ABOVE the ~10 uF guidance. Most
sources tolerate this (Type-C tSrcInrush margins), but a strict fix is an
inrush-limited path (load switch on +VIN ahead of the bucks) or trimming
power.py's input bulk; flagged for the power-tree budget gate (PLAN round 4).
"""

from __future__ import annotations

from schgen.model import Circuit

TYPEC_LIB = "TYPE-C-31-M-12:TYPE-C-31-M-12"
TYPEC_FP = "TYPE-C-31-M-12:TYPE-C-31-M-12"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
TVS_FP = "Diode_SMD:D_SMB"

USB_PD_SHEET = "usb_pd (FUSB302B CC PHY)"
J1_MAP = "som_j1_connector (STM32 USB FS + CC sense)"


def circuit() -> Circuit:
    c = Circuit("pd_input", "Power inlet: USB-C PD 20V/3A receptacle")
    c.part("J1", TYPEC_LIB, "TYPE-C-31-M-12", TYPEC_FP, LCSC="C165948")

    # ---- VBUS -> +VIN: raw 20 V input rail + inlet bulk + TVS clamp --------
    c.part("C1", "Device:C", "100n", C0603, LCSC="C1591")
    c.part("C2", "Device:C", "10u", C1210, LCSC="C596319")   # 50V X7R
    c.part("D1", "Device:D_Zener", "SMBJ22A", TVS_FP, LCSC="C10214")
    c.net("+VIN", "J1.A4B9", "J1.B4A9", "C1.1", "C2.1", "D1.1")
    c.net("GND", "J1.A1B12", "J1.B1A12", "C1.2", "C2.2", "D1.2")

    # ---- CC lines to the FUSB302B (usb_pd sheet) + SoM STM32 ---------------
    c.port("STM32_USB_CC1", "J1.A5")
    c.port("STM32_USB_CC2", "J1.B5")

    # ---- FS data to the STM32 (device/dual-role port), cable-flip paired ---
    c.port("STM32_USB_D_P", "J1.A6", "J1.B6")
    c.port("STM32_USB_D_N", "J1.A7", "J1.B7")
    c.port_type("STM32_USB_D_P", kind="usb_hs_pair", pair_with="STM32_USB_D_N")

    # ---- SBU unused; shell to chassis (usbc_otg pattern) -------------------
    c.nc("J1.A8", "J1.B8")
    c.net("CHASSIS_GND", "J1.1", "J1.2", "J1.3", "J1.4")
    return c
