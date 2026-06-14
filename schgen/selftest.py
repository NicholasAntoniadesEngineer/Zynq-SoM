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

The file/geometry mutants above prove the netlist / ERC / inputs-driven /
visual gates. The MODEL-GATE mutants below close the F1 hole for the
*model-only* gates — the ones that read the declared :class:`Circuit`
(parts/nets/draws/port-types/waivers) rather than the emitted file, and so
were never exercised against a defect by the file-based mutators:

- ``drop_decap``     delete a decoupling cap from an IC supply pin
                     -> design_rules DECAP fires
- ``remove_pullup``  delete an i2c pull-up resistor
                     -> design_rules I2C fires
- ``break_reset``    strip a reset net's cap (the RC half)
                     -> design_rules RESET fires
- ``thermal_overrun``bump a regulator's declared draw so Tj passes its limit
                     -> thermal fires; a companion ``thermal_waiver`` mutant
                     proves ``c.waive_thermal`` DEMOTES the same over-Tj to a
                     note (the waiver path is proven too)
- ``power_overrun``  push a regulator past its datasheet current limit
                     -> powertree fires
- ``divider_drift``  perturb one FB resistor so a named SPICE divider leaves
                     its window -> spice fires
- ``tp_uncovered``   drop a required rail's test point
                     -> testpoints fires
- ``port_rename``    rename one PORT label on one sheet's emitted root so it
                     no longer merges -> the board cross-sheet merge gate fails

Each model-gate mutant ALSO asserts the gate PASSES on the unmutated fixture
(a gate that always fires proves nothing), exactly like the baseline check
the file mutants run first.

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
import re as _re
import shutil
import tempfile
import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path

from schgen import place, sexpr
from schgen.emit import Junction as EJunction
from schgen.emit import PlacedDesign, Wire, emit
from schgen.emit import stable_uuid as _stable_uuid
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


# ---- geometry mutants (the VISUAL gate's province) ----------------------------
# The netlist/ERC/inputs-driven gates read the emitted FILE; the visual gate
# reads the SheetGeometry (boxes + wires) the placer hands back. So a geometry
# defect that leaves the file electrically valid — a wire shifted onto a
# foreign net, a Value box dragged over a wire — is INVISIBLE to every gate
# except visual_gate. These mutants perturb a fresh SheetGeometry rebuilt from
# the baseline emission and are run with geo= so visual_gate.check MUST kill
# them (proving the visual gate, like the others, actually bites — the F1 hole
# was that mutants never passed geo, so visual_gate.check ran on the baseline
# only and was never tested against a defect).

def _rebuild_geo(b: "Built") -> "visual_gate.SheetGeometry":
    """A fresh SheetGeometry equivalent to the baseline emission: the placer's
    boxes + the routed segments as visual_gate Segs (the same construction
    place.place_and_route uses)."""
    return visual_gate.SheetGeometry(
        boxes=list(b.geo.boxes),
        wires=[visual_gate.Seg(s.x0, s.y0, s.x1, s.y1, s.net)
               for s in b.routed.segs])


def mutate_geo_wire_crosses_foreign(b: Built):
    """Shift a wire onto a perpendicular crossing of a FOREIGN net — a wire
    over a different net's wire (LAW-1 crossing / LAW-0 short risk). Returns
    (desc, mutated_geo) or None."""
    geo = _rebuild_geo(b)
    hs = [s for s in geo.wires if abs(s.y0 - s.y1) < 1e-6]   # horizontal
    vs = [s for s in geo.wires if abs(s.x0 - s.x1) < 1e-6]   # vertical
    for v in vs:
        vy0, vy1 = sorted((v.y0, v.y1))
        for i, h in enumerate(hs):
            if h.net == v.net:
                continue
            hx0, hx1 = sorted((h.x0, h.x1))
            ymid = round((vy0 + vy1) / 2, 3)
            if not (vy0 < ymid < vy1):
                continue
            # rebuild h to span ACROSS v.x at y=ymid (strictly interior of v),
            # guaranteeing a perpendicular foreign crossing.
            span = max(hx1 - hx0, 2 * GRID)
            new = visual_gate.Seg(round(v.x0 - span / 2, 3), ymid,
                                  round(v.x0 + span / 2, 3), ymid, h.net)
            geo.wires[geo.wires.index(h)] = new
            return (f"geo: wire {h.net!r} shifted to cross foreign {v.net!r} "
                    f"@({v.x0},{ymid})", geo)
    return None


