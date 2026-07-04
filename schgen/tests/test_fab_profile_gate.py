"""Tests for the FAB-PROFILE gate (GAP3): the emitted board's tightest demanded
geometry vs the pinned JLCPCB 4-layer capability profile.

Locks:
  1. the committed board PASSES the JLC 4-layer profile (every demanded metric
     is at or above the fab floor) — the honest current verdict;
  2. SYNTHETIC BITE — a board that demands finer-than-fab geometry (a hair-thin
     track, a sub-fab via drill, a too-small via annular) FAILS, per-metric;
  3. the measurement is honest (reads the emitted file, not the model) and the
     profile semantics are strict (demand == floor passes; demand < floor fails).

Offline: the bite uses a tiny hand-written .kicad_pcb (no placer, no kicad-cli).
"""

from __future__ import annotations

from pathlib import Path

from schgen.verify import fab_profile
from schgen.verify.fab_profile import JLCPCB_4L, FabProfile, check

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "carrier" / "Zynq_Carrier.kicad_pcb"


# ---- 1. the real board passes ----------------------------------------------------

def test_committed_board_passes_jlc_profile() -> None:
    res = check()
    assert res.ok, res.report()
    # every per-metric row must be PASS
    assert all(ok for _m, _d, _f, ok in res.rows), res.report()
    # the finest via annular the board emits is exactly JLC's preferred-via floor
    assert res.demand.min_via_annular_mm is not None
    assert res.demand.min_via_annular_mm >= JLCPCB_4L.min_via_annular_mm - 1e-6


def test_report_is_deterministic() -> None:
    assert check().report() == check().report()


# ---- 2. synthetic bite: a sub-profile board must FAIL ----------------------------

# a minimal but VALID KiCad pcb: one net-less via with a sub-fab drill (0.1 mm,
# below the 0.15 mm floor) AND a sub-fab annular (dia 0.15 / drill 0.1 -> 0.025 mm
# per side, below the 0.075 mm via-annular floor), plus a hair-thin track segment
# (0.05 mm, below the 0.09 mm trace floor).
_BITE_PCB = """\
(kicad_pcb
  (version 20241229)
  (generator "test")
  (segment (start 0 0) (end 1 0) (width 0.05) (layer "F.Cu") (net 0))
  (via (at 5 5) (size 0.15) (drill 0.1) (layers "F.Cu" "B.Cu") (net 0))
)
"""

# a bite board with NO .dru / .kicad_pro alongside it, so the gate exercises the
# pure emitted-geometry path (no design-rule floors to fold in).


def _write_bite(tmp_path: Path) -> Path:
    p = tmp_path / "bite.kicad_pcb"
    p.write_text(_BITE_PCB)
    return p


def test_sub_profile_board_fails(tmp_path: Path) -> None:
    pcb = _write_bite(tmp_path)
    missing = tmp_path / "nope"            # no .dru / .kicad_pro on this path
    res = check(pcb_path=pcb, dru_path=missing, pro_path=missing)
    assert not res.ok, res.report()
    # the three sub-fab demands are all flagged by name
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
    # annular = (0.15 - 0.1) / 2 = 0.025
    assert abs(d.min_via_annular_mm - 0.025) < 1e-9


# ---- 3. profile semantics: demand == floor PASSES, demand < floor FAILS ----------

def test_equal_to_floor_passes(tmp_path: Path) -> None:
    # a via whose annular is EXACTLY the floor and a track EXACTLY at the trace
    # floor must PASS (no false-fail on representation-equal geometry).
    pcb = tmp_path / "edge.kicad_pcb"
    # via dia 0.30 / drill 0.15 -> annular 0.075 == floor; drill 0.15 == floor;
    # dia 0.30 >= 0.25 floor; track 0.09 == trace floor.
    pcb.write_text(
        "(kicad_pcb (version 20241229) (generator \"test\")\n"
        "  (segment (start 0 0) (end 1 0) (width 0.09) (layer \"F.Cu\") (net 0))\n"
        "  (via (at 5 5) (size 0.30) (drill 0.15) (layers \"F.Cu\" \"B.Cu\") "
        "(net 0))\n)\n")
    missing = tmp_path / "nope"
    res = check(pcb_path=pcb, dru_path=missing, pro_path=missing)
    assert res.ok, res.report()


def test_finer_profile_flips_a_passing_board(tmp_path: Path) -> None:
    # the SAME edge board fails against a STRICTER hypothetical fab (proves the
    # gate compares against the profile, not a hardcoded verdict).
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
    # the 0.15 mm drill is now BELOW the 0.20 mm strict floor
    assert not res.ok
    assert any("drill" in e for e in res.errors)


def test_missing_board_is_vacuously_ok(tmp_path: Path) -> None:
    # no board file -> nothing demanded -> no metric can be finer than the fab.
    res = check(pcb_path=tmp_path / "absent.kicad_pcb",
                dru_path=tmp_path / "nope", pro_path=tmp_path / "nope")
    assert res.ok
