from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from schgen.verify import powertree

TA_AMBIENT = 50.0

TJ_MARGIN = 10.0

BUCK_EFF = 0.85


@dataclass(frozen=True)
class ThermalSpec:
    rth_ja: float
    tj_max: float
    rds_on: float = 0.0
    eff: float = BUCK_EFF
    package: str = ""
    cite: str = ""
    rth_ja_pour: float | None = None
    pour_cite: str = ""
    pour_evidence: str = ""

    @property
    def rth_eff(self) -> float:
        return self.rth_ja_pour if self.rth_ja_pour is not None else self.rth_ja


@dataclass(frozen=True)
class PourNeed:
    value_prefix: str
    min_vias: int
    radius_mm: float
    pour_layers: tuple[str, ...]


# ONE definition: pcb.embed imports this, so emitter and gate mirror alike
LAYER_SWAP = {"F.Cu": "B.Cu", "B.Cu": "F.Cu"}


def pour_layers_for(need: PourNeed, layer: str) -> tuple[str, ...]:
    return (need.pour_layers if layer != "B.Cu"
            else tuple(LAYER_SWAP.get(la, la) for la in need.pour_layers))


POUR_EVIDENCE: dict[str, PourNeed] = {
    "LM61460": PourNeed("LM61460", min_vias=6, radius_mm=5.2,
                        pour_layers=("F.Cu", "B.Cu")),
    "TLV75725_DYD": PourNeed("TLV75725", min_vias=2, radius_mm=3.0,
                             pour_layers=("F.Cu",)),
}


def _pour_evidence(copper, need: PourNeed) -> tuple[bool, str]:
    if copper is None:
        return False, "no emitted-board scan (fail-closed: credit withheld)"
    if not copper.gnd_plane():
        return False, "In1.Cu GND plane NOT emitted"
    insts = copper.instances(need.value_prefix)
    if not insts:
        return False, f"no {need.value_prefix}* footprint on the emitted board"
    rows: list[str] = []
    ok_all = True
    for f in insts:
        nv = copper.gnd_vias_within(f.x, f.y, need.radius_mm)
        lays = pour_layers_for(need, f.layer)
        pours = all(copper.pour_at(f.x, f.y, lay) for lay in lays)
        ok = nv >= need.min_vias and pours
        ok_all = ok_all and ok
        rows.append(
            f"{f.ref}: {nv}/{need.min_vias} GND vias<={need.radius_mm:g}mm, "
            f"local {'+'.join(lay.split('.')[0] for lay in lays)} "
            f"pour {'YES' if pours else 'MISSING'}"
            + ("" if ok else " [INSUFFICIENT]"))
    return ok_all, "In1 GND plane + " + "; ".join(rows)


THERMAL_SPECS: dict[str, ThermalSpec] = {
    "TPS54302": ThermalSpec(
        rth_ja=118.9, tj_max=125.0, eff=BUCK_EFF,
        package="SOT-23-THIN-6 (DDC, no EP)",
        cite="TI SLVSDG6C 5.4 Thermal Information (RthJA 118.9 C/W JESD51-7; "
             "EVM 57.2 C/W) + 5.3 Rec-Op Tj-max 125 C (abs-max 150 C); no EP; "
             "eff floor 0.85 (DS plots 88-92%)"),
    "LM61460": ThermalSpec(
        rth_ja=58.7, tj_max=150.0, eff=BUCK_EFF,
        package="VQFN-HR-14 (RJR, PGND pads->GND pour)",
        cite="TI SNVSBD5D LM61460 (VQFN-HR RthJA 58.7 C/W JESD51-7 bare; "
             "Tj op-max 150 C); eff floor 0.85 (DS plots ~88-91%)",
        rth_ja_pour=35.0,
        pour_cite="DS 7.3: bare 58.7 C/W (JESD51-7) vs 25 C/W on a 4-layer "
                  "PCB (DS note + LM61460-Q1 EVM). Credit gated on EMITTED "
                  "copper, verified in the .kicad_pcb per build: In1.Cu GND "
                  "plane + 8-via PGND field + local F.Cu/B.Cu pours "
                  "(SNVSBD5D 11.1.1). Credited 35 C/W — 10 C/W above the DS "
                  "4-layer 25, ~30% of the bare->4L delta held back (0.5-oz "
                  "inner plane, modest pours vs the EVM, 3-buck mutual "
                  "heating)",
        pour_evidence="LM61460"),
    "AP2112K": ThermalSpec(
        rth_ja=250.0, tj_max=125.0, package="SOT-23-5",
        cite="Diodes AP2112 DS (SOT-23-5 RthJA ~250 C/W; Tj_max 125 C)"),
    "TLV75725": ThermalSpec(
        rth_ja=231.0, tj_max=125.0, package="SOT-23-5 (DBV, no pad)",
        cite="TI TLV757P DS / fmc.md section 3 (DBV RthJA 231 C/W; "
             "Tj_max 125 C) — the HOT default; DYD pad variant below"),
    "SY6280": ThermalSpec(
        rth_ja=250.0, tj_max=150.0, rds_on=0.095, package="SOT-23-5",
        cite="Silergy SY6280 DS (SOT-23-5 RthJA ~250 C/W; Rds_on ~95 mohm; "
             "Tj_max 150 C)"),
    "TPS26631": ThermalSpec(
        rth_ja=33.6, tj_max=125.0, rds_on=0.031, package="HTSSOP-20 (PWP)",
        cite="TI SLVSE94 (HTSSOP-20 PowerPAD RthJA ~33.6 C/W 2s2p; FET "
             "Rds_on 31 mohm; Tj op-max 125 C)"),
}

