from __future__ import annotations

_U1_IN = "1"
_U1_OUT = "5"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "fmc",
    "sheet": "fmc",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "vadj_ldo", "C3": "ldo_in", "C4": "ldo_out",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C3"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_OUT],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["1", "2"],
         "members": ["C1", "C2", "C5"], "max_mm": 8.0,
         "basis": "header power caps at the pin-1/2 end; measured ~50mm at "
                  "the GND end|judgment:8.0"},
    ],
}
