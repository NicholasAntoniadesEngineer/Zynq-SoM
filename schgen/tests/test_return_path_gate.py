"""Tests for the HS-pair return-path gate (schgen/verify/return_path_gate.py).

Unit tests drive SYNTHETIC contact maps (no repo data) to prove the gate's
logic and its seeded-defect kill, in the discipline of
``test_pcb_gate_mutation.py``: a baseline map PASSES, then a mutated map with the
defect class injected FAILS (a gate that always fires would prove nothing).

One integration test loads the REAL ``carrier/som_interface.json`` + footprint
and asserts only that the gate RUNS and returns a well-formed result. The real
board's verdict is a FINDING, not a fixture, so it is deliberately not asserted
pass/fail here.
"""

from __future__ import annotations

from schgen.verify import return_path_gate as g


def _contact(ref, pad, row, index, net):
    """A synthetic contact placed on a regular 0.4 mm-pitch two-row grid.

    Row 0 sits at Y=+1.6, row 1 at Y=-1.6; along-row index maps to X so the
    geometry-based facing/neighbour logic behaves exactly as on the real part."""
    return g.Contact(
        ref=ref, pad=pad, row=row, index=index,
        x=index * 0.4, y=1.6 if row == 0 else -1.6,
        net=net, klass=g.classify_net(net),
    )


def _single_row_map(nets_by_index, ref="J9"):
    """A one-row connector: {along_index: net} -> {ref: [Contact,...]}."""
    contacts = [
        _contact(ref, str(i + 1), 0, i, net)
        for i, net in sorted(nets_by_index.items())
    ]
    return {ref: contacts}


# ---------------------------------------------------------------------------
# (a) a pair with GND adjacent -> PASSES
# ---------------------------------------------------------------------------
def test_pair_with_adjacent_gnd_passes():
    # layout (along-row index): GND, P, N, GND  -> both rails have GND at dist 1
    m = _single_row_map({0: "GND", 1: "LVDS0_P", 2: "LVDS0_N", 3: "GND"})
    res = g.check_map(m)
    assert res.ok is True
    assert res.n_pairs == 1
    assert res.n_pair_contacts == 2
    assert res.violations == []
    assert res.worst_distance == 1
    assert res.per_conn["J9"] == (2, 0)


# ---------------------------------------------------------------------------
# (b) nearest GND at distance K+1 -> FAILS, naming the pair and the distance
# ---------------------------------------------------------------------------
def test_pair_with_gnd_beyond_k_fails():
    # P, N, then three signals, then the only GND -> nearest GND is K+1 away.
    # index:  0        1        2   3   4   5
    #         P        N        S   S   S   GND
    # For the P at index 0 the nearest GND is at index 5 => distance 5 > K=2.
    m = _single_row_map({
        0: "LVDS0_P", 1: "LVDS0_N",
        2: "SIG_A", 3: "SIG_B", 4: "SIG_C", 5: "GND",
    })
    res = g.check_map(m)
    assert res.ok is False
    assert res.n_pairs == 1
    # both P and N are exposed (no GND within K of either)
    assert res.n_fail == 2
    fails = {v.net: v for v in res.violations}
    assert set(fails) == {"LVDS0_P", "LVDS0_N"}
    # the failure names the pair (position-independent '*' base) and reports the
    # (whole-connector) GND distance
    assert fails["LVDS0_P"].base == "LVDS0_*"
    assert fails["LVDS0_P"].distance == 5      # index 0 -> GND at index 5
    assert fails["LVDS0_N"].distance == 4      # index 1 -> GND at index 5
    assert "pair LVDS0" in fails["LVDS0_P"].as_line()
    assert "> K=2" in fails["LVDS0_P"].as_line()


def test_no_gnd_on_connector_reports_none():
    # a pair whose connector has NO ground at all -> distance None, still a fail
    m = _single_row_map({0: "LVDS0_P", 1: "LVDS0_N", 2: "SIG_A"})
    res = g.check_map(m)
    assert res.ok is False
    assert res.n_fail == 2
    v = next(v for v in res.violations if v.net == "LVDS0_P")
    assert v.distance is None
    assert "none-on-connector" in v.as_line()


# ---------------------------------------------------------------------------
# (c) mutation-style: take the PASSING map, reclassify its GND to SIGNAL,
#     the gate must FLIP to fail (seeded-defect kill, LAW-4 discipline).
# ---------------------------------------------------------------------------
def test_mutation_gnd_to_signal_flips_to_fail():
    # BASELINE: the same adjacent-GND layout that passes in test (a).
    passing = _single_row_map(
        {0: "GND", 1: "LVDS0_P", 2: "LVDS0_N", 3: "GND"})
    base = g.check_map(passing)
    assert base.ok is True                      # baseline sanity

    # MUTANT: reclassify every GND net to a plain signal (rename it so
    # classify_net no longer sees ground). The pair now has no ground anywhere.
    mutated = {
        ref: [
            g.Contact(ref=c.ref, pad=c.pad, row=c.row, index=c.index,
                      x=c.x, y=c.y,
                      net=("SIG_MUT" if c.klass == "GND" else c.net),
                      klass=("SIGNAL" if c.klass == "GND"
                             else c.klass))
            for c in contacts
        ]
        for ref, contacts in passing.items()
    }
    mres = g.check_map(mutated)
    assert mres.ok is False                     # mutant is killed
    assert mres.n_fail == 2                      # both P and N now exposed


