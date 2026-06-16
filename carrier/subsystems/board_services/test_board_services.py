"""LOCAL electrical-correctness test for the carrier board_services subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog + the analytic SPICE slice; no kicad-cli, no network, no board). Mirrors
the shape of subsystems/usb_pd/test_usb_pd.py, adapted for a CARRIER-LOCAL
subsystem (real carrier net names wired directly — no abstract-interface / bind
contract, so the bind-API tests do not apply).

LOCAL checks (what this subsystem can prove about ITSELF):
  * model completeness   — every physical pin netted-or-NC (LAW 0: no floats),
    and the intentional no-connects are exactly U2.CLKOUT + U3.MR#.
  * decoupling           — design_rules DECAP/EP/STRAP slice clean: every IC
    supply pin has a local cap-to-GND; no config strap floats; the V_RTC_BAT
    waiver leaves U2.VDD under the rule.
  * part ratings         — every BOM passive's LCSC resolves in the ratings
    catalog and the per-part rating engine raises no hard finding.
  * SPICE passives       — the .cir subckt's capacitor network matches the
    netlist caps one-for-one (parse_si), the subckt pins are the carrier
    externals, and the analytic spice slice runs clean.
  * netlist invariants   — the 0x51 EEPROM strap, the RTC unused-pin handling +
    coin-cell node, the watchdog power-up safety (C2) and bank-33 domain fix.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
shared AUX_I2C pull-up completeness (the pulls live on board_aux), the
link/port-driver graph, the full power-tree headroom, board ERC and the board
netlist merge — all aggregated by `schgen board`.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

from carrier.subsystems.board_services import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "board_services.cir"


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

def test_is_board_services(c: Circuit):
    assert c.name == "board_services"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every physical pin of every part is netted or NC (LAW 0: no silent
    floats) — the same hard check the board build runs."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the two intentional no-connects: RV-3028 CLKOUT (U2.1) and TPS3823 MR#
    # (U3.3, internal pull-up holds it de-asserted).
    assert {str(p) for p in c.nc_pins} == {"U2.1", "U3.3"}


# ---- decoupling completeness (design_rules LOCAL slice) ------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP clean: every IC supply pin has a local cap-to-GND, no
    config strap floats. (The AUX_I2C pull-up completeness is a board-level rule
    — the pulls live on board_aux — so it is NOT asserted here.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the supply decap rule is actually exercised on the three service ICs
    assert r.checked.get("decap", 0) >= 3


def test_each_ic_supply_has_a_local_100n(c: Circuit):
    """Each service IC has its own 100n bypass from +3V3_AUX to GND."""
    n = 0
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        names = {x.name for x in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if x}
        if names == {"+3V3_AUX", "GND"}:
            assert p.value == "100n", (ref, p.value)
            n += 1
    assert n == 3, n


def test_rtc_vbackup_decap_waived_not_vdd(c: Circuit, lib: Library):
    """The waiver is keyed on V_RTC_BAT (the coin-cell net), so U2.VDD stays
    under the decap rule — the slice is still clean with U2 bypassed at line."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert "U2.7" in _pins(c, "+3V3_AUX")            # RTC VDD really is bypassed


# ---- part ratings --------------------------------------------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Every passive (cap AND resistor) LCSC resolves in the ratings catalog."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt <-> netlist passives -----------------------------------------

def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt board_services"):
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
    """The .cir subckt declares the carrier external nets as its pins."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt board_services"))
    pins = header.split()[2:]
    assert pins == ["VDD_AUX", "GND", "AUX_I2C_SCL", "AUX_I2C_SDA",
                    "WATCHDOG_KICK", "WATCHDOG_RST_N"], pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's capacitor network equals the netlist's caps, value-for-value
    (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation and no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- netlist invariants (the facts the gates do not check by themselves) -------

def test_i2c_ports_typed_on_aux_bus(c: Circuit):
    """EEPROM + RTC share AUX_I2C (the isolated segment), typed scl/sda 400 kHz."""
    assert c.port_type_of("AUX_I2C_SCL").kind == "i2c"
    assert c.port_type_of("AUX_I2C_SCL").role == "scl"
    assert c.port_type_of("AUX_I2C_SDA").role == "sda"
    assert c.port_type_of("AUX_I2C_SCL").bus == "AUX_I2C" == \
        c.port_type_of("AUX_I2C_SDA").bus
    assert c.port_type_of("AUX_I2C_SCL").speed_hz == 400_000
    # both the EEPROM (U1) and the RTC (U2) sit on each I2C line
    scl, sda = _pins(c, "AUX_I2C_SCL"), _pins(c, "AUX_I2C_SDA")
    assert {"U1.1", "U2.3"} <= scl, scl       # EEPROM SCL + RTC SCL
    assert {"U1.3", "U2.4"} <= sda, sda       # EEPROM SDA + RTC SDA


def test_eeprom_address_strap_0x51(c: Circuit):
    """EEPROM 24AA025E48 at 0x51: A0 (pin 5) = 1 (+3V3_AUX), A1 (pin 4) = 0."""
    assert "U1.5" in _pins(c, "+3V3_AUX")
    assert "U1.4" in _pins(c, "GND")


def test_eeprom_rtc_watchdog_parts_present(c: Circuit):
    """The three named services are the real datasheet parts."""
    assert c.parts["U1"].lib_id.split(":")[-1] == "24AA025E48T-I_OT"
    assert c.parts["U2"].lib_id.split(":")[-1] == "RV-3028-C7-32.768kHz-1ppm-TA-QC"
    assert c.parts["U3"].lib_id.split(":")[-1] == "TPS3823-33DBVR"
    assert c.parts["BT1"].lib_id.split(":")[-1] == "KH-CR1220-2"


def test_rtc_unused_pins_and_coin_cell(c: Circuit):
    """RV-3028: EVI tied low, CLKOUT no-connect, VBACKUP to the coin cell."""
    assert "U2.8" in _pins(c, "GND")                 # EVI (pin 8) -> GND
    assert not any("U2.1" in _pins(c, n) for n in c.nets)   # CLKOUT NC
    bat = _pins(c, "V_RTC_BAT")
    assert "U2.6" in bat and "BT1.1" in bat          # VBACKUP -> coin cell +


def test_c2_watchdog_safe_at_power_up(c: Circuit):
    """C2: watchdog cannot reset the system at power-up — VDD on the gated rail
    (default OFF), MR# a no-connect, RESET# a PL event line (not a rail/POR)."""
    assert "U3.5" in _pins(c, "+3V3_AUX")            # VDD on gated rail
    assert not any("U3.3" in _pins(c, n) for n in c.nets)   # MR# NC
    assert "U3.1" in _pins(c, "WATCHDOG_RST_N")      # RESET# -> PL event net


def test_watchdog_domain_fix_off_bank35(c: Circuit):
    """Domain fix: both watchdog nets are off the 2.5 V bank-35 pins, onto the
    bank-33 +3V3 LVCMOS33 function nets."""
    assert "WATCHDOG_KICK" in c.nets and "WATCHDOG_RST_N" in c.nets
    assert "IO_L16_P_35" not in c.nets
    assert "IO_L16_N_35" not in c.nets
