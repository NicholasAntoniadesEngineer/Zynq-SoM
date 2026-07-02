"""PLACEMENT CONTRACT (v2) for the ``hdmi_rx`` subsystem — plain data, no logic.

hdmi_rx is the HDMI-A sink front end: the receptacle (J1) plus the TMDS/slow-line
ESD arrays that must sit AT the connector, between the jack and the receiver. This
contract encodes the "ESD close to the connector" datasheet requirement as the
GENERIC ``proximity`` structure type (Decision D10). See
``subsystems/power/placement_contract.py`` for the schema rationale and
``AI_LAYOUT_ROUTING_CONCEPT.md`` "hdmi_rx" (Research wave COMPLETE) for the
verified content — including the EXTRACTION CORRECTION that the ESD parts are two
TI TPD4E02B04 arrays + one TPD4E05U06 (NOT a TPD12S016).

hdmi_rx parts (from hdmi_rx.py, netlist-verified):
    J1  HDMI-019S              the HDMI-A receptacle
    U2  TPD4E02B04DQAR         TMDS ESD array, lanes D2+D1 (0.2 pF/line)
    U3  TPD4E02B04DQAR         TMDS ESD array, lanes D0+CLK
    U4  TPD4E05U06DQAR         slow-line ESD array (DDC/CEC/HPD)
    (EEPROM U1 + the R/C support parts are NOT placement-critical — leftovers.)

Every threshold carries a ``basis`` string (a TI datasheet section citation or
``judgment:<value>`` — LAW 7 / LAW 4).
"""

from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "hdmi_rx",
    "sheet": "hdmi_rx",
    "citations": ["TI SLVSD85B (TPD4E02B04)", "TI SLVSBO7O (TPD4E05U06)"],
    "roles": {
        "J1": "connector",
        "U2": "tmds_esd", "U3": "tmds_esd",
        "U4": "slow_esd",
    },
    "structures": [
        # ---- TMDS ESD arrays at the connector, <= 5 mm of J1 ------------------
        # SLVSD85B 10.1 places the ESD "as close to the connector as possible" so
        # the protected trace between the TVS and the jack is short (no value ->
        # judgment 5.0). Anchored to ANY pad of J1 (whole-connector proximity —
        # the ESD taps the TMDS lines wherever they exit the dense receptacle).
        {"type": "proximity", "anchor": "J1",
         "members": ["U2", "U3"], "max_mm": 5.0, "same_side": True,
         "basis": "SLVSD85B 10.1 (ESD close to the connector)|judgment:5.0"},
        # ---- slow-line ESD array, <= 6 mm of J1 -------------------------------
        # SLVSBO7O 7.4.1 + the per-pin footnote; slightly looser (6.0) because the
        # slow lines exit the opposite edge of the same receptacle.
        {"type": "proximity", "anchor": "J1",
         "members": ["U4"], "max_mm": 6.0, "same_side": True,
         "basis": "SLVSBO7O 7.4.1 (ESD at the connector)|judgment:6.0"},
        # ---- SAME SIDE: every ESD array on the connector's side ---------------
        {"type": "same_side", "ics": ["J1"],
         "basis": "ESD arrays co-located with the receptacle (J1's side)"},
    ],
    "stage_order": ["J1"],
    # ADVISORY (recorded, NOT gated): flow-through orientation — each ESD array's
    # IO row should sit PERPENDICULAR to the TMDS pair direction with the NC row
    # completing the pass-through (SLVSD85B 5 / 7.3.10), so the lanes cross the
    # array without a detour. This is a TEMPLATE-phase orientation term; the gate
    # v1 does not check pad-row orientation, so it is carried as prose only. No
    # decoupling terms (these are passive GND-referenced clamps, cited).
    "external": {
        # ADVISORY flow only (recorded): hdmi_rx -> the SoM receiver. Not gated
        # as a facing/near term (the SoM is a fixed region and the HDMI lanes are
        # high-speed pairs whose routing budget is a routing-phase concern).
    },
}
