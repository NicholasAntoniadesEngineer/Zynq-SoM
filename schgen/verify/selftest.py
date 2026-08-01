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

from schgen.core import sexpr
from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.project import PROJECT_ROOT, positional_sheet_index
from schgen.core.sexpr import Sym
from schgen.core.symbols import GRID, Library, pin_page_position
from schgen.layout import place
from schgen.output.emit import Junction as EJunction
from schgen.output.emit import PlacedDesign, Wire, emit
from schgen.output.emit import stable_uuid as _stable_uuid
from schgen.verify import netlist_gate, visual_gate

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SHEETS = (
    REPO_ROOT / "schgen" / "tests" / "m1_rc_sheet.py",
    PROJECT_ROOT / "subsystems" / "uart_bridge.py",
)


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


@dataclass
class StackVerdict:
    failures: list[str] = field(default_factory=list)
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


def mutate_pin_swap(b: Built) -> tuple[str, Circuit, None] | None:
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
    doc = sexpr.loads(b.text)
    labels = (sexpr.find_all(doc, "global_label")
              + sexpr.find_all(doc, "hierarchical_label")
              + sexpr.find_all(doc, "label"))
    if not labels:
        return None
    lab = labels[0]
    a = str(lab[1])
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
    for p in sorted(b.placement.parts, key=lambda p: p.ref):
        for pin in b.lib.get(p.lib_id).pins:
            pr = PinRef(p.ref, pin.number)
            if b.circuit.net_of(pr) is None:
                continue
            x, y = pin_page_position(pin, p.x, p.y, p.rotation)
            doc = sexpr.loads(b.text)
            nc = [Sym("no_connect"), [Sym("at"), x, y],
                  [Sym("uuid"), str(_uuid.uuid4())]]
            doc.insert(len(doc) - 1, nc)
            return (f"stray NC on netted pin {pr} @({x},{y})",
                    None, sexpr.dumps(doc) + "\n")
    return None


def _grid_point_on(seg) -> tuple[float, float]:
    mx = round(((seg.x0 + seg.x1) / 2) / GRID) * GRID
    my = round(((seg.y0 + seg.y1) / 2) / GRID) * GRID
    return (round(mx, 2), round(my, 2))


def mutate_foreign_junction(b: Built) -> tuple[str, None, str] | None:
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


def _rebuild_geo(b: Built) -> visual_gate.SheetGeometry:
    return visual_gate.SheetGeometry(
        boxes=list(b.geo.boxes),
        wires=[visual_gate.Seg(s.x0, s.y0, s.x1, s.y1, s.net)
               for s in b.routed.segs])


def mutate_geo_wire_crosses_foreign(b: Built):
    geo = _rebuild_geo(b)
    hs = [s for s in geo.wires if abs(s.y0 - s.y1) < 1e-6]
    vs = [s for s in geo.wires if abs(s.x0 - s.x1) < 1e-6]
    for v in vs:
        vy0, vy1 = sorted((v.y0, v.y1))
        for _i, h in enumerate(hs):
            if h.net == v.net:
                continue
            hx0, hx1 = sorted((h.x0, h.x1))
            ymid = round((vy0 + vy1) / 2, 3)
            if not (vy0 < ymid < vy1):
                continue
            span = max(hx1 - hx0, 2 * GRID)
            new = visual_gate.Seg(round(v.x0 - span / 2, 3), ymid,
                                  round(v.x0 + span / 2, 3), ymid, h.net)
            geo.wires[geo.wires.index(h)] = new
            return (f"geo: wire {h.net!r} shifted to cross foreign {v.net!r} "
                    f"@({v.x0},{ymid})", geo)
    return None


def mutate_geo_text_over_wire(b: Built):
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


@dataclass
class _Sheet:
    name: str
    circuit: Circuit


def _net_names_of(c: Circuit, ref: str) -> list[str]:
    return [n.name for n in c.nets.values()
            if any(pr.ref == ref for pr in n.pins)]


def _delete_part(c: Circuit, ref: str) -> None:
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


def _fixture_design_rules() -> list[_Sheet]:
    c = Circuit("selftest_dr", "selftest design-rule fixture")
    c.use_part("CP2102N-A02-GQFN24R", ref="U1", value="CP2102N")
    c.net("+3V3", "U1.5", "U1.7")
    c.net("+VDD_CORE", "U1.6")
    c.net("GND", "U1.2", "U1.25")
    c.decouple("U1.7", "100n")
    c.decouple("U1.5", "100n")
    c.decouple("U1.6", "100n")
    c.port("SC_I2C_SCL", "U1.20", kind="i2c", role="scl")
    c.pullup("U1.20", "4k7", "+3V3")
    c.net("SYS_RST_N", "U1.9")
    c.decouple("U1.9", "100n")
    c.pullup("U1.9", "10k", "+3V3")
    return [_Sheet("selftest_dr", c)]


