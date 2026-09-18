from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from schgen.core import native
from schgen.verify.powertree import _native_sheets, _native_policy

VREF_TPS54302 = 0.596
STM32_BOOT0_PULLDOWN = 1500.0
STM32_VDD = 3.3
STM32_VIH = 0.7 * STM32_VDD
STM32_NRST_PULLUP = 40_000.0
SY7201_VFB = 0.2
AO3400A_VGS_TH_MAX = 1.45
CP2102N_VBUS_MAX = 5.8
CP2102N_VBUS_DETECT = 3.0
LVCMOS33_VMAX = 3.465
LVCMOS33_VIH = 2.0
TPS2663_OVPR_MIN = 1.176
TPS2663_OVPR_MAX = 1.224
PD_CONTRACT_VMAX = 21.0
SMBJ22A_VBR_MIN = 24.4

TPS54302_EN_RISING = 1.21
TPS54302_EN_ENABLE_FLOOR = 1.5
TPS54302_EN_RECMAX = 5.5
TPS54302_EN_IHYS = 1.55e-6
PD_VIN_CONTRACT_LO = 4.75
ZENER_5V1_IZT = 20e-3
ZENER_5V1_ZZT = 17.0
ZENER_5V1_VZ = {"MMSZ5231B": (4.845, 5.1, 5.355),
                "BZT52C5V1": (4.845, 5.1, 5.355)}



@dataclass
class Check:
    name: str
    sheet: str
    kind: str
    detail: str
    value: float
    unit: str
    lo: float | None
    hi: float | None
    engine: str = "analytic"
    spice_value: float | None = None

    @property
    def ok(self) -> bool:
        return native.module().spice_check_ok(asdict(self))


@dataclass
class Result:
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    engine: str = "analytic (closed-form linear solutions)"

    @property
    def errors(self) -> list[str]:
        return native.module().spice_errors(asdict(self))

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def n_checks(self) -> int:
        return len(self.checks)


def _result(raw) -> Result:
    checks = []
    for row in raw["checks"]:
        values = {k: v for k, v in row.items() if k in Check.__dataclass_fields__}
        for key in ("value", "lo", "hi", "spice_value"):
            if values[key] is not None:
                values[key] = float(values[key])
        checks.append(Check(**values))
    return Result(checks=checks, notes=raw["notes"], engine=raw["engine"])


def extract_checks(sheets) -> Result:
    return _result(native.module().spice_extract(_native_sheets(sheets), _native_policy()))


def ngspice_available() -> str | None:
    return native.module().ngspice_available()


def run_ngspice(res: Result) -> None:
    exe = ngspice_available()
    if exe is None:
        return
    result = _result(native.module().spice_crosscheck(asdict(res), exe))
    # Keep caller-owned check objects alive, as the old in-place API did.
    for check, updated in zip(res.checks, result.checks, strict=True):
        check.spice_value = updated.spice_value
        check.engine = updated.engine
    res.notes[:] = result.notes
    res.engine = result.engine


def report(res: Result) -> str:
    return native.module().spice_report(asdict(res), ngspice_available() is not None)


def run(sheets, reports_dir: Path, allow_ngspice: bool = True) -> Result:
    res = extract_checks(sheets)
    if allow_ngspice:
        run_ngspice(res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "spice.txt").write_text(report(res) + "\n")
    return res


def cmd_spice(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.project import PROJECT_ROOT
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    res = run(sheets, PROJECT_ROOT / "reports", allow_ngspice=not args.no_ngspice)
    print(report(res))
    print(f"\nreport: {PROJECT_ROOT / 'reports' / 'spice.txt'}")
    return 0 if res.ok else 1
