"""RETURN-STITCH v2 gate + escape generator — red-on-before, mutation battery,
determinism, byte-superset, transparency (T2 escape wave).

The battery follows the test_pcb_gate_mutation.py discipline: a BASELINE
assertion precedes every mutant (a gate that always fires proves nothing),
then each defect class is injected and the gate must KILL it.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

from schgen.generate.pcb import escape
from schgen.generate.pcb.emit import emit_pcb
from schgen.verify import escape_lane_gate as elg
from schgen.verify import return_stitch_gate as rsg


@pytest.fixture(scope="module")
def model(carrier_model):
    return carrier_model


@pytest.fixture(scope="module")
def board(model, tmp_path_factory):
    out = tmp_path_factory.mktemp("t2_board") / "Zynq_Carrier.kicad_pcb"
    emit_pcb(model, out)
    return out


def _suppressed(model):
    """A copper-suppressed shallow copy — the red-on-before state."""
    m = copy.copy(model)
    m.copper = []
    m.escape_meta = {}
    m.escape_plan = None
    return m


# ---------------------------------------------------------------------------
# red-on-before (permanent): the un-remediated board FAILS with exactly the
# 29-contact baseline, naming the 8 GENUINE TMDS/HDMI halves.
# ---------------------------------------------------------------------------
def test_red_on_before_29_contacts(model):
    r = rsg.check(_suppressed(model))
    assert not r.ok
    assert r.n_contacts == 29 and r.n_covered == 0
    assert r.per_conn == {"J1": (1, 1), "J2": (28, 28), "J3": (0, 0)}
    genuine = [v for v in r.violations if "GENUINE" in v]
    assert len(genuine) == 8
    names = "\n".join(genuine)
    for half in ("HDMI_RX_D0_P", "HDMI_RX_D1_P", "HDMI_RX_D2_N",
                 "HDMI_RX_CLK_P", "ZYNQ_HDMI_TX_TMDS_0_N",
                 "ZYNQ_HDMI_TX_TMDS_1_P", "ZYNQ_HDMI_TX_TMDS_2_P",
                 "ZYNQ_HDMI_TX_TMDS_CLK_P"):
        assert half in names


def test_lane_gate_red_on_before(model):
    r = elg.check(_suppressed(model))
    assert not r.ok and "escape_plan is None" in r.violations[0]


# ---------------------------------------------------------------------------
# green baseline: the built model passes both gates with the emitted file.
# ---------------------------------------------------------------------------
def test_green_baseline(model, board):
    r = rsg.check(model, board)
    assert r.ok, r.summary()
    assert r.n_covered == r.n_contacts == 29
    assert r.worst_mm <= rsg.RETURN_VIA_RADIUS_MM
    assert r.file_parity == "ok"
    # construct tighter than gate (generator target)
    assert model.escape_meta["worst_cover_mm"] <= escape.R_CONSTRUCT
    # >= 2 vias per remediated connector (SPOF rule)
    for _ref, n in model.escape_meta["vias"].items():
        assert n >= escape.MIN_VIAS_PER_CONN
    lane = elg.check(model)
    assert lane.ok, lane.summary()
    assert lane.n_genuine == 15


# ---------------------------------------------------------------------------
# mutation battery — each defect class must be KILLED by the gate.
# ---------------------------------------------------------------------------
def _mutated(model, fn):
    m = copy.copy(model)
    m.copper = copy.deepcopy(model.copper)
    m.escape_meta = copy.deepcopy(model.escape_meta)
    fn(m)
    return m


def test_mutation_delete_via_names_contact(model):
    """Delete a BAND via (not J1's — its redundancy partner absorbs a single
    deletion BY DESIGN, judgment:2): the rightmost J2 via covers band 5 alone,
    so its loss must red the gate naming that band's contacts."""
    def kill_band5_via(m):
        j2 = [c for c in m.copper if c["kind"] == "via" and c["conn"] == "J2"]
        target = max(j2, key=lambda c: c["x"])
        m.copper.remove(target)
    r = rsg.check(_mutated(model, kill_band5_via))
    assert not r.ok
    assert any("> bound" in v for v in r.violations)


