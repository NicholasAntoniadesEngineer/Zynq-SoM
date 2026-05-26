"""Carrier USB-C OTG block: dedicated OTG port with a TPS2051C VBUS load switch.

A second USB-C receptacle (separate from the FUSB302-controlled USB-PD sink
port in ``usb_pd``) wired as a USB 2.0 OTG port for the Zynq PS USB controller:

  * J1 = USBC_16P receptacle on the carrier's right edge — USB 2.0 only
    (no PD negotiation; CC1/CC2 carry 5.1 kOhm Rd pull-downs from the
    USBC_DEVICE_REFCIRCUIT for mechanical-only sink detection by default).
  * U1 = TPS2051C current-limited load switch that gates +VIN onto
    VBUS_OTG when the host enables OTG host mode. /OC fault flag returns
    to the STM32 as STM32_USBOTG_OC_N; /EN driven by STM32_USBOTG_VBUS_EN.
  * USB 2.0 D+/D- pass straight to the SoM USB PHY as USBOTG_DP / USBOTG_DM.
  * ID pin (A8 SBU1 / B8 SBU2 aren't strictly the USB-OTG ID — true
    USB-OTG ID comes from a CC-pin override on full USB-C, but for a
    simple USB 2.0 host/device port we expose a STM32_USBOTG_ID hint
    that firmware can pull from the CC lines via the FUSB302 if needed).

The 5.1 kOhm Rd pull-downs on CC1/CC2 (already in the USBC_DEVICE refcircuit)
make this port behave as a sink by default. To advertise as a source/host
the firmware can either drive an external CC override or use the FUSB302
on the main port — out of scope for this block.
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
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_usbc_otg() -> Block:
    """Return the USB-C OTG block (TPS2051C + USB-C connector)."""
    return Block(
        name="usbc_otg",
        title="USB-C OTG Port (TPS2051C VBUS switch + USB-C)",
        paper_size="A3",
        description=(
            "Dedicated USB-C OTG port for the Zynq PS USB controller. "
            "TPS2051C current-limited switch gates +VIN onto VBUS_OTG when "
            "the host enables OTG mode; /OC fault returns to STM32. CC1/CC2 "
            "carry 5.1 kOhm Rd pull-downs (from USBC_DEVICE_REFCIRCUIT) for "
            "default sink advertisement; USB 2.0 D+/D- pass to the SoM PHY."
        ),
        ics=(
            IcInstance(
                reference="U1",
                refcircuit=REFCIRCUITS["TPS2051CDBVR"],
                lib_id="Power_Management:TPS2051CDBV",
                power_input_net="+VIN",
                power_output_net="VBUS_OTG",
            ),
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["USBC_SINK"],
                lib_id="zynq_eda:USBC_16P",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    # GND pins (top + bottom of each side)
                    ("A1", "GND"), ("A12", "GND"),
                    ("B1", "GND"), ("B12", "GND"),
                    # VBUS pins driven by TPS2051C output, not directly +VIN
                    ("A4", "VBUS_OTG"), ("A9", "VBUS_OTG"),
                    ("B4", "VBUS_OTG"), ("B9", "VBUS_OTG"),
                    # CC1/CC2 — 5.1k Rd to GND from the USBC_DEVICE refcircuit
                    # advertises as sink; firmware can override via FUSB302
                    # on the other port if a host/source role is needed.
                    ("A5", "USBOTG_CC1"),
                    ("B5", "USBOTG_CC2"),
                    # USB 2.0 D+/D- — both A6/B6 and A7/B7 land on the same
                    # differential pair for USB-C reversibility.
                    ("A6", "USBOTG_DP"), ("B6", "USBOTG_DP"),
                    ("A7", "USBOTG_DM"), ("B7", "USBOTG_DM"),
                    # SBU1 = USBOTG_ID (treat SBU1 as the firmware-visible ID
                    # hint; SBU2 unused).
                    ("A8", "STM32_USBOTG_ID"),
                    # Shield to chassis GND via the 1M + 100nF discharge from
                    # the USBC_DEVICE_REFCIRCUIT.
                    ("SH", "CHASSIS_GND"),
                ),
            ),
        ),
        external_nets=(
            # Block consumes +VIN; produces no rail upstream (VBUS_OTG is
            # internal to this block + the connector pin).
            PowerInputNet("+VIN", edge=SheetEdge.LEFT),
            GroundNet("GND", edge=SheetEdge.LEFT),
            # USB 2.0 data pair out to the SoM PHY.
            SignalNet("USBOTG_DP",            direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("USBOTG_DM",            direction="bidirectional", edge=SheetEdge.LEFT),
            # Control / status to the STM32 co-processor.
            SignalNet("STM32_USBOTG_ID",       direction="input",         edge=SheetEdge.LEFT),
            SignalNet("STM32_USBOTG_VBUS_EN",  direction="input",         edge=SheetEdge.LEFT),
            SignalNet("STM32_USBOTG_OC_N",     direction="output",        edge=SheetEdge.LEFT),
            # Chassis ground (separate from signal GND through 1M discharge).
            ExternalNet(
                name="CHASSIS_GND",
                direction="passive",
                edge=SheetEdge.LEFT,
                power_kind="ground",
            ),
        ),
    )
