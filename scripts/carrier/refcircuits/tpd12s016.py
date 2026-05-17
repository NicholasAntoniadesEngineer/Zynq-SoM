"""TPD12S016PWR - HDMI companion chip: ESD + level-shifter + load switch.

Datasheet: Texas Instruments TPD12S016, Rev May 2017
URL: https://www.ti.com/lit/ds/symlink/tpd12s016.pdf
Package: TSSOP-24 (PW)

The TPD12S016 provides everything an HDMI source/sink port needs:
    - ESD protection on TMDS lanes (12 channels)
    - 5V to 3.3V level shift for HPD (Hot-Plug Detect)
    - 5V to 3.3V level shift for I2C (DDC)
    - 5V VCC load switch with current limit (HDMI sourcing only)

Two instances on the carrier:
    - TPD12S016PWR_TX: HDMI source (Zynq drives, supplies +5V)
    - TPD12S016PWR_RX: HDMI sink (Zynq receives, no +5V switch needed)

The difference between TX and RX wiring is the +5V VBUS handling:
    - TX: HDMI_5V_OUT enabled via CT_CP_HPD, sources 5V to connector
    - RX: HDMI_5V_IN comes from external source; CT_CP_HPD = NC

Pin map (per datasheet Table 1):
    1  CEC_A   - CEC source side
    2  HPD_A   - HPD source side (5V level)
    3  GND
    4  SDA_A   - DDC SDA source side (5V level)
    5  SCL_A   - DDC SCL source side
    6  CT_CP_HPD - HPD direction control + 5V switch enable
    7  HPD_B   - HPD MCU side (3.3V)
    8  GND
    9  SDA_B   - DDC SDA MCU side (3.3V)
    10 SCL_B   - DDC SCL MCU side (3.3V)
    11 CEC_B   - CEC MCU side (3.3V)
    12 GND
    13 D2-, D2+ ... TMDS data channels (ESD)
    ... (TMDS pins 13-24)
"""

from __future__ import annotations

from scripts.carrier.core.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


_COMMON_DECOUPLING = (
    ExternalPart(
        from_pin="VCCA",  # 5V supply side
        to_net="GND",
        part_token="1u_0402_X7R",
        justification="DS Sec 9.2: VCCA (5V) bulk decoupling",
    ),
    ExternalPart(
        from_pin="VCCA",
        to_net="GND",
        part_token="100n_0402_X7R",
        justification="DS Sec 9.2: VCCA HF bypass",
    ),
    ExternalPart(
        from_pin="VCCB",  # 3.3V logic side
        to_net="GND",
        part_token="1u_0402_X7R",
        justification="DS Sec 9.2: VCCB (3.3V logic) bulk decoupling",
    ),
    ExternalPart(
        from_pin="VCCB",
        to_net="GND",
        part_token="100n_0402_X7R",
        justification="DS Sec 9.2: VCCB HF bypass",
    ),
)

_COMMON_PULLUPS = (
    # I2C pull-ups (MCU side - SDA_B / SCL_B) - 4.7k to VCCB (3.3V)
    ExternalPart(
        from_pin="SDA_B",
        to_net="+3V3",
        part_token="4k7_0402_1%",
        justification="DS Sec 8.3.3: I2C MCU-side pull-up to VCCB",
    ),
    ExternalPart(
        from_pin="SCL_B",
        to_net="+3V3",
        part_token="4k7_0402_1%",
        justification="DS Sec 8.3.3: I2C MCU-side pull-up to VCCB",
    ),
    # HPD MCU side pull-down (per DS Sec 8.3.4)
    ExternalPart(
        from_pin="HPD_B",
        to_net="GND",
        part_token="100k_0402_1%",
        justification="DS Sec 8.3.4: HPD_B pull-down (MCU input)",
    ),
)

TPD12S016_TX_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TPD12S016PWR",
    lcsc="C201665",
    datasheet_url="https://www.ti.com/lit/ds/symlink/tpd12s016.pdf",
    datasheet_revision="Rev May 2017",
    app_circuit_figure="Figure 13 - HDMI Source Application",
    symbol_token="TPD12S016PWR",
    footprint="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
    description="HDMI source companion: ESD + I2C/HPD level shift + 5V switch",
    external_parts=(
        *_COMMON_DECOUPLING,
        *_COMMON_PULLUPS,
        # CT_CP_HPD pull-up for level shifter direction control (TX side)
        ExternalPart(
            from_pin="CT_CP_HPD",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="DS Sec 8.3.4: CT_CP_HPD GPIO controls direction + 5V switch",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # TMDS data lines pass through with internal ESD; no external R/C
        "D0+", "D0-", "D1+", "D1-", "D2+", "D2-", "CLK+", "CLK-",
    }),
    layout_notes=(
        LayoutNote(
            text="Place TPD12S016 between HDMI connector and Zynq PL within 20mm of connector",
            severity="rule",
            justification="DS Sec 11.1 - ESD protection must precede device",
        ),
        LayoutNote(
            text="TMDS pairs: 100 ohm differential, length-match within 0.5mm across pairs",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.3",
        ),
    ),
)


TPD12S016_RX_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TPD12S016PWR",
    lcsc="C201665",
    datasheet_url="https://www.ti.com/lit/ds/symlink/tpd12s016.pdf",
    datasheet_revision="Rev May 2017",
    app_circuit_figure="Figure 14 - HDMI Sink Application",
    symbol_token="TPD12S016PWR",
    footprint="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
    description="HDMI sink companion: ESD + I2C/HPD level shift (no 5V switch)",
    external_parts=(
        *_COMMON_DECOUPLING,
        *_COMMON_PULLUPS,
        # CT_CP_HPD tied to GND in sink-only mode (level shifters always active TX->RX direction)
        ExternalPart(
            from_pin="CT_CP_HPD",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="DS Sec 8.3.4: CT_CP_HPD always-on for sink mode",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "D0+", "D0-", "D1+", "D1-", "D2+", "D2-", "CLK+", "CLK-",
    }),
    layout_notes=(
        LayoutNote(
            text="HDMI RX 5V comes from connected source, not generated locally",
            severity="info",
        ),
        LayoutNote(
            text="TMDS RX termination: 50 ohm to AVCC inside Zynq RX block; do NOT add external Rs",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.5",
        ),
    ),
)
