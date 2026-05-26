"""Carrier board top-level configuration + block registry."""

from __future__ import annotations

from pathlib import Path

from zynq_eda.core.model.block import Block
from zynq_eda.projects.carrier.blocks.boot_switches import build_boot_switches
from zynq_eda.projects.carrier.blocks.ethernet import build_ethernet
from zynq_eda.projects.carrier.blocks.fmc_lpc_la_high import build_fmc_lpc_la_high
from zynq_eda.projects.carrier.blocks.fmc_lpc_la_low import build_fmc_lpc_la_low
from zynq_eda.projects.carrier.blocks.fmc_lpc_power_clk_jtag import build_fmc_lpc_power_clk_jtag
from zynq_eda.projects.carrier.blocks.hdmi_rx import build_hdmi_rx
from zynq_eda.projects.carrier.blocks.hdmi_tx import build_hdmi_tx
from zynq_eda.projects.carrier.blocks.jtag_swd import build_jtag_swd
from zynq_eda.projects.carrier.blocks.lvds_lcd_power import build_lvds_lcd_power
from zynq_eda.projects.carrier.blocks.lvds_lcd_signals import build_lvds_lcd_signals
from zynq_eda.projects.carrier.blocks.microsd import build_microsd
from zynq_eda.projects.carrier.blocks.mipi_camera import build_mipi_camera
from zynq_eda.projects.carrier.blocks.pmod import build_pmod
from zynq_eda.projects.carrier.blocks.power import build_power
from zynq_eda.projects.carrier.blocks.power_mon import build_power_mon
from zynq_eda.projects.carrier.blocks.som_j1_mio import build_som_j1_mio
from zynq_eda.projects.carrier.blocks.som_j1_pl_power_gnd import build_som_j1_pl_power_gnd
from zynq_eda.projects.carrier.blocks.som_j1_ps_aux import build_som_j1_ps_aux
from zynq_eda.projects.carrier.blocks.som_j2_diff_pairs import build_som_j2_diff_pairs
from zynq_eda.projects.carrier.blocks.som_j2_power import build_som_j2_power
from zynq_eda.projects.carrier.blocks.som_j2_se import build_som_j2_se
from zynq_eda.projects.carrier.blocks.som_j3_diff_pairs import build_som_j3_diff_pairs
from zynq_eda.projects.carrier.blocks.som_j3_power import build_som_j3_power
from zynq_eda.projects.carrier.blocks.som_j3_se import build_som_j3_se
from zynq_eda.projects.carrier.blocks.uart_bridge import build_uart_bridge
from zynq_eda.projects.carrier.blocks.usb_pd import build_usb_pd
from zynq_eda.projects.carrier.blocks.usbc_otg import build_usbc_otg
from zynq_eda.projects.carrier.connector_bank_symbols import (
    bank_symbol_library_paths,
    generate_all_bank_symbols,
)


CARRIER_TITLE = "Zynq SoM Carrier"
CARRIER_OUTPUT_DIR_NAME = "carrier"


REPO_ROOT = Path(__file__).resolve().parents[5]


# Regenerate the per-bank sub-symbols on import so the library paths below
# always resolve to up-to-date .kicad_sym files. The generator is idempotent
# (small, deterministic outputs) so this is cheap.
_GENERATED_BANK_PATHS = generate_all_bank_symbols()


SHARED_SYMBOL_LIBRARIES: tuple[Path, ...] = (
    REPO_ROOT / "shared" / "symbols" / "zynq_eda.kicad_sym",
    # Generated connector symbols
    REPO_ROOT / "shared" / "symbols" / "generated" / "FMC_LPC_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "HDMITX_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "HDMIRX_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "MIPI_CAMERA_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "LVDS_LCD_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "PMOD_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "AUX_GPIO_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "STM32_BREAKOUT_IO.kicad_sym",
    REPO_ROOT / "shared" / "symbols" / "generated" / "XADC_MRCC_IO.kicad_sym",
    # Per-bank sub-symbols for high-pin-count connectors (J1/J2/J3 FX10A,
    # J4 FMC LPC, J5 LVDS FFC). Each .kicad_sym is generated from the
    # parent ``FX10A_168P``/``FMC_LPC``/``FFC_40P`` symbol's pin list.
    *bank_symbol_library_paths(),
)


# Block order on the root sheet mirrors the carrier's functional reading order:
# power first (everything else hangs off it), then USB-PD (the carrier's input
# from USB-C), then peripherals (USB-OTG, UART bridge, video, network,
# storage, expansion headers, SoM mates).
_BLOCK_FACTORIES = {
    "power":                  build_power,
    "power_mon":              build_power_mon,
    "usb_pd":                 build_usb_pd,
    "usbc_otg":               build_usbc_otg,
    "uart_bridge":            build_uart_bridge,
    "hdmi_tx":                build_hdmi_tx,
    "hdmi_rx":                build_hdmi_rx,
    "ethernet":               build_ethernet,
    "microsd":                build_microsd,
    "lvds_lcd_signals":       build_lvds_lcd_signals,
    "lvds_lcd_power":         build_lvds_lcd_power,
    "mipi_camera":            build_mipi_camera,
    "fmc_lpc_la_low":         build_fmc_lpc_la_low,
    "fmc_lpc_la_high":        build_fmc_lpc_la_high,
    "fmc_lpc_power_clk_jtag": build_fmc_lpc_power_clk_jtag,
    "pmod":                   build_pmod,
    "jtag_swd":                build_jtag_swd,
    "boot_switches":           build_boot_switches,
    "som_j1_mio":             build_som_j1_mio,
    "som_j1_ps_aux":          build_som_j1_ps_aux,
    "som_j1_pl_power_gnd":    build_som_j1_pl_power_gnd,
    "som_j2_diff_pairs":      build_som_j2_diff_pairs,
    "som_j2_se":              build_som_j2_se,
    "som_j2_power":           build_som_j2_power,
    "som_j3_diff_pairs":      build_som_j3_diff_pairs,
    "som_j3_se":              build_som_j3_se,
    "som_j3_power":           build_som_j3_power,
}


def block_names() -> tuple[str, ...]:
    return tuple(_BLOCK_FACTORIES.keys())


def build_blocks(only: str | None = None) -> list[Block]:
    """Return the carrier's block list. When ``only`` is set, return just that block."""
    if only is not None:
        if only not in _BLOCK_FACTORIES:
            raise KeyError(
                f"Unknown block {only!r}. Known blocks: "
                + ", ".join(sorted(_BLOCK_FACTORIES.keys()))
            )
        return [_BLOCK_FACTORIES[only]()]
    return [factory() for factory in _BLOCK_FACTORIES.values()]