def mutate_geo_text_over_wire(b: Built):
    """Drag a Value text box onto a wire of a DIFFERENT owner — text through a
    wire (LAW-1 overlap). Returns (desc, mutated_geo) or None."""
    geo = _rebuild_geo(b)
    vals = [i for i, bx in enumerate(geo.boxes) if bx.kind == "value"]
    if not vals or not geo.wires:
        return None
    w = max(geo.wires, key=lambda s: abs(s.x1 - s.x0) + abs(s.y1 - s.y0))
    cx, cy = round((w.x0 + w.x1) / 2, 3), round((w.y0 + w.y1) / 2, 3)
    bi = vals[0]
    old = geo.boxes[bi]
    dx, dy = old.x1 - old.x0, old.y1 - old.y0
    moved = visual_gate.Box(round(cx - dx / 2, 3), round(cy - dy / 2, 3),
                            round(cx + dx / 2, 3), round(cy + dy / 2, 3),
                            old.kind, old.owner)
    geo.boxes[bi] = moved
    return (f"geo: value box {old.owner!r} dragged onto wire {w.net!r} "
            f"@({cx},{cy})", geo)


# ---- model-gate mutants (the F1 hole for the model-only gates) -----------------
# The gates above read the emitted FILE or the placer's geometry. A second
# family of gates reads ONLY the declared Circuit — its parts, nets, draws,
# port-types and waivers — never the file: design_rules (decap / i2c-pullup /
# reset-RC / strap), thermal (Tj = Ta + Pd*RthJA), powertree (regulator current
# limits), spice (divider / FB setpoint windows), testpoints (rail probe
# coverage) and board (the per-PORT cross-sheet merge gate). The file/geometry
# mutators never touch any of them, so — exactly the F1 lesson — each was an
# UNPROVEN gate: green on every input it was ever handed. These mutants build a
# minimal valid fixture, prove the gate PASSES it, inject ONE targeted defect,
# and prove the SAME gate FAILS (or, for a waiver, DEMOTES the failure).
#
# A tiny SheetCircuit-shaped shim is all the model gates need from a sheet
# (they read sc.name + sc.circuit only); building real geometry is unnecessary
# and would only add noise, so the fixtures stay pure netlist.


@dataclass
class _Sheet:
    """The duck-typed shape every model gate consumes (schgen.link.SheetCircuit
    has more, but the gates touch only ``.name`` and ``.circuit``)."""
    name: str
    circuit: Circuit


def _net_names_of(c: Circuit, ref: str) -> list[str]:
    return [n.name for n in c.nets.values()
            if any(pr.ref == ref for pr in n.pins)]


def _delete_part(c: Circuit, ref: str) -> None:
    """Remove a part and every reference to it from the nets (an honest
    deletion — what an author dropping a component would leave behind)."""
    c.parts.pop(ref, None)
    for n in c.nets.values():
        n.pins = [pr for pr in n.pins if pr.ref != ref]


def _find_part(c: Circuit, suffix: str, must_have: tuple[str, ...],
               must_ground: bool = False) -> str | None:
    for ref in sorted(c.parts):
        part = c.parts[ref]
        if not part.lib_id.endswith(suffix):
            continue
        names = _net_names_of(c, ref)
        if all(m in names for m in must_have) and (
                not must_ground or any(_n.startswith("GND") for _n in names)):
            return ref
    return None


