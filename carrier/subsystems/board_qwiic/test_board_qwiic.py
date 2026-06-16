"""LOCAL electrical-correctness test for the carrier board_qwiic subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + the
analytic SPICE slice; no kicad-cli, no network, no board). Mirrors the shape of
subsystems/usb_pd/test_usb_pd.py, adapted for a CARRIER-LOCAL PURE-CONNECTOR
subsystem: real carrier net names wired directly (no abstract-interface / bind
contract), and it adds NO R/C filter network of its own (the AUX-bus pull-ups
live once on board_aux), so the decap/ratings slices are trivially clean and the
SPICE subckt has no netlist passives — the asserted facts are the ESD-array
topology and the always-on clamp reference.

LOCAL checks:
  * model completeness  — every physical pin netted-or-NC (LAW 0), and there is
    NO no-connect (every connector/array pin is used).
  * design_rules slice  — DECAP/EP/STRAP clean (this sheet has no supply IC, so
    the decap rule has nothing to enforce — proven, not skipped).
  * SPICE                — the subckt declares the carrier externals as its pins,
    has no netlist-passive caps (the .cir's cap set is empty == the netlist's),
    and the analytic spice slice runs clean.
  * netlist invariants  — the USBLC6 1<->6 / 3<->4 ESD passthrough, the protected
    pair reaching AUX_I2C only THROUGH the array, the ALWAYS-ON clamp reference
    (+3V3, not the gated rail) and the gated connector POWER (J1.2 = +3V3_AUX).

CROSS-BOARD checks stay at board level: the full power tree, board ERC, and the
link/port-driver graph that resolves AUX_I2C back to board_aux — aggregated by
`schgen board`.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, spice
from schgen.verify.powertree import parse_si

from carrier.subsystems.board_qwiic import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "board_qwiic.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return build()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _pins(c: Circuit, net: str) -> set[str]:
    return {f"{p.ref}.{p.pin}" for p in c.nets[net].pins} if net in c.nets else set()


# ---- model completeness --------------------------------------------------------

def test_is_board_qwiic(c: Circuit):
    assert c.name == "board_qwiic"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every physical pin netted or NC (LAW 0). A pure connector + ESD sheet has
    NO intentional no-connect — every pin is used."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == set()


# ---- design_rules LOCAL slice --------------------------------------------------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    """DECAP/EP/STRAP clean. This sheet has no supply IC, so the decap rule has
    nothing to enforce (checked == 0) — a proven no-op, not a skipped check."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) == 0


# ---- SPICE subckt <-> netlist passives -----------------------------------------

def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt board_qwiic"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_carrier_externals():
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt board_qwiic"))
    pins = header.split()[2:]
    assert pins == ["GND", "V3V3_AUX", "AUX_I2C_SDA", "AUX_I2C_SCL", "V3V3"], pins


def test_cir_has_no_netlist_passive_caps(c: Circuit):
    """A pure connector + ESD sheet adds no capacitor network; the .cir cap set
    is empty and equals the netlist's empty cap set."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    assert netlist == []
    assert sorted(_cir_caps().values()) == netlist


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- netlist invariants --------------------------------------------------------

def test_parts_present(c: Circuit):
    """The QWIIC receptacle and the USBLC6 ESD array are the real parts."""
    assert c.parts["J1"].lib_id.split(":")[-1] == "ZX-SH1.0-4PWT"
    assert c.parts["U1"].lib_id.split(":")[-1] == "USBLC6-2SC6"


def test_esd_passthrough(c: Circuit):
    """USBLC6 1<->6 / 3<->4: external lines on U1.1/U1.3, the protected pair (->
    the isolated bus) on U1.6/U1.4."""
    assert "U1.1" in _pins(c, "QWIIC_SDA")           # external SDA at the array
    assert "U1.3" in _pins(c, "QWIIC_SCL")
    assert "U1.6" in _pins(c, "AUX_I2C_SDA")         # protected -> isolated bus
    assert "U1.4" in _pins(c, "AUX_I2C_SCL")


def test_external_lines_reach_bus_only_through_array(c: Circuit):
    """The connector's SDA/SCL (J1.3/J1.4) must go THROUGH the array, never
    straight onto the isolated bus."""
    assert not ({"J1.3", "J1.4"} & _pins(c, "AUX_I2C_SDA"))
    assert not ({"J1.3", "J1.4"} & _pins(c, "AUX_I2C_SCL"))


def test_clamp_reference_is_always_on(c: Circuit):
    """LAW 0: the ESD clamp reference (U1.5) is the ALWAYS-ON +3V3, NOT the gated
    +3V3_AUX, so protection is valid in every power state; the connector POWER
    (J1.2) stays gated (+3V3_AUX) per constraint C1."""
    assert "U1.5" in _pins(c, "+3V3")
    assert "U1.5" not in _pins(c, "+3V3_AUX")
    assert "J1.2" in _pins(c, "+3V3_AUX")


def test_aux_i2c_ports_typed(c: Circuit):
    """The protected pair is published as AUX_I2C ports (typed i2c 400 kHz) for
    board_aux / board_services."""
    assert c.port_type_of("AUX_I2C_SDA").bus == "AUX_I2C"
    assert c.port_type_of("AUX_I2C_SCL").bus == "AUX_I2C"
    assert c.port_type_of("AUX_I2C_SDA").kind == "i2c"
    assert c.port_type_of("AUX_I2C_SDA").role == "sda"
    assert c.port_type_of("AUX_I2C_SCL").role == "scl"
    assert c.port_type_of("AUX_I2C_SCL").speed_hz == 400_000