def _fixture_ep(ep_net: str | None = "GND") -> list[_Sheet]:
    c = Circuit("selftest_ep", "selftest exposed-pad fixture")
    c.use_part("TLV75725PDYDR", ref="U1",
               footprint="TLV75725PDYDR:TLV75725PDYDR")
    c.net("+3V3", "U1.1", "U1.3")
    c.net("+2V5", "U1.5")
    c.nc("U1.4")
    c.net("GND", "U1.2")
    if ep_net is None:
        c.nc("U1.6")
    else:
        c.net(ep_net, "U1.6")
    return [_Sheet("selftest_ep", c)]


def _fixture_buck(draw_a: float = 0.5, rtop: str = "45k3") -> list[_Sheet]:
    c = Circuit("selftest_buck", "selftest power/thermal/spice fixture")
    c.part("U1", "Regulator_Switching:TPS54302", "TPS54302DDCR",
           "Package_TO_SOT_SMD:SOT-23-6")
    c.part("L1", "Device:L", "2.2uH")
    c.net("+VIN", "U1.3")
    c.net("SW", "U1.2", "L1.1")
    c.net("+3V3", "L1.2")
    c.net("GND", "U1.1")
    c.net("+5V_EN", "U1.5", net_class=NetClass.POWER)
    c.net("FB", "U1.4")
    c.series("+3V3", "FB", rtop)
    c.series("FB", "GND", "10k")
    c.draws("+3V3", draw_a, "selftest declared load")
    return [_Sheet("selftest_buck", c)]


def _fixture_testpoints() -> list[_Sheet]:
    c = Circuit("selftest_tp", "selftest test-point fixture")
    c.part("R1", "Device:R", "10k")
    c.net("+3V3", "R1.1")
    c.net("GND", "R1.2")
    c.testpoint("+3V3")
    c.testpoint("GND")
    return [_Sheet("selftest_tp", c)]


def _fixture_mounting_hole() -> Circuit:
    c = Circuit("selftest_mh", "selftest mounting-hole fixture")
    c.part("R1", "Device:R", "10k")
    c.net("CHASSIS_GND", "R1.1")
    c.net("+3V3", "R1.2")
    return c


def _fixture_rail_cap() -> Circuit:
    c = Circuit("selftest_railcap", "selftest rail-decoupling-cap fixture")
    c.part("R1", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric",
           LCSC="C114625")
    c.port("SIG_A", "R1.1")
    c.net("+3V3", "R1.2")
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric",
           LCSC="C14663")
    c.net("+3V3", "C1.1")
    c.net("GND", "C1.2")
    return c


def _fixture_esd_clamp() -> Circuit:
    c = Circuit("selftest_clamp", "selftest connector+ESD-clamp fixture")
    c.use_part("TPD4E02B04DQAR", ref="U1")
    c.part("J1", "Connector_Generic:Conn_01x04", "J",
           "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical")
    for i, io in enumerate(("IO1", "IO2", "IO3", "IO4"), start=1):
        c.port(f"SIG_{i}", f"J1.{i}", f"U1.{io}")
    c.net("GND", "U1.GND")
    c.nc("U1.NC")
    return c


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


def _mg_design_rules(which: str, lib: Library):
    from schgen.verify import design_rules

    def fires(res, rule: str) -> list[str]:
        return getattr(res, rule)

    base = _fixture_design_rules()
    base_res = design_rules.check(base, lib)
    if which == "drop_decap":
        rule, suffix, have, gnd = "decap", ":C", ("+VDD_CORE",), True
    elif which == "remove_pullup":
        rule, suffix, have, gnd = "i2c", ":R", ("SC_I2C_SCL", "+3V3"), False
    else:
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


def _mg_ep(which: str, lib: Library):
    from schgen.verify import design_rules
    base = design_rules.check(_fixture_ep("GND"), lib)
    base_ok = base.ok and not base.ep
    mut_net = None if which == "float_ep" else "+3V3"
    mut = design_rules.check(_fixture_ep(mut_net), lib)
    killed = bool(mut.ep) and not mut.ok
    by = mut.ep[0] if mut.ep else "(no finding)"
    desc = ("float_ep: nc the TLV75725 EP (pin 6)" if which == "float_ep"
            else "ep_to_power: net the TLV75725 EP onto +3V3 (non-GND)")
    return base_ok, killed, f"{desc}\n            by design_rules EP: {by}"


