from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import Circuit, NetClass
from schgen.core.project import PROJECT_ROOT
from schgen.verify import powertree

PER_CONTACT_A = 0.3
PER_CONTACT_BASIS = (
    "Hirose DF40 series datasheet: rated current 0.3 A/contact "
    "(rated voltage 50 V AC/DC) — CITED (Hirose DF40 catalogue)")

DERATING = 0.8
DERATING_BASIS = (
    "0.8 (20% power-derating margin on the rated per-contact current) — the "
    "standard connector power convention, covering uneven multi-contact load "
    "share + temp-rise tolerance — JUDGMENT, fixed floor (LAW 4)")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INTERFACE_JSON = PROJECT_ROOT / "som_interface.json"


def _link_maps():
    from schgen.core.link import _load_som_conn_gen
    mod = _load_som_conn_gen()
    return mod.resolve_net, dict(mod.ISOLATED_SOM_RAILS)


@dataclass
class Rail:
    name: str
    contacts: int
    current_a: float
    volts: float | None
    conns: dict[str, int]

    @property
    def capacity_a(self) -> float:
        return self.contacts * PER_CONTACT_A * DERATING

    @property
    def margin_a(self) -> float:
        return self.capacity_a - self.current_a

    @property
    def over(self) -> bool:
        return self.current_a > self.capacity_a + 1e-9

    @property
    def util(self) -> float:
        return self.current_a / self.capacity_a if self.capacity_a > 0 else \
            float("inf")


@dataclass
class Result:
    rails: list[Rail] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    per_contact_a: float = PER_CONTACT_A
    derating: float = DERATING

    @property
    def ok(self) -> bool:
        return not self.errors


def analyze(sheets, pt_res: powertree.Result | None = None,
            interface_json: Path | None = None) -> Result:
    from schgen.core import native
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    resolve_net, isolated = _link_maps()
    data = json.loads(Path(interface_json or _INTERFACE_JSON).read_text())
    pins = {ref: c["pins"] for ref, c in data["connectors"].items()}
    resolved = {net: resolve_net(net) for rows in pins.values() for net in rows.values()}
    raw = native.module().pcb_rail_ampacity(
        [(sc.name, sc.circuit.loads) for sc in sheets], pins, resolved, set(isolated))
    raw["rails"] = [Rail(**row) for row in raw["rails"]]
    return Result(**raw)


def report(res: Result) -> str:
    from schgen.verify._native_pcb import summary
    return summary("rail-ampacity", res)

def run(sheets, reports_dir: Path,
        pt_res: powertree.Result | None = None,
        interface_json: Path | None = None) -> Result:
    res = analyze(sheets, pt_res=pt_res, interface_json=interface_json)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "rail_ampacity.txt").write_text(report(res) + "\n")
    return res


def cmd_rail_ampacity(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = getattr(args, "subsystems", None) or \
        [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    res = run(sheets, PROJECT_ROOT / "reports")
    print(report(res))
    print(f"\nreport: {PROJECT_ROOT / 'reports' / 'rail_ampacity.txt'}")
    return 0 if res.ok else 1
