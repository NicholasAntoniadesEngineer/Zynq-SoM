"""Mutation tests for the FAN-OUT CLEARANCE gate (schgen.verify.fanout_gate).

The gate's reason to exist: a multi-pin IC packed too tight against FOREIGN parts
cannot fan its pins out, yet DRC / ratsnest / mech-place are all blind to it. So each
test is a mutant — a synthetic placed model that should PASS, then a single-property
change that must flip the verdict — proving the gate bites AND that the two anti-dumb
guards (own-cluster passive exclusion, opposite-side exclusion) actually exclude.

Pure/offline: real footprints supply the courtyard geometry (via mod_path), pin count
is set on ``pad_nets`` directly so the tier is controllable without a many-pin part.
"""

from __future__ import annotations

from schgen.generate import pcb
from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
    PcbModel,
)
from schgen.verify import fanout_gate as fg

# a resistor footprint (~1.6x0.9 mm courtyard) — crowding neighbour + cluster passive
_R_MOD = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
assert _R_MOD is not None, "R_0603 footprint missing"


def _part(ref, x, y, npins, *, sheet="s", side="top", mod=None, value="x"):
    """A real-footprint FootprintInst at (x, y) whose PIN COUNT is exactly ``npins``
    (set on pad_nets so the intelligent-need tier is controllable)."""
    m = mod or _R_MOD
    pad_nets = {str(i): (i, f"N{i}") for i in range(1, npins + 1)}
    return FootprintInst(ref=ref, value=value, footprint="lib:x", x=x, y=y,
                         rotation=0.0, pad_nets=pad_nets, mod_path=m,
                         sheet=sheet, side=side)


def _model(insts):
    return PcbModel(board_w=100.0, board_h=80.0, insts=insts,
                    net_numbers={"": 0}, netclass_of={}, classes={},
                    placed=len(insts), deferred=[])


# ---- the intelligent-need tiers ------------------------------------------------------

def test_need_scales_with_pin_count():
    """UNIFORM rule, INTELLIGENT value: the floor grows monotonically with pins and hits
    the documented break-points (2-pin passive ~0, a big BGA-class part a full apron).
    """
    n2, _ = fg.intelligent_need(2)
    n8, _ = fg.intelligent_need(8)
    n20, _ = fg.intelligent_need(20)
    n48, _ = fg.intelligent_need(48)
    n100, _ = fg.intelligent_need(100)
    assert n2 == 0.20 and n8 == 0.50 and n20 == 1.00 and n48 == 1.50 and n100 == 2.00
    assert n2 < n8 < n20 < n48 < n100          # strictly monotonic (intelligent)


# ---- a spacious IC PASSES, a starved one FAILS ---------------------------------------

