from __future__ import annotations

import ast
import csv
import json
import re

import pytest

from schgen.core import quantize as q
from schgen.core import si_spec
from schgen.core.link import all_subsystem_paths, load_subsystem
from schgen.core.model import PAIR_KINDS
from schgen.generate import constraints as cst
from schgen.generate import si_constraints as si

MM_PER_MIL = 0.0254

FMC_LPC_MIL, FMC_LPC_MM = 5, 0.127
MIPI_CSI2_MIL, MIPI_CSI2_MM = 20, 0.508
BASE_T_MDI_MIL, BASE_T_MDI_MM = 50, 1.27
HDMI_TMDS_MIL, HDMI_TMDS_MM = 118, 2.9972
USB_HS_MIL, USB_HS_MM = 150, 3.81

HDMI_CTS_BIT_PERIOD_FRACTION = 0.15

JLC_90R_TRACE_MIL = 10.28
JLC_100R_TRACE_MIL = 8.08
SD_BUS_POLICY_MM = 2.5

EMITTED_PAIR_ROWS = 148

CITED = [
    ("FMC_CLK0_M2C_P", FMC_LPC_MIL, FMC_LPC_MM, "VITA 57.1"),
    ("FMC_LA11_N", FMC_LPC_MIL, FMC_LPC_MM, "VITA 57.1"),
    ("CAM_CLK_P", MIPI_CSI2_MIL, MIPI_CSI2_MM, "D-PHY"),
    ("CAM_D1_N", MIPI_CSI2_MIL, MIPI_CSI2_MM, "D-PHY"),
    ("ETH_PHY_MDI0_P", BASE_T_MDI_MIL, BASE_T_MDI_MM, "802.3"),
    ("ETH_LINE_MDI_3_N", BASE_T_MDI_MIL, BASE_T_MDI_MM, "802.3"),
    ("HDMI_RX_D2_P", HDMI_TMDS_MIL, HDMI_TMDS_MM, "HDMI 1.4b"),
    ("ZYNQ_HDMI_TX_TMDS_CLK_N", HDMI_TMDS_MIL, HDMI_TMDS_MM, "HDMI 1.4b"),
    ("USB_D+", USB_HS_MIL, USB_HS_MM, "USB 2.0"),
    ("DBG_USB_DM", USB_HS_MIL, USB_HS_MM, "USB-IF"),
]


def _sheets():
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


def _float_literals(path) -> set[float]:
    return {n.value for n in ast.walk(ast.parse(open(path).read()))
            if isinstance(n, ast.Constant) and isinstance(n.value, float)}


@pytest.fixture(scope="module")
def by_net():
    return si_spec.spec_by_net()


@pytest.mark.parametrize("net,mil,mm,cite", CITED)
def test_every_skew_equals_its_cited_figure(by_net, net, mil, mm, cite):
    spec = by_net[net]
    assert spec.intra_pair_skew_mil == mil
    assert spec.intra_pair_skew_mm == pytest.approx(mm)
    assert spec.intra_pair_skew_mm == pytest.approx(mil * MM_PER_MIL, abs=5e-5)
    assert cite in spec.spec_cite


def test_tmds_budget_is_a_length_not_the_dimensionless_bit_period_fraction(
        by_net):
    spec = by_net["ZYNQ_HDMI_TX_TMDS_2_P"]
    assert str(HDMI_CTS_BIT_PERIOD_FRACTION) in spec.spec_cite
    assert spec.intra_pair_skew_mm == pytest.approx(HDMI_TMDS_MM)
    assert spec.intra_pair_skew_mm > 19 * HDMI_CTS_BIT_PERIOD_FRACTION


def test_one_pair_kind_spans_three_budgets_so_no_per_kind_constant_can_hold(
        by_net):
    budgets: dict[str, set[float]] = {}
    for sc in _sheets():
        c = sc.circuit
        for net in c.nets.values():
            pt = c.port_type_of(net.name)
            if pt.kind in PAIR_KINDS and pt.pair_with:
                budgets.setdefault(pt.kind, set()).add(
                    by_net[net.name].intra_pair_skew_mm)
    assert budgets["diff_pair"] == {FMC_LPC_MM, MIPI_CSI2_MM, BASE_T_MDI_MM}
    assert budgets["tmds_pair"] == {HDMI_TMDS_MM}
    assert budgets["usb_hs_pair"] == {USB_HS_MM}


