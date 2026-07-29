"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) — ``usb_uart_connector`` subsystem, data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): a USB-C UFP receptacle + ESD for a USB-UART side — a
connector-only protection cell, lightweight (same shape as usb_jtag_connector).
Covers PORT-ENTRY ESD (the USBLC6 on the USB2 HS data pair at the receptacle),
the CC Rd role network and the port-VBUS bulk (census wave 2026-07-29 — the
earlier "left to the packer" reading for C1 is REVERSED: the ungated bulk was
the coverage lint's defect class). NO invented electrical requirements, NO
composition / ``external`` block.

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY
refs (usb_uart_connector.py's J1/U1/C1/R1/R2), carried to board refs by the same
per-sheet band rename the netlist uses.

usb_uart_connector parts (usb_uart_connector.py, netlist-verified):
    J1  TYPE-C-31-M-12  USB-C UFP receptacle (the user-touchable port)
    U1  USBLC6-2SC6     low-cap ESD array on the HS data pair (1<->6 / 3<->4
                        passthrough): connector-side DP/DM on U1.1/U1.3, the
                        protected pair to the bridge on U1.6/U1.4, VBUS clamp ref
                        on U1.5, GND on U1.2.
    R1  5.1k  Rd pulldown on CC1 (R1.1 = USB_UART_R1_CC = J1.CC1, R1.2 = GND)
    R2  5.1k  Rd pulldown on CC2 (R2.1 = USB_UART_R2_CC = J1.CC2, R2.2 = GND)
    C1  10u   receptacle-VBUS bulk (C1.1 = USB_UART_VBUS with both J1 VBUS pad
              stacks + the USBLC6 clamp ref U1.5; C1.2 = GND)

A strike enters at the USB-C receptacle, so the USBLC6 is the port-entry
protection and belongs tight to J1. same_side keeps each member on the
connector's side (a separate same_side keyed on U1 would find no members, so it
is omitted; camera precedent).

Type-C pads: CC1=A5, CC2=B5, VBUS=A4B9+B4A9. USBLC6 pins: 1/3 = line side,
6/4 = protected, 5 = VBUS ref, 2 = GND.
"""

from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usb_uart_connector",
    "sheet": "usb_uart_connector",
    "tier": "lightweight",
    "citations": ["USB Type-C spec (Rd 5.1k, sink role)"],
    "roles": {
        "J1": "usbc_receptacle", "U1": "esd_array",
        "R1": "cc_rd", "R2": "cc_rd", "C1": "vbus_bulk",
    },
    "structures": [
        # ---- PORT-ENTRY ESD: the USBLC6 HS-pair array near the receptacle ------
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- CC Rd pulldowns, each at ITS OWN CC pad (census wave 2026-07-29) --
        # USB Type-C spec Rd = 5.1 kohm +-10% (UFP role; the spec numbers the
        # VALUE, not a mm). CC1 = pad A5, CC2 = pad B5 (TYPE-C-31-M-12 dossier
        # footprint, pin-map-verified). Each Rd terminates its CC pad's stub.
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["A5"],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rd=5.1k (UFP role; spec numbers no mm) — Rd "
                  "terminates the CC1 stub at the pad|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["B5"],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rd=5.1k (UFP role; spec numbers no mm) — Rd "
                  "terminates the CC2 stub at the pad|judgment:8.0"},
        # ---- port-VBUS bulk at the receptacle VBUS pad stacks ------------------
        # C1 (10u) rides the receptacle VBUS net (J1.VBUS + U1.5 clamp ref) —
        # usb_uart_connector.py: "10u bulk/bypass (USB-C UFP VBUS decoupling,
        # Cbus per the spec)". Held to the VBUS pad stacks A4B9/B4A9 (usbc_otg
        # hot-plug bulk precedent). The earlier "left to the packer" reading is
        # REVERSED by the census wave.
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["A4B9", "B4A9"],
         "members": ["C1"], "max_mm": 8.0, "same_side": True,
         "basis": "port-VBUS bulk (USB-C UFP Cbus) at the VBUS pads|judgment:8.0"},
    ],
}
