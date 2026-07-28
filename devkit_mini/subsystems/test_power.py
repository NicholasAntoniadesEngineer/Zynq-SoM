"""BIND guard for the carrier power ADAPTER.

This is a THIN ADAPTER over the project-agnostic library subsystem
``subsystems/power/`` — it owns no netlist, only the carrier bind contract
(``META``). The deep electrical proofs (model completeness, decoupling, FB
dividers, the LM61460 heat path, ratings, the SPICE passive network) live in the
library's own ``subsystems/power/test_power.py`` and are NOT duplicated here.

What this guard proves — the only thing the adapter can drift on — is that the
carrier circuit the board build discovers is BYTE-IDENTICAL to binding the
library subsystem with ``META``:

  * adapter ``circuit()`` == ``_lib.circuit(META)`` net-for-net, pin-for-pin,
    part-for-part (so the emitted carrier sheet + its golden render are stable);
  * the bind renames ONLY the external rails/ports (every internal SIGNAL net is
    untouched) and is order-preserving;
  * the carrier real net names are exactly the documented bind targets;
  * the EN-port deferral (``expects``) and the carrier draw-note overrides
    (``notes``) survive into the bound circuit.

The cross-board gates (EN linker graph, full power-tree headroom, thermal join,
board ERC, the netlist merge) stay aggregated by ``schgen board``.
"""

from __future__ import annotations

import pytest

from schgen.core.model import NetClass

from schgen.core.link import load_subsystem
import subsystems.power.power as _lib       # the project-agnostic library subsystem
from devkit_mini.subsystems.power import circuit as build, META


# The documented carrier bind (must match power.py META["bind"] exactly).
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
def c():
    """The carrier-bound circuit the board build actually discovers (via the same
    importlib-by-file path schgen uses), not just ``build()`` — so the discovery
    surface is exercised too."""
    return load_subsystem("power").circuit


@pytest.fixture
def ref():
    """The library subsystem bound with the carrier META — the reference the
    adapter must reproduce byte-for-byte."""
    return _lib.circuit(META)


def _pins(c, net):
    return sorted(f"{p.ref}.{p.pin}" for p in c.nets[net].pins)


# ---- META is the documented contract -------------------------------------------

def test_meta_bind_is_the_documented_map():
    assert META["bind"] == _CARRIER_BIND


def test_exposed_circuit_matches_discovery():
    """The package's exported ``circuit()`` (devkit_mini/subsystems/power/__init__.py)
    builds the SAME netlist the board discovers by file — no skew between the
    importable entry point and the discovery path."""
    assert list(build().nets) == list(load_subsystem("power").circuit.nets)


def test_meta_defers_the_en_ports_to_bringup():
    """Every EN port carries an explicit linker deferral (never a silent open)."""
    for en in ("EN_VOUT_5V", "EN_VOUT_3V3", "EN_VOUT_1V8"):
        assert en in META["expects"]
        assert "bringup" in META["expects"][en]


# ---- the adapter reproduces lib.circuit(META) byte-for-byte --------------------

def test_adapter_equals_lib_bound_netlist(c, ref):
    """The adapter circuit is the SAME object-shape as binding the library with
    META: identical net set + order, identical pin membership per net, identical
    parts. This is what keeps the emitted sheet + golden render byte-stable."""
    assert c.name == ref.name
    assert list(c.nets) == list(ref.nets)
    for net in c.nets:
        assert _pins(c, net) == _pins(ref, net), net
    assert {r: (p.lib_id, p.value, p.footprint) for r, p in c.parts.items()} == \
           {r: (p.lib_id, p.value, p.footprint) for r, p in ref.parts.items()}
    assert {str(p) for p in c.nc_pins} == {str(p) for p in ref.nc_pins}


def test_bind_renames_only_externals(c):
    """Every carrier real net is present; no library ABSTRACT external name
    leaked through unbound (the rename is total over the externals)."""
    nets = set(c.nets)
    for real in _CARRIER_BIND.values():
        assert real in nets, real
    # the abstract external names must be GONE (renamed) — none survive
    abstract = set(_CARRIER_BIND) - {"GND"}     # GND is an identity bind
    assert not (abstract & nets), abstract & nets


def test_internal_signal_nets_untouched(c, ref):
    """Binding touches NO internal SIGNAL net — the private regulator wiring
    (SW/FB/BOOT/BIAS/VCC/RT/PG nodes) is byte-identical to the unbound library."""
    base = _lib.circuit()        # unbound (abstract) library circuit
    sig_base = {n.name for n in base.nets.values()
                if n.net_class is NetClass.SIGNAL}
    sig_bound = {n.name for n in c.nets.values()
                 if n.net_class is NetClass.SIGNAL}
    assert sig_base == sig_bound, sig_base ^ sig_bound


def test_carrier_real_rail_classes(c):
    """The bound rails keep their POWER/GROUND class on the carrier names."""
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["GND"] is NetClass.GROUND
    for rail in ("+VIN_SYS", "+5V_REG", "+5V", "+3V3_REG", "+3V3",
                 "+1V8_REG", "+1V8"):
        assert cls[rail] is NetClass.POWER, (rail, cls[rail])


# ---- carrier draw-note overrides survive ---------------------------------------

def test_carrier_draw_notes_survive(c):
    """The carrier dossier wording for each rail's draw budget reaches the bound
    circuit (keeps carrier/reports/power_tree.txt byte-identical to the hand
    sheet)."""
    notes = {rail: " ".join(note for _, note in entries)
             for rail, entries in c.loads.items()}
    assert notes["+5V"] == META["notes"]["draws_5v"]
    assert notes["+3V3"] == META["notes"]["draws_3v3"]
    assert notes["+1V8"] == META["notes"]["draws_1v8"]
