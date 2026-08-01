from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core.model import Circuit
from schgen.core.symbols import Library, SymbolError

PENDING_MIGRATION: dict[str, str] = {}


@dataclass
class SymbolLawResult:
    violations: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        out = [f"SYMBOL-LAW GATE: {'PASS' if self.ok else 'FAIL'} "
               f"(0 hand-built real-part symbols on the board"
               + (f"; {len(self.pending)} tracked-pending" if self.pending
                  else "") + ")"]
        for v in self.violations:
            out.append(f"  VIOLATION: {v}")
        for p in self.pending:
            out.append(f"  pending (tracked exception): {p}")
        return "\n".join(out)


def _is_power_flag(lib: Library, lib_id: str) -> bool:
    try:
        sdef = lib.get(lib_id)
    except SymbolError:
        return False
    return any(isinstance(x, list) and x and str(x[0]) == "power"
               for x in sdef.raw)


def check(circuits: list[Circuit], lib: Library) -> SymbolLawResult:
    res = SymbolLawResult()
    seen: set[str] = set()
    for c in circuits:
        for ref, part in sorted(c.parts.items()):
            lib_id = part.lib_id
            if not lib_id.startswith("schgen:"):
                continue
            if _is_power_flag(lib, lib_id):
                continue
            if lib_id in PENDING_MIGRATION:
                tag = f"{lib_id} ({c.name}.{ref}) — {PENDING_MIGRATION[lib_id]}"
                if lib_id not in seen:
                    res.pending.append(tag)
                    seen.add(lib_id)
                continue
            res.violations.append(
                f"{c.name}.{ref} uses hand-built schgen-local real-part symbol "
                f"{lib_id!r} — migrate to a parts/<MPN>/ dossier (use_part "
                f"WITHOUT lib_id=) or a stock KiCad symbol; schgen.kicad_sym "
                f"may hold only (power) rail flags.")
    return res
