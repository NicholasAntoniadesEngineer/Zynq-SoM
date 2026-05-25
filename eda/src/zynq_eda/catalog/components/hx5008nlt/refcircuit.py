"""Pulse HX5008NLT - 1000BASE-T Gigabit Ethernet magnetics module.

Datasheet: Pulse Electronics HX5008NL, Rev A (2015)
URL: https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf
Package: SOIC-24 wide-body (PS-0118.001-D outline, ~13.16 x 15.11mm)

A 4-channel 1000BASE-T Ethernet magnetics module: four 1:1 transformers
with integrated common-mode chokes and centre-tap access on both sides.
Sits between a Gigabit PHY (here the Zynq-7000 SoM's onboard PHY) and a
bare shielded RJ45 jack (the carrier's RJHSE5380, ``components/rj45``).

Per-channel pinout (DS Sheet 2 SCHEMATIC, T = "Twisted-pair" PHY side,
M = "Media" cable/RJ45 side):

    Channel 1:   1 TCT1     2 TD1+     3 TD1-       24 MCT1   23 MX1+   22 MX1-
    Channel 2:   4 TCT2     5 TD2+     6 TD2-       21 MCT2   20 MX2+   19 MX2-
    Channel 3:   7 TCT3     8 TD3+     9 TD3-       18 MCT3   17 MX3+   16 MX3-
    Channel 4:  10 TCT4    11 TD4+    12 TD4-       15 MCT4   14 MX4+   13 MX4-

Electrical characteristics (DS Sheet 2):
    Turns ratio                : 1 : 1 +/-2%
    OCL transmit (8 mA bias)   : >= 325 uH, -40 to +85 deg C
    Insertion loss             : -1.2 dB max @ 1-100 MHz
    Return loss (Z = 100 ohm)  : -16 dB min @ 1-40 MHz
    Crosstalk TX-RX            : -50 dB min @ 1 MHz
    Hi-pot isolation           : 1500 V_RMS minimum

Carrier wiring:
    * PHY-side (T-side) pairs TD[1..4] connect to RTL8211F-class MDI pins
      on the SoM. The carrier's KiCad symbol exposes these as PHY0..3_P/N
      (the symbol shorthand is "PHY side of the magnetics" not "TD" pairs).
    * Line-side (M-side) pairs MX[1..4] go to the RJ45 8P8C jack. The
      symbol calls these MDI0..3_P/N (the actual MDI lane on the cable).
    * Line-side centre taps MCT[1..4] are exposed in the symbol as
      CT_PAIR0..3 and tie through 75-ohm + 1nF/2kV to a common BS_COMMON
      node, which then bypasses to CHASSIS_GND via a single 1nF/2kV cap.
      This is the canonical IEEE 802.3 "Bob Smith" termination (IEEE
      802.3 Sec 40.7.1) that absorbs differential-to-common-mode noise
      and gives the cable shield a defined RF return path without
      DC-bonding it to signal ground.
    * PHY-side centre taps TCT[1..4] are NOT exposed in the carrier
      symbol because the SoM's onboard PHY supplies its own internal
      common-mode bias (Realtek RTL8211F: internal centre-tap drive,
      DS Sec 9.2). No external L or bypass cap is required on TCTx.

External-component count per channel (BS network):
    1x 75 ohm 1% 0603       (CT_PAIRn -> BS_COMMON)
    1x 1 nF 2 kV X7R safety (CT_PAIRn -> BS_COMMON)

Plus a single shared cap:
    1x 1 nF 2 kV X7R safety (BS_COMMON -> CHASSIS_GND)
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


def _bob_smith_pair(pair_index: int) -> tuple[ExternalPart, ExternalPart]:
    """75R + 1nF/2kV from one line-side centre tap to BS_COMMON."""
    pin = f"CT_PAIR{pair_index}"
    return (
        ExternalPart(
            from_pin=pin,
            to_net="BS_COMMON",
            part_token="75R_0603_1%",
            justification=(
                f"IEEE 802.3 Sec 40.7.1 (Bob Smith): 75R from pair {pair_index} "
                "line-side centre tap to common point"
            ),
        ),
        ExternalPart(
            from_pin=pin,
            to_net="BS_COMMON",
            part_token="1n_2kV_0603_safety",
            justification=(
                f"IEEE 802.3 Sec 40.7.1: 1nF/2kV (safety-rated) AC-couples pair "
                f"{pair_index} centre tap into the Bob Smith common node"
            ),
        ),
    )


HX5008NLT_REFCIRCUIT = ReferenceCircuit(
    part_mpn="HX5008NLT",
    lcsc="C962544",
    datasheet_url="https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf",
    datasheet_revision="Rev A (PS-0118.001-D, 2015-07-30)",
    app_circuit_figure="DS Sheet 2 SCHEMATIC + IEEE 802.3 Sec 40.7.1 Bob Smith network",
    local_datasheet_path="components/hx5008nlt/datasheet.pdf",
    app_circuit_page="Sheet 2 SCHEMATIC + ELECTRICAL CHARACTERISTICS",
    minimum_circuit_verified=True,
    symbol_token="HX5008NLT",
    footprint="Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm",
    description="1000BASE-T 4-pair Ethernet magnetics module (1:1, 325uH, 1500V isolation)",
    external_parts=(
        *_bob_smith_pair(0),
        *_bob_smith_pair(1),
        *_bob_smith_pair(2),
        *_bob_smith_pair(3),
        # Single shared safety cap from the BS common node to chassis GND.
        # 2 kV rating supports IEC 60950 hi-pot (1500 V_RMS in DS Sheet 2)
        # plus margin for line transients.
        ExternalPart(
            from_pin="BS_COMMON",
            to_net="CHASSIS_GND",
            part_token="1n_2kV_0603_safety",
            justification="IEEE 802.3 Sec 40.7.1 + EN 55032: 1nF/2kV safety cap "
                          "AC-couples Bob Smith common to chassis GND for EMI return",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # Differential pairs pass straight through the magnetics; the
        # IEEE 802.3 PHY MDI termination (50R to internal common mode) is
        # implemented inside the PHY itself per RTL8211F DS Sec 9.2.
        "PHY0_P", "PHY0_N",
        "PHY1_P", "PHY1_N",
        "PHY2_P", "PHY2_N",
        "PHY3_P", "PHY3_N",
        "TD0_P", "TD0_N",
        "TD1_P", "TD1_N",
        "TD2_P", "TD2_N",
        "TD3_P", "TD3_N",
        "MDI0_P", "MDI0_N",
        "MDI1_P", "MDI1_N",
        "MDI2_P", "MDI2_N",
        "MDI3_P", "MDI3_N",
    }),
    layout_notes=(
        LayoutNote(
            text="Each MDI pair: 100R differential impedance, length-matched within "
                 "0.5mm intra-pair, <= 2mm skew across the four pairs",
            severity="rule",
            justification="IEEE 802.3 Sec 40.7 + Pulse layout guide",
        ),
        LayoutNote(
            text="CHASSIS_GND is an island bonded to signal GND only at a single "
                 "star point near the carrier's power-entry connector",
            severity="rule",
            justification="EMC ground-loop avoidance + IEEE 802.3 Sec 14.7",
        ),
        LayoutNote(
            text="Place magnetics within 30mm of the RJ45 connector and keep "
                 "MDI traces straight from magnetics to jack (no vias)",
            severity="rule",
            justification="Pulse HX5008NL layout guide + minimise common-mode noise",
        ),
        LayoutNote(
            text="Route the four Bob Smith 75R + 1nF/2kV networks together near "
                 "the magnetics' line side; use the 2kV safety caps (NOT generic "
                 "1nF MLCCs) for IEC 60950 / IEEE 802.3 isolation compliance",
            severity="rule",
            justification="IEEE 802.3 Sec 40.7.1 + safety isolation",
        ),
        LayoutNote(
            text="Keep PHY-side MDI traces (TD0..3 pairs) on a different copper "
                 "layer or 3x spacing from the line-side MX traces to preserve "
                 "the 1500 V_RMS hi-pot isolation through the magnetics",
            severity="rule",
            justification="HX5008NL DS Sheet 2 (1500 V_RMS minimum I/O isolation)",
        ),
    ),
)