def test_mutation_j1_redundancy_survives_single_deletion(model):
    """POSITIVE control for the SPOF rule (judgment:2): J1's contact stays
    covered when its primary via dies, because the redundancy partner sits
    ~1.0 mm along the channel — that is WHY MIN_VIAS_PER_CONN = 2."""
    def kill_j1_primary(m):
        j1 = [c for c in m.copper if c["kind"] == "via" and c["conn"] == "J1"
              and c["role"] == "stitch"]
        m.copper.remove(j1[0])
    r = rsg.check(_mutated(model, kill_j1_primary))
    assert ("J1", "90") not in [(c[2], c[3]) for c in r.coverage
                                if c[5] is None or c[5] > rsg.RETURN_VIA_RADIUS_MM]


def test_mutation_foreign_barrel_precondition(model, tmp_path):
    """A foreign thru-hole barrel inside the In1 zone rect must RED the
    generator (the octagonal carve-out is a documented FUTURE path, not an
    implemented one — fail loud instead of an unproven fill)."""
    import copy as _copy

    from schgen.generate.pcb.constants import FootprintInst
    mod = tmp_path / "THT_TEST.kicad_mod"
    mod.write_text(
        '(footprint "THT_TEST" (layer "F.Cu")\n'
        '  (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1.0)'
        ' (layers "*.Cu" "*.Mask"))\n)\n')
    m = _copy.copy(model)
    kx0, ky0, kx1, ky1 = model.som_keepout
    m.insts = list(model.insts) + [FootprintInst(
        ref="TP9999", value="THT_TEST", footprint="Test:THT_TEST",
        x=(kx0 + kx1) / 2, y=(ky0 + ky1) / 2 + 5.0, rotation=0.0,
        pad_nets={"1": (model.net_numbers.get("+3V3", 1), "+3V3")},
        mod_path=mod, sheet="board_aux", side="top")]
    with pytest.raises(escape.EscapeError) as exc:
        escape.build_escape_copper(m)
    assert "barrel" in str(exc.value)


def test_mutation_shift_via_beyond_bound(model):
    def shift(m):
        for c in m.copper:
            if c["kind"] == "via":
                c["x"] += 10.0      # clean off the channel
    r = rsg.check(_mutated(model, shift))
    assert not r.ok
    # the message asserts "> bound", never a fabricated distance
    assert any("> bound" in v for v in r.violations)


def test_mutation_renet_via_to_3v3(model):
    def renet(m):
        v = next(c for c in m.copper if c["kind"] == "via")
        v["net"] = model.net_numbers.get("+3V3", 1)
        v["net_name"] = "+3V3"
    r = rsg.check(_mutated(model, renet))
    assert not r.ok
    assert any("LAW 0" in v for v in r.violations)


def test_mutation_delete_spine_breaks_connectivity(model):
    def kill_spine(m):
        i = next(i for i, c in enumerate(m.copper)
                 if c["kind"] == "segment" and c["role"] == "spine"
                 and c["conn"] == "J2")
        del m.copper[i]
    r = rsg.check(_mutated(model, kill_spine))
    assert not r.ok
    assert any("component" in v or "touches no F.Cu" in v
               for v in r.violations)


def test_mutation_strip_canonical_plane_fails_parity(model, board, tmp_path):
    """T2 emits no zone (GAP1's In1 plane is canonical) — but the plane must
    BE in the written file: the stitch vias' buried return half depends on
    it.  Stripping it reds the parity check."""
    text = board.read_text()
    assert text.count('(name "GND_plane_In1")') == 1
    stripped = tmp_path / "noplane.kicad_pcb"
    stripped.write_text(text.replace('(name "GND_plane_In1")',
                                     '(name "NOT_A_PLANE")'))
    r = rsg.check(model, stripped)
    assert not r.ok
    assert any("GND_plane_In1" in v or "parity" in v for v in r.violations)


def test_mutation_tamper_artifact_hash(model):
    def tamper(m):
        m.escape_meta["som_interface_sha256"] = "0" * 64
    r = rsg.check(_mutated(model, tamper))
    assert not r.ok
    assert any("STALE" in v for v in r.violations)


