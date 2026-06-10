"""CP2102N-A02-GQFN24R - USB-to-UART bridge with integrated regulator and oscillator.

Datasheet: Silicon Labs CP2102N, Rev 1.5, 2021
URL: https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf
Package: QFN-24 (4.0 x 4.0 mm, 0.5 mm pitch, 2.45 x 2.45 mm EP)

Single-chip USB 2.0 full-speed (12 Mbps) bridge to a UART, with hardware
flow control and modem-control sidebands. The QFN24 variant has separate
VIO and VDD pins (Table 1.1) so the UART I/O can run at a logic level
distinct from the internal 3.3V regulator output -- we tie VIO = VDD on
the carrier so all UART signals are 3.3V CMOS to the Zynq PS.

Required externals (DS Sec 2.1 / Figure 2.1 -- bus-powered with internal
regulator):

    C_VREGIN  4.7uF + 0.1uF  (each power pin: per DS Sec 2.1 figure
    C_VDD     4.7uF + 0.1uF   caption "4.7uF and 0.1uF bypass capacitors
                              required for each power pin placed as
                              close to the pins as possible")
    R_RST    1 kohm           RSTb pull-up to VIO (DS Sec 2.1: 'a 1 kohm
                              pull-up on the RSTb pin is recommended.
                              This pull-up should be tied to VIO on
                              devices that have it')
    R_VBUS   22.1 kohm /      VBUS sense divider (DS Sec 2.3: 'A
             47.5 kohm        resistor divider (or functionally-
                              equivalent circuit) on VBUS is required
                              to meet [absolute max VIO+2.5V and VIH
                              VIO-0.6V] specifications'). Outputs
                              VBUS_pin = USB_VBUS * 47.5/(22.1+47.5)
                              = USB_VBUS * 0.683.

USB D+/D- need no external termination (the CP2102N integrates the
1.5 kohm full-speed pull-up on D+, see Table 3.8 R_PU = 1.5 kohm typ).

Pin map (DS Table 5.2, QFN24 -- matches KiCad symbol
Interface_USB:CP2102N-Axx-xQFN24 pin names verbatim):

    Pin Name                  Function
    1   ~{RI}/CLK             Ring Indicator (in) / Clock out
    2   GND                   Ground
    3   D+                    USB D+ data
    4   D-                    USB D- data
    5   VIO                   I/O supply voltage (1.71V - VDD)
    6   VDD                   Supply / 3.3V regulator output
    7   VREGIN                Regulator input (5V from USB VBUS)
    8   VBUS                  VBUS sense input
    9   ~{RST}                Active-low reset
    10  NC                    No connect
    11  ~{WAKEUP}/GPIO.3      Remote-wakeup input / GPIO
    12  RS485/GPIO.2          RS485 enable output / GPIO
    13  ~{RXT}/GPIO.1         Receive LED toggle / GPIO
    14  ~{TXT}/GPIO.0         Transmit LED toggle / GPIO
    15  ~{SUSPEND}            Suspend (active low)
    16  NC                    No connect
    17  SUSPEND               Suspend (active high)
    18  ~{CTS}                Clear-to-send input
    19  ~{RTS}                Ready-to-send output
    20  RXD                   UART RX (data into CP2102N)
    21  TXD                   UART TX (data out of CP2102N)
    22  ~{DSR}                Data-set-ready input
    23  ~{DTR}                Data-terminal-ready output
    24  ~{DCD}                Data-carrier-detect input
    25  GND (EP)              Exposed pad / thermal ground
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


CP2102N_REFCIRCUIT = ReferenceCircuit(
    part_mpn="CP2102N-A02-GQFN24R",
    lcsc="C969151",
    datasheet_url="https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf",
    datasheet_revision="Rev 1.5, 2021",
    app_circuit_figure="Figure 2.1 (bus-powered, internal regulator) + Figure 2.5 (USB pins)",
    local_datasheet_path="components/cp2102n/datasheet.pdf",
    app_circuit_page="p.5 Fig 2.1 + p.8 Fig 2.5 (bus-powered USB connection)",
    minimum_circuit_verified=True,
    symbol_token="CP2102N-Axx-xQFN24",
    footprint="Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
    description="USB to UART bridge, USB 2.0 FS, internal 3.3V regulator + 48 MHz oscillator, QFN-24",
    supply_rail="+VIN",
    pin_net_overrides=(
        # VREGIN is the regulator input from USB cable VBUS (=+VIN).
        ("VREGIN", "+VIN"),
        # VDD is the regulator output (3.3V) -- tie to a local CP_VDD33 net
        # so the cluster routes the VDD bulk + bypass caps to it; uart_bridge
        # block aliases this net externally via power_input_net="+VIN".
        ("VDD", "CP2102N_VDD33"),
        # VIO logic-supply pin -- tie to the regulated VDD for 3.3V UART I/O.
        ("VIO", "CP2102N_VDD33"),
        # USB data lines run direct to the receptacle (USBLC6 ESD is optional
        # on this UART-only bridge; the block does not place one).
        ("D+", "USB_UART_DP"),
        ("D-", "USB_UART_DM"),
        # UART pins to the Zynq PS UART0 (block exposes these as hierarchical
        # labels; net names are the Zynq-side carrier convention).
        ("TXD", "ZYNQ_PS_UART0_RXD"),    # CP2102N TX -> Zynq RX
        ("RXD", "ZYNQ_PS_UART0_TXD"),    # CP2102N RX <- Zynq TX
        ("~{RTS}", "ZYNQ_PS_UART0_CTS_N"),
        ("~{CTS}", "ZYNQ_PS_UART0_RTS_N"),
    ),
    external_parts=(
        # ---- VREGIN bypass (DS Sec 2.1 Fig 2.1: 4.7uF + 0.1uF) ----
        ExternalPart(
            from_pin="VREGIN",
            to_net="GND",
            part_token="4u7_0402_X5R",
            justification="DS Fig 2.1: 4.7uF VREGIN bulk (5V regulator input)",
        ),
        ExternalPart(
            from_pin="VREGIN",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 2.1: 100nF VREGIN HF bypass",
        ),
        # ---- VDD bypass (DS Sec 2.1 Fig 2.1: 4.7uF + 0.1uF on regulator out) ----
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="4u7_0402_X5R",
            justification="DS Fig 2.1: 4.7uF VDD bulk (regulator output, 3.3V)",
        ),
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 2.1: 100nF VDD HF bypass",
        ),
        # ---- VIO bypass (separate VIO pin on QFN24 even when tied to VDD;
        # DS caption 'each power pin' implies a separate bypass) ----
        ExternalPart(
            from_pin="VIO",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 2.1: 0.1uF bypass on every power pin (VIO=VDD)",
        ),
        # ---- VBUS sense divider (DS Sec 2.3, Fig 2.5 -- REQUIRED) ----
        # 22.1k upper / 47.5k lower divides 5V VBUS down to 3.41V at the pin
        # (under VIO + 2.5V = 5.8V abs-max with VIO = 3.3V).
        ExternalPart(
            from_pin="VBUS",
            to_net="+VIN",
            part_token="22k1_0402_1%",
            justification="DS Sec 2.3 / Fig 2.5: 22.1k upper leg of VBUS sense divider",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="47k5_0402_1%",
            justification="DS Sec 2.3 / Fig 2.5: 47.5k lower leg of VBUS sense divider",
        ),
        # ---- RSTb pull-up (DS Sec 2.1: 1 kohm to VIO) ----
        ExternalPart(
            from_pin="~{RST}",
            to_net="CP2102N_VDD33",
            part_token="1k_0402_1%",
            justification="DS Sec 2.1: 1 kohm RSTb pull-up to VIO (recommended)",
        ),
    ),
    strap_pins=(),
    lib_symbol_pin_type_overrides=(
        # The stock ``Interface_USB:CP2102N-Axx-xQFN24`` symbol declares
        # RXD (pin 20) and ~{CTS} (pin 18) as ``input`` -- correct in
        # absolute terms, but ERC's ``pin_not_driven`` rule then demands
        # an Output-type driver on the same net. The signal that drives
        # these pins comes from the Zynq PS UART0 TXD / RTS_N on the OTHER
        # side of the FX10A SoM-mate connector (an off-board / off-sheet
        # source). The carrier-side FMC_LPC symbol has no physical pin
        # for these signals (it is a 2-pin stub used only for power refs),
        # so no on-sheet Output exists. Overriding the CP2102N's input
        # pins to ``passive`` matches the electrical reality (an off-board
        # source connects directly to the pin via the SoM connector) and
        # clears the spurious ``pin_not_driven`` ERC violation without
        # globally relaxing the rule -- same approach used for the
        # INA226 Vbus sense pin (see ina226/refcircuit.py).
        #
        # ~{DCD}, ~{DSR}, ~{RI}/CLK, ~{WAKEUP}/GPIO.3 are NOT overridden
        # here -- they are intentionally left as ``no_external_required``
        # so the auto-NC pass marks them unconnected; ERC then ignores
        # them rather than complaining about missing drivers.
        ("RXD",    "passive"),  # Zynq PS UART0 TXD -> CP2102N RXD (in)
        ("~{CTS}", "passive"),  # Zynq PS UART0 RTS_N -> CP2102N ~{CTS} (in)
    ),
    no_external_required=frozenset({
        # D+/D- have integrated 1.5k full-speed pull-up + internal pull-downs
        # (DS Table 3.8 R_PU = 1.5k typ); no external termination needed.
        "D+", "D-",
        # NC pins (datasheet "leave floating" -- pins 10 and 16).
        "NC",
        # UART logic-level outputs / inputs: no termination required at the
        # CP2102N side. Series resistors / level shifters live in the
        # carrier block, not here.
        "TXD", "RXD",
        # Modem-control sidebands routed only to test points / GPIO (the
        # uart_bridge block uses ~{RTS}/~{CTS} for flow control and leaves
        # the rest unconnected). Mark intentionally unconnected here so the
        # auto-NC pass leaves them alone.
        "~{DTR}", "~{DSR}", "~{DCD}", "~{RI}/CLK",
        "~{SUSPEND}", "SUSPEND",
        "~{WAKEUP}/GPIO.3", "RS485/GPIO.2",
        "~{TXT}/GPIO.0", "~{RXT}/GPIO.1",
    }),
    layout_notes=(
        LayoutNote(
            text=(
                "Each power pin (VREGIN pin 7, VDD pin 6, VIO pin 5) gets its "
                "OWN 4.7uF + 0.1uF bypass placed as close to the pin as possible. "
                "Do not share a single 4.7uF across VDD + VIO -- the DS caption "
                "is explicit: 'each power pin placed as close to the pins as "
                "possible'"
            ),
            severity="rule",
            justification="DS Sec 2.1 Fig 2.1 + Fig 2.2 figure captions",
        ),
        LayoutNote(
            text=(
                "VBUS sense divider (22.1k/47.5k) is MANDATORY for bus-powered "
                "operation -- the VBUS pin abs-max is VIO+2.5V (DS Table 3.10) "
                "but USB cable VBUS reaches 5.25V. Divider scales it into spec "
                "while still meeting VIH=VIO-0.6V at low end. Do not omit"
            ),
            severity="rule",
            justification="DS Sec 2.3 + Table 3.10 (abs-max VBUS pin)",
        ),
        LayoutNote(
            text=(
                "Connect exposed pad (EP, pin 25 / center) to GND plane with a "
                "3x3 via stitch. EP is the chip's primary thermal path and the "
                "low-impedance GND return"
            ),
            severity="rule",
            justification="DS Sec 6.2 / 7.2 PCB Land Pattern notes",
        ),
        LayoutNote(
            text=(
                "USB D+/D- routing: 90 ohm differential impedance to the USB-B "
                "(or USB-C) connector pads, length-matched within 2mm. Place "
                "USBLC6 ESD protection inline between the connector and the "
                "CP2102N D+/D- pins (if the parent block includes ESD)"
            ),
            severity="rule",
            justification="USB 2.0 Sec 7.1.6 + standard ESD-placement practice",
        ),
        LayoutNote(
            text=(
                "RSTb pin (pin 9, ~RST in the symbol) is driven LOW during "
                "power-on and power-fail reset. 1 kohm pull-up to VIO holds it "
                "high otherwise. No external C is required -- DS Fig 2.1 shows "
                "only the pull-up"
            ),
            severity="info",
            justification="DS Sec 2.1 (RSTb behaviour) + Fig 2.1 (no R-C filter)",
        ),
        LayoutNote(
            text=(
                "No external crystal: the CP2102N integrates a 48 MHz oscillator "
                "(DS Table 3.5, +/- 0.7% over temp/supply). Do NOT add a crystal "
                "to the unused pins"
            ),
            severity="info",
            justification="DS Sec 3.1.5 + Table 3.5 (Internal Oscillator)",
        ),
    ),
)
