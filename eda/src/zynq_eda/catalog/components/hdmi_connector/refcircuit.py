"""HDMI Type-A receptacle (HDMI 1.4) - SOFNG HDMI-019S, SMD right-angle.

Datasheet: SOFNG HDMI-019S mechanical drawing
URL (LCSC): https://datasheet.lcsc.com/lcsc/SOFNG-HDMI-019S_C111617.pdf
HDMI Spec: HDMI 1.4b Sec 4.2 (signal definitions), Sec 8.1 (DDC), Sec 5 (CEC)

19-pin Type-A receptacle. The DDC pull-ups and CEC pull-up that an
unprotected HDMI port would otherwise need are integrated inside the
TPD12S016 companion (DS Sec 7.3.9). Externals at the connector itself
are therefore limited to +5V VBUS decoupling and shield-to-chassis
discharge per HDMI 1.4 Sec 4.2.7.

Used twice on the carrier (one mechanical part, two roles):

    * HDMI TX (source) - this connector ties to TPD12S016PWR_TX; pin 18
      sources +5V via the TPD's on-chip 55mA load switch; a 24LC256 EDID
      EEPROM sits on the DDC bus (HDMI 1.4 Sec 8.1).
    * HDMI RX (sink)   - this connector ties to TPD12S016PWR_RX; pin 18
      carries +5V coming IN from the upstream source for back-drive-
      protected sensing inside the TPD.

Pin map (HDMI 1.4 Sec 4.2.2, confirmed against SOFNG HDMI-019S sheet 2):

     1  TMDS Data 2+
     2  TMDS Data 2 Shield   (GND)
     3  TMDS Data 2-
     4  TMDS Data 1+
     5  TMDS Data 1 Shield   (GND)
     6  TMDS Data 1-
     7  TMDS Data 0+
     8  TMDS Data 0 Shield   (GND)
     9  TMDS Data 0-
    10  TMDS Clock+
    11  TMDS Clock Shield    (GND)
    12  TMDS Clock-
    13  CEC                  (one-wire bidirectional, 27k pull-up on host)
    14  Reserved (N.C.)      (HEC/Ethernet in HDMI 1.4 Ethernet channel)
    15  SCL                  (DDC clock, +5V open-drain)
    16  SDA                  (DDC data,  +5V open-drain)
    17  DDC/CEC Ground
    18  +5V Power            (max 50mA sourced by upstream/host)
    19  Hot Plug Detect      (+5V level, pulled low <= 0.4V when no sink)

The connector body has four PCB mounting/shell legs that MUST tie to
CHASSIS_GND (an isolated frame-ground pour separate from signal GND).
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


HDMI_A_REFCIRCUIT = ReferenceCircuit(
    part_mpn="HDMI-019S",
    lcsc="C111617",
    datasheet_url="https://datasheet.lcsc.com/lcsc/SOFNG-HDMI-019S_C111617.pdf",
    datasheet_revision="2018-06 mechanical drawing",
    app_circuit_figure="HDMI 1.4b Sec 4.2 + TPD12S016 DS Fig 15",
    local_datasheet_path="components/hdmi_connector/datasheet.pdf",
    app_circuit_page="Sheet 2 (Pin Definition) + HDMI 1.4 Sec 4.2.7",
    minimum_circuit_verified=True,
    symbol_token="HDMI_A_Receptacle",
    footprint="Connector_HDMI:HDMI_A_SOFNG_HDMI-019S",
    description="HDMI Type-A receptacle, 19-pin SMD right-angle, shielded",
    external_parts=(
        # +5V VBUS bulk + bypass at the connector (HDMI 1.4 Sec 4.2.7).
        # Source role: caps absorb load-switch turn-on transients (DS Sec
        # 6.6: T_ON ~ 77us with 0.1uF + 500R, T_OFF ~ 7us).
        # Sink role:  caps decouple the +5V sense input from the upstream
        # cable; TPD12S016 V_CC5V pin only needs ~50uA so no bulk required.
        ExternalPart(
            from_pin="+5V",
            to_net="GND",
            part_token="1u_0402_X7R",
            justification="HDMI 1.4 Sec 4.2.7 / TPD12S016 DS Fig 15: 1uF bulk "
                          "on +5V at the connector to support load-switch turn-on",
        ),
        ExternalPart(
            from_pin="+5V",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="HDMI 1.4 Sec 4.2.7: 100nF HF bypass at the +5V pin",
        ),
        # Shield-to-chassis discharge per HDMI 1.4 Sec 4.2.7 and the
        # generally-recommended 'soft' chassis bond used on most HDMI
        # implementations: 1Mohm bleeds static charge to chassis while
        # 100nF X7R provides a high-frequency EMI return path.
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="1M_0402_1%",
            justification="HDMI 1.4 Sec 4.2.7: 1Mohm DC bleed from connector "
                          "shell to chassis ground to drain static charge",
        ),
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="100n_0402_X7R",
            justification="HDMI 1.4 Sec 4.2.7: 100nF parallel cap provides HF "
                          "return path between shield and chassis (EMI compliance)",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # All TMDS, DDC, CEC, HPD pull-ups are integrated in TPD12S016.
        # The connector itself is purely passive on these pins.
        "TMDS_D0+", "TMDS_D0-",
        "TMDS_D1+", "TMDS_D1-",
        "TMDS_D2+", "TMDS_D2-",
        "TMDS_CLK+", "TMDS_CLK-",
        "CEC", "SCL", "SDA", "HPD",
        # Pin 14 (Reserved / HEC-) - unused in non-Ethernet HDMI.
        "RESERVED",
    }),
    layout_notes=(
        LayoutNote(
            text="TMDS pairs (D2, D1, D0, CLK): 100R differential impedance, "
                 "length-matched within 0.5mm intra-pair",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.3 (TMDS electrical)",
        ),
        LayoutNote(
            text="Inter-pair skew: max 2mm length difference between any two "
                 "TMDS pairs (D0, D1, D2 referenced to CLK)",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.3 timing margin",
        ),
        LayoutNote(
            text="Place TPD12S016 within 10mm of HDMI connector pin 1; route "
                 "TMDS straight through the protection device before any vias",
            severity="rule",
            justification="TPD12S016 DS Sec 10.1 (ESD must dissipate at protection pins)",
        ),
        LayoutNote(
            text="Connector shell legs route to CHASSIS_GND copper island only; "
                 "CHASSIS_GND joins signal GND at a single star point near the "
                 "carrier power-entry connector",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.7 / EMC ground-loop avoidance",
        ),
        LayoutNote(
            text="Keep DDC SDA/SCL traces <= 50mm long and away from the TMDS "
                 "pairs to avoid coupling 100kHz I2C edges onto the high-speed lines",
            severity="guideline",
            justification="HDMI 1.4 Sec 8.1",
        ),
    ),
)
