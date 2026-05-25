"""HDMI Type-A receptacle - HDMI 1.4 wiring with DDC EEPROM topology.

Datasheet: SOFNG HDMI-019S (mechanical only)
LCSC: C111617
HDMI Spec: HDMI Specification v1.4b, Sec 4.2 and Sec 8

Used twice on the carrier:
    - HDMI TX (source): TPD12S016 between Zynq and connector, +5V sourced out, DDC EEPROM with EDID
    - HDMI RX (sink): TPD12S016 between connector and Zynq, +5V sensed (from source)

Pin map (per HDMI 1.4 Sec 4.2):
    1-3   TMDS Data 2 +/- + shield
    4-6   TMDS Data 1 +/- + shield
    7-9   TMDS Data 0 +/- + shield
    10-12 TMDS Clock +/- + shield
    13    CEC
    14    Utility/HEC-
    15    SCL (DDC clock)
    16    SDA (DDC data)
    17    DDC/CEC GND
    18    +5V
    19    Hot Plug Detect
"""

from __future__ import annotations

from scripts.carrier.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)
from scripts.carrier.refcircuits._paths import local_datasheet_path


HDMI_A_REFCIRCUIT = ReferenceCircuit(
    part_mpn="HDMI-019S",
    lcsc="C111617",
    datasheet_url="https://datasheet.lcsc.com/lcsc/SOFNG-HDMI-019S_C111617.pdf",
    datasheet_revision="2022",
    app_circuit_figure="HDMI 1.4 Sec 4.2 / TPD12S016 DS Fig 13-14",
    local_datasheet_path=local_datasheet_path("HDMI-019S"),
    app_circuit_page="HDMI 1.4 Sec 4.2 + DDC pull-ups",
    minimum_circuit_verified=True,
    symbol_token="HDMI_A_Receptacle",
    footprint="Connector_HDMI:HDMI_A_SOFNG_HDMI-019S",
    description="HDMI Type-A receptacle, 19 pin",
    external_parts=(
        # 5V VBUS decoupling at connector
        ExternalPart(
            from_pin="+5V",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="HDMI Sec 4.2.7: 5V bypass at connector",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+5V",
            part_token="2k2_0402_1%",
            justification="HDMI 1.4 DDC: 2.2k SCL pull-up to +5V",
        ),
        ExternalPart(
            from_pin="SDA",
            to_net="+5V",
            part_token="2k2_0402_1%",
            justification="HDMI 1.4 DDC: 2.2k SDA pull-up to +5V",
        ),
        # CEC line pull-up (typically 27k to 3.3V, we approximate with 10k)
        ExternalPart(
            from_pin="CEC",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="HDMI 1.4 Sec 5.1: CEC line idle-high via pull-up",
        ),
        # HPD pull-up on sink side - moved to TPD12S016 sheet logic
        # Shield to chassis GND
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="1M_0402_1%",
            justification="HDMI 1.4 Sec 4.2.7: shield discharge to chassis",
        ),
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="100n_0402_X7R",
            justification="HDMI 1.4 Sec 4.2.7: shield AC bypass to chassis",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "TMDS_D0+", "TMDS_D0-", "TMDS_D1+", "TMDS_D1-",
        "TMDS_D2+", "TMDS_D2-", "TMDS_CLK+", "TMDS_CLK-",
        # TMDS pass straight through; termination is in source/sink IC
    }),
    layout_notes=(
        LayoutNote(
            text="TMDS pairs: 100 ohm differential impedance, length-matched within 0.5mm intra-pair",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.3",
        ),
        LayoutNote(
            text="Inter-pair skew: <= 2mm length difference between any two TMDS pairs",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.3",
        ),
        LayoutNote(
            text="Place TPD12S016 within 10mm of HDMI connector",
            severity="rule",
            justification="TPD12S016 DS Sec 11.1",
        ),
    ),
)
