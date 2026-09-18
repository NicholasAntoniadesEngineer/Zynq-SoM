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


def dissipation(kind: str, v_in: float, v_out: float, i_out: float,
                spec: ThermalSpec) -> float:
    from dataclasses import asdict
    from schgen.core import native
    return native.module().thermal_dissipation(kind, v_in, v_out, i_out, asdict(spec))


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


def _native_policy():
    from dataclasses import asdict
    return dict(ambient_c=TA_AMBIENT, margin_c=TJ_MARGIN,
                specs={key: asdict(value) for key, value in THERMAL_SPECS.items()},
                footprint_specs=[(prefix, footprint, asdict(value))
                                 for (prefix, footprint), value in FOOTPRINT_SPECS.items()],
                pour_needs={key: asdict(value) for key, value in POUR_EVIDENCE.items()})


def analyze(sheets, pt_res: powertree.Result | None = None,
            copper=None, copper_src: str = "") -> Result:
    from dataclasses import asdict
    from schgen.core import native
    sheets = list(sheets)
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    scan = None
    if copper is not None:
        scan = asdict(copper)
        scan["path"] = str(copper.path)
        scan["net_names"] = sorted(copper.net_names)
    raw = native.module().thermal_analyze(
        powertree._native_sheets(sheets), asdict(pt_res), scan, copper_src,
        _native_policy(), powertree._native_policy())
    raw["devices"] = [powertree._native_record(Device, row) for row in raw["devices"]]
    raw["ta"], raw["margin"] = float(raw["ta"]), float(raw["margin"])
    raw["waived"] = {key: tuple(value) for key, value in raw["waived"].items()}
    return Result(**raw)


def report(res: Result) -> str:
    from dataclasses import asdict
    from schgen.core import native
    return native.module().thermal_report(asdict(res))


def run(sheets, reports_dir: Path,
        pt_res: powertree.Result | None = None,
        pcb_path: Path | None = None) -> Result:
    from dataclasses import asdict
    from schgen.core import native
    sheets = list(sheets)
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    raw = native.module().thermal_run(
        powertree._native_sheets(sheets), asdict(pt_res),
        str(pcb_path) if pcb_path is not None else "", str(reports_dir),
        str(Path(__file__).resolve().parents[2]), _native_policy(), powertree._native_policy())
    raw["devices"] = [powertree._native_record(Device, row) for row in raw["devices"]]
    raw["ta"], raw["margin"] = float(raw["ta"]), float(raw["margin"])
    raw["waived"] = {key: tuple(value) for key, value in raw["waived"].items()}
    return Result(**raw)


def cmd_thermal(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.project import PROJECT_ROOT
    names = getattr(args, "subsystems", None) or \
        [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    res = run(sheets, PROJECT_ROOT / "reports",
              pcb_path=PROJECT_ROOT / "Zynq_Carrier.kicad_pcb")
    print(report(res))
    print(f"\nreport: {PROJECT_ROOT / 'reports' / 'thermal.txt'}")
    return 0 if res.ok else 1
