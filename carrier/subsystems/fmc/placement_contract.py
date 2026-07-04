"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``fmc`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): the audit CORRECTED the orchestrator's read and de-escalated
fmc from critical to lightweight — "its 14 differential pairs die at an
uncontrolled stock 0.1in header, placement isn't the circuit". So this contract
covers ONLY the portable, netlist-derivable electrical truth that DOES depend on
placement: the VADJ LDO's per-pin DECOUPLING. NO invented electrical
requirements, NO composition / ``external`` block. NOT wired into the engine
(``_WIRED_SHEETS`` untouched) — authored data for the red-on-before proof via
``discover_contract`` / ``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered
packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY
refs (fmc.py's U1/C3/C4), carried to board refs by the same per-sheet band
rename the netlist uses.

SAME-ROW DIFF-PAIR NOTE (documentation, NOT a gated structure — DO NOT
over-engineer). Each of the 14 pairs (CLK0/CLK1_M2C + LA00-LA11) is authored P
on the ODD header pin and N on the following EVEN pin, so the pair's two contacts
sit side-by-side on ONE physical row of the stock Conn_02x20 footprint. That
same-row placement is INTRINSIC to the connector footprint (both ends are the
SAME part J1 — there is no part-to-part proximity to gate). It is recorded here
so the intent survives, but the P/N-on-one-row requirement is satisfied by
construction and is therefore not emitted as a proximity structure (the gate has
no two-pins-of-one-connector primitive, and inventing one would over-engineer a
requirement the footprint already guarantees).

fmc actives (fmc.py, netlist-verified):
    U1  TLV75725PDYDR   +3V3 -> +2V5_VADJ LDO (DYD thermal-pad SOT-23-6-like);
                        IN = pin 1, OUT = pin 5, EP = pin 6 (netted GND).

DECOUPLING derived from the netlist (the LDO's own in/out caps — the
placement-sensitive pair):
    C3 (1u)   the LDO INPUT cap on +3V3 -> U1.IN (pin 1).
    C4 (10u)  the LDO OUTPUT cap on +2V5_VADJ -> U1.OUT (pin 5).
    C1 (10u) / C2 (100n)  EXCLUDED: +3V3 BULK/bypass shared with J1.1 and the
              LDO input — rail-level parts, not an unambiguous single-pin LDO
              cap (packer precedent for shared-rail bulk).
    C5 (100n) EXCLUDED: the AT-HEADER +2V5_VADJ bypass (belongs at J1, a
              connector-rail bypass — left to the packer, camera/microsd
              precedent for connector-rail decoupling).

TLV75725 pins: IN=1, GND=2, EN=3, NC=4, OUT=5, EP=6.
"""

from __future__ import annotations

_U1_IN = "1"
_U1_OUT = "5"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "fmc",
    "sheet": "fmc",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "vadj_ldo", "C3": "ldo_in", "C4": "ldo_out",
    },
    "structures": [
        # ---- DECOUPLING: TLV75725 LDO input cap --------------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C3"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: TLV75725 LDO output cap -------------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_OUT],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- SAME SIDE: the LDO caps on the LDO's side -------------------------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
