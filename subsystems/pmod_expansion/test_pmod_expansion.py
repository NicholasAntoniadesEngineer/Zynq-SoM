from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.pmod_expansion.pmod_expansion as pmod_expansion
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "pmod_expansion.cir"

_CARRIER_BIND = {
    "+VDD_PMOD": "+3V3",
    "+VSW_PMOD": "+3V3_PMODX",
    "GND": "GND",
    "PMOD_IO1": "PMODX_IO1", "PMOD_IO2": "PMODX_IO2",
    "PMOD_IO3": "PMODX_IO3", "PMOD_IO4": "PMODX_IO4",
    "PMOD_IO5": "PMODX_IO5", "PMOD_IO6": "PMODX_IO6",
    "PMOD_IO7": "PMODX_IO7", "PMOD_IO8": "PMODX_IO8",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return pmod_expansion.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(pmod_expansion.INTERFACE), externals
    carrier = {"+3V3", "+3V3_PMODX"} | {f"PMODX_IO{i}" for i in range(1, 9)}
    assert not (externals & carrier), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in pmod_expansion.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in pmod_expansion.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    for port in pmod_expansion.PORTS:
        assert c.port_type_of(port).kind == "single", port


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {
        "SW1.2", "SW1.4", "SW1.6", "U2.5", "U3.5"}


def test_internal_signal_nets_present(c: Circuit):
    sigs = {n.name for n in c.nets.values()
            if n.net_class is NetClass.SIGNAL}
    assert sigs == {"EN_PMODX", "BS_ISET_PMODX", "BS_PG_PMODX"}, sigs


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_load_switch_bypass_present(c: Circuit):
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            nets = [c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))]
            names = {n.name for n in nets if n}
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("+VDD_PMOD") == ["100n", "10u"]
    assert caps_to_gnd("+VSW_PMOD") == ["100n", "100n", "10u"]


def test_two_esd_arrays_clamp_all_eight_io(c: Circuit):
    esd_refs = {ref for ref, p in c.parts.items()
                if p.value == "TPD4E1U06"}
    assert esd_refs == {"U2", "U3"}, esd_refs
    for ref in esd_refs:
        assert c.net_of(PinRef(ref, "2")).name == "GND"
    for port in pmod_expansion.PORTS:
        pins = c.nets[port].pins
        assert any(p.ref in esd_refs for p in pins), (port, pins)


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    worst = pmod_expansion.RAIL_WORST_V
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = [c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))]
        rail_v = max((worst.get(n.name, 0.0) for n in nets if n), default=0.0)
        if rail_v <= 0:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail "
            f"(<1.3x margin)")


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt pmod_expansion"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    header = next(line for line in CIR.read_text().splitlines()
                  if line.strip().lower().startswith(".subckt pmod_expansion"))
    pins = header.split()[2:]
    assert pins == ["VDD_PMOD", "VSW_PMOD", "GND"], pins
    iface = {n.lstrip("+") for n in pmod_expansion.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = pmod_expansion.circuit()
    bound = pmod_expansion.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    for sig in ("EN_PMODX", "BS_ISET_PMODX", "BS_PG_PMODX"):
        assert sig in bound.nets
    assert "+3V3_PMODX" in bound.loads and "+VSW_PMOD" not in bound.loads


def test_bind_repoints_testpoint_value():
    bound = pmod_expansion.circuit({"bind": _CARRIER_BIND})
    tp = next(p for p in bound.parts.values()
              if p.lib_id == Circuit.TP_LIB_ID)
    assert tp.value == "+3V3_PMODX"


def test_bind_identity_is_noop():
    base = pmod_expansion.circuit()
    ident = pmod_expansion.circuit(
        {"bind": {n: n for n in pmod_expansion.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    base = pmod_expansion.circuit()
    m = pmod_expansion.circuit({"notes": {"draws_pmod": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VSW_PMOD"][0][1] == "custom note"


def test_meta_expects_attaches_port_deferral():
    m = pmod_expansion.circuit({"expects": {"PMOD_IO1": "my_connector"}})
    assert m.port_type_of("PMOD_IO1").expect == "my_connector"
    assert m.port_type_of("PMOD_IO2").expect is None


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        pmod_expansion.circuit({"note": {"draws_pmod": "X"}})


def test_bind_rejects_unknown_name():
    c = pmod_expansion.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3"})


def test_bind_rejects_signal_net():
    c = pmod_expansion.circuit()
    sig = next(n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL)
    assert sig in ("EN_PMODX", "BS_ISET_PMODX", "BS_PG_PMODX")
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({sig: "SOMETHING"})


def test_bind_rejects_collision():
    c = pmod_expansion.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"PMOD_IO1": "SHARED", "PMOD_IO2": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = pmod_expansion.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
