"""Unit tests for the signal-integrity constraint layer
(schgen.generate.si_constraints) — offline + deterministic. They lock the
pieces a regression would break: the vendored si_spec parse, pair harvest from
the carrier's typed ports, the spec<->schematic join, length-match grouping,
the .kicad_dru rule + SI_CONSTRAINTS.md emission, idempotent .dru append, and
the assertion hook. No kicad-cli, no network, no /tmp.
"""

from __future__ import annotations

from schgen.core.link import all_subsystem_paths, load_subsystem
from schgen.generate import si_constraints as si


def _sheets():
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


# ---- vendored spec ---------------------------------------------------------------

def test_si_spec_loads_37_pairs():
    spec = si.load_si_spec()
    assert len(spec) == 37
    # sorted deterministically by (interface, net_p)
    keys = [(s.interface, s.net_p) for s in spec]
    assert keys == sorted(keys)
    # every row carries a non-empty standard citation (LAW: cite every target)
    assert all(s.spec_cite.strip() for s in spec)


def test_si_spec_impedances_are_sane():
    spec = si.load_si_spec()
    for s in spec:
        assert s.z_diff_ohm in (90, 100), f"{s.net_p}: Z={s.z_diff_ohm}"
        assert s.intra_pair_skew_mil > 0 and s.match_tol_mil > 0


# ---- harvest + join --------------------------------------------------------------

def test_declared_pairs_harvested_from_typed_ports():
    decl = si.declared_pairs(_sheets())
    # the carrier declares 37 diff/tmds/usb pairs
    assert len(decl) == 37
    # TMDS clock pair present, keyed order-independently
    assert frozenset(("ZYNQ_HDMI_TX_TMDS_CLK_P",
                      "ZYNQ_HDMI_TX_TMDS_CLK_N")) in decl


def test_every_declared_pair_has_a_spec_row():
    """The assertion hook's invariant: no declared pair is uncovered."""
    model = si.build_model(_sheets())
    v = si.check(model)
    assert v.ok, v.summary()
    assert v.n_pairs == 37
    assert not v.uncovered
    assert not model.missing_in_spec


# ---- length-match groups ---------------------------------------------------------

def test_length_groups_bucket_by_interface():
    model = si.build_model(_sheets())
    gids = {g.gid for g in model.groups}
    # one group per interface family; HDMI TX TMDS is one group of 4 pairs
    tx = next(g for g in model.groups
              if g.gid == si.group_id("HDMI TX (TMDS, source)"))
    assert len(tx.members) == 4          # Data0/1/2 + clock
    assert tx.tol_mil == min(m.match_tol_mil for m in tx.members)
    assert len(gids) == len(model.groups)   # gids unique


# ---- emission --------------------------------------------------------------------

def test_dru_rules_cover_every_pair_and_group():
    model = si.build_model(_sheets())
    text = "\n".join(si._dru_rules(model))
    for p in model.pairs:
        assert f'intra_skew_{si._safe(p.net_p)}' in text
        assert p.spec_cite[:20] in text          # citation embedded
    for g in model.groups:
        assert f'lenmatch_{g.gid}' in text
    # group rules use a relative skew constraint, not an absolute length max
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
    """Appending the SI block twice yields a byte-identical file (determinism +
    no rule duplication)."""
    model = si.build_model(_sheets())
    dru = tmp_path / "x.kicad_dru"
    dru.write_text("(version 1)\n\n(rule \"base\"\n)\n")
    si.append_dru(model, dru)
    once = dru.read_text()
    si.append_dru(model, dru)
    twice = dru.read_text()
    assert once == twice
    # the pre-existing base rule survives the strip-and-reappend
    assert '(rule "base"' in twice
    assert once.count(si._SI_BANNER) == 1


def test_build_model_is_deterministic():
    a = si.build_model(_sheets())
    b = si.build_model(_sheets())
    assert [p.net_p for p in a.pairs] == [p.net_p for p in b.pairs]
    assert [g.gid for g in a.groups] == [g.gid for g in b.groups]
