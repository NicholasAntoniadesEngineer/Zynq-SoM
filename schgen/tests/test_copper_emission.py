from __future__ import annotations

import math
from pathlib import Path

import pytest

from schgen.core import sexpr
from schgen.generate.pcb import embed
from schgen.generate.pcb.constants import (
    ORIGIN_X,
    ORIGIN_Y,
    THERMAL_COPPER,
    THERMAL_VIA_SIZE,
    FootprintInst,
    PcbModel,
)
from schgen.verify import copper_debt

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "carrier" / "Zynq_Carrier.kicad_pcb"


def _mini_model() -> PcbModel:
    mod = REPO / "parts" / "LM61460AANRJRR" / "LM61460AANRJRR.kicad_mod"
    pad_nets = {"9": (2, "GND"), "11": (2, "GND"), "3": (2, "GND"),
                "10": (5, "SW_X"), "8": (4, "+5V"), "12": (4, "+5V"),
                "14": (6, "CBOOT"), "13": (7, "RBOOT"), "1": (8, "BIAS"),
                "4": (9, "FB"), "5": (10, "PGOOD"), "6": (11, "EN"),
                "7": (12, "MODE"), "2": (13, "VCC")}
    inst = FootprintInst(
        ref="U1", value="LM61460AANRJRR",
        footprint="LM61460AANRJRR:LM61460AANRJRR",
        x=ORIGIN_X + 50.0, y=ORIGIN_Y + 40.0, rotation=0.0,
        pad_nets=pad_nets, mod_path=mod, sheet="power")
    return PcbModel(
        board_w=100.0, board_h=80.0, insts=[inst],
        net_numbers={"": 0, "GND": 2, "+5V": 4, "SW_X": 5},
        netclass_of={}, classes={}, placed=1, deferred=[])


def test_thermal_copper_emitters_deterministic():
    m = _mini_model()

    def build():
        seqs: dict[str, int] = {}

        def uid(kind: str) -> str:
            n = seqs.get(kind, 0)
            seqs[kind] = n + 1
            return f"uid-{kind}-{n}"

        plane = embed._gnd_plane_zone(m, uid)
        zones, vias = embed._thermal_copper_nodes(m, uid)
        return sexpr.dumps([plane] + zones + vias)

    a, b = build(), build()
    assert a == b, "zone/via emission must be byte-deterministic"


def test_mini_model_full_via_field_and_pours():
    m = _mini_model()
    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return f"uid-{kind}-{n}"

    zones, vias = embed._thermal_copper_nodes(m, uid)
    spec = THERMAL_COPPER["LM61460"]
    assert len(vias) == spec["max_vias"], \
        f"unobstructed buck must get the full field, got {len(vias)}"
    layers = sorted(str(sexpr.find(z, "layer")[1]) for z in zones)
    assert layers == ["B.Cu", "F.Cu"], layers
    for z in zones:
        assert str(sexpr.find(z, "net_name")[1]) == "GND"
        fill = sexpr.find(z, "fill")
        assert fill[1] == sexpr.Sym("yes")
    for v in vias:
        assert int(sexpr.find(v, "net")[1]) == 2


def _blocked_model(tmp_path) -> PcbModel:
    m = _mini_model()
    buck = m.insts[0]
    covered = THERMAL_COPPER["LM61460"]["via_sites"][:12]
    pads = "\n".join(
        f'\t(pad "{i}" smd roundrect (at {sx} {sy}) (size 0.4 0.4) '
        '(layers "F.Cu"))' for i, (sx, sy) in enumerate(covered, start=1))
    mod = tmp_path / "PadField.kicad_mod"
    mod.write_text('(footprint "PadField"\n\t(layer "F.Cu")\n' + pads + "\n)\n")
    m.insts.append(FootprintInst(
        ref="J9", value="PadField", footprint="test:PadField",
        x=buck.x, y=buck.y, rotation=0.0,
        pad_nets={str(i): (14 + i, f"ISET_{i}")
                  for i in range(1, len(covered) + 1)},
        mod_path=mod, sheet="bringup"))
    return m