def test_mutation_strip_emitted_node_fails_parity(model, board, tmp_path):
    text = board.read_text()
    via = next(c for c in model.copper if c["kind"] == "via")

    def num(x):
        s = f"{x:.4f}".rstrip("0").rstrip(".")
        return s or "0"
    needle = f"(at {num(via['x'])} {num(via['y'])})"
    assert needle in text
    stripped = tmp_path / "stripped.kicad_pcb"
    stripped.write_text(text.replace(needle, "(at 5 5)", 1))
    r = rsg.check(model, stripped)
    assert not r.ok
    assert any("parity" in v for v in r.violations)


def test_mutation_lane_gate_kills_bad_genuine_pair(model):
    m = copy.copy(model)
    m.escape_plan = copy.deepcopy(model.escape_plan)
    g = next(p for p in m.escape_plan["pairs"] if p["si_class"] == "GENUINE")
    g["delta_lane"] = 5
    r = elg.check(m)
    assert not r.ok
    assert any("hard terms" in v for v in r.violations)


def test_mutation_lane_gate_kills_nonmonotonic_ports(model):
    m = copy.copy(model)
    m.escape_plan = copy.deepcopy(model.escape_plan)
    lns = [ln for ln in m.escape_plan["lanes"]["J2"]
           if ln["dir"] == "outward" and ln["row"] == 1]
    a, b = lns[0], lns[1]
    a["port"], b["port"] = b["port"], a["port"]
    r = elg.check(m)
    assert not r.ok
    assert any("monotonic" in v for v in r.violations)


def test_mutation_lane_gate_kills_stale_content_key(model):
    m = copy.copy(model)
    m.escape_plan = copy.deepcopy(model.escape_plan)
    m.escape_plan["content_key"] = "0" * 64
    r = elg.check(m)
    assert not r.ok
    assert any("STALE" in v for v in r.violations)


# ---------------------------------------------------------------------------
# generator unit tests — banding, seating, determinism, fail-loud.
# ---------------------------------------------------------------------------
def test_band_cover_absorbs_within_2r():
    pts = [(0.0, "1"), (0.4, "2"), (0.8, "3"), (5.0, "4")]
    bands = escape.band_cover(pts, reach=1.0)
    assert [len(b) for b in bands] == [3, 1]


def test_band_cover_window_nonempty_by_construction():
    # span just under 2r stays one band; the via window is the intersection
    pts = [(0.0, "1"), (1.9, "2")]
    bands = escape.band_cover(pts, reach=1.0)
    assert len(bands) == 1
    (u_first, _), (u_last, _) = bands[0][0], bands[0][-1]
    assert u_last - 1.0 <= u_first + 1.0   # nonempty window


def test_band_cover_splits_beyond_2r():
    pts = [(0.0, "1"), (2.1, "2")]
    assert [len(b) for b in escape.band_cover(pts, reach=1.0)] == [1, 1]


def test_band_cover_tiebreak_deterministic():
    pts = [(0.4, "90"), (0.4, "11")]     # facing-row pads share u exactly
    bands = escape.band_cover(pts, reach=1.0)
    assert bands[0] == [(0.4, "11"), (0.4, "90")]


def test_seat_band_prefers_on_axis():
    m = escape._Member(pad="1", net="X", u=0.4, v=-1.355, klass="LOW")
    obs = escape._Obstacles()
    seats = escape._seat_band([m], obs, 1.355, [], "JX")
    assert len(seats) == 1
    assert seats[0]["v"] == 0.0 and abs(seats[0]["u"] - 0.4) < 1e-9
    assert (seats[0]["dia"], seats[0]["drill"]) == escape.VIA_LADDER[0]


def test_seat_band_obstacle_accumulation_hole_to_hole():
    m = escape._Member(pad="1", net="X", u=0.0, v=-1.355, klass="LOW")
    obs = escape._Obstacles()
    obs.holes.append((0.0, 0.0, 0.15, "prior-via"))     # a via already there
    seats = escape._seat_band([m], obs, 1.355, [], "JX")
    (s,) = seats
    d = math.hypot(s["u"], s["v"])
    assert d >= 0.5 + 0.15 + s["drill"] / 2 - 1e-9      # hole-hole respected


