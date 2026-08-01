from __future__ import annotations

import types

import pytest

from schgen.core.model import Circuit, CircuitError, NetClass
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules

from subsystems.usb_pd import usb_pd as lib_usb_pd
from subsystems.usbc_otg import usbc_otg as lib_usbc_otg
from subsystems.microsd import microsd as lib_microsd
from subsystems.uart_bridge import uart_bridge as lib_uart_bridge

from examples.devkit_mini import devkit_mini as dk


@pytest.fixture(scope="module")
def lib() -> Library:
    return Library()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _externals(c: Circuit) -> set[str]:
    return {n.name for n in c.nets.values() if n.net_class is not NetClass.SIGNAL}


_CASES = [
    ("usb_pd", lib_usb_pd, dk.usb_pd_circuit, dk.USB_PD_META),
    ("usbc_otg", lib_usbc_otg, dk.usbc_otg_circuit, dk.USBC_OTG_META),
    ("microsd", lib_microsd, dk.microsd_circuit, dk.MICROSD_META),
    ("uart_bridge", lib_uart_bridge, dk.uart_bridge_circuit, dk.UART_BRIDGE_META),
]
_IDS = [c[0] for c in _CASES]

_CARRIER_NAMES = {
    "+3V3_SC", "+3V3", "+3V3_SD", "+5V_USB", "+1V8", "+VBUS_IN",
    "USB_D+", "USB_D-", "SC_INT_N", "VBUS_OUT_EN", "USBOTG_FLT_N",
    "SD_CARD_DETECT", "USB_UART_VBUS", "USB_UART_DP", "USB_UART_DM",
}
_CARRIER_PREFIXES = ("STM32", "SDIO_", "ZYNQ_PS")

# Mirrors carrier/subsystems/usb_pd.py META["bind"] — keep the two in sync.
_CARRIER_USB_PD_BIND = {
    "+VDD_LOGIC": "+3V3_SC", "+VBUS_SENSE": "+VBUS_IN", "GND": "GND",
    "CC1": "STM32_USB_CC1", "CC2": "STM32_USB_CC2",
    "I2C_SDA": "STM32_I2C2_SDA", "I2C_SCL": "STM32_I2C2_SCL",
    "INT_N": "SC_INT_N",
}

_IDENTITY_RAILS = ("GND", "CHASSIS_GND")
_MIN_SUBSYSTEMS_SHARING_A_RAIL = 2


def test_all_project_subsystems_are_covered():
    assert [name for name, _ in dk.PROJECT] == _IDS


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_subsystem_builds_under_devkit_bind(name, libmod, build, meta):
    c = build()
    assert isinstance(c, Circuit)
    assert c.name == name
    assert c.parts, "subsystem produced no parts"


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_devkit_names_present_no_abstract_or_carrier_leak(name, libmod, build, meta):
    bind = meta["bind"]
    ext = _externals(build())
    assert ext == set(bind.values()), (name, ext, set(bind.values()))
    abstract = set(libmod.INTERFACE)
    identity_bound = {a for a in abstract if bind.get(a) == a}
    assert (ext & abstract) <= identity_bound, (name, ext & abstract)
    assert not (ext & _CARRIER_NAMES), (name, ext & _CARRIER_NAMES)
    assert not any(e.startswith(_CARRIER_PREFIXES) for e in ext), (name, ext)


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_rail_and_port_net_classes_preserved(name, libmod, build, meta):
    c = build()
    bind = meta["bind"]
    cls = {n.name: n.net_class for n in c.nets.values()}
    for abstract in libmod.RAILS:
        real = bind[abstract]
        want = NetClass.GROUND if abstract in _IDENTITY_RAILS else NetClass.POWER
        assert cls[real] is want, (name, abstract, real, cls[real])
    for abstract in libmod.PORTS:
        real = bind[abstract]
        assert cls[real] is NetClass.PORT, (name, abstract, real, cls[real])


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_rejects_unknown_name(name, libmod, build, meta):
    c = libmod.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_REAL_PORT": "+3V3_MINI"})


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_rejects_signal_net(name, libmod, build, meta):
    c2 = Circuit("t", "t")
    c2.part("R1", "Device:R", "1k", "")
    c2.part("R2", "Device:R", "1k", "")
    c2.net("PRIVATE_MID", "R1.2", "R2.1")
    assert c2.nets["PRIVATE_MID"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c2.bind({"PRIVATE_MID": "SOMETHING"})


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_rejects_collision(name, libmod, build, meta):
    c = libmod.circuit()
    p1, p2 = libmod.PORTS[0], libmod.PORTS[1]
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({p1: "SHARED_BAD", p2: "SHARED_BAD"})


def test_meta_rejects_unknown_top_level_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        lib_usb_pd.circuit({"binds": dk.USB_PD_META["bind"]})


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bound_subsystem_passes_local_design_rules(name, libmod, build, meta, lib):
    # usbc_otg presents no decap-rule supply pin, so the rule-actually-ran
    # assertion belongs at the aggregate, not here.
    r = design_rules.check([_sheet(build())], lib)
    assert not r.decap, (name, r.decap)
    assert not r.ep, (name, r.ep)
    assert not r.strap, (name, r.strap)


def test_project_aggregate_exercises_decap_rule(lib):
    sheets = [_sheet(c) for _, c in dk.subsystem_circuits()]
    r = design_rules.check(sheets, lib)
    assert not (r.decap or r.ep or r.strap), r.findings
    assert r.checked.get("decap", 0) >= 1, r.checked


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bound_subsystem_passes_part_rules(name, libmod, build, meta, tmp_path):
    r = part_rules.run([_sheet(build())], tmp_path)
    assert r.ok, (name, r.findings)


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bound_subsystem_model_is_complete(name, libmod, build, meta, lib):
    c = build()
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_is_byte_stable_rename(name, libmod, build, meta):
    base = libmod.circuit()
    bound = build()
    bind = meta["bind"]
    assert set(bound.parts) == set(base.parts), name
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}, name
    expected_order = [bind.get(n, n) for n in base.nets]
    assert list(bound.nets) == expected_order, name


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_draw_budget_follows_renamed_rail(name, libmod, build, meta):
    bound = build()
    bind = meta["bind"]
    for rail in bound.loads:
        assert rail in bind.values(), (name, rail)
    abstract_power = {a for a in libmod.RAILS if bind.get(a, a) != a}
    assert not (set(bound.loads) & abstract_power), (name, bound.loads.keys())


