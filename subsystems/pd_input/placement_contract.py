"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``pd_input`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only; the pd_input->usb_pd->power FLOW chain is
carried by the usb_pd/power contracts). NOT wired into the engine
(``_WIRED_SHEETS`` untouched) — authored data for the red-on-before proof via
``discover_contract`` / ``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered
packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(pd_input.py's J1/U1/U2/D1/C...), carried to board refs by the same per-sheet
band rename the netlist uses.

pd_input actives (pd_input.py, netlist-verified):
    J1  TYPE-C-31-M-12   the PD power-inlet receptacle (user-touchable port)
    U1  TPS26631         eFuse; IN = pins 1/2/3, OUT = pins 18/19/20
    U2  USBLC6-2SC6      FS D+/D- ESD array at the receptacle
    D1  SMBJ22A          VBUS surge TVS at the inlet

DECOUPLING derived from the netlist:
    C1 (100n)  the inlet-VBUS HF bypass. AMBIGUITY NOTED: +VBUS_CONN is a
               SHARED net (J1 VBUS pads + D1 + U1.IN/IN_SYS/UVLO + R3); C1 is
               authored on the connector line but the eFuse IN pins are the
               supply pins it bypasses -> bound to U1.IN (judgment).
    C2 (10u)   the eFuse OUTPUT cap ("the dVdT-charged board bulk starts
               here") — the only cap on the U1.OUT rail, unambiguous.
    C3 (47n)   EXCLUDED: the dVdT soft-start FUNCTION cap (pin 10), not rail
               bypass — outside the lightweight decoupling tier.

PORT-ENTRY protection: U2 (data-line ESD) and D1 (VBUS surge clamp) both clamp
strikes entering at J1, so both belong at the port entry.

TPS26631 pins used: IN=1/2/3, OUT=18/19/20.
"""

from __future__ import annotations

# TPS26631 supply pins (authored by NUMBER, footprint-revision-independent).
_U1_IN = ["1", "2", "3"]
_U1_OUT = ["18", "19", "20"]

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "pd_input",
    "sheet": "pd_input",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J1": "usbc_receptacle", "U1": "efuse", "U2": "esd_array",
        "D1": "vbus_tvs", "C1": "in_bypass", "C2": "out_cap",
    },
    "structures": [
        # ---- DECOUPLING: eFuse input HF bypass at the IN pins ------------------
        # (shared inlet-VBUS net — binding judgment recorded in the header.)
        {"type": "proximity", "anchor": "U1", "anchor_pins": _U1_IN,
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: eFuse output cap at the OUT pins ----------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": _U1_OUT,
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY protection: data ESD + VBUS surge TVS at the inlet -----
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["11"],
         "members": ["R5"], "max_mm": 4.0,
         "basis": "ILIM set resistor short/quiet; measured 13.8mm|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["10"],
         "members": ["C3"], "max_mm": 4.0,
         "basis": "dVdT soft-start cap at its pin; measured 10.4mm|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["8"],
         "members": ["R3", "R4"], "max_mm": 5.0,
         "basis": "OVP divider at the pin; measured ~11mm|judgment:5.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["A4B9", "B4A9"],
         "members": ["D1"], "max_mm": 5.0, "same_side": True,
         "basis": "surge TVS on the VBUS pads, not the shell; any-pad passed "
                  "via shell while VBUS measured 10.75mm|judgment:5.0"},
        {"type": "proximity", "anchor": "J1",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- SAME SIDE: the eFuse caps on the eFuse's side ---------------------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
