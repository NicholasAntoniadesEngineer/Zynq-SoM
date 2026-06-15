"""Tests for the connected-components gate (schgen/verify/cc_gate.py) — the
SECOND, kicad-cli-INDEPENDENT electrical witness that rebuilds connectivity
from emitted GEOMETRY alone.

Locks: a clean RC divider's geometry agrees with its declared netlist (PASS, a
real declared-net + component count); a stray wire bridging two declared nets is
caught as a SHORT (net-blind geometry merge); and a missing wire leg that
strands a pin is caught as an OPEN. Pure/offline: model + geometry only, no
subprocess, no file I/O (the gate's whole point is to never call kicad-cli).

Geometry uses the hand-placed M1 RC layout (every wire endpoint exactly on a
pin, on the 1.27 mm grid). ``placement`` / ``routed`` are duck-typed: cc_gate
reads .parts(.ref/.lib_id/.x/.y/.rotation), .powers(.net_name/.x/.y),
.hlabels(.name/.x/.y), .llabels, and routed.segs / routed.junctions."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.core.symbols import Library
from schgen.layout.route import RoutedSheet
from schgen.verify import cc_gate
from schgen.verify.visual_gate import Seg

_LIB = Library()


def _part(ref, lib_id, x, y, rot=0):
    return types.SimpleNamespace(ref=ref, lib_id=lib_id, x=x, y=y, rotation=rot)


def _power(net_name, x, y):
    return types.SimpleNamespace(net_name=net_name, x=x, y=y)


def _hlabel(name, x, y):
    return types.SimpleNamespace(name=name, x=x, y=y)


def _rc_circuit() -> Circuit:
    # +3V3 - R1 - MID(port) - R2 - GND, with C1 from MID to GND (the M1 divider)
    c = Circuit("cc", "cc")
    c.part("R1", "Device:R", "10k")
    c.part("R2", "Device:R", "10k")
    c.part("C1", "Device:C", "100n")
    c.net("+3V3", "R1.1")
    c.port("MID", "R1.2", "R2.1", "C1.1")
    c.net("GND", "R2.2", "C1.2")
    c.validate({r: _LIB.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    return c


def _placement():
    # pin page positions (from the M1 hand-place, library-derived):
    #   R1.1=(101.6,77.47) R1.2=(101.6,85.09)  R2.1=(101.6,97.79) R2.2=(101.6,105.41)
    #   C1.1=(111.76,91.44) C1.2=(111.76,99.06)
    return types.SimpleNamespace(
        parts=[_part("R1", "Device:R", 101.6, 81.28),
               _part("R2", "Device:R", 101.6, 101.6),
               _part("C1", "Device:C", 111.76, 95.25)],
        powers=[_power("+3V3", 101.6, 77.47),
                _power("GND", 101.6, 105.41),
                _power("GND", 111.76, 99.06)],
        hlabels=[_hlabel("MID", 116.84, 91.44)],
        llabels=[],
    )


def _clean_segs():
    # MID trunk: R1.2 -> tap -> R2.1, tap -> C1.1 -> label stub
    return [
        Seg(101.6, 85.09, 101.6, 91.44, "MID"),
        Seg(101.6, 91.44, 101.6, 97.79, "MID"),
        Seg(101.6, 91.44, 111.76, 91.44, "MID"),
        Seg(111.76, 91.44, 116.84, 91.44, "MID"),
    ]


def test_clean_geometry_agrees_with_netlist():
    c = _rc_circuit()
    routed = RoutedSheet()
    routed.segs = _clean_segs()
    routed.junctions = [(101.6, 91.44), (111.76, 91.44)]
    r = cc_gate.check(c, _placement(), routed, _LIB, sheet="cc")
    assert r.ok, f"clean geometry must agree: {r.shorts} {r.opens}"
    assert r.n_declared == 3                       # +3V3, MID, GND
    assert r.n_components >= 3                      # real component partition


def test_stray_wire_short_is_caught():
    # a stray wire bridging the +3V3 node (101.6,77.47) to the MID trunk top
    # (101.6,85.09) geometrically merges two DIFFERENT declared nets -> SHORT.
    c = _rc_circuit()
    routed = RoutedSheet()
    routed.segs = [Seg(101.6, 77.47, 101.6, 85.09, "+3V3")] + _clean_segs()
    routed.junctions = []
    r = cc_gate.check(c, _placement(), routed, _LIB, sheet="cc")
    assert not r.ok, "a +3V3/MID geometry bridge must be a SHORT"
    assert any("+3V3" in s and "MID" in s for s in r.shorts), r.shorts


def test_missing_leg_open_is_caught():
    # drop the tap->R2.1 leg: R2.1 strands away from the MID trunk -> OPEN.
    c = _rc_circuit()
    routed = RoutedSheet()
    routed.segs = [
        Seg(101.6, 85.09, 101.6, 91.44, "MID"),
        Seg(101.6, 91.44, 111.76, 91.44, "MID"),
        Seg(111.76, 91.44, 116.84, 91.44, "MID"),
        # MISSING: tap (101.6,91.44) -> R2.1 (101.6,97.79)
    ]
    routed.junctions = []
    r = cc_gate.check(c, _placement(), routed, _LIB, sheet="cc")
    assert not r.ok, "a stranded MID pin must be an OPEN"
    assert any("MID" in o and "split" in o for o in r.opens), r.opens
