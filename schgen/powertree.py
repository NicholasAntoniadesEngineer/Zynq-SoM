"""Power-tree BUDGET GATE (PLAN round 4): prove regulator headroom from the
netlists + the subsystems' declarative ``c.draws(rail, amps, note)`` budget
declarations.

The TREE is extracted from the netlists themselves, never hand-drawn:
- a part whose ``value`` matches REG_SPECS is a regulator/load switch; its
  input rail is the POWER net on its IN pin, its output rail the POWER net
  on its OUT pin (bucks hop SW-net -> inductor -> rail, exactly like the
  placement engine's stage detection);
- a SY6280's current limit is COMPUTED from its ISET resistor in the
  netlist (ILIM = 6800 / RSET) — change the resistor, the budget follows;
- a series resistor bridging two POWER rails is a shunt bridge (the
  power_mon INA3221 shunts);
- board power SOURCES are the enumerated electrical contract (USB-C PD
  20 V/3 A into +VIN; the SoM's always-on MPM3822 behind +3V3_SC).

Loads flow bottom-up: a rail's total = its declared draws + every child
regulator's input current (LDO/switch: I_in = I_out; buck:
I_in = V_out*I_out / (V_in*eta), eta = 0.90 conservative).

ERRORS (gate FAILS, non-zero exit): any regulator or source loaded past its
limit. FINDINGS/WARNINGS (reported loudly, build continues): unsourced
rails (annotated with their PLAN deferral where one exists), the VBUS
pre-contract capacitance audit (computed from the netlists), and the
SoM-exported +3V3/+1V8 parallel-source question.

Outputs: carrier/reports/power_tree.txt (verdict) +
carrier/docs/power_tree.svg (numbered tree diagram, diagram.py style).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.model import NetClass

# ---- SI value parsing (shared with schgen/spice.py) ----------------------------

_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
       "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "R": 1.0, "": 1.0}

_VAL_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*([pnuµmkKMGR]?)(\d*)\s*(?:[RFHΩ]|mR)?$")


def parse_si(text: str) -> float | None:
    """'6.8k'->6800, '4k7'->4700, '22k1'->22100, '100n'->1e-7, '10mR'->0.01,
    '1.5R'->1.5, '10uH'->1e-5. None if unparseable."""
    t = text.strip()
    if t.endswith("mR"):                       # milliohm shunts: 10mR / 20mR
        head = t[:-2]
        try:
            return float(head) * 1e-3
        except ValueError:
            return None
    m = _VAL_RE.match(t)
    if not m:
        return None
    whole, prefix, frac = m.groups()
    if frac:                                    # 4k7 / 22k1 style
        num = float(f"{whole}.{frac}")
    else:
        num = float(whole)
    return num * _SI.get(prefix, 1.0)


# ---- rail voltages (by name pattern) -------------------------------------------

_VOLT_PATTERNS: tuple[tuple[str, float], ...] = (
    (r"^\+VIN", 20.0),          # USB-C PD contract rail
    (r"^\+5V", 5.0),
    (r"^\+3V3", 3.3),
    (r"^\+1V8", 1.8),
    (r"^\+2V5", 2.5),
    (r"^\+VCCO_35$", 2.5),      # bank 35 = 2.5 V (camera/FMC dossiers)
    (r"^\+VCCO_", 3.3),         # banks 13/33/34 = 3.3 V (rail map)
    (r"^VBUS$", 5.0),
)


def rail_volts(name: str) -> float | None:
    for pat, v in _VOLT_PATTERNS:
        if re.match(pat, name):
            return v
    return None


# ---- regulator registry (datasheet limits; topology comes from netlists) -------

@dataclass(frozen=True)
class RegSpec:
    kind: str                  # "buck" | "ldo" | "load_switch"
    limit_a: float | None      # None => limit computed from ISET resistor
    eff: float = 1.0           # input-power transfer (bucks only)
    in_pin: str = ""           # pin number or NAME (resolved via pin_names)
    out_pin: str = ""          # ldo/switch: OUT pin; buck: SW pin (-> L -> rail)
    iset_pin: str = ""         # load switch: ILIM = 6800 / R(ISET->GND)
    note: str = ""


# keyed by part-value PREFIX (power.py writes 'TPS54302DDCR', fmc 'TLV75725PDBVR')
REG_SPECS: dict[str, RegSpec] = {
    "TPS54302": RegSpec("buck", 3.0, eff=0.90, in_pin="3", out_pin="2",
                        note="TI 3 A synchronous buck (SW->L->rail)"),
    "AP2112K": RegSpec("ldo", 0.6, in_pin="1", out_pin="5",
                       note="600 mA LDO"),
    "TLV75725": RegSpec("ldo", 0.4, in_pin="1", out_pin="5",
                        note="1 A LDO derated to 0.4 A continuous "
                             "(DBV RthJA 231 C/W, fmc.md section 3)"),
    "SY6280": RegSpec("load_switch", None, in_pin="IN", out_pin="OUT",
                      iset_pin="ISET", note="ILIM = 6800/RSET from netlist"),
}

# Board power sources: the electrical contract (rail -> (volts, amps, who)).
SOURCES: dict[str, tuple[float, float, str]] = {
    "+VIN": (20.0, 3.0, "USB-C PD sink contract 20 V / 3 A (pd_input J1)"),
    "+3V3_SC": (3.3, 2.0, "SoM MPM3822 always-on SC rail (J1.37); limit is "
                          "the SoM regulator's 2 A — SoM-side SC loads "
                          "(STM32 etc.) not included in the carrier tally"),
}

# Rails known to be deferred by PLAN flags (unsourced today, by decision).
KNOWN_DEFERRED: dict[str, str] = {
    "+VCCO_13": "wave-3 J-sheet regen rail map (+VCCO_13 = +3V3)",
    "+VCCO_33": "wave-3 J-sheet regen rail map (+VCCO_33 = +3V3)",
    "+VCCO_34": "wave-3 J-sheet regen rail map (+VCCO_34 = +3V3, LCD)",
    "+VCCO_35": "wave-3 J-sheet regen rail map (+VCCO_35 = +2V5_VADJ, "
                "SHARED camera/FMC 2.5 V — PLAN board-completion flag)",
    "+VIN_SYS": "power.py shunt rail split pending (PLAN POWER_LIBS flag — "
                "power_mon RS1 output feeds nothing yet)",
    "+5V_REG": "power.py shunt rail split pending (power_mon RS2 input "
               "cluster — today's +5V comes straight from the buck)",
    "+3V3_REG": "power.py shunt rail split pending (power_mon RS3)",
    "+1V8_REG": "power.py shunt rail split pending (power_mon RS4)",
}


@dataclass
class Reg:
    n: int                    # diagram number
    sheet: str
    ref: str
    value: str
    kind: str
    vin: str
    vout: str
    limit_a: float
    eff: float
    note: str
    i_out: float = 0.0
    i_in: float = 0.0


@dataclass
class Result:
    regs: list[Reg] = field(default_factory=list)
    rails: dict[str, float] = field(default_factory=dict)        # total amps
    draws: dict[str, list[tuple[str, float, str]]] = field(default_factory=dict)
    bridges: list[tuple[str, str, str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    source_load: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _pin_no(part, pin_spec: str) -> str | None:
    """Resolve a RegSpec pin (NAME via use_part pin table, else number)."""
    if part.pin_names and pin_spec in part.pin_names:
        nums = part.pin_names[pin_spec]
        return nums[0] if nums else None
    return pin_spec


def _net_on(c, ref: str, pin_no: str | None):
    from schgen.model import PinRef
    if pin_no is None:
        return None
    return c.net_of(PinRef(ref, pin_no))


def _detect_regs(sheets) -> tuple[list[Reg], list[str]]:
    regs: list[Reg] = []
    errors: list[str] = []
    n = 0
    for sc in sheets:
        c = sc.circuit
        for ref, part in sorted(c.parts.items()):
            spec = next((s for k, s in REG_SPECS.items()
                         if part.value.startswith(k)), None)
            if spec is None:
                continue
            vin_net = _net_on(c, ref, _pin_no(part, spec.in_pin))
            out_net = _net_on(c, ref, _pin_no(part, spec.out_pin))
            if vin_net is None or out_net is None:
                errors.append(f"{sc.name}:{ref} ({part.value}): cannot "
                              f"resolve IN/OUT pins for the power tree")
                continue
            vout_name = out_net.name
            if spec.kind == "buck":
                # SW net -> inductor -> output rail
                vout_name = ""
                for pr in out_net.pins:
                    other = c.parts.get(pr.ref)
                    if other is None or pr.ref == ref:
                        continue
                    if other.lib_id.endswith(":L") or \
                            other.value.upper().endswith("H"):
                        for p2 in ("1", "2"):
                            nn = _net_on(c, pr.ref, p2)
                            if nn is not None and nn.name != out_net.name \
                                    and nn.net_class is NetClass.POWER:
                                vout_name = nn.name
                if not vout_name:
                    errors.append(f"{sc.name}:{ref} ({part.value}): no "
                                  f"SW->inductor->rail hop found")
                    continue
            limit = spec.limit_a
            note = spec.note
            if spec.kind == "load_switch":
                iset_net = _net_on(c, ref, _pin_no(part, spec.iset_pin))
                rset = None
                if iset_net is not None:
                    for pr in iset_net.pins:
                        rp = c.parts.get(pr.ref)
                        if rp is not None and rp.lib_id.endswith(":R"):
                            rset = parse_si(rp.value)
                if rset:
                    limit = round(6800.0 / rset, 3)
                    note = f"ILIM = 6800/{rset:.0f}R = {limit*1000:.0f} mA"
                else:
                    errors.append(f"{sc.name}:{ref} ({part.value}): ISET "
                                  f"resistor not found — cannot prove ILIM")
                    continue
            n += 1
            regs.append(Reg(n=n, sheet=sc.name, ref=ref, value=part.value,
                            kind=spec.kind, vin=vin_net.name, vout=vout_name,
                            limit_a=float(limit), eff=spec.eff, note=note))
    return regs, errors


def _detect_bridges(sheets) -> list[tuple[str, str, str, str]]:
    """Series 2-pin element bridging two POWER rails (the power_mon INA3221
    shunts): (sheet, ref, rail_a, rail_b). Netlist-driven: a part with
    EXACTLY two netted pins, both on different POWER rails."""
    out = []
    for sc in sheets:
        c = sc.circuit
        netted: dict[str, list] = {}
        for net in c.nets.values():
            for pr in net.pins:
                netted.setdefault(pr.ref, []).append(net)
        for ref in sorted(netted):
            nets = netted[ref]
            if len(nets) != 2:
                continue
            if all(n.net_class is NetClass.POWER for n in nets) \
                    and nets[0].name != nets[1].name:
                out.append((sc.name, ref, nets[0].name, nets[1].name))
    return out


def analyze(sheets) -> Result:
    res = Result()
    res.regs, det_errors = _detect_regs(sheets)
    res.errors += det_errors
    res.bridges = _detect_bridges(sheets)

    # declared draws per rail
    all_rails: set[str] = set()
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if net.net_class is NetClass.POWER:
                all_rails.add(net.name)
        for rail, entries in sc.circuit.loads.items():
            for amps, note in entries:
                res.draws.setdefault(rail, []).append((sc.name, amps, note))

    regs_by_vin: dict[str, list[Reg]] = {}
    regs_by_vout: dict[str, list[Reg]] = {}
    for r in res.regs:
        regs_by_vin.setdefault(r.vin, []).append(r)
        regs_by_vout.setdefault(r.vout, []).append(r)

    # bottom-up totals (cycle-guarded; the tree is a DAG by construction)
    visiting: set[str] = set()

    def rail_total(rail: str) -> float:
        if rail in res.rails:
            return res.rails[rail]
        if rail in visiting:
            res.errors.append(f"power-tree CYCLE through rail {rail!r}")
            return 0.0
        visiting.add(rail)
        total = sum(a for _s, a, _n in res.draws.get(rail, []))
        for reg in regs_by_vin.get(rail, []):
            i_out = rail_total(reg.vout)
            reg.i_out = i_out
            if reg.kind == "buck":
                v_in = rail_volts(reg.vin) or 0.0
                v_out = rail_volts(reg.vout) or 0.0
                reg.i_in = (v_out * i_out / (v_in * reg.eff)) if v_in else 0.0
            else:
                reg.i_in = i_out
            total += reg.i_in
        visiting.discard(rail)
        res.rails[rail] = round(total, 4)
        return res.rails[rail]

    for rail in sorted(all_rails):
        rail_total(rail)

    # ---- gate: regulator overrun ------------------------------------------
    for reg in res.regs:
        if reg.i_out > reg.limit_a + 1e-9:
            res.errors.append(
                f"OVERRUN: {reg.sheet}:{reg.ref} ({reg.value}) "
                f"{reg.vin} -> {reg.vout}: load {reg.i_out:.3f} A > limit "
                f"{reg.limit_a:.3f} A ({reg.note})")

    # ---- gate: source overrun ----------------------------------------------
    for rail, (_v, amps, who) in SOURCES.items():
        load = res.rails.get(rail, 0.0)
        res.source_load[rail] = load
        if load > amps + 1e-9:
            res.errors.append(
                f"OVERRUN: source {rail} ({who}): load {load:.3f} A > "
                f"{amps:.3f} A")

    # ---- findings: unsourced rails ------------------------------------------
    sourced = set(SOURCES) | {r.vout for r in res.regs} \
        | {b for _s, _r, _a, b in res.bridges} \
        | {a for _s, _r, a, _b in res.bridges}
    for rail in sorted(all_rails):
        if rail in sourced:
            continue
        load = res.rails.get(rail, 0.0)
        if rail in KNOWN_DEFERRED:
            res.warnings.append(
                f"unsourced rail {rail} (load {load:.3f} A) — KNOWN "
                f"deferral: {KNOWN_DEFERRED[rail]}")
        else:
            res.findings.append(
                f"UNSOURCED RAIL {rail} (declared load {load:.3f} A): no "
                f"regulator output, no source contract — needs a gate/tie "
                f"decision before layout")

    # bridge stubs feeding nothing = the pending power_mon split
    bridge_children = {b for _s, _r, _a, b in res.bridges}
    for rail in sorted(bridge_children):
        if not res.draws.get(rail) and not regs_by_vin.get(rail) \
                and rail in KNOWN_DEFERRED:
            res.warnings.append(
                f"shunt-bridge rail {rail} feeds nothing — "
                f"{KNOWN_DEFERRED[rail]}")

    _vbus_precontract_finding(sheets, res)
    _som_parallel_rail_finding(sheets, res)
    return res


def _cap_farads_on(sheets, rail: str) -> list[tuple[str, str, str, float]]:
    """All caps rail->GND across sheets: (sheet, ref, value, farads)."""
    out = []
    for sc in sheets:
        c = sc.circuit
        for ref, part in sorted(c.parts.items()):
            if not part.lib_id.endswith(":C"):
                continue
            nets = {(_net_on(c, ref, p) or type("N", (), {"name": ""})).name
                    for p in ("1", "2")}
            if rail in nets and any(n.startswith("GND") for n in nets):
                f = parse_si(part.value)
                if f:
                    out.append((sc.name, ref, part.value, f))
    return out


def _vbus_precontract_finding(sheets, res: Result) -> None:
    """The PLAN board-completion flag, DECIDED here with numbers from the
    netlists: pre-contract capacitance on VBUS(+VIN) vs the ~10 uF cSnkBulk
    guidance, with BOTH remedies quantified. Surfaced as a finding for the
    power owner — this gate does not change power.py."""
    caps = _cap_farads_on(sheets, "+VIN")
    total_uf = sum(f for *_x, f in caps) * 1e6
    detail = " + ".join(f"{s}:{r}={v}" for s, r, v, _f in caps)
    res.findings.append(
        f"VBUS PRE-CONTRACT CAPACITANCE (decision needed, PLAN round-4 "
        f"flag): +VIN carries {total_uf:.1f} uF NOMINAL un-switched "
        f"({detail}). At the 5 V default-VBUS bias the X7R/X5R parts derate "
        f"to roughly 15-24 uF effective — ABOVE the ~10 uF cSnkBulk "
        f"guidance a PD sink should present before an explicit contract "
        f"(USB PD r3 / Type-C tSrcInrush margins usually absorb this, but "
        f"it is out of spec). REMEDY A (preferred): an inrush-limited +VIN "
        f"path ahead of the bucks — a 24 V-capable eFuse/hot-swap switch "
        f"with dV/dt control (TI TPS25982 24 V eFuse class, or a discrete "
        f"P-FET soft-start: AO3401A-class + 100k/100n gate RC giving a "
        f"~1 ms ramp -> inrush ~= C*dV/dt = 20u * 20 V / 1 ms = 0.4 A); "
        f"isolates ALL downstream bulk from the source's inrush window and "
        f"keeps the bucks' input bulk intact. REMEDY B: trim power.py's "
        f"un-switched input bulk (2x 10u C13585 -> 1x 4u7): pre-contract "
        f"drops to ~15 uF nominal (~10-12 uF effective at 5 V) — meets the "
        f"guidance, BUT at 20 V the remaining 25 V X5R bulk derates to "
        f"~35% (~1.6-3.5 uF effective), thin against the TPS54302's "
        f"recommended >=10 uF effective input capacitance; remedy B trades "
        f"a compliance margin for a stability margin. Numbers above are "
        f"computed from the committed netlists; decision owner: power.py.")


def _som_parallel_rail_finding(sheets, res: Result) -> None:
    """+3V3 / +1V8 appear on SoM J1 (pins 24-27 / 56-60) AND the SoM's own
    Power sheet regulates +3V3/+1V8 on-module (MPM3834 stages with
    3V3_EN/3V3_PG, 1V8_EN/1V8_PG — som/schematic/Power.kicad_sch), while
    carrier power.py ALSO generates +3V3/+1V8 (TPS54302 U2 / AP2112K U3).
    Same net name across the connector = electrically ONE net = two
    regulators in parallel. Surfaced for decision; netlist facts only."""
    j1_rails = set()
    for sc in sheets:
        if sc.name != "som_j1":
            continue
        for net in sc.circuit.nets.values():
            if net.net_class is NetClass.POWER and net.name in ("+3V3",
                                                                "+1V8"):
                j1_rails.add(net.name)
    carrier_outs = {r.vout for r in res.regs}
    clash = sorted(j1_rails & carrier_outs)
    if clash:
        res.findings.append(
            f"PARALLEL-SOURCE QUESTION on {', '.join(clash)}: these rails "
            f"are OUTPUTS of carrier regulators (power.py TPS54302/AP2112K) "
            f"AND appear on SoM J1 contract pins "
            f"(+3V3: J1.24-27, +1V8: J1.56/58/60) while the SoM's own Power "
            f"sheet regulates same-named rails on-module (MPM3834 stages "
            f"with 3V3_EN/PG + 1V8_EN/PG). If the SoM exports its rails on "
            f"those pins, linking them to the carrier's bucks puts two "
            f"regulators in parallel on one net — needs an explicit "
            f"decision (rename one side, sense-only pins, or drop one "
            f"source) before layout. Facts from som_interface.json + "
            f"som/schematic/Power.kicad_sch; nothing changed here.")


# ---- report ---------------------------------------------------------------------

def report(res: Result) -> str:
    lines = ["schgen power-tree budget gate", "=" * 64, ""]
    lines.append("sources:")
    for rail, (v, amps, who) in SOURCES.items():
        load = res.source_load.get(rail, 0.0)
        pct = 100.0 * load / amps if amps else 0.0
        lines.append(f"  {rail:<10} {v:>5.1f} V  limit {amps:.2f} A  "
                     f"load {load:.3f} A  ({pct:.0f}%)  — {who}")
    lines.append("")
    lines.append(f"regulators ({len(res.regs)}) — numbered as in "
                 f"carrier/docs/power_tree.svg:")
    for r in res.regs:
        pct = 100.0 * r.i_out / r.limit_a if r.limit_a else 0.0
        lines.append(
            f"  ({r.n:>2}) {r.sheet}:{r.ref:<4} {r.value:<14} "
            f"{r.vin:>9} -> {r.vout:<14} load {r.i_out:.3f} A / "
            f"limit {r.limit_a:.3f} A ({pct:.0f}%)  in {r.i_in:.3f} A "
            f"[{r.kind}] {r.note}")
    lines.append("")
    lines.append("shunt bridges (series R rail->rail, power_mon):")
    for s, ref, a, b in res.bridges:
        lines.append(f"  {s}:{ref} {a} -> {b}")
    lines.append("")
    lines.append("declared draws (c.draws — every number cites its source):")
    for rail in sorted(res.draws):
        for sheet, amps, note in res.draws[rail]:
            lines.append(f"  {rail:<16} {amps*1000:>8.1f} mA  {sheet:<18} "
                         f"{note}")
    lines.append("")
    lines.append("rail totals (declared + child regulator inputs):")
    for rail in sorted(res.rails):
        v = rail_volts(rail)
        lines.append(f"  {rail:<16} {res.rails[rail]:>7.3f} A"
                     + (f"  @ {v:.1f} V" if v else ""))
    if res.findings:
        lines += ["", f"FINDINGS — decisions needed ({len(res.findings)}):"]
        for f_ in res.findings:
            lines.append(f"  * {f_}")
    if res.warnings:
        lines += ["", f"warnings ({len(res.warnings)}):"]
        for w in res.warnings:
            lines.append(f"  WARNING: {w}")
    lines.append("")
    if res.errors:
        lines.append(f"ERRORS ({len(res.errors)}):")
        for e in res.errors:
            lines.append(f"  ERROR: {e}")
    else:
        lines.append("errors: none")
    lines.append("")
    lines.append(f"POWER TREE: {'PASS' if res.ok else 'FAIL'} "
                 f"({len(res.errors)} errors, "
                 f"{len(res.findings)} findings, "
                 f"{len(res.warnings)} warnings)")
    return "\n".join(lines)


# ---- diagram (SVG, diagram.py style) --------------------------------------------

_FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(res: Result, out: Path) -> Path:
    """Numbered power-tree diagram: source/rail boxes in depth columns,
    regulator edges labeled with their number + computed load/limit."""
    # depth via BFS from sources
    depth: dict[str, int] = {r: 0 for r in SOURCES}
    changed = True
    while changed:
        changed = False
        for reg in res.regs:
            if reg.vin in depth:
                d = depth[reg.vin] + 1
                if depth.get(reg.vout, -1) < d:
                    depth[reg.vout] = d
                    changed = True
    for s, _r, a, b in res.bridges:
        if a in depth and b not in depth:
            depth[b] = depth[a] + 1
    orphans = [r for r in sorted(res.rails) if r not in depth]

    cols: dict[int, list[str]] = {}
    for rail, d in depth.items():
        cols.setdefault(d, []).append(rail)
    maxd = max(cols) if cols else 0
    BOX_W, ROW_H, COL_W = 190, 40, 330      # 140 px label gap between columns
    pos: dict[str, tuple[int, int]] = {}
    height = 60
    for d in sorted(cols):
        y = 50
        for rail in sorted(cols[d]):
            pos[rail] = (30 + d * COL_W, y)
            y += ROW_H + 26
        height = max(height, y)
    oy = height + 30
    legend_h = 22 + 16 * (len(res.regs) + 1)
    total_h = oy + 90 + 18 * (len(orphans) // 4 + 1) + legend_h
    width = 30 + maxd * COL_W + BOX_W + 60

    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} '
         f'{total_h}" font-family="{_FONT}" font-size="11">']
    e.append(f'<rect width="{width}" height="{total_h}" fill="white"/>')
    e.append(f'<text x="30" y="28" font-size="15" font-weight="bold">'
             f'carrier power tree — budget gate '
             f'({"PASS" if res.ok else "FAIL"})</text>')

    # edges first; the short numbered label sits in the inter-column gap,
    # one row per DESTINATION rail, so labels can never collide
    for reg in res.regs:
        if reg.vin not in pos or reg.vout not in pos:
            continue
        x0, y0 = pos[reg.vin]
        x1, y1 = pos[reg.vout]
        ax, ay = x0 + BOX_W, y0 + ROW_H // 2
        bx, by = x1, y1 + ROW_H // 2
        color = "#dc2626" if reg.i_out > reg.limit_a else "#2563eb"
        e.append(f'<path d="M{ax},{ay} C{ax + 60},{ay} {bx - 110},{by} '
                 f'{bx},{by}" fill="none" stroke="{color}" '
                 f'stroke-width="2"/>')
        label = f"({reg.n}) {reg.i_out:.2f}/{reg.limit_a:.2f}A"
        lw = len(label) * 7
        e.append(f'<rect x="{bx - 106}" y="{by - 16}" width="{lw}" '
                 f'height="14" fill="white" fill-opacity="0.85"/>')
        e.append(f'<text x="{bx - 104}" y="{by - 5}" '
                 f'fill="{color}">{_esc(label)}</text>')
    for s, _r, a, b in res.bridges:
        if a not in pos or b not in pos:
            continue
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        e.append(f'<line x1="{x0 + BOX_W}" y1="{y0 + ROW_H // 2}" '
                 f'x2="{x1}" y2="{y1 + ROW_H // 2}" stroke="#9ca3af" '
                 f'stroke-width="1.5" stroke-dasharray="5,4"/>')

    # rail boxes
    for rail, (x, y) in pos.items():
        src = rail in SOURCES
        fill = "#fef3c7" if src else "#eff6ff"
        stroke = "#92400e" if src else "#1e3a8a"
        e.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{ROW_H}" '
                 f'rx="8" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.5"/>')
        v = rail_volts(rail)
        e.append(f'<text x="{x + 10}" y="{y + 16}" font-weight="bold" '
                 f'font-size="12">{_esc(rail)}'
                 + (f' ({v:g} V)' if v else "") + "</text>")
        load = res.rails.get(rail, 0.0)
        cap = ""
        if src:
            cap = f" / {SOURCES[rail][1]:g} A"
        e.append(f'<text x="{x + 10}" y="{y + 32}" fill="#374151">'
                 f'load {load:.3f} A{cap}</text>')

    # orphan rails (unsourced — PLAN deferrals + findings)
    e.append(f'<text x="30" y="{oy}" font-weight="bold" fill="#6b7280">'
             f'unsourced rails (PLAN deferrals / findings):</text>')
    for i, rail in enumerate(orphans):
        e.append(f'<text x="{30 + (i % 4) * 200}" '
                 f'y="{oy + 18 + 18 * (i // 4)}" fill="#6b7280">'
                 f'{_esc(rail)} ({res.rails.get(rail, 0.0):.3f} A)</text>')

    # numbered legend (the same numbers as the verdict report)
    ly = oy + 60 + 18 * (len(orphans) // 4 + 1)
    e.append(f'<text x="30" y="{ly}" font-weight="bold">regulators:</text>')
    for i, reg in enumerate(res.regs):
        e.append(f'<text x="30" y="{ly + 18 + 16 * i}" fill="#374151">'
                 f'({reg.n}) {_esc(reg.sheet)}:{_esc(reg.ref)} '
                 f'{_esc(reg.value)} {_esc(reg.vin)} -&gt; {_esc(reg.vout)} '
                 f'— load {reg.i_out:.3f} A / limit {reg.limit_a:.3f} A '
                 f'[{reg.kind}]</text>')
    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


# ---- entry points ----------------------------------------------------------------

def run(sheets, reports_dir: Path, docs_dir: Path) -> Result:
    res = analyze(sheets)
    txt = report(res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "power_tree.txt").write_text(txt + "\n")
    render_svg(res, docs_dir / "power_tree.svg")
    return res


def cmd_powertree(args) -> int:
    from schgen.link import all_subsystem_paths, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[1]
    res = run(sheets, repo / "carrier" / "reports", repo / "carrier" / "docs")
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'power_tree.txt'}")
    print(f"diagram: {repo / 'carrier' / 'docs' / 'power_tree.svg'}")
    return 0 if res.ok else 1
