"""Hirose DM3AT-SF-PEJM5 - microSD push-push card socket.

Datasheet: Hirose DM3 series catalog (Aug 2020), distributed locally as
``components/microsd/datasheet.pdf``. URL:
https://www.hirose.com/en/product/document?clcode=CL0540-1284-2-51&productname=DM3AT-SF-PEJM5(51)&series=DM3
SDIO reference: SD Specifications - Part 1: Physical Layer Simplified
Specification (SD Association).

Push-push top-mount microSD socket with built-in mechanical card-detect
switch. Interfaces directly with the Zynq PS SDIO peripheral (SD1) via
SoM J1 in 4-bit mode.

Pin map (DM3AT-SF-PEJM5 catalog page 3):
    1   DAT2
    2   CD/DAT3          (DAT3 in SDIO 4-bit mode; doubles as host-side CD
                          when card uses internal pull-up on DAT3)
    3   CMD
    4   VDD              (2.7-3.6 V card supply)
    5   CLK
    6   VSS              (GND)
    7   DAT0
    8   DAT1
    A   DET_A            (mechanical card-detect switch terminal A;
                          normally open, closed to DET_B when card inserted)
    B   DET_B            (mechanical card-detect switch terminal B)

The DM3 datasheet has no electrical reference circuit (the connector is
purely passive); the supporting passives below come from the SD
Specification Part 1.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


MICROSD_DM3AT_REFCIRCUIT = ReferenceCircuit(
    part_mpn="DM3AT-SF-PEJM5",
    lcsc="C114218",
    datasheet_url="https://www.hirose.com/en/product/document?clcode=CL0540-1284-2-51&productname=DM3AT-SF-PEJM5(51)&series=DM3",
    datasheet_revision="DM3 series catalog, 2020-08",
    app_circuit_figure="SD Spec Part 1 Sec 4.5 'SD Bus Topology' + Sec 6.3 power; DM3AT catalog p. 3",
    local_datasheet_path="components/microsd/datasheet.pdf",
    app_circuit_page="DM3AT catalog p. 3 + SD Phys Layer Sec 6.3-6.5",
    minimum_circuit_verified=True,
    symbol_token="microSD_DM3AT",
    footprint="Connector_Card:microSD_HiroseDM3AT-SF-PEJM5_Push-Push",
    description="microSD push-push card socket with mechanical card-detect switch",
    supply_rail="+3V3",
    external_parts=(
        # VDD bulk decoupling - SD spec requires the host to source >150 mA
        # transients at card insertion. A 4.7uF bulk cap absorbs the inrush.
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="4u7_0402_X5R",
            justification="SD Spec Part 1 Sec 6.3: 4.7uF bulk cap for card insertion transients",
        ),
        # VDD high-frequency bypass.
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="SD Spec Part 1 Sec 6.3: 100nF VDD HF bypass at the socket",
        ),
        # SDIO data pull-ups - SD Spec recommends 10k-100k on every DAT and
        # CMD line. The Zynq PS SDIO controller has internal pull-ups but
        # they are not guaranteed across all PS clock modes, so we explicitly
        # add them on the carrier side.
        ExternalPart(
            from_pin="DAT0",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="SD Spec Part 1 Sec 6.5: DAT0 pull-up (10-100k recommended)",
        ),
        ExternalPart(
            from_pin="DAT1",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="SD Spec Part 1 Sec 6.5: DAT1 pull-up (10-100k recommended)",
        ),
        ExternalPart(
            from_pin="DAT2",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="SD Spec Part 1 Sec 6.5: DAT2 pull-up (10-100k recommended)",
        ),
        ExternalPart(
            from_pin="DAT3/CD",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="SD Spec Part 1 Sec 6.5: DAT3/CD pull-up (also enables card-internal CD)",
        ),
        ExternalPart(
            from_pin="CMD",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="SD Spec Part 1 Sec 6.5: CMD pull-up (10-100k recommended)",
        ),
        # Mechanical card-detect switch: DET_A is tied to GND on the block
        # sheet, DET_B is the host-side CD_N signal that needs a pull-up
        # so the host reads a clean high when no card is inserted.
        ExternalPart(
            from_pin="DET_B",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Mechanical CD switch is open-when-empty; pull-up biases host GPIO high",
        ),
    ),
    strap_pins=(),
    # CLK is a push-pull host output - no pull-up required (the SD card
    # presents a high-Z input). SHIELD is tied to GND on the block sheet.
    no_external_required=frozenset({"CLK", "SHIELD", "VSS"}),
    layout_notes=(
        LayoutNote(
            text="Length-match SDIO_CLK to CMD and DAT[0..3] within 5 mm",
            severity="rule",
            justification="SD Spec Part 1 Sec 6.5: SDIO timing margin at UHS speeds",
        ),
        LayoutNote(
            text="Keep all SDIO signal traces under 50 mm; route them as a "
                 "tight bundle with 4-5 mil spacing over a solid ground plane",
            severity="rule",
            justification="SD Spec Part 1 Sec 6.5: crosstalk and rise-time control",
        ),
        LayoutNote(
            text="Place the 22 ohm series terminations near the host SoM "
                 "(already provided inside the SoM); no series Rs on the carrier",
            severity="info",
            justification="SoM-internal termination — carrier carries only pull-ups + bulk caps",
        ),
        LayoutNote(
            text="Tie the connector metal shield to the carrier GND plane "
                 "through a short, low-inductance trace or via fence",
            severity="rule",
            justification="DM3 datasheet 'Effective ground and shield configuration' feature; EMI compliance",
        ),
    ),
)
