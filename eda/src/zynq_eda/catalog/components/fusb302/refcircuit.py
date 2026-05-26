"""FUSB302BMPX - USB Type-C Port Controller with USB-PD (BMC physical layer).

Datasheet: ONsemi FUSB302B, Rev 5, Aug 2021
URL: https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf
Package: WQFN-14 (2.5x2.5mm, 0.5mm pitch, 1.45x1.45mm EP)

The FUSB302B integrates CC1/CC2 termination (5.1k Rd as device,
host pull-ups, VCONN switch), the USB-PD BMC PHY (CRC32/4b5b
transmitter and receiver), and an I2C slave that exposes all of
it to a host MCU. The chip is dual-role-capable (DRP toggle) but
we use it as a SNK on the USB-C input port.

External-part values come from the manufacturer reference schematic
(Figure 18 / Table 43, Recommended Component Values):

    C_VDD1   100nF VDD HF bypass     (Table 43)
    C_VDD2   1uF   VDD bulk          (Table 43)
    C_VCONN  100nF VCONN HF bypass   (Table 43)
    C_BULK   10uF  VCONN bulk        (Table 43, min 10uF)
    C_RECV   200pF on each CC pin    (Table 43, range 200-600pF)
    R_PU     4.7k  on SDA, SCL       (Table 43)
    R_PU_INT 4.7k  on INT_N          (Table 43, range 1-4.7k)

Pin map (per datasheet Figure 5, WQFN-14):
    1  CC2     - CC config-channel B (paired with pin 14)
    2  VBUS    - VBUS sense (5-21V detect, OVP-protected input)
    3  VDD     - 2.7-5.5V chip supply
    4  VDD     - (duplicate VDD pad)
    5  INT_N   - active-low open-drain interrupt
    6  SCL     - I2C clock (Fast-Mode-Plus up to 1MHz)
    7  SDA     - I2C data (open-drain)
    8  GND
    9  GND
    10 CC1     - CC config-channel A (paired with pin 11)
    11 CC1
    12 VCONN   - VCONN supply input (switched to active CC pin)
    13 VCONN
    14 CC2
    EP GND    - thermal pad

The KiCad symbol "zynq_eda:FUSB302BMPX" collapses pin pairs into
single-named pins, but exposes both VCONN_1 and VCONN_2 — they are
on the same VCONN net and share the VCONN cap network. We treat
VCONN as unconnected here because the carrier never sources VCONN
(SNK role only, no full-featured-cable power required); the host
firmware leaves VCONN_CC1/VCONN_CC2 control bits at 0 (DS Table 18).
"""

from __future__ import annotations

from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)
from zynq_eda.core.model.templates import IcBlockTemplate, PinGroup, PinGroupOffset


FUSB302_BLOCK_TEMPLATE = IcBlockTemplate(
    ic_anchor_offset=Point(0.0, 0.0),
    pin_group_offsets={
        PinGroup.DECOUPLING: PinGroupOffset(
            offset=Point(-15.24, -25.4),
            stride=Point(0.0, -12.7),
        ),
        PinGroup.SIGNAL_FILTER: PinGroupOffset(
            offset=Point(-15.24, 12.7),
            stride=Point(0.0, 12.7),
        ),
        PinGroup.BULK: PinGroupOffset(
            offset=Point(-15.24, 38.1),
            stride=Point(0.0, 12.7),
        ),
        PinGroup.PULL_UP: PinGroupOffset(
            offset=Point(38.1, -7.62),
            stride=Point(0.0, 12.7),
        ),
    },
)


