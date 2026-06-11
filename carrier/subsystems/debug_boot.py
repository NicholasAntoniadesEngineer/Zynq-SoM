"""debug_boot — Zynq JTAG header, STM32 SWD header, boot-request DIP, reset.

Per carrier/research/debug_boot_pmod.md (all nets verified against the SoM
netlist): Xilinx-standard 2x7 2.00mm JTAG header (Molex 87831-1420) on the
dedicated ZYNQ_T* nets with 4k7 insurance pull-ups on TMS/TDI (VREF = +3V3 =
VCCO_0); ARM Cortex 10-pin 1.27mm SWD header on the SC's PA13/PA14 (J1 names
STM32_GPIO6/5), VTref = always-on +3V3_SC so debug works with main rails down;
pin 14 SRST and SWO are explicit NCs (not exported by the SoM). Boot-mode DIP:
pos1 drives STM32_BOOT0 high through 100R against the SoM's 1k5 pull-down
(closed + reset = USB DFU), pos2/3 are BOOTSEL request straps to STM32_GPIO7/8
(SC firmware decodes -> drives the on-module Zynq BMODE pins), pos4 spare.
Reset tact resets the SC = whole-system reset (RC debounce lives on the SoM).
"""

from __future__ import annotations

from schgen.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"

J1_MAP = "som_j1_connector"


def circuit() -> Circuit:
    c = Circuit("debug_boot", "JTAG + SWD headers, boot-request DIP, reset")
    c.use_part("878311420", ref="J1")                        # 2x7 JTAG header
    c.use_part("HX_JN1.27-2x5_TP_H4.9", ref="J2", value="HX_JN1.27-2x5")
    c.use_part("DSHP04TSGER", ref="SW1", value="DIP-4")
    c.use_part("TS-1187A-B-A-B", ref="SW2", value="RESET")

    # ---- Zynq JTAG (2x7, odd row = GND shield) ----------------------------
    c.net("GND", "J1.1", "J1.3", "J1.5", "J1.7", "J1.9", "J1.11", "J1.13")
    c.net("+3V3", "J1.2")                          # VREF, = VCCO_0 level
    c.part("R1", "Device:R", "4k7", R0603, LCSC="C23162")
    c.part("R2", "Device:R", "4k7", R0603, LCSC="C23162")
    c.port("ZYNQ_TMS", "J1.4", "R1.2", expect=J1_MAP)
    c.port("ZYNQ_TCK", "J1.6", expect=J1_MAP)
    c.port("ZYNQ_TDO", "J1.8", expect=J1_MAP)
    c.port("ZYNQ_TDI", "J1.10", "R2.2", expect=J1_MAP)
    c.net("+3V3", "R1.1", "R2.1")
    c.nc("J1.12", "J1.14")                         # NC + SRST not on SoM J1

    # ---- STM32 SWD (ARM 10-pin; VTref on the always-on SC rail) -----------
    c.net("+3V3_SC", "J2.1")
    c.net("GND", "J2.3", "J2.5", "J2.9")
    c.port("STM32_GPIO6", "J2.2", expect=J1_MAP)   # PA13 = SWDIO
    c.port("STM32_GPIO5", "J2.4", expect=J1_MAP)   # PA14 = SWCLK
    c.port("STM32_NRST", "J2.10", "SW2.1", "SW2.2", expect=J1_MAP)
    c.nc("J2.6", "J2.7", "J2.8")                   # SWO unrouted, KEY, TDI

    # reset tact: other contact pair to GND (SoM provides the RC)
    c.net("GND", "SW2.3", "SW2.4")

    # ---- boot-request DIP (poles 1-4 pair with contacts 8-5) --------------
    # pos1: BOOT0 high through 100R vs the SoM's 1k5 pull-down -> USB DFU
    c.part("R3", "Device:R", "100R", R0603, LCSC="C22775")
    c.port("STM32_BOOT0", "SW1.1", expect=J1_MAP)
    c.net("BOOT0_SET", "SW1.8", "R3.2")
    c.net("+3V3_SC", "R3.1")
    # pos2/3: BOOTSEL[0:1] request straps, closed = GND, 10k defined-high
    c.part("R4", "Device:R", "10k", R0603, LCSC="C25804")
    c.part("R5", "Device:R", "10k", R0603, LCSC="C25804")
    c.port("STM32_GPIO7", "SW1.2", "R4.2", expect=J1_MAP)   # BOOTSEL0
    c.port("STM32_GPIO8", "SW1.3", "R5.2", expect=J1_MAP)   # BOOTSEL1
    c.net("GND", "SW1.7", "SW1.6")
    # pos4: spare, same defined-high pattern
    c.part("R6", "Device:R", "10k", R0603, LCSC="C25804")
    c.net("BOOT_SPARE", "SW1.4", "R6.2")
    c.net("GND", "SW1.5")
    c.net("+3V3_SC", "R4.1", "R5.1", "R6.1")
    return c
