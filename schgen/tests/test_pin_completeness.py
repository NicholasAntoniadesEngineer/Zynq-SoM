"""Tests for the pin-completeness gate (schgen/verify/pin_completeness.py).

Locks the LAW-0 invariant: a multi-pin IC pin that is neither netted nor NC is
a SILENT FLOAT (probable missing connection) and must be flagged; a part whose
every pin is netted or NC passes. Also locks that the allowlist correctly
splits the board's author-declared NCs into [seed] (blessed) vs [new] (backlog),
seeded from the datasheet-confirmed CH347 / RV-3028 findings.

Synthetic parts use a stub Library so the float/complete cases are pure/offline;
the board-level cases exercise the real model + committed allowlist."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import pin_completeness


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


class _Lib:
    """Stub Library: a single 4-pin part 'X:Y' with named pins 1..4."""

    class _Sym:
        def __init__(self, pins):
            self.pins = pins

    def __init__(self):
        P = pin_completeness  # noqa: F841 (keep import obviously used)
        self._pins = [types.SimpleNamespace(number=str(i), name=f"P{i}")
                      for i in range(1, 5)]

    def get(self, lib_id):
        return _Lib._Sym(self._pins)

    def pin_numbers(self, lib_id):
        return {p.number for p in self._pins}


def test_silent_float_detected():
    # 4-pin IC: pins 1,2 netted, pin 3 NC, pin 4 left FLOATING -> flagged.
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
    # every pin netted or NC -> no float.
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
    # pin 3 NC and in the allowlist -> [seed]; pin 4 NC but not -> [new].
    c = Circuit("t", "t")
    c.part("U1", "X:Y", "PART")
    c.net("A", "U1.1")
    c.net("A", "U1.2")
    c.nc("U1.3", "U1.4")
    r = pin_completeness.run([_sheet("t", c)], lib=_Lib(),
                             allowlist={"t": {"U1": ["3"]}})
    assert r.ok, r.floats               # no floats; both pins are NC
    assert any("U1.3" in s for s in r.nc_seeded), r.nc_seeded
    assert any("U1.4" in n for n in r.nc_new), r.nc_new


def test_current_board_no_floats_and_seeds_resolve():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = pin_completeness.run(sheets)
    assert r.parts_checked > 100         # broad coverage, not a no-op
    assert r.floats == [], r.floats      # validated board has zero floats
    assert r.nc_total > 0
    # the datasheet-confirmed seeds (morning_stageA usb_jtag-3 / io_misc-4)
    # must land in the BLESSED set, not the backlog.
    assert any("usb_jtag:U1.2" in s for s in r.nc_seeded), r.nc_seeded
    assert any("board_services:U2.1" in s for s in r.nc_seeded), r.nc_seeded
