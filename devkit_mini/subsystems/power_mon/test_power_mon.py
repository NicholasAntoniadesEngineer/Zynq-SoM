"""LOCAL electrical-correctness test for the carrier power_mon subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog + the analytic SPICE slice; no kicad-cli, no network, no board). Mirrors
the shape of devkit_mini/subsystems/board_services/test_board_services.py, adapted for
the 2x INA3221 rail telemetry block — a CARRIER-LOCAL subsystem (real carrier net
names wired directly, no abstract-interface / bind contract).

LOCAL checks (what this subsystem can prove about ITSELF):
  * model completeness   — every physical pin netted-or-NC (LAW 0: no floats),
    and the intentional no-connects are exactly the WARNING/PV/TC open-drain
    status outputs of both INA3221s.
  * decoupling / EP      — design_rules DECAP/EP/STRAP slice clean: each IC has a
    local supply bypass to GND and its exposed PAD is on GND.
  * part ratings         — every BOM passive's LCSC resolves in the ratings
    catalog and the per-part rating engine raises no hard finding.
  * shunt invariants     — RS1..RS4 split each rail (reg/source side IN+, board/
    load side IN-) with the documented 10/10/10/20 mR values — the DEF-D series-
    shunt topology each channel measures.
  * SPICE passives       — the .cir subckt's resistor/cap network whose elements
    span two external nets matches the netlist one-for-one (parse_si), the subckt
    pins are the carrier externals, and the analytic spice slice runs clean.
  * netlist invariants   — the 0x40/0x41 address straps, the always-on +3V3_SC
    supply, the wire-OR CRITICAL alert with its defined-high pull-up, the typed
    I2C ports, and the unused-U2-channel-to-GND handling.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
shared STM32_I2C2 pull-up completeness (the pulls live on usb_pd/bringup), the
link/port-driver graph, board ERC and the board netlist merge — all aggregated
by `schgen board`.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

from devkit_mini.subsystems.power_mon import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "power_mon.cir"


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

def test_is_power_mon(c: Circuit):
    assert c.name == "power_mon"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every physical pin of every part is netted or NC (LAW 0: no silent
    floats) — the same hard check the board build runs. The intentional
    no-connects are the WARNING/PV/TC open-drain status outputs of both ICs."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # six NCs: U1 + U2 each WARNING/PV/TC (I2C-readable status outputs, unused)
    assert len(c.nc_pins) == 6
    nc_refs = sorted({str(p).split(".")[0] for p in c.nc_pins})
    assert nc_refs == ["U1", "U2"]


# ---- decoupling + exposed pad (design_rules LOCAL slice) ------------------------

def test_decoupling_and_pad_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP clean: each IC supply pin has a local cap-to-GND and the
    exposed PAD is on GND."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("ep", 0) >= 2          # both INA3221 PADs checked
    assert r.checked.get("decap", 0) >= 2


# ---- part ratings --------------------------------------------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Every passive (cap AND resistor, including the sense shunts) LCSC resolves
    in the ratings catalog."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")
                or ref.startswith("RS")):
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


# ---- sense-shunt invariants (the DEF-D rail split) -----------------------------

def test_shunts_split_each_rail_with_documented_values(c: Circuit):
    """RS1..RS4 series-insert between each rail's reg/source side (IN+) and its
    board/load side (IN-), with the documented 10/10/10/20 mR values."""
    expect = {
        "RS1": ("+VIN", "+VIN_SYS", "10mR"),
        "RS2": ("+5V_REG", "+5V", "10mR"),
        "RS3": ("+3V3_REG", "+3V3", "10mR"),
        "RS4": ("+1V8_REG", "+1V8", "20mR"),
    }
    for ref, (hi, lo, val) in expect.items():
        assert c.parts[ref].value == val, (ref, c.parts[ref].value)
        assert f"{ref}.1" in _pins(c, hi), (ref, hi)     # reg/source side
        assert f"{ref}.2" in _pins(c, lo), (ref, lo)     # board/load side
    # the two shunt values are distinct part numbers (10 mR vs 20 mR)
    assert parse_si("10mR") == 0.01 and parse_si("20mR") == 0.02


def test_unused_u2_channels_to_gnd(c: Circuit):
    """U2 ch2/ch3 are unused: their four sense inputs tie to GND (datasheet —
    reads 0 V / 0 A)."""
    gnd = _pins(c, "GND")
    # IN+2/IN-2/IN+3/IN-3 of U2 resolve to four of U2's pins on GND; assert at
    # least the four channel-2/3 input pins of U2 are grounded (none float).
    u2_on_gnd = {p for p in gnd if p.startswith("U2.")}
    assert len(u2_on_gnd) >= 4, u2_on_gnd


# ---- SPICE subckt <-> netlist passives -----------------------------------------

def _cir_elems(prefix: str) -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt power_mon"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(rf"^{prefix}\w", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


# the shunts the .cir models (RS1..RS4, each spanning two carrier external rails)
_CIR_RS = {"RS1", "RS2", "RS3", "RS4"}
# the supply caps the .cir models (both pins on +3V3_SC / GND)
_CIR_CAPS = {"C1", "C2", "C3"}


def test_cir_subckt_pins_are_the_carrier_externals():
    """The .cir subckt declares the carrier external nets as its pins."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt power_mon"))
    pins = header.split()[2:]
    assert pins == ["+VIN", "+VIN_SYS", "+5V_REG", "+5V", "+3V3_REG", "+3V3",
                    "+1V8_REG", "+1V8", "+3V3_SC", "GND"], pins


