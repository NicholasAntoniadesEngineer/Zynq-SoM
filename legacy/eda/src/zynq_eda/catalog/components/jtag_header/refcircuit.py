"""Megastar ZX-PM2.54-2-7PY - 2x7 (14-position) 2.54 mm pin header (Xilinx JTAG).

Datasheet: Megastar / Zhaoxing ZX-PM2.54 series mechanical drawing,
distributed locally as ``components/jtag_header/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/Megastar-ZX-PM2-54-2-7PY_C7499342.pdf

A 2.54 mm pitch, 2x7 (14-position) 'Y-type' through-hole pin header
following the standard Xilinx Platform Cable USB / DLC9LP pin convention
documented in Xilinx UG470 (7 Series FPGAs Configuration User Guide,
Sec 3 'Programming Cables').

Mechanical highlights (catalog page 1):
    - Current rating: 3 A per contact
    - Withstand voltage: 1000 V AC
    - Contact material: brass, gold flash plated
    - Operating temperature: -40 to +105 deg C

Pin map (Xilinx UG470 14-pin JTAG header):
    1   VREF       - host I/O reference voltage (carrier-side: +3V3)
    2   TMS        - test mode select
    3   GND
    4   TCK        - test clock
    5   GND
    6   TDO        - test data out (DUT -> host)
    7   GND
    8   TDI        - test data in  (host -> DUT)
    9   GND
    10  N.C.
    11  N.C.
    12  N.C.
    13  N.C.
    14  N.C.

(Note: pin 4 is TCK and pin 6 is TDO in the official Xilinx layout. The
KiCad symbol in ``shared/symbols/zynq_eda.kicad_sym`` collapses several
GND pins; the carrier block in ``projects/carrier/blocks/jtag_swd.py``
exposes only VCC/TDI/GND/TMS/TCK/TDO.)

IEEE 1149.1 recommends a host-side pull-up on TMS and TDI to drive the
DUT TAP controller into a deterministic state when the programming cable
is disconnected. We add 10k pull-ups on each.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


JTAG_HEADER_REFCIRCUIT = ReferenceCircuit(
    part_mpn="ZX-PM2.54-2-7PY",
    lcsc="C7499342",
    datasheet_url="https://datasheet.lcsc.com/lcsc/Megastar-ZX-PM2-54-2-7PY_C7499342.pdf",
    datasheet_revision="Megastar ZX-PM2.54 series mechanical drawing, 2022",
    app_circuit_figure="Xilinx UG470 Sec 3 'Programming Cables' + IEEE 1149.1 host-side biasing",
    local_datasheet_path="components/jtag_header/datasheet.pdf",
    app_circuit_page="ZX-PM2.54 mechanical p. 1 + IEEE 1149.1 Sec 5",
    minimum_circuit_verified=True,
    symbol_token="JTAG_2x7",
    footprint="Connector_PinHeader_2.54mm:PinHeader_2x07_P2.54mm_Vertical",
    description="2x7 2.54 mm pin header (Xilinx UG470 PS JTAG pinout)",
    supply_rail="+3V3",
    external_parts=(
        # IEEE 1149.1 host-side pull-ups on TMS and TDI - keeps the TAP
        # controller in a known state (Run-Test/Idle eventually) when the
        # programmer is disconnected.
        ExternalPart(
            from_pin="TMS",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="IEEE 1149.1 Sec 5: TMS pull-up to drive TAP into Test-Logic-Reset",
        ),
        ExternalPart(
            from_pin="TDI",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="IEEE 1149.1 Sec 5: TDI pull-up for deterministic input data",
        ),
        # Optional 22-100 ohm series resistors close to the header on TCK
        # and TMS to dampen reflections on the dangling cable. Xilinx
        # UG470 recommends but does not require these.
        ExternalPart(
            from_pin="TCK",
            to_net="PL_TCK",
            part_token="22R_0402_1%",
            justification="UG470 Sec 3: 22 ohm series on TCK for ringing control on long cables",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # TDO is a high-Z output from the DUT - no host-side bias needed.
        "TDO",
        # VCC / GND have decoupling at the SoM regulator output.
        "VCC", "GND",
    }),
    layout_notes=(
        LayoutNote(
            text="Keep all JTAG traces under 50 mm and isolate from PS clocks "
                 "(memory clock, USB ref clock) by 10+ mm",
            severity="rule",
            justification="UG470 Sec 3: JTAG signal integrity",
        ),
        LayoutNote(
            text="Place the 10k pull-ups on TMS and TDI within 5 mm of the header",
            severity="rule",
            justification="IEEE 1149.1 host-side bias placement",
        ),
        LayoutNote(
            text="Route the 14-pin header so pin 1 (VREF) is clearly marked - "
                 "incorrect cable orientation drives 3.3V into TDO",
            severity="rule",
        ),
        LayoutNote(
            text="GND pins on the header (3, 5, 7, 9) should be stitched to "
                 "the carrier GND plane with multiple vias for return-current "
                 "control during TCK toggling",
            severity="guideline",
        ),
    ),
)
