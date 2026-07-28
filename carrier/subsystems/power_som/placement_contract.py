"""PLACEMENT CONTRACT (v1) for the ``power_som`` subsystem — plain data, no logic.

power_som is a THIRD LM61460 buck (U4: +VIN_SYS -> +5V_SOM, the always-on SoM
supply) — the SAME device as the ``power`` pilot's U1/U2, so every SNVSBD5D
citation and structure type transfers wholesale. Drafted by the orchestrator
from the verified netlist extraction (2026-07-02) + the pilot contract schema
(subsystems/power/placement_contract.py — read it for the schema rationale:
library refs, existential hot-loop, basis strings).

CARRIER-LOCAL PACKAGE NOTE: this subsystem lives in carrier/subsystems/ (a
board-local package), NOT the portable top-level subsystems/ library. The
contract registry (placement_contract_gate.load_contract) resolves both the
portable ``subsystems.<sheet>`` root AND the carrier-local
``carrier.subsystems.<sheet>`` root (E1), so this board-local contract registers
the same way the portable ones do.

ENGINE EXTENSIONS this contract exercises (LANDED — no longer pending):
  (E1) registry: also resolves ``carrier.subsystems.<sheet>.placement_contract``.
  (E2) fb_cluster gate branch: tolerates ABSENT foreign_* keys (single-buck
       sheet — the foreign-SW guard is inter-subsystem here, carried by the
       composition FAR/flow gate, not intra-zone geometry).
  (E3) flow/facing gate: resolves downstream "@som" to the SoM core rect
       (PcbModel.som_core centroid) — the SoM is a fixed region, not a zone.
  (E4') the EN clamp is expressed with the GENERIC ``proximity`` structure type
       (Decision D10), replacing the one-off ``en_cluster`` — the gate FAILS
       LOUD on any structure type it does not implement.

LM61460 PIN MAP (SNVSBD5D Rev. D, identical to the pilot):
    1 BIAS  2 VCC  3 AGND  4 FB  5 PGOOD  6 RT  7 EN/SYNC
    8 VIN1  9 PGND1  10 SW  11 PGND2  12 VIN2  13 RBOOT  14 CBOOT
SWPA8040S inductor: pad 1 = SW side, pad 2 = OUTPUT side.
"""

from __future__ import annotations

