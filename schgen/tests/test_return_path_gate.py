from __future__ import annotations

from schgen.verify import return_path_gate as g


def _contact(ref, pad, row, index, net):
    return g.Contact(
        ref=ref, pad=pad, row=row, index=index,
        x=index * 0.4, y=1.6 if row == 0 else -1.6,
        net=net, klass=g.classify_net(net),
    )


def _single_row_map(nets_by_index, ref="J9"):
    contacts = [
        _contact(ref, str(i + 1), 0, i, net)
        for i, net in sorted(nets_by_index.items())
    ]
    return {ref: contacts}


def test_pair_with_adjacent_gnd_passes():
    m = _single_row_map({0: "GND", 1: "LVDS0_P", 2: "LVDS0_N", 3: "GND"})
    res = g.check_map(m)
    assert res.ok is True
    assert res.n_pairs == 1
    assert res.n_pair_contacts == 2
    assert res.violations == []
    assert res.worst_distance == 1
    assert res.per_conn["J9"] == (2, 0)


def test_pair_with_gnd_beyond_k_fails():
    m = _single_row_map({
        0: "LVDS0_P", 1: "LVDS0_N",
        2: "SIG_A", 3: "SIG_B", 4: "SIG_C", 5: "GND",
    })
    res = g.check_map(m)
    assert res.ok is False
    assert res.n_pairs == 1
    assert res.n_fail == 2
    fails = {v.net: v for v in res.violations}
    assert set(fails) == {"LVDS0_P", "LVDS0_N"}
    assert fails["LVDS0_P"].base == "LVDS0_*"
    assert fails["LVDS0_P"].distance == 5
    assert fails["LVDS0_N"].distance == 4
    assert "pair LVDS0" in fails["LVDS0_P"].as_line()
    assert "> K=2" in fails["LVDS0_P"].as_line()


def test_no_gnd_on_connector_reports_none():
    m = _single_row_map({0: "LVDS0_P", 1: "LVDS0_N", 2: "SIG_A"})
    res = g.check_map(m)
    assert res.ok is False
    assert res.n_fail == 2
    v = next(v for v in res.violations if v.net == "LVDS0_P")
    assert v.distance is None
    assert "none-on-connector" in v.as_line()


def test_mutation_gnd_to_signal_flips_to_fail():
    passing = _single_row_map(
        {0: "GND", 1: "LVDS0_P", 2: "LVDS0_N", 3: "GND"})
    base = g.check_map(passing)
    assert base.ok is True

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
    assert mres.ok is False
    assert mres.n_fail == 2


def test_facing_row_gnd_counts():
    p = _contact("J9", "1", 0, 0, "LVDS0_P")
    n = _contact("J9", "2", 0, 1, "LVDS0_N")
    s = _contact("J9", "3", 0, 2, "SIG_A")
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
    nets = {
        "ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N",
        "STM32_USB_D_P", "STM32_USB_D_N",
        "IO_L10_P_35", "IO_L10_N_35",
        "SOLO_P",
    }
    assert g.hs_pair_bases(nets) == ["ETH_PHY_MDI0", "STM32_USB_D"]


def test_pair_partner_both_naming_styles():
    assert g.pair_partner("ETH_PHY_MDI0_P") == "ETH_PHY_MDI0_N"
    assert g.pair_partner("ETH_PHY_MDI0_N") == "ETH_PHY_MDI0_P"
    assert g.pair_partner("IO_L10_P_13") == "IO_L10_N_13"
    assert g.pair_partner("IO_L10_N_35") == "IO_L10_P_35"
    assert g.pair_partner("IO_L11_SRCC_P_13") == "IO_L11_SRCC_N_13"
    assert g.pair_partner("IO_L14_P_SRCC_13") == "IO_L14_N_SRCC_13"
    assert g.pair_partner("IO_0_35") is None
    assert g.pair_partner("GND") is None
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
        "IO_L10_P_13", "IO_L10_N_13",
        "ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N",
        "IO_L21_P_13",
        "IO_0_35",
    }
    m = g.hs_pairs_in(nets)
    assert m == {
        "IO_L10_P_13": "IO_L10_*_13",
        "IO_L10_N_13": "IO_L10_*_13",
        "ETH_PHY_MDI0_P": "ETH_PHY_MDI0_*",
        "ETH_PHY_MDI0_N": "ETH_PHY_MDI0_*",
    }


