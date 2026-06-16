"""BIND GUARD for the carrier usb_jtag ADAPTER (offline, no kicad / no board).

This is a CARRIER-LOCAL bind guard: it proves the thin adapter
(carrier/subsystems/usb_jtag/usb_jtag.py) binds the project-agnostic library
subsystem (subsystems/usb_jtag/) to the carrier's REAL net names byte-for-byte,
so the emitted carrier/schematic/usb_jtag.kicad_sch + its golden render stay
unchanged. The library's OWN electrical correctness is proven by
subsystems/usb_jtag/test_usb_jtag.py — this guard only checks the BIND.

Guarantees:
  * bind equivalence   — the adapter's circuit is exactly the library circuit
    built with the carrier META: list(adapter.nets) == list(lib.circuit(META).nets),
    same order, same names (the fold cannot drift the binding).
  * carrier nets appear — every real net named in META["bind"] is present.
  * no abstract leak    — no remapped ABSTRACT interface name (a bind key that
    differs from its real value) survives in the bound netlist (LAW 0: a leaked
    abstract name would be a silent open at board-merge time).
"""

from __future__ import annotations

from carrier.subsystems.usb_jtag import circuit, META
from subsystems.usb_jtag import usb_jtag as _lib


def test_adapter_circuit_equals_library_bound_with_meta():
    """The adapter circuit IS the library circuit built with the carrier META —
    identical net set AND order (the fold is byte-neutral to the binding)."""
    adapter = circuit()
    lib = _lib.circuit(META)
    assert list(adapter.nets) == list(lib.nets)


def test_carrier_real_net_names_present():
    """Every carrier real net the bind map targets appears in the bound netlist."""
    nets = set(circuit().nets)
    missing = [real for real in META["bind"].values() if real not in nets]
    assert not missing, f"carrier bind targets missing from netlist: {missing}"


def test_no_abstract_interface_name_leaks():
    """No remapped ABSTRACT interface name survives the bind (a leak would be a
    silent open when the board linker merges by real net name)."""
    nets = set(circuit().nets)
    leaked = [abstract for abstract, real in META["bind"].items()
              if abstract != real and abstract in nets]
    assert not leaked, f"abstract interface names leaked into the netlist: {leaked}"
