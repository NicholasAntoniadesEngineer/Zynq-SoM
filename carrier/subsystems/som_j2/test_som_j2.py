"""LOCAL correctness test for the som_j2 carrier subsystem (SoM connector J2).

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
sheet's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so the
foldering migration carries full 4-artifact parity with the generic
``subsystems/<name>/`` library.

som_j2 is the SoM side of the carrier<->SoM contract: a PURE pass-through DF40
receptacle (FPGA bank 13/33 IO + VCCO) with NO on-sheet passive network. The
LOCAL checks a connector can prove about ITSELF are model completeness, the
DECAP/EP/STRAP design-rule slice (zero findings), the part/spice slices, and the
sheet invariants (rails, HDMI TMDS typing, key function ports, connector ref).

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

from carrier.subsystems.som_j2.som_j2 import circuit

HERE = Path(__file__).resolve().parent
CIR = HERE / "som_j2.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- identity / structure ------------------------------------------------------

def test_is_the_j2_connector(c: Circuit):
    assert c.name == "som_j2"
    assert c.title == "SoM J2: FPGA bank 13/33 IO + VCCO rails"
    assert sorted(c.parts) == ["J2"]
    assert c.parts["J2"].lib_id.endswith("DF40C-100DS-0.4V_51")
    assert c.parts["J2"].value == "DF40C-100DS-0.4V(51)"


def test_connector_has_no_discretes(c: Circuit):
    passive = [r for r, p in c.parts.items()
               if p.lib_id.endswith((":C", ":R", ":L"))]
    assert passive == [], passive


# ---- model completeness (LAW 0) ------------------------------------------------

def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every one of the 100 physical pins is netted; J2 has no no-connects."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins == set()


def test_every_part_pin_is_accounted_for(c: Circuit, lib: Library):
    total = len(lib.pin_numbers(c.parts["J2"].lib_id))
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

def test_vcco_rail_present_and_classed(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    # banks 13+33 VCCO source onto the carrier +3V3 rail (SYS-1 in-fan tap)
    assert cls.get("+3V3") is NetClass.POWER
    assert cls.get("GND") is NetClass.GROUND
    # the abstract +VCCO_* contract names are NOT externals here (they merge)
    assert "+VCCO_13" not in cls and "+VCCO_33" not in cls


def test_vcco_draw_declared(c: Circuit):
    assert "+3V3" in c.loads
    amps = sum(a for a, _ in c.loads["+3V3"])
    assert amps == pytest.approx(0.020)


def test_hdmi_tmds_pairs_typed_100r(c: Circuit):
    pairs = [
        ("HDMI_RX_CLK_P", "HDMI_RX_CLK_N"),
        ("HDMI_RX_D0_P", "HDMI_RX_D0_N"),
        ("HDMI_RX_D1_P", "HDMI_RX_D1_N"),
        ("HDMI_RX_D2_P", "HDMI_RX_D2_N"),
        ("ZYNQ_HDMI_TX_TMDS_CLK_P", "ZYNQ_HDMI_TX_TMDS_CLK_N"),
        ("ZYNQ_HDMI_TX_TMDS_0_P", "ZYNQ_HDMI_TX_TMDS_0_N"),
        ("ZYNQ_HDMI_TX_TMDS_1_P", "ZYNQ_HDMI_TX_TMDS_1_N"),
        ("ZYNQ_HDMI_TX_TMDS_2_P", "ZYNQ_HDMI_TX_TMDS_2_N"),
    ]
    for p, n in pairs:
        assert p in c.nets and n in c.nets, (p, n)
        pt = c.port_type_of(p)
        assert pt.kind == "tmds_pair" and pt.pair_with == n and pt.impedance == 100


def test_key_function_ports_present(c: Circuit):
    """The wave-3 bank-13/33 function renames the consumers (lcd, pmod, hdmi,
    uart_bridge, usb_jtag, microsd) bind to."""
    for port in ("LCD_CTP_SDA", "LCD_CTP_SCL", "LCD_CTP_RST", "LCD_CTP_INT",
                 "PMODX_IO1", "PMODX_IO8",
                 "ZYNQ_PS_UART0_CTS_N", "ZYNQ_PS_UART0_RTS_N",
                 "DBG_UART_RXD", "DBG_UART_TXD",
                 "PL_BTN0", "PL_BTN1", "FMC_PRSNT_N", "SD_CARD_DETECT",
                 "ZYNQ_HDMI_TX_SCL", "ZYNQ_HDMI_TX_SDA", "ZYNQ_HDMI_TX_HPD",
                 "HDMI_RX_CEC", "HDMI_RX_5V_DET"):
        assert port in c.nets, port


# ---- .cir subckt stub ----------------------------------------------------------

def test_cir_subckt_parses_and_declares_rail():
    text = CIR.read_text()
    header = next(l for l in text.splitlines()
                  if l.strip().lower().startswith(".subckt som_j2"))
    pins = header.split()[2:]
    assert pins[-1] == "GND"
    assert "V3V3" in pins
    assert not re.search(r"(?m)^C\d", text)