def test_seat_band_blocked_channel_raises_with_audit():
    m = escape._Member(pad="1", net="X", u=0.0, v=-1.355, klass="LOW")
    obs = escape._Obstacles()
    obs.b_cu.append((-5.0, -5.0, 5.0, 5.0, 0.15, "WALL(everything).1"))
    with pytest.raises(escape.EscapeError) as exc:
        escape._seat_band([m], obs, 1.355, [], "JX")
    assert "WALL" in str(exc.value)
    assert "bottom-channel-keepout" in str(exc.value)   # LAW-7 named remedy


def test_via_in_pad_dfm_rule():
    """The drill must stay off SAME-NET pad copper (fine-pitch solder-wick
    DFM rule) — a candidate centered in the 0.2 mm GND pair-gap is rejected."""
    obs = escape._Obstacles()
    obs.samenet_pads.append((-0.3, -1.685, -0.1, -1.025, 0.15, "GNDpadL"))
    obs.samenet_pads.append((0.1, -1.685, 0.3, -1.025, 0.15, "GNDpadR"))
    audit: list[str] = []
    ok = escape._via_feasible(0.0, -1.355, 0.45, 0.3, obs, audit)
    assert not ok and any("via-in-pad DFM" in a for a in audit)


def test_generator_determinism(model):
    c1, m1 = escape.build_escape_copper(model)
    c2, m2 = escape.build_escape_copper(model)
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)
    assert (json.dumps(m1, sort_keys=True, default=list)
            == json.dumps(m2, sort_keys=True, default=list))
    p1 = escape.build_escape_plan(model)
    p2 = escape.build_escape_plan(model)
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


# ---------------------------------------------------------------------------
# emission: byte-superset + double-emit determinism + silk transparency.
# ---------------------------------------------------------------------------
def test_emission_byte_superset_and_deterministic(model, board, tmp_path):
    pre = tmp_path / "pre.kicad_pcb"
    emit_pcb(_suppressed(model), pre)
    post = board.read_text()
    again = tmp_path / "again.kicad_pcb"
    emit_pcb(model, again)
    assert post == again.read_text()                    # build twice
    pre_text = pre.read_text()
    assert post.startswith(pre_text[:-2])               # byte-superset
    tail = post[len(pre_text) - 2:]
    # the appended tail is copper only — invisible to every silk/refdes scan
    assert "(segment" in tail and "(via" in tail
    assert "(zone" not in tail          # zones are GAP1's, never appended here
    assert "fp_text" not in tail and "gr_text" not in tail
    assert "(locked yes)" in tail
    # every escape node is locked (Freerouting fixed-preroute contract)
    n_locked = tail.count("(locked yes)")
    n_nodes = tail.count("(via") + tail.count("(segment")
    assert n_locked == n_nodes


def test_zone_emitted_unfilled(board):
    """The CANONICAL In1 GND plane (GAP1 emission) carries (fill yes ...) but
    NO filled_polygon nodes — fills exist only in kicad-cli memory via
    --refill-zones (T2 P0 probe; cross-checks GAP1's own emission tests)."""
    text = board.read_text()
    assert '(name "GND_plane_In1")' in text
    zone_at = text.index('(name "GND_plane_In1")')
    assert "filled_polygon" not in text[zone_at:]


def test_refill_zones_at_exactly_two_drc_sites():
    """--refill-zones must appear at the two and only two DRC sites."""
    from pathlib import Path
    root = Path(escape.__file__).resolve().parents[3]
    emit_src = (root / "schgen" / "generate" / "pcb" / "emit.py").read_text()
    main_src = (root / "schgen" / "__main__.py").read_text()
    assert emit_src.count('"--refill-zones"') == 1
    assert main_src.count('"--refill-zones"') == 1


