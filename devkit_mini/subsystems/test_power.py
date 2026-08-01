from __future__ import annotations

import pytest

from schgen.core.model import NetClass

from schgen.core.link import load_subsystem
import subsystems.power.power as _lib
from devkit_mini.subsystems.power import circuit as build, META


_CARRIER_BIND = {
    "+VIN": "+VIN_SYS",
    "+VOUT_5V_REG": "+5V_REG",
    "+VOUT_5V": "+5V",
    "+VOUT_3V3_REG": "+3V3_REG",
    "+VOUT_3V3": "+3V3",
    "+VOUT_1V8_REG": "+1V8_REG",
    "+VOUT_1V8": "+1V8",
    "GND": "GND",
    "EN_VOUT_5V": "EN_5V0",
    "EN_VOUT_3V3": "EN_3V3",
    "EN_VOUT_1V8": "EN_1V8",
}


@pytest.fixture
def discovered():
    return load_subsystem("power").circuit


@pytest.fixture
def lib_bound():
    return _lib.circuit(META)


def _pins(circuit, net):
    return sorted(f"{p.ref}.{p.pin}" for p in circuit.nets[net].pins)


def test_meta_bind_is_the_documented_map():
    assert META["bind"] == _CARRIER_BIND


def test_exposed_circuit_matches_discovery():
    assert list(build().nets) == list(load_subsystem("power").circuit.nets)


def test_meta_defers_the_en_ports_to_bringup():
    for en in ("EN_VOUT_5V", "EN_VOUT_3V3", "EN_VOUT_1V8"):
        assert en in META["expects"]
        assert "bringup" in META["expects"][en]


def test_adapter_equals_lib_bound_netlist(discovered, lib_bound):
    assert discovered.name == lib_bound.name
    assert list(discovered.nets) == list(lib_bound.nets)
    for net in discovered.nets:
        assert _pins(discovered, net) == _pins(lib_bound, net), net
    def shape(circuit):
        return {r: (p.lib_id, p.value, p.footprint)
                for r, p in circuit.parts.items()}
    assert shape(discovered) == shape(lib_bound)
    assert {str(p) for p in discovered.nc_pins} == {str(p) for p in lib_bound.nc_pins}


def test_bind_renames_only_externals(discovered):
    nets = set(discovered.nets)
    for real in _CARRIER_BIND.values():
        assert real in nets, real
    abstract = set(_CARRIER_BIND) - {"GND"}
    assert not (abstract & nets), abstract & nets


def test_internal_signal_nets_untouched(discovered, lib_bound):
    base = _lib.circuit()
    sig_base = {n.name for n in base.nets.values()
                if n.net_class is NetClass.SIGNAL}
    sig_bound = {n.name for n in discovered.nets.values()
                 if n.net_class is NetClass.SIGNAL}
    assert sig_base == sig_bound, sig_base ^ sig_bound


def test_carrier_real_rail_classes(discovered):
    cls = {n.name: n.net_class for n in discovered.nets.values()}
    assert cls["GND"] is NetClass.GROUND
    for rail in ("+VIN_SYS", "+5V_REG", "+5V", "+3V3_REG", "+3V3",
                 "+1V8_REG", "+1V8"):
        assert cls[rail] is NetClass.POWER, (rail, cls[rail])


def test_carrier_draw_notes_survive(discovered):
    notes = {rail: " ".join(note for _, note in entries)
             for rail, entries in discovered.loads.items()}
    assert notes["+5V"] == META["notes"]["draws_5v"]
    assert notes["+3V3"] == META["notes"]["draws_3v3"]
    assert notes["+1V8"] == META["notes"]["draws_1v8"]
