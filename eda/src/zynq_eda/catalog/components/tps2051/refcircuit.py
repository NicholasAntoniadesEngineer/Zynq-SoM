"""TPS2051CDBVR - USB current-limited power switch.

Datasheet: Texas Instruments TPS2051C, Rev May 2014
URL: https://www.ti.com/lit/ds/symlink/tps2051c.pdf
Package: SOT-23-5 (DBV)

USB host VBUS load switch with 0.5A current limit and active-high
fault flag. Used to source 5V VBUS to the USB-A host receptacle from
VIN_5V; protects against overcurrent and short circuit conditions.

Pin map (per datasheet):
    1  IN     - 5V input
    2  GND
    3  /EN    - Enable input (active low)
    4  /OC    - Overcurrent fault flag (open drain, active low)
    5  OUT    - 5V output to USB connector
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


TPS2051_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TPS2051CDBVR",
    lcsc="C129581",
    datasheet_url="https://www.ti.com/lit/ds/symlink/tps2051c.pdf",
    datasheet_revision="Rev May 2014",
    app_circuit_figure="Figure 8-1 - Typical Application Circuit",
    local_datasheet_path="components/tps2051/datasheet.pdf",
    app_circuit_page="Figure 8-1 - Typical Application Circuit",
    minimum_circuit_verified=True,
    symbol_token="TPS2051CDBVR",
    footprint="Package_TO_SOT_SMD:SOT-23-5",
    description="USB current-limited load switch 0.5A, SOT-23-5",
    external_parts=(
        # Input cap (DS Sec 8.2.2.1)
        ExternalPart(
            from_pin="IN",
            to_net="GND",
            part_token="1u_0402_X7R",
            justification="DS Sec 8.2.2.1: 1uF ceramic on IN pin",
        ),
        # Output cap (DS Sec 8.2.2.1) - 150uF max, use 100uF for headroom
        ExternalPart(
            from_pin="OUT",
            to_net="GND",
            part_token="100u_1206_X5R",
            justification="DS Sec 8.2.2.1: 1-150uF on OUT pin; meets USB 2.0 Vbus capacitance",
        ),
        # /OC fault flag pull-up to logic VCC (open drain output)
        ExternalPart(
            from_pin="OC_N",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="DS Sec 7.3.2: /OC is open-drain, requires pull-up to logic supply",
        ),
        # /EN active-low: typical use is direct GPIO drive; pull to GND through 10k if floating
        # We use a 10k pull-up to keep disabled by default, GPIO pulls low to enable
        ExternalPart(
            from_pin="EN_N",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="DS Sec 7.3.1: /EN default state high (disabled); GPIO pulls low to enable",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset(),
    layout_notes=(
        LayoutNote(
            text="Output cap >= 1uF, <= 150uF; place close to OUT pin for transient response",
            severity="rule",
            justification="DS Sec 8.2.2.1",
        ),
    ),
)
