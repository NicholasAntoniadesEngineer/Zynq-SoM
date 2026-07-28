"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``pmod`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(pmod.py's J1/J2/U1..U4), carried to board refs by the same per-sheet band
rename the netlist uses.

PMOD IS AN ESD+PASSIVES CELL (like camera). The only active parts are the four
TI TPD4E1U06 4-ch ESD arrays — GND-referenced (no VCC pin), so there is NO
powered IC with a decoupling rail and this contract has NO decoupling structure.
C1..C4 (100n + 10u per port) are the connector +VCC_PMOD rail bypass, not an
IC's per-pin bypass, so they are left to the packer (camera precedent:
lightweight tier = per-IC decoupling only).

Port mapping (pmod.py, netlist-verified): U1 + U2 clamp the eight PMOD0 lines
of J1; U3 + U4 clamp the eight PMOD1 lines of J2. The arrays sit on the
HOST-side net of the 200R series resistors (audit 2026-06-20: socket-side
meshes the float placer), but a strike still enters at the socket, so the
clamps (with their series Rs) belong at the port entry.

TPD4E1U06 pins: D1+/D2+/D2-/D1- = 1/3/4/6, GND = 2, NC = 5.
"""

from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "pmod",
    "sheet": "pmod",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J1": "pmod0_socket", "J2": "pmod1_socket",
        "U1": "esd_array", "U2": "esd_array",
        "U3": "esd_array", "U4": "esd_array",
    },
    "structures": [
        # ---- PORT-ENTRY ESD: PMOD0's two TPD4E1U06 arrays near J1 --------------
        # (the proximity's own same_side clause keeps the arrays on the socket's
        # side — a separate same_side structure would key on U1..U4 as ANCHORS
        # and find no members, so it is omitted; camera precedent.)
        {"type": "proximity", "anchor": "J1",
         "members": ["U1", "U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- PORT-ENTRY ESD: PMOD1's two TPD4E1U06 arrays near J2 --------------
        {"type": "proximity", "anchor": "J2",
         "members": ["U3", "U4"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        {"type": "proximity", "anchor": "U1",
         "members": ["R1", "R2", "R3", "R4"], "max_mm": 8.0,
         "basis": "port0 IO1-4 series R beside their clamp array; measured to "
                  "37.8mm cross-port|judgment:8.0"},
        {"type": "proximity", "anchor": "U2",
         "members": ["R5", "R6", "R7", "R8"], "max_mm": 8.0,
         "basis": "port0 IO5-8 series R beside their clamp array|judgment:8.0"},
        {"type": "proximity", "anchor": "U3",
         "members": ["R9", "R10", "R11", "R12"], "max_mm": 8.0,
         "basis": "port1 IO1-4 series R beside their clamp array|judgment:8.0"},
        {"type": "proximity", "anchor": "U4",
         "members": ["R13", "R14", "R15", "R16"], "max_mm": 8.0,
         "basis": "port1 IO5-8 series R beside their clamp array|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "members": ["C1", "C2"],
         "max_mm": 6.0,
         "basis": "+VCC_PMOD bypass at the socket power pads (shared rail, "
                  "paired by convention)|judgment:6.0"},
        {"type": "proximity", "anchor": "J2", "members": ["C3", "C4"],
         "max_mm": 6.0,
         "basis": "+VCC_PMOD bypass at the socket power pads|judgment:6.0"},
    ],
}
