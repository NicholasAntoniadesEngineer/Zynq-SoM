from __future__ import annotations

_VIN1, _PGND1 = "8", "9"
_VIN2, _PGND2 = "12", "11"
_SW = "10"
_FB, _AGND = "4", "3"
_RBOOT, _CBOOT = "13", "14"
_VCC = "2"
_BIAS = "1"
_RT = "6"

_L_SW, _L_OUT = "1", "2"

_LDO_VIN = "1"
_LDO_VOUT = "5"

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "power",
    "sheet": "power",
    "citations": ["SNVSBD5D Rev. D (LM61460)", "AP2112K"],
    "roles": {
        "U1": "buck_ic",
        "C1": "cin_hf@VIN1", "C25": "cin_hf@VIN2",
        "C2": "cin_bulk", "C3": "cin_bulk",
        "C5": "cout_bulk", "C6": "cout_bulk", "C26": "cout_bulk",
        "L1": "sw_inductor",
        "R1": "fb_top", "R2": "fb_bot", "C27": "fb_cff", "R12": "fb_rff",
        "C4": "boot_cap",
        "C24": "vcc_cap",
        "R11": "bias_r", "C28": "bias_cap",
        "R10": "rt_r",
        "U2": "buck_ic",
        "C7": "cin_hf@VIN1", "C29": "cin_hf@VIN2",
        "C8": "cin_bulk", "C30": "cin_bulk",
        "C10": "cout_bulk", "C11": "cout_bulk",
        "L2": "sw_inductor",
        "R4": "fb_top", "R5": "fb_bot", "C23": "fb_cff", "R15": "fb_rff",
        "C9": "boot_cap",
        "C31": "vcc_cap",
        "R13": "bias_r", "C32": "bias_cap",
        "R14": "rt_r",
        "U3": "ldo_ic",
        "C12": "ldo_cin", "C13": "ldo_cout",
    },
    "structures": [
        {"type": "hot_loop", "ic": "U1",
         "pin_pairs": [[_VIN1, _PGND1], [_VIN2, _PGND2]],
         "caps": ["C1", "C25"],
         "max_pad_to_pin_mm": 1.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.5|judgment:1.0"},
        {"type": "hot_loop", "ic": "U2",
         "pin_pairs": [[_VIN1, _PGND1], [_VIN2, _PGND2]],
         "caps": ["C7", "C29"],
         "max_pad_to_pin_mm": 1.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.5|judgment:1.0"},

        {"type": "bulk_in", "ic": "U1", "caps": ["C2", "C3"],
         "vin_pins": [_VIN1, _VIN2], "max_pad_to_pin_mm": 5.0,
         "basis": "SNVSBD5D 9.2.2.5|judgment:5.0"},
        {"type": "bulk_in", "ic": "U2", "caps": ["C8", "C30"],
         "vin_pins": [_VIN1, _VIN2], "max_pad_to_pin_mm": 5.0,
         "basis": "SNVSBD5D 9.2.2.5|judgment:5.0"},

        {"type": "bulk_out", "ic": "U1", "caps": ["C5", "C6", "C26"],
         "inductor": "L1", "inductor_out_pin": _L_OUT,
         "max_pad_to_pin_mm": 5.0, "same_side": True,
         "basis": "SNVSBD5D 11.2 Fig 11-2 (COUT adjacent to L)|judgment:5.0"},
        {"type": "bulk_out", "ic": "U2", "caps": ["C10", "C11"],
         "inductor": "L2", "inductor_out_pin": _L_OUT,
         "max_pad_to_pin_mm": 5.0, "same_side": True,
         "basis": "SNVSBD5D 11.2 Fig 11-2 (COUT adjacent to L)|judgment:5.0"},

        {"type": "sw_node", "ic": "U1", "inductor": "L1", "sw_pin": _SW,
         "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 11.1 Fig 11-2|judgment:3.0"},
        {"type": "sw_node", "ic": "U2", "inductor": "L2", "sw_pin": _SW,
         "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 11.1 Fig 11-2|judgment:3.0"},

        {"type": "fb_cluster", "ic": "U1", "fb_pin": _FB,
         "members": ["R1", "R2", "C27", "R12"],
         "own_sw_pin": _SW, "own_inductor": "L1",
         "foreign_ic": "U2", "foreign_sw_pin": _SW, "foreign_inductor": "L2",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 2.0, "min_to_foreign_sw_mm": 5.0,
         "basis": "SNVSBD5D 11.1|judgment:2.0 — FB pad is ~1.3mm from SW pad on "
                  "the 4.0x3.5mm RJR package (TI Fig 11-2 places the divider "
                  "immediately at FB); 3.0 was geometrically infeasible for the "
                  "nearest divider part; noise protection carried by "
                  "min_to_foreign_sw=5.0 + routing-phase trace rules"},
        {"type": "fb_cluster", "ic": "U2", "fb_pin": _FB,
         "members": ["R4", "R5", "C23", "R15"],
         "own_sw_pin": _SW, "own_inductor": "L2",
         "foreign_ic": "U1", "foreign_sw_pin": _SW, "foreign_inductor": "L1",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 2.0, "min_to_foreign_sw_mm": 5.0,
         "basis": "SNVSBD5D 11.1|judgment:2.0 — FB pad is ~1.3mm from SW pad on "
                  "the 4.0x3.5mm RJR package (TI Fig 11-2 places the divider "
                  "immediately at FB); 3.0 was geometrically infeasible for the "
                  "nearest divider part; noise protection carried by "
                  "min_to_foreign_sw=5.0 + routing-phase trace rules"},

        {"type": "boot", "ic": "U1", "cap": "C4",
         "pins": [_RBOOT, _CBOOT], "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.6, 11.1|judgment:2.0"},
        {"type": "boot", "ic": "U2", "cap": "C9",
         "pins": [_RBOOT, _CBOOT], "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.6, 11.1|judgment:2.0"},

        {"type": "vcc_cap", "ic": "U1", "cap": "C24",
         "pin": _VCC, "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.8, 11.1|judgment:2.0"},
        {"type": "vcc_cap", "ic": "U2", "cap": "C31",
         "pin": _VCC, "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.8, 11.1|judgment:2.0"},

        {"type": "bias_cap", "ic": "U1", "cap": "C28",
         "pin": _BIAS, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 9.2.2.9|judgment:3.0"},
        {"type": "bias_cap", "ic": "U2", "cap": "C32",
         "pin": _BIAS, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 9.2.2.9|judgment:3.0"},

        {"type": "rt_r", "ic": "U1", "resistor": "R10",
         "pin": _RT, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 8.3.5, 11.1|judgment:3.0"},
        {"type": "rt_r", "ic": "U2", "resistor": "R14",
         "pin": _RT, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 8.3.5, 11.1|judgment:3.0"},

        {"type": "ldo_stage", "ic": "U3",
         "cin": "C12", "cin_pin": _LDO_VIN,
         "cout": "C13", "cout_pin": _LDO_VOUT,
         "max_pad_to_pin_mm": 2.0,
         "basis": "AP2112K 8.2.2|judgment:2.0"},

        {"type": "same_side", "ics": ["U1", "U2", "U3"],
         "basis": "SNVSBD5D 11.1 Fig 11-2"},
    ],
    "stage_order": ["U1", "U2", "U3"],
    "external": {
        "flow": ["usb_pd", "power", "power_som"],
        "downstream": "power_som",
        "output_roles": ["cout_bulk"],
        "far": [
            {"what": "ethernet.line_side", "min_mm": 10.0,
             "basis": "judgment:10.0 — buck switching node vs Ethernet MDI/"
                      "magnetics analog line side; datasheet silent on inter-"
                      "subsystem spacing (SNVSBD5D covers intra-stage only)"},
        ],
    },
}
