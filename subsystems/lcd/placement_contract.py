"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``lcd`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(lcd.py's U1/U2/C.../J1), carried to board refs by the same per-sheet band rename
the netlist uses.

lcd actives (lcd.py, netlist-verified):
    U1  SY7201ABC        backlight boost WLED driver; IN = pin 6 (+VBOOST_IN)
    U2  USBLC6-2SC6      touch-I2C ESD array at the FFC (J1)
    L1/D1/R.../C2..C4    boost power train + panel housekeeping — NOT per-IC
                         decoupling, left to the packer (lightweight tier).

DECOUPLING derived from the netlist: the SY7201 IN pin (pin 6) is bypassed by
C1 (10u bulk) + C5 (1u HF) on +VBOOST_IN (lcd.py: "SY7201 IN decoupling: C1 10u
bulk + a dedicated 1u HF ceramic at the pin"). U2 (USBLC6) has only a clamp-
reference pin (+VDD_TP_CLAMP, pin 5) with no bypass cap of its own -> no
decoupling structure for U2; it is covered by the port-entry ESD structure.

SY7201ABC pins used: 1 LX, 2 GND, 3 FB, 4 EN/PWM, 5 OVP, 6 IN.
USBLC6-2SC6 pins: 1/3 = unprotected I/O, 6/4 = protected I/O, 5 = VBUS clamp
    ref, 2 = GND.
"""

from __future__ import annotations

# SY7201 boost input pin (authored by NUMBER, footprint-revision-independent).
_U1_IN = "6"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "lcd",
    "sheet": "lcd",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "boost_ic", "U2": "esd_array", "J1": "ffc_connector",
        "C1": "boost_in_bulk", "C5": "boost_in_hf",
        "L1": "boost_l", "D1": "boost_d", "C2": "vled_cap",
        "R1": "iset_fb", "R4": "en_pulldown",
    },
    "structures": [
        # ---- DECOUPLING: SY7201 IN-pin bypass (C1 10u + C5 1u) tight to pin 6 --
        # Generic per-pin bypass proximity: both input caps within 2 mm of the
        # boost IN pin, same side as the driver (short input loop).
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C1", "C5"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY ESD: the USBLC6 touch-I2C array near the FFC (J1) ------
        {"type": "proximity", "anchor": "J1",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- BOOST SWITCHING CHAIN: U1.LX -> L1 -> D1 -> C2 -------------------
        # 2026-07-28 audit: the boost loop was TORN (U1-to-L1 37.5mm, input cap
        # to inductor 35.6mm) because L1/D1/C2 carried no structure at all — a
        # switching converter's hot loop left to the leftover band. Chain the
        # loop tight; whole-part anchors (no pin-number guessing on SOT-23-6).
        {"type": "proximity", "anchor": "U1",
         "members": ["L1"], "max_mm": 3.0, "same_side": True,
         "basis": "boost LX hot loop — inductor at the switch pin|judgment:3.0"},
        {"type": "proximity", "anchor": "L1",
         "members": ["D1"], "max_mm": 4.0, "same_side": True,
         "basis": "catch diode on the LX node beside the inductor|judgment:4.0"},
        {"type": "proximity", "anchor": "D1",
         "members": ["C2"], "max_mm": 4.0, "same_side": True,
         "basis": "VLED output cap closes the boost loop|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["3"],
         "members": ["R1"], "max_mm": 4.0,
         "basis": "ISET/FB current-sense return at the FB pin; rode the far "
                  "half, measured 30mm|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["4"],
         "members": ["R4"], "max_mm": 8.0,
         "basis": "EN/PWM pull-down with its pin; measured 42.6mm|judgment:8.0"},
        # ---- SAME SIDE: the boost's input caps on the driver's side -----------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