# Fixture A — an IC with named supply pins + i2c + reset, for design_rules.
# The CP2102N symbol carries real power-named pins (VIO/VDD/VREGIN), an i2c
# port and a reset net; VDD is parked on its OWN rail with a SINGLE decap so a
# dropped cap leaves that rail bare (the +3V3 rail keeps two, so a defect there
# would be masked). Every rule passes at baseline — including STRAP (no config
# pin floats).

def _fixture_design_rules() -> list[_Sheet]:
    c = Circuit("selftest_dr", "selftest design-rule fixture")
    c.part("U1", "schgen:CP2102N_UART", "CP2102N")
    c.net("+3V3", "U1.5", "U1.7")          # VIO + VREGIN share +3V3
    c.net("+VDD_CORE", "U1.6")             # VDD on its own rail
    c.net("GND", "U1.2", "U1.25")
    c.decouple("U1.7", "100n")             # +3V3 decaps (two)
    c.decouple("U1.5", "100n")
    c.decouple("U1.6", "100n")             # the ONLY +VDD_CORE decap
    c.port("SC_I2C_SCL", "U1.20", kind="i2c", role="scl")
    c.pullup("U1.20", "4k7", "+3V3")       # i2c pull-up to a rail
    c.net("SYS_RST_N", "U1.9")             # reset net: cap-to-GND + pull
    c.decouple("U1.9", "100n")
    c.pullup("U1.9", "10k", "+3V3")
    return [_Sheet("selftest_dr", c)]


# Fixture B — a TPS54302 buck with an FB divider, for powertree / thermal /
# spice. SW -> L -> +3V3 (the rail behind the inductor); FB divider 45k3/10k
# gives Vout = 0.596*(1+45.3/10) = 3.30 V (in the +/-3% window); EN parked on a
# POWER rail so the spice EN-clamp check stays out of the SIGNAL path. The
# declared draw (0.5 A) is well under the 3 A limit and cool (Tj << limit).

def _fixture_buck(draw_a: float = 0.5, rtop: str = "45k3") -> list[_Sheet]:
    c = Circuit("selftest_buck", "selftest power/thermal/spice fixture")
    # TPS54302: 1 GND 2 SW 3 VIN 4 FB 5 EN 6 BOOT
    c.part("U1", "Regulator_Switching:TPS54302", "TPS54302DDCR",
           "Package_TO_SOT_SMD:SOT-23-6")
    c.part("L1", "Device:L", "2.2uH")
    c.net("+VIN", "U1.3")
    c.net("SW", "U1.2", "L1.1")
    c.net("+3V3", "L1.2")                   # rail behind the inductor
    c.net("GND", "U1.1")
    c.net("+5V_EN", "U1.5", net_class=NetClass.POWER)  # EN on a rail: skip clamp
    c.net("FB", "U1.4")
    c.series("+3V3", "FB", rtop)            # R1: FB top
    c.series("FB", "GND", "10k")            # R2: FB bottom
    c.draws("+3V3", draw_a, "selftest declared load")
    return [_Sheet("selftest_buck", c)]


# Fixture C — a rail + ground, each with a probe point, for testpoints.

def _fixture_testpoints() -> list[_Sheet]:
    c = Circuit("selftest_tp", "selftest test-point fixture")
    c.part("R1", "Device:R", "10k")
    c.net("+3V3", "R1.1")
    c.net("GND", "R1.2")
    c.testpoint("+3V3")
    c.testpoint("GND")
    return [_Sheet("selftest_tp", c)]


def _fixture_mounting_hole() -> Circuit:
    """A sheet with CHASSIS_GND and +3V3 declared, ready for mounting_hole()."""
    c = Circuit("selftest_mh", "selftest mounting-hole fixture")
    c.part("R1", "Device:R", "10k")
    c.net("CHASSIS_GND", "R1.1")
    c.net("+3V3", "R1.2")
    return c


# Fixture D — two sheets sharing PORT 'SELFTEST_LINK', for the board merge gate.

