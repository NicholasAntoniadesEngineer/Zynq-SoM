"""Tests for the firmware-contract I2C address map (re-audit fix).

The SC-firmware contract DERIVES the board-ID EEPROM's 7-bit address from its
A1/A0 straps (so a strap edit cannot silently drift the contract) and the
generator fails loudly on any address collision. These lock that behaviour as
pure, offline assertions — no kicad-cli, no SoM netlist, no board build.
"""

from __future__ import annotations

import pytest

from schgen.core.link import load_subsystem
from schgen.core.model import Circuit
from schgen.generate.firmware import ID_EEPROM_BASE, RV3028_ADDR, _id_eeprom_addr


@pytest.fixture(scope="module")
def services():
    return load_subsystem("board_services").circuit


def test_id_eeprom_derives_0x51(services):
    # A0 = +3V3_AUX (1), A1 = GND (0)  ->  0x50 | 0b01 = 0x51
    assert _id_eeprom_addr(services) == 0x51


def test_id_eeprom_is_strap_derived_not_the_base(services):
    # the value must come from reading the netlist, not the bare base constant
    # (0x50); the A0=1 strap lifts it to 0x51.
    assert _id_eeprom_addr(services) != ID_EEPROM_BASE
    assert _id_eeprom_addr(services) == (ID_EEPROM_BASE | 0x1)


def test_aux_bus_addresses_are_distinct():
    # the EEPROM base + strapped ID-EEPROM (0x51) + RTC must all be distinct
    assert len({ID_EEPROM_BASE, 0x51, RV3028_ADDR}) == 3


def test_misstrap_to_0x50_is_derivable():
    # a synthetic mis-strap (A0=A1=GND) must derive the bare 0x50 base — proving
    # the helper truly reads the straps (not a hard-coded 0x51).
    c = Circuit("t", "t")
    c.use_part("24AA025E48T-I_OT", ref="U1")
    c.net("+3V3", "U1.VCC")
    c.net("GND", "U1.VSS", "U1.A0", "U1.A1")        # both straps low -> 0x50
    c.net("AUX_SCL", "U1.SCL")
    c.net("AUX_SDA", "U1.SDA")
    assert _id_eeprom_addr(c) == ID_EEPROM_BASE      # the bare base 0x50


def test_missing_eeprom_raises():
    # if the ID-EEPROM is ever removed, the contract generator must fail loudly
    from schgen.generate.firmware import FirmwareError
    c = Circuit("t", "t")
    c.part("R1", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
    c.net("GND", "R1.2")
    c.net("+3V3", "R1.1")
    with pytest.raises(FirmwareError):
        _id_eeprom_addr(c)
