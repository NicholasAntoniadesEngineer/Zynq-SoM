from __future__ import annotations

_VS = "4"
_VPU = "16"
_CRITICAL = "9"
_CH1 = ["12", "11"]
_CH2 = ["15", "14"]
_CH3 = ["2", "1"]

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "power_mon",
    "sheet": "power_mon",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "current_monitor", "U2": "current_monitor",
        "RS1": "sense_shunt", "RS2": "sense_shunt",
        "RS3": "sense_shunt", "RS4": "sense_shunt",
        "C1": "vs_bypass", "C2": "vs_bypass",
        "C3": "rail_bulk", "R1": "alert_pullup",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VS],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_VS],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": _CH1,
         "members": ["RS1"], "max_mm": 4.0, "same_side": True,
         "basis": "judgment:4.0 — Kelvin shunt at its INA input pair "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": _CH2,
         "members": ["RS2"], "max_mm": 4.0, "same_side": True,
         "basis": "judgment:4.0 — Kelvin shunt at its INA input pair "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": _CH3,
         "members": ["RS3"], "max_mm": 4.0, "same_side": True,
         "basis": "judgment:4.0 — Kelvin shunt at its INA input pair "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": _CH1,
         "members": ["RS4"], "max_mm": 4.0, "same_side": True,
         "basis": "judgment:4.0 — Kelvin shunt at its INA input pair "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VS, _VPU],
         "members": ["C3"], "max_mm": 8.0, "same_side": True,
         "basis": "shared +3V3_SC bulk at the master INA's supply pins (census "
                  "wave; binding judgment in the header)|judgment:8.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_CRITICAL],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "PMON_ALERT_N wire-OR pull-up with the master CRITICAL pin"
                  "|judgment:8.0"},
        {"type": "same_side", "ics": ["U1", "U2"],
         "basis": "judgment — bypass/shunt co-located with its IC "
                  "(lightweight tier)"},
    ],
}
