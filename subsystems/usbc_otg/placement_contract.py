from __future__ import annotations

_U1_IN = "5"
_U1_FLT = "3"
_U1_EN = "4"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usbc_otg",
    "sheet": "usbc_otg",
    "tier": "lightweight",
    "citations": ["USB Type-C spec (Rp 56k default-USB, pull-up to VBUS)"],
    "roles": {
        "J2": "usbc_receptacle", "U1": "vbus_switch", "U2": "esd_array",
        "C1": "switch_in_bypass",
        "R1": "cc_rp", "R2": "cc_rp",
        "R3": "flt_pullup", "R5": "en_pulldown", "R4": "id_strap",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "J2",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["A4B9", "B4A9"],
         "members": ["C2", "C3"], "max_mm": 8.0,
         "basis": "hot-plug hold-up bulk at the port VBUS (TPS2051C DS 150uF "
                  "ref); measured ~14mm|judgment:8.0"},
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["A5"],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rp=56k default-USB (spec numbers no mm) — "
                  "Rp terminates the CC1 stub at the pad|judgment:8.0"},
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["B5"],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rp=56k default-USB (spec numbers no mm) — "
                  "Rp terminates the CC2 stub at the pad|judgment:8.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_FLT],
         "members": ["R3"], "max_mm": 6.0, "same_side": True,
         "basis": "open-drain FLT# pull-up with its pin|judgment:6.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_EN],
         "members": ["R5"], "max_mm": 6.0, "same_side": True,
         "basis": "EN default-OFF pulldown with its pin (power-on safety "
                  "strap)|judgment:6.0"},
        {"type": "proximity", "anchor": "J2",
         "members": ["R4"], "max_mm": 12.0, "same_side": True,
         "basis": "OTG ID host-role strap kept inside the port zone (no IC pin "
                  "on this sheet)|judgment:12.0"},
    ],
}