def test_blocked_buck_still_seats_the_pour_credit_floor(tmp_path):
    m = _blocked_model(tmp_path)
    buck = m.insts[0]
    spec = THERMAL_COPPER["LM61460"]
    need = embed._pour_credit_need(buck.value)
    reach = max(abs(v) for site in spec["via_sites"] for v in site) + 20.0
    obstacles = embed._via_obstacles(m, buck, reach)
    curated = [(round(buck.x + sx, 3), round(buck.y + sy, 3))
               for sx, sy in spec["via_sites"]]
    survivors: list[tuple[float, float]] = []
    for vx, vy in curated:
        if embed._via_site_blocker(vx, vy, m, obstacles, survivors) is None:
            survivors.append((vx, vy))
    assert len(survivors) < need.min_vias, \
        f"scenario is not a curated-list shortfall ({len(survivors)} seats)"

    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return f"uid-{kind}-{n}"

    _zones, vias = embed._thermal_copper_nodes(m, uid)
    seats = [(float(sexpr.find(v, "at")[1]), float(sexpr.find(v, "at")[2]))
             for v in vias]
    within = [p for p in seats
              if math.hypot(p[0] - buck.x, p[1] - buck.y) <= need.radius_mm]
    assert len(within) >= need.min_vias, \
        f"exhausted search still short: {len(within)} < {need.min_vias}"
    assert any(p not in curated for p in within), \
        "fallback lattice contributed nothing"
    for vx, vy in seats:
        assert embed._via_site_blocker(
            vx, vy, m, obstacles,
            [p for p in seats if p != (vx, vy)]) is None, \
            f"illegal seat emitted at ({vx},{vy})"


def test_fallback_sites_inside_the_pour_nearest_first():
    spec = THERMAL_COPPER["LM61460"]
    sites = embed._fallback_via_sites(spec)
    x0, y0, x1, y1 = spec["pour"]
    m = THERMAL_VIA_SIZE / 2
    for sx, sy in sites:
        assert x0 + m <= sx <= x1 - m and y0 + m <= sy <= y1 - m, (sx, sy)
    radii = [round(math.hypot(sx, sy), 4) for sx, sy in sites]
    assert radii == sorted(radii), "fallback must walk outward from the part"
    assert embed._fallback_via_sites(spec) == sites


def test_gnd_plane_zone_geometry():
    m = _mini_model()
    plane = embed._gnd_plane_zone(m, lambda k: f"uid-{k}")
    assert str(sexpr.find(plane, "layer")[1]) == "In1.Cu"
    assert str(sexpr.find(plane, "net_name")[1]) == "GND"
    pts = sexpr.find(sexpr.find(plane, "polygon"), "pts")
    xs = [float(xy[1]) for xy in pts[1:]]
    ys = [float(xy[2]) for xy in pts[1:]]
    assert min(xs) == ORIGIN_X + 0.5 and max(xs) == ORIGIN_X + 100.0 - 0.5
    assert min(ys) == ORIGIN_Y + 0.5 and max(ys) == ORIGIN_Y + 80.0 - 0.5


