"""thermal — per-device JUNCTION-TEMPERATURE gate (verification P2).

The PWR-2/PWR-3 thermal *decisions* (the VADJ LDO DBV->DYD package swap, the
"0.4 A honest continuous" derate, the always-on +5V_SOM buck duty) live today
only as PROSE in fmc.py / power.py docstrings. A prose comment is not a
regression lock: nothing FAILS the build if someone re-rates the VADJ LDO back
to the bare DBV part, bumps a buck's output current past its thermal envelope,
or drops the eFuse onto a hotter package. This module turns every one of those
decisions into a netlist-driven Tj gate.

HOW IT WORKS
============
The regulator TREE and the per-regulator output current ``I_out`` are NOT
recomputed here — they are read straight from :mod:`schgen.powertree`
(``powertree.analyze(sheets)`` -> ``Result.regs``, each ``Reg`` already
carrying ``vin`` / ``vout`` / ``i_out`` / ``kind`` summed bottom-up through the
declared ``c.draws`` budget). This gate adds only the THERMAL layer on top:

  1. a per-part thermal-spec table (:data:`THERMAL_SPECS`), keyed by MPN prefix
     (and disambiguated by FOOTPRINT where one MPN ships in several packages —
     the VADJ LDO's DYD thermal-pad vs the bare DBV is exactly this case),
     carrying ``RthJA`` (C/W, junction-to-ambient, per package), ``Tj_max``
     (C), and the loss-model knobs (buck efficiency, switch/eFuse Rds_on). Every
     number cites its datasheet — the SAME figures already in the fmc.md /
     power.py docstrings.

  2. a board ambient ``Ta`` (:data:`TA_AMBIENT`, 50 C — the value the fmc.md /
     wave3_function_map.md thermal math is written against).

  3. a dissipation model per device kind:
       LDO          Pd = (Vin - Vout) * Iout
       buck         Pd = (1/eff - 1) * Vout * Iout         (input-side loss shed)
       load_switch / efuse:  Pd = Iout^2 * Rds_on          (conduction loss)

  4. junction temperature  Tj = Ta + Pd * RthJA  and the verdict:
       FAIL  when  Tj > Tj_max - MARGIN   (:data:`TJ_MARGIN`, 10 C guard band).

A device whose MPN/footprint is not in the table is reported as UNSPECED (a
finding, not a silent pass): the gate cannot prove an unlisted package's Tj, so
it says so loudly. An author who has a legitimate exception (a part run hotter
than the guard band on purpose, with a layout/derate justification) declares
``c.waive_thermal(ref, reason)`` — listed verbatim in the report, never
silence (the testpoints.py ``c.waive_tp`` idiom).

OUTPUT
======
``carrier/reports/thermal.txt`` (next to ``power_tree.txt``): the full table
(device | package | Vin->Vout | Iout | Pd | RthJA | Tj | limit | margin |
verdict), the waivers, the findings, then PASS/FAIL. Deterministic, no
timestamps.

Run standalone:  ``python -m schgen thermal``   (or via cmd_thermal below).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from schgen.verify import powertree

# ---- board thermal assumptions -------------------------------------------------

# Ambient the dossier thermal math is written against (fmc.md section 3 /
# wave3_function_map.md section 3.1 both use Ta = 50 C for the VADJ envelope).
TA_AMBIENT = 50.0          # C

# Guard band below Tj_max at which the gate FAILS. 10 C keeps a part off its
# absolute junction limit (derating headroom for tolerance + aging + the
# uncertainty in a single-number RthJA on a real 4-layer board).
TJ_MARGIN = 10.0           # C

# Conservative fixed buck efficiency for the dissipation model. The TPS54302
# datasheet (SLVSDG6) shows 88-92% across this load range; 0.85 is the
# deliberately pessimistic floor (more dissipation than reality), so a PASS
# here is a true PASS. (powertree uses eta=0.90 for the INPUT-CURRENT budget;
# this gate is intentionally a notch more conservative on the THERMAL side.)
BUCK_EFF = 0.85


# ---- per-device thermal spec table ---------------------------------------------

@dataclass(frozen=True)
class ThermalSpec:
    rth_ja: float              # junction-to-ambient, C/W (per package)
    tj_max: float              # absolute max junction temp, C
    rds_on: float = 0.0        # ohms (load_switch / efuse conduction loss)
    eff: float = BUCK_EFF      # buck efficiency (buck only)
    package: str = ""          # human label for the report
    cite: str = ""             # datasheet provenance


# Keyed by part-VALUE prefix (powertree's Reg.value: power.py writes
# 'TPS54302DDCR', fmc.py 'TLV75725PDYDR', bringup 'SY6280AAC', pd_input
# 'TPS26631PWPR', power.py LDO 'AP2112K-1.8'). Where ONE mpn ships in several
# packages with different RthJA (the VADJ LDO DBV vs DYD), a second key on the
# FOOTPRINT substring disambiguates — see FOOTPRINT_SPECS below.
THERMAL_SPECS: dict[str, ThermalSpec] = {
    # power.py: 2x +5V/+3V3 step-down + the always-on +5V_SOM buck.
    # TPS54302DDCR is the TSOT-23-6 (DDC) synchronous buck. TI SLVSDG6:
    # RthJA = 70.6 C/W (JESD51-7 high-K 2s2p), Tj operating max 150 C.
    "TPS54302": ThermalSpec(
        rth_ja=70.6, tj_max=150.0, eff=BUCK_EFF, package="TSOT-23-6 (DDC)",
        cite="TI SLVSDG6 Thermal Information (RthJA 70.6 C/W 2s2p; "
             "Tj op-max 150 C); eff floor 0.85 (DS plots 88-92%)"),
    # power.py +5V buck U1 — RESELECTED from the TPS54302 to the LMR33630ADDA
    # (HSOIC-8 PowerPAD, EP->GND). The board's highest-dissipation converter
    # (2.95 A @ 5 V); its Tj is COMPUTED here (was silently unspeced -> the gate
    # PASSed blind) so it is proven, then explicitly waived in power.py with the
    # EP-pour bench-verify justification (mirrors the TPS54302 U2/U4 waivers).
    "LMR33630": ThermalSpec(
        rth_ja=41.0, tj_max=125.0, eff=BUCK_EFF,
        package="HSOIC-8 (DDA, EP->GND pour)",
        cite="TI SNVSAQ4 LMR33630 (DDA HSOIC-8 PowerPAD RthJA ~41 C/W JEDEC "
             "2s2p; Tj op-max 125 C); EP->GND pour layout-critical; eff floor 0.85"),
    # power.py +1V8 LDO. Diodes AP2112K-1.8, SOT-23-5: RthJA ~250 C/W,
    # Tj_max 125 C (Diodes AP2112 DS). Load is tiny (~6 mA) so Tj ~= Ta.
    "AP2112K": ThermalSpec(
        rth_ja=250.0, tj_max=125.0, package="SOT-23-5",
        cite="Diodes AP2112 DS (SOT-23-5 RthJA ~250 C/W; Tj_max 125 C)"),
    # fmc.py VADJ LDO. DEFAULT (no footprint match) is the conservative bare
    # DBV number so a careless re-pin lands on the HOT package; the DYD
    # thermal-pad part is matched by footprint in FOOTPRINT_SPECS and is the
    # one fmc.py actually instantiates (PWR-3 swap).
    "TLV75725": ThermalSpec(
        rth_ja=231.0, tj_max=125.0, package="SOT-23-5 (DBV, no pad)",
        cite="TI TLV757P DS / fmc.md section 3 (DBV RthJA 231 C/W; "
             "Tj_max 125 C) — the HOT default; DYD pad variant below"),
    # bringup_modules.py: 10x per-module load switch. Silergy SY6280AAC,
    # SOT-23-5: typical Rds_on ~95 mohm, RthJA ~250 C/W, Tj_max 150 C.
    "SY6280": ThermalSpec(
        rth_ja=250.0, tj_max=150.0, rds_on=0.095, package="SOT-23-5",
        cite="Silergy SY6280 DS (SOT-23-5 RthJA ~250 C/W; Rds_on ~95 mohm; "
             "Tj_max 150 C)"),
    # pd_input.py inlet eFuse. TI TPS26631, HTSSOP-20 PowerPAD: integrated FET
    # Rds_on 31 mohm (DS typ), RthJA ~33.6 C/W with the EP soldered to copper
    # (TI SLVSE94 Thermal Information, JEDEC 2s2p), Tj op-max 125 C.
    "TPS26631": ThermalSpec(
        rth_ja=33.6, tj_max=125.0, rds_on=0.031, package="HTSSOP-20 (PWP)",
        cite="TI SLVSE94 (HTSSOP-20 PowerPAD RthJA ~33.6 C/W 2s2p; FET "
             "Rds_on 31 mohm; Tj op-max 125 C)"),
}

# Footprint-substring overrides: same MPN, a package the bare-MPN row would
# get WRONG. The VADJ LDO is the canonical case — fmc.py instantiates the DYD
# thermal-pad variant (footprint 'TLV75725PDYDR:TLV75725PDYDR') whose EP, bonded
# to the GND pour, drops RthJA from the bare 231 C/W to ~92.5 C/W (PWR-3 /
# fmc.md section 3). Keyed (value-prefix, footprint-substring) -> spec.
FOOTPRINT_SPECS: dict[tuple[str, str], ThermalSpec] = {
    ("TLV75725", "DYD"): ThermalSpec(
        rth_ja=92.5, tj_max=125.0, package="SOT-23-5 (DYD, EP->GND pour)",
        cite="TI TLV757P DS / fmc.md section 3 + PWR-3 (DYD thermal-pad "
             "RthJA ~92.5 C/W with EP soldered to GND copper; Tj_max 125 C)"),
}


def _spec_for(value: str, footprint: str) -> ThermalSpec | None:
    """Resolve the thermal spec: footprint-disambiguated row first (e.g. the
    DYD thermal-pad VADJ LDO), else the bare MPN-prefix row."""
    for (vpfx, fpsub), spec in FOOTPRINT_SPECS.items():
        if value.startswith(vpfx) and fpsub in footprint:
            return spec
    for pfx, spec in THERMAL_SPECS.items():
        if value.startswith(pfx):
            return spec
    return None


# ---- dissipation model ---------------------------------------------------------

def dissipation(kind: str, v_in: float, v_out: float, i_out: float,
                spec: ThermalSpec) -> float:
    """Worst-case device dissipation [W] for the device KIND.

    LDO:          Pd = (Vin - Vout) * Iout               (linear pass loss)
    buck:         Pd = (1/eff - 1) * Vout * Iout         (input-side loss shed)
    load_switch / efuse:  Pd = Iout^2 * Rds_on           (conduction loss)
    """
    if kind == "ldo":
        return max(0.0, (v_in - v_out)) * i_out
    if kind == "buck":
        return max(0.0, (1.0 / spec.eff - 1.0)) * v_out * i_out
    if kind in ("load_switch", "efuse"):
        return i_out * i_out * spec.rds_on
    return 0.0


# ---- result --------------------------------------------------------------------

@dataclass
class Device:
    sheet: str
    ref: str
    value: str
    package: str
    kind: str
    vin: str
    vout: str
    v_in: float
    v_out: float
    i_out: float
    pd: float
    rth_ja: float
    tj: float
    tj_max: float
    margin: float          # Tj_max - TJ_MARGIN - Tj  (negative => over limit)
    cite: str

    @property
    def over(self) -> bool:
        return self.margin < 0.0


@dataclass
class Result:
    devices: list[Device] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)        # over-Tj failures
    findings: list[str] = field(default_factory=list)      # unspeced devices
    waived: dict[str, tuple[str, str]] = field(default_factory=dict)  # ref->(sheet,reason)
    notes: list[str] = field(default_factory=list)
    ta: float = TA_AMBIENT
    margin: float = TJ_MARGIN

    @property
    def ok(self) -> bool:
        return not self.errors


# ---- waiver harvesting ---------------------------------------------------------

def _collect_waivers(sheets) -> dict[str, tuple[str, str]]:
    """Author thermal waivers: net them by part REF, keyed sheet-qualified
    'sheet:ref'. Read from ``circuit.thermal_waivers`` (the model.py API added
    by waive_thermal — see the waiver_mechanism snippet); absent attribute =>
    no waivers, gate runs unchanged."""
    out: dict[str, tuple[str, str]] = {}
    for sc in sheets:
        waivers = getattr(sc.circuit, "thermal_waivers", {})
        for ref, reason in waivers.items():
            out[f"{sc.name}:{ref}"] = (sc.name, reason)
    return out


# ---- the gate ------------------------------------------------------------------

def analyze(sheets, pt_res: powertree.Result | None = None) -> Result:
    """Build the Tj table. The regulator tree + per-regulator I_out come from
    powertree (computed once, reused — never recomputed here)."""
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    res = Result()
    res.waived = _collect_waivers(sheets)

    # footprint lookup: powertree's Reg does not carry the footprint, so read
    # it from the part on its source sheet (sheet:ref is unique).
    fp_by: dict[tuple[str, str], str] = {}
    for sc in sheets:
        for ref, part in sc.circuit.parts.items():
            fp_by[(sc.name, ref)] = part.footprint

    for reg in sorted(pt_res.regs, key=lambda r: (r.sheet, r.ref)):
        footprint = fp_by.get((reg.sheet, reg.ref), "")
        spec = _spec_for(reg.value, footprint)
        wkey = f"{reg.sheet}:{reg.ref}"
        if spec is None:
            res.findings.append(
                f"UNSPECED: {reg.sheet}:{reg.ref} ({reg.value}, fp "
                f"{footprint or '<none>'}) has no thermal spec — add a "
                f"THERMAL_SPECS/FOOTPRINT_SPECS row with its datasheet RthJA "
                f"+ Tj_max before its Tj can be proven")
            continue
        v_in = powertree.rail_volts(reg.vin) or 0.0
        v_out = powertree.rail_volts(reg.vout) or 0.0
        pd = dissipation(reg.kind, v_in, v_out, reg.i_out, spec)
        tj = res.ta + pd * spec.rth_ja
        limit = spec.tj_max - res.margin
        margin = limit - tj
        dev = Device(
            sheet=reg.sheet, ref=reg.ref, value=reg.value,
            package=spec.package, kind=reg.kind, vin=reg.vin, vout=reg.vout,
            v_in=v_in, v_out=v_out, i_out=reg.i_out, pd=pd,
            rth_ja=spec.rth_ja, tj=tj, tj_max=spec.tj_max, margin=margin,
            cite=spec.cite)
        res.devices.append(dev)
        if dev.over:
            if wkey in res.waived:
                res.notes.append(
                    f"WAIVED over-limit: {wkey} ({reg.value}) Tj {tj:.1f} C > "
                    f"limit {limit:.1f} C (Tj_max {spec.tj_max:.0f} - margin "
                    f"{res.margin:.0f}) — author waiver: "
                    f"{res.waived[wkey][1]}")
            else:
                res.errors.append(
                    f"OVER Tj: {reg.sheet}:{reg.ref} ({reg.value}, "
                    f"{spec.package}) {reg.vin}->{reg.vout}: Iout "
                    f"{reg.i_out:.3f} A -> Pd {pd*1000:.0f} mW, "
                    f"Tj = {res.ta:.0f} + {pd*1000:.0f}mW*{spec.rth_ja:g} = "
                    f"{tj:.1f} C > limit {limit:.1f} C "
                    f"(Tj_max {spec.tj_max:.0f} - margin {res.margin:.0f}) "
                    f"[{spec.cite}]")
    return res


# ---- report --------------------------------------------------------------------

def report(res: Result) -> str:
    lines = ["schgen per-device thermal (Tj) gate", "=" * 78, ""]
    lines.append(f"model: Tj = Ta + Pd*RthJA ; Ta = {res.ta:.0f} C ; "
                 f"FAIL when Tj > Tj_max - {res.margin:.0f} C margin")
    lines.append("  Pd(LDO) = (Vin-Vout)*Iout ; "
                 f"Pd(buck) = (1/eff-1)*Vout*Iout, eff={BUCK_EFF:g} ; "
                 "Pd(switch/eFuse) = Iout^2*Rds_on")
    lines.append("")
    hdr = (f"  {'device':<22} {'package':<24} {'kind':<11} "
           f"{'in->out':<20} {'Iout/A':>7} {'Pd/mW':>7} {'RthJA':>7} "
           f"{'Tj/C':>7} {'limit':>7} {'mgn/C':>7}  verdict")
    lines.append(hdr)
    lines.append("  " + "-" * (len(hdr) - 2))
    for d in sorted(res.devices, key=lambda x: (-x.tj, x.sheet, x.ref)):
        verdict = "OVER" if d.over else "ok"
        lines.append(
            f"  {d.sheet+':'+d.ref:<22} {d.package:<24} {d.kind:<11} "
            f"{d.vin+'->'+d.vout:<20} {d.i_out:>7.3f} {d.pd*1000:>7.0f} "
            f"{d.rth_ja:>7.1f} {d.tj:>7.1f} {d.tj_max-res.margin:>7.1f} "
            f"{d.margin:>7.1f}  {verdict}")
    lines.append("")
    lines.append("datasheet provenance (every RthJA / Tj_max / Rds_on cited):")
    seen: set[str] = set()
    for d in sorted(res.devices, key=lambda x: x.value):
        key = d.value + d.package
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  {d.value:<16} {d.package:<26} {d.cite}")
    if res.waived:
        lines.append("")
        lines.append(f"author thermal waivers, verbatim ({len(res.waived)}):")
        for wkey in sorted(res.waived):
            _sheet, reason = res.waived[wkey]
            lines.append(f"  {wkey:<22} {reason}")
    if res.notes:
        lines.append("")
        lines.append(f"notes ({len(res.notes)}):")
        for n_ in res.notes:
            lines.append(f"  + {n_}")
    if res.findings:
        lines.append("")
        lines.append(f"FINDINGS — unspeced devices ({len(res.findings)}):")
        for f_ in res.findings:
            lines.append(f"  * {f_}")
    lines.append("")
    if res.errors:
        lines.append(f"ERRORS ({len(res.errors)}):")
        for e in res.errors:
            lines.append(f"  ERROR: {e}")
    else:
        lines.append("errors: none")
    lines.append("")
    hot = max((d.tj for d in res.devices), default=res.ta)
    hot_dev = max(res.devices, key=lambda d: d.tj, default=None)
    hot_str = (f"; hottest {hot_dev.sheet}:{hot_dev.ref} "
               f"({hot_dev.value}) Tj {hot:.1f} C" if hot_dev else "")
    lines.append(f"THERMAL: {'PASS' if res.ok else 'FAIL'} "
                 f"({len(res.devices)} devices speced, {len(res.errors)} "
                 f"over-limit, {len(res.findings)} unspeced, "
                 f"{len(res.waived)} waived){hot_str}")
    return "\n".join(lines)


# ---- entry points --------------------------------------------------------------

def run(sheets, reports_dir: Path,
        pt_res: powertree.Result | None = None) -> Result:
    """Analyze + write carrier/reports/thermal.txt (next to power_tree.txt)."""
    res = analyze(sheets, pt_res=pt_res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "thermal.txt").write_text(report(res) + "\n")
    return res


def cmd_thermal(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = getattr(args, "subsystems", None) or \
        [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports")
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'thermal.txt'}")
    return 0 if res.ok else 1