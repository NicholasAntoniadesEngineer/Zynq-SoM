"""schgen selftest — who watches the watchmen (PLAN.md round 4).

The project has NO CI; every guarantee rests on the gate stack (netlist
equivalence, ERC, visual zero-overlap, the strict inputs-driven check).
This command proves the gates themselves still bite, by MUTATION testing:

For each known-green sheet (default: the m1_rc smoke sheet + a real carrier
sheet) it builds the sheet, asserts the baseline is green, then injects one
defect per mutation class — into the EMITTED ``.kicad_sch`` or into the
declared circuit — and PROVES at least one gate fails ("kills") each mutant:

- ``pin_swap``        two pins exchanged between two different nets
                      (declared netlist no longer matches the drawing)
- ``wire_delete``     EVERY wire segment deleted in turn (each one must be
                      load-bearing: an open, a dangling label, or a lost
                      PWR_FLAG — something must scream)
- ``label_alias``     one net label rewritten to another net's name (the
                      classic silent merge/short of two different nets)
- ``stray_nc``        a no_connect dropped onto a pin that carries a net
                      (the historical "NC cheat" that once fooled ERC)
- ``foreign_junction``a junction placed where a bridge wire meets a FOREIGN
                      net (the LAW-0 short: junction at a crossing of two
                      different nets — ERC=0 and overlap=0 do not see it)

A mutant that survives every gate is a hole in the gate stack: selftest
prints it loudly and exits non-zero. The gates are never relaxed here —
if a mutant survives, the fix is a stronger gate, never a weaker mutant.

DETERMINISM: the same sheet is built twice from scratch (fresh module load,
fresh library) and the two ``.kicad_sch`` must be BYTE-IDENTICAL — uuids
included, with zero tolerance (emit derives every id from content via
uuid5, so even the ids must reproduce exactly). Any drift between two
builds — geometric, textual, or a single id — is a FAIL.

Run: ``PYTHONPATH=. python -m schgen selftest`` (non-zero exit on any hole).
"""

from __future__ import annotations

import argparse
import copy
import difflib
import importlib.util
import shutil
import tempfile
import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path

from schgen import place, sexpr
from schgen.emit import Junction as EJunction
from schgen.emit import PlacedDesign, Wire, emit
from schgen.model import Circuit, NetClass, PinRef
from schgen.sexpr import Sym
from schgen.symbols import GRID, Library, pin_page_position
from schgen.verify import netlist_gate, visual_gate

REPO_ROOT = Path(__file__).resolve().parents[1]

# Known-green fixtures: the engine-placed M1 smoke sheet + one real carrier
# sheet (small enough that mutating EVERY wire stays fast).
DEFAULT_SHEETS = (
    REPO_ROOT / "schgen" / "tests" / "m1_rc_sheet.py",
    REPO_ROOT / "carrier" / "subsystems" / "uart_bridge.py",
)


# ---- building a sheet (same pipeline as `schgen build`, no CLI) ---------------

@dataclass
class Built:
    circuit: Circuit
    sch: Path
    text: str
    placement: object
    routed: object
    geo: object
    lib: Library


