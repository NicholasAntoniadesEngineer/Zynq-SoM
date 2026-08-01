from __future__ import annotations

_J1_CEC, _J1_SCL, _J1_SDA, _J1_5V, _J1_HPD = "13", "15", "16", "18", "19"
_U1_VCC = "8"

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "hdmi_rx",
    "sheet": "hdmi_rx",
    "citations": ["TI SLVSD85B (TPD4E02B04)", "TI SLVSBO7O (TPD4E05U06)",
                  "ST M24C02 DS (VCC decoupling)",
                  "HDMI 1.4 sec 8.5 (EDID readable from cable 5V)"],
    "roles": {
        "J1": "connector",
        "U2": "tmds_esd", "U3": "tmds_esd",
        "U4": "slow_esd",
        "U1": "edid_eeprom", "C1": "eeprom_vcc_bypass",
        "R1": "hpd_assert", "R2": "cec_pullup",
        "R3": "det_divider_top", "R4": "det_divider_bottom",
    },
    "structures": [
        {"type": "proximity", "anchor": "J1",
         "members": ["U2", "U3"], "max_mm": 5.0, "same_side": True,
         "basis": "SLVSD85B 10.1 (ESD close to the connector)|judgment:5.0"},
        {"type": "proximity", "anchor": "J1",
         "members": ["U4"], "max_mm": 6.0, "same_side": True,
         "basis": "SLVSBO7O 7.4.1 (ESD at the connector)|judgment:6.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_SCL, _J1_SDA],
         "members": ["U1"], "max_mm": 12.0, "same_side": True,
         "basis": "HDMI 1.4 sec 8.5 (cable-read EDID; DDC is private jack<->"
                  "EEPROM wiring) — EEPROM at the DDC pads|judgment:12.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "ST M24C02 DS VCC decoupling (no mm stated)|judgment:2.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_HPD],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "HPD passive assert (cable 5V -> pin 19) with its pad; HDMI "
                  "1.4 HPD is 5V-domain sheet-local|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_CEC],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "CEC 27k pull-up (HDMI 1.4 CEC electrical) with the CEC "
                  "pad|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_5V],
         "members": ["R3"], "max_mm": 8.0, "same_side": True,
         "basis": "5V-presence divider top taps the cable-5V entry pad"
                  "|judgment:8.0"},
        {"type": "proximity", "anchor": "R3",
         "members": ["R4"], "max_mm": 3.0, "same_side": True,
         "basis": "divider bottom at the mid-node junction (one lumped "
                  "divider, short HDMI_RX_5V_DET tap)|judgment:3.0"},
        {"type": "same_side", "ics": ["J1"],
         "basis": "ESD arrays co-located with the receptacle (J1's side)"},
    ],
    "stage_order": ["J1"],
    "external": {
    },
}
