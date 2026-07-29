"""PLACEMENT CONTRACT (v2, CRITICAL) for the ``camera`` subsystem — plain data.

camera is the Raspberry-Pi 15-pin FFC 2-lane MIPI CSI-2 D-PHY port: the FFC (J1),
two low-cap ESD arrays (U1/U2) that clamp the user-touchable FFC lines, and the
THREE in-path 100 ohm D-PHY differential terminations (R1 = CSI_D0, R2 = CSI_D1,
R3 = CSI_CLK). This contract was PROMOTED from the D6 lightweight tier to a
CRITICAL, datasheet-cited v2 (the HS-family audit) to encode the ONE SI truth the
lightweight tier missed: on a 7-series HR-bank RX the 100 ohm D-PHY termination is
an EXTERNAL resistor that MUST be placed at the RECEIVER (FPGA/mezzanine) END of
each lane, NOT at the FFC. See ``subsystems/power/placement_contract.py`` for the
schema rationale and ``subsystems/usb_pd/placement_contract.py`` for the
proximity/same_side + external exemplar.

PRIMARY CITATIONS (pdftotext-verified):
  * Xilinx XAPP894 (v1.0.1, Feb 1 2021) "D-PHY Solutions" — the 7-series external-
    resistor ("compatible") D-PHY topology this camera uses (camera.py: "a fixed
    external 100R differential termination per D-PHY pair, placed at the FPGA/SoM-
    connector END of each trace (NOT at the FFC)"):
      - LVDS section (Figure 4): "a current transmitter generating a voltage drop
        across a termination resistor placed at the receiver side." (the term IS a
        receiver-end element).
      - Figure 6 (Basic DC-coupling Circuit), the resistor-network annotation:
        "Place close to FPGA." (the external termination network goes at the FPGA
        receiver, not the far cable/FFC end).
  * MIPI D-PHY / CSI-2: HS line termination is 100 ohm differential at the
    receiver (80-125 ohm range, 100 ohm nominal); it is switched OUT in LP mode.
    (D-PHY spec; camera.py types each lane diff_pair @100R.)

camera parts (from camera.py, netlist-verified):
    J1  SFW15R-1STE1LF   15P FFC (the user-touchable camera port); FFC pin n = RPi
                         pin n. CSI pairs: D0 = FFC 3/2, D1 = FFC 6/5, CLK = 9/8.
    U1  TPD4E02B04DQAR   low-cap ESD array, clamps CSI D0+D1 (IO1..IO4)
    U2  TPD4E02B04DQAR   low-cap ESD array, clamps CSI CLK (IO1/IO2) + the two
                         spare channels on CAM_SCL/CAM_SDA (IO3/IO4)
    R1  100R  -> CSI_D0_P/N   in-path D-PHY diff termination (RECEIVER-end)
    R2  100R  -> CSI_D1_P/N   in-path D-PHY diff termination (RECEIVER-end)
    R3  100R  -> CSI_CLK_P/N  in-path D-PHY diff termination (RECEIVER-end)
    R4/R5  4k7   CAM I2C (CCI) pull-ups on +VDD_CAM. CENSUS WAVE 2026-07-29:
                 graduate from "leftovers" — each held at its FFC bus pad
                 (R4.2 = CAM_SCL = J1.13 + U2.4 tap; R5.2 = CAM_SDA = J1.14 +
                 U2.5 tap) so the open-drain pulls ride the connector's I2C
                 entry with the clamp taps.
    C1/C2  100n/10u  +VDD_CAM bypass at the connector (structure below)

Every threshold carries a ``basis`` string (a CITED XAPP894 reference or
``judgment:<value>`` — LAW 7 / LAW 4).
"""

