"""Block-factory registry — 19 real functional blocks, no placeholders."""

from collections.abc import Callable

from scripts.carrier.blocks import (
    aux_io,
    boot_switches,
    ethernet,
    fmc_lpc,
    hdmi_rx,
    hdmi_tx,
    jtag_swd,
    lvds_lcd,
    mipi_camera,
    pmod,
    power,
    power_mon,
    som_connector,
    uart_bridge,
    usb_pd,
    usbc_otg,
    microsd,
    xadc_clk,
)
from scripts.carrier.model.block import Block


BlockFactory = Callable[[], Block]


BLOCK_FACTORIES: dict[str, BlockFactory] = {
    "som_j1": som_connector.build_j1,
    "som_j2": som_connector.build_j2,
    "som_j3": som_connector.build_j3,
    "usb_pd": usb_pd.build,
    "power": power.build,
    "power_mon": power_mon.build,
    "aux_io": aux_io.build,
    "usbc_otg": usbc_otg.build,
    "uart_bridge": uart_bridge.build,
    "jtag_swd": jtag_swd.build,
    "boot_switches": boot_switches.build,
    "ethernet": ethernet.build,
    "microsd": microsd.build,
    "hdmi_tx": hdmi_tx.build,
    "hdmi_rx": hdmi_rx.build,
    "lvds_lcd": lvds_lcd.build,
    "mipi_camera": mipi_camera.build,
    "fmc_lpc": fmc_lpc.build,
    "pmod": pmod.build,
    "xadc_clk": xadc_clk.build,
}


def all_block_factories() -> dict[str, BlockFactory]:
    return dict(BLOCK_FACTORIES)


__all__ = [
    "BlockFactory",
    "BLOCK_FACTORIES",
    "all_block_factories",
]
