from __future__ import annotations

_U1_VCC = "20"
_U1_OE = "19"
_U3_IN = "5"
_U3_ISET = "3"
_U3_OUT = "1"
_J1_SIG_0_3 = ["1", "2", "3", "4"]
_J1_SIG_4_7 = ["5", "6", "7", "8"]

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "motor_pwm",
    "sheet": "motor_pwm",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "output_buffer", "U3": "load_switch", "J1": "esc_header",
        "D1": "esd_array", "D2": "esd_array",
        "RN1": "damping_array", "RN2": "damping_array",
        "C1": "vcc_bypass", "C2": "cin_bypass", "R2": "iset",
        "C3": "out_holdup", "R1": "oe_pullup",
    },
    "structures": [
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U3", "anchor_pins": [_U3_IN],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U3", "anchor_pins": [_U3_ISET],
         "members": ["R2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — ISET resistor at its load-switch pin "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U3", "anchor_pins": [_U3_OUT],
         "members": ["C3"], "max_mm": 3.0, "same_side": True,
         "basis": "SY6280 DS output cap at OUT (motor_pwm.py servo-rail "
                  "hold-up; pmod_expansion C3-at-OUT precedent)|judgment:3.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_OE],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "#OE fail-safe ARM pull-up with the pin it defines "
                  "(default-disarmed buffer)|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": _J1_SIG_0_3,
         "members": ["D1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": _J1_SIG_4_7,
         "members": ["D2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "proximity", "anchor": "U1",
         "members": ["RN1", "RN2"], "max_mm": 6.0, "same_side": True,
         "basis": "judgment:6.0 — series-damping array at its buffer "
                  "(D6 lightweight tier)"},
        {"type": "same_side", "ics": ["U1", "U3"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
