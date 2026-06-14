"""uart_bridge — CP2102N USB-UART bridge, self-powered at 3.3 V.

Reference circuit per the SiLabs CP2102N datasheet (self-powered config):
VREGIN + VDD + VIO tied directly to the +3V3 rail; decoupling 100n + 10u on
VREGIN, 100n on VDD, 100n on VIO; ~RST pulled up 1k to the rail; VBUS sensed
through a 22k1 / 47k5 divider from the UART USB connector's own 5 V VBUS
(port USB_UART_VBUS, wave-2 receptacle; datasheet self-powered VBUS divider)
with the mid-point on the VBUS pin. D+/D- go to the USB connector
(ports USB_UART_DP/DM); the four UART signals cross over to the Zynq PS UART0
(bridge TXD -> ZYNQ_PS_UART0_RXD etc.). All GPIO / modem-control / suspend
pins are unused by design -> explicit author no-connects.

Symbol: schgen:CP2102N_UART — corrected copy of the carrier's re-pinned
zynq_eda:CP2102N_UART (power/reset LEFT, the six signals RIGHT at 5.08 mm
pitch, unused pins below, GND on the bottom edge). The schgen copy moves GND
(pins 2/25) to the bottom-LEFT so its vertical pin-name text clears the long
GPIO names on the lower right rows (the zynq_eda copy has an intrinsic text
overlap there that the visual gate rightly rejects). Stacked hidden GND pin
25 is declared on GND with its visible twin pin 2.
"""

from __future__ import annotations

from schgen.core.model import Circuit

LIB_ID = "schgen:CP2102N_UART"
FOOTPRINT = "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm"


def circuit() -> Circuit:
    c = Circuit("uart_bridge", "UART bridge: CP2102N USB-UART")
    # CP2102N-A02-GQFN24R — LCSC C969151, live-verified 2026-06-11:
    # Extended, stock 24,473 (the non-reel -GQFN24 C1550551 is at 0)
    c.part("U1", LIB_ID, "CP2102N-A02", FOOTPRINT, LCSC="C969151")

    # power: VIO(5) + VDD(6) + VREGIN(7) tied directly to +3V3 (self-powered);
    # GND pin 2 + stacked hidden twin 25
    c.net("+3V3", "U1.5", "U1.6", "U1.7")
    c.net("GND", "U1.2", "U1.25")
    for cap, lcsc in zip(c.decouple("U1.7", "100n", "10u"),     # C1, C2
                         ("C14663", "C15850")):                 # both Basic
        cap.fields["LCSC"] = lcsc
    for cap in c.decouple("U1.6", "100n"):   # C3 on VDD
        cap.fields["LCSC"] = "C14663"
    for cap in c.decouple("U1.5", "100n"):   # C4 on VIO
        cap.fields["LCSC"] = "C14663"

    # reset pull-up (RST is open-drain, needs the external pull to VDD33)
    c.net("CP2102N_RST_N", "U1.9")
    c.pullup("U1.9", "1k", "+3V3").fields["LCSC"] = "C21190"    # R1, Basic

    # VBUS sense divider, datasheet self-powered config: senses the UART
    # USB connector's OWN 5 V VBUS (the cable-attach detect this pin is
    # for). FIX 2026-06-11, caught by the schgen spice gate: this divider
    # was authored from +VIN — after PD negotiation that rail is 20 V and
    # the divider would put 13.6 V on a 5.8 V abs-max pin, destroying the
    # bridge. USB_UART_VBUS is the wave-2 USB-UART receptacle's VBUS.
    # USB_UART_VBUS -[22k1]- CP2102N_VBUS_SNS -[47k5]- GND, mid to pin 8
    # (22.1k = C25961, 47.5k = C23061 — both UNI-ROYAL 1% 0603, Extended,
    # stock 87k/91k live-verified 2026-06-11)
    c.port("USB_UART_VBUS", expect="usb_uart_connector (wave 2)")
    c.net("CP2102N_VBUS_SNS", "U1.8")
    c.series("USB_UART_VBUS", "CP2102N_VBUS_SNS", "22k1") \
        .fields["LCSC"] = "C25961"                  # R2
    c.series("CP2102N_VBUS_SNS", "GND", "47k5") \
        .fields["LCSC"] = "C23061"                  # R3

    # USB data to the connector — a 90R differential pair (USB 2.0 HS);
    # the USB receptacle subsystem lands in wave 2.
    c.port("USB_UART_DP", "U1.3")
    c.port("USB_UART_DM", "U1.4")
    c.port_type("USB_UART_DP", kind="usb_hs_pair", pair_with="USB_UART_DM",
                expect="usb_uart_connector (wave 2)")

    # UART to the Zynq PS UART0 — TXD->RXD / RTS->CTS crossover naming.
    # The SoM contract exposes raw ZYNQ_PS_MIO* names; the generated J1 sheet
    # (wave 3) carries the MIO->UART0 function map, so these are deferred.
    J1_MAP = "som_j1_connector (wave 3 MIO function map)"
    c.port("ZYNQ_PS_UART0_RXD", "U1.21", expect=J1_MAP)    # bridge TXD -> Zynq RXD
    c.port("ZYNQ_PS_UART0_TXD", "U1.20", expect=J1_MAP)    # Zynq TXD -> bridge RXD
    c.port("ZYNQ_PS_UART0_CTS_N", "U1.19", expect=J1_MAP)  # bridge ~RTS -> Zynq ~CTS
    c.port("ZYNQ_PS_UART0_RTS_N", "U1.18", expect=J1_MAP)  # Zynq ~RTS -> bridge ~CTS

    # unused by design: ~RI/CLK, GPIO.0-3, SUSPEND/~SUSPEND, ~DSR/~DTR/~DCD,
    # and the two physical NC pins (10, 16)
    c.nc("U1.1", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15",
         "U1.16", "U1.17", "U1.22", "U1.23", "U1.24")

    # round-4 coverage gate: the console UART is THE bring-up bus — probe
    # both directions at the bridge
    c.testpoint("ZYNQ_PS_UART0_TXD")
    c.testpoint("ZYNQ_PS_UART0_RXD")

    # power-tree budget (round 4): CP2102N active ICC ~14 mA typ (DS table
    # 4.3) + 1k RST pull-up, self-powered from +3V3
    c.draws("+3V3", 0.015, "CP2102N active ~14 mA typ + RST 1k pull-up")
    # design-rule waiver (verification P1): CP2102N_RST_N is a defined-high
    # open-drain RST with the 1k external pull-up only — no RC cap by design
    # (the CP2102N has its own internal POR; a runtime reset is host-driven).
    c.waive_reset("CP2102N_RST_N",
                  "open-drain RST: 1k pull-up only, internal POR; no RC cap")
    return c
