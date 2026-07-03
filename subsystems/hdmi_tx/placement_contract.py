"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``hdmi_tx`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(hdmi_tx.py's U1/J1/C...), carried to board refs by the same per-sheet band
rename the netlist uses.

hdmi_tx actives (hdmi_tx.py, netlist-verified):
    U1  TPD12S016   HDMI companion: 12-ch ESD clamp + level shift + 5V/HPD
                    housekeeping; VCCA = pin 24 (3V3), VCC5V = pin 11 (5V)
    J1  HDMI-019S   HDMI Type-A receptacle (the user-touchable port)

DECOUPLING derived from the netlist (authored decouple() calls):
    C1 (100n)  via decouple("U1.24")  -> VCCA bypass.
    C2 (100n)  via decouple("U1.11")  -> VCC5V bypass.
    C5 (10u)   EXCLUDED: the module-level BULK on the shared +VDD_IO/VCCA rail
               ("each module owns its bulk" — rail bulk, not per-pin bypass;
               camera precedent). AMBIGUITY NOTED.
    C3 (100n) + C4 (1u)  EXCLUDED from the decoupling tier: they bypass the
               SWITCHED CABLE +5V net (U1.5V_OUT pin 13 -> J1 pin 18) and are
               authored "at the connector per HDMI 1.4 Sec 4.2.7" — a
               connector-side term, not an IC supply-pin bypass. RECORDED AS
               ADVISORY ONLY (no structure): the lightweight tier gates only
               per-IC supply bypass + port-entry protection.

PORT-ENTRY protection: U1 itself IS the port protection (the TPD12S016 clamps
all 12 TMDS/DDC/CEC/HPD lines), so the port-entry structure keeps U1 at the
receptacle.

TPD12S016 pins used: VCCA=24, VCC5V=11, 5V_OUT=13.
"""

from __future__ import annotations

# TPD12S016 supply pins (authored by NUMBER, footprint-revision-independent).
_U1_VCCA = "24"
_U1_VCC5V = "11"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "hdmi_tx",
    "sheet": "hdmi_tx",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "hdmi_companion_esd", "J1": "hdmi_receptacle",
        "C1": "vcca_bypass", "C2": "vcc5v_bypass",
    },
    "structures": [
        # ---- DECOUPLING: TPD12S016 VCCA bypass (pin 24) ------------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCCA],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- DECOUPLING: TPD12S016 VCC5V bypass (pin 11) -----------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC5V],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY ESD: the TPD12S016 companion near the HDMI jack --------
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- SAME SIDE: the companion's bypass on the companion's side ---------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
