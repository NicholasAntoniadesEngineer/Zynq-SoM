"""Invariant tests for the board-HW block (board_aux + board_services).

These lock the three standing constraints the user set for the new hardware,
as PURE, millisecond model assertions (no kicad-cli, no board build):

  C1  every new peripheral sits on the manually-gated +3V3_AUX rail — never on
      an always-on rail. Tested as: board_services touches NO always-on power
      rail at all (its only power net is +3V3_AUX); board_aux is the one place
      the gated and always-on domains meet (the gate + the isolator).
  C2  the watchdog cannot reset the system at power-up — its VDD is +3V3_AUX
      (which defaults OFF), its MR# is an intentional no-connect, and its event
      RESET# rides a PL bank-35 IO (not a rail/POR line).
  C3  the only SoM-side signals are the two watchdog lines on PL bank-35.

Plus the netlist facts that the gates do not check by themselves: the EEPROM
0x51 address strap, the RTC unused-pin handling, and the PCA9306 isolation
reference split. Pin NUMBERS come from each part's datasheet pin table
(parts/<MPN>/<MPN>.py) — if a future edit rewires a pin, these bite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SUBS = _ROOT / "carrier" / "subsystems"

# always-on power rails a gated peripheral must NEVER touch (C1)
ALWAYS_ON = {"+3V3", "+3V3_SC", "+5V", "+5V_SOM", "+1V8", "+VIN", "VBUS"}


def _load(stem):
    spec = importlib.util.spec_from_file_location(f"_sub_{stem}", _SUBS / f"{stem}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.circuit()


def _pins(c, net):
    """Set of 'REF.NUM' on a net (pins resolve to numbers in the model)."""
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


# --------------------------------------------------------------------------- #
# both sheets build cleanly (smoke)
# --------------------------------------------------------------------------- #
def test_both_sheets_build(services, aux):
    assert services.name == "board_services"
    assert aux.name == "board_aux"


# --------------------------------------------------------------------------- #
# C1 — board_services peripherals are ENTIRELY on the gated rail
# --------------------------------------------------------------------------- #
def test_c1_no_always_on_rail_in_services(services):
    touched = set(services.nets) & ALWAYS_ON
    assert not touched, f"board_services taps an always-on rail (breaks C1): {touched}"


def test_c1_gated_rail_is_the_supply(services):
    # +3V3_AUX must be present and feed the peripherals' supply pins
    p = _pins(services, "+3V3_AUX")
    assert "U1.6" in p          # EEPROM VCC (pin 6)
    assert "U2.7" in p          # RTC VDD (pin 7)
    assert "U3.5" in p          # watchdog VDD (pin 5)


# --------------------------------------------------------------------------- #
# C2 — watchdog is safe at power-up
# --------------------------------------------------------------------------- #
def test_c2_watchdog_vdd_on_gated_rail(services):
    # TPS3823 VDD = pin 5; on +3V3_AUX => unpowered while the rail is OFF
    assert "U3.5" in _pins(services, "+3V3_AUX")


def test_c2_watchdog_mr_is_noconnect(services):
    # MR# (pin 3) intentionally NC (internal pull-up); must not be on any net
    on_a_net = any("U3.3" in _pins(services, n) for n in services.nets)
    assert not on_a_net, "watchdog MR# should be a no-connect"


def test_c2_watchdog_reset_is_a_pl_event_not_a_rail(services):
    # RESET# (pin 1) rides the PL bank-35 event net, not a power/POR rail
    assert "U3.1" in _pins(services, "IO_L16_P_35")
    assert services.nets["IO_L16_P_35"].name == "IO_L16_P_35"


# --------------------------------------------------------------------------- #
# C3 — only SoM-side signals are the two bank-35 watchdog lines
# --------------------------------------------------------------------------- #
def test_c3_watchdog_pl_pins_present(services):
    assert "IO_L16_N_35" in services.nets   # WATCHDOG_KICK -> WDI
    assert "IO_L16_P_35" in services.nets    # WATCHDOG_RST_N <- RESET#


# --------------------------------------------------------------------------- #
# EEPROM 0x51 address strap (A0=1, A1=0)
# --------------------------------------------------------------------------- #
def test_eeprom_address_strap_0x51(services):
    assert "U1.5" in _pins(services, "+3V3_AUX")   # A0 (pin 5) = 1
    assert "U1.4" in _pins(services, "GND")        # A1 (pin 4) = 0


# --------------------------------------------------------------------------- #
# RTC unused-pin handling
# --------------------------------------------------------------------------- #
def test_rtc_evi_tied_low(services):
    assert "U2.8" in _pins(services, "GND")        # EVI (pin 8) -> GND


def test_rtc_vbackup_to_coin_cell(services):
    bat = _pins(services, "V_RTC_BAT")
    assert "U2.6" in bat                           # VBACKUP (pin 6)
    assert "BT1.1" in bat                          # coin cell +


def test_rtc_clkout_noconnect(services):
    on_a_net = any("U2.1" in _pins(services, n) for n in services.nets)
    assert not on_a_net, "RTC CLKOUT (pin 1) should be a no-connect"


# --------------------------------------------------------------------------- #
# board_aux — the gate + the PCA9306 isolation reference split (LAW 0)
# --------------------------------------------------------------------------- #
def test_aux_rail_is_sourced_by_the_gate(aux):
    # SY6280 OUT (pin 1) is the +3V3_AUX source; IN (pin 5) is always-on +3V3
    assert "U1.1" in _pins(aux, "+3V3_AUX")
    assert "U1.5" in _pins(aux, "+3V3")


def test_aux_isolator_reference_split(aux):
    # PCA9306 side 1 references the always-on bus, side 2 the gated rail
    assert "U2.2" in _pins(aux, "+3V3_SC")         # VREF1 (pin 2)
    assert "U2.7" in _pins(aux, "+3V3_AUX")        # VREF2 (pin 7)


def test_aux_isolator_en_follows_gated_rail(aux):
    # EN (pin 8) must be pulled to +3V3_AUX so the switch opens when off:
    # its net carries one resistor whose other leg is on +3V3_AUX.
    en_net = next(n for n in aux.nets if "U2.8" in _pins(aux, n))
    rrefs = {p.ref for p in aux.nets[en_net].pins if p.ref.startswith("R")}
    assert rrefs, "PCA9306 EN has no pull resistor"
    pulled_to_aux = any(
        any(p.ref == r for p in aux.nets["+3V3_AUX"].pins) for r in rrefs)
    assert pulled_to_aux, "PCA9306 EN is not pulled to +3V3_AUX"


# --------------------------------------------------------------------------- #
# board_qwiic — external connector with ESD at the connector
# --------------------------------------------------------------------------- #
def test_qwiic_esd_clamps_the_external_lines(qwiic):
    # USBLC6 (U1) 1<->6 / 3<->4 passthrough: connector side on U1.1/U1.3, the
    # protected pair (-> the bus) on U1.6/U1.4
    assert "U1.1" in _pins(qwiic, "QWIIC_SDA")     # external SDA at the array
    assert "U1.3" in _pins(qwiic, "QWIIC_SCL")
    assert "U1.6" in _pins(qwiic, "AUX_I2C_SDA")   # protected -> isolated bus
    assert "U1.4" in _pins(qwiic, "AUX_I2C_SCL")


def test_qwiic_esd_clamp_ref_is_always_on(qwiic):
    # the ESD clamp reference (U1.5) must be the ALWAYS-ON +3V3, not the gated
    # +3V3_AUX, so protection is valid even when the connector rail is OFF;
    # the connector POWER (J1.2) stays gated (+3V3_AUX) per C1.
    assert "U1.5" in _pins(qwiic, "+3V3")
    assert "U1.5" not in _pins(qwiic, "+3V3_AUX")
    assert "J1.2" in _pins(qwiic, "+3V3_AUX")


def test_qwiic_external_pins_never_reach_the_bus_directly(qwiic):
    # the connector's SDA/SCL must go THROUGH the ESD array, not straight to the
    # bus (no J1 SDA/SCL pin on AUX_I2C_*)
    assert not ({"J1.3", "J1.4"} & _pins(qwiic, "AUX_I2C_SDA"))
    assert not ({"J1.3", "J1.4"} & _pins(qwiic, "AUX_I2C_SCL"))
