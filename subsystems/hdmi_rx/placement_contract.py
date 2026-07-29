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
    U1  M24C02-WMN6TP          EDID EEPROM on the DDC bus (SDA=5, SCL=6,
                               WC#=7 + VCC=8 both on cable-5V HDMI_RX_5V)
    C1  100n                   EEPROM VCC bypass (C1.1 = HDMI_RX_5V with U1.8)
    R1  1k                     HPD assert, cable 5V -> HPD (R1.2 = J1.19 net)
    R2  27k                    CEC pull-up (R2.2 = CEC = J1.13 net)
    R3  10k / R4  15k          cable-5V presence divider: R3.1 = HDMI_RX_5V
                               (J1.18), R3.2 = R4.1 = HDMI_RX_5V_DET port,
                               R4.2 = GND

CENSUS WAVE 2026-07-29 — the EDID/slow-line support network graduates from
"leftovers" to gated structures: the EEPROM + its bypass and the HPD/CEC/5V-DET
passives are all cable-domain elements of the connector's slow-line region (the
DDC bus is PRIVATE jack<->EEPROM wiring mastered over the cable — HDMI 1.4
sec 8.5 requires the source to read EDID with the board off — so the whole
cluster belongs at the receptacle, not strewn across the zone).

Every threshold carries a ``basis`` string (a TI/ST datasheet section citation
or ``judgment:<value>`` — LAW 7 / LAW 4).
"""

from __future__ import annotations

# HDMI-019S receptacle pads on the slow-line/cable-5V region (dossier footprint,
# HDMI 1.4 sec 4.2.2 pinout): 13=CEC, 15=SCL, 16=SDA, 18=+5V, 19=HPD.
_J1_CEC, _J1_SCL, _J1_SDA, _J1_5V, _J1_HPD = "13", "15", "16", "18", "19"
_U1_VCC = "8"

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "hdmi_rx",
    "sheet": "hdmi_rx",
    "citations": ["TI SLVSD85B (TPD4E02B04)", "TI SLVSBO7O (TPD4E05U06)",
                  "ST M24C02 DS (VCC decoupling)",
                  "HDMI 1.4 sec 8.5 (EDID readable from cable 5V)"],
    "roles": {
        "J1": "connector",
        "U2": "tmds_esd", "U3": "tmds_esd",
        "U4": "slow_esd",
        "U1": "edid_eeprom", "C1": "eeprom_vcc_bypass",
        "R1": "hpd_assert", "R2": "cec_pullup",
        "R3": "det_divider_top", "R4": "det_divider_bottom",
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
        # ---- EDID EEPROM on the private DDC stub at the jack ------------------
        # The DDC bus is jack<->EEPROM-only wiring read over the cable (HDMI 1.4
        # sec 8.5, board-off EDID read), so U1 sits in the receptacle's slow-line
        # region keeping the SCL/SDA stubs short. No spec mm -> judgment 12.0
        # (behind the <=6mm slow-line ESD, inside the connector region).
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_SCL, _J1_SDA],
         "members": ["U1"], "max_mm": 12.0, "same_side": True,
         "basis": "HDMI 1.4 sec 8.5 (cable-read EDID; DDC is private jack<->"
                  "EEPROM wiring) — EEPROM at the DDC pads|judgment:12.0"},
        # ---- EEPROM VCC bypass at its supply pin ------------------------------
        # ST M24C02 DS (Power-up/decoupling): 100 nF between VCC and VSS at the
        # device; no mm stated -> judgment 2.0 (house per-pin bypass family).
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "ST M24C02 DS VCC decoupling (no mm stated)|judgment:2.0"},
        # ---- HPD assert + CEC pull-up in the slow-line region -----------------
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_HPD],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "HPD passive assert (cable 5V -> pin 19) with its pad; HDMI "
                  "1.4 HPD is 5V-domain sheet-local|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_CEC],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "CEC 27k pull-up (HDMI 1.4 CEC electrical) with the CEC "
                  "pad|judgment:8.0"},
        # ---- cable-5V presence divider: tap at pin 18, junction tight ---------
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_5V],
         "members": ["R3"], "max_mm": 8.0, "same_side": True,
         "basis": "5V-presence divider top taps the cable-5V entry pad"
                  "|judgment:8.0"},
        {"type": "proximity", "anchor": "R3",
         "members": ["R4"], "max_mm": 3.0, "same_side": True,
         "basis": "divider bottom at the mid-node junction (one lumped "
                  "divider, short HDMI_RX_5V_DET tap)|judgment:3.0"},
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