def _mg_cap_voltage(lib: Library):
    from schgen.verify import part_rules

    def fix(rail: str):
        c = Circuit("selftest_capv", "selftest cap-voltage fixture")
        c.part("C1", "Device:C", "10u",
               "Capacitor_SMD:C_0805_2012Metric", LCSC="C15850")
        c.net(rail, "C1.1", net_class=NetClass.POWER)
        c.net("GND", "C1.2")
        return [_Sheet("selftest_capv", c)]

    base = part_rules.analyze(fix("HDMI_RX_5V"))
    base_ok = base.ok
    mut = part_rules.analyze(fix("+VIN"))
    killed = (not mut.ok) and bool(mut.findings)
    by = mut.findings[0] if mut.findings else "(no finding)"
    return base_ok, killed, ("cap_voltage: 25 V MLCC HDMI_RX_5V (ok) -> +VIN "
                             f"20 V (25 < 2x20)\n            by part_rules: {by}")


def _mg_power_overrun(lib: Library):
    from schgen.verify import powertree
    base_ok = powertree.analyze(_fixture_buck()).ok
    mut = _fixture_buck()
    mut[0].circuit.loads["+3V3"] = [(4.0, "selftest overrun")]
    res = powertree.analyze(mut)
    killed = (not res.ok) and any("OVERRUN" in e for e in res.errors)
    by = res.errors[0] if res.errors else "(no error)"
    return base_ok, killed, ("power_overrun: +3V3 load 0.5A -> 4.0A (> 3 A "
                             f"limit)\n            by powertree: {by}")


def _mg_thermal(which: str, lib: Library):
    from schgen.verify import powertree, thermal

    def run(sheets):
        pt = powertree.analyze(sheets)
        return pt, thermal.analyze(sheets, pt_res=pt)

    _pt0, base = run(_fixture_buck())
    base_ok = base.ok and not base.errors and not base.notes
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
    c.waive_thermal("U1", "selftest: copper-pour derate not in single RthJA")
    pt, res = run(mut)
    demoted = res.ok and any("WAIVED over-limit" in n for n in res.notes)
    by = next((n for n in res.notes if "WAIVED over-limit" in n),
              "(not demoted)")
    return base_ok, demoted, ("thermal_waiver: same over-Tj + c.waive_thermal "
                              "-> demoted to a note, gate stays green"
                              f"\n            by thermal waiver path: {by[:90]}")


def _mg_divider_drift(lib: Library):
    from schgen.verify import spice
    base_ok = spice.extract_checks(_fixture_buck()).ok
    mut = _fixture_buck(rtop="33k")
    res = spice.extract_checks(mut)
    killed = (not res.ok) and any("FB" in e for e in res.errors)
    by = res.errors[0] if res.errors else "(no error)"
    return base_ok, killed, ("divider_drift: FB top 45k3 -> 33k (Vout leaves "
                             f"+/-3%)\n            by spice: {by}")


def _mg_tp_uncovered(lib: Library):
    from schgen.verify import testpoints
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
    from schgen.core.model import CircuitError, PinRef
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


