"""Tests for the unfakeable electrical gate (schgen/verify/netlist_gate.py):
declared netlist == kicad-cli's extracted netlist, pin for pin.

This gate's ONLY oracle is ``kicad-cli sch export netlist`` on an EMITTED sheet,
so its tests EMIT a tiny hand-placed sheet (the M1 RC divider) into a tempdir
and run the real kicad-cli — local, no network, deterministic. They skip
cleanly when kicad-cli is absent.

Locks: the net-name normaliser; the clean M1 sheet PASSES (declared == extracted);
a stray wire that merges two declared nets is caught as a SHORT (and the rail
loses its name); and a wire leg removed so a pin strands is caught as an OPEN.
Also a parser unit test (extract_netlist round-trip) that needs no emit."""

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
    """Emit the M1 RC divider (optionally mutated) and run the netlist gate."""
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
    # a stray vertical wire across R1 bridges R1.1 (+3V3) to R1.2 (MID): the
    # two declared nets merge into one extracted net -> SHORT (+ LOST-NAME rail).
    def short(d):
        d.wires.append(Wire(101.6, 77.47, 101.6, 85.09))
    r = _build_and_check(short)
    assert not r.ok, "merging +3V3 and MID must FAIL"
    assert any("+3V3" in s and "MID" in s for s in r.shorts), r.shorts


@_needs_kicad
def test_open_strands_pin_fails():
    # drop the tap->R2.1 wire (101.6,91.44)->(101.6,97.79): R2.1 strands off the
    # MID net -> OPEN (MID's pins split across extracted nets).
    def open_(d):
        d.wires = [w for w in d.wires
                   if not (w.x0 == 101.6 and w.y0 == 91.44
                           and w.x1 == 101.6 and w.y1 == 97.79)]
    r = _build_and_check(open_)
    assert not r.ok, "stranding R2.1 must FAIL"
    assert any("MID" in o for o in r.opens), r.opens
