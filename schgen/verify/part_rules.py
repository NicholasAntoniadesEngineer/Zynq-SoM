from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from schgen.verify import powertree
from schgen.verify.ratings import RATINGS_BY_LCSC

DERATE_MLCC = 2.0
DERATE_C0G = 1.5
DERATE_ELEC = 1.5
DERATE_RES = 2.0


def _ohms(value: str) -> float | None:
    from schgen.core import native
    return native.module().parse_resistor_ohms(value or "")


@dataclass
class Result:
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unspecced: list[str] = field(default_factory=list)
    waived: dict[str, tuple[str, str]] = field(default_factory=dict)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings


def _native_policy():
    return [DERATE_MLCC, DERATE_C0G, DERATE_ELEC, DERATE_RES]


def analyze(sheets, pt_res: powertree.Result | None = None) -> Result:
    from dataclasses import asdict
    from schgen.core import native
    sheets = list(sheets)
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    raw = native.module().part_rules_analyze(
        powertree._native_sheets(sheets), asdict(pt_res),
        {key: asdict(value) for key, value in RATINGS_BY_LCSC.items()},
        _native_policy(), powertree._native_policy())
    raw["waived"] = {key: tuple(value) for key, value in raw["waived"].items()}
    return Result(**raw)


def report(res: Result) -> str:
    from dataclasses import asdict
    from schgen.core import native
    return native.module().part_rules_report(asdict(res), _native_policy())


def run(sheets, reports_dir: Path,
        pt_res: powertree.Result | None = None) -> Result:
    res = analyze(sheets, pt_res=pt_res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "part_rules.txt").write_text(report(res) + "\n")
    return res


def cmd_part_rules(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.project import PROJECT_ROOT
    names = getattr(args, "subsystems", None) or \
        [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    res = run(sheets, PROJECT_ROOT / "reports")
    print(report(res))
    print(f"\nreport: {PROJECT_ROOT / 'reports' / 'part_rules.txt'}")
    return 0 if res.ok else 1