def _mg_symbol_law(lib: Library):
    from schgen.verify import symbol_law

    def fix(real_part: bool):
        c = Circuit("selftest_symlaw", "selftest symbol-law fixture")
        c.part("R1", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
        c.net("+3V3", "R1.1", net_class=NetClass.POWER)
        c.net("GND", "R1.2")
        if real_part:
            c.part("U1", "schgen:LM61460", "LM61460",
                   "LM61460AANRJRR:LM61460AANRJRR")
            c.net("+VIN_SYS", "U1.8")
            c.net("GND", "U1.9")
        return c

    base = symbol_law.check([fix(real_part=False)], lib)
    base_ok = base.ok and not base.violations
    saved = dict(symbol_law.PENDING_MIGRATION)
    symbol_law.PENDING_MIGRATION.clear()
    try:
        mut = symbol_law.check([fix(real_part=True)], lib)
    finally:
        symbol_law.PENDING_MIGRATION.update(saved)
    killed = (not mut.ok) and any("schgen:LM61460" in v for v in mut.violations)
    by = mut.violations[0] if mut.violations else "(no violation)"
    return base_ok, killed, ("symbol_law: re-add hand-built schgen:LM61460 "
                             "real-part symbol (PENDING emptied)"
                             f"\n            by symbol_law: {by[:110]}")


def _mg_port_rename(lib: Library, tmp: Path):
    from schgen.generate import board

    def _placed(sheets, root="board"):
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
    _fx = _board_fixture_sheets()
    _fx_index = positional_sheet_index(sc.name for sc in _fx)
    base_ok = board.build_board(_fx, lib, base_out, root_name="board",
                                sheet_index=_fx_index)
    mut_out = tmp / "board_mut"
    board.build_board(_board_fixture_sheets(), lib, mut_out,
                      root_name="board", sheet_index=_fx_index)
    root = mut_out / "board.kicad_sch"
    txt = root.read_text()
    new = _re.sub(r'(\(global_label\s+)"SELFTEST_LINK"',
                  r'\1"SELFTEST_LINK_BROKEN"', txt, count=1)
    if new == txt:
        return base_ok, False, ("port_rename: could not find a SELFTEST_LINK "
                                "root label to rename")
    root.write_text(new)
    placed = _placed(_board_fixture_sheets())
    killed = not board._board_gate(placed, root, mut_out, lib)
    return base_ok, killed, ("port_rename: one SELFTEST_LINK root label -> "
                             "SELFTEST_LINK_BROKEN (its sheet pin keeps the "
                             "old name)\n            by board merge gate: PORT "
                             "no longer merges across the two sheets")


def _validated(c: Circuit, lib: Library) -> Circuit:
    c.validate({ref: set(lib.pin_numbers(p.lib_id))
                for ref, p in c.parts.items()})
    return c


def _mg_rail_decoup_dropped(lib: Library):
    base_ok = True
    try:
        place.build(_validated(_fixture_rail_cap(), lib), lib, place.Spacing())
    except place.PlaceError:
        base_ok = False
    orig = place._Engine._rail_decoupling_columns
    place._Engine._rail_decoupling_columns = lambda self: None
    killed = False
    by = "(no error)"
    try:
        place.build(_validated(_fixture_rail_cap(), lib), lib, place.Spacing())
    except place.PlaceError as e:
        killed = "unplaced" in str(e)
        by = str(e).splitlines()[0]
    finally:
        place._Engine._rail_decoupling_columns = orig
    return base_ok, killed, ("rail_decoup_dropped: stub _rail_decoupling_columns "
                             "-> the +3V3->GND cap is never drained"
                             f"\n            by placer missing-gate: {by[:90]}")


def _mg_clamp_thresh_strict(lib: Library):
    base_ok = True
    try:
        place.place_and_route(_validated(_fixture_esd_clamp(), lib), lib)
    except place.PlaceError:
        base_ok = False
    orig_run = place._Engine.run

    def strict_run(self):
        mset = set(self.multi)
        strict = []
        for ref in self.multi:
            sig = [n for n in self.c.nets.values()
                   if n.net_class in (NetClass.SIGNAL, NetClass.PORT)
                   and any(pr.ref == ref for pr in n.pins)]
            if sig and all(
                    len({pr.ref for pr in n.pins
                         if pr.ref in mset and pr.ref != ref}) >= 2
                    for n in sig):
                strict.append(ref)
        self.shunts = strict
        return orig_run(self)

    place._Engine.run = strict_run
    killed = False
    by = "(no error)"
    try:
        place.place_and_route(_validated(_fixture_esd_clamp(), lib), lib)
    except place.PlaceError as e:
        killed = True
        by = str(e).splitlines()[-1]
    finally:
        place._Engine.run = orig_run
    return base_ok, killed, ("clamp_thresh_strict: revert the clamp shunt rule "
                             "to >=2 -> the ESD array crosses lanes"
                             f"\n            by placer route/visual: {by[:90]}")


def _ratsnest_fixture():
    from schgen.generate.pcb import (
        ORIGIN_X,
        ORIGIN_Y,
        FootprintInst,
        PcbModel,
        resolve_mod,
    )
    fp = "Resistor_SMD:R_0603_1608Metric"
    mod = resolve_mod(fp)
    bw, bh = 60.0, 40.0

    def inst(ref, sheet, x, y, net):
        return FootprintInst(
            ref=ref, value="10k", footprint=fp,
            x=ORIGIN_X + x, y=ORIGIN_Y + y, rotation=0.0,
            pad_nets={"1": (1, net), "2": (2, "GND")}, mod_path=mod,
            sheet=sheet, side="top")

    insts = [
        inst("R1", "subsys_a", 8, 8, "A_SIG"),
        inst("R2", "subsys_a", 12, 8, "A_SIG"),
        inst("R3", "subsys_a", 10, 12, "A_SIG"),
        inst("R7", "subsys_a", 8, 12, "A_SIG"),
        inst("R4", "subsys_b", 48, 8, "A_SIG"),
        inst("R5", "subsys_b", 52, 8, "B_SIG"),
        inst("R6", "subsys_b", 50, 12, "B_SIG"),
    ]
    return PcbModel(
        board_w=bw, board_h=bh, insts=insts,
        net_numbers={"": 0, "A_SIG": 1, "B_SIG": 2, "GND": 3},
        netclass_of={}, classes={}, placed=len(insts), deferred=[],
        som_keepout=None, n_top=len(insts), n_bottom=0, two_side=True)


def _mg_ratsnest(which: str, lib: Library):
    from schgen.verify import ratsnest_gate
    base = ratsnest_gate.check(_ratsnest_fixture())
    base_ok = base.ok
    mut = _ratsnest_fixture()
    if which == "ratsnest_offboard":
        for i in mut.insts:
            if i.ref == "R6":
                i.x = i.x + 200.0
        res = ratsnest_gate.check(mut)
        killed = (not res.ok) and bool(res.off_board)
        by = res.off_board[0] if res.off_board else "(no off-board finding)"
        return base_ok, killed, ("ratsnest_offboard: shove R6 200 mm past "
                                 "Edge.Cuts\n            by LAW-5 gate: "
                                 f"{by[:90]}")
    spread = [(2, 2), (55, 2), (55, 36), (2, 36)]
    k = 0
    for i in mut.insts:
        if i.sheet == "subsys_a":
            from schgen.generate.pcb import ORIGIN_X, ORIGIN_Y
            i.x = ORIGIN_X + spread[k][0]
            i.y = ORIGIN_Y + spread[k][1]
            k += 1
    res = ratsnest_gate.check(mut)
    killed = (not res.ok) and bool(res.dispersed)
    by = res.dispersed[0] if res.dispersed else "(no dispersion finding)"
    return base_ok, killed, ("ratsnest_dispersed: scatter subsys_a across the "
                             "board\n            by LAW-5 gate: "
                             f"{by[:90]}")


def selftest_model_gates(tmp: Path) -> tuple[int, int, list[str]]:
    lib = Library()
    problems: list[str] = []
    print("--- model-gate mutants (design_rules / thermal / powertree / "
          "spice / testpoints / board / placer) ---")
    runners = [
        ("drop_decap",      lambda: _mg_design_rules("drop_decap", lib)),
        ("remove_pullup",   lambda: _mg_design_rules("remove_pullup", lib)),
        ("break_reset",     lambda: _mg_design_rules("break_reset", lib)),
        ("float_ep",        lambda: _mg_ep("float_ep", lib)),
        ("ep_to_power",     lambda: _mg_ep("ep_to_power", lib)),
        ("cap_voltage",     lambda: _mg_cap_voltage(lib)),
        ("thermal_overrun", lambda: _mg_thermal("thermal_overrun", lib)),
        ("thermal_waiver",  lambda: _mg_thermal("thermal_waiver", lib)),
        ("power_overrun",   lambda: _mg_power_overrun(lib)),
        ("divider_drift",   lambda: _mg_divider_drift(lib)),
        ("tp_uncovered",    lambda: _mg_tp_uncovered(lib)),
        ("mh_short",        lambda: _mg_mh_short(lib)),
        ("symbol_law",      lambda: _mg_symbol_law(lib)),
        ("port_rename",     lambda: _mg_port_rename(lib, tmp / "board")),
        ("rail_decoup_dropped", lambda: _mg_rail_decoup_dropped(lib)),
        ("clamp_thresh_strict", lambda: _mg_clamp_thresh_strict(lib)),
        ("ratsnest_offboard", lambda: _mg_ratsnest("ratsnest_offboard", lib)),
        ("ratsnest_dispersed", lambda: _mg_ratsnest("ratsnest_dispersed", lib)),
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


def determinism_check(path: Path, tmp: Path) -> tuple[bool, str]:
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
    import os
    import subprocess
    import sys
    code = ("import sys; from pathlib import Path; "
            "from schgen.verify.selftest import _build; "
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


def _resolve_sheet(spec: str) -> Path:
    p = Path(spec)
    if p.suffix == ".py" and p.exists():
        return p.resolve()
    cand = PROJECT_ROOT / "subsystems" / f"{spec}.py"
    if cand.exists():
        return cand
    raise SystemExit(f"selftest: sheet not found: {spec}")


def selftest_sheet(path: Path, tmp: Path) -> tuple[int, int, list[str]]:
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
        verdict = _run_stack(base.circuit, base.sch, base.lib, geo=mgeo)
        if verdict.green:
            problems.append(f"{name}: GEOMETRY MUTANT SURVIVED every gate: "
                            f"{desc}")
            print(f"  SURVIVED  {desc}   <-- HOLE IN THE VISUAL GATE")
        elif not any(f.startswith("visual gate") for f in verdict.failures):
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
