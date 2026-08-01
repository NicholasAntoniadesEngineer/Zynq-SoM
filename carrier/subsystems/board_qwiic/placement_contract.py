from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "board_qwiic",
    "sheet": "board_qwiic",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J1": "qwiic_receptacle", "U1": "esd_array",
    },
    "structures": [
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
    ],
}
