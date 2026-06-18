"""Docs-can't-silently-drift guard for the design-documentation packet.

The comprehensive packet (carrier/docs/DESIGN_SPEC.md + COMPLIANCE.md + the
generated carrier/docs/power_sequence.svg) describes the board's rails,
interfaces and power-up sequence in prose. Prose rots: a rail gets renamed in
a subsystem netlist, an interface sheet is split, a regulator is re-spec'd —
and the doc still says the old thing. These tests bind the docs to the LIVE
netlist analysis so such a drift fails the regression instead of shipping.

Fully offline + deterministic (LAW: no flakiness, no duplication of existing
gates): they load the carrier subsystems (no kicad-cli, no SoM project, no
network, no /tmp) and run the same power-tree analysis the budget gate uses.
They assert RELATIONSHIPS the docs claim, never re-derive numbers (the gate
reports own those) — so they do not duplicate powertree.py / si_constraints.py.
"""

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

_RAIL_RE = re.compile(r"\+[A-Z0-9_]+")          # +3V3, +VIN_SYS, +5V_SOM, …


def _sheets():
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


def _sheet_names() -> set[str]:
    return {p.stem for p in all_subsystem_paths()}


def _all_rail_names(res: powertree.Result) -> set[str]:
    """Every rail the live power-tree analysis knows: sources, regulator vins
    and vouts, shunt-bridge endpoints, and the summed-load rail set."""
    rails: set[str] = set(SOURCES) | set(res.rails)
    for r in res.regs:
        rails.add(r.vin)
        rails.add(r.vout)
    for _s, _r, a, b in res.bridges:
        rails.update((a, b))
    return rails


# ---- the packet exists -----------------------------------------------------------

def test_packet_files_present():
    assert DESIGN_SPEC.is_file(), "DESIGN_SPEC.md missing"
    assert COMPLIANCE.is_file(), "COMPLIANCE.md missing"


# ---- DESIGN_SPEC rails are real --------------------------------------------------

def test_design_spec_rail_table_rails_are_real():
    """Every rail named in the DESIGN_SPEC §3.2 rail table must be a real rail
    in the live power-tree analysis — the spec cannot list a phantom rail."""
    res = powertree.analyze(_sheets())
    known = _all_rail_names(res)
    # §3.2 'Rail tree' table: the lines that start with '| `+RAIL`' or '| +RAIL'.
    text = DESIGN_SPEC.read_text()
    # restrict to the rail-totals table region to avoid prose false-positives:
    # the table rows are pipe-delimited and lead with a rail token.
    table_rails: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        first = line.split("|", 2)[1].strip().strip("`")
        # a cell like "+5V (+5V_REG)" -> harvest each rail token in it
        for m in _RAIL_RE.findall(first):
            table_rails.add(m)
    assert table_rails, "no rail tokens found in DESIGN_SPEC tables"
    unknown = sorted(r for r in table_rails if r not in known)
    assert not unknown, (
        f"DESIGN_SPEC names rails the netlist does not have: {unknown}")


def test_design_spec_core_rails_documented():
    """The load-bearing rails MUST appear in the spec (so a rail can't quietly
    vanish from the doc). These are stable design anchors."""
    text = DESIGN_SPEC.read_text()
    for rail in ("+VIN", "+5V", "+3V3", "+1V8", "+5V_SOM", "+3V3_SC",
                 "+2V5_VADJ"):
        assert rail in text, f"DESIGN_SPEC does not mention core rail {rail}"


# ---- COMPLIANCE interfaces map to real sheets ------------------------------------

def test_compliance_cited_sheets_exist():
    """Every backticked sheet name in a COMPLIANCE interface header line must be
    a real carrier subsystem — an interface can't cite a sheet that was renamed
    or removed."""
    names = _sheet_names()
    text = COMPLIANCE.read_text()
    cited: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("## ") or "sheet" not in line:
            continue
        # header e.g. "## 3. Gigabit Ethernet 1000BASE-T — sheets `ethernet`, `rj45_connector`"
        for tok in re.findall(r"`([a-z0-9_]+)`", line):
            cited.add(tok)
    assert cited, "no sheet citations found in COMPLIANCE headers"
    unknown = sorted(t for t in cited if t not in names)
    assert not unknown, (
        f"COMPLIANCE cites sheets that do not exist: {unknown}")


def test_compliance_covers_every_required_interface():
    """The packet was commissioned to cover these interfaces; each must have a
    section so coverage can't silently shrink."""
    text = COMPLIANCE.read_text()
    for interface in ("HDMI", "Ethernet", "USB 2.0", "MIPI CSI-2",
                      "USB-PD", "bank-35 IO"):
        assert interface in text, f"COMPLIANCE missing the {interface} section"


# ---- power-up sequence diagram: deterministic + covers every regulator -----------

def test_power_sequence_partitions_every_regulator():
    """Every regulator's output rail lands in EXACTLY ONE of the three stages
    (stage-0 always-on / chain / gated module) — the diagram cannot drop or
    double-count a rail relative to the power tree."""
    sheets = _sheets()
    res = powertree.analyze(sheets)
    seq = ps.build(sheets, res)
    placed = list(seq["stage0"])  # rail names
    placed += [r["vout"] for r in seq["chain"]]
    placed += [r["vout"] for r in seq["modules"]]
    # every regulator vout is represented
    for reg in res.regs:
        assert reg.vout in placed, (
            f"power-sequence drops regulator output {reg.vout}")
    # load_switch rails are ALWAYS in the module column, never stage-0/chain
    chain_vouts = {r["vout"] for r in seq["chain"]}
    for reg in res.regs:
        if reg.kind == "load_switch":
            assert reg.vout not in seq["stage0"], (
                f"{reg.vout} is a load switch but sits in stage-0")
            assert reg.vout not in chain_vouts, (
                f"{reg.vout} is a load switch but sits in the rail chain")
    # the sources are stage-0 by construction
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
    """Re-rendering the SVG with the same inputs is byte-identical (no
    timestamps / no set-iteration leak into output)."""
    sheets = _sheets()
    res = powertree.analyze(sheets)
    p1 = ps.generate(sheets, res, out=tmp_path / "a.svg")
    p2 = ps.generate(sheets, res, out=tmp_path / "b.svg")
    assert p1.read_bytes() == p2.read_bytes()
    # well-formed XML + a non-trivial drawing
    import xml.dom.minidom
    xml.dom.minidom.parseString(p1.read_text())
    assert p1.read_text().count("<rect") >= len(res.regs)


def test_design_spec_references_the_three_diagrams():
    """The spec's diagram table must name all three generated diagrams so the
    doc and the generators stay in lockstep."""
    text = DESIGN_SPEC.read_text()
    for art in ("block_diagram.svg", "power_tree.svg", "power_sequence.svg"):
        assert art in text, f"DESIGN_SPEC does not reference {art}"
