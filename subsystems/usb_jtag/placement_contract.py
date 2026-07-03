"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``usb_jtag`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD — plus, for THIS sheet only, (3) the crystal-at-its-IC
proximity (a render-audit finding). NO invented electrical requirements, NO
composition / ``external`` block (critical-six only). NOT wired into the engine
(``_WIRED_SHEETS`` untouched) — authored data for the red-on-before proof via
``discover_contract`` / ``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered
packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(usb_jtag.py's U1/U2/U4/Y1/C...), carried to board refs by the same per-sheet
band rename the netlist uses.

usb_jtag actives (usb_jtag.py, netlist-verified):
    U4  AP2112K-3.3   the debug-island LDO; VIN = pin 1, VOUT = pin 5
    U1  CH347T        USB to JTAG/UART bridge; VCC = pin 14, XI/XO = pins 19/20
    Y1  8 MHz crystal (KDS 1C208000BC0R) on U1.XI/XO
    U2  SN74LVC125A   JTAG isolation buffer; VCC = pin 14

DECOUPLING derived from the netlist (authored decouple() calls, no ambiguity):
    C1 (1u)            via decouple("U4.VIN")   -> LDO input bypass.
    C2 (10u)+C3 (100n) via decouple("U4.VOUT")  -> LDO output caps at pin 5.
    C4 (100n)          via decouple("U1.14")    -> CH347 VCC bypass.
    C7 (100n)          via decouple("U2.14")    -> LVC125 VCC bypass.
    C5/C6 (16p)        crystal LOAD caps — function caps, not rail bypass; they
                       ride with the Y1 cluster but the lightweight tier gates
                       only the crystal->IC distance (below), noted here.

NO PORT-ENTRY ESD STRUCTURE: this sheet carries no connector — the USB-C UFP
receptacle + its USBLC6 ESD array live on the project-side
``usb_jtag_connector`` sheet, so the port-entry term belongs there, not here.

CH347T pins used: VCC=14, XI=19, XO=20. AP2112K: VIN=1, VOUT=5. LVC125: VCC=14.
"""

from __future__ import annotations

# Supply/oscillator pins (authored by NUMBER, footprint-revision-independent).
_U4_VIN, _U4_VOUT = "1", "5"
_U1_VCC = "14"
_U1_XI, _U1_XO = "19", "20"
_U2_VCC = "14"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usb_jtag",
    "sheet": "usb_jtag",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U4": "ldo", "U1": "usb_jtag_bridge", "U2": "jtag_buffer",
        "Y1": "crystal",
        "C1": "ldo_in_bypass", "C2": "ldo_out_bulk", "C3": "ldo_out_hf",
        "C4": "bridge_vcc_bypass", "C7": "buffer_vcc_bypass",
    },
    "structures": [
        # ---- DECOUPLING: AP2112K LDO input bypass at VIN (pin 1) ---------------
        {"type": "proximity", "anchor": "U4", "anchor_pins": [_U4_VIN],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: AP2112K LDO output caps at VOUT (pin 5) ---------------
        {"type": "proximity", "anchor": "U4", "anchor_pins": [_U4_VOUT],
         "members": ["C2", "C3"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: CH347 VCC bypass (pin 14) -----------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: SN74LVC125 VCC bypass (pin 14) ------------------------
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_VCC],
         "members": ["C7"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- CRYSTAL: Y1 tight to the CH347 XI/XO pins (render-audit finding) --
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_XI, _U1_XO],
         "members": ["Y1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — crystal at its IC (render-audit finding)"},
        # ---- SAME SIDE: each IC's bypass (and the crystal) on that IC's side ---
        {"type": "same_side", "ics": ["U4", "U1", "U2"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
