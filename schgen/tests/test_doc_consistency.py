from __future__ import annotations

import re
from pathlib import Path

from schgen.core.link import all_subsystem_paths, load_subsystem
from schgen.generate import power_sequence as ps
from schgen.verify import powertree
from schgen.verify.powertree import SOURCES

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "carrier" / "docs"
DESIGN_SPEC = DOCS / "DESIGN_SPEC.md"
COMPLIANCE = DOCS / "COMPLIANCE.md"

_RAIL_RE = re.compile(r"\+[A-Z0-9_]+")


def _sheets():
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


def _sheet_names() -> set[str]:
    return {p.stem for p in all_subsystem_paths()}


def _all_rail_names(res: powertree.Result) -> set[str]:
    rails: set[str] = set(SOURCES) | set(res.rails)
    for r in res.regs:
        rails.add(r.vin)
        rails.add(r.vout)
    for _s, _r, a, b in res.bridges:
        rails.update((a, b))
    return rails


def test_packet_files_present():
    assert DESIGN_SPEC.is_file(), "DESIGN_SPEC.md missing"
    assert COMPLIANCE.is_file(), "COMPLIANCE.md missing"


def test_design_spec_rail_table_rails_are_real():
    res = powertree.analyze(_sheets())
    known = _all_rail_names(res)
    text = DESIGN_SPEC.read_text()
    table_rails: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        first = line.split("|", 2)[1].strip().strip("`")
        for m in _RAIL_RE.findall(first):
            table_rails.add(m)
    assert table_rails, "no rail tokens found in DESIGN_SPEC tables"
    unknown = sorted(r for r in table_rails if r not in known)
    assert not unknown, (
        f"DESIGN_SPEC names rails the netlist does not have: {unknown}")


def test_design_spec_core_rails_documented():
    text = DESIGN_SPEC.read_text()
    for rail in ("+VIN", "+5V", "+3V3", "+1V8", "+5V_SOM", "+3V3_SC",
                 "+2V5_VADJ"):
        assert rail in text, f"DESIGN_SPEC does not mention core rail {rail}"


def test_compliance_cited_sheets_exist():
    names = _sheet_names()
    text = COMPLIANCE.read_text()
    cited: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("## ") or "sheet" not in line:
            continue
        for tok in re.findall(r"`([a-z0-9_]+)`", line):
            cited.add(tok)
    assert cited, "no sheet citations found in COMPLIANCE headers"
    unknown = sorted(t for t in cited if t not in names)
    assert not unknown, (
        f"COMPLIANCE cites sheets that do not exist: {unknown}")


def test_compliance_covers_every_required_interface():
    text = COMPLIANCE.read_text()
    for interface in ("HDMI", "Ethernet", "USB 2.0", "MIPI CSI-2",
                      "USB-PD", "bank-35 IO"):
        assert interface in text, f"COMPLIANCE missing the {interface} section"


def test_power_sequence_partitions_every_regulator():
    sheets = _sheets()
    res = powertree.analyze(sheets)
    seq = ps.build(sheets, res)
    placed = list(seq["stage0"])
    placed += [r["vout"] for r in seq["chain"]]
    placed += [r["vout"] for r in seq["modules"]]
    for reg in res.regs:
        assert reg.vout in placed, (
            f"power-sequence drops regulator output {reg.vout}")
    chain_vouts = {r["vout"] for r in seq["chain"]}
    for reg in res.regs:
        if reg.kind == "load_switch":
            assert reg.vout not in seq["stage0"], (
                f"{reg.vout} is a load switch but sits in stage-0")
            assert reg.vout not in chain_vouts, (
                f"{reg.vout} is a load switch but sits in the rail chain")
    for src in SOURCES:
        assert src in seq["stage0"], f"source {src} not in stage-0"


def test_power_sequence_build_is_deterministic():
    sheets = _sheets()
    a = ps.build(sheets)
    b = ps.build(sheets)
    assert a["stage0"] == b["stage0"]
    assert [r["vout"] for r in a["chain"]] == [r["vout"] for r in b["chain"]]
    assert [r["vout"] for r in a["modules"]] == [r["vout"] for r in b["modules"]]


def test_power_sequence_svg_byte_deterministic(tmp_path):
    sheets = _sheets()
    res = powertree.analyze(sheets)
    p1 = ps.generate(sheets, res, out=tmp_path / "a.svg")
    p2 = ps.generate(sheets, res, out=tmp_path / "b.svg")
    assert p1.read_bytes() == p2.read_bytes()
    import xml.dom.minidom
    xml.dom.minidom.parseString(p1.read_text())
    assert p1.read_text().count("<rect") >= len(res.regs)


def test_design_spec_references_the_three_diagrams():
    text = DESIGN_SPEC.read_text()
    for art in ("block_diagram.svg", "power_tree.svg", "power_sequence.svg"):
        assert art in text, f"DESIGN_SPEC does not reference {art}"
