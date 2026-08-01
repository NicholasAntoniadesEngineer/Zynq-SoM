from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import NetClass

_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
       "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "R": 1.0, "": 1.0}

_VAL_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*([pnuµmkKMGR]?)(\d*)\s*(?:[RFHΩ]|mR)?$")


def parse_si(text: str) -> float | None:
    t = text.strip()
    if t.endswith("mR"):
        head = t[:-2]
        try:
            return float(head) * 1e-3
        except ValueError:
            return None
    m = _VAL_RE.match(t)
    if not m:
        return None
    whole, prefix, frac = m.groups()
    if frac:
        num = float(f"{whole}.{frac}")
    else:
        num = float(whole)
    return num * _SI.get(prefix, 1.0)


# first match wins: an exact-anchored rail must precede its generic prefix
_VOLT_PATTERNS: tuple[tuple[str, float], ...] = (
    (r"^\+VBUS_IN$", 20.0),
    (r"^\+VIN_SYS$", 20.0),
    (r"^\+VIN", 20.0),
    (r"^\+5V_SOM$", 4.65),
    (r"^\+5V_REG$", 5.0),
    (r"^\+5V", 5.0),
    (r"^USB_VBUS$", 5.0),
    (r"^USB_UART_VBUS$", 5.0),
    (r"^HDMI_RX_5V$", 5.0),
    (r"^HDMI_TX_CON_5V0$", 5.0),
    (r"^LCD_VLED_P$", 30.0),
    (r"^\+3V3_REG$", 3.3),
    (r"^\+3V3", 3.3),
    (r"^\+1V8_REG$", 1.8),
    (r"^\+1V8", 1.8),
    (r"^\+2V5", 2.5),
    (r"^\+VCCO_35$", 2.5),
    (r"^\+VCCO_", 3.3),
    (r"^VBUS$", 5.0),
)


def rail_volts(name: str) -> float | None:
    for pat, v in _VOLT_PATTERNS:
        if re.match(pat, name):
            return v
    return None


@dataclass(frozen=True)
class RegSpec:
    kind: str
    limit_a: float | None
    eff: float = 1.0
    in_pin: str = ""
    out_pin: str = ""
    iset_pin: str = ""
    ilim_num: float = 6800.0
    note: str = ""


REG_SPECS: dict[str, RegSpec] = {
    "TPS54302": RegSpec("buck", 3.0, eff=0.90, in_pin="3", out_pin="2",
                        note="TI 3 A synchronous buck (SW->L->rail); "
                             "thermal-gate test fixture"),
    "LM61460": RegSpec("buck", 6.0, eff=0.90, in_pin="8", out_pin="10",
                       note="TI 6 A 3-36V synchronous buck (VIN1=8 ->L<-SW=10 ->rail)"),
    "LMR33630": RegSpec("buck", 3.0, eff=0.90, in_pin="2", out_pin="8",
                        note="TI 3 A 36V synchronous buck (VIN=2, SW=8 ->L->rail)"),
    "AP2112K": RegSpec("ldo", 0.6, in_pin="1", out_pin="5",
                       note="600 mA LDO"),
    "TLV75725": RegSpec("ldo", 0.4, in_pin="1", out_pin="5",
                        note="1 A LDO held to 0.4 A continuous (PWR-3: DYD "
                             "thermal-pad, RthJA ~92.5 C/W EP-to-GND, Tj ~80 C "
                             "at 0.32 W/Ta=50 C — fmc.md section 3)"),
    "SY6280": RegSpec("load_switch", None, in_pin="IN", out_pin="OUT",
                      iset_pin="ISET", note="ILIM = 6800/RSET from netlist"),
    "TPS26631": RegSpec("efuse", None, in_pin="IN", out_pin="OUT",
                        iset_pin="ILIM", ilim_num=18000.0,
                        note="ILIM = 18/R_kohm from netlist (TPS2663 Eq 5)"),
}

SOURCES: dict[str, tuple[float, float, str]] = {
    "+VBUS_IN": (20.0, 3.0, "USB-C PD sink contract 20 V / 3 A at the "
                            "receptacle (pd_input J1; +VIN sits behind "
                            "the TPS26631 eFuse, round 5)"),
    "+3V3_SC": (3.3, 0.3, "SoM TPS7A20 always-on SC LDO U13 (J1.37); 300 mA "
                          "class — the SoM power_architecture sheet says "
                          "'3V3 (300mA)'. Envelope shared with the SoM-side "
                          "SC (STM32G431 ~50 mA); carrier tally only here"),
    "+5V_DBG": (5.0, 0.5, "debug USB-C VBUS (usb_jtag_connector J1) — host-"
                          "supplied 5 V / 0.5 A USB2 default; feeds the usb_jtag "
                          "AP2112K-3.3 debug-island LDO; isolated from carrier +5V"),
}