def test_committed_board_contains_thermal_copper():
    bc = copper_debt.scan_board(BOARD)
    assert bc.gnd_plane("In1.Cu"), "In1.Cu GND plane zone missing"
    bucks = bc.instances("LM61460")
    assert len(bucks) == 3, [f.ref for f in bucks]
    for f in bucks:
        nv = bc.gnd_vias_within(f.x, f.y, 5.2)
        assert nv >= 6, f"{f.ref}: via field short ({nv} < 6)"
        assert bc.pour_at(f.x, f.y, "F.Cu"), f"{f.ref}: no F.Cu pour"
        assert bc.pour_at(f.x, f.y, "B.Cu"), f"{f.ref}: no B.Cu pour"
    ldos = bc.instances("TLV75725")
    assert len(ldos) == 1
    assert bc.gnd_vias_within(ldos[0].x, ldos[0].y, 3.0) >= 2
    assert bc.pour_at(ldos[0].x, ldos[0].y, "F.Cu")
    voids = bc.zone_named("ethernet_isolation_void")
    assert len(voids) == 2 and all(z.keepout and "In1.Cu" in z.layers
                                   for z in voids)
    assert bc.segments == 9, bc.segments
    text = BOARD.read_text()
    import re as _re
    seg_blocks = _re.findall(r"\(segment\b.*?\n\t\)", text, _re.DOTALL)
    assert len(seg_blocks) == 9
    for sb in seg_blocks:
        assert "(locked yes)" in sb, "non-preroute segment on the foundation"


def test_committed_board_zones_unfilled_on_disk():
    import re
    txt = BOARD.read_text()
    assert "filled_polygon" not in txt
    assert re.search(r"\(fill\s+yes", txt), "fill settings must be present"


def test_copper_debt_ledger_complete_and_deterministic():
    res1 = copper_debt.analyze(BOARD)
    res2 = copper_debt.analyze(BOARD)
    rep1, rep2 = copper_debt.report(res1), copper_debt.report(res2)
    assert rep1 == rep2, "ledger must be deterministic"
    ids = [e.eid for e in res1.entries]
    assert ids == [f"CD-0{i}" for i in range(1, 9)], ids
    for e in res1.entries:
        for w in e.where:
            rel, _, line = w.rpartition(":")
            assert (REPO / rel).is_file() and line.isdigit(), f"{e.eid}: {w}"
    by = {e.eid: e for e in res1.entries}
    assert by["CD-01"].status == "EMITTED", by["CD-01"].emits
    assert by["CD-02"].status == "EMITTED", by["CD-02"].emits
    assert by["CD-03"].status == "EMITTED", by["CD-03"].emits
    assert by["CD-04"].status == "NOTHING"
    assert by["CD-05"].status == "NOTHING"
    assert by["CD-06"].status == "PARTIAL"
    assert by["CD-08"].status == "PARTIAL", by["CD-08"].emits
    assert "rail fanout vias: none emitted" in by["CD-08"].emits


def _anchor_fixture(tmp_path, monkeypatch) -> None:
    (tmp_path / "m.py").write_text(
        '"""a docstring claim."""\n# a comment claim\nANCHOR_HOME = ()\n')
    monkeypatch.setattr(copper_debt, "REPO_ROOT", tmp_path)


def test_a_dead_anchor_fails_loudly_naming_the_claim(tmp_path, monkeypatch):
    _anchor_fixture(tmp_path, monkeypatch)
    with pytest.raises(copper_debt.AnchorError) as gone:
        copper_debt._where("CD-99", "m.py", "a phrase no structure carries")
    assert "CD-99" in str(gone.value) and "no structure carries" in str(
        gone.value)
    with pytest.raises(copper_debt.AnchorError, match="CD-99"):
        copper_debt._where("CD-99", "vanished.py", "anything at all")


def test_an_anchor_may_not_bind_to_prose(tmp_path, monkeypatch):
    _anchor_fixture(tmp_path, monkeypatch)
    for prose in ("a comment claim", "a docstring claim"):
        with pytest.raises(copper_debt.AnchorError, match="PROSE"):
            copper_debt._where("CD-99", "m.py", prose)
    assert copper_debt._where("CD-99", "m.py", "ANCHOR_HOME = ()") == "m.py:3"


def test_copper_debt_unmeasured_without_board():
    res = copper_debt.analyze(None)
    assert all(e.status == "UNMEASURED" for e in res.entries)
    assert "NO BOARD SCANNED" in res.inventory
