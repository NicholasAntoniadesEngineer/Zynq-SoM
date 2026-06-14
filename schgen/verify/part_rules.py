"""part_rules — per-part RATING gate (verification).

design_rules.py checks that a decap/pull/strap EXISTS; thermal.py checks Tj.
Neither checks whether a part is RATED for the stress the netlist puts on it: a
ceramic cap below (or insufficiently derated above) its rail voltage, a resistor
past its package power, a regulator driven beyond its input abs-max. This gate
adds that layer. Ratings come from schgen/ratings.py (LCSC-keyed; EasyEDA gives
no structured ratings and the load-bearing passives are inline c.part(...,
LCSC=...) with no parts/ folder, so LCSC is the primary key); the regulator tree
+ rail voltages are reused from schgen.powertree (never recomputed).

ENFORCED rules (hard FAIL), chosen so the CURRENT board passes (it already
self-derates: the +VIN 20 V bulk is a 50 V part, the LCD boost-out is 50 V):
  CAP_VOLTAGE  ceramic v_max >= 2x rail (DC-bias droop); C0G/NP0 >= 1.5x;
               electrolytic/tantalum >= 1.5x.
  IC_VIN       regulator/eFuse/load-switch/LDO vin_max (abs-max) >= the rail it
               runs from (reused from powertree's Reg.vin).
ADVISORY rules (reported as NOTES, never fail — too many shunt/divider edge
cases to enforce a worst-case power model without false positives):
  RES_POWER    resistor P = dV^2/R vs 2x-derated p_max, only when BOTH pins
               resolve to a known voltage.

FAIL-SOFT: a part with no ratings, or whose rail does not resolve, is reported
UNSPEC and does NOT fail the gate (the testpoints.py idiom) — coverage is
visible without blocking the board. A genuine tight-margin exception is
``c.waive_part_rule(ref, reason)`` (verbatim in the report, never silence; LAW
4 — never relax a derate, waive the one part). Deterministic; no timestamps.
Report: carrier/reports/part_rules.txt. Run: ``python -m schgen part-rules``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen import powertree
from schgen.ratings import RATINGS_BY_LCSC, Ratings

# ---- derating policy (LAW 4: a tight exception is WAIVED, never relaxed) --------
DERATE_MLCC = 2.0     # X7R/X5R ceramic: DC-bias capacitance loss -> 2x the rail
DERATE_C0G = 1.5      # C0G/NP0: no DC-bias droop, still derate
DERATE_ELEC = 1.5     # electrolytic / tantalum
DERATE_RES = 2.0      # 50% resistor power derating (advisory)


def _ratings_for(part) -> Ratings | None:
    lcsc = (part.fields or {}).get("LCSC", "").strip()
    return RATINGS_BY_LCSC.get(lcsc)


def _ohms(value: str) -> float | None:
    """Parse a resistor value ('10k','330R','4k7','0.01','10m') to ohms."""
    s = (value or "").strip().replace("Ω", "").replace("ohm", "")
    m = re.fullmatch(r"(\d+)([RrKkMm])(\d+)", s)          # 4k7 -> 4700
    if m:
        mult = {"r": 1, "k": 1e3, "m": 1e-3}[m.group(2).lower()]
        if m.group(2).lower() == "m" and float(m.group(1)) >= 1:
            mult = 1e-3                                    # 10m = milliohm
        return (float(m.group(1)) + float(m.group(3)) / 10) * mult
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([RrKkMm]?)", s)
    if not m:
        return None
    base = float(m.group(1))
    suf = m.group(2).lower()
    return base * {"": 1, "r": 1, "k": 1e3, "m": 1e-3}.get(suf, 1)


def _pin_volts(c, ref) -> list[float]:
    """The known rail voltages on a part's pins (GND=0; +5V=5; signal=skip)."""
    vs: list[float] = []
    for net in c.nets.values():
        if any(pr.ref == ref for pr in net.pins):
            v = powertree.rail_volts(net.name)
            if v is not None:
                vs.append(v)
    return vs


def _cap_derate(r: Ratings) -> float:
    if (r.dielectric or "").upper() in ("C0G", "NP0"):
        return DERATE_C0G
    if r.kind in ("elec", "tant"):
        return DERATE_ELEC
    return DERATE_MLCC


# ---- result --------------------------------------------------------------------

@dataclass
class Result:
    findings: list[str] = field(default_factory=list)      # hard fails
    notes: list[str] = field(default_factory=list)         # advisory + waived
    unspecced: list[str] = field(default_factory=list)     # no ratings / no rail
    waived: dict[str, tuple[str, str]] = field(default_factory=dict)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings


def _collect_waivers(sheets) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for sc in sheets:
        for ref, reason in getattr(sc.circuit, "part_rule_waivers", {}).items():
            out[f"{sc.name}:{ref}"] = (sc.name, reason)
    return out