def test_facing_row_gnd_counts():
    # A pair on row 0 with NO in-row ground but a GND directly FACING one rail
    # on row 1 must PASS (the facing-row neighbourhood carries the return).
    p = _contact("J9", "1", 0, 0, "LVDS0_P")
    n = _contact("J9", "2", 0, 1, "LVDS0_N")
    s = _contact("J9", "3", 0, 2, "SIG_A")
    # facing row: a GND at the same along-row index as P (physically across it)
    fg = _contact("J9", "4", 1, 0, "GND")
    res = g.check_map({"J9": [p, n, s, fg]})
    assert res.ok is True
    assert res.n_pair_contacts == 2


def test_classify_net():
    assert g.classify_net("GND") == "GND"
    assert g.classify_net("AGND") == "GND"
    assert g.classify_net("PS_MGTAVCC_GND") == "GND"
    assert g.classify_net("+3V3") == "POWER"
    assert g.classify_net("+1V8") == "POWER"
    assert g.classify_net("VCCO_35") == "POWER"
    assert g.classify_net("VDD_CORE") == "POWER"
    assert g.classify_net("ETH_PHY_MDI0_P") == "SIGNAL"


def test_hs_pair_bases_only_exact_pn_suffix():
    # hs_pair_bases is the NARROW suffix-only helper (kept for its stable
    # contract). It deliberately ignores mid-name Xilinx P/N; the full gate uses
    # pair_partner()/hs_pairs_in() for that (see the tests below).
    nets = {
        "ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N",
        "STM32_USB_D_P", "STM32_USB_D_N",
        # mid-name Xilinx IO is NOT a _P/_N suffix, so this narrow helper skips it
        "IO_L10_P_35", "IO_L10_N_35",
        # an unpaired rail must NOT appear
        "SOLO_P",
    }
    assert g.hs_pair_bases(nets) == ["ETH_PHY_MDI0", "STM32_USB_D"]


# ---------------------------------------------------------------------------
# Xilinx MID-NAME P/N pair detection (the defect this change closes)
# ---------------------------------------------------------------------------
def test_pair_partner_both_naming_styles():
    # suffix style
    assert g.pair_partner("ETH_PHY_MDI0_P") == "ETH_PHY_MDI0_N"
    assert g.pair_partner("ETH_PHY_MDI0_N") == "ETH_PHY_MDI0_P"
    # Xilinx: P/N token before the bank suffix
    assert g.pair_partner("IO_L10_P_13") == "IO_L10_N_13"
    assert g.pair_partner("IO_L10_N_35") == "IO_L10_P_35"
    # Xilinx SRCC/MRCC variant: P/N after the clock-capability token
    assert g.pair_partner("IO_L11_SRCC_P_13") == "IO_L11_SRCC_N_13"
    # Xilinx VREF/SRCC variant: P/N before the capability token
    assert g.pair_partner("IO_L14_P_SRCC_13") == "IO_L14_N_SRCC_13"
    # no P/N token -> no partner
    assert g.pair_partner("IO_0_35") is None
    assert g.pair_partner("GND") is None
    # more than one P/N token is ambiguous -> refuse to guess (conservative)
    assert g.pair_partner("IO_LP_N_P") is None


def test_pair_base_is_position_independent_and_shared():
    b1 = g.pair_base("IO_L10_P_13", "IO_L10_N_13")
    b2 = g.pair_base("IO_L10_N_13", "IO_L10_P_13")
    assert b1 == b2 == "IO_L10_*_13"
    assert g.pair_base("ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N") == "ETH_PHY_MDI0_*"
    assert g.pair_base("IO_L14_P_SRCC_13",
                       "IO_L14_N_SRCC_13") == "IO_L14_*_SRCC_13"


def test_hs_pairs_in_requires_both_halves():
    nets = {
        "IO_L10_P_13", "IO_L10_N_13",      # complete Xilinx pair
        "ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N",  # complete suffix pair
        "IO_L21_P_13",                       # half-pair (partner absent) -> single
        "IO_0_35",                           # single-ended, no P/N token
    }
    m = g.hs_pairs_in(nets)
    assert m == {
        "IO_L10_P_13": "IO_L10_*_13",
        "IO_L10_N_13": "IO_L10_*_13",
        "ETH_PHY_MDI0_P": "ETH_PHY_MDI0_*",
        "ETH_PHY_MDI0_N": "ETH_PHY_MDI0_*",
    }


