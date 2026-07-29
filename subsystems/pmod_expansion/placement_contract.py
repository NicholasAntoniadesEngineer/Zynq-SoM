"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``pmod_expansion`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): the critical subsystems carry DEEP datasheet-grounded
contracts; pmod_expansion is a gated 3.3 V Pmod breakout with cable-facing ESD —
lightweight. Covers ONLY (1) per-pin SUPPLY-RAIL DECOUPLING (the SY6280 load
switch's Cin + its ISET set-resistor) and (2) PORT-ENTRY ESD (the two TPD4E1U06
arrays at the socket). MIRRORS the sibling ``subsystems/pmod/placement_contract.py``
for the ESD half, and adds the SY6280 decoupling the sibling lacks (pmod has no
load switch). NO invented electrical requirements, NO composition / ``external``
block. NOT wired into the engine (``_WIRED_SHEETS`` untouched) — authored data
for the red-on-before proof via ``discover_contract`` / ``check_all``.
RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY
refs (pmod_expansion.py's U1/U2/U3/J1/C1/R1), carried to board refs by the same
per-sheet band rename the netlist uses. (This package exists in BOTH roots — the
portable library here and a carrier-flat adapter ``carrier/subsystems/
pmod_expansion.py``; ``discover_contract`` resolves the portable root first, and
the ref map derives from the carrier-bound netlist either way.)

pmod_expansion actives (pmod_expansion.py, netlist-verified):
    U1  SY6280AAC     manual power gate +VDD_PMOD -> +VSW_PMOD; IN=5, ISET=3
    U2  TPD4E1U06     4-ch ESD array clamping Pmod IO 1-4 at the socket
    U3  TPD4E1U06     4-ch ESD array clamping Pmod IO 5-8 at the socket
    J1  DS1024-2x6R2  the 2x6 Pmod socket (the cable-facing port)

DECOUPLING derived from the netlist:
    C1 (100n)  via decouple("U1.IN")  -> the SY6280 input HF bypass (pin 5).
    R1 (13k)   SY6280 ISET (ILIM = 6800/13k = 523 mA); on U1.ISET pin 3 — the
               current-limit set resistor belongs tight to its ISET pin.
    C2 (10u)   +VDD_PMOD input BULK behind the HF bypass. CENSUS WAVE
               2026-07-29: graduates from "packer precedent" — the SY6280 DS
               is explicit (Pin Description: "IN ... decoupled with a 10uF
               capacitor to GND"; App Info: "a 10uF ceramic capacitor from
               VIN to GND is strongly recommended"), so the bulk is held at
               the IN pin behind the 2 mm C1.
    R2 (100k)  EN_PMODX default-OFF pulldown (R2.1 = EN_PMODX = U1.EN pin 4):
               holds the gate OFF until SW1 closes. CENSUS WAVE: held at the
               EN pin it defines.

PORT-ENTRY ESD (cable-facing): each of the 8 Pmod IO carries a GND-referenced
TPD4E1U06 clamp channel at the socket; a strike enters at J1 so both arrays
belong tight to the connector (mirror of the sibling pmod contract). The arrays
sit on the host-side net alongside the socket pad (the placer's connector +
pure-clamp shunt idiom); the same_side clause keeps them on the socket's side.

TPD4E1U06 pins: D1+/D2+/D2-/D1- = 1/3/4/6, GND = 2, NC = 5.
SY6280 pins: OUT=1, GND=2, ISET=3, EN=4, IN=5.
"""

from __future__ import annotations

_U1_IN = "5"
_U1_ISET = "3"
_U1_EN = "4"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "pmod_expansion",
    "sheet": "pmod_expansion",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "load_switch", "U2": "esd_array", "U3": "esd_array",
        "J1": "pmod_socket", "C1": "cin_bypass", "R1": "iset",
        "C2": "cin_bulk", "R2": "en_pulldown",
    },
    "structures": [
        # ---- DECOUPLING: SY6280 load-switch Cin + ISET -------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- SY6280 IN bulk behind the HF bypass (census wave) -----------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C2"], "max_mm": 4.0, "same_side": True,
         "basis": "SY6280 DS Pin Description/App Info ('IN ... decoupled with "
                  "a 10uF capacitor'; no mm stated) — bulk behind the HF "
                  "bypass|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_ISET],
         "members": ["R1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — ISET resistor at its load-switch pin "
                  "(D6 lightweight tier)"},
        # ---- EN default-OFF pulldown at its pin (census wave) ------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_EN],
         "members": ["R2"], "max_mm": 6.0, "same_side": True,
         "basis": "EN_PMODX default-OFF pulldown with the EN pin it defines"
                  "|judgment:6.0"},
        # ---- PORT-ENTRY ESD: both TPD4E1U06 arrays at the Pmod socket ----------
        # (mirror of subsystems/pmod: same_side clause keeps the arrays on J1's
        # side; a separate same_side keyed on U2/U3 would find no members.)
        {"type": "proximity", "anchor": "J1",
         "members": ["U2", "U3"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- SAME SIDE: the SY6280 bypass on the switch's side ----------------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["1"],
         "members": ["C3"], "max_mm": 3.0, "same_side": True,
         "basis": "SY6280 output cap at OUT; nearest rail cap measured "
                  "16.6mm|judgment:3.0"},
        {"type": "proximity", "anchor": "J1", "members": ["C4", "C5"],
         "max_mm": 6.0,
         "basis": "socket VCC bypass at the socket (C4 100n + C5 10u on "
                  "+VSW_PMOD, empirically verified)|judgment:6.0"},
        {"type": "proximity", "anchor": "D1", "members": ["R3"], "max_mm": 5.0,
         "basis": "LED with its series resistor; measured 11.7mm split across "
                  "sides|judgment:5.0"},
    ],
}