def analyze(sheets, pt_res: powertree.Result | None = None) -> Result:
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    res = Result()
    res.waived = _collect_waivers(sheets)

    # ---- CAP_VOLTAGE + RES_POWER: walk every part with ratings -------------
    for sc in sorted(sheets, key=lambda s: s.name):
        c = sc.circuit
        for ref, part in sorted(c.parts.items()):
            r = _ratings_for(part)
            wkey = f"{sc.name}:{ref}"
            if r is None:
                if (part.fields or {}).get("LCSC", "").strip():
                    res.unspecced.append(f"{wkey} ({part.value}, LCSC "
                                         f"{part.fields.get('LCSC')}) — no ratings row")
                continue
            if r.kind in ("mlcc", "elec", "tant", "film") and r.v_max:
                vs = _pin_volts(c, ref)
                if not vs:
                    res.unspecced.append(f"{wkey} ({part.value}) — cap rail unresolved")
                    continue
                v_rail = max(vs)
                if v_rail <= 0:
                    continue                              # GND-only / bypass net
                res.checked += 1
                need = _cap_derate(r) * v_rail
                if r.v_max < need:
                    msg = (f"CAP_V {wkey} ({part.value}, LCSC "
                           f"{part.fields.get('LCSC')}): {r.v_max:g}V "
                           f"{r.dielectric or r.kind} on a {v_rail:g}V rail — "
                           f"needs >= {_cap_derate(r):g}x = {need:g}V "
                           f"(margin {r.v_max/v_rail:.1f}x). Pick a higher-V part "
                           f"or c.waive_part_rule({ref!r}, reason)")
                    if wkey in res.waived:
                        res.notes.append(f"WAIVED {msg} [{res.waived[wkey][1]}]")
                    else:
                        res.findings.append(msg)
            elif r.kind == "res" and r.p_max:
                ohms = _ohms(part.value)
                vs = _pin_volts(c, ref)
                if ohms and ohms > 0 and len(vs) >= 2:
                    dv = max(vs) - min(vs)
                    p = dv * dv / ohms
                    res.checked += 1
                    if p > DERATE_RES * r.p_max:
                        res.notes.append(
                            f"RES_POWER(advisory) {wkey} ({part.value}): "
                            f"P~={p*1000:.0f}mW across {dv:g}V > {DERATE_RES:g}x "
                            f"rated {r.p_max*1000:.0f}mW — verify it is not a "
                            f"full-rail dissipator")

    # ---- IC_VIN: reuse the powertree regulator tree ------------------------
    fp_lcsc: dict[tuple[str, str], str] = {}
    for sc in sheets:
        for ref, part in sc.circuit.parts.items():
            fp_lcsc[(sc.name, ref)] = (part.fields or {}).get("LCSC", "").strip()
    for reg in sorted(pt_res.regs, key=lambda r: (r.sheet, r.ref)):
        lcsc = fp_lcsc.get((reg.sheet, reg.ref), "")
        r = RATINGS_BY_LCSC.get(lcsc)
        wkey = f"{reg.sheet}:{reg.ref}"
        if r is None or r.vin_max is None:
            res.unspecced.append(f"{wkey} ({reg.value}) — no vin_max rating")
            continue
        v_in = powertree.rail_volts(reg.vin)
        if v_in is None:
            res.unspecced.append(f"{wkey} ({reg.value}) — input rail "
                                 f"{reg.vin} unresolved")
            continue
        res.checked += 1
        if r.vin_max < v_in:
            msg = (f"IC_VIN {wkey} ({reg.value}): abs-max input {r.vin_max:g}V "
                   f"< its rail {reg.vin} {v_in:g}V — over-stress")
            if wkey in res.waived:
                res.notes.append(f"WAIVED {msg} [{res.waived[wkey][1]}]")
            else:
                res.findings.append(msg)
    return res


def report(res: Result) -> str:
    L = ["schgen per-part rule engine (ratings vs netlist usage)", "=" * 78, ""]
    L.append(f"enforced: CAP_VOLTAGE (MLCC {DERATE_MLCC:g}x / C0G "
             f"{DERATE_C0G:g}x / elec {DERATE_ELEC:g}x rail), IC_VIN "
             f"(abs-max >= input rail). advisory: RES_POWER ({DERATE_RES:g}x).")
    L.append(f"{res.checked} part-checks evaluated; ratings from "
             f"schgen/ratings.py (LCSC-keyed).")
    if res.waived:
        L.append("")
        L.append(f"author waivers, verbatim ({len(res.waived)}):")
        for wkey in sorted(res.waived):
            L.append(f"  {wkey:<22} {res.waived[wkey][1]}")
    if res.notes:
        L.append("")
        L.append(f"notes / advisory ({len(res.notes)}):")
        for n_ in sorted(res.notes):
            L.append(f"  + {n_}")
    if res.unspecced:
        L.append("")
        L.append(f"UNSPEC — reported, NOT failing ({len(res.unspecced)}):")
        for u in sorted(res.unspecced):
            L.append(f"  ? {u}")
    L.append("")
    if res.findings:
        L.append(f"ERRORS ({len(res.findings)}):")
        for f_ in sorted(res.findings):
            L.append(f"  ERROR: {f_}")
    else:
        L.append("errors: none")
    L.append("")
    L.append(f"PART RULES: {'PASS' if res.ok else 'FAIL'} "
             f"({res.checked} checks, {len(res.findings)} findings, "
             f"{len(res.unspecced)} unspeced, {len(res.waived)} waived)")
    return "\n".join(L)


def run(sheets, reports_dir: Path,
        pt_res: powertree.Result | None = None) -> Result:
    res = analyze(sheets, pt_res=pt_res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "part_rules.txt").write_text(report(res) + "\n")
    return res


def cmd_part_rules(args) -> int:
    from schgen.link import all_subsystem_paths, load_subsystem
    names = getattr(args, "subsystems", None) or \
        [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports")
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'part_rules.txt'}")
    return 0 if res.ok else 1
