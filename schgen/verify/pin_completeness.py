from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.symbols import Library

_DATA = Path(__file__).resolve().parent / "data" / "nc_allowlist.json"


@dataclass
class PinCompletenessResult:
    ok: bool = True
    parts_checked: int = 0
    nc_total: int = 0
    floats: list[str] = field(default_factory=list)
    nc_seeded: list[str] = field(default_factory=list)
    nc_new: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = ["pin completeness gate "
                 "(every multi-pin IC pin is NETTED or explicit NC)",
                 "=" * 64,
                 "STATUS: REPORT-FIRST (does NOT fail the board yet; promotes "
                 "to HARD-FAIL once the NC allowlist is fully blessed)",
                 f"{self.parts_checked} multi-pin parts checked; "
                 f"{self.nc_total} author-declared NC pins"]
        if self.floats:
            lines.append("")
            lines.append(f"SILENT FLOATS ({len(self.floats)}) — pin neither "
                         f"netted nor NC (probable missing connection):")
            lines += [f"  {f}" for f in self.floats]
        else:
            lines.append("silent floats: none")
        lines.append("")
        lines.append(f"NC ALLOWLIST — {len(self.nc_seeded)} blessed [seed], "
                     f"{len(self.nc_new)} to bless [new]:")
        for n in self.nc_seeded:
            lines.append(f"  [seed] {n}")
        for n in self.nc_new:
            lines.append(f"  [new]  {n}")
        return "\n".join(lines)


def load_allowlist() -> dict:
    if _DATA.exists():
        return json.loads(_DATA.read_text())
    return {}


def run(sheets, rep_dir: Path | None = None,
        lib: Library | None = None,
        allowlist: dict | None = None) -> PinCompletenessResult:
    lib = lib if lib is not None else Library()
    allow = allowlist if allowlist is not None else load_allowlist()
    res = PinCompletenessResult()
    seeded: list[str] = []
    new: list[str] = []
    for sc in sheets:
        c = sc.circuit
        netted: dict[str, set[str]] = {}
        for net in c.nets.values():
            for pr in net.pins:
                netted.setdefault(pr.ref, set()).add(pr.pin)
        nc: dict[str, set[str]] = {}
        for pr in c.nc_pins:
            nc.setdefault(pr.ref, set()).add(pr.pin)
        sheet_allow = allow.get(sc.name, {})
        for ref, part in sorted(c.parts.items()):
            pins = lib.pin_numbers(part.lib_id)
            if len(pins) < 2:
                continue
            res.parts_checked += 1
            names = {p.number: p.name for p in lib.get(part.lib_id).pins}
            nn = netted.get(ref, set())
            cc = nc.get(ref, set())
            floats = sorted(pins - nn - cc, key=lambda s: (len(s), s))
            if floats:
                res.ok = False
                fdesc = ", ".join(f"{n}({names.get(n, '')})" for n in floats)
                res.floats.append(
                    f"{sc.name}:{ref} ({part.value}) silent float pin(s): "
                    f"{fdesc}")
            blessed = set(sheet_allow.get(ref, []))
            for pin in sorted(cc, key=lambda s: (len(s), s)):
                tag = f"{sc.name}:{ref}.{pin} ({part.value} {names.get(pin, '')})"
                (seeded if pin in blessed else new).append(tag)
                res.nc_total += 1
    res.nc_seeded = seeded
    res.nc_new = new
    if rep_dir is not None:
        (Path(rep_dir) / "pin_completeness.txt").write_text(res.report() + "\n")
    return res
