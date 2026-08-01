from __future__ import annotations

from schgen.core.link import load_subsystem
import subsystems.usb_uart_connector.usb_uart_connector as lib
from carrier.subsystems.usb_uart_connector import META


def test_adapter_matches_library_bound():
    adapter = load_subsystem("usb_uart_connector").circuit
    direct = lib.circuit(META)
    assert list(adapter.nets) == list(direct.nets)
    assert set(adapter.parts) == set(direct.parts)


def test_carrier_real_nets_present():
    adapter = load_subsystem("usb_uart_connector").circuit
    for real in ("GND", "CHASSIS_GND", "USB_UART_VBUS", "USB_UART_DP",
                 "USB_UART_DM"):
        assert real in adapter.nets, real


def test_no_abstract_library_name_leaks():
    adapter = load_subsystem("usb_uart_connector").circuit
    bind = META["bind"]
    for abstract in lib.INTERFACE:
        if bind.get(abstract, abstract) != abstract:
            assert abstract not in adapter.nets, abstract
