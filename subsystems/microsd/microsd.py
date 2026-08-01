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
INTERFACE = RAILS + PORTS

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
    meta = Meta(meta)
    draws_card_note = meta.note("draws_card", DRAWS_CARD_NOTE)
    draws_host_note = meta.note("draws_host", DRAWS_HOST_NOTE)
    c = Circuit("microsd", "microSD slot (1.8V SoM <-> 3.3V card, TXS02612)")
    c.use_part("TXS02612RTWR", ref="U1")
    c.use_part("TF-01A", ref="J1")
    c.use_part("TPD6E001RSER", ref="U2")

    for net, (a, b0, slot, esd) in LANES.items():
        c.port(net, f"U1.{a}", **meta.expect_kw(net))
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"U1.{b0}", f"J1.{slot}", f"U2.{esd}")
        c.port_type(net, kind="sd_bus", level_v=HOST_LEVEL_V)

    pull_pins = []
    for i, net in enumerate(PULLED, start=1):
        ref = f"R{i}"
        c.part(ref, "Device:R", MICROSD_CARD_PULL, R0603, LCSC=LCSC_CARD_PULL)
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"{ref}.2")
        pull_pins.append(f"{ref}.1")

    c.part("R6", "Device:R", MICROSD_DETECT_PULL, R0603,
           LCSC=LCSC_DETECT_PULL)
    c.port("CD_N", "J1.CD", "R6.2", **meta.expect_kw("CD_N"))
    pull_pins.append("R6.1")

    c.net("+VDD_HOST", "U1.VCCA")
    for cap in c.decouple("U1.VCCA", MICROSD_HOST_BYPASS):
        cap.fields["LCSC"] = LCSC_BYPASS
    c.part("C2", "Device:C", MICROSD_CARD_BYPASS, C0603, LCSC=LCSC_BYPASS)
    c.part("C3", "Device:C", MICROSD_CARD_BULK, C0805, LCSC=LCSC_BULK)
    c.net("+VDD_CARD", "J1.VDD", "U1.VCCB0", "U1.VCCB1", "C2.1", "C3.1",
          "U2.VCC", *pull_pins)
    c.net("GND", "C2.2", "C3.2")
    for cap in c.decouple("U2.VCC", MICROSD_ESD_BYPASS):
        cap.fields["LCSC"] = LCSC_BYPASS

    c.net("GND", "U1.SEL", "U1.EP", "U1.GND",
          "J1.VSS", "J1.GND", "U2.GND")

    c.nc("U1.DAT2B1", "U1.DAT3B1", "U1.CMDB1", "U1.CLKB1",
         "U1.DAT0B1", "U1.DAT1B1")
    c.nc("U2.NC")

    c.testpoint("SD_CMD")
    c.testpoint("SD_CLK")

    c.draws("+VDD_CARD", DRAWS_CARD_A, draws_card_note)
    c.draws("+VDD_HOST", DRAWS_HOST_A, draws_host_note)
    return meta.finish(c)
