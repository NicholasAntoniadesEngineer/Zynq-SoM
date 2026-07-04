"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``board_qwiic`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): board_qwiic is a QWIIC / STEMMA-QT expansion connector plus
its ESD array — a connector-only protection cell, lightweight. Covers ONLY
PORT-ENTRY ESD (the USBLC6 on the I2C SDA/SCL at the JST-SH). NO invented
electrical requirements, NO composition / ``external`` block. NOT wired into the
engine (``_WIRED_SHEETS`` untouched) — authored data for the red-on-before proof
via ``discover_contract`` / ``check_all``. RED-ON-BEFORE IS EXPECTED (the
scattered packer violates it).

CARRIER-LOCAL: this package lives ONLY under ``carrier/subsystems/board_qwiic/``
(the earlier skip parked it as carrier-local — the isolated AUX I2C bus it
protects is a carrier feature), so ``discover_contract`` resolves it via the
carrier root. Schema + gate: ``subsystems/usb_pd/placement_contract.py``
(proximity + same_side exemplar) and ``schgen/verify/placement_contract_gate.py``.
Refs are LIBRARY refs (board_qwiic.py's J1/U1), carried to board refs by the same
per-sheet band rename the netlist uses.

board_qwiic actives (board_qwiic.py, netlist-verified):
    J1  ZX-SH1.0-4PWT   4-pin JST-SH QWIIC receptacle (the user-touchable port)
    U1  USBLC6-2SC6     low-cap ESD array on SDA/SCL (1<->6 / 3<->4 passthrough
                        idiom): external SDA on U1.1, SCL on U1.3; protected pair
                        to the isolated bus on U1.6/U1.4; +3V3 clamp ref on U1.5.

BOARD_QWIIC IS AN ESD-ONLY CELL. The only active part is the passive USBLC6 ESD
array — no powered IC with a decoupling rail — so this contract has NO decoupling
structure. QWIIC is hot-plugged by hand, so a strike enters at the JST-SH; the
USBLC6 is the port-entry protection and belongs tight to J1. same_side keeps the
array on the connector's side (a separate same_side keyed on U1 would find no
members, so it is omitted; camera precedent).

USBLC6 pins: 1/3 = line side, 6/4 = protected, 5 = VBUS/rail ref, 2 = GND.
"""

from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "board_qwiic",
    "sheet": "board_qwiic",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J1": "qwiic_receptacle", "U1": "esd_array",
    },
    "structures": [
        # ---- PORT-ENTRY ESD: the USBLC6 SDA/SCL array near the JST-SH ----------
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
    ],
}
