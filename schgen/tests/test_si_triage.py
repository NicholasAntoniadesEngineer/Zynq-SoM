"""si_triage — full-population classification + fail-loud (T2 escape wave)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from schgen.verify import return_path_gate as rpg
from schgen.verify import si_triage

_REPO = Path(__file__).resolve().parents[2]


def _population() -> set[str]:
    data = json.loads((_REPO / "carrier" / "som_interface.json").read_text())
    nets: set[str] = set()
    for conn in data["connectors"].values():
        for net in conn["pins"].values():
            if rpg.classify_net(net) == "SIGNAL":
                nets.add(net)
    return nets


def test_full_population_classifies_without_raising():
    """Every SIGNAL net crossing the DF40s has a curated class (the fail-loud
    contract: an uncurated net reds the first build, so the table must stay
    complete)."""
    table = si_triage.classify_all(_population())
    assert len(table) >= 200          # 205 measured 2026-07-02; >= guards drift
    for sc in table.values():
        assert sc.klass in (si_triage.GENUINE, si_triage.MODERATE,
                            si_triage.LOW)
        assert sc.basis                # every class row carries a basis string


def test_uncurated_net_raises():
    with pytest.raises(si_triage.SiTriageError):
        si_triage.classify("TOTALLY_NOVEL_NET_NAME_42")


def test_function_map_resolves_raw_contract_names():
    """Raw IO_* contract nets resolve through the SAME wave-3 function map the
    J-sheets/XDC use — the failing TMDS halves must classify GENUINE even
    though the connector pin carries the raw Xilinx name."""
    sc = si_triage.classify("IO_L10_P_33")
    assert sc.function == "HDMI_RX_D0_P"
    assert sc.klass == si_triage.GENUINE
    sc = si_triage.classify("IO_L21_DQS_P_33")
    assert sc.function == "ZYNQ_HDMI_TX_TMDS_CLK_P"
    assert sc.klass == si_triage.GENUINE


def test_failing_set_class_tally():
    """The 29 v1-failing contacts triage to 8 GENUINE + 1 MODERATE + 20 LOW
    (measured 2026-07-02; drift here follows the v1 pinned-scalar alarm)."""
    res = rpg.check()
    tally = {"GENUINE": 0, "MODERATE": 0, "LOW": 0}
    for v in res.violations:
        tally[si_triage.classify(v.net).klass] += 1
    assert tally == {"GENUINE": 8, "MODERATE": 1, "LOW": 20}


def test_classes_are_ordering_only_not_a_waiver():
    """No gate consumes the class as an exemption: the return_stitch gate
    source must not branch its pass/fail on the triage class (grep-proof)."""
    src = (_REPO / "schgen" / "verify" / "return_stitch_gate.py").read_text()
    # the class appears in REPORT ordering only; the coverage check is
    # class-blind: assert no conditional couples klass to the bound
    for line in src.splitlines():
        if "RETURN_VIA_RADIUS_MM" in line and ("klass" in line
                                               or "GENUINE" in line):
            raise AssertionError(f"class-coupled bound: {line!r}")


def test_moderate_and_low_examples():
    assert si_triage.classify("IO_L5_P_35").function == "FMC_LA10_P"
    assert si_triage.classify("IO_L5_P_35").klass == si_triage.MODERATE
    assert si_triage.classify("IO_L16_P_13").klass == si_triage.LOW  # LCD CTP
    assert si_triage.classify("IO_L10_N_13").klass == si_triage.LOW  # raw pmod
