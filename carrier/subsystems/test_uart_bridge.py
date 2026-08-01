from __future__ import annotations

from carrier.subsystems.uart_bridge import circuit, META
from subsystems.uart_bridge import uart_bridge as _lib


def test_adapter_circuit_equals_library_bound_with_meta():
    adapter = circuit()
    lib = _lib.circuit(META)
    assert list(adapter.nets) == list(lib.nets)


def test_carrier_real_net_names_present():
    nets = set(circuit().nets)
    missing = [real for real in META["bind"].values() if real not in nets]
    assert not missing, f"carrier bind targets missing from netlist: {missing}"


def test_no_abstract_interface_name_leaks():
    nets = set(circuit().nets)
    leaked = [abstract for abstract, real in META["bind"].items()
              if abstract != real and abstract in nets]
    assert not leaked, f"abstract interface names leaked into the netlist: {leaked}"
