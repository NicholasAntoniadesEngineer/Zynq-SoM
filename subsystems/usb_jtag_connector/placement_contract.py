"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) — ``usb_jtag_connector`` subsystem, data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): a USB-C UFP receptacle + ESD for a USB device port — a
connector-only protection cell, lightweight. Covers PORT-ENTRY ESD (the USBLC6
on the USB2 HS data pair at the receptacle), the CC Rd role network and the
port-VBUS bulk (census wave 2026-07-29 — the earlier "left to the packer"
reading for C1 is REVERSED: the ungated bulk was the coverage lint's defect
class). NO invented electrical requirements, NO composition / ``external``
block.

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY
refs (usb_jtag_connector.py's J1/U1/C1/R1/R2), carried to board refs by the same
per-sheet band rename the netlist uses.

usb_jtag_connector parts (usb_jtag_connector.py, netlist-verified):
    J1  TYPE-C-31-M-12  USB-C UFP receptacle (the user-touchable port)
    U1  USBLC6-2SC6     low-cap ESD array on the HS data pair (1<->6 / 3<->4
                        passthrough): connector-side DP/DM on U1.1/U1.3, the
                        protected pair to the consumer on U1.6/U1.4, VBUS clamp
                        ref on U1.5, GND on U1.2.
    R1  5.1k  Rd pulldown on CC1 (R1.1 = DBG_R1_CC = J1.CC1, R1.2 = GND)
    R2  5.1k  Rd pulldown on CC2 (R2.1 = DBG_R2_CC = J1.CC2, R2.2 = GND)
    C1  10u   +VBUS port bulk (C1.1 = +5V_DBG with both J1 VBUS pad stacks +
              the USBLC6 clamp ref U1.5; C1.2 = GND)

CC Rd AT THE PORT: the 5.1k Rd pulldowns are the port's UFP role advertisement
(USB Type-C spec Rd = 5.1 kohm +-10%; the spec numbers the VALUE, not a mm).
Each Rd terminates its CC pad's stub — a stranded Rd drags the CC net across the
zone — so each resistor is held to ITS OWN CC pad (CC1 = pad A5, CC2 = pad B5,
pin-map-verified against the TYPE-C-31-M-12 dossier footprint). VBUS BULK at
the VBUS pad stacks (A4B9/B4A9), same bound family as the usbc_otg hot-plug
bulk precedent.

Type-C pads: CC1=A5, CC2=B5, VBUS=A4B9+B4A9. USBLC6 pins: 1/3 = line side,
6/4 = protected, 5 = VBUS ref, 2 = GND.
"""

from __future__ import annotations

_CC1, _CC2 = "A5", "B5"
_VBUS = ["A4B9", "B4A9"]

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usb_jtag_connector",
    "sheet": "usb_jtag_connector",
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
        # ---- CC Rd pulldowns, each at ITS OWN CC pad ---------------------------
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_CC1],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rd=5.1k (UFP role; spec numbers no mm) — Rd "
                  "terminates the CC1 stub at the pad|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_CC2],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rd=5.1k (UFP role; spec numbers no mm) — Rd "
                  "terminates the CC2 stub at the pad|judgment:8.0"},
        # ---- port-VBUS bulk at the receptacle VBUS pad stacks ------------------
        {"type": "proximity", "anchor": "J1", "anchor_pins": _VBUS,
         "members": ["C1"], "max_mm": 8.0, "same_side": True,
         "basis": "port-VBUS hold-up bulk at the VBUS pads (usbc_otg hot-plug "
                  "bulk precedent)|judgment:8.0"},
    ],
}
