"""Kinghelm KH-SMA-P-8496 - SMA female PCB right-angle 50 ohm connector.

Datasheet: Kinghelm KH-SMA-P-8496 mechanical drawing, distributed
locally as ``components/sma_clock/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/kinghelm-KH-SMA-P-8496_C910123.pdf

A standard 50 ohm SMA female receptacle, right-angle PCB mount,
1/4''-36UNS-2B threaded interface, gold-plated centre pin. Used on the
carrier as the external clock input for the Zynq XADC (the external
reference clock allows synchronous sampling at >= 1 MSPS) or the FPGA
PL clock-capable MRCC input.

Mechanical highlights (catalog page 1):
    - Body: brass with nickel plate
    - Centre contact: brass with gold plate (PTFE insulator)
    - Mounting: 4-leg through-hole, 5 PCB legs total
    - Threading: 1/4''-36 UNS-2B (SMA standard)

The datasheet provides no electrical reference circuit (the connector
is a passive 50 ohm RF receptacle). The recommended interface for an
external CMOS or LVCMOS clock driving the Zynq XADC / MRCC is taken
from Xilinx UG480 'XADC User Guide' and AR# 53353 'Driving XADC clock':

    SMA centre  ---||--- (50 ohm trace) ---+--- to XADC_DCLK / MRCC pin
                  10 nF                    |
                                          === 49.9R to GND (parallel)
                                           |
                                          GND

The 10 nF AC-couples the input (the XADC clock pin is a CMOS input but
the external source is often AC-coupled to allow either 0-3.3V or
sine-wave sources). The 49.9R sets a 50 ohm parallel termination to
match the cable.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


SMA_CLOCK_REFCIRCUIT = ReferenceCircuit(
    part_mpn="KH-SMA-P-8496",
    lcsc="C910123",
    datasheet_url="https://datasheet.lcsc.com/lcsc/kinghelm-KH-SMA-P-8496_C910123.pdf",
    datasheet_revision="Kinghelm KH-SMA-P-8496 mechanical drawing, 2018-03",
    app_circuit_figure="Xilinx UG480 XADC external clock + AR# 53353",
    local_datasheet_path="components/sma_clock/datasheet.pdf",
    app_circuit_page="KH-SMA-P-8496 mechanical p. 1 + UG480 Sec 4 'XADC Clock'",
    minimum_circuit_verified=True,
    symbol_token="SMA_RA_TH",
    footprint="Connector_Coaxial:SMA_Amphenol_132289-14_Vertical",
    description="SMA female right-angle 50 ohm PCB connector (external clock input)",
    external_parts=(
        # AC-coupling cap: 10 nF presents a low impedance from ~1 MHz up.
        # For very low frequency clocks (< 1 MHz) bump this to 100 nF.
        ExternalPart(
            from_pin="CENTER",
            to_net="XADC_CLK_AC",
            part_token="10n_0402_X7R",
            justification="UG480 / AR# 53353: AC coupling cap on external XADC clock",
        ),
        # 50 ohm parallel termination to GND. 49.9R is the closest E96 value.
        ExternalPart(
            from_pin="XADC_CLK_AC",
            to_net="GND",
            part_token="49R9_0402_1%",
            justification="50 ohm parallel termination to match SMA cable impedance",
        ),
        # Optional DC-restore pull-up to mid-rail (1.65V) for sine-wave sources.
        # When driven by a single-ended LVCMOS source, this pair pulls the
        # AC-coupled signal to mid-rail so the receiver sees a CMOS swing.
        # On this carrier the FPGA is configured for LVCMOS33 input - we
        # omit the divider and let the user populate it if needed.
        # Coaxial shell goes to GND via the connector body - no external
        # part required for the shield.
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # The connector shell ties to GND through the body lugs - no part.
        "SHELL", "GND",
    }),
    layout_notes=(
        LayoutNote(
            text="Route the SMA centre-pin trace as 50 ohm controlled "
                 "impedance microstrip with continuous GND reference",
            severity="rule",
            justification="SMA is a 50 ohm interface; impedance discontinuities cause reflections",
        ),
        LayoutNote(
            text="Place the AC-coupling cap and termination resistor within "
                 "5 mm of the SMA centre pin",
            severity="rule",
            justification="Lumped passives must sit close to the connector to preserve impedance",
        ),
        LayoutNote(
            text="Tie all four mechanical mounting lugs to the GND plane "
                 "with short, low-inductance traces (or directly to the plane via pad)",
            severity="rule",
            justification="RF shield continuity",
        ),
        LayoutNote(
            text="Avoid 90 degree corners on the centre-pin trace; use two "
                 "45 degree turns or a smooth curve instead",
            severity="guideline",
            justification="High-frequency impedance discontinuity",
        ),
    ),
)
