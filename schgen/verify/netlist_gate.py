from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import native as _nat
from schgen.core.model import Circuit, PinRef


@dataclass
class GateResult:
    ok: bool
    shorts: list[str] = field(default_factory=list)
    opens: list[str] = field(default_factory=list)
    nc_cheats: list[str] = field(default_factory=list)
    part_mismatches: list[str] = field(default_factory=list)
    name_mismatches: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "NETLIST GATE: PASS (extracted == declared)"
        lines = ["NETLIST GATE: FAIL"]
        for tag, items in (("SHORT", self.shorts), ("OPEN", self.opens),
                           ("NC-CHEAT", self.nc_cheats),
                           ("PART", self.part_mismatches),
                           ("NAME", self.name_mismatches)):
            for it in items:
                lines.append(f"  {tag}: {it}")
        return "\n".join(lines)


def extract_netlist(sch_path: Path) -> dict[str, list[PinRef]]:
    return {name: [PinRef(ref, pin) for ref, pin in pins]
            for name, pins in _nat.module().netlist_extract(str(sch_path)).items()}


def _norm(name: str) -> str:
    return _nat.module().netlist_normalize_name(name)


def _dead_two_terminal(circuit: Circuit) -> list[str]:
    return _nat.module().netlist_dead_two_terminal(circuit)


def check(circuit: Circuit, sch_path: Path) -> GateResult:
    # Keep the observable extraction seam while all gate decisions run in C++.
    extracted = extract_netlist(sch_path)
    text = Path(sch_path).read_text(errors="ignore")
    return GateResult(*_nat.module().netlist_check(circuit, extracted, text))


def _emitted_nc_cheats(circuit: Circuit, sch_text: str) -> list[str]:
    return _nat.module().netlist_emitted_nc_cheats(circuit, sch_text)