def test_xilinx_pair_with_adjacent_gnd_passes():
    m = _single_row_map(
        {0: "GND", 1: "IO_L10_P_13", 2: "IO_L10_N_13", 3: "GND"})
    res = g.check_map(m)
    assert res.ok is True
    assert res.n_pairs == 1
    assert res.n_pair_contacts == 2
    assert res.per_conn["J9"] == (2, 0)
    assert res.pairs_per_conn["J9"] == 1


def test_xilinx_pair_with_gnd_beyond_k_fails():
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
    assert fails["IO_L11_SRCC_P_35"].distance == 5
    assert fails["IO_L11_SRCC_N_35"].distance == 4
    assert "pair IO_L11_SRCC_*_35" in fails["IO_L11_SRCC_P_35"].as_line()


def test_xilinx_mutation_break_partner_flips_to_single_ended():
    passing = _single_row_map(
        {0: "GND", 1: "IO_L10_P_13", 2: "IO_L10_N_13", 3: "GND"})
    base = g.check_map(passing)
    assert base.ok is True
    assert base.n_pairs == 1

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


def test_real_board_runs_and_is_wellformed():
    res = g.check()
    assert isinstance(res.ok, bool)
    assert res.k == g.K == 2
    assert res.connectors == ["J1", "J2", "J3"]
    assert res.n_pairs >= 1
    assert res.n_pair_contacts >= 2 * res.n_pairs - res.n_pairs
    assert res.n_fail == len(res.violations)
    assert set(res.per_conn) == {"J1", "J2", "J3"}
    total_pair_contacts = sum(pc for pc, _ in res.per_conn.values())
    assert total_pair_contacts == res.n_pair_contacts
    total_fail = sum(fc for _, fc in res.per_conn.values())
    assert total_fail == res.n_fail
    assert "RETURN-PATH GATE" in res.summary()
    assert g.check().summary() == res.summary()


def test_real_board_determinism_full():
    assert g.check().summary() == g.check().summary()


def test_real_board_pinned_scalars():
    res = g.check()
    assert res.n_pairs == 69
    assert res.n_pair_contacts == 138
    assert res.n_fail == 29
    assert res.worst_distance == 4
    per = {r: fc for r, (_pc, fc) in res.per_conn.items()}
    assert per == {"J1": 1, "J2": 28, "J3": 0}


def test_v1_is_report_only_by_design():
    from pathlib import Path
    main_src = (Path(g.__file__).resolve().parents[1].parent
                / "schgen" / "__main__.py").read_text()
    assert 'pcb_res.get("return_stitch")' in main_src
    assert "ok_all = ok_all and rsg_.ok" in main_src
    assert 'pcb_res.get("return_path")' in main_src
    assert "rp_.summary()" in main_src
    import re as _re
    for line in main_src.splitlines():
        if "ok_all" in line and "rp_" in line:
            raise AssertionError(f"v1 wired into ok_all: {line!r}")
    assert g.K == 2
    src = Path(g.__file__).read_text()
    assert _re.search(r"^K = 2$", src, _re.M)


def test_v2_gate_cross_check_matches_pins():
    from schgen.verify import return_stitch_gate as rsg
    assert rsg.V1_PINNED == {"n_pairs": 69, "n_pair_contacts": 138,
                             "n_fail": 29, "worst_distance": 4}
    res = g.check()
    live = {"n_pairs": res.n_pairs, "n_pair_contacts": res.n_pair_contacts,
            "n_fail": res.n_fail, "worst_distance": res.worst_distance}
    assert live == rsg.V1_PINNED
