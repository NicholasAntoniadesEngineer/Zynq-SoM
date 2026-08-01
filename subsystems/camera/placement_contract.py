from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "camera",
    "sheet": "camera",
    "citations": ["Xilinx XAPP894 v1.0.1 (D-PHY Solutions)",
                  "MIPI D-PHY (100R HS termination at receiver)"],
    "roles": {
        "J1": "ffc_connector",
        "U1": "esd_array", "U2": "esd_array",
        "R1": "dphy_term", "R2": "dphy_term", "R3": "dphy_term",
        "R4": "cci_scl_pullup", "R5": "cci_sda_pullup",
    },
    "structures": [
        {"type": "proximity", "anchor": "J1",
         "members": ["U1", "U2"], "max_mm": 5.0, "same_side": True,
         "basis": "ESD at the FFC port entry (jack->host clamp)|judgment:5.0"},
        {"type": "proximity", "anchor": "U1",
         "members": ["R1", "R2", "R3"], "max_mm": 40.0, "same_side": True,
         "min_from": [{"part": "J1", "min_mm": 8.0}],
         "basis": "XAPP894 Fig 4/Fig 6 'Place close to FPGA' — every D-PHY term at "
                  "the RECEIVER end, >=8mm clear of the FFC|judgment:8.0 FFC "
                  "clearance (40mm max is a loose zone-span host bound)"},
        {"type": "proximity", "anchor": "R1",
         "members": ["R2", "R3"], "max_mm": 6.0, "same_side": True,
         "basis": "D-PHY term trio clustered for short matched stubs at the "
                  "receiver|judgment:6.0"},
        {"type": "same_side", "ics": ["J1"],
         "basis": "camera discretes co-located on the FFC side (no via mid-lane "
                  "on the D-PHY pairs)"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["15"],
         "members": ["C1", "C2"], "max_mm": 6.0,
         "basis": "gated +VDD_CAM bypass at the FFC supply pad; measured "
                  "8-10mm|judgment:6.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["13"],
         "members": ["R4"], "max_mm": 8.0, "same_side": True,
         "basis": "CAM_SCL 4k7 pull-up with the FFC I2C entry pad"
                  "|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["14"],
         "members": ["R5"], "max_mm": 8.0, "same_side": True,
         "basis": "CAM_SDA 4k7 pull-up with the FFC I2C entry pad"
                  "|judgment:8.0"},
    ],
    "stage_order": ["J1"],
    "external": {
        "flow": ["camera", "@som"],
    },
}
