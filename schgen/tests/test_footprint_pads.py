from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import footprint_pads


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


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
        c = pathlib.Path(td) / "c.kicad_mod"
        c.write_text(_mod_singleline(["1", "", "2"]))
        assert footprint_pads._read_pad_numbers(c) == {"1", "2"}


def test_pin_exceeding_pads_is_detected():
    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mod = pathlib.Path(td) / "fp3.kicad_mod"
        mod.write_text(_mod_singleline(["1", "2", "3"]))

        class _Lib:
            def pin_numbers(self, lib_id):
                return {"1", "2", "3", "4"}

        c = Circuit("t", "t")
        c.part("U1", "X:Y", "PART", str(mod))
        c.net("A", "U1.1")
        c.net("A", "U1.2")
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
    assert r.ok
    assert r.checked == 0
    assert any("NoSuchFootprint" in u for u in r.unresolved)


def test_current_board_clean():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = footprint_pads.run(sheets)
    assert r.checked > 100, r.checked
    assert r.ok, f"unexpected pin-without-pad: {r.violations}"
    assert not r.violations, r.violations
