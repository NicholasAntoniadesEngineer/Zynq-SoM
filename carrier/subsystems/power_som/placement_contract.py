from __future__ import annotations

_VIN1, _PGND1 = "8", "9"
_VIN2, _PGND2 = "12", "11"
_SW = "10"
_FB = "4"
_RBOOT, _CBOOT = "13", "14"
_VCC = "2"
_BIAS = "1"
_RT = "6"
_EN = "7"
_L_SW, _L_OUT = "1", "2"

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "power_som",
    "sheet": "power_som",
    "citations": ["SNVSBD5D Rev. D (LM61460)"],
    "roles": {
        "U4": "buck_ic",
        "C14": "cin_hf@VIN1", "C25": "cin_hf@VIN2",
        "C15": "cin_bulk", "C16": "cin_bulk",
        "C18": "cout_bulk", "C19": "cout_bulk",
        "L3": "sw_inductor",
        "R14": "fb_top", "R15": "fb_bot",
        "C21": "fb_cff", "R19": "fb_rff",
        "C17": "boot_cap",
        "C22": "vcc_cap",
        "R17": "bias_r", "C23": "bias_cap",
        "R18": "rt_r",
        "R12": "en_series", "D5": "en_zener", "C20": "en_cap",
    },
    "structures": [
        {"type": "hot_loop", "ic": "U4",
         "pin_pairs": [[_VIN1, _PGND1], [_VIN2, _PGND2]],
         "caps": ["C14", "C25"],
         "max_pad_to_pin_mm": 1.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.5|judgment:1.0"},

        {"type": "bulk_in", "ic": "U4", "caps": ["C15", "C16"],
         "vin_pins": [_VIN1, _VIN2], "max_pad_to_pin_mm": 5.0,
         "basis": "SNVSBD5D 9.2.2.5|judgment:5.0"},

        {"type": "bulk_out", "ic": "U4", "caps": ["C18", "C19"],
         "inductor": "L3", "inductor_out_pin": _L_OUT,
         "max_pad_to_pin_mm": 5.0, "same_side": True,
         "basis": "SNVSBD5D 11.2 Fig 11-2 (COUT adjacent to L)|judgment:5.0"},

        {"type": "sw_node", "ic": "U4", "inductor": "L3", "sw_pin": _SW,
         "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 11.1 Fig 11-2|judgment:3.0"},

        {"type": "fb_cluster", "ic": "U4", "fb_pin": _FB,
         "members": ["R14", "R15", "C21", "R19"],
         "own_sw_pin": _SW, "own_inductor": "L3",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 2.0,
         "basis": "SNVSBD5D 11.1|judgment:2.0 — same RJR-package geometry "
                  "rationale as the pilot (FB pad ~1.3mm from SW)"},

        {"type": "boot", "ic": "U4", "cap": "C17",
         "pins": [_RBOOT, _CBOOT], "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.6, 11.1|judgment:2.0"},

        {"type": "vcc_cap", "ic": "U4", "cap": "C22",
         "pin": _VCC, "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.8, 11.1|judgment:2.0"},

        {"type": "bias_cap", "ic": "U4", "cap": "C23",
         "pin": _BIAS, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 9.2.2.9|judgment:3.0"},

        {"type": "rt_r", "ic": "U4", "resistor": "R18",
         "pin": _RT, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 8.3.5, 11.1|judgment:3.0"},

        {"type": "proximity", "anchor": "U4", "anchor_pins": [_EN],
         "members": ["R12", "D5", "C20"],
         "max_mm": 6.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.2 (EN clamp, PWR-1)|judgment:6.0"},

        {"type": "same_side", "ics": ["U4"],
         "basis": "SNVSBD5D 11.1 Fig 11-2"},
    ],
    "stage_order": ["U4"],
    "external": {
        "flow": ["power_mon", "power_som"],
        "downstream": "@som",
        "output_roles": ["cout_bulk"],
        "far": [
            {"what": "ethernet.line_side", "min_mm": 10.0,
             "basis": "judgment:10.0 — same rationale as the power pilot"},
        ],
    },
}
