from __future__ import annotations

_U1_VCCA = "5"
_U1_VCCB0, _U1_VCCB1 = "21", "17"
_U1_B0 = ["20", "18", "16", "23", "22"]
_U2_VCC = "10"
_J1_CD = "9"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "microsd",
    "sheet": "microsd",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "level_translator", "U2": "esd_array", "J1": "sd_slot",
        "C1": "vcca_bypass", "C2": "vccb_bypass", "C4": "esd_vcc_bypass",
        "R1": "card_pull", "R2": "card_pull", "R3": "card_pull",
        "R4": "card_pull", "R5": "card_pull", "R6": "cd_pullup",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCCA],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1",
         "anchor_pins": [_U1_VCCB0, _U1_VCCB1],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_VCC],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "J1",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "same_side", "ics": ["U1", "U2"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
        {"type": "proximity", "anchor": "J1", "members": ["U1"], "max_mm": 8.0,
         "same_side": True,
         "basis": "level-shifter B-port at the card socket; SD_CARD_CLK "
                  "measured 15.0mm|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["4"],
         "members": ["C3"], "max_mm": 8.0,
         "basis": "card-rail hold-up bulk at the slot VDD pad; measured "
                  "~12mm|judgment:8.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": _U1_B0,
         "members": ["R1", "R2", "R3", "R4", "R5"], "max_mm": 10.0,
         "same_side": True,
         "basis": "SD-2 anti-float pull bank grouped on the card-side lines "
                  "(SCEA054A names the value band, no mm)|judgment:10.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_CD],
         "members": ["R6"], "max_mm": 8.0, "same_side": True,
         "basis": "card-detect pull-up with the slot's CD switch pad"
                  "|judgment:8.0"},
    ],
}
