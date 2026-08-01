from __future__ import annotations

_U4_VIN, _U4_VOUT = "1", "5"
_U1_VCC = "14"
_U1_XI, _U1_XO = "19", "20"
_U1_RST, _U1_DTR1, _U1_RTS1 = "1", "10", "13"
_U2_VCC = "14"
_U2_OE = ["1", "4", "10", "13"]

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usb_jtag",
    "sheet": "usb_jtag",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U4": "ldo", "U1": "usb_jtag_bridge", "U2": "jtag_buffer",
        "Y1": "crystal",
        "C1": "ldo_in_bypass", "C2": "ldo_out_bulk", "C3": "ldo_out_hf",
        "C4": "bridge_vcc_bypass", "C7": "buffer_vcc_bypass",
        "R1": "rst_pullup", "R2": "mode_strap", "R3": "mode_strap",
        "R4": "oe_pullup",
    },
    "structures": [
        {"type": "proximity", "anchor": "U4", "anchor_pins": [_U4_VIN],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U4", "anchor_pins": [_U4_VOUT],
         "members": ["C2", "C3"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_VCC],
         "members": ["C7"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_XI, _U1_XO],
         "members": ["Y1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — crystal at its IC (render-audit finding)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_RST],
         "members": ["R1"], "max_mm": 6.0, "same_side": True,
         "basis": "CH347 RST# external 10k with its pin (DS: internal pull-up, "
                  "external adds margin)|judgment:6.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_DTR1],
         "members": ["R2"], "max_mm": 6.0, "same_side": True,
         "basis": "CH347 DS 5.2 POR-latched mode strap (DTR1) at its latch "
                  "pin|judgment:6.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_RTS1],
         "members": ["R3"], "max_mm": 6.0, "same_side": True,
         "basis": "CH347 DS 5.2 POR-latched mode strap (RTS1) at its latch "
                  "pin|judgment:6.0"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": _U2_OE,
         "members": ["R4"], "max_mm": 8.0, "same_side": True,
         "basis": "default-Hi-Z OE# pull-up with the buffer's OE# pads "
                  "(contention-safety strap)|judgment:8.0"},
        {"type": "proximity", "anchor": "Y1", "members": ["C5", "C6"],
         "max_mm": 3.0, "same_side": True,
         "basis": "crystal load caps inside the oscillator loop; measured "
                  "11.3/14.1mm on the OPPOSITE side|judgment:3.0"},
        {"type": "same_side", "ics": ["U4", "U1", "U2", "Y1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
