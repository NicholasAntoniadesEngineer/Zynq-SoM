"""USB Type-C 16P SMD receptacle - configured as Device/Sink.

Datasheet: Korean Hroparts Elec TYPE-C-31-M-12
LCSC: C165948
Package: USB Type-C SMD receptacle

USB Type-C device-mode (sink-only) configuration. The CC1/CC2 pins are
each terminated with a 5.1k Rd pull-down to GND to advertise as a device
(sink). VBUS is the power input.

For the dedicated FUSB302-controlled port (STM32 side), the CC pins go
to the FUSB302 directly and the 5.1k Rd is NOT external (handled by
FUSB302 internally - covered by FUSB302_REFCIRCUIT).

For the Zynq OTG port using simple sink-only, both CC1/CC2 carry their
own 5.1k Rd to GND. Use this REFCIRCUIT for the simple-sink port.

Pin map (per USB Type-C R2.0 Sec 3.4):
    A1, B12 GND
    A4, B9  VBUS
    A5      CC1   (5.1k Rd to GND - sink advertisement)
    B5      CC2   (5.1k Rd to GND - sink advertisement)
    A6, A7  D+    (USB 2.0 data, also valid on B6/B7 reverse orientation)
    A2, A3  TX1+/-  (USB 3.0 - unused for USB 2.0)
    B10,B11 RX1+/-  (USB 3.0 - unused)
    A8      SBU1
    B8      SBU2
    SHIELD  CHASSIS_GND (via 1M + 100nF)
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


USBC_DEVICE_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TYPE-C-31-M-12",
    lcsc="C165948",
    datasheet_url="https://datasheet.lcsc.com/lcsc/2304140030_Korean-Hroparts-Elec-TYPE-C-31-M-12_C165948.pdf",
    datasheet_revision="2023",
    app_circuit_figure="USB Type-C R2.0 Sec 3.4.4 - Sink Configuration",
    local_datasheet_path="components/usbc_connector/datasheet.pdf",
    app_circuit_page="USB Type-C R2.0 Sec 3.4.4 - Sink Configuration",
    minimum_circuit_verified=True,
    symbol_token="USBC_16P",
    footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    description="USB Type-C 16P SMD receptacle, configured as sink/device",
    external_parts=(
        # CC1 / CC2 5.1k Rd pull-downs (sink advertisement)
        ExternalPart(
            from_pin="CC1",
            to_net="GND",
            part_token="5k1_0402_1%",
            justification="USB-C R2.0 Sec 4.5: 5.1k Rd advertises sink role",
        ),
        ExternalPart(
            from_pin="CC2",
            to_net="GND",
            part_token="5k1_0402_1%",
            justification="USB-C R2.0 Sec 4.5: 5.1k Rd on each CC for reversibility",
        ),
        # VBUS bulk cap (USB-PD requires 1-10uF on VBUS, USB 2.0 requires 100nF min)
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="10u_0402_X5R",
            justification="USB-PD Sec 7.1.6: VBUS bulk capacitance",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="USB 2.0 Sec 7.1.6.1: VBUS HF bypass",
        ),
        # Shield to chassis GND via discharge path (USB-IF recommended)
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="1M_0402_1%",
            justification="USB-IF Compliance: 1M shield-to-GND discharge resistor",
        ),
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="100n_0402_X7R",
            justification="USB-IF Compliance: 100nF shield AC-coupling to chassis",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "D+", "D-",  # data lines pass to PHY/MCU directly
        "SBU1", "SBU2",  # USB 3 / Alt mode - unused
        "TX1+", "TX1-", "RX1+", "RX1-",  # USB 3 SS lanes - unused
    }),
    layout_notes=(
        LayoutNote(
            text="USB 2.0 D+/D- routing: 90 ohm differential impedance, matched length within 5mm",
            severity="rule",
            justification="USB 2.0 Sec 7.1.6",
        ),
        LayoutNote(
            text="VBUS routing: minimum 0.3mm trace width for >= 1A current",
            severity="rule",
            justification="IPC-2221 current carrying capacity",
        ),
        LayoutNote(
            text="Connect connector mounting tabs to CHASSIS_GND only (not signal GND)",
            severity="rule",
            justification="EMI compliance",
        ),
    ),
)
