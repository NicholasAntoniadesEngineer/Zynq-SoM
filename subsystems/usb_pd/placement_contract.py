from __future__ import annotations

_VDD1, _VDD2 = "3", "4"
_VBUS = "2"
_CC1_A, _CC1_B = "10", "11"
_CC2_A, _CC2_B = "1", "14"

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "usb_pd",
    "sheet": "usb_pd",
    "citations": ["FUSB302B (onsemi)", "AN-5086 (CC filter)"],
    "roles": {
        "U1": "phy_ic",
        "C1": "vdd_hf", "C2": "vdd_bulk",
        "C3": "vbus_bypass",
        "C4": "cc_filter", "C5": "cc_filter",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VDD1, _VDD2],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "FUSB302B (onsemi states no value/distance)|judgment:2.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VDD1, _VDD2],
         "members": ["C2"], "max_mm": 5.0, "same_side": True,
         "basis": "FUSB302B (onsemi states no value/distance)|judgment:5.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VBUS],
         "members": ["C3"], "max_mm": 3.0, "same_side": True,
         "basis": "FUSB302B (onsemi states no value/distance)|judgment:3.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_CC1_A, _CC1_B],
         "members": ["C4"], "max_mm": 3.0, "same_side": True,
         "basis": "AN-5086 (cReceiver budget + EVB topology)|judgment:3.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_CC2_A, _CC2_B],
         "members": ["C5"], "max_mm": 3.0, "same_side": True,
         "basis": "AN-5086 (cReceiver budget + EVB topology)|judgment:3.0"},
        {"type": "same_side", "ics": ["U1"],
         "basis": "FUSB302B EVB (bypass/filter co-located with the PHY)"},
    ],
    "stage_order": ["U1"],
    "external": {
        "flow": ["pd_input", "usb_pd", "power"],
        "near_max": [
            {"other": "pd_input", "max_mm": 10.0,
             "basis": "judgment:10.0 (D11 edge-gap metric) — keep the CC net "
                      "short end-to-end; onsemi numbers no inter-part CC-run "
                      "length"},
        ],
    },
}
