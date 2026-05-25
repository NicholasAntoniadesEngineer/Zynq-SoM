"""Amphenol RJHSE5380 - Bare shielded RJ45 with LEDs (no magnetics).

Datasheet: Amphenol RJHSE5380 series
URL: https://www.amphenol-cs.com/product-series/rjhse5380.html
Package: RJ45 through-hole right-angle

Bare shielded 8P8C RJ45 socket with two integrated LED windows
(Green/Yellow typical). Used with separate Pulse HX5008NLT magnetics
module - allows scope probing of the MDI signals between PHY and
magnetics for debug.

Pin map (per RJ45 standard / RJHSE5380 datasheet):
    1-8  Signal contacts (paired via TIA-568B: TX+/TX-/RX+/RX- + GbE 2 more pairs)
    9    LED1 anode (left LED)
    10   LED1 cathode
    11   LED2 anode (right LED)
    12   LED2 cathode
    SH1-SH4  Shield tabs (chassis GND)

For 1000BASE-T the four pairs are MDI0/1/2/3 (bidirectional).
LEDs drive 5-20mA typical (need series resistor).
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


RJ45_REFCIRCUIT = ReferenceCircuit(
    part_mpn="RJHSE5380",
    lcsc="C464586",
    datasheet_url="https://www.amphenol-cs.com/product-series/rjhse5380.html",
    datasheet_revision="2023",
    app_circuit_figure="Amphenol RJHSE5380 datasheet, pin diagram",
    local_datasheet_path="components/rj45/datasheet.pdf",
    app_circuit_page="Amphenol RJHSE5380 datasheet, pin diagram",
    minimum_circuit_verified=True,
    symbol_token="RJ45_RJHSE5380",
    footprint="Connector_RJ:RJ45_Amphenol_RJHSE5380_Horizontal",
    description="Bare shielded RJ45 with 2 integrated LEDs, right-angle TH",
    external_parts=(
        # LED1 (Green - Link/1000): anode -> +3V3 via 330 ohm
        ExternalPart(
            from_pin="LED1_A",
            to_net="+3V3",
            part_token="330R_0402_1%",
            justification="LED current limit: 3.3V - 2.2V Vf / 330R ~ 3mA (Green Link)",
        ),
        # LED2 (Yellow - Activity): anode -> +3V3 via 330 ohm
        ExternalPart(
            from_pin="LED2_A",
            to_net="+3V3",
            part_token="330R_0402_1%",
            justification="LED current limit: 3.3V - 2.0V Vf / 330R ~ 4mA (Yellow Activity)",
        ),
        # Shield tabs -> CHASSIS_GND directly (no caps)
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N",
        "MDI2_P", "MDI2_N", "MDI3_P", "MDI3_N",
    }),
    layout_notes=(
        LayoutNote(
            text="Connect shield tabs (SH1..SH4) directly to CHASSIS_GND copper pour",
            severity="rule",
            justification="EMI compliance",
        ),
        LayoutNote(
            text="Keep RJ45 within 30mm of HX5008NLT magnetics; route MDI pairs as 100R differential",
            severity="rule",
            justification="IEEE 802.3 / Pulse layout guide",
        ),
    ),
)
