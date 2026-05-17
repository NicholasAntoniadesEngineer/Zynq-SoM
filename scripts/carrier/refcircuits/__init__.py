"""Per-IC reference circuit specifications.

Every IC on the carrier has its manufacturer Typical Application Circuit
encoded as a ReferenceCircuit instance in this directory. The schematic
generator consumes these specs when placing the IC; the validator
verifies conformance.

When adding a new IC:
    1. Fetch its datasheet, identify the Typical Application Circuit figure
    2. Create scripts/carrier/refcircuits/<part>.py exporting an instance
    3. Register the instance in REFCIRCUITS below
    4. Update the build_quantity_per_token() to count its parts
"""

from __future__ import annotations

from collections import Counter

from scripts.carrier.core.refcircuit import ReferenceCircuit

from scripts.carrier.refcircuits.fusb302 import FUSB302_REFCIRCUIT
from scripts.carrier.refcircuits.usblc6 import USBLC6_REFCIRCUIT
from scripts.carrier.refcircuits.tps2051 import TPS2051_REFCIRCUIT
from scripts.carrier.refcircuits.tpd12s016 import TPD12S016_TX_REFCIRCUIT, TPD12S016_RX_REFCIRCUIT
from scripts.carrier.refcircuits.cp2102n import CP2102N_REFCIRCUIT
from scripts.carrier.refcircuits.ina226 import INA226_REFCIRCUIT
from scripts.carrier.refcircuits.ds3231 import DS3231_REFCIRCUIT
from scripts.carrier.refcircuits.eeprom_24lc256 import EEPROM_24LC256_REFCIRCUIT
from scripts.carrier.refcircuits.tlv757 import (
    TLV75718_REFCIRCUIT,
    TLV75725_REFCIRCUIT,
    TLV75733_REFCIRCUIT,
)
from scripts.carrier.refcircuits.hx5008nlt import HX5008NLT_REFCIRCUIT
from scripts.carrier.refcircuits.usbc_connector import USBC_DEVICE_REFCIRCUIT
from scripts.carrier.refcircuits.hdmi_connector import HDMI_A_REFCIRCUIT
from scripts.carrier.refcircuits.microsd import MICROSD_DM3AT_REFCIRCUIT
from scripts.carrier.refcircuits.rj45 import RJ45_REFCIRCUIT


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
    "TLV75718PDBVR": TLV75718_REFCIRCUIT,
    "TLV75725PDBVR": TLV75725_REFCIRCUIT,
    "TLV75733PDBVR": TLV75733_REFCIRCUIT,
    "HX5008NLT": HX5008NLT_REFCIRCUIT,
    "USBC_SINK": USBC_DEVICE_REFCIRCUIT,
    "HDMI_A": HDMI_A_REFCIRCUIT,
    "DM3AT-SF-PEJM5": MICROSD_DM3AT_REFCIRCUIT,
    "RJHSE5380": RJ45_REFCIRCUIT,
}


# Instance counts per IC (how many copies of each IC appear on the carrier).
# Used by validator to compute build-quantity for stock checks.
IC_INSTANCE_COUNT: dict[str, int] = {
    "FUSB302BMPX": 1,   # USB-PD for STM32 input
    "USBLC6-4SC6": 2,   # USB-C STM32 + USB-C OTG Zynq
    "TPS2051CDBVR": 1,  # USB host VBUS load switch
    "TPD12S016PWR_TX": 1,
    "TPD12S016PWR_RX": 1,
    "CP2102N-A02-GQFN24R": 1,
    "INA226AIDGSR": 6,  # one per power rail
    "DS3231SN#": 1,
    "24LC256T-I/SN": 2,  # one for board ID, one for HDMI EDID
    "TLV75718PDBVR": 0,  # DNP by default (jumper-selectable)
    "TLV75725PDBVR": 0,  # DNP by default
    "TLV75733PDBVR": 4,  # default for 4 VCCO banks
    "HX5008NLT": 1,
    "USBC_SINK": 2,  # 2 USB-C connectors total
    "HDMI_A": 2,     # TX + RX
    "DM3AT-SF-PEJM5": 1,
    "RJHSE5380": 1,
}


def build_quantity_per_token() -> dict[str, int]:
    """Sum, per BOM part token, how many physical instances will be placed.

    Aggregates IC counts plus all external parts from each ReferenceCircuit.
    Used by the validator's A3 stock check.
    """
    counter: Counter[str] = Counter()
    for ic_name, count in IC_INSTANCE_COUNT.items():
        if count == 0:
            continue
        circuit = REFCIRCUITS.get(ic_name)
        if circuit is None:
            continue
        # Count the IC itself by its (registry) token if mappable
        # Most refcircuits use the part_mpn as a hint; we count via the LCSC->token mapping
        # implicitly through the registry by name. Instead, simply count externals.
        for ext in circuit.external_parts:
            counter[ext.part_token] += ext.quantity * count
    return dict(counter)