def test_spacious_ic_passes():
    """An 8-pin IC (need 0.5 mm) whose nearest FOREIGN part is far is NOT starved."""
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    far = _part("R9", ORIGIN_X + 40, ORIGIN_Y + 20, npins=2, sheet="b")  # foreign ~18mm
    res = fg.check(_model([ic, far]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert not rec.starved, res.summary()
    assert res.n_starved == 0 and res.ok
    assert rec.clearance > rec.need


def test_starved_ic_fails():
    """The SAME 8-pin IC with a FOREIGN part jammed against its courtyard (gap < 0.5 mm)
    IS starved — and with baseline 0 the ratchet FAILS the board (a regression)."""
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    # a foreign IC ~0.2 mm off U1's courtyard (0603 half-w ~0.8 mm; centres 1.9 apart)
    near = _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b")
    res = fg.check(_model([ic, near]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert rec.starved, res.summary()
    assert rec.clearance < rec.need
    assert res.n_starved >= 1
    assert not res.ok, "baseline 0 => a starved IC is a ratchet regression => FAIL"
    assert any("U1" in g for g in res.regressions)


# ---- the anti-dumb guards -----------------------------------------------------------

def test_own_cluster_passive_excluded():
    """A 2-pin decoupling cap on the IC's OWN sheet sitting tight ON its pins must NOT
    count as crowding — the whole point of the cluster-aware rule. With ONLY the cap
    nearby the IC is NOT starved (the cap is invisible to the clearance scan)."""
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="pwr")
    # a decoupling cap 0.1 mm off the courtyard, SAME sheet, 2-pin C -> excluded
    cap = _part("C1", ORIGIN_X + 21.7, ORIGIN_Y + 20, npins=2, sheet="pwr",
                value="100nF")
    cap.ref = "C1"        # C prefix -> cluster passive
    res = fg.check(_model([ic, cap]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert not rec.starved, ("own-cluster cap must not crowd", res.summary())
    assert rec.nearest_ref == "(none)"     # no foreign neighbour at all
    assert res.ok


def test_foreign_sheet_passive_does_crowd():
    """The SAME tight 2-pin cap on a DIFFERENT sheet is FOREIGN and DOES crowd — proving
    the exclusion is scoped to the IC's OWN cluster, not to all passives."""
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="pwr")
    cap = _part("C9", ORIGIN_X + 21.7, ORIGIN_Y + 20, npins=2, sheet="OTHER",
                value="100nF")
    res = fg.check(_model([ic, cap]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert rec.starved, ("foreign-sheet cap must crowd", res.summary())
    assert rec.nearest_ref == "C9"


def test_opposite_side_part_excluded():
    """A part directly UNDER the IC but on the OPPOSITE copper side is the 2-side
    assembly working as designed, not fan-out crowding — it must be excluded (measuring
    across the plane is the dumb cross-layer halo the intent rejects)."""
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a", side="top")
    # a foreign IC at the SAME xy but on the BOTTOM (courtyards fully overlap, gap 0)
    under = _part("U2", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="b",
                  side="bottom")
    res = fg.check(_model([ic, under]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert not rec.starved, ("opposite-side part must not crowd", res.summary())
    assert rec.nearest_ref == "(none)"
    # and flipping the neighbour to the SAME side makes it crowd (gap 0 << need)
    under.side = "top"
    res2 = fg.check(_model([ic, under]), baseline=0)
    rec2 = next(r for r in res2.records if r.ref == "U1")
    assert rec2.starved and rec2.clearance == 0.0, res2.summary()


def test_df40_plug_excluded_as_subject_and_neighbour():
    """The DF40 mezzanine plug (som_j* sheet, >=40 pins) is EXCLUDED as a fan-out
    subject (no-inflate) AND never counts as a crowding neighbour."""
    plug = _part("J24001", ORIGIN_X + 20, ORIGIN_Y + 20, npins=104, sheet="som_j1")
    # an IC jammed right against the plug — the plug must be invisible to it
    ic = _part("U1", ORIGIN_X + 22, ORIGIN_Y + 20, npins=8, sheet="a")
    res = fg.check(_model([plug, ic]), baseline=0)
    assert not any(r.ref == "J24001" for r in res.records), "DF40 must not be a subject"
    rec = next(r for r in res.records if r.ref == "U1")
    assert rec.nearest_ref == "(none)", ("DF40 must not crowd", res.summary())
    assert not rec.starved


def test_two_pin_passive_not_a_subject():
    """A 1-2-pin passive is a cluster member, never a fan-out SUBJECT (min 3 pins)."""
    r1 = _part("R1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=2, sheet="a")
    ic = _part("U1", ORIGIN_X + 40, ORIGIN_Y + 20, npins=8, sheet="a")
    res = fg.check(_model([r1, ic]), baseline=0)
    subjects = {r.ref for r in res.records}
    assert "R1" not in subjects and "U1" in subjects


# ---- the report-first ratchet -------------------------------------------------------

def test_ratchet_passes_at_or_below_baseline_fails_above():
    """REPORT-FIRST: the standing debt does NOT block (starved <= baseline => PASS); a
    NEW starved IC over the baseline FAILS loudly."""
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    near = _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b")
    m = _model([ic, near])
    # the two ICs crowd EACH OTHER -> 2 starved. baseline 2 => PASS (debt tolerated);
    # baseline 1 => FAIL (one more starved than the ceiling allows).
    assert fg.check(m, baseline=2).n_starved == 2
    assert fg.check(m, baseline=2).ok
    assert not fg.check(m, baseline=1).ok


def test_first_run_self_pins_baseline_and_passes(monkeypatch, tmp_path):
    """With no baseline supplied and no sidecar, the current starved count is adopted as
    the baseline and the gate PASSES (first run pins the debt, never blocks).

    Hermetic: the repo now SHIPS a ratcheted sidecar (starved_baseline 0), so point the
    gate at an ABSENT temp path to exercise the genuine first-run / no-sidecar branch
    rather than reading the real ceiling (else this test becomes order-dependent)."""
    monkeypatch.setattr(fg, "_BASELINE_PATH", tmp_path / "absent_fanout_baseline.json")
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    near = _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b")
    res = fg.check(_model([ic, near]), baseline=None)
    # baseline is either the sidecar's value or self-pinned; either way it must be >=
    # the live count so the first run passes.
    assert res.baseline is not None and res.baseline >= res.n_starved
    assert res.ok


def test_write_baseline_only_ratchets_down(tmp_path):
    """The persisted ceiling may only DECREASE (a build can never regrow the debt)."""
    p = tmp_path / "fanout_baseline.json"
    fg.write_baseline(18, path=p)
    fg.write_baseline(12, path=p)     # improvement -> ratchets down
    import json
    assert json.loads(p.read_text())["starved_baseline"] == 12
    fg.write_baseline(30, path=p)     # regression attempt -> must NOT raise the ceiling
    assert json.loads(p.read_text())["starved_baseline"] == 12


# ---- determinism --------------------------------------------------------------------

def test_records_sorted_worst_first_deterministic():
    """The offender list is sorted by slack (worst first), ties by ref — stable x2."""
    insts = [
        _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=24, sheet="a"),   # big need
        _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b"),  # crowds U1
        _part("U3", ORIGIN_X + 60, ORIGIN_Y + 20, npins=8, sheet="c"),    # spacious
    ]
    r1 = fg.check(_model(insts), baseline=0)
    r2 = fg.check(_model(insts), baseline=0)
    assert [r.ref for r in r1.records] == [r.ref for r in r2.records]
    slacks = [r.slack for r in r1.records]
    assert slacks == sorted(slacks), "worst slack must come first"
