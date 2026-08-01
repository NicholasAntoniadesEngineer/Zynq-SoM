from __future__ import annotations

from schgen.core.link import all_subsystem_paths, load_subsystem
from schgen.generate import si_constraints as si


def _sheets():
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


def test_si_spec_loads_37_pairs():
    spec = si.load_si_spec()
    assert len(spec) == 37
    keys = [(s.interface, s.net_p) for s in spec]
    assert keys == sorted(keys)
    assert all(s.spec_cite.strip() for s in spec)


def test_si_spec_impedances_are_sane():
    spec = si.load_si_spec()
    for s in spec:
        assert s.z_diff_ohm in (90, 100), f"{s.net_p}: Z={s.z_diff_ohm}"
        assert s.intra_pair_skew_mil > 0 and s.match_tol_mil > 0


def test_declared_pairs_harvested_from_typed_ports():
    decl = si.declared_pairs(_sheets())
    assert len(decl) == 37
    assert frozenset(("ZYNQ_HDMI_TX_TMDS_CLK_P",
                      "ZYNQ_HDMI_TX_TMDS_CLK_N")) in decl


def test_every_declared_pair_has_a_spec_row():
    model = si.build_model(_sheets())
    v = si.check(model)
    assert v.ok, v.summary()
    assert v.n_pairs == 37
    assert not v.uncovered
    assert not model.missing_in_spec


def test_length_groups_bucket_by_interface():
    model = si.build_model(_sheets())
    gids = {g.gid for g in model.groups}
    tx = next(g for g in model.groups
              if g.gid == si.group_id("HDMI TX (TMDS, source)"))
    assert len(tx.members) == 4
    assert tx.tol_mil == min(m.match_tol_mil for m in tx.members)
    assert len(gids) == len(model.groups)


def test_dru_rules_cover_every_pair_and_group():
    model = si.build_model(_sheets())
    text = "\n".join(si._dru_rules(model))
    for p in model.pairs:
        assert f'intra_skew_{si._safe(p.net_p)}' in text
        assert p.spec_cite[:20] in text
    for g in model.groups:
        assert f'lenmatch_{g.gid}' in text
    assert "constraint skew" in text
    assert "constraint length" not in text


def test_md_table_lists_every_pair():
    model = si.build_model(_sheets())
    md = si._md(model)
    assert md.count("|") > 0
    for p in model.pairs:
        assert f"`{p.net_p}`" in md and f"`{p.net_n}`" in md
    assert "37 differential pairs" in md


def test_append_dru_is_idempotent(tmp_path):
    model = si.build_model(_sheets())
    dru = tmp_path / "x.kicad_dru"
    dru.write_text("(version 1)\n\n(rule \"base\"\n)\n")
    si.append_dru(model, dru)
    once = dru.read_text()
    si.append_dru(model, dru)
    twice = dru.read_text()
    assert once == twice
    assert '(rule "base"' in twice
    assert once.count(si._SI_BANNER) == 1


def test_build_model_is_deterministic():
    a = si.build_model(_sheets())
    b = si.build_model(_sheets())
    assert [p.net_p for p in a.pairs] == [p.net_p for p in b.pairs]
    assert [g.gid for g in a.groups] == [g.gid for g in b.groups]
