from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import pin_completeness


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


class _Lib:
    class _Sym:
        def __init__(self, pins):
            self.pins = pins

    def __init__(self):
        P = pin_completeness  # noqa: F841
        self._pins = [types.SimpleNamespace(number=str(i), name=f"P{i}")
                      for i in range(1, 5)]

    def get(self, lib_id):
        return _Lib._Sym(self._pins)

    def pin_numbers(self, lib_id):
        return {p.number for p in self._pins}


def test_silent_float_detected():
    c = Circuit("t", "t")
    c.part("U1", "X:Y", "PART")
    c.net("A", "U1.1")
    c.net("A", "U1.2")
    c.nc("U1.3")
    r = pin_completeness.run([_sheet("t", c)], lib=_Lib(), allowlist={})
    assert not r.ok, "pin 4 (neither netted nor NC) must be a SILENT FLOAT"
    assert any("U1" in f and "4(P4)" in f for f in r.floats), r.floats
    assert r.parts_checked == 1
    assert r.nc_total == 1


def test_fully_accounted_part_passes():
    c = Circuit("t", "t")
    c.part("U1", "X:Y", "PART")
    c.net("A", "U1.1")
    c.net("A", "U1.2")
    c.net("B", "U1.3")
    c.net("B", "U1.4")
    r = pin_completeness.run([_sheet("t", c)], lib=_Lib(), allowlist={})
    assert r.ok, r.floats
    assert not r.floats
    assert r.parts_checked == 1
    assert r.nc_total == 0


def test_allowlist_splits_seed_vs_new():
    c = Circuit("t", "t")
    c.part("U1", "X:Y", "PART")
    c.net("A", "U1.1")
    c.net("A", "U1.2")
    c.nc("U1.3", "U1.4")
    r = pin_completeness.run([_sheet("t", c)], lib=_Lib(),
                             allowlist={"t": {"U1": ["3"]}})
    assert r.ok, r.floats
    assert any("U1.3" in s for s in r.nc_seeded), r.nc_seeded
    assert any("U1.4" in n for n in r.nc_new), r.nc_new


def test_current_board_no_floats_and_seeds_resolve():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = pin_completeness.run(sheets)
    assert r.parts_checked > 100
    assert r.floats == [], r.floats
    assert r.nc_total > 0
    assert any("usb_jtag:U1.2" in s for s in r.nc_seeded), r.nc_seeded
    assert any("board_services:U2.1" in s for s in r.nc_seeded), r.nc_seeded
