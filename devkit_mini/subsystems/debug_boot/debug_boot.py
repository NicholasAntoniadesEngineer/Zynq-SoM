from __future__ import annotations

from devkit_mini.basis import register
from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"

J1_MAP = "som_j1_connector"

JTAG_HEADER = register(
    "debug_boot.jtag_header", "878311420", "part",
    "Xilinx-standard 2x7 2.00 mm JTAG header (Molex 87831-1420) on the "
    "dedicated ZYNQ_T* nets. VREF = +3V3 = VCCO_0. Pin 14 SRST and pin 12 are "
    "explicit NCs — the SoM does not export them.",
    "datasheet")

SWD_HEADER = register(
    "debug_boot.swd_header", "HX_JN1.27-2x5_TP_H4.9", "part",
    "ARM Cortex 10-pin 1.27 mm SWD header on the SC's PA13/PA14 (J1 names "
    "STM32_GPIO6/5). VTref is the ALWAYS-ON +3V3_SC so debug works with the "
    "main rails down. SWO and KEY are explicit NCs.",
    "datasheet")

JTAG_PULLUP = register(
    "debug_boot.jtag_pullup", "4k7", "ohm",
    "Insurance pull-ups on TMS/TDI to +3V3 (= VCCO_0, the header VREF level), "
    "so the chain is defined with no pod attached. LCSC C23162.",
    "datasheet")

BOOT0_SERIES_R = register(
    "debug_boot.boot0_series_r", "100R", "ohm",
    "DIP pos 1 drives STM32_BOOT0 high through 100R against the SoM's 1k5 "
    "pull-down, so closed + reset selects USB DFU. The 100R/1k5 ratio is what "
    "makes the strap win without fighting the module pull hard. LCSC C22775.",
    "datasheet")

BOOTSEL_PULLUP = register(
    "debug_boot.bootsel_pullup", "10k", "ohm",
    "Defined-high pull for the BOOTSEL request straps and the spare; closing "
    "the DIP pulls the line to GND. SC firmware decodes these and drives the "
    "on-module Zynq BMODE pins. LCSC C25804.",
    "datasheet")

SC_DRAW_A = register(
    "debug_boot.sc_draw", 0.004, "A",
    "BOOT0 strap 3.3 V/(100R+1k5) ~= 2 mA when closed, plus three 10k "
    "BOOTSEL/spare pulls at ~0.33 mA each held.",
    "datasheet")

JTAG_DRAW_A = register("debug_boot.jtag_draw", 0.002, "A",
                       "The two 4k7 TMS/TDI insurance pulls when driven low.",
                       "datasheet")


def circuit() -> Circuit:
    c = Circuit("debug_boot", "JTAG + SWD headers, boot-request DIP, reset")
    c.use_part(JTAG_HEADER, ref="J1")
    c.use_part(SWD_HEADER, ref="J2", value="HX_JN1.27-2x5")
    c.use_part("DSHP04TSGER", ref="SW1", value="DIP-4")
    c.use_part("TS-1187A-B-A-B", ref="SW2", value="RESET")

    c.net("GND", "J1.1", "J1.3", "J1.5", "J1.7", "J1.9", "J1.11", "J1.13")
    c.net("+3V3", "J1.2")
    c.part("R1", "Device:R", JTAG_PULLUP, R0603, LCSC="C23162")
    c.part("R2", "Device:R", JTAG_PULLUP, R0603, LCSC="C23162")
    c.port("ZYNQ_TMS", "J1.4", "R1.2", expect=J1_MAP)
    c.port("ZYNQ_TCK", "J1.6", expect=J1_MAP)
    c.port("ZYNQ_TDO", "J1.8", expect=J1_MAP)
    c.port("ZYNQ_TDI", "J1.10", "R2.2", expect=J1_MAP)
    c.net("+3V3", "R1.1", "R2.1")
    c.nc("J1.12", "J1.14")

    c.net("+3V3_SC", "J2.1")
    c.net("GND", "J2.3", "J2.5", "J2.9")
    c.port("STM32_GPIO6", "J2.2", expect=J1_MAP)
    c.port("STM32_GPIO5", "J2.4", expect=J1_MAP)
    c.port("STM32_NRST", "J2.10", "SW2.1", "SW2.2", expect=J1_MAP)
    c.nc("J2.6", "J2.7", "J2.8")

    # The reset tact resets the SC = a whole-system reset; the RC debounce for
    # it lives on the SoM, not here.
    c.net("GND", "SW2.3", "SW2.4")

    c.part("R3", "Device:R", BOOT0_SERIES_R, R0603, LCSC="C22775")
    c.port("STM32_BOOT0", "SW1.1", expect=J1_MAP)
    c.net("BOOT0_SET", "SW1.8", "R3.2")
    c.net("+3V3_SC", "R3.1")
    c.part("R4", "Device:R", BOOTSEL_PULLUP, R0603, LCSC="C25804")
    c.part("R5", "Device:R", BOOTSEL_PULLUP, R0603, LCSC="C25804")
    c.port("STM32_GPIO7", "SW1.2", "R4.2", expect=J1_MAP)
    c.port("STM32_GPIO8", "SW1.3", "R5.2", expect=J1_MAP)
    c.net("GND", "SW1.7", "SW1.6")
    c.part("R6", "Device:R", BOOTSEL_PULLUP, R0603, LCSC="C25804")
    c.net("BOOT_SPARE", "SW1.4", "R6.2")
    c.net("GND", "SW1.5")
    c.net("+3V3_SC", "R4.1", "R5.1", "R6.1")

    c.draws("+3V3_SC", SC_DRAW_A, "BOOT0 strap ~2 mA closed + BOOTSEL pulls")
    c.draws("+3V3", JTAG_DRAW_A, "JTAG TMS/TDI 4k7 insurance pulls when driven")
    return c
