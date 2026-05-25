"""Per-IC reference circuit specifications."""

from __future__ import annotations

from collections import Counter

from zynq_eda.core.model.refcircuit import ReferenceCircuit

from zynq_eda.catalog.refcircuits.fusb302 import FUSB302_REFCIRCUIT
from zynq_eda.catalog.refcircuits.usblc6 import USBLC6_REFCIRCUIT
from zynq_eda.catalog.refcircuits.tps2051 import TPS2051_REFCIRCUIT
from zynq_eda.catalog.refcircuits.tpd12s016 import (
    TPD12S016_RX_REFCIRCUIT,
    TPD12S016_TX_REFCIRCUIT,
)
from zynq_eda.catalog.refcircuits.cp2102n import CP2102N_REFCIRCUIT
from zynq_eda.catalog.refcircuits.ina226 import INA226_REFCIRCUIT
from zynq_eda.catalog.refcircuits.ds3231 import DS3231_REFCIRCUIT
from zynq_eda.catalog.refcircuits.eeprom_24lc256 import EEPROM_24LC256_REFCIRCUIT
from zynq_eda.catalog.refcircuits.eeprom_24lc256_edid import EEPROM_24LC256_EDID_REFCIRCUIT
from zynq_eda.catalog.refcircuits.tlv757 import (
    TLV75718_REFCIRCUIT,
    TLV75725_REFCIRCUIT,
    TLV75733_REFCIRCUIT,
)
from zynq_eda.catalog.refcircuits.hx5008nlt import HX5008NLT_REFCIRCUIT
from zynq_eda.catalog.refcircuits.usbc_connector import USBC_DEVICE_REFCIRCUIT
from zynq_eda.catalog.refcircuits.hdmi_connector import HDMI_A_REFCIRCUIT
from zynq_eda.catalog.refcircuits.microsd import MICROSD_DM3AT_REFCIRCUIT
from zynq_eda.catalog.refcircuits.rj45 import RJ45_REFCIRCUIT
from zynq_eda.catalog.refcircuits.power_input import POWER_INPUT_REFCIRCUIT
from zynq_eda.catalog.refcircuits.fmc_lpc import FMC_LPC_REFCIRCUIT
from zynq_eda.catalog.refcircuits.pmod import PMOD_REFCIRCUIT
from zynq_eda.catalog.refcircuits.lvds_lcd import LVDS_LCD_REFCIRCUIT
from zynq_eda.catalog.refcircuits.mipi_camera import MIPI_CAMERA_REFCIRCUIT
from zynq_eda.catalog.refcircuits.jtag_header import JTAG_HEADER_REFCIRCUIT
from zynq_eda.catalog.refcircuits.swd_header import SWD_HEADER_REFCIRCUIT
from zynq_eda.catalog.refcircuits.sma_clock import SMA_CLOCK_REFCIRCUIT
from zynq_eda.catalog.refcircuits.user_led import USER_LED_REFCIRCUIT
from zynq_eda.catalog.refcircuits.tactile_switch import TACTILE_SWITCH_REFCIRCUIT
from zynq_eda.catalog.refcircuits.dip_switch import DIP_SWITCH_REFCIRCUIT


REFCIRCUITS: dict[str, ReferenceCircuit] = {
    "FUSB302BMPX": FUSB302_REFCIRCUIT,
    "USBLC6-4SC6": USBLC6_REFCIRCUIT,
    "TPS2051CDBVR": TPS2051_REFCIRCUIT,
    "TPD12S016PWR_TX": TPD12S016_TX_REFCIRCUIT,
    "TPD12S016PWR_RX": TPD12S016_RX_REFCIRCUIT,
    "CP2102N-A02-GQFN24R": CP2102N_REFCIRCUIT,
    "INA226AIDGSR": INA226_REFCIRCUIT,
    "DS3231SN#": DS3231_REFCIRCUIT,
    "24LC256T-I/SN": EEPROM_24LC256_REFCIRCUIT,
    "24LC256T-I/SN_EDID": EEPROM_24LC256_EDID_REFCIRCUIT,
    "TLV75718PDBVR": TLV75718_REFCIRCUIT,
    "TLV75725PDBVR": TLV75725_REFCIRCUIT,
    "TLV75733PDBVR": TLV75733_REFCIRCUIT,
    "HX5008NLT": HX5008NLT_REFCIRCUIT,
    "USBC_SINK": USBC_DEVICE_REFCIRCUIT,
    "HDMI_A": HDMI_A_REFCIRCUIT,
    "DM3AT-SF-PEJM5": MICROSD_DM3AT_REFCIRCUIT,
    "RJHSE5380": RJ45_REFCIRCUIT,
    "SS14": POWER_INPUT_REFCIRCUIT,
    "FX10A-168P-SV(91)": FMC_LPC_REFCIRCUIT,
    "PM254R-12-08-H85": PMOD_REFCIRCUIT,
    "FPC-05F-40PH20": LVDS_LCD_REFCIRCUIT,
    "1.0-15P": MIPI_CAMERA_REFCIRCUIT,
    "ZX-PM2.54-2-7PY": JTAG_HEADER_REFCIRCUIT,
    "HX-PZ1.27-2x5P-TP": SWD_HEADER_REFCIRCUIT,
    "KH-SMA-P-8496": SMA_CLOCK_REFCIRCUIT,
    "YLED0603G": USER_LED_REFCIRCUIT,
    "TS-1002S-06026C": TACTILE_SWITCH_REFCIRCUIT,
    "DS-04P": DIP_SWITCH_REFCIRCUIT,
}


IC_INSTANCE_COUNT: dict[str, int] = {
    "FUSB302BMPX": 1,
    "USBLC6-4SC6": 3,
    "TPS2051CDBVR": 1,
    "TPD12S016PWR_TX": 1,
    "TPD12S016PWR_RX": 1,
    "CP2102N-A02-GQFN24R": 1,
    "INA226AIDGSR": 6,
    "DS3231SN#": 1,
    "24LC256T-I/SN": 1,
    "24LC256T-I/SN_EDID": 1,
    "TLV75718PDBVR": 0,
    "TLV75725PDBVR": 0,
    "TLV75733PDBVR": 4,
    "HX5008NLT": 1,
    "USBC_SINK": 2,
    "HDMI_A": 2,
    "DM3AT-SF-PEJM5": 1,
    "RJHSE5380": 1,
    "SS14": 1,
    "FX10A-168P-SV(91)": 1,
    "PM254R-12-08-H85": 2,
    "FPC-05F-40PH20": 1,
    "1.0-15P": 1,
    "ZX-PM2.54-2-7PY": 1,
    "HX-PZ1.27-2x5P-TP": 1,
    "KH-SMA-P-8496": 2,
    "YLED0603G": 4,
    "TS-1002S-06026C": 4,
    "DS-04P": 1,
}


def build_quantity_per_token() -> dict[str, int]:
    counter: Counter[str] = Counter()
    for ic_name, count in IC_INSTANCE_COUNT.items():
        if count == 0:
            continue
        circuit = REFCIRCUITS.get(ic_name)
        if circuit is None:
            continue
        for ext in circuit.external_parts:
            counter[ext.part_token] += ext.quantity * count
    return dict(counter)
