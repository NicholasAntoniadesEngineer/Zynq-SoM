"""Carrier board top-level configuration + block registry."""

from __future__ import annotations

from pathlib import Path

from zynq_eda.core.model.block import Block
from zynq_eda.projects.carrier.blocks.boot_switches import build_boot_switches
from zynq_eda.projects.carrier.blocks.ethernet import build_ethernet
from zynq_eda.projects.carrier.blocks.fmc_lpc import build_fmc_lpc
from zynq_eda.projects.carrier.blocks.hdmi_rx import build_hdmi_rx
from zynq_eda.projects.carrier.blocks.hdmi_tx import build_hdmi_tx
from zynq_eda.projects.carrier.blocks.jtag_swd import build_jtag_swd
from zynq_eda.projects.carrier.blocks.lvds_lcd import build_lvds_lcd
from zynq_eda.projects.carrier.blocks.microsd import build_microsd
from zynq_eda.projects.carrier.blocks.mipi_camera import build_mipi_camera
from zynq_eda.projects.carrier.blocks.pmod import build_pmod
from zynq_eda.projects.carrier.blocks.power import build_power
from zynq_eda.projects.carrier.blocks.power_mon import build_power_mon
from zynq_eda.projects.carrier.blocks.som_j1 import build_som_j1
from zynq_eda.projects.carrier.blocks.som_j2 import build_som_j2
from zynq_eda.projects.carrier.blocks.som_j3 import build_som_j3
from zynq_eda.projects.carrier.blocks.uart_bridge import build_uart_bridge
from zynq_eda.projects.carrier.blocks.usb_pd import build_usb_pd
from zynq_eda.projects.carrier.blocks.usbc_otg import build_usbc_otg


CARRIER_TITLE = "Zynq SoM Carrier"
CARRIER_OUTPUT_DIR_NAME = "carrier"


REPO_ROOT = Path(__file__).resolve().parents[5]


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
)


# Block order on the root sheet mirrors the carrier's functional reading order:
# power first (everything else hangs off it), then USB-PD (the carrier's input
# from USB-C), then peripherals (USB-OTG, UART bridge, video, network,
# storage, expansion headers, SoM mates).
_BLOCK_FACTORIES = {
    "power":         build_power,
    "power_mon":     build_power_mon,
    "usb_pd":        build_usb_pd,
    "usbc_otg":      build_usbc_otg,
    "uart_bridge":   build_uart_bridge,
    "hdmi_tx":       build_hdmi_tx,
    "hdmi_rx":       build_hdmi_rx,
    "ethernet":      build_ethernet,
    "microsd":       build_microsd,
    "lvds_lcd":      build_lvds_lcd,
    "mipi_camera":   build_mipi_camera,
    "fmc_lpc":       build_fmc_lpc,
    "pmod":          build_pmod,
    "jtag_swd":      build_jtag_swd,
    "boot_switches": build_boot_switches,
    "som_j1":        build_som_j1,
    "som_j2":        build_som_j2,
    "som_j3":        build_som_j3,
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
