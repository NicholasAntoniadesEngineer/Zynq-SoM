"""microsd — card slot behind the MANDATED SDIO level translator.

PLAN-verified: the SoM's SDIO_* nets run straight to the Zynq at 1.8V and
standard SD cards initialize at 3.3V, so a TXS02612 sits between them:
port A = 1.8V SoM side (contract nets SDIO_* verbatim, typed sd_bus 1.8V),
port B0 = 3.3V card side to the TF-01A push-push slot, port B1 unused.
SEL strapped low selects B0 (verify polarity against the TI datasheet at
bring-up; one-line fix here if inverted). Card-side CMD/DAT pull-ups 10k to
the bring-up-gated +3V3_SD rail; TPD6E001 6-ch ESD across the card lines;
card-detect pulled up and reported.
"""

from __future__ import annotations

from schgen.model import Circuit

TXS_LIB = "TXS02612RTWR:TXS02612RTWR"
TXS_FP = "TXS02612RTWR:TXS02612RTWR"
SLOT_LIB = "TF-01A:TF-01A"
SLOT_FP = "TF-01A:TF-01A"
ESD_LIB = "TPD6E001RSER:TPD6E001RSER"
ESD_FP = "TPD6E001RSER:TPD6E001RSER"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

BRINGUP = "bringup (gated +3V3_SD rail)"
J1_MAP = "som_j1_connector (STM32 GPIO function map)"

# SoM contract net -> (TXS A-side pin, TXS B0-side pin, slot pin, ESD channel)
LANES = {
    "SDIO_CLK": ("9", "19", "5", "1"),
    "SDIO_CMD": ("4", "20", "3", "2"),
    "SDIO_D0": ("6", "18", "7", "3"),
    "SDIO_D1": ("7", "16", "8", "6"),
    "SDIO_D2": ("1", "23", "1", "7"),
    "SDIO_D3": ("3", "22", "2", "8"),
}
PULLED = ("SDIO_CMD", "SDIO_D0", "SDIO_D1", "SDIO_D2", "SDIO_D3")


def circuit() -> Circuit:
    c = Circuit("microsd", "microSD slot (1.8V SoM <-> 3.3V card, TXS02612)")
    c.part("U1", TXS_LIB, "TXS02612RTWR", TXS_FP, LCSC="C140276")
    c.part("J1", SLOT_LIB, "TF-01A", SLOT_FP, LCSC="C91145")
    c.part("U2", ESD_LIB, "TPD6E001RSER", ESD_FP, LCSC="C1973318")

    # ---- lanes: SoM(1.8V, port) -> TXS -> card(3.3V) + ESD ----------------
    for net, (a, b0, slot, esd) in LANES.items():
        c.port(net, f"U1.{a}")
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"U1.{b0}", f"J1.{slot}", f"U2.{esd}")
        c.port_type(net, kind="sd_bus", level_v=1.8)

    # card-side pull-ups to the gated rail
    pull_pins = []
    for i, net in enumerate(PULLED, start=1):
        ref = f"R{i}"
        c.part(ref, "Device:R", "10k", R0603, LCSC="C25804")
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"{ref}.2")
        pull_pins.append(f"{ref}.1")

    # card detect: switch closes to GND, pulled up, reported to the SoM
    c.part("R6", "Device:R", "10k", R0603, LCSC="C25804")
    c.port("SD_CARD_DETECT", "J1.9", "R6.2", expect=J1_MAP)
    pull_pins.append("R6.1")

    # ---- power -------------------------------------------------------------
    c.net("+1V8", "U1.5")                       # VCCA, SoM-side level
    c.decouple("U1.5", "100n")
    # gated card rail (+3V3_SD is the bring-up-gated module rail — SY6280 on
    # the bringup sheet — a POWER net with its own symbol, like +5V_USB):
    # slot VDD + both VCCB + every pull-up + bulk
    c.part("C2", "Device:C", "100n", C0603, LCSC="C1591")
    c.part("C3", "Device:C", "22u", C0805, LCSC="C45783")
    c.net("+3V3_SD", "J1.4", "U1.21", "U1.17", "C2.1", "C3.1", *pull_pins)
    c.net("GND", "C2.2", "C3.2")

    # SEL low selects port B0; EP + grounds
    c.net("GND", "U1.24", "U1.25", "U1.2", "U1.11",
          "J1.6", "J1.10", "J1.11", "J1.12", "J1.13", "U2.5")

    # unused TXS port B1 + ESD spares
    c.nc("U1.8", "U1.10", "U1.12", "U1.13", "U1.14", "U1.15")
    c.nc("U2.4", "U2.9", "U2.10")
    return c
