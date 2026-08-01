from __future__ import annotations

from schgen.core.link import load_subsystem
import subsystems.usbc_otg.usbc_otg as lib
from carrier.subsystems.usbc_otg import META


def test_adapter_matches_library_bound():
    adapter = load_subsystem("usbc_otg").circuit
    direct = lib.circuit(META)
    assert list(adapter.nets) == list(direct.nets)
    assert set(adapter.parts) == set(direct.parts)


def test_carrier_real_nets_present():
    adapter = load_subsystem("usbc_otg").circuit
    for real in ("+5V_USB", "+3V3_SC", "GND", "CHASSIS_GND", "USB_D+",
                 "USB_D-", "USB_VBUS", "VBUS_OUT_EN", "USBOTG_FLT_N",
                 "USB_ID"):
        assert real in adapter.nets, real


def test_no_abstract_library_name_leaks():
    adapter = load_subsystem("usbc_otg").circuit
    bind = META["bind"]
    for abstract in lib.INTERFACE:
        if bind.get(abstract, abstract) != abstract:
            assert abstract not in adapter.nets, abstract
