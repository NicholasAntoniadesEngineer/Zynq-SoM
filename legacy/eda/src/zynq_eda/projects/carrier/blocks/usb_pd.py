"""Carrier USB-C Power Delivery block: USB-C → FUSB302 controller + USBLC6 ESD.

A single USB-C port that:

  * Negotiates USB-PD via FUSB302BMPX (I2C-controlled USB-C port
    controller). The STM32 co-processor talks to it over I2C2.
  * Provides ESD protection on USB 2.0 D+/D- via USBLC6-4SC6.
  * Exposes USB 2.0 D+/D- to the STM32 MCU's USB HS PHY.
  * Delivers VBUS (5 V or 9 V depending on PD negotiation) as the
    carrier's +VIN power rail.

The 5.1 kΩ Rd pull-downs on CC1/CC2 (from USBC_DEVICE_REFCIRCUIT's
external_parts) are redundant when FUSB302 is in command — FUSB302
handles CC termination internally. They're harmless and keep the
mechanical-only sink mode (without FUSB302) viable as a fallback.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    ExternalNet,
    GroundNet,
    IcInstance,
    PowerInputNet,
    PowerOutputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_usb_pd() -> Block:
    """Return the USB-PD block (FUSB302 + USBLC6 + USB-C connector)."""
    return Block(
        name="usb_pd",
        title="USB-C Power Delivery (FUSB302 + USBLC6 + USB-C)",
        paper_size="A3",
        description=(
            "USB-C port controlled by FUSB302 over I2C. USBLC6-4SC6 protects "
            "the USB 2.0 D+/D- lines. VBUS from the USB-C connector is the "
            "carrier's +VIN rail. CC1/CC2 are owned by FUSB302; the 5.1k Rd "
            "on each CC (from the USBC_DEVICE refcircuit) is a redundant "
            "fallback for mechanical-only sink mode."
        ),
        ics=(
            IcInstance(
                reference="U1",
                refcircuit=REFCIRCUITS["FUSB302BMPX"],
                lib_id="zynq_eda:FUSB302BMPX",
                power_input_net="+3V3",
                # FUSB302's I2C pull-ups in the shared refcircuit target
                # +3V3_SC (a catalog-scoped rail name). On the carrier they
                # land on the main +3V3 rail; remap collapses the otherwise-
                # orphan +3V3_SC net onto +3V3 so ERC sees a driven net.
                external_part_net_remap=(("+3V3_SC", "+3V3"),),
            ),
            IcInstance(
                reference="U2",
                refcircuit=REFCIRCUITS["USBLC6-4SC6"],
                lib_id="zynq_eda:USBLC6-4SC6",
                power_input_net="+VIN",
                # USBLC6 pin renames: I/O1/2 are the USB 2.0 data pair the
                # carrier exposes; I/O3/4 are unused (single USB port).
                net_overrides=(
                    ("I/O1", "USB_DP"),
                    ("I/O2", "USB_DM"),
                ),
            ),
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["USBC_SINK"],
                lib_id="zynq_eda:USBC_16P",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    # Ground pins (top + bottom of each side)
                    ("A1", "GND"), ("A12", "GND"),
                    ("B1", "GND"), ("B12", "GND"),
                    # VBUS pins (A4/A9 on side A, B4/B9 on side B)
                    ("A4", "+VIN"), ("A9", "+VIN"),
                    ("B4", "+VIN"), ("B9", "+VIN"),
                    # CC1/CC2 -> FUSB302 (also via 5.1k Rd to GND from refcircuit)
                    ("A5", "STM32_USB_CC1"),
                    ("B5", "STM32_USB_CC2"),
                    # USB 2.0 D+/D- — both A6/B6 and A7/B7 land on the same
                    # differential pair (USB-C reversibility).
                    ("A6", "USB_DP"), ("B6", "USB_DP"),
                    ("A7", "USB_DM"), ("B7", "USB_DM"),
                    # SBU1/SBU2 unused (USB 2.0 only)
                    # Shield to chassis ground (1M + 100nF discharge)
                    ("SH", "CHASSIS_GND"),
                ),
            ),
        ),
        external_nets=(
            # Block consumes +3V3 to power the FUSB302 VDD pin.
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            # +VIN sourced from the USB-C VBUS pins. Declared as input
            # (not output) because the USB-C connector's VBUS pins are
            # typed `power_input` in the KiCad symbol, not `power_output`
            # — so KiCad's ERC needs a root-level PWR_FLAG to satisfy
            # the `power_pin_not_driven` rule on the VBUS pins themselves
            # and on downstream consumers (INA226 Vbus). Declaring as
            # PowerInputNet keeps +VIN OUT of `nets_with_producer` so
            # root.py emits the flag.
            PowerInputNet("+VIN", edge=SheetEdge.LEFT),
            # Inter-block signal nets going to/from the STM32.
            SignalNet("STM32_I2C2_SDA",     direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("STM32_I2C2_SCL",     direction="input",         edge=SheetEdge.LEFT),
            SignalNet("STM32_FUSB302_INT",  direction="output",        edge=SheetEdge.LEFT),
            SignalNet("STM32_USB_CC1",      direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("STM32_USB_CC2",      direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("USB_DP",             direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("USB_DM",             direction="bidirectional", edge=SheetEdge.LEFT),
            # Ground references (one on each side of the sheet).
            GroundNet("GND", edge=SheetEdge.LEFT),
            ExternalNet(
                name="CHASSIS_GND",
                direction="passive",
                edge=SheetEdge.LEFT,
                power_kind="ground",
            ),
        ),
    )
