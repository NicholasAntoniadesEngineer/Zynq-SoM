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
    assert r.n_declared == 3
    assert r.n_components >= 3


def test_stray_wire_short_is_caught():
    c = _rc_circuit()
    routed = RoutedSheet()
    routed.segs = [Seg(101.6, 77.47, 101.6, 85.09, "+3V3")] + _clean_segs()
    routed.junctions = []
    r = cc_gate.check(c, _placement(), routed, _LIB, sheet="cc")
    assert not r.ok, "a +3V3/MID geometry bridge must be a SHORT"
    assert any("+3V3" in s and "MID" in s for s in r.shorts), r.shorts


def test_missing_leg_open_is_caught():
    c = _rc_circuit()
    routed = RoutedSheet()
    routed.segs = [
        Seg(101.6, 85.09, 101.6, 91.44, "MID"),
        Seg(101.6, 91.44, 111.76, 91.44, "MID"),
        Seg(111.76, 91.44, 116.84, 91.44, "MID"),
    ]
    routed.junctions = []
    r = cc_gate.check(c, _placement(), routed, _LIB, sheet="cc")
    assert not r.ok, "a stranded MID pin must be an OPEN"
    assert any("MID" in o and "split" in o for o in r.opens), r.opens
