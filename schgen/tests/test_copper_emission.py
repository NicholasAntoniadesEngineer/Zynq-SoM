"""Tests for the EMITTED thermal copper (GAP1) + the copper-debt ledger.

Three locks:
  1. the zone/via emitters are DETERMINISTIC (same model -> byte-identical
     s-expressions) and the zones are emitted UNFILLED-with-fill-settings
     (no fill polygons on disk — the build-twice byte-identity choice; DRC
     refills in memory via --refill-zones);
  2. the COMMITTED board actually CONTAINS the copper the thermal gate
     credits (In1 GND plane, per-buck via fields + local pours, ethernet
     isolation voids) — scanned from the .kicad_pcb, never the model;
  3. the copper-debt ledger is complete (CD-01..CD-08), anchor-resolved and
     deterministic.

Pure/offline: the emitters run on a tiny synthetic model (no placer, no
kicad-cli); the board checks parse the committed file.
"""

from __future__ import annotations

from pathlib import Path

from schgen.core import sexpr
from schgen.generate.pcb import embed
from schgen.generate.pcb.constants import (
    ORIGIN_X,
    ORIGIN_Y,
    THERMAL_COPPER,
    FootprintInst,
    PcbModel,
)
from schgen.verify import copper_debt

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "carrier" / "Zynq_Carrier.kicad_pcb"


# ---- synthetic single-buck model --------------------------------------------------

def _mini_model() -> PcbModel:
    """One LM61460 alone on a 100x80 board — every primary via site is
    unobstructed, so the emitter must place the full max_vias field."""
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
    # every zone: net GND, fill settings ON, no fill polygons
    for z in zones:
        assert str(sexpr.find(z, "net_name")[1]) == "GND"
        fill = sexpr.find(z, "fill")
        assert fill[1] == sexpr.Sym("yes")
    # every via: net 2 (GND), inside the F.Cu pour bbox
    for v in vias:
        assert int(sexpr.find(v, "net")[1]) == 2


def test_gnd_plane_zone_geometry():
    m = _mini_model()
    plane = embed._gnd_plane_zone(m, lambda k: f"uid-{k}")
    assert str(sexpr.find(plane, "layer")[1]) == "In1.Cu"
    assert str(sexpr.find(plane, "net_name")[1]) == "GND"
    pts = sexpr.find(sexpr.find(plane, "polygon"), "pts")
    xs = [float(xy[1]) for xy in pts[1:]]
    ys = [float(xy[2]) for xy in pts[1:]]
    # inset 0.5 from Edge.Cuts on all sides
    assert min(xs) == ORIGIN_X + 0.5 and max(xs) == ORIGIN_X + 100.0 - 0.5
    assert min(ys) == ORIGIN_Y + 0.5 and max(ys) == ORIGIN_Y + 80.0 - 0.5


# ---- the COMMITTED board carries the credited copper ------------------------------

def test_committed_board_contains_thermal_copper():
    """The copper the thermal gate credits must be IN the committed board
    file: In1 GND plane, >=6-via field + F/B pours per LM61460, >=2 vias +
    F pour at the DYD LDO. This is the same scan the gate itself runs."""
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
    # ethernet isolation: the plane is VOIDED under the magnetics + RJ45
    voids = bc.zone_named("ethernet_isolation_void")
    assert len(voids) == 2 and all(z.keepout and "In1.Cu" in z.layers
                                   for z in voids)
    # still an UNROUTED foundation — the ONLY track segments are the T2
    # escape-wave GND return ladder (locked Freerouting preroute: spines +
    # GND-pad stubs under the DF40s; re-pinned at the T2xGAP1 reconciliation,
    # base 28f8e15). Any OTHER segment would be a stray route.
    assert bc.segments == 10, bc.segments
    text = BOARD.read_text()
    import re as _re
    seg_blocks = _re.findall(r"\(segment\b.*?\n\t\)", text, _re.DOTALL)
    assert len(seg_blocks) == 10
    for sb in seg_blocks:
        assert "(locked yes)" in sb, "non-preroute segment on the foundation"


def test_committed_board_zones_unfilled_on_disk():
    """DETERMINISM CHOICE (documented): zones carry (fill yes ...) settings
    but NO computed fill polygons on disk — kicad-cli DRC refills in memory
    (--refill-zones), so build-twice byte-identity and meaningful DRC hold
    simultaneously. A filled_polygon appearing on disk means someone saved a
    refilled board over the emitted one."""
    import re
    txt = BOARD.read_text()
    assert "filled_polygon" not in txt
    assert re.search(r"\(fill\s+yes", txt), "fill settings must be present"


# ---- the copper-debt ledger --------------------------------------------------------

def test_copper_debt_ledger_complete_and_deterministic():
    res1 = copper_debt.analyze(BOARD)
    res2 = copper_debt.analyze(BOARD)
    rep1, rep2 = copper_debt.report(res1), copper_debt.report(res2)
    assert rep1 == rep2, "ledger must be deterministic"
    ids = [e.eid for e in res1.entries]
    assert ids == [f"CD-0{i}" for i in range(1, 9)], ids
    # anchors must RESOLVE (a moved basis string is a loud ledger defect).
    # Checked on the entries' WHERE fields — the report HEADER legitimately
    # mentions the ANCHOR-NOT-FOUND marker in its own explanation.
    for e in res1.entries:
        for w in e.where:
            assert "ANCHOR-NOT-FOUND" not in w and "FILE-MISSING" not in w, \
                f"{e.eid}: unresolved anchor {w}"
    by = {e.eid: e for e in res1.entries}
    # the CRITICAL thermal entries are EMITTED on the committed board
    assert by["CD-01"].status == "EMITTED", by["CD-01"].emits
    assert by["CD-02"].status == "EMITTED", by["CD-02"].emits
    assert by["CD-03"].status == "EMITTED", by["CD-03"].emits
    # honest debt stays visible: chassis bond / Bob-Smith are NOT emitted;
    # the ethernet moat is PARTIAL (bodies voided, corridor not); the SoM
    # fanout moved NOTHING -> PARTIAL at the T2 reconciliation (the 8 escape
    # GND stitch vias land under the SoM body; the RAIL fanout vias are still
    # debt — the ledger text says so)
    assert by["CD-04"].status == "NOTHING"
    assert by["CD-05"].status == "NOTHING"
    assert by["CD-06"].status == "PARTIAL"
    assert by["CD-08"].status == "PARTIAL", by["CD-08"].emits
    assert "rail fanout vias: none emitted" in by["CD-08"].emits


def test_copper_debt_unmeasured_without_board():
    res = copper_debt.analyze(None)
    assert all(e.status == "UNMEASURED" for e in res.entries)
    assert "NO BOARD SCANNED" in res.inventory
