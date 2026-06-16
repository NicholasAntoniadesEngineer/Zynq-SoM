"""LOCAL electrical-correctness test for the debug_boot CARRIER subsystem.

Runs the SUBSYSTEM-LOCAL slices of the carrier's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). Mirrors the shape of
subsystems/usb_pd/test_usb_pd.py, adapted to a carrier-local subsystem (no
abstract-interface / bind contract — debug_boot binds verbatim carrier nets).

LOCAL checks:
  * model completeness  — every pin netted or NC, with EXACTLY the intentional
    no-connects (JTAG pin 12/14, SWD SWO/KEY/TDI).
  * design-rules slice   — DECAP/EP/STRAP/RESET clean (no floating config strap;
    the reset net is recognised — its RC lives on the SoM).
  * strap census         — the boot-mode straps and JTAG insurance pulls are
    present at the right values on the right rails (BOOT0 100R, BOOTSEL/spare
    10k -> +3V3_SC, JTAG TMS/TDI 4k7 -> +3V3).
  * part ratings         — every BOM passive's LCSC resolves; part_rules clean.
  * SPICE passives       — the .cir subckt's R network matches the netlist
    one-for-one (parse_si), and the analytic spice slice runs clean.

CROSS-BOARD checks (the link graph, board ERC, the firmware BOOTSEL contract)
stay at board level — not duplicated here.
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

import carrier.subsystems.debug_boot.debug_boot as debug_boot

HERE = Path(__file__).resolve().parent
CIR = HERE / "debug_boot.cir"

# The intentional no-connects (debug_boot.py): JTAG pin 12 + SRST (14) not on
# the SoM J1; SWD SWO (6), KEY (7), TDI (8) unrouted.
EXPECTED_NC = {"J1.12", "J1.14", "J2.6", "J2.7", "J2.8"}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return debug_boot.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- model completeness ---------------------------------------------------------

def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every physical pin netted or NC, with exactly the intentional NCs."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == EXPECTED_NC


def test_rail_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3"] is NetClass.POWER
    assert cls["+3V3_SC"] is NetClass.POWER       # always-on SC rail
    assert cls["GND"] is NetClass.GROUND


# ---- design-rules slice ---------------------------------------------------------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    """DECAP/EP/STRAP/RESET clean: no floating config strap; the reset net is
    recognised (its RC debounce lives on the SoM, so no local RC is required)."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert not r.reset, r.reset
    # the reset rule is actually exercised (STM32_NRST recognised, not a no-op)
    assert r.checked.get("reset", 0) >= 1


# ---- strap census (the electrical contract) -------------------------------------

def _pin_net(c: Circuit, pin: str) -> str | None:
    ref, num = pin.split(".")
    n = c.net_of(PinRef(ref, num))
    return n.name if n else None


def test_jtag_insurance_pullups(c: Circuit):
    """TMS and TDI each carry a 4k7 insurance pull-up to +3V3 (= VCCO_0)."""
    pulls = [(ref, p.value) for ref, p in c.parts.items()
             if p.lib_id == "Device:R" and p.value == "4k7"]
    assert len(pulls) == 2, pulls
    for rref, _ in pulls:
        assert _pin_net(c, f"{rref}.1") == "+3V3"      # pull-up rail
    # both pull tops are on +3V3, and the bottoms join TMS / TDI
    bottoms = {_pin_net(c, f"{rref}.2") for rref, _ in pulls}
    assert bottoms == {"ZYNQ_TMS", "ZYNQ_TDI"}, bottoms


def test_boot0_series_strap_100R_to_sc_rail(c: Circuit):
    """BOOT0 drives high through a 100R series against the SoM 1k5 pull-down,
    fed from the always-on +3V3_SC (closed = USB DFU)."""
    series = [ref for ref, p in c.parts.items()
              if p.lib_id == "Device:R" and p.value == "100R"]
    assert len(series) == 1, series
    (r3,) = series
    nets = {_pin_net(c, f"{r3}.1"), _pin_net(c, f"{r3}.2")}
    assert "+3V3_SC" in nets and "BOOT0_SET" in nets, nets
    # the BOOT0 port reaches the DIP node that the 100R feeds
    assert _pin_net(c, "SW1.1") == "STM32_BOOT0"


def test_bootsel_and_spare_10k_defined_high_to_sc_rail(c: Circuit):
    """BOOTSEL0/1 + the spare each carry a 10k defined-high pull-up to the
    always-on +3V3_SC (level defined before SC firmware enables internal pulls)."""
    pulls = [ref for ref, p in c.parts.items()
             if p.lib_id == "Device:R" and p.value == "10k"]
    assert len(pulls) == 3, pulls
    for rref in pulls:
        assert _pin_net(c, f"{rref}.1") == "+3V3_SC", rref


def test_reset_button_grounds_its_far_contacts(c: Circuit):
    """The reset tact ties STM32_NRST through its signal contacts and grounds
    the opposite pair (RC debounce lives on the SoM)."""
    assert _pin_net(c, "SW2.1") == "STM32_NRST"
    assert _pin_net(c, "SW2.2") == "STM32_NRST"
    assert _pin_net(c, "SW2.3") == "GND"
    assert _pin_net(c, "SW2.4") == "GND"


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

def _cir_resistors() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt debug_boot"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^R\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's R network equals the netlist's resistors, value-for-value
    (debug_boot has no caps — header/switch subsystem, no active parts)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id == "Device:R")
    cir = sorted(_cir_resistors().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- power-tree intent ----------------------------------------------------------

def test_draws_on_both_rails(c: Circuit):
    """Draws declared on the always-on SC rail (BOOT0 strap + BOOTSEL pulls)
    and the +3V3 rail (JTAG insurance pulls)."""
    assert "+3V3_SC" in c.loads
    assert "+3V3" in c.loads