def test_xilinx_pair_with_adjacent_gnd_passes():
    # Xilinx mid-name pair with GND on both sides -> PASSES, counted as 1 pair.
    m = _single_row_map(
        {0: "GND", 1: "IO_L10_P_13", 2: "IO_L10_N_13", 3: "GND"})
    res = g.check_map(m)
    assert res.ok is True
    assert res.n_pairs == 1
    assert res.n_pair_contacts == 2
    assert res.per_conn["J9"] == (2, 0)
    assert res.pairs_per_conn["J9"] == 1


def test_xilinx_pair_with_gnd_beyond_k_fails():
    # Xilinx pair, three signals, then the only GND -> nearest GND is K+1 away.
    m = _single_row_map({
        0: "IO_L11_SRCC_P_35", 1: "IO_L11_SRCC_N_35",
        2: "SIG_A", 3: "SIG_B", 4: "SIG_C", 5: "GND",
    })
    res = g.check_map(m)
    assert res.ok is False
    assert res.n_pairs == 1
    assert res.n_fail == 2
    fails = {v.net: v for v in res.violations}
    assert set(fails) == {"IO_L11_SRCC_P_35", "IO_L11_SRCC_N_35"}
    assert fails["IO_L11_SRCC_P_35"].base == "IO_L11_SRCC_*_35"
    assert fails["IO_L11_SRCC_P_35"].distance == 5   # index 0 -> GND at index 5
    assert fails["IO_L11_SRCC_N_35"].distance == 4   # index 1 -> GND at index 5
    assert "pair IO_L11_SRCC_*_35" in fails["IO_L11_SRCC_P_35"].as_line()


def test_xilinx_mutation_break_partner_flips_to_single_ended():
    # BASELINE: a Xilinx pair with adjacent GND passes and counts as a pair.
    passing = _single_row_map(
        {0: "GND", 1: "IO_L10_P_13", 2: "IO_L10_N_13", 3: "GND"})
    base = g.check_map(passing)
    assert base.ok is True
    assert base.n_pairs == 1

    # MUTANT: rename the N half so the P/N token no longer flips to an existing
    # net. The gate must stop seeing a pair (0 pairs, 0 pair-contacts) — this is
    # the exact defect the fix closes, in reverse: mis-detecting the pair as
    # single-ended silently drops it from the return-path check.
    mutated = {
        ref: [
            g.Contact(ref=c.ref, pad=c.pad, row=c.row, index=c.index,
                      x=c.x, y=c.y,
                      net=("IO_L10_X_13" if c.net == "IO_L10_N_13" else c.net),
                      klass=c.klass)
            for c in contacts
        ]
        for ref, contacts in passing.items()
    }
    mres = g.check_map(mutated)
    assert mres.n_pairs == 0
    assert mres.n_pair_contacts == 0
    assert mres.pairs_per_conn["J9"] == 0


def test_pair_requires_same_connector():
    # P on J1, N on J2 -> NOT a pair (a pair needs both halves on ONE connector).
    p_on_j1 = _contact("J1", "1", 0, 0, "IO_L10_P_13")
    gnd_j1 = _contact("J1", "2", 0, 1, "GND")
    n_on_j2 = _contact("J2", "1", 0, 0, "IO_L10_N_13")
    gnd_j2 = _contact("J2", "2", 0, 1, "GND")
    res = g.check_map({"J1": [p_on_j1, gnd_j1], "J2": [n_on_j2, gnd_j2]})
    assert res.n_pairs == 0
    assert res.n_pair_contacts == 0
    assert res.pairs_per_conn["J1"] == 0
    assert res.pairs_per_conn["J2"] == 0


def test_determinism_synthetic():
    m = _single_row_map(
        {0: "GND", 1: "LVDS0_P", 2: "LVDS0_N", 3: "GND"})
    assert g.check_map(m).summary() == g.check_map(m).summary()


# ---------------------------------------------------------------------------
# integration: REAL interface + footprint. Assert it RUNS and is well-formed;
# do NOT assert pass/fail (the real verdict is a finding, not a fixture).
# ---------------------------------------------------------------------------
def test_real_board_runs_and_is_wellformed():
    res = g.check()
    assert isinstance(res.ok, bool)
    assert res.k == g.K == 2
    # the SoM crosses exactly three DF40 mezzanine connectors
    assert res.connectors == ["J1", "J2", "J3"]
    # at least one HS pair crosses the DF40s (Ethernet MDI + USB)
    assert res.n_pairs >= 1
    # every pair contributes contacts; each is either OK or a named violation
    assert res.n_pair_contacts >= 2 * res.n_pairs - res.n_pairs  # >= 1 per pair
    assert res.n_fail == len(res.violations)
    # per-connector tallies cover all three connectors
    assert set(res.per_conn) == {"J1", "J2", "J3"}
    total_pair_contacts = sum(pc for pc, _ in res.per_conn.values())
    assert total_pair_contacts == res.n_pair_contacts
    total_fail = sum(fc for _, fc in res.per_conn.values())
    assert total_fail == res.n_fail
    # summary renders and is deterministic
    assert "RETURN-PATH GATE" in res.summary()
    assert g.check().summary() == res.summary()


def test_real_board_determinism_full():
    assert g.check().summary() == g.check().summary()
