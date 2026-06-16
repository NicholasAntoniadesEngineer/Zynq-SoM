"""LOCAL correctness test for the som_j1 carrier subsystem (SoM connector J1).

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
sheet's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so the
foldering migration carries full 4-artifact parity with the generic
``subsystems/<name>/`` library.

som_j1 is the SoM side of the carrier<->SoM contract: a PURE pass-through DF40
receptacle with NO on-sheet passive network. So the LOCAL checks a connector can
prove about ITSELF are:
  * model completeness  — every physical pin of the 100-pin part is netted-or-NC
    (the same hard check the board build runs; LAW 0: no silent floats).
  * design-rule slice   — DECAP/EP/STRAP report ZERO findings (a connector has no
    IC supply pin, no exposed pad, no config strap to anchor).
  * part-rules + spice  — the per-part rating and analytic-spice slices run clean.
  * sheet invariants    — the expected rails, the isolated-rail no-connects, the
    diff-pair/SD-bus typing, and the connector ref are exactly as the contract
    declares (so a regen drift is caught locally).

CROSS-BOARD checks (link/port-driver graph, full power-tree headroom, board ERC
and the board netlist merge) stay at board level — aggregated by ``schgen board``.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice

from carrier.subsystems.som_j1.som_j1 import circuit

HERE = Path(__file__).resolve().parent
CIR = HERE / "som_j1.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- identity / structure ------------------------------------------------------

def test_is_the_j1_connector(c: Circuit):
    assert c.name == "som_j1"
    assert c.title == "SoM J1: power / USB / STM32 / JTAG / SDIO / ETH MDI"
    # exactly one part: the DF40 mezzanine receptacle at ref J1
    assert sorted(c.parts) == ["J1"]
    assert c.parts["J1"].lib_id.endswith("DF40C-100DS-0.4V_51")
    assert c.parts["J1"].value == "DF40C-100DS-0.4V(51)"


def test_connector_has_no_discretes(c: Circuit):
    """A pure pass-through receptacle: no caps/resistors/inductors on the sheet
    (the placement engine's connector fan requires a lone >=40-pin part)."""
    passive = [r for r, p in c.parts.items()
               if p.lib_id.endswith((":C", ":R", ":L"))]
    assert passive == [], passive


# ---- model completeness (LAW 0) ------------------------------------------------

def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every one of the 100 physical pins is netted or an explicit NC."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the seven round-5 isolated-rail pins are the only no-connects
    assert {str(p) for p in c.nc_pins} == {
        "J1.24", "J1.25", "J1.26", "J1.27", "J1.56", "J1.58", "J1.60"}


def test_every_part_pin_is_accounted_for(c: Circuit, lib: Library):
    """100-pin part = (netted pins) + (NC pins), with no leftovers."""
    total = len(lib.pin_numbers(c.parts["J1"].lib_id))
    netted = {pr for n in c.nets.values() for pr in n.pins}
    assert total == 100
    assert len(netted) + len(c.nc_pins) == total


# ---- design-rule / part / spice slices (a connector finds nothing) -------------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: a connector has no IC supply pin, exposed pad or config
    strap, so all three report ZERO findings."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # nothing to decouple on a connector sheet
    assert r.checked.get("decap", 0) == 0


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- sheet invariants (catch a regen drift) ------------------------------------

def test_rails_present_and_classed(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    # P0 rebind: the SoM module input rides the carrier +5V_SOM buck, never +VIN
    assert cls.get("+5V_SOM") is NetClass.POWER
    assert "+VIN" not in cls          # the 20 V PD rail never reaches the SoM
    assert cls.get("+3V3_SC") is NetClass.POWER
    assert cls.get("GND") is NetClass.GROUND


def test_module_power_draw_declared(c: Circuit):
    """J1 declares the SoM module draw on the +5V_SOM rail (~10 W class)."""
    assert "+5V_SOM" in c.loads
    amps = sum(a for a, _ in c.loads["+5V_SOM"])
    assert amps == pytest.approx(2.0)


def test_ethernet_mdi_pairs_typed_100r(c: Circuit):
    for i in range(4):
        p, n = f"ETH_PHY_MDI{i}_P", f"ETH_PHY_MDI{i}_N"
        assert p in c.nets and n in c.nets
        pt = c.port_type_of(p)
        assert pt.kind == "diff_pair" and pt.pair_with == n and pt.impedance == 100


def test_usb_pairs_typed_90r(c: Circuit):
    for p, n in (("STM32_USB_D_P", "STM32_USB_D_N"), ("USB_D+", "USB_D-")):
        pt = c.port_type_of(p)
        assert pt.kind == "usb_hs_pair" and pt.pair_with == n and pt.impedance == 90


def test_sdio_bus_typed_1v8(c: Circuit):
    for s in ("SDIO_CLK", "SDIO_CMD", "SDIO_D0", "SDIO_D1", "SDIO_D2", "SDIO_D3"):
        pt = c.port_type_of(s)
        assert pt.kind == "sd_bus" and pt.bus == "SDIO" and pt.level_v == 1.8


def test_key_function_ports_present(c: Circuit):
    """The wave-3 function renames + JTAG/PS ports the consumers bind to."""
    for port in ("STM32_RAIL_EN_5V0", "STM32_RAIL_EN_3V3", "STM32_RAIL_EN_1V8",
                 "SC_INT_N", "STM32_I2C2_SDA", "STM32_I2C2_SCL",
                 "STM32_NRST", "STM32_BOOT0",
                 "ZYNQ_TCK", "ZYNQ_TDI", "ZYNQ_TDO", "ZYNQ_TMS",
                 "ZYNQ_PS_UART0_RXD", "ZYNQ_PS_UART0_TXD"):
        assert port in c.nets, port


# ---- .cir subckt stub ----------------------------------------------------------

def test_cir_subckt_parses_and_declares_rails():
    """The .cir declares a som_j1 subckt whose pins are the sheet's rails (GND
    last) and adds no passive caps (a pure connector has no on-sheet network)."""
    text = CIR.read_text()
    header = next(l for l in text.splitlines()
                  if l.strip().lower().startswith(".subckt som_j1"))
    pins = header.split()[2:]
    assert pins[-1] == "GND"
    assert "V5V_SOM" in pins and "V3V3_SC" in pins
    # no capacitor lines (connector carries no on-sheet passive network)
    assert not re.search(r"(?m)^C\d", text)
