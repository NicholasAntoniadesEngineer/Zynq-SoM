from __future__ import annotations

from pathlib import Path

from schgen.verify import fab_profile
from schgen.verify.fab_profile import JLCPCB_4L, FabProfile, check

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "carrier" / "Zynq_Carrier.kicad_pcb"


def test_committed_board_passes_jlc_profile() -> None:
    res = check()
    assert res.ok, res.report()
    assert all(ok for _m, _d, _f, ok in res.rows), res.report()
    assert res.demand.min_via_annular_mm is not None
    assert res.demand.min_via_annular_mm >= JLCPCB_4L.min_via_annular_mm - 1e-6


def test_report_is_deterministic() -> None:
    assert check().report() == check().report()


_BITE_PCB = """\
(kicad_pcb
  (version 20241229)
  (generator "test")
  (segment (start 0 0) (end 1 0) (width 0.05) (layer "F.Cu") (net 0))
  (via (at 5 5) (size 0.15) (drill 0.1) (layers "F.Cu" "B.Cu") (net 0))
)
"""


def _write_bite(tmp_path: Path) -> Path:
    p = tmp_path / "bite.kicad_pcb"
    p.write_text(_BITE_PCB)
    return p


def test_sub_profile_board_fails(tmp_path: Path) -> None:
    pcb = _write_bite(tmp_path)
    missing = tmp_path / "nope"
    res = check(pcb_path=pcb, dru_path=missing, pro_path=missing)
    assert not res.ok, res.report()
    joined = "\n".join(res.errors)
    assert "trace width" in joined
    assert "drill" in joined
    assert "annular" in joined


def test_bite_measures_the_real_geometry(tmp_path: Path) -> None:
    pcb = _write_bite(tmp_path)
    missing = tmp_path / "nope"
    d = fab_profile.measure_board(pcb, missing, missing)
    assert d.n_segments == 1 and d.n_vias == 1
    assert d.min_trace_mm == 0.05
    assert d.min_drill_mm == 0.1
    assert d.min_via_dia_mm == 0.15
    assert abs(d.min_via_annular_mm - 0.025) < 1e-9


def test_equal_to_floor_passes(tmp_path: Path) -> None:
    pcb = tmp_path / "edge.kicad_pcb"
    pcb.write_text(
        "(kicad_pcb (version 20241229) (generator \"test\")\n"
        "  (segment (start 0 0) (end 1 0) (width 0.09) (layer \"F.Cu\") (net 0))\n"
        "  (via (at 5 5) (size 0.30) (drill 0.15) (layers \"F.Cu\" \"B.Cu\") "
        "(net 0))\n)\n")
    missing = tmp_path / "nope"
    res = check(pcb_path=pcb, dru_path=missing, pro_path=missing)
    assert res.ok, res.report()


def test_finer_profile_flips_a_passing_board(tmp_path: Path) -> None:
    pcb = tmp_path / "edge.kicad_pcb"
    pcb.write_text(
        "(kicad_pcb (version 20241229) (generator \"test\")\n"
        "  (via (at 5 5) (size 0.30) (drill 0.15) (layers \"F.Cu\" \"B.Cu\") "
        "(net 0))\n)\n")
    missing = tmp_path / "nope"
    strict = FabProfile(
        name="hypothetical fine fab", min_trace_mm=0.05, min_clearance_mm=0.05,
        min_drill_mm=0.20, min_via_dia_mm=0.25, min_via_annular_mm=0.075,
        min_hole_to_hole_mm=0.15, source="test")
    res = check(profile=strict, pcb_path=pcb, dru_path=missing, pro_path=missing)
    assert not res.ok
    assert any("drill" in e for e in res.errors)


def test_missing_board_is_vacuously_ok(tmp_path: Path) -> None:
    res = check(pcb_path=tmp_path / "absent.kicad_pcb",
                dru_path=tmp_path / "nope", pro_path=tmp_path / "nope")
    assert res.ok
