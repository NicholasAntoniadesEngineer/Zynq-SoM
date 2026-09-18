from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from schgen.core import native
from schgen.verify.powertree import _native_sheets

_DATA = Path(__file__).resolve().parent / "data" / "lcsc_values.json"


@dataclass
class BomValueResult:
    ok: bool = True
    checked: int = 0
    mismatches: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    catalog_size: int = 0

    def report(self) -> str:
        return native.module().bom_value_report(self)


def _norm(value: str, cls_hint: str | None) -> tuple[str, float] | None:
    return native.module().bom_value_normalize(value, cls_hint)


def _equal(a: tuple[str, float], b: tuple[str, float]) -> bool:
    return native.module().bom_value_equal(a, b)


def load_catalog() -> dict[str, dict]:
    return json.loads(_DATA.read_text())


def run(sheets, rep_dir: Path | None = None,
        catalog: dict | None = None) -> BomValueResult:
    raw = native.module().bom_value_check(
        _native_sheets(sheets), catalog if catalog is not None else load_catalog())
    raw.pop("report")
    result = BomValueResult(**raw)
    if rep_dir is not None:
        (Path(rep_dir) / "bom_values.txt").write_text(result.report() + "\n")
    return result
