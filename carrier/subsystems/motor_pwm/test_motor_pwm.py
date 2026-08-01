from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

from carrier.subsystems.motor_pwm import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "motor_pwm.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return build()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_is_motor_pwm(c: Circuit):
    assert c.name == "motor_pwm"
    assert c.parts["U1"].lib_id.endswith("SN74HCT245PWR")
    assert c.parts["U3"].lib_id.endswith("SY6280AAC")
    assert "J1" in c.parts


def test_model_complete_no_unexpected_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins == [] or {str(p) for p in c.nc_pins} == set()


def test_eight_pwm_inputs_plus_oe_published(c: Circuit):
    for i in range(8):
        assert f"ESC_PWM_IN{i}" in c.nets, f"missing ESC_PWM_IN{i}"
    assert "ESC_BUF_OE_N" in c.nets


def test_buffer_failsafe_and_direction(c: Circuit):
    assert {"U1.1", "U1.20"} <= {str(p) for p in c.nets["+5V"].pins}
    assert any(str(p) == "U1.19" for p in c.nets["ESC_BUF_OE_N"].pins)


def test_servo_rail_gated_by_sy6280(c: Circuit):
    assert any(str(p) == "U3.1" for p in c.nets["+5V_MOTOR_IO"].pins)
    assert any(str(p) == "U3.5" for p in c.nets["+5V"].pins)
    rail = {str(p) for p in c.nets["+5V_MOTOR_IO"].pins}
    assert "J1.9" in rail and "J1.16" in rail


def test_each_buffered_output_lands_on_the_header_sig_row(c: Circuit):
    """Element j of a 4D03 array spans facing pads j+1 and 8-j, not adjacent pads."""
    for i in range(8):
        rn = "RN1" if i < 4 else "RN2"
        j = i % 4
        assert c.parts[rn].lib_id.endswith("4D03WGJ0330T5E")
        assert f"ESC_SIG{i}" in c.nets
        assert any(str(p) == f"{rn}.{j + 1}" for p in c.nets[f"ESC_SIG{i}"].pins)
        assert f"ESC_OUT{i}" in c.nets
        out_pins = {str(p) for p in c.nets[f"ESC_OUT{i}"].pins}
        assert f"{rn}.{8 - j}" in out_pins
        assert f"J1.{1 + i}" in out_pins


def test_part_and_spice_slices_clean(c: Circuit, lib, tmp_path):
    assert part_rules.run([_sheet(c)], tmp_path).ok
    assert spice.extract_checks([_sheet(c)]).ok
    assert "C6779" in RATINGS_BY_LCSC, "HCT245 missing from ratings catalog"


def test_cir_caps_match_netlist(c: Circuit):
    text = CIR.read_text()
    cir_caps = sorted(parse_si(m) for m in
                      re.findall(r"(?m)^C\d+\s+\S+\s+\S+\s+(\S+)", text))
    net_caps = sorted(parse_si(p.value) for r, p in c.parts.items()
                      if p.lib_id.endswith(":C"))
    assert cir_caps == net_caps, (cir_caps, net_caps)
