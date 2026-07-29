"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``microsd`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(microsd.py's U1/U2/J1/C...), carried to board refs by the same per-sheet band
rename the netlist uses.

microsd actives (microsd.py, netlist-verified):
    U1  TXS02612RTWR   SDIO level translator; VCCA = pin 5 (host rail),
                       VCCB0/VCCB1 = pins 21/17 (card rail)
    J1  TF-01A         the microSD slot (the user-touchable port)
    U2  TPD6E001RSER   6-ch ESD array on the card lines; VCC = pin 10

DECOUPLING derived from the netlist:
    C1 (100n)  via decouple("U1.VCCA")  -> the translator's host-side bypass.
    C2 (100n)  the card-rail HF bypass, authored with the +VDD_CARD rail
               declaration -> bound to the translator's VCCB pins 21/17.
               AMBIGUITY NOTED: +VDD_CARD is a SHARED rail (J1.VDD, both VCCB,
               every pull-up, U2.VCC); C2 is the only free 100n on it, so the
               binding to the VCCB supply pins is a judgment reading of the
               source comment ("slot VDD + both VCCB + ... + bulk").
    C4 (100n)  via decouple("U2.VCC")   -> the TPD6E001 clamp-reference bypass
               (SD-1: VCC biased to the card rail, bypassed locally).
    C3 (22u)   the card-rail BULK serving slot + VCCB + pull-ups on the shared
               +VDD_CARD net — held at the slot VDD pad (structure below).

CENSUS WAVE 2026-07-29 — the card-line pull bank graduates from ungated:
    R1..R5 (100k)  SD-2 anti-float pulls on the TXS02612 B0 one-shot outputs
               (R1=CMD, R2=D0, R3=D1, R4=D2, R5=D3; each R.2 on its
               SD_CARD_* net, R.1 on +VDD_CARD). The card-side lines run
               U1.B0 -> J1 slot -> U2 ESD; the pulls belong grouped on that
               card-side bank (TI SCEA054A names the VALUE band >50k, no mm)
               — held to the nearest of U1's B0 card pads {CMD=20, D0=18,
               D1=16, D2=23, D3=22}.
    R6 (10k)   card-detect pull-up (R6.2 = SD_CARD_DETECT = J1.CD pad 9):
               held at the slot's CD pad.

TXS02612 pins used: VCCA=5, VCCB0=21, VCCB1=17, B0 card pads CMD=20 D0=18
D1=16 D2=23 D3=22. TPD6E001 pins: VCC=10, GND=5. TF-01A slot: VDD=4, CD=9.
"""

from __future__ import annotations

# Supply pins (authored by NUMBER, footprint-revision-independent).
_U1_VCCA = "5"
_U1_VCCB0, _U1_VCCB1 = "21", "17"
_U1_B0 = ["20", "18", "16", "23", "22"]     # CMD, D0, D1, D2, D3 card pads
_U2_VCC = "10"
_J1_CD = "9"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "microsd",
    "sheet": "microsd",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "level_translator", "U2": "esd_array", "J1": "sd_slot",
        "C1": "vcca_bypass", "C2": "vccb_bypass", "C4": "esd_vcc_bypass",
        "R1": "card_pull", "R2": "card_pull", "R3": "card_pull",
        "R4": "card_pull", "R5": "card_pull", "R6": "cd_pullup",
    },
    "structures": [
        # ---- DECOUPLING: TXS02612 host-side (VCCA) bypass ----------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCCA],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: TXS02612 card-side (VCCB0/VCCB1) bypass ---------------
        # (shared +VDD_CARD rail — binding judgment recorded in the header.)
        {"type": "proximity", "anchor": "U1",
         "anchor_pins": [_U1_VCCB0, _U1_VCCB1],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: TPD6E001 VCC clamp-reference bypass (SD-1) ------------
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_VCC],
         "members": ["C4"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY ESD: the TPD6E001 array near the microSD slot ----------
        {"type": "proximity", "anchor": "J1",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- SAME SIDE: each IC's bypass on that IC's side ---------------------
        {"type": "same_side", "ics": ["U1", "U2"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
        {"type": "proximity", "anchor": "J1", "members": ["U1"], "max_mm": 8.0,
         "same_side": True,
         "basis": "level-shifter B-port at the card socket; SD_CARD_CLK "
                  "measured 15.0mm|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["4"],
         "members": ["C3"], "max_mm": 8.0,
         "basis": "card-rail hold-up bulk at the slot VDD pad; measured "
                  "~12mm|judgment:8.0"},
        # ---- CARD-LINE PULL BANK grouped at the B0 card pads (census wave) -----
        # SCEA054A fixes the VALUE (>50k band), not a mm; each 100k held to the
        # nearest of U1's B0 card pads so the bank rides the card-side lines
        # (U1 itself is held <=8mm off the slot above).
        {"type": "proximity", "anchor": "U1", "anchor_pins": _U1_B0,
         "members": ["R1", "R2", "R3", "R4", "R5"], "max_mm": 10.0,
         "same_side": True,
         "basis": "SD-2 anti-float pull bank grouped on the card-side lines "
                  "(SCEA054A names the value band, no mm)|judgment:10.0"},
        # ---- CARD-DETECT pull-up at the slot CD pad (census wave) --------------
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_CD],
         "members": ["R6"], "max_mm": 8.0, "same_side": True,
         "basis": "card-detect pull-up with the slot's CD switch pad"
                  "|judgment:8.0"},
    ],
}
