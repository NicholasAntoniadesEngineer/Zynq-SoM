from __future__ import annotations

_U1_IN = ["1", "2", "3"]
_U1_OUT = ["18", "19", "20"]
_U1_FLT = "15"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "pd_input",
    "sheet": "pd_input",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J1": "usbc_receptacle", "U1": "efuse", "U2": "esd_array",
        "D1": "vbus_tvs", "C1": "in_bypass", "C2": "out_cap",
        "R6": "flt_pullup",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": _U1_IN,
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": _U1_OUT,
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["11"],
         "members": ["R5"], "max_mm": 4.0,
         "basis": "ILIM set resistor short/quiet; measured 13.8mm|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["10"],
         "members": ["C3"], "max_mm": 4.0,
         "basis": "dVdT soft-start cap at its pin; measured 10.4mm|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["8"],
         "members": ["R3", "R4"], "max_mm": 5.0,
         "basis": "OVP divider at the pin; measured ~11mm|judgment:5.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_FLT],
         "members": ["R6"], "max_mm": 6.0,
         "basis": "open-drain FLT# pull-up with its pin|judgment:6.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["A4B9", "B4A9"],
         "members": ["D1"], "max_mm": 5.0, "same_side": True,
         "basis": "surge TVS on the VBUS pads, not the shell; any-pad passed "
                  "via shell while VBUS measured 10.75mm|judgment:5.0"},
        {"type": "proximity", "anchor": "J1",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
