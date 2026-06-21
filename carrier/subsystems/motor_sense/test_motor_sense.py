"""LOCAL correctness test for the carrier motor_sense subsystem (motor-rail
telemetry). Runs the SUBSYSTEM-LOCAL gate slices on JUST this sheet (model +
ratings + spice; no kicad-cli, no network, no board). Cross-board checks stay at
board level. Also asserts the PL pin ledger (the FUNCTION_MAP ESC renames) does
not double-claim a contract pin (LAW 0).
"""

from __future__ import annotations

import json
import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library
from schgen.verify import part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

from carrier.subsystems.motor_sense import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "motor_sense.cir"
REPO = HERE.parents[2]


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return build()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_is_motor_sense(c: Circuit):
    assert c.name == "motor_sense"
    assert c.parts["U2"].lib_id.endswith("INA3221AIRGVR")
    assert {"J2", "J3", "RS1", "D1"} <= set(c.parts)


def test_model_complete_only_unused_ina_alerts_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"U2.8", "U2.10", "U2.13"}


def test_shunt_in_line_and_ina_reads_both_sides(c: Circuit):
    # pins stringify REF.NUMBER; XT60 +=2; INA3221 IN+1=12, IN-1=11
    # RS1 sits IN-LINE J2(in) -> RS1 -> J3(out); INA reads current across it
    assert any(str(p) == "RS1.1" for p in c.nets["ESC_VRAIL_IN"].pins)
    assert any(str(p) == "RS1.2" for p in c.nets["ESC_VRAIL"].pins)
    assert any(str(p) == "J2.2" for p in c.nets["ESC_VRAIL_IN"].pins)
    assert any(str(p) == "J3.2" for p in c.nets["ESC_VRAIL"].pins)
    assert any(str(p) == "U2.12" for p in c.nets["ESC_VRAIL_IN"].pins)
    assert any(str(p) == "U2.11" for p in c.nets["ESC_VRAIL"].pins)


def test_ina3221_address_0x42_strap(c: Circuit):
    # INA3221 A0=5, SDA=7; A0 strapped onto SDA => 0x42
    sda = {str(p) for p in c.nets["STM32_I2C2_SDA"].pins}
    assert {"U2.5", "U2.7"} <= sda
    assert "ESC_FAULT_N" in c.nets               # CRITICAL alert published


def test_tvs_clamps_the_rail(c: Circuit):
    # SMBJ28A K=1 (rail), A=2 (GND)
    assert any(str(p) == "D1.1" for p in c.nets["ESC_VRAIL_IN"].pins)
    assert any(str(p) == "D1.2" for p in c.nets["GND"].pins)


def test_pl_fault_pin_is_free_and_real():
    fmap = (REPO / "carrier" / "som_conn_gen.py").read_text()
    esc = dict(re.findall(r'"(IO_[A-Z0-9_]+)":\s*"(ESC_[A-Z0-9_]+)"', fmap))
    assert len(esc) == 10 and len(set(esc.values())) == 10   # no double-claim
    assert esc.get("IO_L1_N_13") == "ESC_FAULT_N"
    contract = json.loads((REPO / "carrier" / "som_interface.json").read_text())
    nets = {n for conn in contract["connectors"].values()
            for n in (conn.get("pins", conn) if isinstance(conn, dict)
                      else {}).values()}
    assert "IO_L1_N_13" in nets


def test_part_and_spice_slices_clean(c: Circuit, tmp_path):
    assert part_rules.run([_sheet(c)], tmp_path).ok
    assert spice.extract_checks([_sheet(c)]).ok
    assert "C42440491" in RATINGS_BY_LCSC       # SMBJ28A TVS catalogued


def test_cir_caps_match_netlist(c: Circuit):
    text = CIR.read_text()
    cir_caps = sorted(parse_si(m) for m in
                      re.findall(r"(?m)^C\d+\s+\S+\s+\S+\s+(\S+)", text))
    net_caps = sorted(parse_si(p.value) for r, p in c.parts.items()
                      if p.lib_id.endswith(":C"))
    assert cir_caps == net_caps, (cir_caps, net_caps)
