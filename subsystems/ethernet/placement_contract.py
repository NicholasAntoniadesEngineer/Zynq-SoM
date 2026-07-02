"""PLACEMENT CONTRACT (v2) for the ``ethernet`` subsystem — plain data, no logic.

ethernet is the Pulse HX5008NL 1000BASE-T magnetics module (T1, 24-pad) with the
Bob-Smith / IEEE 802.3 §40.7.1 media-side termination. This contract encodes the
line-side layout requirement — each media centre-tap's 75R||1n Bob-Smith pair
tight to its MCT pin, the single 2 kV barrier cap near the media row, everything
on the magnetics' side — as the GENERIC ``proximity`` structure type (Decision
D10). See ``subsystems/power/placement_contract.py`` for the schema rationale
and ``AI_LAYOUT_ROUTING_CONCEPT.md`` "Ethernet line-side research landed" for the
verified content.

HX5008NL PIN MAP (faithful Pulse dossier, verbatim from ethernet.py) — MEDIA /
RJ45 side, the line side this contract governs:
    24 MCT1   23 MX1+  22 MX1-
    21 MCT2   20 MX2+  19 MX2-
    18 MCT3   17 MX3+  16 MX3-
    15 MCT4   14 MX4+  13 MX4-
The CHIP/PHY side (pins 1-12) faces the SoM and carries no discretes here.

ethernet parts (from ethernet.py, netlist-verified):
    T1  HX5008NLT               the magnetics module
    R1/C1  75R / 1n(2kV)  ->  MCT1  (T1.24)   Bob-Smith pair, channel 0
    R2/C2  75R / 1n(2kV)  ->  MCT2  (T1.21)   Bob-Smith pair, channel 1
    R3/C3  75R / 1n(2kV)  ->  MCT3  (T1.18)   Bob-Smith pair, channel 2
    R4/C4  75R / 1n(2kV)  ->  MCT4  (T1.15)   Bob-Smith pair, channel 3
    C5     1n(2kV)              the single BS_COMMON -> CHASSIS_GND barrier cap

Every threshold carries a ``basis`` string (a CITED Pulse v7 figure or
``judgment:<value>`` — LAW 7 / LAW 4).
"""

from __future__ import annotations

# HX5008NL MEDIA-side centre-tap pin numbers (authored by NUMBER).
_MCT1, _MCT2, _MCT3, _MCT4 = "24", "21", "18", "15"
# the whole media row (centre taps + the MX pairs) — the region C5 must sit near.
_MEDIA_ROW = [_MCT1, "23", "22", _MCT2, "20", "19",
              _MCT3, "17", "16", _MCT4, "14", "13"]

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "ethernet",
    "sheet": "ethernet",
    "citations": ["Pulse HX5008NL PS-0118.001-D (v7)", "IEEE 802.3 40.7.1"],
    "roles": {
        "T1": "magnetics",
        "R1": "bst_r", "C1": "bst_c",
        "R2": "bst_r", "C2": "bst_c",
        "R3": "bst_r", "C3": "bst_c",
        "R4": "bst_r", "C4": "bst_c",
        "C5": "barrier_cap",
    },
    "structures": [
        # ---- BOB-SMITH pairs: each 75R||1n <= 4 mm of its MCT pin --------------
        # Each channel's termination pair must hug its media centre tap so the
        # 75R||1n network sits right at the winding tap (short common-mode return);
        # Pulse numbers no discrete-to-pin distance -> judgment 4.0 (0603/1206
        # bodies at a 24-pad module tap).
        {"type": "proximity", "anchor": "T1", "anchor_pins": [_MCT1],
         "members": ["R1", "C1"], "max_mm": 4.0, "same_side": True,
         "basis": "IEEE 802.3 40.7.1 Bob-Smith at the media CT|judgment:4.0"},
        {"type": "proximity", "anchor": "T1", "anchor_pins": [_MCT2],
         "members": ["R2", "C2"], "max_mm": 4.0, "same_side": True,
         "basis": "IEEE 802.3 40.7.1 Bob-Smith at the media CT|judgment:4.0"},
        {"type": "proximity", "anchor": "T1", "anchor_pins": [_MCT3],
         "members": ["R3", "C3"], "max_mm": 4.0, "same_side": True,
         "basis": "IEEE 802.3 40.7.1 Bob-Smith at the media CT|judgment:4.0"},
        {"type": "proximity", "anchor": "T1", "anchor_pins": [_MCT4],
         "members": ["R4", "C4"], "max_mm": 4.0, "same_side": True,
         "basis": "IEEE 802.3 40.7.1 Bob-Smith at the media CT|judgment:4.0"},
        # ---- BARRIER cap: the single 2 kV BS_COMMON -> CHASSIS_GND cap near the
        # media row (it closes the common-mode path to the chassis island) ------
        {"type": "proximity", "anchor": "T1", "anchor_pins": _MEDIA_ROW,
         "members": ["C5"], "max_mm": 8.0, "same_side": True,
         "basis": "Bob-Smith trunk -> chassis barrier, near the media row"
                  "|judgment:8.0"},
        # ---- SAME SIDE: every media-side discrete on the magnetics' side -------
        {"type": "same_side", "ics": ["T1"],
         "basis": "media-side Bob-Smith co-located with the magnetics"},
    ],
    "stage_order": ["T1"],
    # ADVISORY intra-comment terms (recorded, NOT gated — kept out of the gated
    # structures deliberately):
    #   * T1 -> SoM region >= 25 mm: Pulse v7 p.2 gives PHY<->magnetics >= 25 mm,
    #     but here it is measured ACROSS the mezzanine to the remote PHY on the
    #     SoM (a remote-PHY caveat) — not a term this carrier can gate as a
    #     zone-centroid distance without over-constraining the floorplan.
    #   * total media path < 100 mm (magnetics -> RJ45) — an advisory routing
    #     budget, not a placement bound.
    "external": {
        # NEAR_MAX (E5-lite, D11): the magnetics must sit close to its RJ45 jack —
        # the ONE PRIMARY-CITED inter-subsystem distance in this design. Pulse's
        # rule is a PART-to-PART <=25 mm; D11 made near_max a zone bbox EDGE-to-EDGE
        # gap, so the CITED 25 mm part-to-part limit is re-expressed as the more
        # conservative <=20 mm zone edge gap (the edge gap is <= any part-to-part
        # distance, so 20 mm edge gap keeps every magnetics part within the cited
        # 25 mm of the jack with margin).
        "near_max": [
            {"other": "rj45_connector", "max_mm": 20.0,
             "basis": "Pulse v7 p.1 <=25mm part-to-part|judgment:20.0 edge-gap "
                      "proxy (D11)"},
        ],
        # FAR_MIN: keep the switching power stage out of the analog line side.
        "far": [
            {"what": "power", "min_mm": 10.0,
             "basis": "judgment:10.0 — buck switching node vs Ethernet media/"
                      "magnetics analog line side"},
        ],
    },
}
