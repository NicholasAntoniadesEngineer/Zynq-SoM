from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    MICROSD_CARD_BULK,
    MICROSD_CARD_BYPASS,
    MICROSD_CARD_PULL,
    MICROSD_DETECT_PULL,
    MICROSD_ESD_BYPASS,
    MICROSD_HOST_BYPASS,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_CARD_PULL = "C25803"
LCSC_DETECT_PULL = "C25804"
LCSC_BYPASS = "C14663"
LCSC_BULK = "C45783"

RAILS = ("+VDD_HOST", "+VDD_CARD", "GND")
PORTS = ("SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3", "CD_N")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('microsd')

HOST_LEVEL_V = 1.8
RAIL_WORST_V = {"+VDD_HOST": 1.8, "+VDD_CARD": 3.3, "GND": 0.0}

DRAWS_CARD_NOTE = ("SD card write burst ~200 mA + pull-ups + TXS02612 VCCB")
DRAWS_CARD_A = 0.250
DRAWS_HOST_NOTE = "TXS02612 VCCA (host-side level)"
DRAWS_HOST_A = 0.005

LANES = {
    "SD_CLK": ("CLKA", "CLKB0", "CLK(SCLK)", "IO1"),
    "SD_CMD": ("CMDA", "CMDB0", "CMD(DI)", "IO2"),
    "SD_D0": ("DAT0A", "DAT0B0", "DAT0(D0)", "IO3"),
    "SD_D1": ("DAT1A", "DAT1B0", "DAT1(RSV)", "IO4"),
    "SD_D2": ("DAT2A", "DAT2B0", "DAT2(RSV)", "IO5"),
    "SD_D3": ("DAT3A", "DAT3B0", "CDDAT3(CS)", "IO6"),
}
PULLED = ("SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3")


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('microsd', meta)
