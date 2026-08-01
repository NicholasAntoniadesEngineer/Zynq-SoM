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
    table = si_triage.classify_all(_population())
    assert len(table) >= 200
    for sc in table.values():
        assert sc.klass in (si_triage.GENUINE, si_triage.MODERATE,
                            si_triage.LOW)
        assert sc.basis


def test_uncurated_net_raises():
    with pytest.raises(si_triage.SiTriageError):
        si_triage.classify("TOTALLY_NOVEL_NET_NAME_42")


def test_function_map_resolves_raw_contract_names():
    sc = si_triage.classify("IO_L10_P_33")
    assert sc.function == "HDMI_RX_D0_P"
    assert sc.klass == si_triage.GENUINE
    sc = si_triage.classify("IO_L21_DQS_P_33")
    assert sc.function == "ZYNQ_HDMI_TX_TMDS_CLK_P"
    assert sc.klass == si_triage.GENUINE


def test_v1_failing_contacts_triage_to_8_genuine_1_moderate_20_low():
    res = rpg.check()
    tally = {"GENUINE": 0, "MODERATE": 0, "LOW": 0}
    for v in res.violations:
        tally[si_triage.classify(v.net).klass] += 1
    assert tally == {"GENUINE": 8, "MODERATE": 1, "LOW": 20}


def test_classes_are_ordering_only_not_a_waiver():
    src = (_REPO / "schgen" / "verify" / "return_stitch_gate.py").read_text()
    for line in src.splitlines():
        if "RETURN_VIA_RADIUS_MM" in line and ("klass" in line
                                               or "GENUINE" in line):
            raise AssertionError(f"class-coupled bound: {line!r}")


def test_moderate_and_low_examples():
    assert si_triage.classify("IO_L5_P_35").function == "FMC_LA10_P"
    assert si_triage.classify("IO_L5_P_35").klass == si_triage.MODERATE
    assert si_triage.classify("IO_L16_P_13").klass == si_triage.LOW
    assert si_triage.classify("IO_L10_N_13").klass == si_triage.LOW
