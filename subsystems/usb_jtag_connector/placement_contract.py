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
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_CC1],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rd=5.1k (UFP role; spec numbers no mm) — Rd "
                  "terminates the CC1 stub at the pad|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_CC2],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rd=5.1k (UFP role; spec numbers no mm) — Rd "
                  "terminates the CC2 stub at the pad|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": _VBUS,
         "members": ["C1"], "max_mm": 8.0, "same_side": True,
         "basis": "port-VBUS hold-up bulk at the VBUS pads (usbc_otg hot-plug "
                  "bulk precedent)|judgment:8.0"},
    ],
}
