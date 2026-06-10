"""XFCN PM254R-12-08-H85 - 2x6 right-angle female pin header (Digilent PMOD).

Datasheet: XFCN PM254V-12-XX-H85 series mechanical drawing, distributed
locally as ``components/pmod/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/XFCN-PM254R-12-08-H85_C53026548.pdf

A 2.54 mm pitch, 2x6 (12-position) right-angle female header used as a
Digilent-standard PMOD socket. Purely passive - no electrical components
required at the connector. Electrical contract is defined by Digilent's
PMOD Interface Specification Rev E (Type 1A: 8 single-ended GPIO + GND +
3V3).

Mechanical highlights (catalog page 1):
    - Voltage rating: 250 V AC/DC
    - Current rating: 3 A AC/DC per contact
    - Operating temperature: -40 to +105 deg C
    - Contact material: brass with Sn-on-Ni plating

Pin map (Digilent PMOD Type 1A, top-row 1-6, bottom-row 7-12 looking
into the socket from the daughtercard side):
    1   IO0
    2   IO1
    3   IO2
    4   IO3
    5   GND
    6   +3V3
    7   IO4
    8   IO5
    9   IO6
    10  IO7
    11  GND
    12  +3V3

There are no required external passives at the PMOD socket - all
buffering, level translation, or pull-ups are the responsibility of the
PMOD daughtercard. This refcircuit therefore declares an empty
``external_parts`` and the audit explicitly allows that via
``_ZERO_EXTERNAL_ALLOWED`` (audit.py).
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import LayoutNote, ReferenceCircuit


PMOD_REFCIRCUIT = ReferenceCircuit(
    part_mpn="PM254R-12-08-H85",
    lcsc="C53026548",
    datasheet_url="https://datasheet.lcsc.com/lcsc/XFCN-PM254R-12-08-H85_C53026548.pdf",
    datasheet_revision="XFCN PM254V-12-XX-H85 series, 2010-04",
    app_circuit_figure="Digilent PMOD Interface Spec Rev E (Type 1A)",
    local_datasheet_path="components/pmod/datasheet.pdf",
    app_circuit_page="Digilent PMOD Spec Sec 2 - Type 1A pinout (no required passives)",
    minimum_circuit_verified=True,
    symbol_token="PMOD_2x6_RA",
    footprint="Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical",
    description="Digilent PMOD 2x6 right-angle female header (Type 1A, 8 GPIO + 3V3 + GND)",
    supply_rail="+3V3",
    external_parts=(),
    no_external_required=frozenset({
        "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7",
        "VCC", "GND",
    }),
    layout_notes=(
        LayoutNote(
            text="PMOD signal pins are 3.3V LVCMOS - never drive 5V into them",
            severity="rule",
            justification="Digilent PMOD Interface Spec Rev E Sec 2 (Type 1A signalling)",
        ),
        LayoutNote(
            text="Series-terminate (33 ohm) high-speed PMOD signals at the host "
                 "SoM if the PMOD daughtercard drives clocks >= 25 MHz",
            severity="guideline",
            justification="Digilent PMOD Spec Sec 4: signal integrity recommendation",
        ),
        LayoutNote(
            text="Decouple +3V3 with 10uF + 100nF within 5 mm of the connector "
                 "to absorb PMOD daughtercard inrush (handled at the carrier "
                 "+3V3 rail, not per-PMOD)",
            severity="info",
            justification="Digilent PMOD Spec Sec 3: power rating 1A total per PMOD",
        ),
        LayoutNote(
            text="Place the two PMOD connectors edge-aligned with the carrier "
                 "outline so PMOD daughtercards fold cleanly off the board",
            severity="guideline",
        ),
    ),
)
