from __future__ import annotations

import carrier.subsystems.rj45_connector as pkg
from carrier.subsystems.rj45_connector import circuit, META
from subsystems.rj45_connector import rj45_connector as _lib


def test_package_reexports_circuit_and_meta():
    assert callable(pkg.circuit)
    assert isinstance(pkg.META, dict) and "bind" in pkg.META
    assert set(pkg.__all__) == {"circuit", "META"}


def test_bind_equivalent_to_library():
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
    nets = set(circuit().nets)
    missing = sorted(v for v in META["bind"].values() if v not in nets)
    assert not missing, f"carrier bind targets absent from circuit: {missing}"


def test_no_abstract_leak():
    nets = set(circuit().nets)
    leaked = sorted(src for src, dst in META["bind"].items()
                    if src != dst and src in nets)
    assert not leaked, f"abstract net names leaked through the bind: {leaked}"


def test_carrier_specific_nets_bound():
    nets = set(circuit().nets)
    assert "+3V3" in nets and "+VLED" not in nets
    assert "ETH_LINE_MDI_0_P" in nets and "RJ45_MDI0_P" not in nets
