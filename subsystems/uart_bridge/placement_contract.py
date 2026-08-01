from __future__ import annotations

_VIO, _VDD, _VREGIN = "5", "6", "7"
_VBUS_SNS, _RST = "8", "9"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "uart_bridge",
    "sheet": "uart_bridge",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "usb_uart_bridge",
        "C1": "vregin_hf", "C2": "vregin_bulk",
        "C3": "vdd_bypass", "C4": "vio_bypass",
        "R1": "rst_pullup", "R2": "vbus_divider_top", "R3": "vbus_divider_bottom",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VREGIN],
         "members": ["C1", "C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VDD],
         "members": ["C3"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VIO],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VBUS_SNS],
         "members": ["R2", "R3"], "max_mm": 5.0, "same_side": True,
         "basis": "CP2102N DS self-powered VBUS divider at the VBUS pin (DS "
                  "numbers no mm)|judgment:5.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_RST],
         "members": ["R1"], "max_mm": 6.0, "same_side": True,
         "basis": "CP2102N DS open-drain ~RST external pull-up, held at the "
                  "pin|judgment:6.0"},
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
    "external": {
        "near_max": [
            {"other": "usb_uart_connector", "max_mm": 40.0,
             "basis": "judgment:10.0 (D11 edge-gap) — CP2102N's USB DP/DM "
                      "pair terminates at the UART USB-C; measured 365mm of "
                      "cross-board airwire (avg 122mm) with the block "
                      "anchored mid-board and a STALE floorplan near-intent "
                      "pointing at rj45_connector"},
        ],
    },
}
