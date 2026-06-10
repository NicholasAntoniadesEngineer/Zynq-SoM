"""uart_bridge — CP2102N USB-UART bridge, self-powered at 3.3 V.

Reference circuit per the SiLabs CP2102N datasheet (self-powered config):
VREGIN + VDD + VIO tied directly to the +3V3 rail; decoupling 100n + 10u on
VREGIN, 100n on VDD, 100n on VIO; ~RST pulled up 1k to the rail; VBUS sensed
through a 22k1 / 47k5 divider from +VIN to GND (datasheet self-powered VBUS
divider) with the mid-point on the VBUS pin. D+/D- go to the USB connector
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

from schgen.model import Circuit

LIB_ID = "schgen:CP2102N_UART"
FOOTPRINT = "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm"


def circuit() -> Circuit:
    c = Circuit("uart_bridge", "UART bridge: CP2102N USB-UART")
    c.part("U1", LIB_ID, "CP2102N-A02", FOOTPRINT)

    # power: VIO(5) + VDD(6) + VREGIN(7) tied directly to +3V3 (self-powered);
    # GND pin 2 + stacked hidden twin 25
    c.net("+3V3", "U1.5", "U1.6", "U1.7")
    c.net("GND", "U1.2", "U1.25")
    c.decouple("U1.7", "100n", "10u")        # C1, C2 on VREGIN
    c.decouple("U1.6", "100n")               # C3 on VDD
    c.decouple("U1.5", "100n")               # C4 on VIO

    # reset pull-up (RST is open-drain, needs the external pull to VDD33)
    c.net("CP2102N_RST_N", "U1.9")
    c.pullup("U1.9", "1k", "+3V3")           # R1

    # VBUS sense divider, datasheet self-powered config:
    # +VIN -[22k1]- CP2102N_VBUS_SNS -[47k5]- GND, mid-point to the VBUS pin
    c.net("CP2102N_VBUS_SNS", "U1.8")
    c.series("+VIN", "CP2102N_VBUS_SNS", "22k1")    # R2
    c.series("CP2102N_VBUS_SNS", "GND", "47k5")     # R3

    # USB data to the connector
    c.port("USB_UART_DP", "U1.3")
    c.port("USB_UART_DM", "U1.4")

    # UART to the Zynq PS UART0 — TXD->RXD / RTS->CTS crossover naming
    c.port("ZYNQ_PS_UART0_RXD", "U1.21")     # bridge TXD drives Zynq RXD
    c.port("ZYNQ_PS_UART0_TXD", "U1.20")     # Zynq TXD feeds bridge RXD
    c.port("ZYNQ_PS_UART0_CTS_N", "U1.19")   # bridge ~RTS drives Zynq ~CTS
    c.port("ZYNQ_PS_UART0_RTS_N", "U1.18")   # Zynq ~RTS feeds bridge ~CTS

    # unused by design: ~RI/CLK, GPIO.0-3, SUSPEND/~SUSPEND, ~DSR/~DTR/~DCD,
    # and the two physical NC pins (10, 16)
    c.nc("U1.1", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15",
         "U1.16", "U1.17", "U1.22", "U1.23", "U1.24")
    return c
