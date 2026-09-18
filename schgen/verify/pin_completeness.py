from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from schgen.core import native
from schgen.core.symbols import Library
from schgen.verify.powertree import _native_sheets

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
        return native.module().pin_completeness_report(self)


def load_allowlist() -> dict:
    return json.loads(_DATA.read_text()) if _DATA.exists() else {}


def run(sheets, rep_dir: Path | None = None,
        lib: Library | None = None,
        allowlist: dict | None = None) -> PinCompletenessResult:
    lib = lib if lib is not None else Library()
    raw = native.module().pin_completeness_check(
        _native_sheets(sheets), lib.get,
        allowlist if allowlist is not None else load_allowlist())
    raw.pop("report")
    result = PinCompletenessResult(**raw)
    if rep_dir is not None:
        (Path(rep_dir) / "pin_completeness.txt").write_text(result.report() + "\n")
    return result
