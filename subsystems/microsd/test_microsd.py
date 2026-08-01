from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.microsd.microsd as microsd
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "microsd.cir"

_CARRIER_BIND = {
    "+VDD_HOST": "+1V8", "+VDD_CARD": "+3V3_SD", "GND": "GND",
    "SD_CLK": "SDIO_CLK", "SD_CMD": "SDIO_CMD",
    "SD_D0": "SDIO_D0", "SD_D1": "SDIO_D1",
    "SD_D2": "SDIO_D2", "SD_D3": "SDIO_D3",
    "CD_N": "SD_CARD_DETECT",
}

_CARD_SIGNALS = {"SD_CARD_CLK", "SD_CARD_CMD", "SD_CARD_D0", "SD_CARD_D1",
                 "SD_CARD_D2", "SD_CARD_D3"}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return microsd.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(microsd.INTERFACE), externals
    assert "+1V8" not in externals and "+3V3_SD" not in externals
    assert not any(n.startswith("SDIO_") or n == "SD_CARD_DETECT"
                   for n in externals), externals


def test_card_side_nets_are_private_signal(c: Circuit):
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == _CARD_SIGNALS, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in microsd.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in microsd.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    for p in ("SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3"):
        pt = c.port_type_of(p)
        assert pt.kind == "sd_bus", (p, pt.kind)
        assert pt.level_v == microsd.HOST_LEVEL_V, (p, pt.level_v)


def test_two_distinct_supply_rails(c: Circuit):
    assert "+VDD_HOST" != "+VDD_CARD"
    host_u1 = {str(p) for p in c.nets["+VDD_HOST"].pins if p.ref == "U1"}
    card_u1 = {str(p) for p in c.nets["+VDD_CARD"].pins if p.ref == "U1"}
    assert len(host_u1) == 1, host_u1
    assert len(card_u1) == 2, card_u1
    assert host_u1.isdisjoint(card_u1)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    nc = {str(p) for p in c.nc_pins}
    assert any(s.startswith("U1.") for s in nc) and len(nc) >= 6, nc


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 1
    assert r.checked.get("ep", 0) >= 1


def test_each_rail_has_a_local_bypass(c: Circuit):
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
    assert caps_to_gnd("+VDD_HOST") == ["100n"]
    assert caps_to_gnd("+VDD_CARD") == ["100n", "100n", "22u"]


def test_card_pulls_are_100k_and_card_detect_10k(c: Circuit):
    pulls = sorted(p.value for ref, p in c.parts.items()
                   if p.lib_id.endswith(":R"))
    assert pulls == ["100k", "100k", "100k", "100k", "100k", "10k"], pulls


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
    worst = microsd.RAIL_WORST_V
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
        if s.lower().startswith(".subckt microsd"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_rails():
    header = next(line for line in CIR.read_text().splitlines()
                  if line.strip().lower().startswith(".subckt microsd"))
    pins = header.split()[2:]
    assert pins == ["VDD_HOST", "VDD_CARD", "GND"], pins
    iface = {n.lstrip("+") for n in microsd.INTERFACE}
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
    base = microsd.circuit()
    bound = microsd.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    expect = [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert list(bound.nets) == expect
    assert _CARD_SIGNALS <= set(bound.nets)
    assert bound.port_type_of("SDIO_CLK").kind == "sd_bus"
    assert bound.port_type_of("SDIO_CLK").level_v == microsd.HOST_LEVEL_V
    assert "+3V3_SD" in bound.loads and "+VDD_CARD" not in bound.loads
    assert "+1V8" in bound.loads and "+VDD_HOST" not in bound.loads


def test_bind_identity_is_noop():
    base = microsd.circuit()
    ident = microsd.circuit({"bind": {n: n for n in microsd.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    base = microsd.circuit()
    m = microsd.circuit({"notes": {"draws_card": "card note",
                                   "draws_host": "host note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VDD_CARD"][0][1] == "card note"
    assert m.loads["+VDD_HOST"][0][1] == "host note"


def test_expects_attaches_card_detect_deferral():
    m = microsd.circuit({"expects": {"CD_N": "my_connector"}})
    assert m.port_type_of("CD_N").expect == "my_connector"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        microsd.circuit({"bus": {"i2c": "X"}})


def test_bind_rejects_unknown_name():
    c = microsd.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_SD"})


def test_bind_rejects_signal_net():
    c = microsd.circuit()
    assert c.nets["SD_CARD_CLK"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"SD_CARD_CLK": "SOMETHING"})


def test_bind_rejects_collision():
    c = microsd.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"SD_D0": "SHARED", "SD_D1": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = microsd.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