def test_shared_logic_rail_and_gnd_are_one_net_across_subsystems():
    circs = dk.subsystem_circuits()
    assert {n for n, _ in circs} == set(_IDS)
    where: dict[str, list[str]] = {r: [] for r in dk.SHARED_RAILS}
    klass: dict[str, set] = {r: set() for r in dk.SHARED_RAILS}
    for name, c in circs:
        for rail in dk.SHARED_RAILS:
            net = c.nets.get(rail)
            if net is not None:
                where[rail].append(name)
                klass[rail].add(net.net_class)
    for rail in dk.SHARED_RAILS:
        assert len(where[rail]) >= _MIN_SUBSYSTEMS_SHARING_A_RAIL, (rail, where[rail])
        assert len(klass[rail]) == 1, (rail, klass[rail])
    assert set(where[dk.V3V3]) == set(_IDS), where[dk.V3V3]
    assert NetClass.POWER in klass[dk.V3V3]
    assert NetClass.GROUND in klass["GND"]


def test_no_devkit_net_collides_across_subsystems_by_accident():
    circs = dk.subsystem_circuits()
    owners: dict[str, list[str]] = {}
    for name, c in circs:
        for nm, net in c.nets.items():
            if net.net_class is not NetClass.SIGNAL:
                owners.setdefault(nm, []).append(name)
    shared = {nm: who for nm, who in owners.items() if len(who) > 1}
    assert set(shared) == set(dk.SHARED_RAILS), shared


def test_same_library_binds_to_carrier_or_devkit_from_one_source():
    carrier_bind = _CARRIER_USB_PD_BIND
    devkit_bind = dk.USB_PD_META["bind"]

    carrier_c = lib_usb_pd.circuit({"bind": carrier_bind})
    devkit_c = lib_usb_pd.circuit({"bind": devkit_bind})

    carrier_ext = _externals(carrier_c)
    devkit_ext = _externals(devkit_c)

    assert carrier_ext == set(carrier_bind.values())
    assert devkit_ext == set(devkit_bind.values())
    assert carrier_ext & devkit_ext == {"GND"}
    abstract = set(lib_usb_pd.INTERFACE) - {"GND"}
    assert not (carrier_ext & abstract)
    assert not (devkit_ext & abstract)
    assert set(carrier_c.parts) == set(devkit_c.parts)
    assert list(carrier_c.parts) == list(devkit_c.parts)


def test_devkit_uart_crossover_lives_in_the_bind_not_the_library():
    bind = dk.UART_BRIDGE_META["bind"]
    assert bind["UART_TXD"] == "FPGA_UART0_RXD"
    assert bind["UART_RXD"] == "FPGA_UART0_TXD"
    assert bind["UART_RTS_N"] == "FPGA_UART0_CTS_N"
    assert bind["UART_CTS_N"] == "FPGA_UART0_RTS_N"
    ext = _externals(dk.uart_bridge_circuit())
    assert {"FPGA_UART0_RXD", "FPGA_UART0_TXD",
            "FPGA_UART0_CTS_N", "FPGA_UART0_RTS_N"} <= ext


def test_devkit_subsystems_compose_no_shorts_or_opens():
    from schgen.layout import place
    from schgen.verify import cc_gate

    lib = Library()
    prepared = []
    for name, c in dk.subsystem_circuits():
        c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
        placement, routed, _geo = place.place_and_route(c, lib)
        prepared.append((name, c, placement, routed))
    assert [n for n, *_ in prepared] == ["usb_pd", "usbc_otg", "microsd",
                                         "uart_bridge"]
    res = cc_gate.check_board(prepared, lib)
    assert res.ok, res.summary()
