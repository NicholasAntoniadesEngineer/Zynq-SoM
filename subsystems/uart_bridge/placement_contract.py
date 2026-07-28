"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``uart_bridge`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(uart_bridge.py's U1/C...), carried to board refs by the same per-sheet band
rename the netlist uses.

uart_bridge actives (uart_bridge.py, netlist-verified):
    U1  CP2102N-A02-GQFN24R   USB-UART bridge; VIO = pin 5, VDD = pin 6,
                              VREGIN = pin 7 (all tied to +VDD_IO, self-powered)

DECOUPLING derived from the netlist — the rail is SHARED across pins 5/6/7, but
the per-pin binding is AUTHORED by the source's decouple() calls (no ambiguity):
    C1 (100n) + C2 (10u)  via decouple("U1.7")  -> VREGIN pin bypass + input
                          bulk, both authored AT pin 7.
    C3 (100n)             via decouple("U1.6")  -> VDD pin bypass.
    C4 (100n)             via decouple("U1.5")  -> VIO pin bypass.

NO PORT-ENTRY ESD STRUCTURE: this sheet carries no connector — the USB-C
receptacle and its USBLC6 ESD array live on the project-side
``usb_uart_connector`` sheet, so the port-entry term belongs there, not here.

CP2102N pins used: VIO=5, VDD=6, VREGIN=7 (dossier numbers = SiLabs DS 1:1).
"""

from __future__ import annotations

# CP2102N supply pins (authored by NUMBER, footprint-revision-independent).
_VIO, _VDD, _VREGIN = "5", "6", "7"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "uart_bridge",
    "sheet": "uart_bridge",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "usb_uart_bridge",
        "C1": "vregin_hf", "C2": "vregin_bulk",
        "C3": "vdd_bypass", "C4": "vio_bypass",
    },
    "structures": [
        # ---- DECOUPLING: VREGIN (pin 7) — 100n HF + 10u bulk, both authored
        # at the pin by decouple("U1.7", "100n", "10u") ---------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VREGIN],
         "members": ["C1", "C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: VDD (pin 6) bypass ------------------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VDD],
         "members": ["C3"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: VIO (pin 5) bypass ------------------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VIO],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- SAME SIDE: every bypass on the bridge's side ----------------------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
    "external": {
        "near_max": [
            {"other": "usb_uart_connector", "max_mm": 40.0,
             "basis": "judgment:10.0 (D11 edge-gap) — CP2102N's USB DP/DM pair terminates at the UART USB-C; measured 365mm of cross-board airwire (avg 122mm) with the block anchored mid-board and a STALE floorplan near-intent pointing at rj45_connector"},
        ],
    },
}
