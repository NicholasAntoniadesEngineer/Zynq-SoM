"""PLACEMENT CONTRACT (v2) for the ``usb_pd`` subsystem — plain data, no logic.

usb_pd is the FUSB302B USB Type-C / Power-Delivery sink-PHY (U1, WQFN-14 + EP).
This contract encodes the datasheet/EVB layout requirement for its bypass +
CC-filter network as the GENERIC ``proximity`` structure type (Decision D10) so
the placement-contract gate checks it against the EMITTED board with NO
subsystem-specific gate branch. See ``subsystems/power/placement_contract.py``
for the schema rationale (library refs, per-member checks, basis strings) and
``AI_LAYOUT_ROUTING_CONCEPT.md`` "Research wave COMPLETE" for the verified
content.

RESEARCH CAVEAT (recorded): the FUSB302B datasheet (onsemi) states NO value or
distance for the VDD/VBUS bypass caps, so those bounds are JUDGMENT. The only
PRIMARY-CITED figure is the 200 pF CC filter (Fairchild/onsemi AN-5086 cReceiver
budget + the EVB topology) — cited on the C4/C5 proximity ``basis``.

usb_pd parts (from usb_pd.py, netlist-verified):
    U1  FUSB302BMPX               the PHY
    C1  100 nF  on +VDD_LOGIC     VDD bypass  (U1.3/U1.4)
    C2  10 uF   on +VDD_LOGIC     VDD bulk    (U1.3/U1.4)
    C3  100 nF  on +VBUS_SENSE    VBUS-sense bypass (U1.2)
    C4  200 pF  on CC1            CC1 analog filter (U1.10, U1.11)
    C5  200 pF  on CC2            CC2 analog filter (U1.1,  U1.14)

FUSB302B PIN MAP (Interface_USB:FUSB302BMPX, WQFN-14 + EP):
    1 CC2   2 VBUS   3 VDD   4 VDD(stacked)   5 INT_N   6 SCL   7 SDA
    8 GND   9 GND(EP)  10 CC1   11 CC1(stacked)   12 VCONN(NC)   13 VCONN(NC)
    14 CC2(stacked)   15 GND(EP)

EVERY threshold carries a ``basis`` string (an AN-5086 citation or
``judgment:<value>`` for a distance no datasheet numbers — LAW 7 / LAW 4).
"""

from __future__ import annotations

# FUSB302B pin numbers (authored by NUMBER, footprint-revision-independent).
_VDD1, _VDD2 = "3", "4"          # VDD + its stacked twin
_VBUS = "2"                      # VBUS sense
_CC1_A, _CC1_B = "10", "11"      # CC1 + its stacked twin
_CC2_A, _CC2_B = "1", "14"       # CC2 + its stacked twin

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "usb_pd",
    "sheet": "usb_pd",
    "citations": ["FUSB302B (onsemi)", "AN-5086 (CC filter)"],
    "roles": {
        "U1": "phy_ic",
        "C1": "vdd_hf", "C2": "vdd_bulk",
        "C3": "vbus_bypass",
        "C4": "cc_filter", "C5": "cc_filter",
    },
    "structures": [
        # ---- VDD bypass: 100 nF HF at the VDD pins, tight -----------------------
        # onsemi states NO distance -> judgment 2.0 (HF bypass wants the shortest
        # loop to the VDD/GND pins; same family as the pilot's vcc_cap 2.0).
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VDD1, _VDD2],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "FUSB302B (onsemi states no value/distance)|judgment:2.0"},
        # ---- VDD bulk: 10 uF, behind the HF cap, <= 5 mm of VDD -----------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VDD1, _VDD2],
         "members": ["C2"], "max_mm": 5.0, "same_side": True,
         "basis": "FUSB302B (onsemi states no value/distance)|judgment:5.0"},
        # ---- VBUS-sense bypass: 100 nF <= 3 mm of the VBUS pin ------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_VBUS],
         "members": ["C3"], "max_mm": 3.0, "same_side": True,
         "basis": "FUSB302B (onsemi states no value/distance)|judgment:3.0"},
        # ---- CC1 analog filter: 200 pF <= 3 mm of the CC1 pins -----------------
        # PRIMARY-CITED value (AN-5086 cReceiver + EVB); the <=3 mm keeps the CC
        # filter node short so it does not distort the BMC signalling.
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_CC1_A, _CC1_B],
         "members": ["C4"], "max_mm": 3.0, "same_side": True,
         "basis": "AN-5086 (cReceiver budget + EVB topology)|judgment:3.0"},
        # ---- CC2 analog filter: 200 pF <= 3 mm of the CC2 pins -----------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_CC2_A, _CC2_B],
         "members": ["C5"], "max_mm": 3.0, "same_side": True,
         "basis": "AN-5086 (cReceiver budget + EVB topology)|judgment:3.0"},
        # ---- SAME SIDE: every bypass/filter cap on the PHY's side --------------
        {"type": "same_side", "ics": ["U1"],
         "basis": "FUSB302B EVB (bypass/filter co-located with the PHY)"},
    ],
    "stage_order": ["U1"],
    # ADVISORY (recorded, NOT gated): the FUSB302B EP -> GND fanout (datasheet
    # Fig. 5) is a fanout-phase judgment (via array under the EP), not an
    # intra-zone placement term. VCONN pins 12/13 are correct NC (sink-only).
    "external": {
        # FLOW: the board-level PD input chain — the Type-C receptacle
        # (pd_input) feeds this PHY (usb_pd), which commands the input rail into
        # ``power``. Consistent with the power pilot's chain.
        "flow": ["pd_input", "usb_pd", "power"],
        # NEAR_MAX (E5-lite): keep the PHY close to its receptacle so the CC net
        # stays short end-to-end (a long CC run degrades the BMC PHY). onsemi
        # gives no number -> judgment.
        "near_max": [
            {"other": "pd_input", "max_mm": 15.0,
             "basis": "judgment:15.0 — keep the CC net short end-to-end; onsemi "
                      "numbers no inter-part CC-run length"},
        ],
    },
}
