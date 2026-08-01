from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from schgen.output.emit import Wire, emit
from schgen.verify import netlist_gate

_KICAD = shutil.which("kicad-cli")
_needs_kicad = pytest.mark.skipif(
    _KICAD is None, reason="kicad-cli not installed (the gate's only oracle)")


def test_norm_strips_kicad_sheet_prefix():
    assert netlist_gate._norm("/MID") == "MID"
    assert netlist_gate._norm("+3V3") == "+3V3"
    assert netlist_gate._norm("//x") == "x"


def _build_and_check(mutate=None):
    from schgen.tests import m1_rc
    c, d, lib = m1_rc.build()
    if mutate is not None:
        mutate(d)
    with tempfile.TemporaryDirectory(prefix="schgen_nl_test_") as td:
        out = Path(td) / "rc.kicad_sch"
        emit(d, out, lib)
        return netlist_gate.check(c, out)


@_needs_kicad
def test_clean_sheet_passes():
    r = _build_and_check()
    assert r.ok, (f"clean M1 sheet must pass: shorts={r.shorts} "
                  f"opens={r.opens} names={r.name_mismatches}")


@_needs_kicad
def test_short_two_nets_fails():
    def short(d):
        d.wires.append(Wire(101.6, 77.47, 101.6, 85.09))
    r = _build_and_check(short)
    assert not r.ok, "merging +3V3 and MID must FAIL"
    assert any("+3V3" in s and "MID" in s for s in r.shorts), r.shorts


def test_dead_two_terminal_flags_capshort():
    from schgen.core.model import Circuit
    c = Circuit("t", "capshort test")
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric")
    c.net("+3V3", "C1.1")
    c.net("GND", "C1.2")
    c.part("C2", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric")
    c.net("GND", "C2.1", "C2.2")
    c.part("R9", "Device:R", "0", "Resistor_SMD:R_0603_1608Metric")
    c.net("NETA", "R9.1")
    c.net("NETB", "R9.2")
    dead = netlist_gate._dead_two_terminal(c)
    assert any("C2" in s for s in dead), dead
    assert not any("C1" in s or "R9" in s for s in dead), dead


@_needs_kicad
def test_open_strands_pin_fails():
    def open_(d):
        d.wires = [w for w in d.wires
                   if not (w.x0 == 101.6 and w.y0 == 91.44
                           and w.x1 == 101.6 and w.y1 == 97.79)]
    r = _build_and_check(open_)
    assert not r.ok, "stranding R2.1 must FAIL"
    assert any("MID" in o for o in r.opens), r.opens
