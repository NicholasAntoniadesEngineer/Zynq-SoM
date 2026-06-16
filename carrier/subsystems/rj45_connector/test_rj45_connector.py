"""byte-identical-BIND guard for the carrier rj45_connector ADAPTER package.

This is a THIN ADAPTER over the project-agnostic library subsystem
``subsystems/rj45_connector/``. The folded package must keep doing EXACTLY what
the flat ``carrier/subsystems/rj45_connector.py`` did: expose ``circuit()`` that
returns the library subsystem bound through ``META`` to the carrier's real net
names. So the test that matters here is a BIND guard, not a re-derivation of the
device — the library's own ``subsystems/rj45_connector/test_rj45_connector.py``
proves the electrical content; the board build proves the rendered sheet.

Guarantees:
  * BIND equivalence — the adapter's ``circuit()`` is net-for-net identical to
    ``_lib.circuit(META)`` (so the adapter adds NOTHING but the bind).
  * carrier names appear — every ``META["bind"]`` target net is a real net in
    the bound circuit.
  * no abstract leak — no abstract interface net name that was bound to a
    DIFFERENT carrier name survives in the bound circuit.
  * the package re-exports ``circuit`` and ``META`` (discovery + this test
    import the package, not the inner module).
"""

from __future__ import annotations

import carrier.subsystems.rj45_connector as pkg
from carrier.subsystems.rj45_connector import circuit, META
from subsystems.rj45_connector import rj45_connector as _lib


def test_package_reexports_circuit_and_meta():
    assert callable(pkg.circuit)
    assert isinstance(pkg.META, dict) and "bind" in pkg.META
    assert set(pkg.__all__) == {"circuit", "META"}


def test_bind_equivalent_to_library():
    """The adapter is the library subsystem bound through META — net-for-net,
    part-for-part identical, nothing added."""
    adapter = circuit()
    lib = _lib.circuit(META)
    assert adapter.name == lib.name == "rj45_connector"
    assert set(adapter.nets) == set(lib.nets)
    assert set(adapter.parts) == set(lib.parts)
    for n in adapter.nets:
        ap = {f"{p.ref}.{p.pin}" for p in adapter.nets[n].pins}
        lp = {f"{p.ref}.{p.pin}" for p in lib.nets[n].pins}
        assert ap == lp, (n, ap ^ lp)


def test_carrier_names_appear():
    """Every META bind target is a real net in the bound carrier circuit."""
    nets = set(circuit().nets)
    missing = sorted(v for v in META["bind"].values() if v not in nets)
    assert not missing, f"carrier bind targets absent from circuit: {missing}"


def test_no_abstract_leak():
    """No abstract interface net that was REMAPPED to a different carrier name
    survives in the bound circuit (the bind must fully rename)."""
    nets = set(circuit().nets)
    leaked = sorted(src for src, dst in META["bind"].items()
                    if src != dst and src in nets)
    assert not leaked, f"abstract net names leaked through the bind: {leaked}"


def test_carrier_specific_nets_bound():
    """Spot-check the carrier always-on LED rail + the line-side MDI nets are the
    ones in the netlist (not the abstract +VLED / RJ45_MDIn_*), proving this is
    the CARRIER bind. ETH_LINE_MDI_x is the peer net the ethernet sheet defers."""
    nets = set(circuit().nets)
    assert "+3V3" in nets and "+VLED" not in nets
    assert "ETH_LINE_MDI_0_P" in nets and "RJ45_MDI0_P" not in nets
