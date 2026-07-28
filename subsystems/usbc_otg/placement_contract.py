"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``usbc_otg`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(usbc_otg.py's J2/U1/U2/C...), carried to board refs by the same per-sheet band
rename the netlist uses.

usbc_otg actives (usbc_otg.py, netlist-verified):
    J2  TYPE-C-31-M-12   USB-C receptacle (the user-touchable port)
    U1  TPS2051C         VBUS power switch; IN = pin 5, OUT = pin 1
    U2  USBLC6-2SC6      D+/D- ESD array at the receptacle

DECOUPLING derived from the netlist:
    C1 (100n)  the TPS2051 input bypass at IN (pin 5) — the only part with U1
               on its +5V_USB rail, unambiguous.
    C2 (22u) + C3 (100u)  EXCLUDED: the VBUS BULK on the SHARED switched-VBUS
               net (U1.OUT + both J2 VBUS pad stacks + U2.5 clamp ref + the CC
               Rp pull-ups) — port-rail bulk with no unambiguous per-pin IC
               binding (camera precedent: connector-rail bulk is left to the
               packer at the lightweight tier). AMBIGUITY NOTED.

TPS2051C pins used: IN=5, OUT=1. USBLC6 pins: 1/3 line side, 6/4 protected,
5 = VBUS clamp ref, 2 = GND.
"""

from __future__ import annotations

# TPS2051C supply pin (authored by NUMBER, footprint-revision-independent).
_U1_IN = "5"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usbc_otg",
    "sheet": "usbc_otg",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J2": "usbc_receptacle", "U1": "vbus_switch", "U2": "esd_array",
        "C1": "switch_in_bypass",
    },
    "structures": [
        # ---- DECOUPLING: TPS2051 input bypass at IN (pin 5) --------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY ESD: the USBLC6 D+/D- array near the receptacle --------
        {"type": "proximity", "anchor": "J2",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- SAME SIDE: the switch's input bypass on the switch's side ---------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["A4B9", "B4A9"],
         "members": ["C2", "C3"], "max_mm": 8.0,
         "basis": "hot-plug hold-up bulk at the port VBUS (TPS2051C DS 150uF "
                  "ref); measured ~14mm|judgment:8.0"},
    ],
}
