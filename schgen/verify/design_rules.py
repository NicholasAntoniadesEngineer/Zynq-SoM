from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import native as _nat


def is_power_pin_name(name: str) -> bool:
    return _nat.module().design_rule_power_pin(name)


@dataclass
class DesignRuleResult:
    decap: list[str] = field(default_factory=list)
    i2c: list[str] = field(default_factory=list)
    reset: list[str] = field(default_factory=list)
    strap: list[str] = field(default_factory=list)
    ep: list[str] = field(default_factory=list)
    waived: list[str] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not (self.decap or self.i2c or self.reset or self.strap
                    or self.ep)

    @property
    def findings(self) -> list[str]:
        return self.decap + self.i2c + self.reset + self.strap + self.ep

    def summary(self) -> str:
        return _nat.module().design_rule_format(self)[0]

    def report(self) -> str:
        return _nat.module().design_rule_format(self)[1]


def check(sheets, lib) -> DesignRuleResult:
    raw = _nat.module().design_rule_check(sheets, lib.get)
    keys = ("decap", "i2c", "reset", "strap", "ep", "waived", "checked")
    return DesignRuleResult(**{key: raw[key] for key in keys})


def run(sheets, reports_dir: Path | None = None,
        lib=None) -> DesignRuleResult:
    if lib is None:
        from schgen.core.symbols import Library
        lib = Library()
    res = check(sheets, lib)
    if reports_dir is not None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "design_rules.txt").write_text(res.report() + "\n")
    return res


def cmd_design_rules(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.project import PROJECT_ROOT
    from schgen.core.symbols import Library
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    lib = Library()
    reports = PROJECT_ROOT / "reports"
    res = run(sheets, reports, lib=lib)
    print(res.report())
    print(f"\nreport: {reports / 'design_rules.txt'}")
    return 0 if res.ok else 1
