from __future__ import annotations

from devkit_mini.basis import PROJECT, register
from devkit_mini.som_conn_gen import SDIO_LEVEL_V
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

I2C_SPEED_HZ = register(
    "debug_boot.i2c_speed", 400_000, "Hz",
    "Fast-mode STM32_I2C2, shared with the two INA3221 monitors.",
    "datasheet")

I2C_PULLUP = register(
    "debug_boot.i2c_pullup", "4k7", "ohm",
    "The devkit omits bringup_rails, so its SC debug sheet owns one pull-up "
    "per STM32_I2C2 line to always-on +3V3_SC, matching the carrier and the "
    "INA3221/STM32 supply domain. C23162, 0603 1%. About 0.70 mA per "
    "asserted line; at 400 kHz the 300 ns rise-time limit allows about "
    "74 pF including resistor tolerance. Keep bus/probe stubs short and "
    "verify rise time at bring-up.",
    "datasheet")

I2C_PULLUP_DRAW_A = register(
    "debug_boot.i2c_pullup_draw", 0.0015, "A",
    "Both 4k7 lines held low: 2 * (3.3 V + 5%) / (4.7k - 1%) = "
    "1.49 mA, rounded up separately from BOOT0/BOOTSEL loads.",
    "policy")


def circuit() -> Circuit:
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'debug_boot', __file__)
