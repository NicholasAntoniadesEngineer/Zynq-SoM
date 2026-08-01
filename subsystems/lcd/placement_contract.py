from __future__ import annotations

_U1_IN = "6"
_J1_VDD, _J1_PCLK, _J1_DISP, _J1_RST = "4", "30", "31", "39"
_U2_SDA, _U2_SCL = "6", "4"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "lcd",
    "sheet": "lcd",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "boost_ic", "U2": "esd_array", "J1": "ffc_connector",
        "C1": "boost_in_bulk", "C5": "boost_in_hf",
        "L1": "boost_l", "D1": "boost_d", "C2": "vled_cap",
        "R1": "iset_fb", "R4": "en_pulldown",
        "C3": "panel_vdd_hf", "C4": "panel_vdd_bulk",
        "R7": "pclk_series_term",
        "R2": "ctp_sda_pullup", "R3": "ctp_scl_pullup",
        "R5": "ctp_rst_pulldown", "R6": "disp_pullup",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C1", "C5"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "J1",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "proximity", "anchor": "U1",
         "members": ["L1"], "max_mm": 3.0, "same_side": True,
         "basis": "boost LX hot loop — inductor at the switch pin|judgment:3.0"},
        {"type": "proximity", "anchor": "L1",
         "members": ["D1"], "max_mm": 4.0, "same_side": True,
         "basis": "catch diode on the LX node beside the inductor|judgment:4.0"},
        {"type": "proximity", "anchor": "D1",
         "members": ["C2"], "max_mm": 4.0, "same_side": True,
         "basis": "VLED output cap closes the boost loop|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["3"],
         "members": ["R1"], "max_mm": 4.0,
         "basis": "ISET/FB current-sense return at the FB pin; rode the far "
                  "half, measured 30mm|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["4"],
         "members": ["R4"], "max_mm": 8.0,
         "basis": "EN/PWM pull-down with its pin; measured 42.6mm|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_VDD],
         "members": ["C3"], "max_mm": 5.0, "same_side": True,
         "basis": "lcd_backlight.md 3.1 panel-VDD 100n at the FFC power entry"
                  "|judgment:5.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_VDD],
         "members": ["C4"], "max_mm": 8.0, "same_side": True,
         "basis": "lcd_backlight.md 3.1 panel-VDD 10u bulk at the FFC power "
                  "entry|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_PCLK],
         "members": ["R7"], "max_mm": 8.0, "same_side": True,
         "basis": "PCLK 22R source-series damping at its FFC pad (lcd.py "
                  "host-end series R; 2-pin LCD_PCLK_PANEL net)|judgment:8.0"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_SDA],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "CTP SDA 4k7 pull-up with the protected bus node"
                  "|judgment:8.0"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_SCL],
         "members": ["R3"], "max_mm": 8.0, "same_side": True,
         "basis": "CTP SCL 4k7 pull-up with the protected bus node"
                  "|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_RST],
         "members": ["R5"], "max_mm": 8.0, "same_side": True,
         "basis": "TP_RST 100k hold-down at its FFC pad (reset held until the "
                  "host releases)|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_DISP],
         "members": ["R6"], "max_mm": 8.0, "same_side": True,
         "basis": "LCD_DISP 10k default-ON pull-up at its FFC pad"
                  "|judgment:8.0"},
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
