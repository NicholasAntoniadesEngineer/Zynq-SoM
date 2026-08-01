from __future__ import annotations

_MCT1, _MCT2, _MCT3, _MCT4 = "24", "21", "18", "15"
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
        {"type": "proximity", "anchor": "T1", "anchor_pins": _MEDIA_ROW,
         "members": ["C5"], "max_mm": 8.0, "same_side": True,
         "basis": "Bob-Smith trunk -> chassis barrier, near the media row"
                  "|judgment:8.0"},
        {"type": "same_side", "ics": ["T1"],
         "basis": "media-side Bob-Smith co-located with the magnetics"},
    ],
    "stage_order": ["T1"],
    "external": {
        "media_faces_near_max": True,
        "near_max": [
            {"other": "rj45_connector", "max_mm": 20.0,
             "basis": "Pulse v7 p.1 <=25mm part-to-part|judgment:20.0 edge-gap "
                      "proxy (D11)"},
        ],
        "far": [
            {"what": "power", "min_mm": 10.0,
             "basis": "judgment:10.0 — buck switching node vs Ethernet media/"
                      "magnetics analog line side"},
        ],
    },
}