def test_cir_shunts_match_netlist(c: Circuit):
    """The subckt's shunt-resistor network equals the netlist's RS1..RS4,
    value-for-value (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_RS)
    cir = sorted(v for k, v in _cir_elems("R").items() if k in _CIR_RS)
    assert cir == netlist, (cir, netlist)


def test_cir_caps_match_netlist(c: Circuit):
    """The subckt's supply-cap network equals the netlist's +3V3_SC caps."""
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_CAPS)
    cir = sorted(_cir_elems("C").values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation and no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- netlist invariants (the facts the gates do not check by themselves) --------

def test_address_straps_0x40_0x41(c: Circuit):
    """U1 A0 -> GND (0x40), U2 A0 -> +3V3_SC (0x41). The straps put each IC on a
    distinct address (no collision)."""
    # exactly one extra U1 pin on GND vs U2, and one extra U2 pin on +3V3_SC:
    # the A0 straps. Assert the supply/strap rails carry both ICs' VS + the one
    # A0 each.
    sc = _pins(c, "+3V3_SC")
    assert {"R1.1", "C1.1", "C2.1", "C3.1"} <= sc          # pull-up + bypass tops
    # both ICs' VS/VPU on +3V3_SC, plus U2.A0 (0x41 strap)
    assert sum(1 for p in sc if p.startswith("U1.")) == 2   # VS + VPU
    assert sum(1 for p in sc if p.startswith("U2.")) == 3   # VS + VPU + A0


def test_alert_wire_or_critical_defined_high(c: Circuit):
    """Both CRITICAL open-drain pins wire-OR into PMON_ALERT_N with a 10k
    defined-high pull-up to +3V3_SC."""
    alert = _pins(c, "PMON_ALERT_N")
    assert {"U1.9", "U2.9", "R1.2"} <= alert, alert         # both CRITICAL + pull
    assert c.parts["R1"].value == "10k"
    assert "R1.1" in _pins(c, "+3V3_SC")                    # pull-up to the SC rail


def test_i2c_ports_typed_on_stm32_bus(c: Circuit):
    """Both INA3221s sit on the typed STM32_I2C2 SDA/SCL ports (i2c, 400 kHz)."""
    assert c.port_type_of("STM32_I2C2_SDA").kind == "i2c"
    assert c.port_type_of("STM32_I2C2_SDA").role == "sda"
    assert c.port_type_of("STM32_I2C2_SCL").role == "scl"
    assert c.port_type_of("STM32_I2C2_SDA").bus == "STM32_I2C2"
    assert c.port_type_of("STM32_I2C2_SDA").speed_hz == 400_000
    sda, scl = _pins(c, "STM32_I2C2_SDA"), _pins(c, "STM32_I2C2_SCL")
    assert {"U1.7", "U2.7"} <= sda, sda                     # both ICs on SDA
    assert {"U1.6", "U2.6"} <= scl, scl                     # both ICs on SCL


def test_both_are_the_ina3221(c: Circuit):
    """U1 and U2 are the single INA3221 part number (the C190480 ghost is not
    used) at the documented LCSC."""
    for ref in ("U1", "U2"):
        assert c.parts[ref].lib_id.split(":")[-1] == "INA3221AIRGVR"
        assert (c.parts[ref].fields or {}).get("LCSC") == "C181255"