def test_backstop_kicad_drc_kills_via_at_tmds_pad(model, tmp_path):
    """Third LAW-0 proof layer: a via emitted AT a TMDS pad center must raise
    kicad-cli DRC ERRORS (clearance/shorting are error class) — proving the
    toolchain backstop bites beyond the in-process gates.  Baseline first:
    the unmutated board is error-clean under the same rules."""
    import copy as _copy
    import shutil
    import subprocess

    from schgen.generate.pcb.constants import CARRIER

    def drc_errors(pcb) -> int:
        rpt = pcb.with_suffix(".drc.json")
        subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json",
             "--severity-error", "--refill-zones", "-o", str(rpt), str(pcb)],
            capture_output=True, text=True, check=False)
        return len(json.loads(rpt.read_text()).get("violations", []))

    shutil.copy(CARRIER / "Zynq_Carrier.kicad_pro",
                tmp_path / "Zynq_Carrier.kicad_pro")
    base = tmp_path / "Zynq_Carrier.kicad_pcb"
    emit_pcb(model, base)
    assert drc_errors(base) == 0          # baseline: error-clean

    m = _copy.copy(model)
    m.copper = _copy.deepcopy(model.copper)
    # TMDS pad 69 center on J2 (board frame, from the same transform the
    # gates use)
    from schgen.verify.placement_contract_gate import _inst_pad_boxes
    j2 = next(i for i in model.insts if i.sheet == "som_j2")
    bb = _inst_pad_boxes(j2)["69"]
    v = next(c for c in m.copper if c["kind"] == "via")
    v["x"], v["y"] = round((bb[0] + bb[2]) / 2, 4), round((bb[1] + bb[3]) / 2, 4)
    shutil.copy(CARRIER / "Zynq_Carrier.kicad_pro",
                tmp_path / "mut.kicad_pro")
    mut = tmp_path / "mut.kicad_pcb"
    emit_pcb(m, mut)
    assert drc_errors(mut) > 0            # the backstop bites


def test_coexistence_verdicts_present(model):
    """F5: every bottom-side part inside the escape region carries an explicit
    STAY/CONSTRAINT/EVICT verdict with a basis string — never silent."""
    co = model.escape_meta["coexistence"]
    assert isinstance(co, list), "coexistence table missing"
    assert model.escape_meta.get("escape_region"), (
        "escape_region absent — coexistence machinery dead, not merely clean")
    assert all(c["verdict"] in ("STAY", "CONSTRAINT", "EVICT") for c in co)
    assert all(c["basis"] for c in co)
    # CONSTRAINT is a GEOMETRY-DERIVED verdict, re-derived every build: an
    # hdmi_rx_term strap earns it IFF it lands in a connector whose escape ledger
    # recorded a window split (split_u/split_row) that build. Assert the machinery
    # tracks the ledger EXACTLY — not a fixed CONSTRAINT count (a packer that opens
    # the windows, like the T1 ethernet-wave repack, legitimately leaves 0 splits
    # and thus all-STAY; a CONSTRAINT with no split, or a split with no CONSTRAINT,
    # is the real bug this kills). See ``escape._coexistence`` ``escal_conns``.
    ledger = model.escape_meta["ledger"]
    split_conns = {e["conn"] for e in ledger
                   if e.get("kind") in ("split_u", "split_row")}
    constrained = {c["conn"] for c in co if c["verdict"] == "CONSTRAINT"}
    assert all(c["sheet"] == "hdmi_rx_term"
               for c in co if c["verdict"] == "CONSTRAINT"), (
        "only hdmi_rx_term straps may be CONSTRAINT")
    assert constrained <= split_conns, (
        f"CONSTRAINT on a connector with no window split: "
        f"{constrained - split_conns}")
    # every split connector with an hdmi_rx_term strap in its region MUST show the
    # CONSTRAINT (never a silent STAY that hides a narrowed window)
    hdmi_conns = {c["conn"] for c in co if c["sheet"] == "hdmi_rx_term"}
    assert (split_conns & hdmi_conns) <= constrained, (
        f"window split near an hdmi_rx_term strap not surfaced as CONSTRAINT: "
        f"{(split_conns & hdmi_conns) - constrained}")
    # nothing was deleted or moved: verdicts are data, the insts still exist
    refs = {i.ref for i in model.insts}
    assert all(c["ref"] in refs for c in co)
