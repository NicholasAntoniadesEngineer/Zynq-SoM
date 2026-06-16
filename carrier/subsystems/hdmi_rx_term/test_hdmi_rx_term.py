"""LOCAL electrical-correctness test for the hdmi_rx_term CARRIER subsystem.

Runs the SUBSYSTEM-LOCAL slices of the carrier's own verify gates on JUST this
subsystem's circuit, standalone and offline. Mirrors the shape of
subsystems/usb_pd/test_usb_pd.py, adapted to a carrier-local subsystem (no
abstract-interface / bind contract — hdmi_rx_term binds the HDMI_RX_* ports
hdmi_rx.py exports and the carrier +3V3 rail verbatim).

LOCAL checks:
  * model completeness  — every pin netted or NC (no silent floats).
  * design-rules slice   — DECAP/EP/STRAP clean.
  * the 8x49.9 sink term  — EVERY single-ended TMDS-RX line has exactly one
    49.9 ohm 1% resistor to AVCC (= +3V3 = VCCO_33); 8 lines, 8 resistors.
  * AVCC bypass           — the bank-local 100n + 1u bypass to GND is present.
  * part ratings         — every BOM passive's LCSC resolves; part_rules clean.
  * SPICE passives       — the .cir subckt's R+C network matches the netlist
    one-for-one (parse_si), and the analytic spice slice runs clean.

CROSS-BOARD checks (the link merge with the FPGA bank-33 pins, board ERC, the
full power-tree headroom) stay at board level — not duplicated here.
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

import carrier.subsystems.hdmi_rx_term.hdmi_rx_term as hdmi_rx_term

HERE = Path(__file__).resolve().parent
CIR = HERE / "hdmi_rx_term.cir"

# The 8 single-ended TMDS-RX lines (3 data lanes + clock).
TMDS_LINES = (
    "HDMI_RX_D2_P", "HDMI_RX_D2_N",
    "HDMI_RX_D1_P", "HDMI_RX_D1_N",
    "HDMI_RX_D0_P", "HDMI_RX_D0_N",
    "HDMI_RX_CLK_P", "HDMI_RX_CLK_N",
)


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return hdmi_rx_term.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- model completeness ---------------------------------------------------------

def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins, sorted(str(p) for p in c.nc_pins)


def test_ports_and_rail_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3"] is NetClass.POWER         # AVCC = VCCO_33 = +3V3
    assert cls["GND"] is NetClass.GROUND
    for line in TMDS_LINES:
        assert cls[line] is NetClass.PORT, (line, cls.get(line))


# ---- design-rules slice ---------------------------------------------------------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


# ---- the 8x 49.9 ohm sink termination (the whole point of the sheet) ------------

def test_eight_terminations_each_49R9_to_avcc(c: Circuit):
    """SI-HDMIRX-TERM / DEF-6: every single-ended TMDS-RX line carries exactly
    one 49.9 ohm 1% resistor to AVCC (= +3V3). 8 lines -> 8 resistors, no more,
    no fewer (a missing one = a dead lane; an extra one = double-termination)."""
    avcc_pins = {str(p) for p in c.nets["+3V3"].pins}
    term_value_by_line: dict[str, str] = {}
    for ref, p in c.parts.items():
        if p.lib_id != "Device:R":
            continue
        n1 = c.net_of(PinRef(ref, "1"))
        n2 = c.net_of(PinRef(ref, "2"))
        names = {n.name for n in (n1, n2) if n}
        # one foot on AVCC, the other on a TMDS line
        assert f"{ref}.2" in avcc_pins, f"{ref} not terminated to AVCC(+3V3)"
        line = (names - {"+3V3"}).pop()
        assert line in TMDS_LINES, f"{ref} terminates a non-TMDS net {line!r}"
        term_value_by_line[line] = p.value
    # all 8 lines terminated, each at 49.9 ohm, exactly 8 resistors total
    assert set(term_value_by_line) == set(TMDS_LINES), term_value_by_line
    assert set(term_value_by_line.values()) == {"49.9R"}, term_value_by_line
    assert sum(1 for p in c.parts.values() if p.lib_id == "Device:R") == 8


def test_avcc_local_bypass_present(c: Circuit):
    """AVCC (= +3V3) carries the bank-local 100n HF + 1u reservoir to GND."""
    caps_to_gnd = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        if "+3V3" in names and "GND" in names:
            caps_to_gnd.append(p.value)
    assert sorted(caps_to_gnd) == ["100n", "1u"], caps_to_gnd


# ---- part ratings ---------------------------------------------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if p.lib_id != "Device:R" and not p.lib_id.endswith(":C"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt <-> netlist passives ------------------------------------------

def _cir_passives() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt hdmi_rx_term"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^[RC]\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's R+C network equals the netlist value-for-value (8x 49.9 +
    100n + 1u)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id == "Device:R" or p.lib_id.endswith(":C"))
    cir = sorted(_cir_passives().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- power-tree intent ----------------------------------------------------------

def test_draws_on_avcc(c: Circuit):
    """The 8x sink termination current is sourced from AVCC (+3V3); the
    worst-case ~64 mA budget is declared so the board power-tree gate sees it."""
    assert "+3V3" in c.loads
    total = sum(a for a, _ in c.loads["+3V3"])
    assert total == pytest.approx(0.064), total
