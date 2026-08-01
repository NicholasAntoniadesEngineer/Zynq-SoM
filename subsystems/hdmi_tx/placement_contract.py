from __future__ import annotations

_U1_VCCA = "24"
_U1_VCC5V = "11"
_U1_5V_OUT = "13"
_U1_TMDS_A = ["23", "22", "21", "20", "18", "17", "16", "15"]

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "hdmi_tx",
    "sheet": "hdmi_tx",
    "citations": ["TI TPD12S016 SLLSE96F", "TI SLLA324 (HDMI ESD PCB layout)"],
    "roles": {
        "U1": "hdmi_companion_esd", "J1": "hdmi_receptacle",
        "C1": "vcca_bypass", "C2": "vcc5v_bypass",
        "C3": "cable5v_hf", "C4": "cable5v_bulk",
        "C5": "vdd_io_bulk",
    },
    "structures": [
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.5, "same_side": True,
         "basis": "SLLSE96F 8.2/10.1 + SLLA324 Fig 8 (companion AT the HDMI "
                  "connector, TMDS pass-through)|judgment:5.5"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["1"],
         "members": ["U1"], "max_mm": 9.0, "same_side": True,
         "basis": "flow-through centering, outer TMDS pad A; TMDS_2 measured "
                  "20.0mm|judgment:9.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["12"],
         "members": ["U1"], "max_mm": 9.0, "same_side": True,
         "basis": "flow-through centering, outer TMDS pad B|judgment:9.0"},
        {"type": "proximity", "anchor": "U1", "members": ["R1", "R2"],
         "max_mm": 6.0,
         "basis": "LS_OE / CT_HPD straps at their pins; measured "
                  "15.9/15.7mm|judgment:6.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCCA],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "SLLSE96F 10.1 (caps close to their pins; DS lists VBUS/VOTG_IN "
                  "in the TPD-family template — the principle applies to VCCA/"
                  "VCC5V here, shown at the pin in Fig 15/17)|judgment:2.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC5V],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "SLLSE96F 10.1 (caps close to their pins; DS lists VBUS/VOTG_IN "
                  "in the TPD-family template — the principle applies to VCCA/"
                  "VCC5V here, shown at the pin in Fig 15/17)|judgment:2.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_5V_OUT],
         "members": ["C3"], "max_mm": 3.0, "same_side": True,
         "basis": "HDMI 1.4 4.2.7 (cable +5V bypass at the connector), HF cap"
                  "|judgment:3.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_5V_OUT],
         "members": ["C4"], "max_mm": 5.0, "same_side": True,
         "basis": "HDMI 1.4 4.2.7 (cable +5V bypass at the connector), bulk cap"
                  "|judgment:5.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCCA],
         "members": ["C5"], "max_mm": 8.0, "same_side": True,
         "basis": "module +VDD_IO bulk behind the VCCA HF bypass (the rail's "
                  "only consumer on this sheet)|judgment:8.0"},
        {"type": "same_side", "ics": ["U1"],
         "basis": "SLLSE96F 10.1 — companion + bypass co-located (single-side "
                  "flow-through, avoid vias between clamp pin and connector)"},
    ],
    "stage_order": ["U1"],
    "external": {
        "flow": ["hdmi_tx", "@som"],
    },
}