FOOTPRINT_SPECS: dict[tuple[str, str], ThermalSpec] = {
    ("TLV75725", "DYD"): ThermalSpec(
        rth_ja=231.0, tj_max=125.0,
        package="SOT-23-5 (DYD, EP+vias->In1 plane)",
        cite="TI TLV757P DS / fmc.md section 3 + PWR-3 (DYD thermal-pad "
             "RthJA ~92.5 C/W JESD51-7 WITH JESD51-5 vias; Tj_max 125 C); "
             "no-copper fallback = DBV bare 231 C/W",
        rth_ja_pour=92.5,
        pour_cite="DS DYD RthJA 92.5 C/W presumes the JESD51-5 stackup "
                  "(thermal pad soldered + vias into a buried plane). Credit "
                  "gated on EMITTED copper, verified per build: In1.Cu GND "
                  "plane + >=2 GND vias beside the pad + local F.Cu pour. "
                  "Fallback without it: DBV bare 231 C/W (no pad benefit "
                  "claimable)",
        pour_evidence="TLV75725_DYD"),
}


def _spec_for(value: str, footprint: str) -> ThermalSpec | None:
    for (vpfx, fpsub), spec in FOOTPRINT_SPECS.items():
        if value.startswith(vpfx) and fpsub in footprint:
            return spec
    for pfx, spec in THERMAL_SPECS.items():
        if value.startswith(pfx):
            return spec
    return None


def dissipation(kind: str, v_in: float, v_out: float, i_out: float,
                spec: ThermalSpec) -> float:
    if kind == "ldo":
        return max(0.0, (v_in - v_out)) * i_out
    if kind == "buck":
        return max(0.0, (1.0 / spec.eff - 1.0)) * v_out * i_out
    if kind in ("load_switch", "efuse"):
        return i_out * i_out * spec.rds_on
    return 0.0


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
    margin: float
    cite: str
    rth_bare: float = 0.0
    pour_cite: str = ""
    pour_granted: bool = False
    evidence: str = ""

    @property
    def over(self) -> bool:
        return self.margin < 0.0

    @property
    def poured(self) -> bool:
        return self.pour_granted and self.rth_ja < self.rth_bare


