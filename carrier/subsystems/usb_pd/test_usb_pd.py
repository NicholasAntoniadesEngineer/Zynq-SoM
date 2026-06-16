"""BIND GUARD for the usb_pd carrier adapter package.

Offline (model only; no kicad-cli, no network, no board). Proves the foldered
carrier adapter is EXACTLY the reusable library subsystem bound to the carrier
META — the byte-identical-sheet contract restated as a net-level invariant:

  * the adapter circuit's net list == the library circuit bound to this META
    (same nets, same order), and its parts set matches;
  * every carrier REAL net the bind map produces is present;
  * NO abstract library interface name (the renamed-away rails/ports) leaks
    into the bound carrier circuit.

If any of these trips, the fold drifted from the hand-written sheet (or the
generic library changed under the adapter) — the golden-render byte check would
also fail downstream, but this catches it locally and offline.
"""

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
    """Every abstract interface name the META renames away must be ABSENT from
    the bound carrier circuit (only identity binds like GND survive verbatim)."""
    adapter = load_subsystem("usb_pd").circuit
    bind = META["bind"]
    for abstract in lib.INTERFACE:
        if bind.get(abstract, abstract) != abstract:   # renamed away
            assert abstract not in adapter.nets, abstract
