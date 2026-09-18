from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from schgen.core import native
from schgen.core.symbols import Library
from schgen.verify.powertree import _native_sheets

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"
_KICAD_FP_ROOT = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
_FP_LIB_TABLES = (_REPO_ROOT / "som" / "fp-lib-table",)


@dataclass
class FootprintPadsResult:
    ok: bool = True
    checked: int = 0
    violations: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def report(self) -> str:
        return native.module().footprint_pad_report(self)


def _read_pad_numbers(mod_path: Path) -> set[str]:
    return native.module().footprint_pad_numbers(mod_path.read_text(errors="replace"))


def _options(aliases=None):
    return {"parts_dir": str(_PARTS_DIR), "root": str(_KICAD_FP_ROOT),
            "tables": [str(p) for p in _FP_LIB_TABLES],
            "aliases": aliases if aliases is not None else _footprint_aliases()}


def _load_fp_lib_table() -> dict[str, Path]:
    return {k: Path(v) for k, v in
            native.module().footprint_library_tables(_options()).items()}


def _footprint_aliases() -> dict[str, str]:
    from schgen.generate.pcb import _FOOTPRINT_ALIASES
    return dict(_FOOTPRINT_ALIASES)


def _resolve_footprint(fp: str, fp_libs: dict[str, Path],
                       aliases: dict[str, str]) -> Path | None:
    path = native.module().footprint_resolve(
        fp, {k: str(v) for k, v in fp_libs.items()}, _options(aliases))
    return Path(path) if path is not None else None


def run(sheets, rep_dir: Path | None = None,
        lib: Library | None = None) -> FootprintPadsResult:
    lib = lib if lib is not None else Library()
    raw = native.module().footprint_pad_check(
        _native_sheets(sheets), lib.pin_numbers, _options())
    raw.pop("report")
    result = FootprintPadsResult(**raw)
    if rep_dir is not None:
        (Path(rep_dir) / "footprint_pads.txt").write_text(result.report() + "\n")
    return result