def _board_fixture_sheets() -> list[_Sheet]:
    a = Circuit("selftest_brd_a", "selftest board fixture A")
    a.part("R1", "Device:R", "10k")
    a.net("+3V3", "R1.1")
    a.port("SELFTEST_LINK", "R1.2")
    b = Circuit("selftest_brd_b", "selftest board fixture B")
    b.part("R2", "Device:R", "10k")
    b.port("SELFTEST_LINK", "R2.1")
    b.net("GND", "R2.2")
    return [_Sheet("selftest_brd_a", a), _Sheet("selftest_brd_b", b)]


# ---- the model-gate runners (each returns (passed_baseline, killed, detail)) ----
# Signature is uniform so the driver treats them exactly like the file mutants:
# it credits a kill only when baseline is green AND the mutant is red.

def _mg_design_rules(which: str, lib: Library):
    """drop_decap / remove_pullup / break_reset against design_rules.check."""
    from schgen.verify import design_rules

    def fires(res, rule: str) -> list[str]:
        return getattr(res, rule)

    base = _fixture_design_rules()
    base_res = design_rules.check(base, lib)
    if which == "drop_decap":
        rule, suffix, have, gnd = "decap", ":C", ("+VDD_CORE",), True
    elif which == "remove_pullup":
        rule, suffix, have, gnd = "i2c", ":R", ("SC_I2C_SCL", "+3V3"), False
    else:                                          # break_reset
        rule, suffix, have, gnd = "reset", ":C", ("SYS_RST_N",), False
    base_ok = base_res.ok and not fires(base_res, rule)

    mut = _fixture_design_rules()
    c = mut[0].circuit
    ref = _find_part(c, suffix, have, must_ground=gnd)
    desc = f"{which}: delete {ref} ({'/'.join(have)})"
    if ref is None:
        return base_ok, False, f"{which}: target part not found in fixture"
    _delete_part(c, ref)
    mut_res = design_rules.check(mut, lib)
    fired = fires(mut_res, rule)
    killed = bool(fired) and not mut_res.ok
    by = (fired[0] if fired else "(no finding)")
    return base_ok, killed, f"{desc}\n            by design_rules {rule.upper()}: {by}"


def _mg_power_overrun(lib: Library):
    """power_overrun: load the buck past its 3 A limit -> powertree fires."""
    from schgen import powertree
    base_ok = powertree.analyze(_fixture_buck()).ok
    mut = _fixture_buck()
    mut[0].circuit.loads["+3V3"] = [(4.0, "selftest overrun")]
    res = powertree.analyze(mut)
    killed = (not res.ok) and any("OVERRUN" in e for e in res.errors)
    by = res.errors[0] if res.errors else "(no error)"
    return base_ok, killed, ("power_overrun: +3V3 load 0.5A -> 4.0A (> 3 A "
                             f"limit)\n            by powertree: {by}")


def _mg_thermal(which: str, lib: Library):
    """thermal_overrun (Tj over limit -> thermal fires) and thermal_waiver
    (the SAME over-Tj demoted to a note by c.waive_thermal)."""
    from schgen import powertree, thermal

    def run(sheets):
        pt = powertree.analyze(sheets)
        return pt, thermal.analyze(sheets, pt_res=pt)

    _pt0, base = run(_fixture_buck())
    base_ok = base.ok and not base.errors and not base.notes
    # 2.5 A is UNDER the 3 A powertree limit but the buck's Pd*RthJA pushes Tj
    # over the guard band — so the kill is unambiguously the thermal gate's,
    # never powertree's.
    mut = _fixture_buck(draw_a=2.5)
    c = mut[0].circuit
    if which == "thermal_overrun":
        pt, res = run(mut)
        killed = (not pt.ok) is False and (not res.ok) and \
            any("OVER Tj" in e for e in res.errors)
        by = res.errors[0].split(" [")[0] if res.errors else "(no error)"
        return base_ok, killed, ("thermal_overrun: +3V3 draw 0.5A -> 2.5A "
                                 "(Tj over limit, under 3 A current limit)"
                                 f"\n            by thermal: {by}")
    # thermal_waiver: same over-Tj, but waived -> demoted to a note, gate OK
    c.waive_thermal("U1", "selftest: copper-pour derate not in single RthJA")
    pt, res = run(mut)
    demoted = res.ok and any("WAIVED over-limit" in n for n in res.notes)
    by = next((n for n in res.notes if "WAIVED over-limit" in n),
              "(not demoted)")
    return base_ok, demoted, ("thermal_waiver: same over-Tj + c.waive_thermal "
                              "-> demoted to a note, gate stays green"
                              f"\n            by thermal waiver path: {by[:90]}")


