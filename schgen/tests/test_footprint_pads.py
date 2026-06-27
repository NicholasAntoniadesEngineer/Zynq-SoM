"""Tests for the footprint pad-coverage gate (schgen/verify/footprint_pads.py).

Locks the LAW-0 invariant: a symbol pin NUMBER with no PAD in the assigned
footprint is a guaranteed OPEN and must be flagged. A part whose every symbol
pin has a pad passes; a pad-number parse covers both the single-line and the
multi-line .kicad_mod formats; and the CURRENT board is CLEAN — the ethernet:T1
25/26 open that motivated the gate is fixed (faithful 24-pad HX5008NL), so the
hard-fail gate passes with zero pin-without-pad.

Synthetic footprints are written to a tmp dir and referenced by bare path, so
the tests are pure/offline (no dependency on the KiCad install)."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import footprint_pads


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


# Minimal .kicad_mod bodies in BOTH pad layouts schgen meets in the wild.
def _mod_singleline(nums) -> str:
    pads = "\n".join(
        f'  (pad "{n}" smd roundrect (at 0 0) (size 1 1) (layers "F.Cu"))'
        for n in nums)
    return f'(footprint "T" (layer "F.Cu")\n{pads}\n)\n'


def _mod_multiline(nums) -> str:
    pads = "\n".join(
        f'  (pad\n    "{n}"\n    smd\n    rect\n    (at 0 0)\n'
        f'    (size 1 1)\n    (layers "F.Cu")\n  )' for n in nums)
    return f'(footprint "T" (layer "F.Cu")\n{pads}\n)\n'


def test_pad_regex_both_formats():
    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        a = pathlib.Path(td) / "a.kicad_mod"
        b = pathlib.Path(td) / "b.kicad_mod"
        a.write_text(_mod_singleline(["1", "2", "3"]))
        b.write_text(_mod_multiline(["1", "2", "15"]))
        assert footprint_pads._read_pad_numbers(a) == {"1", "2", "3"}
        assert footprint_pads._read_pad_numbers(b) == {"1", "2", "15"}
        # an empty-number pad (NPTH/fiducial) is dropped, never referenced.
        c = pathlib.Path(td) / "c.kicad_mod"
        c.write_text(_mod_singleline(["1", "", "2"]))
        assert footprint_pads._read_pad_numbers(c) == {"1", "2"}


def test_pin_exceeding_pads_is_detected():
    # A 3-pad footprint with a symbol that uses pin 4 -> pin 4 is a dead OPEN.
    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mod = pathlib.Path(td) / "fp3.kicad_mod"
        mod.write_text(_mod_singleline(["1", "2", "3"]))

        class _Lib:
            def pin_numbers(self, lib_id):     # symbol uses 1..4
                return {"1", "2", "3", "4"}

        c = Circuit("t", "t")
        c.part("U1", "X:Y", "PART", str(mod))
        c.net("A", "U1.1")
        c.net("A", "U1.2")   # geometry irrelevant here
        r = footprint_pads.run([_sheet("t", c)], lib=_Lib())
        assert not r.ok, "pin 4 with no pad must be a VIOLATION"
        assert r.checked == 1
        assert any("U1" in v and "'4'" in v for v in r.violations), r.violations


def test_normal_part_passes():
    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mod = pathlib.Path(td) / "fp3.kicad_mod"
        mod.write_text(_mod_multiline(["1", "2", "3"]))

        class _Lib:
            def pin_numbers(self, lib_id):
                return {"1", "2", "3"}

        c = Circuit("t", "t")
        c.part("U1", "X:Y", "PART", str(mod))
        c.net("A", "U1.1")
        c.net("A", "U1.2")
        r = footprint_pads.run([_sheet("t", c)], lib=_Lib())
        assert r.ok, r.violations
        assert r.checked == 1
        assert not r.violations


def test_unresolved_footprint_is_reported_not_crashing():
    c = Circuit("t", "t")
    c.part("U1", "X:Y", "PART", "NoSuchLib:NoSuchFootprint")
    c.net("A", "U1.1")
    c.net("A", "U1.2")

    class _Lib:
        def pin_numbers(self, lib_id):
            return {"1", "2"}

    r = footprint_pads.run([_sheet("t", c)], lib=_Lib())
    assert r.ok                          # unresolved never fails the build
    assert r.checked == 0
    assert any("NoSuchFootprint" in u for u in r.unresolved)


def test_current_board_clean():
    # After the HX5008NL rebuild (faithful 24-pad dossier), the board has ZERO
    # pin-without-pad: every symbol pin lands on a real footprint pad. The gate
    # is hard-fail and must PASS on the current board.
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = footprint_pads.run(sheets)
    assert r.checked > 100, r.checked      # broad real coverage, not a no-op
    assert r.ok, f"unexpected pin-without-pad: {r.violations}"
    assert not r.violations, r.violations