@dataclass
class Result:
    devices: list[Device] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    waived: dict[str, tuple[str, str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    ta: float = TA_AMBIENT
    margin: float = TJ_MARGIN
    copper_src: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


def _collect_waivers(sheets) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for sc in sheets:
        waivers = getattr(sc.circuit, "thermal_waivers", {})
        for ref, reason in waivers.items():
            out[f"{sc.name}:{ref}"] = (sc.name, reason)
    return out


def analyze(sheets, pt_res: powertree.Result | None = None,
            copper=None, copper_src: str = "") -> Result:
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    res = Result()
    res.waived = _collect_waivers(sheets)
    res.copper_src = copper_src if copper is not None else ""

    ev: dict[str, tuple[bool, str]] = {
        key: _pour_evidence(copper, need)
        for key, need in POUR_EVIDENCE.items()}

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
        granted, detail = (ev.get(spec.pour_evidence, (False, ""))
                           if spec.rth_ja_pour is not None else (False, ""))
        rth_eff = spec.rth_ja_pour if granted else spec.rth_ja
        tj = res.ta + pd * rth_eff
        limit = spec.tj_max - res.margin
        margin = limit - tj
        dev = Device(
            sheet=reg.sheet, ref=reg.ref, value=reg.value,
            package=spec.package, kind=reg.kind, vin=reg.vin, vout=reg.vout,
            v_in=v_in, v_out=v_out, i_out=reg.i_out, pd=pd,
            rth_ja=rth_eff, tj=tj, tj_max=spec.tj_max, margin=margin,
            cite=spec.cite, rth_bare=spec.rth_ja, pour_cite=spec.pour_cite,
            pour_granted=granted, evidence=detail)
        res.devices.append(dev)
        if spec.rth_ja_pour is not None and not granted:
            res.notes.append(
                f"POUR CREDIT WITHHELD: {wkey} ({reg.value}) judged at the "
                f"bare {spec.rth_ja:g} C/W, not the credited "
                f"{spec.rth_ja_pour:g} — required copper not verified: "
                f"{detail}")
        if dev.over:
            withheld = (" — POUR CREDIT WITHHELD (required copper not "
                        f"emitted: {detail})"
                        if spec.rth_ja_pour is not None and not granted
                        else "")
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
                    f"Tj = {res.ta:.0f} + {pd*1000:.0f}mW*{rth_eff:g} = "
                    f"{tj:.1f} C > limit {limit:.1f} C "
                    f"(Tj_max {spec.tj_max:.0f} - margin {res.margin:.0f}) "
                    f"[{spec.cite}]{withheld}")
    return res


def report(res: Result) -> str:
    lines = ["schgen per-device thermal (Tj) gate", "=" * 78, ""]
    lines.append(f"model: Tj = Ta + Pd*RthJA ; Ta = {res.ta:.0f} C ; "
                 f"FAIL when Tj > Tj_max - {res.margin:.0f} C margin")
    lines.append("  Pd(LDO) = (Vin-Vout)*Iout ; "
                 f"Pd(buck) = (1/eff-1)*Vout*Iout, eff={BUCK_EFF:g} ; "
                 "Pd(switch/eFuse) = Iout^2*Rds_on")
    lines.append("  RthJA = bare JEDEC, unless '*' = pour-aware effective RthJA "
                 "(EP/power pads -> GND copper + vias; basis cited below)")
    lines.append("  pour credits are granted ONLY against copper VERIFIED in "
                 "the emitted board")
    src = res.copper_src or \
        "NONE — all pour credits withheld (fail-closed)"
    lines.append(f"  emitted-copper evidence source: {src}")
    lines.append("")
    hdr = (f"  {'device':<22} {'package':<24} {'kind':<11} "
           f"{'in->out':<20} {'Iout/A':>7} {'Pd/mW':>7} {'RthJA':>7} "
           f"{'Tj/C':>7} {'limit':>7} {'mgn/C':>7}  verdict")
    lines.append(hdr)
    lines.append("  " + "-" * (len(hdr) - 2))
    for d in sorted(res.devices, key=lambda x: (-x.tj, x.sheet, x.ref)):
        verdict = "OVER" if d.over else "ok"
        rth = f"{d.rth_ja:.1f}{'*' if d.poured else ' '}"
        lines.append(
            f"  {d.sheet+':'+d.ref:<22} {d.package:<24} {d.kind:<11} "
            f"{d.vin+'->'+d.vout:<20} {d.i_out:>7.3f} {d.pd*1000:>7.0f} "
            f"{rth:>7} {d.tj:>7.1f} {d.tj_max-res.margin:>7.1f} "
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
    poured = [d for d in sorted(res.devices, key=lambda x: x.value) if d.poured]
    if poured:
        lines.append("")
        lines.append("pour-aware effective RthJA (* rows) — basis, per part "
                     "(bare->credited, cited; conservative, bench-verify at "
                     "bring-up):")
        seenp: set[str] = set()
        for d in poured:
            if d.value in seenp:
                continue
            seenp.add(d.value)
            lines.append(f"  {d.value:<16} bare {d.rth_bare:g} -> eff "
                         f"{d.rth_ja:g} C/W ; {d.pour_cite}")
            lines.append(f"  {'':<16} emitted-copper evidence (verified in "
                         f"the board file): {d.evidence}")
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


def run(sheets, reports_dir: Path,
        pt_res: powertree.Result | None = None,
        pcb_path: Path | None = None) -> Result:
    copper = None
    copper_src = ""
    if pcb_path is not None and Path(pcb_path).exists():
        from schgen.verify import copper_debt
        copper = copper_debt.scan_board(Path(pcb_path))
        repo = Path(__file__).resolve().parents[2]
        try:
            copper_src = str(Path(pcb_path).resolve().relative_to(repo))
        except ValueError:
            copper_src = str(pcb_path)
    res = analyze(sheets, pt_res=pt_res, copper=copper, copper_src=copper_src)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "thermal.txt").write_text(report(res) + "\n")
    return res


def cmd_thermal(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = getattr(args, "subsystems", None) or \
        [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports",
              pcb_path=repo / "carrier" / "Zynq_Carrier.kicad_pcb")
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'thermal.txt'}")
    return 0 if res.ok else 1
