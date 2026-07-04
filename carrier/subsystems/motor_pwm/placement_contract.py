"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``motor_pwm`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): the critical subsystems carry DEEP datasheet-grounded
contracts; motor_pwm is a benchtop PWM/ESC output buffer (no regulation loop, no
controlled-impedance diff pairs — the ESC leads are off-board) so it is
lightweight. This contract covers ONLY the portable, netlist-derivable
electrical truths — (1) per-pin SUPPLY-RAIL DECOUPLING proximity, (2) PORT-ENTRY
ESD at the off-board ESC header, and (3) the series-damping array kept tight to
the buffer it damps. NO invented electrical requirements, NO composition /
``external`` block. NOT wired into the engine (``_WIRED_SHEETS`` untouched) —
authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY
refs (motor_pwm.py's U1/U3/J1/D1/D2/RN1/RN2/C1/C2/R2), carried to board refs by
the same per-sheet band rename the netlist uses.

motor_pwm actives (motor_pwm.py, netlist-verified):
    U1  SN74HCT245PWR  octal 3.3V->5V output buffer; VCC = pin 20
    U3  SY6280AAC      servo-rail load switch; IN = pin 5, ISET = pin 3
    J1  HX_PZ2.54-3x8P 3x8 output header (SIG=1..8 / +5V=9..16 / GND=17..24)
    D1  SRV05-4        5-line ESD array on ESC_OUT0..3 -> header SIG pins 1..4
    D2  SRV05-4        5-line ESD array on ESC_OUT4..7 -> header SIG pins 5..8
    RN1 4D03WGJ0330T5E 4x33R series-damping array, buffer ch0-3 -> SIG
    RN2 4D03WGJ0330T5E 4x33R series-damping array, buffer ch4-7 -> SIG

DECOUPLING derived from the netlist:
    C1 (100n)  via decouple("U1.VCC")  -> the HCT245 buffer supply bypass.
    C2 (100n)  via decouple("U3.IN")   -> the SY6280 load-switch input bypass
               (SY6280 Cin: datasheet Pin Description "IN ... decoupled with a
               10uF capacitor"; the 100n here is the HF companion).
    R2 (13k)   SY6280 ISET (ILIM = 6800/13k = 523 mA); on U3.ISET pin 3 — the
               current-limit set resistor belongs tight to its ISET pin.
    C3 (10u)   EXCLUDED: +5V_MOTOR_IO servo-rail HOLD-UP on U3.OUT (rail bulk,
               not an IN-pin bypass — packer precedent).
    R1 (10k)   EXCLUDED: #OE fail-safe pull-up, not a decoupling element.

PORT-ENTRY ESD (LAW 7 landed): the two SRV05-4 arrays clamp the 8 off-board ESC
leads at the header (ESC_OUT{i} = J1.SIG{1+i}); a strike enters at J1 so the
clamps belong tight to the connector. D1 -> J1 SIG pins 1..4, D2 -> 5..8.

SERIES-DAMPING near the buffer: each 33R element sits between the HCT245 B
output and the header SIG row; the array belongs tight to the buffer whose edges
it damps (short stub from B pin -> R -> connector). Anchored to U1 (any pad —
the RN spans all 8 B outputs pins 11..18, so a whole-part proximity is the
honest bound, not a single pin).

SN74HCT245 pins: VCC=20. SY6280 pins: OUT=1, GND=2, ISET=3, EN=4, IN=5.
J1 header: SIG row = pins 1..8.
"""

from __future__ import annotations

_U1_VCC = "20"
_U3_IN = "5"
_U3_ISET = "3"
# header SIG pins each SRV05 array clamps (ESC_OUT{i} -> J1.{1+i})
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
    },
    "structures": [
        # ---- DECOUPLING: HCT245 buffer VCC bypass ------------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: SY6280 load-switch Cin + ISET -------------------------
        {"type": "proximity", "anchor": "U3", "anchor_pins": [_U3_IN],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U3", "anchor_pins": [_U3_ISET],
         "members": ["R2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — ISET resistor at its load-switch pin "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY ESD: the two SRV05-4 arrays at the ESC header ----------
        {"type": "proximity", "anchor": "J1", "anchor_pins": _J1_SIG_0_3,
         "members": ["D1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": _J1_SIG_4_7,
         "members": ["D2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- SERIES-DAMPING: RN arrays tight to the buffer they damp -----------
        {"type": "proximity", "anchor": "U1",
         "members": ["RN1", "RN2"], "max_mm": 6.0, "same_side": True,
         "basis": "judgment:6.0 — series-damping array at its buffer "
                  "(D6 lightweight tier)"},
        # ---- SAME SIDE: each IC's bypass on that IC's side ---------------------
        {"type": "same_side", "ics": ["U1", "U3"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
