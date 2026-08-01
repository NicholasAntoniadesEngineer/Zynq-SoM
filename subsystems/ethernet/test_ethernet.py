from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.ethernet.ethernet as ethernet
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "ethernet.cir"

_CARRIER_BIND = {
    "CHASSIS_GND": "CHASSIS_GND",
    "MDI0_P": "ETH_PHY_MDI0_P", "MDI0_N": "ETH_PHY_MDI0_N",
    "MDI1_P": "ETH_PHY_MDI1_P", "MDI1_N": "ETH_PHY_MDI1_N",
    "MDI2_P": "ETH_PHY_MDI2_P", "MDI2_N": "ETH_PHY_MDI2_N",
    "MDI3_P": "ETH_PHY_MDI3_P", "MDI3_N": "ETH_PHY_MDI3_N",
    "MX0_P": "ETH_LINE_MDI_0_P", "MX0_N": "ETH_LINE_MDI_0_N",
    "MX1_P": "ETH_LINE_MDI_1_P", "MX1_N": "ETH_LINE_MDI_1_N",
    "MX2_P": "ETH_LINE_MDI_2_P", "MX2_N": "ETH_LINE_MDI_2_N",
    "MX3_P": "ETH_LINE_MDI_3_P", "MX3_N": "ETH_LINE_MDI_3_N",
}

_RJ45_DEFER = "rj45_connector (wave 2)"
_CARRIER_EXPECTS = {f"MX{n}_P": _RJ45_DEFER for n in range(4)}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return ethernet.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(ethernet.INTERFACE), externals
    assert not any(n.startswith("ETH_PHY") or n.startswith("ETH_LINE")
                   for n in externals), externals
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert {"MCT1", "MCT2", "MCT3", "MCT4", "BS_COMMON"} == signals, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["CHASSIS_GND"] is NetClass.GROUND, cls["CHASSIS_GND"]
    for port in ethernet.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_mdi_and_mx_pairs_typed(c: Circuit):
    for n in range(4):
        for pp, pn in ((f"MDI{n}_P", f"MDI{n}_N"), (f"MX{n}_P", f"MX{n}_N")):
            tp, tn = c.port_type_of(pp), c.port_type_of(pn)
            assert tp.kind == "diff_pair" and tn.kind == "diff_pair", (pp, pn)
            assert tp.impedance == 100 and tn.impedance == 100, (pp, pn)
            assert tp.pair_with == pn and tn.pair_with == pp, (pp, pn)


def test_hx5008nl_pin_faithful_mapping(c: Circuit):
    expect = [(0, 2, 3, 23, 22, 24, 1),
              (1, 5, 6, 20, 19, 21, 4),
              (2, 8, 9, 17, 16, 18, 7),
              (3, 11, 12, 14, 13, 15, 10)]
    for ch, td_p, td_n, mx_p, mx_n, mct, tct in expect:
        assert {str(p) for p in c.nets[f"MDI{ch}_P"].pins} == {f"T1.{td_p}"}
        assert {str(p) for p in c.nets[f"MDI{ch}_N"].pins} == {f"T1.{td_n}"}
        assert {str(p) for p in c.nets[f"MX{ch}_P"].pins} == {f"T1.{mx_p}"}
        assert {str(p) for p in c.nets[f"MX{ch}_N"].pins} == {f"T1.{mx_n}"}
        assert PinRef("T1", str(mct)) in c.nets[f"MCT{ch + 1}"].pins
        assert PinRef("T1", str(tct)) in c.nc_pins
    assert c.parts["T1"].lib_id.endswith("HX5008NLT") or \
        "HX5008NLT" in c.parts["T1"].lib_id


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"T1.1", "T1.4", "T1.7", "T1.10"}


def test_bob_smith_per_centre_tap(c: Circuit):
    for ch in range(4):
        mct = f"MCT{ch + 1}"
        names = {str(p) for p in c.nets[mct].pins}
        assert f"R{ch + 1}.1" in names and f"C{ch + 1}.1" in names, (mct, names)
        bs = {str(p) for p in c.nets["BS_COMMON"].pins}
        assert f"R{ch + 1}.2" in bs and f"C{ch + 1}.2" in bs, bs
        assert c.parts[f"R{ch + 1}"].value == "75R"
        assert c.parts[f"C{ch + 1}"].value == "1n"


def test_isolation_barrier_cap_to_chassis(c: Circuit):
    bs = {str(p) for p in c.nets["BS_COMMON"].pins}
    ch = {str(p) for p in c.nets["CHASSIS_GND"].pins}
    assert "C5.1" in bs, bs
    assert "C5.2" in ch, ch
    assert c.parts["C5"].value == "1n"
    for ref in ("C1", "C2", "C3", "C4", "C5"):
        lcsc = c.parts[ref].fields["LCSC"]
        assert RATINGS_BY_LCSC[lcsc].v_max >= 2000, (ref, lcsc)


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt ethernet"):
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
    lines = CIR.read_text().splitlines()
    hdr_idx = next(i for i, line in enumerate(lines)
                   if line.strip().lower().startswith(".subckt ethernet"))
    header = lines[hdr_idx].split()[2:]
    j = hdr_idx + 1
    while j < len(lines) and lines[j].lstrip().startswith("+"):
        header += lines[j].lstrip()[1:].split()
        j += 1
    assert header == [
        "MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N", "MDI2_P", "MDI2_N",
        "MDI3_P", "MDI3_N", "MX0_P", "MX0_N", "MX1_P", "MX1_N",
        "MX2_P", "MX2_N", "MX3_P", "MX3_N", "CHASSIS_GND"], header
    assert set(header) == set(ethernet.INTERFACE), header


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = ethernet.circuit()
    bound = ethernet.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert bound.port_type_of("ETH_PHY_MDI0_P").pair_with == "ETH_PHY_MDI0_N"
    assert bound.port_type_of("ETH_PHY_MDI0_N").pair_with == "ETH_PHY_MDI0_P"
    assert bound.port_type_of("ETH_LINE_MDI_2_P").pair_with == "ETH_LINE_MDI_2_N"
    assert bound.port_type_of("ETH_LINE_MDI_2_P").impedance == 100


def test_bind_with_expects_threads_media_deferral():
    bound = ethernet.circuit({"bind": _CARRIER_BIND,
                              "expects": _CARRIER_EXPECTS})
    for n in range(4):
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_P").expect == _RJ45_DEFER
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_N").expect == _RJ45_DEFER
        assert bound.port_type_of(f"ETH_PHY_MDI{n}_P").expect is None
        assert bound.port_type_of(f"ETH_PHY_MDI{n}_N").expect is None


def test_bind_identity_is_noop():
    base = ethernet.circuit()
    ident = ethernet.circuit({"bind": {n: n for n in ethernet.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        ethernet.circuit({"bus": {"x": "Y"}})


def test_bind_rejects_unknown_name():
    c = ethernet.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    c = ethernet.circuit()
    assert c.nets["BS_COMMON"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"BS_COMMON": "SOMETHING"})


def test_bind_rejects_collision():
    c = ethernet.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"MDI0_P": "SHARED", "MDI0_N": "SHARED"})
