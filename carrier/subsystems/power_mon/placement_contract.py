"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``power_mon`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): the critical subsystems carry DEEP datasheet-grounded
contracts; power_mon is TELEMETRY (no regulation loop, no diff pairs) so the
audit de-escalated it to lightweight. This contract covers ONLY the portable,
netlist-derivable electrical truths — (1) per-pin SUPPLY-RAIL DECOUPLING
proximity, and (2) the sense-measurement KELVIN geometry (each INA3221 input
channel straddling its own series shunt). NO invented electrical requirements,
NO composition / ``external`` block (critical-tier only). NOT wired into the
engine (``placement_contract_gate._WIRED_SHEETS`` untouched) — authored data for
the red-on-before proof via ``discover_contract`` / ``check_all``.
RED-ON-BEFORE IS EXPECTED (the scattered value-sorted packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY
refs (power_mon.py's U1/U2/RS1..RS4/C1..C3), carried to board refs by the same
per-sheet band rename the netlist uses.

power_mon actives (power_mon.py, netlist-verified):
    U1  INA3221AIRGVR   triple current/voltage monitor @ 0x40 (chans 1/2/3)
    U2  INA3221AIRGVR   triple current/voltage monitor @ 0x41 (chan 1 used)
    RS1 10mR  +VIN  sense shunt  -> U1 chan 1 (IN+1=12 / IN-1=11)
    RS2 10mR  +5V   sense shunt  -> U1 chan 2 (IN+2=15 / IN-2=14)
    RS3 10mR  +3V3  sense shunt  -> U1 chan 3 (IN+3=2  / IN-3=1)
    RS4 20mR  +1V8  sense shunt  -> U2 chan 1 (IN+1=12 / IN-1=11)

KELVIN across the shunt (the sense-integrity requirement): a current-shunt
monitor's IN+/IN- must Kelvin-tap DIRECTLY across the shunt resistor's two pads,
so the shunt sits tight to the INA's input-pin pair (short, matched sense leads;
no shared IR drop). Expressed as a per-channel proximity of the shunt to that
channel's IN+/IN- pins (netlist-verified above). Judgment threshold — the
INA3221 datasheet gives no numeric distance (a routing/star-Kelvin concern), but
the placement intent is unambiguous: the shunt belongs next to its monitor.

DECOUPLING derived from the netlist: both INAs run off the always-on +3V3_SC.
    C1 (100n)  U1.VS bypass  (decouple("U1.VS"), pin 4; VPU=16 shares the rail).
    C2 (100n)  U2.VS bypass  (decouple("U2.VS"), pin 4).
    C3 (10u)   EXCLUDED: shared +3V3_SC BULK (both INAs + the ALERT pull-up on
               one net) — rail-level bulk with no unambiguous per-pin binding
               (microsd/camera precedent: shared-rail bulk is left to the packer
               at the lightweight tier).
    R1 (10k)   EXCLUDED: PMON_ALERT_N pull-up, not a supply-decoupling element.

INA3221 pins used (pin_names, netlist): VS=4, IN-1=11, IN+1=12, IN-2=14,
IN+2=15, IN-3=1, IN+3=2.
"""

from __future__ import annotations

# Supply / sense pins (authored by NUMBER, footprint-revision-independent).
_VS = "4"
_CH1 = ["12", "11"]        # IN+1 / IN-1
_CH2 = ["15", "14"]        # IN+2 / IN-2
_CH3 = ["2", "1"]          # IN+3 / IN-3

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
    },
    "structures": [
        # ---- DECOUPLING: each INA3221's VS supply bypass -----------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VS],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_VS],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- KELVIN: each shunt straddles its INA input-pin pair ---------------
        # RS1/RS2/RS3 -> U1 chans 1/2/3; RS4 -> U2 chan 1. same_side keeps the
        # shunt on the monitor's side so the Kelvin sense leads stay short/matched.
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
        # ---- SAME SIDE: each INA's bypass + shunt on that INA's side -----------
        {"type": "same_side", "ics": ["U1", "U2"],
         "basis": "judgment — bypass/shunt co-located with its IC "
                  "(lightweight tier)"},
    ],
}