def _mg_divider_drift(lib: Library):
    """divider_drift: perturb the FB top resistor so Vout leaves +/-3% -> spice
    fires on the named FB-divider window."""
    from schgen import spice
    base_ok = spice.extract_checks(_fixture_buck()).ok
    # 45k3 -> 33k drops Vout from 3.30 V to 0.596*(1+3.3) = 2.56 V, far below
    # the 3.20..3.40 V window.
    mut = _fixture_buck(rtop="33k")
    res = spice.extract_checks(mut)
    killed = (not res.ok) and any("FB" in e for e in res.errors)
    by = res.errors[0] if res.errors else "(no error)"
    return base_ok, killed, ("divider_drift: FB top 45k3 -> 33k (Vout leaves "
                             f"+/-3%)\n            by spice: {by}")


def _mg_tp_uncovered(lib: Library):
    """tp_uncovered: drop the +3V3 rail's test point -> testpoints fires."""
    from schgen import testpoints
    base_ok = testpoints.check_coverage(_fixture_testpoints()).ok
    mut = _fixture_testpoints()
    c = mut[0].circuit
    drop = None
    for ref in list(c.parts):
        if testpoints.is_testpoint(c.parts[ref]) and \
                "+3V3" in _net_names_of(c, ref):
            drop = ref
            break
    if drop is None:
        return base_ok, False, "tp_uncovered: +3V3 test point not found"
    _delete_part(c, drop)
    cov = testpoints.check_coverage(mut)
    killed = (not cov.ok) and any("+3V3" in e for e in cov.errors)
    by = next((e for e in cov.errors if "+3V3" in e), "(no error)")
    return base_ok, killed, ("tp_uncovered: drop the +3V3 probe point"
                             f"\n            by testpoints: {by}")


def _mg_mh_short(lib: Library):
    """mh_short: prove mounting_hole()'s LAW-0 guard rejects a non-GROUND net.
    BASELINE — a CHASSIS_GND hole succeeds, is BOM-excluded, and lands its pin
    on CHASSIS_GND (the chassis bond is real netlisted copper). MUTANT — the
    SAME call on +3V3 (a POWER rail) MUST raise CircuitError: a mounting hole
    is a chassis/earth bond, never a rail, so bonding it to +3V3 would be a
    short. The guard IS the gate here (no emit needed)."""
    from schgen.model import CircuitError, PinRef
    base = _fixture_mounting_hole()
    p = base.mounting_hole("CHASSIS_GND")
    base_ok = (p.fields.get("BOM") == "exclude"
               and PinRef(p.ref, "1") in base.nets["CHASSIS_GND"].pins
               and base.nets["CHASSIS_GND"].net_class is NetClass.GROUND)
    mut = _fixture_mounting_hole()
    try:
        mut.mounting_hole("+3V3")
        killed = False
        by = "(no raise — +3V3 mounting hole was ACCEPTED)"
    except CircuitError as e:
        killed = "GROUND" in str(e)
        by = str(e)
    return base_ok, killed, ("mh_short: c.mounting_hole('+3V3') on a POWER rail"
                             f"\n            by mounting_hole guard: {by}")