def _load_circuit(path: Path) -> Circuit:
    spec = importlib.util.spec_from_file_location(
        f"schgen_selftest_{path.stem}_{_uuid.uuid4().hex[:8]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # type: ignore[union-attr]
    return mod.circuit()


def _build(path: Path, outdir: Path) -> Built:
    lib = Library()
    c = _load_circuit(path)
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    placement, routed, geo = place.place_and_route(c, lib)
    design = PlacedDesign(
        circuit=c, parts=placement.parts, powers=placement.powers,
        wires=[Wire(s.x0, s.y0, s.x1, s.y1) for s in routed.segs],
        junctions=[EJunction(x, y) for x, y in routed.junctions],
        hlabels=placement.hlabels, llabels=placement.llabels,
        no_connects=placement.no_connects, paper=placement.paper)
    outdir.mkdir(parents=True, exist_ok=True)
    sch = outdir / f"{c.name}.kicad_sch"
    emit(design, sch, lib)
    return Built(circuit=c, sch=sch, text=sch.read_text(),
                 placement=placement, routed=routed, geo=geo, lib=lib)


# ---- the gate stack ------------------------------------------------------------

@dataclass
class StackVerdict:
    failures: list[str] = field(default_factory=list)   # "gate: detail"
    passed: list[str] = field(default_factory=list)

    @property
    def green(self) -> bool:
        return not self.failures

    def killed_by(self) -> str:
        return "; ".join(self.failures[:2]) + \
            (f" (+{len(self.failures) - 2} more)" if len(self.failures) > 2
             else "")


def _run_stack(circuit: Circuit, sch: Path, lib: Library,
               geo: object = None) -> StackVerdict:
    """Every gate the build runs, against (declared circuit, emitted file).

    ERC policy and the strict inputs-driven check are imported from the
    build itself (schgen.__main__) so selftest can never drift from what
    `schgen build` actually enforces.
    """
    from schgen.__main__ import _check_inputs_driven, _erc
    v = StackVerdict()
    net_res = netlist_gate.check(circuit, sch)
    if net_res.ok:
        v.passed.append("netlist")
    else:
        first = net_res.summary().splitlines()[1].strip()
        v.failures.append(f"netlist gate: {first}")
    erc_ok, erc_txt = _erc(sch, sch.with_suffix(".erc.rpt"))
    if erc_ok:
        v.passed.append("erc")
    else:
        line = next((ln.strip() for ln in erc_txt.splitlines()
                     if "; error" in ln.lower() or "[" in ln), "errors > 0")
        v.failures.append(f"ERC gate: {line[:120]}")
    driven = _check_inputs_driven(circuit, lib)
    if driven:
        v.failures.append(f"inputs-driven gate: {driven[0]}")
    else:
        v.passed.append("inputs-driven")
    if geo is not None:
        vis = visual_gate.check(geo)
        if vis.ok:
            v.passed.append("visual")
        else:
            v.failures.append(f"visual gate: {vis.findings[0]}")
    return v


# ---- mutation classes ----------------------------------------------------------
# Each mutator returns (description, mutated_circuit_or_None, mutated_text_or_
# None). Exactly one side mutates: the gates must notice the two sides of the
# proof (declared netlist vs emitted file) disagreeing.

def mutate_pin_swap(b: Built) -> tuple[str, Circuit, None] | None:
    """Exchange one pin between the first two distinct nets (declared side)."""
    m = copy.deepcopy(b.circuit)
    nets = [n for n in sorted(m.nets.values(), key=lambda n: n.name) if n.pins]
    if len(nets) < 2:
        return None
    a, bb = nets[0], nets[1]
    pa, pb = a.pins[0], bb.pins[0]
    a.pins[0], bb.pins[0] = pb, pa
    return (f"pin swap: {pa} ({a.name!r}) <-> {pb} ({bb.name!r})", m, None)


def _wire_nodes(doc: list) -> list[list]:
    return sexpr.find_all(doc, "wire")


def mutate_wire_delete(b: Built, index: int) -> tuple[str, None, str] | None:
    """Delete wire segment #index from the emitted file."""
    doc = sexpr.loads(b.text)
    wires = _wire_nodes(doc)
    if index >= len(wires):
        return None
    w = wires[index]
    pts = sexpr.find(w, "pts")
    coords = " ".join(str(x) for xy in sexpr.find_all(pts, "xy")
                      for x in xy[1:]) if pts else "?"
    doc.remove(w)
    return (f"wire delete #{index} [{coords}]", None, sexpr.dumps(doc) + "\n")


def mutate_label_alias(b: Built) -> tuple[str, None, str] | None:
    """Rewrite one net label to ANOTHER net's name (silent merge/short)."""
    doc = sexpr.loads(b.text)
    labels = (sexpr.find_all(doc, "global_label")
              + sexpr.find_all(doc, "hierarchical_label")
              + sexpr.find_all(doc, "label"))
    if not labels:
        return None
    lab = labels[0]
    a = str(lab[1])
    # prefer merging into a GROUND net (the historical killer), else any
    # other net that has pins.
    cands = sorted((n for n in b.circuit.nets.values()
                    if n.name != a and n.pins),
                   key=lambda n: (n.net_class != NetClass.GROUND, n.name))
    if not cands:
        return None
    target = cands[0].name
    lab[1] = target
    return (f"label alias: label {a!r} rewritten to {target!r}",
            None, sexpr.dumps(doc) + "\n")


def mutate_stray_nc(b: Built) -> tuple[str, None, str] | None:
    """Drop a no_connect onto a pin that carries a net (the NC cheat)."""
    for p in sorted(b.placement.parts, key=lambda p: p.ref):
        for pin in b.lib.get(p.lib_id).pins:
            pr = PinRef(p.ref, pin.number)
            if b.circuit.net_of(pr) is None:
                continue
            x, y = pin_page_position(pin, p.x, p.y, p.rotation)
            doc = sexpr.loads(b.text)
            nc = [Sym("no_connect"), [Sym("at"), x, y],
                  [Sym("uuid"), str(_uuid.uuid4())]]
            doc.insert(len(doc) - 1, nc)   # before sheet_instances
            return (f"stray NC on netted pin {pr} @({x},{y})",
                    None, sexpr.dumps(doc) + "\n")
    return None


def _grid_point_on(seg) -> tuple[float, float]:
    """A 1.27-grid point on the segment (midpoint, snapped)."""
    mx = round(((seg.x0 + seg.x1) / 2) / GRID) * GRID
    my = round(((seg.y0 + seg.y1) / 2) / GRID) * GRID
    return (round(mx, 2), round(my, 2))


def mutate_foreign_junction(b: Built) -> tuple[str, None, str] | None:
    """Bridge two DIFFERENT nets with a wire and junction the contacts —
    the LAW-0 short (junction at a foreign crossing)."""
    by_net: dict[str, list] = {}
    for s in b.routed.segs:
        by_net.setdefault(s.net, []).append(s)
    nets = sorted(by_net)
    if len(nets) < 2:
        return None
    sa = max(by_net[nets[0]], key=lambda s: abs(s.x1 - s.x0) + abs(s.y1 - s.y0))
    sb = max(by_net[nets[1]], key=lambda s: abs(s.x1 - s.x0) + abs(s.y1 - s.y0))
    (ax, ay), (bx, by) = _grid_point_on(sa), _grid_point_on(sb)
    doc = sexpr.loads(b.text)

    def wire(x0, y0, x1, y1):
        return [Sym("wire"),
                [Sym("pts"), [Sym("xy"), x0, y0], [Sym("xy"), x1, y1]],
                [Sym("stroke"), [Sym("width"), 0],
                 [Sym("type"), Sym("default")]],
                [Sym("uuid"), str(_uuid.uuid4())]]

    def junction(x, y):
        return [Sym("junction"), [Sym("at"), x, y], [Sym("diameter"), 0],
                [Sym("color"), 0, 0, 0, 0], [Sym("uuid"), str(_uuid.uuid4())]]

    add: list = []
    if ax != bx:
        add.append(wire(ax, ay, bx, ay))
    if ay != by:
        add.append(wire(bx, ay, bx, by))
    add += [junction(ax, ay), junction(bx, by)]
    for node in add:
        doc.insert(len(doc) - 1, node)
    return (f"foreign junction: bridge {nets[0]!r}@({ax},{ay}) -> "
            f"{nets[1]!r}@({bx},{by}) with junctioned contacts",
            None, sexpr.dumps(doc) + "\n")


# ---- determinism ---------------------------------------------------------------

def determinism_check(path: Path, tmp: Path) -> tuple[bool, str]:
    """FULL byte-equality, no uuid tolerance: emit derives every id from
    content (uuid5), so two builds must reproduce every byte — ids
    included. A uuid that differs is drift like any other."""
    texts = []
    for i in (1, 2):
        b = _build(path, tmp / f"det{i}")
        texts.append(b.text)
    if texts[0] == texts[1]:
        return True, "byte-identical (uuids included, zero tolerance)"
    diff = list(difflib.unified_diff(
        texts[0].splitlines(), texts[1].splitlines(),
        "build-1", "build-2", lineterm="", n=0))
    return False, "DRIFT between two builds:\n    " + "\n    ".join(diff[:12])


# ---- driver ----------------------------------------------------------------------

def _resolve_sheet(spec: str) -> Path:
    p = Path(spec)
    if p.suffix == ".py" and p.exists():
        return p.resolve()
    cand = REPO_ROOT / "carrier" / "subsystems" / f"{spec}.py"
    if cand.exists():
        return cand
    raise SystemExit(f"selftest: sheet not found: {spec}")


def selftest_sheet(path: Path, tmp: Path) -> tuple[int, int, list[str]]:
    """Returns (mutants_injected, mutants_killed, problems)."""
    problems: list[str] = []
    base = _build(path, tmp / "base")
    name = base.circuit.name
    print(f"--- {name} ({path.relative_to(REPO_ROOT)}) ---")

    v0 = _run_stack(base.circuit, base.sch, base.lib, geo=base.geo)
    if not v0.green:
        problems.append(f"{name}: baseline NOT green: {v0.killed_by()}")
        print(f"  baseline: FAIL — {v0.killed_by()}")
        return 0, 0, problems
    print(f"  baseline: green ({', '.join(v0.passed)})")

    n_wires = len(_wire_nodes(sexpr.loads(base.text)))
    mutants: list[tuple[str, Circuit | None, str | None]] = []
    for mk in (mutate_pin_swap, mutate_label_alias, mutate_stray_nc,
               mutate_foreign_junction):
        m = mk(base)
        if m is None:
            problems.append(f"{name}: mutation {mk.__name__} NOT APPLICABLE "
                            f"— fixture too small to exercise the gate")
            continue
        mutants.append(m)
    for i in range(n_wires):
        m = mutate_wire_delete(base, i)
        if m:
            mutants.append(m)

    injected = killed = 0
    for k, (desc, mcirc, mtext) in enumerate(mutants):
        injected += 1
        if mtext is not None:
            msch = tmp / "mut" / f"{name}.mut{k:02d}.kicad_sch"
            msch.parent.mkdir(parents=True, exist_ok=True)
            msch.write_text(mtext)
            verdict = _run_stack(mcirc or base.circuit, msch, base.lib)
        else:
            verdict = _run_stack(mcirc, base.sch, base.lib)
        if verdict.green:
            problems.append(f"{name}: MUTANT SURVIVED every gate: {desc}")
            print(f"  SURVIVED  {desc}   <-- HOLE IN THE GATE STACK")
        else:
            killed += 1
            print(f"  killed    {desc}\n"
                  f"            by {verdict.killed_by()}")
    return injected, killed, problems


def run(sheet_specs: list[str], keep: bool = False) -> int:
    sheets = [_resolve_sheet(s) for s in sheet_specs] if sheet_specs \
        else [Path(p) for p in DEFAULT_SHEETS]
    tmp = Path(tempfile.mkdtemp(prefix="schgen_selftest_"))
    print(f"schgen selftest — gate mutation testing + determinism "
          f"({len(sheets)} sheets, scratch {tmp})")
    total_inj = total_kill = 0
    problems: list[str] = []
    try:
        for path in sheets:
            inj, kill, probs = selftest_sheet(path, tmp / path.stem)
            total_inj += inj
            total_kill += kill
            problems += probs
            det_ok, det_msg = determinism_check(path, tmp / path.stem)
            print(f"  determinism: {'PASS' if det_ok else 'FAIL'} — {det_msg}")
            if not det_ok:
                problems.append(f"{path.stem}: determinism FAIL")
    finally:
        if keep:
            print(f"scratch kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print()
    if problems:
        print(f"SELFTEST: FAIL — {total_kill}/{total_inj} mutants killed; "
              f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"SELFTEST: PASS — {total_kill}/{total_inj} mutants killed, "
          f"determinism proven on {len(sheets)} sheet(s)")
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    return run(args.sheets, keep=args.keep)
