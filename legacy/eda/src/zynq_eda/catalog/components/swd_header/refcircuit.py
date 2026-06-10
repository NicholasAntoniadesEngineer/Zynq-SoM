"""HANXIA HX-PZ1.27-2x5P-TP - 2x5 (10-position) 1.27 mm pin header (ARM Cortex SWD).

Datasheet: HANXIA HX-PZ1.27 series mechanical drawing, distributed
locally as ``components/swd_header/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/hanxia-HX-PZ1-27-2x5P-TP_C41376037.pdf

A 1.27 mm pitch, 2x5 (10-position) through-hole pin header matching the
ARM Cortex Debug Connector standard (ARM Debug Interface v5.2). Used on
the carrier to expose the STM32 power-controller MCU's SWD interface.

Mechanical highlights (catalog page 1):
    - Current rating: 1.0 A per contact
    - Withstand voltage: 500 V AC
    - Contact material: brass, gold flash plated
    - Operating temperature: -40 to +105 deg C

Pin map (ARM Cortex Debug Connector, 10-pin SWD subset):
    1   VTREF        - target I/O reference (+3V3)
    2   SWDIO        - serial wire data (bidirectional)
    3   GND
    4   SWCLK        - serial wire clock (host -> target)
    5   GND
    6   SWO          - SWO trace output (target -> host) - optional
    7   KEY          - mechanical key (no electrical connection)
    8   NC / TDI     - JTAG TDI when in JTAG mode; NC for pure SWD
    9   GNDDetect    - GND (also used by some debuggers as a target-present sense)
    10  nRESET       - target reset (open-drain bidirectional)

ARM Debug Interface v5.2 requires the target to provide pull-up resistors
on SWDIO and nRESET so the lines float to a deterministic state when
the debugger is disconnected. The SWO line, when used, is a high-Z
output and needs no host-side bias.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


SWD_HEADER_REFCIRCUIT = ReferenceCircuit(
    part_mpn="HX-PZ1.27-2x5P-TP",
    lcsc="C41376037",
    datasheet_url="https://datasheet.lcsc.com/lcsc/hanxia-HX-PZ1-27-2x5P-TP_C41376037.pdf",
    datasheet_revision="HANXIA HX-PZ1.27 series mechanical drawing, 2020-06",
    app_circuit_figure="ARM Debug Interface v5.2 - 10-pin Cortex Debug Connector",
    local_datasheet_path="components/swd_header/datasheet.pdf",
    app_circuit_page="HX-PZ1.27 mechanical p. 1 + ARM ADI v5.2 Sec B5.2.2",
    minimum_circuit_verified=True,
    symbol_token="SWD_2x5",
    footprint="Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical",
    description="2x5 1.27 mm pin header (ARM Cortex 10-pin Debug Connector for STM32 SWD)",
    supply_rail="+3V3",
    external_parts=(
        # ARM ADI v5.2 mandates a target-side pull-up on SWDIO (10k typical).
        ExternalPart(
            from_pin="SWDIO",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="ARM ADI v5.2 Sec B5.2.2: SWDIO target-side pull-up to VTREF",
        ),
        # nRESET is open-drain bidirectional; target-side pull-up holds it
        # high when debugger is disconnected.
        ExternalPart(
            from_pin="nRESET",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="ARM ADI v5.2: nRESET pull-up so target boots when debugger is removed",
        ),
        # 100nF cap on nRESET adds debounce against probe glitches.
        ExternalPart(
            from_pin="nRESET",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="STM32 AN2606 / RM0008 reset network: 100nF debounce cap on nRST",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # SWCLK is host-driven push-pull; needs no target-side bias.
        "SWCLK",
        # SWO is target-driven push-pull output.
        "SWO",
        # KEY pin is mechanically blanked off (no electrical connection).
        "KEY",
        "VCC", "GND",
    }),
    layout_notes=(
        LayoutNote(
            text="Place the 10k SWDIO and nRESET pull-ups within 10 mm of the "
                 "header so the bias network is short",
            severity="rule",
            justification="ARM ADI v5.2 host-side biasing recommendation",
        ),
        LayoutNote(
            text="Keep SWD trace length under 50 mm; signals run at up to "
                 "10 MHz so transmission-line effects on long cables matter",
            severity="rule",
            justification="ST AN4989 'Getting started with SWD' Sec 4",
        ),
        LayoutNote(
            text="Pin 7 must remain mechanically blanked (key pin) - do not "
                 "use it as an electrical connection",
            severity="rule",
            justification="ARM Cortex Debug Connector keying spec",
        ),
        LayoutNote(
            text="Route SWD signals away from the LVDS LCD and HDMI clocks - "
                 "SWD probes are unshielded and pick up coupling easily",
            severity="guideline",
        ),
    ),
)