FUSB302_REFCIRCUIT = ReferenceCircuit(
    part_mpn="FUSB302BMPX",
    lcsc="C442699",
    datasheet_url="https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf",
    datasheet_revision="Rev 5, Aug 2021",
    app_circuit_figure="Figure 18 - Reference Schematic Diagram",
    local_datasheet_path="components/fusb302/datasheet.pdf",
    app_circuit_page="p.30, Figure 18 + Table 43",
    minimum_circuit_verified=True,
    symbol_token="FUSB302BMPX",
    footprint="Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm",
    description="USB Type-C / PD CC controller, I2C-controlled, WQFN-14",
    supply_rail="+3V3",
    layout_template=FUSB302_BLOCK_TEMPLATE,
    # FUSB302 has 15 external_parts across 7-8 pins (VDD/VBUS/VCONN x2,
    # CC1/CC2 caps, SCL/SDA/INT_N pull-ups). The default LEFT/RIGHT
    # swarm pitch (15.24 mm) packs the cap value labels tightly enough
    # that the rendered text overlaps between adjacent slot columns.
    # Opt into the 20.32 mm dense pitch for breathing room.
    dense_swarm=True,
    pin_net_overrides=(
        ("CC1", "STM32_USB_CC1"),
        ("CC2", "STM32_USB_CC2"),
        ("VDD", "+3V3"),
        ("VBUS", "+VIN"),
        ("SDA", "STM32_I2C2_SDA"),
        ("SCL", "STM32_I2C2_SCL"),
        ("INT_N", "STM32_FUSB302_INT"),
    ),
    external_parts=(
        # ---- VDD decoupling (DS Table 43: C_VDD1=100nF, C_VDD2=1uF) ----
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="1u_0402_X7R",
            justification="DS Table 43 C_VDD2: 1uF VDD bulk",
        ),
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Table 43 C_VDD1: 100nF VDD HF bypass",
        ),
        # ---- VBUS sense (DS Table 7: VBUS pin abs-max 28V, OVP-protected;
        # FUSB302 has an internal divider for the 6-bit DAC up to 26V, so
        # no external divider is required for chip operation. The 1M/100k
        # divider here is the carrier-specific tap that lets the host MCU's
        # ADC observe VBUS independently of the FUSB302 register read; keep
        # for design parity with the existing usb_pd block).
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 18: VBUS pin bypass (HF noise filter)",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="+VIN",
            part_token="1M_0402_1%",
            justification="Carrier VBUS sense divider upper leg (1M, R1)",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100k_0402_1%",
            justification="Carrier VBUS sense divider lower leg (100k, R2)",
        ),
        # ---- CC receiver capacitance (DS Table 43 C_RECV: 200-600pF) ----
        ExternalPart(
            from_pin="CC1",
            to_net="GND",
            part_token="200p_0402_C0G",
            justification="DS Table 43 C_RECV: 200pF on CC1 (min of 200-600pF)",
        ),
        ExternalPart(
            from_pin="CC2",
            to_net="GND",
            part_token="200p_0402_C0G",
            justification="DS Table 43 C_RECV: 200pF on CC2 (min of 200-600pF)",
        ),
        # ---- VCONN bulk + decoupling (DS Table 43 C_BULK=10uF min,
        # C_VCONN=100nF). VCONN_1 and VCONN_2 are the same net (DS Fig 18
        # shows a single VCONN pin); the symbol exposes both for layout
        # convenience. One cap pair per pin keeps the supply impedance low
        # near both bond-out pads. Even when VCONN is not sourced by the
        # carrier (SNK role), the caps provide a quiet return path for the
        # internal VCONN switch leakage. ----
        ExternalPart(
            from_pin="VCONN_1",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="DS Table 43 C_BULK: 10uF VCONN bulk (min 10uF)",
        ),
        ExternalPart(
            from_pin="VCONN_1",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Table 43 C_VCONN: 100nF VCONN HF bypass",
        ),
        ExternalPart(
            from_pin="VCONN_2",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="DS Table 43 C_BULK: 10uF VCONN bulk (paralleled pad)",
        ),
        ExternalPart(
            from_pin="VCONN_2",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Table 43 C_VCONN: 100nF VCONN HF bypass (paralleled pad)",
        ),
        # ---- I2C pull-ups (DS Table 43 R_PU = 4.7k typ) ----
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3_SC",
            part_token="4k7_0402_1%",
            justification="DS Table 43 R_PU: 4.7k I2C SDA pull-up (1.71V-VDD range)",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3_SC",
            part_token="4k7_0402_1%",
            justification="DS Table 43 R_PU: 4.7k I2C SCL pull-up",
        ),
        # ---- INT_N pull-up (DS Table 43 R_PU_INT = 4.7k typ, range 1-4.7k);
        # open-drain output, IOL_NTN = 4mA at VOLINTN <= 0.4V ----
        ExternalPart(
            from_pin="INT_N",
            to_net="+3V3_SC",
            part_token="4k7_0402_1%",
            justification="DS Table 43 R_PU_INT: 4.7k INT_N pull-up (open-drain)",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # GND pins (8, 9, 11..13 in datasheet pin order, plus EP) are
        # power_in symbol pins automatically tied to GND by the layout
        # engine — no external parts hang off them.
    }),
    layout_notes=(
        LayoutNote(
            text=(
                "VDD decoupling: place 100nF (C_VDD1) within 1mm of VDD pin, "
                "1uF (C_VDD2) within 3mm. Return current through shortest GND via"
            ),
            severity="rule",
            justification="DS Table 43 + general decoupling practice",
        ),
        LayoutNote(
            text=(
                "CC1/CC2 traces: 90 ohm differential impedance to USB-C connector, "
                "matched length within 5mm. Place C_RECV (200pF) next to FUSB302, "
                "not next to the USB-C connector (USB-PD reference uses C_RECV as "
                "the receiver filter cap)"
            ),
            severity="rule",
            justification="USB-C R2.0 Sec 3.2.1 + DS Fig 18 (C_RECV at FUSB302 side)",
        ),
        LayoutNote(
            text=(
                "VBUS trace from USB-C VBUS to FUSB302 pin 2: keep under 10mm, route "
                "as a wide trace (>= 0.3mm) to minimise series inductance for the "
                "VBUS sense comparator (vBC_LVL trip thresholds <= 1.31V)"
            ),
            severity="guideline",
            justification="DS Table 10 (vBC_LVL) + VBUS sense latency",
        ),
        LayoutNote(
            text=(
                "Connect the exposed pad (EP, pin 15 / GND_EP) to the PCB GND plane "
                "with a 3x3 via stitch for thermal + electrical performance"
            ),
            severity="rule",
            justification="DS Fig 5 mechanical drawing (EP=Connect to GND for Thermal)",
        ),
        LayoutNote(
            text=(
                "I2C pull-ups (4.7k) tie to the same +3V3_SC rail as the STM32 I2C "
                "controller; DS Table 13 note 6 requires VPU between 1.71V and VDD"
            ),
            severity="rule",
            justification="DS Table 13 note 6 (I2C pull-up voltage 1.71V-VDD)",
        ),
    ),
)
