from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from schgen.core import native
from schgen.core.model import Circuit
from schgen.core.symbols import Library, SymbolError
from schgen.verify.powertree import _native_sheets

PENDING_MIGRATION: dict[str, str] = {}


@dataclass
class SymbolLawResult:
    violations: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        return native.module().symbol_law_summary(self)


def _raw_symbol(lib, lib_id):
    try:
        return lib.get(lib_id).raw
    except SymbolError:
        return None


def _is_power_flag(lib: Library, lib_id: str) -> bool:
    raw = _raw_symbol(lib, lib_id)
    return False if raw is None else native.module().symbol_power_flag(raw)


def check(circuits: list[Circuit], lib: Library) -> SymbolLawResult:
    raw = native.module().symbol_law_check(
        _native_sheets([SimpleNamespace(name=c.name, circuit=c) for c in circuits]),
        lambda lib_id: _raw_symbol(lib, lib_id), PENDING_MIGRATION)
    return SymbolLawResult(violations=raw["violations"], pending=raw["pending"])