def _mg_port_rename(lib: Library, tmp: Path):
    """port_rename: build the two-sheet board (baseline merge gate PASSES),
    then rewrite ONE 'SELFTEST_LINK' PORT label on the emitted ROOT so its
    sheet pin no longer merges with the other sheet's -> the board cross-sheet
    merge gate FAILS. The mutated emitted file disagrees with the declared
    circuits (which still demand the merge), which is precisely what the board
    gate exists to catch."""
    from schgen import board

    def _placed(sheets, root="board"):
        # mirror build_board's place->uniquify (the only model state the merge
        # gate reads); the public place/uniquify functions, no gate logic.
        out = []
        for i, sc in enumerate(sheets, start=1):
            placement, routed, _geo = place.place_and_route(sc.circuit, lib)
            d = PlacedDesign(
                circuit=sc.circuit, parts=placement.parts,
                powers=placement.powers,
                wires=[Wire(s.x0, s.y0, s.x1, s.y1) for s in routed.segs],
                junctions=[EJunction(x, y) for x, y in routed.junctions],
                hlabels=placement.hlabels, llabels=placement.llabels,
                no_connects=placement.no_connects, paper=placement.paper)
            d = board.uniquify(d, i)
            out.append((sc.name, d, _stable_uuid(root, "sheet-symbol", sc.name)))
        return out

    base_out = tmp / "board_base"
    base_ok = board.build_board(_board_fixture_sheets(), lib, base_out,
                                root_name="board")
    # mutant: re-emit (fresh dir), then tamper the root label
    mut_out = tmp / "board_mut"
    board.build_board(_board_fixture_sheets(), lib, mut_out, root_name="board")
    root = mut_out / "board.kicad_sch"
    txt = root.read_text()
    new = _re.sub(r'(\(global_label\s+)"SELFTEST_LINK"',
                  r'\1"SELFTEST_LINK_BROKEN"', txt, count=1)
    if new == txt:
        return base_ok, False, ("port_rename: could not find a SELFTEST_LINK "
                                "root label to rename")
    root.write_text(new)
    placed = _placed(_board_fixture_sheets())
    killed = not board._board_gate(placed, root, mut_out)
    return base_ok, killed, ("port_rename: one SELFTEST_LINK root label -> "
                             "SELFTEST_LINK_BROKEN (its sheet pin keeps the "
                             "old name)\n            by board merge gate: PORT "
                             "no longer merges across the two sheets")


def selftest_model_gates(tmp: Path) -> tuple[int, int, list[str]]:
    """Run every model-gate mutant. Returns (injected, killed, problems),
    feeding the SAME tally + exit code as the file/geometry mutants. Each
    mutant proves its gate PASSES the clean fixture AND FAILS the defect (a
    waiver mutant instead proves the failure is DEMOTED)."""
    lib = Library()
    problems: list[str] = []
    print("--- model-gate mutants (design_rules / thermal / powertree / "
          "spice / testpoints / board) ---")
    runners = [
        ("drop_decap",      lambda: _mg_design_rules("drop_decap", lib)),
        ("remove_pullup",   lambda: _mg_design_rules("remove_pullup", lib)),
        ("break_reset",     lambda: _mg_design_rules("break_reset", lib)),
        ("thermal_overrun", lambda: _mg_thermal("thermal_overrun", lib)),
        ("thermal_waiver",  lambda: _mg_thermal("thermal_waiver", lib)),
        ("power_overrun",   lambda: _mg_power_overrun(lib)),
        ("divider_drift",   lambda: _mg_divider_drift(lib)),
        ("tp_uncovered",    lambda: _mg_tp_uncovered(lib)),
        ("mh_short",        lambda: _mg_mh_short(lib)),
        ("port_rename",     lambda: _mg_port_rename(lib, tmp / "board")),
    ]
    injected = killed = 0
    for name, fn in runners:
        injected += 1
        base_ok, did_kill, detail = fn()
        if not base_ok:
            problems.append(f"model-gate {name}: BASELINE not green — the "
                            f"clean fixture already trips (or pre-fires) the "
                            f"gate; a gate that always fires proves nothing")
            print(f"  BASELINE-FAIL {name}   <-- fixture not clean")
            continue
        if did_kill:
            killed += 1
            print(f"  killed    {detail}")
        else:
            problems.append(f"model-gate {name}: MUTANT SURVIVED its gate: "
                            f"{detail.splitlines()[0]}")
            print(f"  SURVIVED  {detail.splitlines()[0]}   <-- HOLE IN THE "
                  f"MODEL GATE")
    return injected, killed, problems


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


