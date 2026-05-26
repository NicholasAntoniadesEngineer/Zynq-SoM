"""XUNPU FPC-05F-40PH20 - 40-pin 0.5 mm pitch FFC/FPC connector for LVDS LCD.

Datasheet: XUNPU FPC-05F-40PH20 mechanical drawing, distributed locally
as ``components/lvds_lcd/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/XUNPU-FPC-05F-40PH20_C2856812.pdf

Right-angle SMT FFC receptacle with 40 contacts on a 0.5 mm pitch.
Pure-mechanical part; the carrier carries the electrical termination
network for the LVDS panel link plus the panel-control pull-ups.

The actual pinout used on the carrier is *not* defined by the connector
datasheet (FFC connectors are panel-driven); it is a single-link 4-lane
LVDS panel interface that mirrors the common Innolux / Chimei FFC
schedule:

    1   GND
    2-3 +3V3 (panel logic supply)
    4   EDID_SDA
    5   EDID_SCL
    6   GND
    7   LVDS_CLK-
    8   LVDS_CLK+
    9   GND
    10  LVDS_DATA0-
    11  LVDS_DATA0+
    12  GND
    13  LVDS_DATA1-
    14  LVDS_DATA1+
    15  GND
    16  LVDS_DATA2-
    17  LVDS_DATA2+
    18  GND
    19  LVDS_DATA3-
    20  LVDS_DATA3+
    21  GND
    22  RESET_N
    23  GND
    24  STBY_N
    25  PWM (backlight)
    26  BL_EN
    27-30 +12V (backlight)
    31-40 GND

The block sheet (``projects/carrier/blocks/lvds_lcd.py``) wires the FFC
pins to those nets. The connector's own symbol exposes only the four
high-speed pairs (CLK+/CLK-/DATA0+/DATA0-) plus power / ground; the
remaining lanes are routed inside the symbol implementation.

LVDS uses 350 mV differential swing per IEEE 1596.3 / TIA-644-A. The
parallel 100 ohm termination resistor must sit at the *receiver* (LCD
panel) end, but most modern panels integrate this. The two 100 ohm
resistors in this refcircuit are an extra safety termination at the
carrier-side connector for cable-length compensation.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


LVDS_LCD_REFCIRCUIT = ReferenceCircuit(
    part_mpn="FPC-05F-40PH20",
    lcsc="C2856812",
    datasheet_url="https://datasheet.lcsc.com/lcsc/XUNPU-FPC-05F-40PH20_C2856812.pdf",
    datasheet_revision="XUNPU FPC-05F-40PH20 mechanical drawing, 2022",
    app_circuit_figure="LVDS panel termination (IEEE 1596.3) + panel vendor reference",
    local_datasheet_path="components/lvds_lcd/datasheet.pdf",
    app_circuit_page="FFC mechanical p. 1 + IEEE 1596.3 termination",
    minimum_circuit_verified=True,
    symbol_token="FFC_40P_0.5mm",
    footprint="Connector_FFC-FPC:FPC-05F-40PH20",
    description="40-pin 0.5 mm pitch FFC receptacle for LVDS LCD panel",
    supply_rail="+3V3",
    external_parts=(
        # LVDS far-end terminations - 100 ohm differential across each pair
        # at the connector. Many integrated panels include this internally,
        # but adding it here lets the carrier drive an external panel
        # via a longer FFC. Resistor placed close to the connector.
        #
        # NOTE: from_pin/to_net values match the FFC_40P symbol's pin names
        # (see shared/symbols/zynq_eda.kicad_sym). When the carrier supplies
        # a pin_to_net map on ConnectorInstance, the symbol pin name
        # (e.g. "LVDS_CLK+") still has to exist on the symbol so cluster
        # placement can find its geometry. The to_net for non-net symbol
        # pin names is resolved via pin_to_net overrides.
        ExternalPart(
            from_pin="LVDS_CLK+",
            to_net="LVDS_CLK-",
            part_token="100R_0402_1%",
            justification="IEEE 1596.3 / TIA-644-A: 100 ohm differential termination at receiver",
        ),
        ExternalPart(
            from_pin="LVDS_DATA0+",
            to_net="LVDS_DATA0-",
            part_token="100R_0402_1%",
            justification="IEEE 1596.3 / TIA-644-A: 100 ohm differential termination at receiver",
        ),
        # +3V3 panel-logic bypass at the connector. ``+3V3`` is the
        # symbol pin name; pin_to_net wires it to the same net so
        # to_net="GND" lands on the global GND.
        ExternalPart(
            from_pin="+3V3",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="Bulk decoupling for panel logic supply at FFC",
        ),
        ExternalPart(
            from_pin="+3V3",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="HF bypass for panel logic supply at FFC",
        ),
        # +12V backlight bypass.
        ExternalPart(
            from_pin="+12V",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="Bulk decoupling for backlight rail at FFC",
        ),
        # EDID I2C pull-ups (carrier-owned, common 2.2k to 4.7k to +3V3).
        ExternalPart(
            from_pin="EDID_SCL",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="EDID I2C pull-up to +3V3 (panel side is open-drain)",
        ),
        ExternalPart(
            from_pin="EDID_SDA",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="EDID I2C pull-up to +3V3",
        ),
        # Backlight enable pull-down so the panel stays dark if the host
        # GPIO is floating (avoid bootup white-screen).
        ExternalPart(
            from_pin="BL_EN",
            to_net="GND",
            part_token="100k_0402_1%",
            justification="Backlight EN default-off pull-down (prevents flicker during reset)",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "LVDS_DATA1+", "LVDS_DATA1-",
        "LVDS_DATA2+", "LVDS_DATA2-",
        "LVDS_DATA3+", "LVDS_DATA3-",
        # Termination on remaining lanes is panel-internal.
    }),
    layout_notes=(
        LayoutNote(
            text="Route all LVDS pairs as 100 ohm differential controlled "
                 "impedance, intra-pair skew under 0.1 mm, inter-pair "
                 "under 1 mm",
            severity="rule",
            justification="IEEE 1596.3 / TIA-644-A LVDS signal integrity",
        ),
        LayoutNote(
            text="Place the LVDS termination resistors within 5 mm of the "
                 "connector pins on the panel side",
            severity="rule",
            justification="LVDS termination must sit at the receiver end",
        ),
        LayoutNote(
            text="Reference all LVDS pairs to an unbroken GND plane on the "
                 "adjacent layer; do not cross plane splits",
            severity="rule",
            justification="LVDS return-current control",
        ),
        LayoutNote(
            text="Separate +12V backlight power from the +3V3 logic supply on "
                 "the FFC (different layers if possible) to avoid PWM noise "
                 "coupling into logic",
            severity="guideline",
        ),
    ),
)
