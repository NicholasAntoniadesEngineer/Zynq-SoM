from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.pmod.pmod as pmod
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "pmod.cir"

_CARRIER_PORT_NETS = {
    "PMOD0": ["IO_L2_P_13", "IO_L2_N_13", "IO_L3_P_13", "IO_L3_N_13",
              "IO_L4_P_13", "IO_L4_N_13", "IO_L5P_13", "IO_L5_N_13"],
    "PMOD1": ["IO_L7_P_13", "IO_L7_N_13", "IO_L8_P_13", "IO_L8_N_13",
              "IO_L9_DQS_P_13", "IO_L9_DQS_N_13", "IO_L10_P_13", "IO_L10_N_13"],
}
_CARRIER_BIND = {"+VCC_PMOD": "+3V3_PMOD", "GND": "GND",
                 **{f"{port}_SIG{io}": net
                    for port, nets in _CARRIER_PORT_NETS.items()
                    for io, net in enumerate(nets, start=1)}}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return pmod.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(pmod.INTERFACE), externals
    assert not any(n.endswith("_13") or n == "+3V3_PMOD" for n in externals), \
        externals


def test_interface_shape(c: Circuit):
    assert pmod.RAILS == ("+VCC_PMOD", "GND")
    assert len(pmod.PORTS) == 16
    assert pmod.PORTS[:8] == tuple(f"PMOD0_SIG{i}" for i in range(1, 9))
    assert pmod.PORTS[8:] == tuple(f"PMOD1_SIG{i}" for i in range(1, 9))


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in pmod.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in pmod.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_internal_io_nets_stay_private_signal(c: Circuit):
    signal = {n.name for n in c.nets.values()
              if n.net_class is NetClass.SIGNAL}
    assert signal == {f"PMOD{p}_IO{io}"
                      for p in (0, 1) for io in range(1, 9)}, signal
    assert not (signal & set(pmod.INTERFACE))


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"U1.5", "U2.5", "U3.5", "U4.5"}, \
        {str(p) for p in c.nc_pins}


def test_four_esd_arrays_clamp_all_sixteen_io(c: Circuit):
    esd_refs = {ref for ref, p in c.parts.items() if p.value == "TPD4E1U06"}
    assert esd_refs == {"U1", "U2", "U3", "U4"}, esd_refs
    for ref in esd_refs:
        assert c.net_of(PinRef(ref, "2")).name == "GND"
    for port_net in pmod.PORTS:
        net = c.nets[port_net]
        assert any(p.ref in esd_refs for p in net.pins), (port_net, net.pins)


def test_200r_series_on_every_io(c: Circuit):
    res = [(ref, p) for ref, p in c.parts.items() if p.lib_id.endswith(":R")]
    assert len(res) == 16, [r for r, _ in res]
    assert {p.value for _, p in res} == {"200R"}
    for port in ("PMOD0", "PMOD1"):
        for io in range(1, 9):
            sig = f"{port}_SIG{io}"
            iol = f"{port}_IO{io}"
            bridging = [ref for ref, _ in res
                        if {n.name for n in (c.net_of(PinRef(ref, "1")),
                                             c.net_of(PinRef(ref, "2"))) if n}
                        == {sig, iol}]
            assert len(bridging) == 1, (sig, iol, bridging)


def test_each_port_has_a_local_vcc_bypass(c: Circuit):
    bypass = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if nets == {"+VCC_PMOD", "GND"}:
            bypass.append(p.value)
    assert sorted(bypass) == ["100n", "100n", "10u", "10u"], sorted(bypass)


def test_design_rules_slice_runs_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_bypass_caps_voltage_derated_for_rail(c: Circuit):
    rail_v = pmod.RAIL_NOM_V["+VCC_PMOD"]
    seen = 0
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if "+VCC_PMOD" not in nets:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail (<1.3x)")
        seen += 1
    assert seen == 4, seen


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_passives() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt pmod"):
            in_subckt = True
            continue
        if in_subckt and s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^[RC]\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    text = CIR.read_text()
    lines = text.splitlines()
    hdr = []
    started = False
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith(".subckt pmod"):
            hdr.append(s)
            started = True
            continue
        if started and s.startswith("+"):
            hdr.append(s[1:].strip())
            continue
        if started:
            break
    pins = " ".join(hdr).split()[2:]
    want = ["VCC_PMOD"] + [f"PMOD{p}_SIG{io}"
                           for p in (0, 1) for io in range(1, 9)] + ["GND"]
    assert pins == want, pins
    iface = {n.lstrip("+") for n in pmod.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":R") or p.lib_id.endswith(":C"))
    cir = sorted(_cir_passives().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = pmod.circuit()
    bound = pmod.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    expect = [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert list(bound.nets) == expect
    assert "PMOD0_IO1" in bound.nets and "PMOD1_IO8" in bound.nets
    assert "+3V3_PMOD" in bound.loads and "+VCC_PMOD" not in bound.loads


def test_bind_carries_port_deferral_payload():
    bound = pmod.circuit({
        "bind": _CARRIER_BIND,
        "expects": {f"{port}_SIG{io}": "som_j2_connector"
                    for port in ("PMOD0", "PMOD1") for io in range(1, 9)},
    })
    assert bound.port_type_of("IO_L2_P_13").expect == "som_j2_connector"
    assert bound.port_type_of("IO_L10_N_13").expect == "som_j2_connector"


def test_bind_identity_is_noop():
    base = pmod.circuit()
    ident = pmod.circuit({"bind": {n: n for n in pmod.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    base = pmod.circuit()
    m = pmod.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VCC_PMOD"][0][1] == "custom note"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        pmod.circuit({"note": {"draws": "X"}})


def test_bind_rejects_unknown_name():
    c = pmod.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_PMOD"})


def test_bind_rejects_signal_net():
    c = pmod.circuit()
    assert c.nets["PMOD0_IO1"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"PMOD0_IO1": "SOMETHING"})


def test_bind_rejects_collision():
    c = pmod.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"PMOD0_SIG1": "SHARED", "PMOD0_SIG2": "SHARED"})
