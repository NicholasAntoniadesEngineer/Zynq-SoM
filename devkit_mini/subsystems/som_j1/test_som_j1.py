from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice

from devkit_mini.subsystems.som_j1.som_j1 import circuit

HERE = Path(__file__).resolve().parent
CIR = HERE / "som_j1.cir"

DF40_TOTAL_PINS = 104
SOM_MODULE_DRAW_A = 2.15


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_is_the_j1_connector(c: Circuit):
    """DP is the plug that mates the SoM-side DS receptacle (2026-06-20 no-mate fix)."""
    assert c.name == "som_j1"
    assert c.title == "SoM J1: power / USB / STM32 / JTAG / SDIO / ETH MDI"
    assert sorted(c.parts) == ["J1"]
    assert c.parts["J1"].lib_id.endswith("DF40C-100DP-0.4V_51")
    assert c.parts["J1"].value == "DF40C-100DP-0.4V(51)"


def test_connector_has_no_discretes(c: Circuit):
    """The placement engine's connector fan needs a lone >=40-pin part on the sheet."""
    passive = [r for r, p in c.parts.items()
               if p.lib_id.endswith((":C", ":R", ":L"))]
    assert passive == [], passive


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {
        "J1.24", "J1.25", "J1.26", "J1.27", "J1.56", "J1.58", "J1.60",
        "J1.101", "J1.102", "J1.103", "J1.104"}


def test_every_part_pin_is_accounted_for(c: Circuit, lib: Library):
    total = len(lib.pin_numbers(c.parts["J1"].lib_id))
    netted = {pr for n in c.nets.values() for pr in n.pins}
    assert total == DF40_TOTAL_PINS
    assert len(netted) + len(c.nc_pins) == total


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


def test_rails_present_and_classed(c: Circuit):
    """+VIN is the 20 V PD inlet and must never reach the SoM (it rides +5V_SOM)."""
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls.get("+5V_SOM") is NetClass.POWER
    assert "+VIN" not in cls
    assert cls.get("+3V3_SC") is NetClass.POWER
    assert cls.get("GND") is NetClass.GROUND


def test_module_power_draw_declared(c: Circuit):
    assert "+5V_SOM" in c.loads
    amps = sum(a for a, _ in c.loads["+5V_SOM"])
    assert amps == pytest.approx(SOM_MODULE_DRAW_A)


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
    for port in ("STM32_I2C2_SDA", "STM32_I2C2_SCL",
                 "STM32_NRST", "STM32_BOOT0",
                 "ZYNQ_TCK", "ZYNQ_TDI", "ZYNQ_TDO", "ZYNQ_TMS",
                 "ZYNQ_PS_UART0_RXD", "ZYNQ_PS_UART0_TXD"):
        assert port in c.nets, port
    for spare in ("STM32_GPIO1", "STM32_GPIO2", "STM32_GPIO3", "STM32_GPIO4"):
        assert spare in c.nets, spare


def test_cir_subckt_parses_and_declares_rails():
    text = CIR.read_text()
    header = next(l for l in text.splitlines()
                  if l.strip().lower().startswith(".subckt som_j1"))
    pins = header.split()[2:]
    assert pins[-1] == "GND"
    assert "V5V_SOM" in pins and "V3V3_SC" in pins
    assert not re.search(r"(?m)^C\d", text)
