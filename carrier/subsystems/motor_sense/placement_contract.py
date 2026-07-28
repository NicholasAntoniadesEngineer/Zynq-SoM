"""PLACEMENT CONTRACT (v2) for the ``motor_sense`` subsystem — plain data, no logic.

motor_sense is the ESC motor-rail telemetry front end: an in-line 10 mR shunt
(RS1) between two XT60 connectors (J2 in, J3 out) read by an INA3221 (U2), with a
TVS clamp (D1) at the input and a 470 uF bulk (C4) on the load-side rail. This
contract encodes the "supply pin bypass tight / current-sense amp close to the
shunt / clamp at the entry / bulk at the load" layout requirement as the GENERIC
``proximity`` structure type (Decision D10). See
``subsystems/power/placement_contract.py`` for the schema rationale and
``AI_LAYOUT_ROUTING_CONCEPT.md`` "motor_sense" (Research wave COMPLETE) for the
verified content — including the EXTRACTION CORRECTION that U2 is an INA3221 (NOT
an INA226).

CARRIER-LOCAL PACKAGE: this subsystem lives in carrier/subsystems/; the contract
registry resolves ``carrier.subsystems.<sheet>.placement_contract`` (E1).

motor_sense parts (from motor_sense.py, netlist-verified):
    U2   INA3221AIRGVR          the 3-ch current/bus-V monitor (VS = pin 4)
    RS1  RLM12FTCMR010 10 mR    the in-line shunt (ESC_VRAIL_IN -> ESC_VRAIL)
    J2   XT60PW-M               ESC battery / bench-supply IN
    J3   XT60PW-M               ESC rail OUT (to off-board ESCs)
    D1   SMBJ28A                TVS clamp on the ESC bus (at J2)
    C2   100 nF  on +3V3_SC     INA3221 VS bypass (U2.4)
    C3   10 uF   on +3V3_SC     INA3221 VS bulk
    C4   470 uF  on ESC_VRAIL   load-side bulk (at J3)

INA3221 PIN MAP (relevant): 4 VS (supply).

Every threshold carries a ``basis`` string (an SBOS576C section citation or
``judgment:<value>`` — LAW 7 / LAW 4).
"""

from __future__ import annotations

_VS = "4"          # INA3221 supply pin (bypass anchor)

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "motor_sense",
    "sheet": "motor_sense",
    "citations": ["TI SBOS576C (INA3221)"],
    "roles": {
        "U2": "sense_ic", "RS1": "shunt",
        "J2": "power_in", "J3": "power_out", "D1": "tvs",
        "C2": "vs_hf", "C3": "vs_bulk", "C4": "load_bulk",
        "C1": "in_hf", "R1": "crit_pullup",
    },
    "structures": [
        # ---- VS bypass: 100 nF <= 2 mm of the INA3221 VS pin ------------------
        # SBOS576C 8.2/8.3 "bypass ... as close as possible"; no number -> 2.0.
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_VS],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "SBOS576C 8.2/8.3 (bypass close as possible)|judgment:2.0"},
        # ---- VS bulk: 10 uF <= 5 mm of the INA3221 (any pad) ------------------
        {"type": "proximity", "anchor": "U2",
         "members": ["C3"], "max_mm": 5.0, "same_side": True,
         "basis": "SBOS576C 8.2/8.3 (supply bulk near the device)|judgment:5.0"},
        # ---- SENSE AMP at the shunt: U2 <= 10 mm of RS1 -----------------------
        # SBOS576C 7.4.1 "place the device close to the shunt"; expressed as a
        # proximity with members=[U2] anchored to RS1 (whole-part). The in-line
        # chain J2->RS1->J3 is a PLACEMENT concern after all: unconstrained, the
        # placer parked the shunt+INA 52 mm from the connectors across a foreign
        # column (2026-07-28 visual audit) — routing cannot repair that. RS1 is
        # therefore anchored to J2 below, putting the whole sense chain at the
        # power entry.
        {"type": "proximity", "anchor": "RS1",
         "members": ["U2"], "max_mm": 10.0, "same_side": True,
         "basis": "SBOS576C 7.4.1 (device close to the shunt)|judgment:10.0"},
        # ---- in-line sense chain AT the entry: RS1 <= 12 mm of J2 -------------
        {"type": "proximity", "anchor": "J2",
         "members": ["RS1"], "max_mm": 12.0, "same_side": True,
         "basis": "J2->RS1->J3 in-line current path at the connectors; measured "
                  "52mm adrift when unconstrained|judgment:12.0"},
        # ---- input HF bypass AT the entry node: C1 <= 6 mm of J2 --------------
        {"type": "proximity", "anchor": "J2",
         "members": ["C1"], "max_mm": 6.0, "same_side": True,
         "basis": "ESC_VRAIL_IN HF bypass at the entry beside the TVS; was "
                  "orphaned bottom-side|judgment:6.0"},
        # ---- CRITICAL pull-up with the IC: R1 <= 8 mm of U2 -------------------
        {"type": "proximity", "anchor": "U2",
         "members": ["R1"], "max_mm": 8.0,
         "basis": "open-drain CRITICAL pull-up lives with the INA3221; was "
                  "orphaned 65mm|judgment:8.0"},
        # ---- TVS clamp at the entry: D1 <= 5 mm of J2 -------------------------
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["2"],
         "members": ["D1"], "max_mm": 6.0,
         "basis": "clamp on the '+' entry pad — any-pad passed via a GND tab "
                  "while the + run measured 18.9mm|judgment:6.0"},
        {"type": "proximity", "anchor": "J3", "anchor_pins": ["2"],
         "members": ["RS1"], "max_mm": 30.0,
         "basis": "in-line J2->RS1->J3: bound to BOTH ends so the chain sits "
                  "between the XT60s; measured 51mm north|judgment:30.0"},
        # ---- load-side bulk: C4 470 uF <= 8 mm of J3 --------------------------
        {"type": "proximity", "anchor": "J3",
         "members": ["C4"], "max_mm": 8.0,
         "basis": "load-side bulk near the ESC rail out (README)|judgment:8.0"},
        # ---- SAME SIDE: the sense amp + its shunt + the VS caps share a side ---
        {"type": "same_side", "ics": ["U2", "RS1"],
         "basis": "sense amp, shunt and VS bypass co-located (top side)"},
    ],
    "stage_order": ["U2"],
    "external": {
        # NEAR_MAX (E5-lite): the telemetry front end sits by the PWM output half
        # (Decision D9 — the two halves of the motor interface move to the same
        # board edge). No datasheet number -> judgment.
        "near_max": [
            {"other": "motor_pwm", "max_mm": 20.0,
             "basis": "judgment:20.0 (D9) — motor telemetry beside the PWM out"},
        ],
        # FAR_MIN: keep both switching power stages off the dirty ESC rail /
        # sense node (SBOS576C 7.4.1 noise-coupling rationale).
        "far": [
            {"what": "power", "min_mm": 10.0,
             "basis": "judgment:10.0 — SBOS576C 7.4.1 noise coupling: buck "
                      "switching node vs the current-sense node"},
            {"what": "power_som", "min_mm": 10.0,
             "basis": "judgment:10.0 — SBOS576C 7.4.1 noise coupling: buck "
                      "switching node vs the current-sense node"},
        ],
    },
}