def test_constraints_module_restates_no_researched_figure():
    assert not hasattr(cst, "INTRA_PAIR_SKEW_MM")
    assert re.search(r"si_spec\.(spec_by_net|researched_pair)",
                     open(cst.__file__).read())
    assert _float_literals(cst.__file__) == {
        MM_PER_MIL, SD_BUS_POLICY_MM, JLC_90R_TRACE_MIL, JLC_100R_TRACE_MIL}


def test_sd_bus_match_is_named_for_having_no_cited_source():
    assert cst.SD_BUS_MATCH_MM_UNCITED_POLICY == SD_BUS_POLICY_MM
    assert not any(s.net_p.startswith("SD_") for s in si_spec.load_si_spec())


def test_group_tolerance_is_the_conservative_intra_pair_figure_reused():
    for s in si_spec.load_si_spec():
        assert s.match_tol_mil == s.intra_pair_skew_mil, s.net_p
    for g in si.build_model(_sheets()).groups:
        assert g.tol_mil == min(m.intra_pair_skew_mil for m in g.members)


def test_a_zero_single_ended_length_limit_is_declared_not_available():
    rows = json.loads(si_spec.SI_SPEC_PATH.read_text()).get("single_ended", [])
    for r in rows:
        assert r["max_len_mil"] > 0 or r.get("max_len_mil_note") == "n/a", r


def test_a_pair_with_no_researched_row_fails_loudly():
    with pytest.raises(KeyError, match="no row in"):
        si_spec.researched_pair("NOT_A_NET_P", "diff_pair", {})


def test_csv_tolerance_equals_the_researched_figure_for_every_net(
        tmp_path, by_net):
    cst.export(_sheets(), tmp_path)
    rows = list(csv.DictReader(open(tmp_path / "layout_constraints.csv")))
    seen = 0
    for r in rows:
        if r["kind"] not in PAIR_KINDS or not r["pair_with"]:
            continue
        seen += 1
        assert float(r["match_tolerance_mm"]) == pytest.approx(
            by_net[r["net"]].intra_pair_skew_mm)
        assert by_net[r["net"]].spec_cite in r["notes"]
    assert seen == EMITTED_PAIR_ROWS


def test_csv_dru_and_md_carry_identical_figures(tmp_path):
    sheets = _sheets()
    cst.export(sheets, tmp_path)
    model = si.build_model(sheets)
    dru = tmp_path / "board.kicad_dru"
    si.append_dru(model, dru)
    si.write_md(model, tmp_path / "SI.md")
    dru_txt, md_txt = dru.read_text(), (tmp_path / "SI.md").read_text()
    rows = list(csv.DictReader(open(tmp_path / "layout_constraints.csv")))
    csv_of = {r["net"]: r["match_tolerance_mm"] for r in rows
              if r["kind"] in PAIR_KINDS and r["pair_with"]}
    for p in model.pairs:
        mm = f"{p.intra_pair_skew_mm:g}"
        assert csv_of[p.net_p] == mm and csv_of[p.net_n] == mm
        assert f"(constraint skew (max {p.intra_pair_skew_mm}mm))" in dru_txt
        assert f"({p.intra_pair_skew_mm} mm)" in md_txt


def test_declared_impedance_never_diverges_from_the_researched_ohms():
    v = si.check(si.build_model(_sheets()))
    assert not v.z_divergent, v.summary()
    assert v.ok


def test_est_via_cost_value_never_contained_the_skew_figure():
    basis = q.REGISTRY["est_via_cost"].basis
    assert "RE-BASED on " in basis
    assert str(FMC_LPC_MM) in basis
    assert HDMI_CTS_BIT_PERIOD_FRACTION not in _float_literals(q.__file__)
    assert q.est_via_cost(True) == pytest.approx(
        2 * 2 * (q.VIA_SIZE_MM + 2 * q.VIA_CLEAR_MM)
        + 2 * q.STACK_THICKNESS_MM) == pytest.approx(7.6)
    tightest = min(s.intra_pair_skew_mm for s in si_spec.load_si_spec())
    assert q.STACK_THICKNESS_MM > 12 * tightest
