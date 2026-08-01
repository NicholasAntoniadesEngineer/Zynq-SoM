from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SUBS = _ROOT / "carrier" / "subsystems"

ALWAYS_ON = {"+3V3", "+3V3_SC", "+5V", "+5V_SOM", "+1V8", "+VIN", "VBUS"}


def _subsystem_file(stem):
    foldered = _SUBS / stem / f"{stem}.py"
    return foldered if foldered.exists() else _SUBS / f"{stem}.py"


def _load(stem):
    spec = importlib.util.spec_from_file_location(f"_sub_{stem}", _subsystem_file(stem))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.circuit()


def _pins(c, net):
    return {f"{p.ref}.{p.pin}" for p in c.nets[net].pins} if net in c.nets else set()


@pytest.fixture(scope="module")
def services():
    return _load("board_services")


@pytest.fixture(scope="module")
def aux():
    return _load("board_aux")


@pytest.fixture(scope="module")
def qwiic():
    return _load("board_qwiic")


def test_both_sheets_build(services, aux):
    assert services.name == "board_services"
    assert aux.name == "board_aux"


def test_c1_no_always_on_rail_in_services(services):
    touched = set(services.nets) & ALWAYS_ON
    assert not touched, f"board_services taps an always-on rail (breaks C1): {touched}"


def test_c1_gated_rail_is_the_supply(services):
    p = _pins(services, "+3V3_AUX")
    assert "U1.6" in p
    assert "U2.7" in p
    assert "U3.5" in p


def test_c2_watchdog_vdd_on_gated_rail(services):
    assert "U3.5" in _pins(services, "+3V3_AUX")


def test_c2_watchdog_mr_is_noconnect(services):
    on_a_net = any("U3.3" in _pins(services, n) for n in services.nets)
    assert not on_a_net, "watchdog MR# should be a no-connect"


def test_c2_watchdog_reset_is_a_pl_event_not_a_rail(services):
    assert "U3.1" in _pins(services, "WATCHDOG_RST_N")
    assert services.nets["WATCHDOG_RST_N"].name == "WATCHDOG_RST_N"
    assert "IO_L16_P_35" not in services.nets


def test_c3_watchdog_pl_pins_present(services):
    assert "WATCHDOG_KICK" in services.nets
    assert "WATCHDOG_RST_N" in services.nets
    assert "IO_L16_N_35" not in services.nets
    assert "IO_L16_P_35" not in services.nets


def test_eeprom_address_strap_0x51(services):
    assert "U1.5" in _pins(services, "+3V3_AUX")
    assert "U1.4" in _pins(services, "GND")


def test_rtc_evi_tied_low(services):
    assert "U2.8" in _pins(services, "GND")


def test_rtc_vbackup_to_coin_cell(services):
    bat = _pins(services, "V_RTC_BAT")
    assert "U2.6" in bat
    assert "BT1.1" in bat


def test_rtc_clkout_noconnect(services):
    on_a_net = any("U2.1" in _pins(services, n) for n in services.nets)
    assert not on_a_net, "RTC CLKOUT (pin 1) should be a no-connect"


def test_aux_rail_is_sourced_by_the_gate(aux):
    assert "U1.1" in _pins(aux, "+3V3_AUX")
    assert "U1.5" in _pins(aux, "+3V3")


def test_aux_isolator_reference_split(aux):
    assert "U2.2" in _pins(aux, "+3V3_SC")
    assert "U2.7" in _pins(aux, "+3V3_AUX")


def test_aux_isolator_en_follows_gated_rail(aux):
    en_net = next(n for n in aux.nets if "U2.8" in _pins(aux, n))
    rrefs = {p.ref for p in aux.nets[en_net].pins if p.ref.startswith("R")}
    assert rrefs, "PCA9306 EN has no pull resistor"
    pulled_to_aux = any(
        any(p.ref == r for p in aux.nets["+3V3_AUX"].pins) for r in rrefs)
    assert pulled_to_aux, "PCA9306 EN is not pulled to +3V3_AUX"


def test_qwiic_esd_clamps_the_external_lines(qwiic):
    assert "U1.1" in _pins(qwiic, "QWIIC_SDA")
    assert "U1.3" in _pins(qwiic, "QWIIC_SCL")
    assert "U1.6" in _pins(qwiic, "AUX_I2C_SDA")
    assert "U1.4" in _pins(qwiic, "AUX_I2C_SCL")


def test_qwiic_esd_clamp_ref_is_always_on(qwiic):
    assert "U1.5" in _pins(qwiic, "+3V3")
    assert "U1.5" not in _pins(qwiic, "+3V3_AUX")
    assert "J1.2" in _pins(qwiic, "+3V3_AUX")


def test_qwiic_external_pins_never_reach_the_bus_directly(qwiic):
    assert not ({"J1.3", "J1.4"} & _pins(qwiic, "AUX_I2C_SDA"))
    assert not ({"J1.3", "J1.4"} & _pins(qwiic, "AUX_I2C_SCL"))
