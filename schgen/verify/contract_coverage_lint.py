"""CONTRACT COVERAGE LINT (advisory) — every wired-sheet part in >=1 contract
structure or explicitly FREE.

THE SYSTEMIC FINDING (2026-07-28 placement audit): every placement defect traced
to UNGATED function passives. A part named by NO contract structure has no seat
in the stage template and no intra-zone check, so the packer sweeps it into a
boundary strip — crystal load caps landing opposite-side from their crystal,
boost trains torn apart, ILIM straps exiled from their eFuse. The remedy is an
authoring NET: every sheet part either appears in >=1 contract structure or is
declared explicitly free, and this lint reports the gap per sheet.

CLASSES (per wired sheet — ``project.json placement.wired_sheets`` — over every
ref of the subsystem circuit):

  STRUCTURED  named by >=1 contract structure: the union of the gate's typed
              ref fields (``ic``/``anchor``/``cap``/``resistor``/``inductor``/
              ``cin``/``cout``/``own_inductor``/``foreign_ic``/
              ``foreign_inductor``), the list fields (``caps``/``members``/
              ``ics``), ``min_from[].part``, and the ``roles`` keys — the SAME
              traversal ``placement_contract_gate.check`` measures and
              ``stage_templates.contract_member_brefs`` seats (roles drive the
              placer's same-side override, so a roles-listed part IS
              placement-governed).
  FREE        matched by the optional contract key ``free``: a list of
              ``{"ref": <lib ref>, "why": <one-line reason>}`` entries for
              parts that legitimately float (test points, LEDs, mounting).
              A free entry that names no sheet part, shadows a STRUCTURED ref,
              or lacks a ``why`` is surfaced as a NOTE — the channel is
              self-policing, never a silent waiver.
  UNGATED     neither — the audit's defect class. Reported with the board ref
              (same per-sheet band rename the netlist/board flow uses), the
              part value and its nets from the subsystem circuit, so an author
              can judge each part directly from the report.

ADVISORY: the build writes ``report()`` to ``reports/contract_coverage_lint.txt``
and prints ``summary_line()``; nothing fails. Flipping :data:`ENFORCE` to True
is the ONE-LINE enforcement switch — ``__main__`` folds
:attr:`CoverageLintResult.ok` (ungated == 0) into the gate verdict behind it.

Hermetic: subsystem circuits + contract dicts only — no board model, no
kicad-cli. Deterministic: sheets, refs, free entries, notes and nets are all
emitted in sorted order. No import side effects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ENFORCE = False

_REF_KEYS = ("ic", "anchor", "cap", "resistor", "inductor", "cin", "cout",
             "own_inductor", "foreign_ic", "foreign_inductor")
_REF_LIST_KEYS = ("caps", "members", "ics")
_NETS_SHOWN = 6
_UNSET = object()
_REF_RE = re.compile(r"([A-Za-z_+#]+)(\d*)")


def _ref_key(ref: str) -> tuple[str, int, str]:
    m = _REF_RE.match(ref)
    if not m:
        return (ref, 0, ref)
    return (m.group(1), int(m.group(2) or 0), ref)


def structured_lib_refs(contract: dict | None) -> frozenset[str]:
    """Every LIBRARY ref the contract's structures (or roles) name — the
    membership union described in the module docstring."""
    if not contract:
        return frozenset()
    libs: set[str] = set(contract.get("roles") or {})
    for st in contract.get("structures", []):
        for k in _REF_KEYS:
            v = st.get(k)
            if isinstance(v, str):
                libs.add(v)
        for k in _REF_LIST_KEYS:
            libs.update(st.get(k) or ())
        for mf in st.get("min_from") or []:
            p = mf.get("part") if isinstance(mf, dict) else None
            if isinstance(p, str):
                libs.add(p)
    return frozenset(libs)


def free_entries(contract: dict | None) -> tuple[dict[str, str], list[str]]:
    """(lib ref -> why, malformed-entry notes) from the optional ``free`` key."""
    out: dict[str, str] = {}
    notes: list[str] = []
    for e in (contract or {}).get("free") or []:
        if not (isinstance(e, dict) and isinstance(e.get("ref"), str)):
            notes.append(f"free entry {e!r} is not {{'ref','why'}}")
            continue
        why = str(e.get("why") or "").strip()
        if not why:
            notes.append(f"free {e['ref']}: missing 'why'")
        out[e["ref"]] = why
    return out, notes


@dataclass
class SheetCoverage:
    sheet: str
    have_contract: bool = False
    n_parts: int = 0
    structured: list[str] = field(default_factory=list)
    free_used: list[tuple[str, str]] = field(default_factory=list)
    ungated: list[tuple[str, str, str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        head = (f"{self.sheet:20} parts={self.n_parts:3}  "
                f"structured={len(self.structured):3}  "
                f"free={len(self.free_used):2}  "
                f"UNGATED={len(self.ungated):3}"
                f"{'' if self.have_contract else '  (no contract)'}")
        out = [head]
        for lib, bref, value, nets in self.ungated:
            out.append(f"    UNGATED {lib:6} -> {bref:8} {value:22} "
                       f"nets: {nets}")
        for lib, why in self.free_used:
            out.append(f"    FREE    {lib:6} — {why}")
        for n in self.notes:
            out.append(f"    NOTE    {n}")
        return out


def lint_sheet(sheet_name: str, *, circuit=None, contract=_UNSET,
               ref_map: dict[str, str] | None = None) -> SheetCoverage:
    """Classify every part of ``sheet_name`` as STRUCTURED / FREE / UNGATED.

    ``circuit`` (anything with ``.parts``/``.nets`` mappings), ``contract`` and
    ``ref_map`` (lib ref -> board ref) are injectable for hermetic tests;
    defaults load the real subsystem, discover its authored contract and derive
    the ref map from the frozen per-sheet band."""
    from schgen.verify import placement_contract_gate as _g

    if contract is _UNSET:
        contract = _g.discover_contract(sheet_name)
    if circuit is None:
        from schgen.core.link import load_subsystem
        circuit = load_subsystem(sheet_name).circuit
    if ref_map is None:
        ref_map = _g._board_refs_by_sheet(sheet_name, parts=circuit.parts)

    res = SheetCoverage(sheet=sheet_name, have_contract=contract is not None,
                        n_parts=len(circuit.parts))
    structured = structured_lib_refs(contract)
    free, notes = free_entries(contract)
    res.notes.extend(notes)

    ref_nets: dict[str, set[str]] = {}
    for net in circuit.nets.values():
        for pin in net.pins:
            ref_nets.setdefault(pin.ref, set()).add(net.name)

    free_used: set[str] = set()
    for ref in sorted(free, key=_ref_key):
        if ref not in circuit.parts:
            res.notes.append(f"free {ref!r} names no part on this sheet")
        elif ref in structured:
            res.notes.append(f"free {ref!r} is already STRUCTURED (redundant)")
        else:
            free_used.add(ref)
            res.free_used.append((ref, free[ref]))

    for ref in sorted(circuit.parts, key=_ref_key):
        if ref in structured:
            res.structured.append(ref)
        elif ref in free_used:
            continue
        else:
            nets = sorted(ref_nets.get(ref, ()))
            shown = ", ".join(nets[:_NETS_SHOWN]) or "-"
            if len(nets) > _NETS_SHOWN:
                shown += f" (+{len(nets) - _NETS_SHOWN} more)"
            part = circuit.parts[ref]
            value = str(getattr(part, "value", "") or "?")
            res.ungated.append((ref, ref_map.get(ref, "?"), value, shown))
    res.notes.sort()
    return res


@dataclass
class CoverageLintResult:
    sheets: list[SheetCoverage] = field(default_factory=list)

    @property
    def n_parts(self) -> int:
        return sum(s.n_parts for s in self.sheets)

    @property
    def n_structured(self) -> int:
        return sum(len(s.structured) for s in self.sheets)

    @property
    def n_free(self) -> int:
        return sum(len(s.free_used) for s in self.sheets)

    @property
    def n_ungated(self) -> int:
        return sum(len(s.ungated) for s in self.sheets)

    @property
    def ok(self) -> bool:
        return self.n_ungated == 0

    def summary_line(self) -> str:
        mode = "HARD" if ENFORCE else "advisory"
        return (f"CONTRACT COVERAGE LINT ({mode}): {len(self.sheets)} sheets, "
                f"{self.n_parts} parts — {self.n_structured} structured / "
                f"{self.n_free} free / {self.n_ungated} UNGATED")

    def report(self) -> str:
        out = ["CONTRACT COVERAGE LINT — every wired-sheet part in >=1 "
               "contract structure or explicitly free",
               self.summary_line(), ""]
        for s in sorted(self.sheets, key=lambda s: s.sheet):
            out.extend(s.lines())
        return "\n".join(out)


def lint_project(sheets: list[str] | None = None) -> CoverageLintResult:
    """Lint every engine-wired sheet (default: the project spec's
    ``wired_sheets``, sorted)."""
    if sheets is None:
        from schgen.core.project import spec as _spec
        sheets = sorted(_spec().wired_sheets)
    return CoverageLintResult(sheets=[lint_sheet(s) for s in sheets])
