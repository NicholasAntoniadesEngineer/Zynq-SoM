"""LOCAL correctness test for the som_j3 carrier subsystem (SoM connector J3).

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
sheet's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so the
foldering migration carries full 4-artifact parity with the generic
``subsystems/<name>/`` library.

som_j3 is the SoM side of the carrier<->SoM contract: a PURE pass-through DF40
receptacle (FPGA bank 33/34/35 IO + VCCO) with NO on-sheet passive network. The
LOCAL checks a connector can prove about ITSELF are model completeness, the
DECAP/EP/STRAP design-rule slice (zero findings), the part/spice slices, and the
sheet invariants (rails, camera/FMC diff-pair typing, key function ports,
connector ref).

CROSS-BOARD checks (link/port-driver graph, full power-tree headroom, board ERC
and the board netlist merge) stay at board level — aggregated by ``schgen board``.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice

from carrier.subsystems.som_j3.som_j3 import circuit

HERE = Path(__file__).resolve().parent
CIR = HERE / "som_j3.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- identity / structure ------------------------------------------------------

def test_is_the_j3_connector(c: Circuit):
    assert c.name == "som_j3"
    assert c.title == "SoM J3: FPGA bank 33/34/35 IO + VCCO rails"
    assert sorted(c.parts) == ["J3"]
    assert c.parts["J3"].lib_id.endswith("DF40C-100DS-0.4V_51")
    assert c.parts["J3"].value == "DF40C-100DS-0.4V(51)"


def test_connector_has_no_discretes(c: Circuit):
    passive = [r for r, p in c.parts.items()
               if p.lib_id.endswith((":C", ":R", ":L"))]
    assert passive == [], passive


# ---- model completeness (LAW 0) ------------------------------------------------

def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every one of the 100 physical pins is netted; J3 has no no-connects."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins == set()


def test_every_part_pin_is_accounted_for(c: Circuit, lib: Library):
    total = len(lib.pin_numbers(c.parts["J3"].lib_id))
    netted = {pr for n in c.nets.values() for pr in n.pins}
    assert total == 100
    assert len(netted) + len(c.nc_pins) == total


# ---- design-rule / part / spice slices (a connector finds nothing) -------------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) == 0


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- sheet invariants (catch a regen drift) ------------------------------------

def test_vcco_rails_present_and_classed(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    # bank 34 VCCO -> +3V3, bank 35 VCCO -> +2V5_VADJ (SYS-1 in-fan taps)
    assert cls.get("+3V3") is NetClass.POWER
    assert cls.get("+2V5_VADJ") is NetClass.POWER
    assert cls.get("GND") is NetClass.GROUND
    assert "+VCCO_34" not in cls and "+VCCO_35" not in cls


def test_vcco_draws_declared(c: Circuit):
    assert sum(a for a, _ in c.loads["+3V3"]) == pytest.approx(0.010)
    assert sum(a for a, _ in c.loads["+2V5_VADJ"]) == pytest.approx(0.050)


def test_camera_pairs_typed_100r(c: Circuit):
    for p, n in (("CAM_CLK_P", "CAM_CLK_N"),
                 ("CAM_D0_P", "CAM_D0_N"),
                 ("CAM_D1_P", "CAM_D1_N")):
        assert p in c.nets and n in c.nets
        pt = c.port_type_of(p)
        assert pt.kind == "diff_pair" and pt.pair_with == n and pt.impedance == 100


def test_fmc_pairs_typed_100r(c: Circuit):
    fmc_pairs = [("FMC_CLK0_M2C_P", "FMC_CLK0_M2C_N"),
                 ("FMC_CLK1_M2C_P", "FMC_CLK1_M2C_N"),
                 ("FMC_LA00_CC_P", "FMC_LA00_CC_N"),
                 ("FMC_LA01_CC_P", "FMC_LA01_CC_N")]
    fmc_pairs += [(f"FMC_LA0{i}_P", f"FMC_LA0{i}_N") for i in range(2, 8)]
    for p, n in fmc_pairs:
        assert p in c.nets and n in c.nets, (p, n)
        pt = c.port_type_of(p)
        assert pt.kind == "diff_pair" and pt.pair_with == n and pt.impedance == 100


def test_key_function_ports_present(c: Circuit):
    """The wave-3 bank-33/34/35 function renames the consumers (lcd, camera, fmc,
    board_services watchdog, bringup_rails PUDC strap) bind to."""
    for port in ("LCD_R0", "LCD_R7", "LCD_G0", "LCD_G7", "LCD_B0", "LCD_B7",
                 "LCD_PCLK", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE", "LCD_DISP",
                 "LCD_BL_PWM",
                 "CAM_SCL", "CAM_SDA", "CAM_EN", "CAM_LED",
                 "WATCHDOG_RST_N", "WATCHDOG_KICK", "PUDC_34"):
        assert port in c.nets, port


# ---- .cir subckt stub ----------------------------------------------------------

def test_cir_subckt_parses_and_declares_rails():
    text = CIR.read_text()
    header = next(l for l in text.splitlines()
                  if l.strip().lower().startswith(".subckt som_j3"))
    pins = header.split()[2:]
    assert pins[-1] == "GND"
    assert "V3V3" in pins and "V2V5_VADJ" in pins
    assert not re.search(r"(?m)^C\d", text)