_VIN1, _PGND1 = "8", "9"
_VIN2, _PGND2 = "12", "11"
_SW = "10"
_FB = "4"
_RBOOT, _CBOOT = "13", "14"
_VCC = "2"
_BIAS = "1"
_RT = "6"
_EN = "7"
_L_SW, _L_OUT = "1", "2"

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "power_som",
    "sheet": "power_som",
    "citations": ["SNVSBD5D Rev. D (LM61460)"],
    # Netlist-derived roles (verified against carrier/subsystems/power_som/
    # power_som.py nets, 2026-07-02 extraction).
    "roles": {
        "U4": "buck_ic",
        "C14": "cin_hf@VIN1", "C25": "cin_hf@VIN2",   # 100n on +VIN_SYS/GND
        "C15": "cin_bulk", "C16": "cin_bulk",          # 10u 1206 on +VIN_SYS
        "C18": "cout_bulk", "C19": "cout_bulk",        # 22u on +5V_SOM
        "L3": "sw_inductor",                           # SW_5V_SOM -> +5V_SOM
        "R14": "fb_top", "R15": "fb_bot",              # 47.5k / 13k
        "C21": "fb_cff", "R19": "fb_rff",              # 22p + 1k series damp
        "C17": "boot_cap",                             # 100n BOOT<->SW
        "C22": "vcc_cap",                              # 1u U4_VCC
        "R17": "bias_r", "C23": "bias_cap",            # 10R + 1u BIAS tie
        "R18": "rt_r",                                 # 22k fSW=600kHz
        "R12": "en_series", "D5": "en_zener", "C20": "en_cap",  # EN clamp
        # leftovers (band-packed, uncontracted): D4/R16 PG LED, TP1
    },
    "structures": [
        # HOT LOOP — existential per VIN/PGND pair (pilot rationale applies).
        {"type": "hot_loop", "ic": "U4",
         "pin_pairs": [[_VIN1, _PGND1], [_VIN2, _PGND2]],
         "caps": ["C14", "C25"],
         "max_pad_to_pin_mm": 1.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.5|judgment:1.0"},

        {"type": "bulk_in", "ic": "U4", "caps": ["C15", "C16"],
         "vin_pins": [_VIN1, _VIN2], "max_pad_to_pin_mm": 5.0,
         "basis": "SNVSBD5D 9.2.2.5|judgment:5.0"},

        {"type": "bulk_out", "ic": "U4", "caps": ["C18", "C19"],
         "inductor": "L3", "inductor_out_pin": _L_OUT,
         "max_pad_to_pin_mm": 5.0, "same_side": True,
         "basis": "SNVSBD5D 11.2 Fig 11-2 (COUT adjacent to L)|judgment:5.0"},

        {"type": "sw_node", "ic": "U4", "inductor": "L3", "sw_pin": _SW,
         "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 11.1 Fig 11-2|judgment:3.0"},

        # FB CLUSTER — single-buck sheet: NO foreign_* keys (E2). The nearest
        # foreign switcher is the ``power`` subsystem's U1/U2 — an inter-zone
        # concern carried by the composition gate (external.far below), not by
        # intra-zone geometry this contract can express.
        {"type": "fb_cluster", "ic": "U4", "fb_pin": _FB,
         "members": ["R14", "R15", "C21", "R19"],
         "own_sw_pin": _SW, "own_inductor": "L3",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 2.0,
         "basis": "SNVSBD5D 11.1|judgment:2.0 — same RJR-package geometry "
                  "rationale as the pilot (FB pad ~1.3mm from SW)"},

        {"type": "boot", "ic": "U4", "cap": "C17",
         "pins": [_RBOOT, _CBOOT], "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.6, 11.1|judgment:2.0"},

        {"type": "vcc_cap", "ic": "U4", "cap": "C22",
         "pin": _VCC, "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.8, 11.1|judgment:2.0"},

        {"type": "bias_cap", "ic": "U4", "cap": "C23",
         "pin": _BIAS, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 9.2.2.9|judgment:3.0"},

        {"type": "rt_r", "ic": "U4", "resistor": "R18",
         "pin": _RT, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 8.3.5, 11.1|judgment:3.0"},

        # EN CLUSTER — the always-on EN strap: R12 10k series from +VIN_SYS,
        # D5 5.1V zener clamp EN->GND, C20 100n EN bypass. The clamp node must
        # stay short (a long EN node picks up SW noise and the zener's clamp
        # action needs the loop tight); the datasheet's EN section (SNVSBD5D
        # 9.2.2.2 / power_som.py PWR-1) gives no distance -> judgment. Expressed
        # as the GENERIC ``proximity`` type (E4' / Decision D10): the EN cluster
        # is a set of members near a specific anchor pin, exactly what proximity
        # encodes — no bespoke gate branch needed.
        # RE-JUDGED 3.0 -> 6.0 (2026-07-28): EN/SYNC is a slow logic input;
        # 3.0 was measured UNPLACEABLE against the datasheet-faithful core
        # banks (hot-loop 1.0 + boot/vcc 2.0 + fb/rt/bias 3.0 fully ring the
        # 4x4 QFN; the solver's bound-priority displacement proved single-slot
        # musical chairs — no legal assignment exists at 3.0). 6.0 keeps the
        # clamp node one grid-step off the pin region, far from SW.
        {"type": "proximity", "anchor": "U4", "anchor_pins": [_EN],
         "members": ["R12", "D5", "C20"],
         "max_mm": 6.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.2 (EN clamp, PWR-1)|judgment:6.0"},

        {"type": "same_side", "ics": ["U4"],
         "basis": "SNVSBD5D 11.1 Fig 11-2"},
    ],
    "stage_order": ["U4"],
    "external": {
        # +VIN_SYS arrives from power_mon (post-shunt); +5V_SOM feeds the SoM
        # DF40 VIN directly (som_conn_gen binds J1 VIN -> +5V_SOM).
        "flow": ["power_mon", "power_som"],
        # Downstream is the SoM itself — a fixed core region, not a zone (E3).
        "downstream": "@som",
        "output_roles": ["cout_bulk"],
        "far": [
            {"what": "ethernet.line_side", "min_mm": 10.0,
             "basis": "judgment:10.0 — same rationale as the power pilot"},
        ],
    },
}