from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "camera",
    "sheet": "camera",
    "citations": ["Xilinx XAPP894 v1.0.1 (D-PHY Solutions)",
                  "MIPI D-PHY (100R HS termination at receiver)"],
    "roles": {
        "J1": "ffc_connector",
        "U1": "esd_array", "U2": "esd_array",
        "R1": "dphy_term", "R2": "dphy_term", "R3": "dphy_term",
        "R4": "cci_scl_pullup", "R5": "cci_sda_pullup",
    },
    "structures": [
        # ---- PORT-ENTRY ESD (flow-through at the FFC): U1/U2 <= 5 mm of J1 -----
        # Both arrays clamp the user-touchable FFC lines, so a strike enters at J1
        # and the clamp belongs at the port entry (jack -> host). Universal per
        # member (both arrays). same_side keeps them on J1's side. No datasheet mm
        # -> judgment 5.0 (generic ESD-at-connector, same family as hdmi_rx/usb_pd).
        {"type": "proximity", "anchor": "J1",
         "members": ["U1", "U2"], "max_mm": 5.0, "same_side": True,
         "basis": "ESD at the FFC port entry (jack->host clamp)|judgment:5.0"},
        # ---- D-PHY TERMINATIONS at the RECEIVER end, CLEAR of the FFC ----------
        # XAPP894 (Fig 4 / Fig 6 "Place close to FPGA") puts the 100R diff term at
        # the RECEIVER. On this sheet the receiver is the SoM/mezzanine (off-sheet,
        # bank pins on som_j2), so the gatable INTRA-zone requirement is a NEGATIVE
        # one: all three terminations must CLEAR the FFC (J1) — a term hugging the
        # FFC is the exact wrong-end defect XAPP894 forbids. This structure hosts
        # the clearance on U1 (an FFC-side ESD array, a real anchor) with a LOOSE
        # max (the terms need not be near U1) so its load-bearing clause is the
        # ``min_from J1 >= 8 mm`` applied to EACH of the three terms — pushing them
        # to the mezzanine-facing side of the zone (the external flow term aims that
        # side at @som).
        {"type": "proximity", "anchor": "U1",
         "members": ["R1", "R2", "R3"], "max_mm": 40.0, "same_side": True,
         "min_from": [{"part": "J1", "min_mm": 8.0}],
         "basis": "XAPP894 Fig 4/Fig 6 'Place close to FPGA' — every D-PHY term at "
                  "the RECEIVER end, >=8mm clear of the FFC|judgment:8.0 FFC "
                  "clearance (40mm max is a loose zone-span host bound)"},
        # ---- TERM CLUSTER: R1/R2/R3 tight together (short, matched stubs) ------
        # The three terminations stay clustered so the four D-PHY stubs (each bank
        # pin -> 100R) are short and length-matched at the receiver. Anchored to R1;
        # anchor-pin absent -> measured to any pad of R1.
        {"type": "proximity", "anchor": "R1",
         "members": ["R2", "R3"], "max_mm": 6.0, "same_side": True,
         "basis": "D-PHY term trio clustered for short matched stubs at the "
                  "receiver|judgment:6.0"},
        # ---- SAME SIDE: ESD + terminations on the FFC/receiver side -----------
        {"type": "same_side", "ics": ["J1"],
         "basis": "camera discretes co-located on the FFC side (no via mid-lane "
                  "on the D-PHY pairs)"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["15"],
         "members": ["C1", "C2"], "max_mm": 6.0,
         "basis": "gated +VDD_CAM bypass at the FFC supply pad; measured "
                  "8-10mm|judgment:6.0"},
        # ---- CCI I2C PULL-UPS at their FFC bus pads (census wave) --------------
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["13"],
         "members": ["R4"], "max_mm": 8.0, "same_side": True,
         "basis": "CAM_SCL 4k7 pull-up with the FFC I2C entry pad"
                  "|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": ["14"],
         "members": ["R5"], "max_mm": 8.0, "same_side": True,
         "basis": "CAM_SDA 4k7 pull-up with the FFC I2C entry pad"
                  "|judgment:8.0"},
    ],
    "stage_order": ["J1"],
    # ADVISORY (recorded, NOT gated):
    #   * RECEIVER-END FACING: the R1/R2/R3 termination cluster should sit on the
    #     mezzanine-facing half of the camera zone (the CSI lanes run FFC -> term
    #     -> SoM bank); the ``flow`` term below aims the zone at @som. A facing-
    #     aware template term (like ethernet's media_faces_near_max) is future work.
    #   * The XAPP894 LP-observability resistor-divider is a DNP stuffing option
    #     off this sheet (camera.py CAM-1). C1/C2/R4/R5 are rail bypass / I2C pull-
    #     ups (leftovers), not layout-critical.
    "external": {
        # FLOW: the CSI-2 lanes run camera -> the SoM/mezzanine receiver. @som
        # resolves to the SoM core rectangle (E3); keeping the zone's receiver-end
        # (term) side toward the module keeps each D-PHY stub short.
        "flow": ["camera", "@som"],
    },
}