KNOWN_DEFERRED: dict[str, str] = {}


@dataclass
class Reg:
    n: int
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
    rails: dict[str, float] = field(default_factory=dict)
    draws: dict[str, list[tuple[str, float, str]]] = field(default_factory=dict)
    bridges: list[tuple[str, str, str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_load: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _pin_no(part, pin_spec: str) -> str | None:
    if part.pin_names and pin_spec in part.pin_names:
        nums = part.pin_names[pin_spec]
        return nums[0] if nums else None
    return pin_spec


def _net_on(c, ref: str, pin_no: str | None):
    from schgen.core.model import PinRef
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
            if spec.kind in ("load_switch", "efuse"):
                iset_net = _net_on(c, ref, _pin_no(part, spec.iset_pin))
                rset = None
                if iset_net is not None:
                    for pr in iset_net.pins:
                        rp = c.parts.get(pr.ref)
                        if rp is not None and rp.lib_id.endswith(":R"):
                            rset = parse_si(rp.value)
                if rset:
                    limit = round(spec.ilim_num / rset, 3)
                    note = (f"ILIM = {spec.ilim_num:.0f}/{rset:.0f}R = "
                            f"{limit*1000:.0f} mA")
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

    has_load = set(res.draws) | set(regs_by_vin)

    bridge_down: dict[str, list[str]] = {}
    for _s, _r, a, b in res.bridges:
        a_down, b_down = a in has_load, b in has_load
        if b_down and not a_down:
            up, down = a, b
        elif a_down and not b_down:
            up, down = b, a
        else:
            continue
        bridge_down.setdefault(up, []).append(down)

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
        for down in bridge_down.get(rail, []):
            total += rail_total(down)
        visiting.discard(rail)
        res.rails[rail] = round(total, 4)
        return res.rails[rail]

    for rail in sorted(all_rails):
        rail_total(rail)

    for reg in res.regs:
        if reg.i_out > reg.limit_a + 1e-9:
            res.errors.append(
                f"OVERRUN: {reg.sheet}:{reg.ref} ({reg.value}) "
                f"{reg.vin} -> {reg.vout}: load {reg.i_out:.3f} A > limit "
                f"{reg.limit_a:.3f} A ({reg.note})")

    for rail, (_v, amps, who) in SOURCES.items():
        load = res.rails.get(rail, 0.0)
        res.source_load[rail] = load
        if load > amps + 1e-9:
            res.errors.append(
                f"OVERRUN: source {rail} ({who}): load {load:.3f} A > "
                f"{amps:.3f} A")

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
    inlet = "+VBUS_IN"
    inlet_caps = _cap_farads_on(sheets, inlet)
    inlet_uf = sum(f for *_x, f in inlet_caps) * 1e6
    bulk_caps = _cap_farads_on(sheets, "+VIN")
    bulk_uf = sum(f for *_x, f in bulk_caps) * 1e6
    efuses = [r for r in res.regs if r.kind == "efuse" and r.vin == inlet]
    if not efuses:
        detail = " + ".join(f"{s}:{r}={v}" for s, r, v, _f in
                            inlet_caps + bulk_caps)
        res.findings.append(
            f"VBUS PRE-CONTRACT CAPACITANCE (decision needed — the round-5 "
            f"inlet eFuse is GONE from the netlist): the PD source sees "
            f"{inlet_uf + bulk_uf:.1f} uF un-switched ({detail}) vs the "
            f"~10 uF cSnkBulk guidance; restore an inrush-limited path "
            f"(TPS2663-class eFuse with dVdT control) between the "
            f"receptacle and the board bulk.")
        return
    if inlet_uf > 10.0:
        detail = " + ".join(f"{s}:{r}={v}" for s, r, v, _f in inlet_caps)
        res.findings.append(
            f"VBUS PRE-CONTRACT CAPACITANCE: {inlet} (ahead of the eFuse) "
            f"carries {inlet_uf:.1f} uF nominal ({detail}) — above the "
            f"~10 uF cSnkBulk guidance; keep the receptacle side lean and "
            f"let the dVdT eFuse charge the bulk.")
        return
    slew_note = ""
    for sc in sheets:
        c = sc.circuit
        for r in efuses:
            if r.sheet != sc.name:
                continue
            part = c.parts[r.ref]
            dvdt_net = _net_on(c, r.ref, _pin_no(part, "dVdT"))
            if dvdt_net is None:
                continue
            for pr in dvdt_net.pins:
                cp = c.parts.get(pr.ref)
                if cp is not None and cp.lib_id.endswith(":C"):
                    cdvdt = parse_si(cp.value)
                    if cdvdt:
                        slew = 1.0 / (20.8e3 * cdvdt)
                        inrush_ma = bulk_uf * 1e-6 * slew * 1e3
                        slew_note = (f"; dVdT {cp.value} -> slew "
                                     f"{slew / 1e3:.2f} V/ms, inrush into "
                                     f"the bulk ~{inrush_ma:.0f} mA")
    res.notes.append(
        f"VBUS pre-contract audit (round-4 flag, RESOLVED round 5): source "
        f"sees {inlet_uf:.2f} uF at the receptacle ({inlet}) — within the "
        f"~10 uF cSnkBulk guidance; {bulk_uf:.1f} uF board bulk sits "
        f"behind the {', '.join(f'{r.sheet}:{r.ref} {r.value}' for r in efuses)} "
        f"eFuse{slew_note}.")


def _som_parallel_rail_finding(sheets, res: Result) -> None:
    j1_rails = set()
    for sc in sheets:
        if not sc.name.startswith("som_j"):
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
            f"are OUTPUTS of carrier regulators (power.py LM61460/AP2112K) "
            f"AND appear on SoM J1 contract pins "
            f"(+3V3: J1.24-27, +1V8: J1.56/58/60) while the SoM's own Power "
            f"sheet regulates same-named rails on-module (MPM3834 stages "
            f"with 3V3_EN/PG + 1V8_EN/PG). If the SoM exports its rails on "
            f"those pins, linking them to the carrier's bucks puts two "
            f"regulators in parallel on one net — needs an explicit "
            f"decision (rename one side, sense-only pins, or drop one "
            f"source) before layout. Facts from som_interface.json + "
            f"som/schematic/Power.kicad_sch; nothing changed here.")


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
    if res.notes:
        lines += ["", f"notes — resolved audits, recomputed every run "
                      f"({len(res.notes)}):"]
        for n_ in res.notes:
            lines.append(f"  + {n_}")
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


_FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(res: Result, out: Path) -> Path:
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
    for _s, _r, a, b in res.bridges:
        if a in depth and b not in depth:
            depth[b] = depth[a] + 1
    orphans = [r for r in sorted(res.rails) if r not in depth]

    cols: dict[int, list[str]] = {}
    for rail, d in depth.items():
        cols.setdefault(d, []).append(rail)
    maxd = max(cols) if cols else 0
    BOX_W, ROW_H, COL_W = 190, 40, 330
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
    for _s, _r, a, b in res.bridges:
        if a not in pos or b not in pos:
            continue
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        e.append(f'<line x1="{x0 + BOX_W}" y1="{y0 + ROW_H // 2}" '
                 f'x2="{x1}" y2="{y1 + ROW_H // 2}" stroke="#9ca3af" '
                 f'stroke-width="1.5" stroke-dasharray="5,4"/>')

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

    e.append(f'<text x="30" y="{oy}" font-weight="bold" fill="#6b7280">'
             f'unsourced rails (PLAN deferrals / findings):</text>')
    for i, rail in enumerate(orphans):
        e.append(f'<text x="{30 + (i % 4) * 200}" '
                 f'y="{oy + 18 + 18 * (i // 4)}" fill="#6b7280">'
                 f'{_esc(rail)} ({res.rails.get(rail, 0.0):.3f} A)</text>')

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


def run(sheets, reports_dir: Path, docs_dir: Path) -> Result:
    res = analyze(sheets)
    txt = report(res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "power_tree.txt").write_text(txt + "\n")
    render_svg(res, docs_dir / "power_tree.svg")
    return res


def cmd_powertree(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports", repo / "carrier" / "docs")
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'power_tree.txt'}")
    print(f"diagram: {repo / 'carrier' / 'docs' / 'power_tree.svg'}")
    return 0 if res.ok else 1
