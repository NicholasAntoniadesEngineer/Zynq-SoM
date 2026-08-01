from __future__ import annotations

from schgen.core.link import load_subsystem
import subsystems.usb_pd.usb_pd as lib
from carrier.subsystems.usb_pd import META


def test_adapter_matches_library_bound():
    adapter = load_subsystem("usb_pd").circuit
    direct = lib.circuit(META)
    assert list(adapter.nets) == list(direct.nets)
    assert set(adapter.parts) == set(direct.parts)


def test_carrier_real_nets_present():
    adapter = load_subsystem("usb_pd").circuit
    for real in ("+3V3_SC", "+VBUS_IN", "STM32_USB_CC1", "STM32_USB_CC2",
                 "STM32_I2C2_SDA", "STM32_I2C2_SCL", "SC_INT_N", "GND"):
        assert real in adapter.nets, real


def test_no_abstract_library_name_leaks():
    adapter = load_subsystem("usb_pd").circuit
    bind = META["bind"]
    for abstract in lib.INTERFACE:
        if bind.get(abstract, abstract) != abstract:
            assert abstract not in adapter.nets, abstract