def determinism_hashseed_check(path: Path, tmp: Path) -> tuple[bool, str]:
    """CROSS-SEED byte-equality. The same-process double-build above shares one
    PYTHONHASHSEED, so it cannot catch non-determinism from set/dict ITERATION
    ORDER (e.g. an unsorted set feeding emitted geometry). Build the sheet in
    two SUBPROCESSES with different hash seeds and require byte-identical output
    — this is the gate that proves the emit path is hash-seed-robust."""
    import os
    import subprocess
    import sys
    code = ("import sys; from pathlib import Path; "
            "from schgen.selftest import _build; "
            "sys.stdout.write(_build(Path(sys.argv[1]), Path(sys.argv[2])).text)")
    texts = []
    for seed in ("0", "987654321"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run(
            [sys.executable, "-c", code, str(path), str(tmp / f"hs{seed}")],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True)
        if r.returncode != 0:
            return False, f"subprocess build failed (seed {seed}): {r.stderr[-300:]}"
        texts.append(r.stdout)
    if texts[0] == texts[1]:
        return True, "byte-identical across PYTHONHASHSEED {0, 987654321}"
    diff = list(difflib.unified_diff(
        texts[0].splitlines(), texts[1].splitlines(),
        "seed-0", "seed-987654321", lineterm="", n=0))
    return False, "HASH-SEED DRIFT (set/dict iteration leaks into output):\n    " \
        + "\n    ".join(diff[:12])


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

    # geometry mutants: defects ONLY the visual gate can see (the file stays
    # electrically valid, so netlist/ERC/inputs-driven all pass — the visual
    # gate MUST be the killer). Run with the baseline circuit+sch and the
    # MUTATED geo so visual_gate.check actually runs against a defect.
    geo_mutants: list[tuple[str, object]] = []
    for gk in (mutate_geo_wire_crosses_foreign, mutate_geo_text_over_wire):
        gm = gk(base)
        if gm is None:
            problems.append(f"{name}: geometry mutation {gk.__name__} NOT "
                            f"APPLICABLE — fixture lacks the geometry to "
                            f"exercise the visual gate")
            continue
        geo_mutants.append(gm)

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

    for desc, mgeo in geo_mutants:
        injected += 1
        # baseline electrical truth + MUTATED geometry: only visual can bite
        verdict = _run_stack(base.circuit, base.sch, base.lib, geo=mgeo)
        if verdict.green:
            problems.append(f"{name}: GEOMETRY MUTANT SURVIVED every gate: "
                            f"{desc}")
            print(f"  SURVIVED  {desc}   <-- HOLE IN THE VISUAL GATE")
        elif not any(f.startswith("visual gate") for f in verdict.failures):
            # killed, but NOT by the visual gate — the geometry defect must be
            # the visual gate's to catch; anything else is a miscredit.
            problems.append(f"{name}: geometry mutant killed by a NON-visual "
                            f"gate ({verdict.killed_by()}): {desc}")
            print(f"  MISCREDIT {desc}   <-- not the visual gate")
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
            hs_ok, hs_msg = determinism_hashseed_check(path, tmp / path.stem)
            print(f"  hash-seed:   {'PASS' if hs_ok else 'FAIL'} — {hs_msg}")
            if not hs_ok:
                problems.append(f"{path.stem}: hash-seed determinism FAIL")
        # model-gate mutants are board-wide (their own minimal fixtures), so
        # they run ONCE — not per input sheet — and fold into the same tally.
        mg_inj, mg_kill, mg_probs = selftest_model_gates(tmp / "model_gates")
        total_inj += mg_inj
        total_kill += mg_kill
        problems += mg_probs
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
