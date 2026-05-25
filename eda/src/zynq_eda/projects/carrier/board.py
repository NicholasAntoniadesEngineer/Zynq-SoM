"""Carrier board top-level configuration + block registry."""

from __future__ import annotations

from pathlib import Path

from zynq_eda.core.model.block import Block
from zynq_eda.projects.carrier.blocks.power import build_power
from zynq_eda.projects.carrier.blocks.power_mon import build_power_mon
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


_BLOCK_FACTORIES = {
    "power":       build_power,
    "usb_pd":      build_usb_pd,
    "power_mon":   build_power_mon,
    "usbc_otg":    build_usbc_otg,
    "uart_bridge": build_uart_bridge,
    # Additional blocks land in Stage 6 as they get implemented.
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
