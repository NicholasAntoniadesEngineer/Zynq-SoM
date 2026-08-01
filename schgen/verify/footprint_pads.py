from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.symbols import Library

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"

_KICAD_FP_ROOT = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

_FP_LIB_TABLES = (_REPO_ROOT / "som" / "fp-lib-table",)

_PAD_RE = re.compile(r'\(pad\s+"([^"]*)"')

_LIBROW_RE = re.compile(
    r'\(lib\s+\(name\s+"([^"]+)"\).*?\(uri\s+"([^"]+)"\)', re.DOTALL)


@dataclass
class FootprintPadsResult:
    ok: bool = True
    checked: int = 0
    violations: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = ["footprint pad-coverage gate "
                 "(every symbol pin NUMBER has a footprint PAD)",
                 "=" * 64,
                 "STATUS: HARD-FAIL (any symbol pin with no footprint pad fails "
                 "the board) — the ethernet:T1 25/26 open that motivated it is "
                 "fixed",
                 f"{self.checked} parts with a resolved footprint checked"]
        if self.violations:
            lines.append("")
            lines.append(f"VIOLATIONS ({len(self.violations)}) — symbol pin "
                         f"with NO footprint pad (guaranteed OPEN):")
            lines += [f"  {v}" for v in self.violations]
        else:
            lines.append("violations: none")
        if self.unresolved:
            lines.append("")
            lines.append(f"UNRESOLVED footprints — reported, NOT failing "
                         f"({len(self.unresolved)}):")
            lines += [f"  {u}" for u in sorted(set(self.unresolved))]
        return "\n".join(lines)


def _read_pad_numbers(mod_path: Path) -> set[str]:
    text = mod_path.read_text(errors="replace")
    return {n for n in _PAD_RE.findall(text) if n != ""}


def _fp_lib_uri(uri: str) -> Path | None:
    for tbl in _FP_LIB_TABLES:
        s = uri.replace("${KIPRJMOD}", str(tbl.parent))
        if "$" in s:
            continue
        p = Path(s)
        if p.exists():
            return p
    return None


def _load_fp_lib_table() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for tbl in _FP_LIB_TABLES:
        if not tbl.exists():
            continue
        for nick, uri in _LIBROW_RE.findall(tbl.read_text()):
            pretty = _fp_lib_uri(uri)
            if pretty is not None:
                out[nick] = pretty
    return out


def _footprint_aliases() -> dict[str, str]:
    try:
        from schgen.generate.pcb import _FOOTPRINT_ALIASES
        return dict(_FOOTPRINT_ALIASES)
    except Exception:
        return {}


def _resolve_footprint(fp: str, fp_libs: dict[str, Path],
                       aliases: dict[str, str]) -> Path | None:
    if ":" not in fp:
        p = Path(fp)
        return p if p.is_file() and p.suffix == ".kicad_mod" else None
    nick, _, name = fp.partition(":")
    dossier = _PARTS_DIR / nick / f"{name}.kicad_mod"
    if dossier.is_file():
        return dossier
    pretty = fp_libs.get(nick)
    if pretty is not None:
        cand = pretty / f"{name}.kicad_mod"
        if cand.is_file():
            return cand
    cand = _KICAD_FP_ROOT / f"{nick}.pretty" / f"{name}.kicad_mod"
    if cand.is_file():
        return cand
    alias = aliases.get(fp)
    if alias is not None and alias != fp:
        return _resolve_footprint(alias, fp_libs, {})
    return None


def run(sheets, rep_dir: Path | None = None,
        lib: Library | None = None) -> FootprintPadsResult:
    lib = lib if lib is not None else Library()
    fp_libs = _load_fp_lib_table()
    aliases = _footprint_aliases()
    res = FootprintPadsResult()
    pad_cache: dict[str, set[str] | None] = {}
    for sc in sheets:
        for ref, part in sorted(sc.circuit.parts.items()):
            fp = part.footprint
            if not fp:
                res.unresolved.append(f"{sc.name}:{ref} (no footprint)")
                continue
            if fp not in pad_cache:
                mod = _resolve_footprint(fp, fp_libs, aliases)
                pad_cache[fp] = _read_pad_numbers(mod) if mod is not None else None
            pads = pad_cache[fp]
            if pads is None:
                res.unresolved.append(f"{sc.name}:{ref} footprint {fp!r}")
                continue
            res.checked += 1
            sym_pins = lib.pin_numbers(part.lib_id)
            missing = sorted(sym_pins - pads,
                             key=lambda s: (len(s), s))
            if missing:
                res.ok = False
                res.violations.append(
                    f"{sc.name}:{ref} ({part.value}, {part.lib_id}) "
                    f"footprint {fp!r} has {len(pads)} pads — symbol pin(s) "
                    f"{missing} have NO pad (guaranteed OPEN)")
    if rep_dir is not None:
        (Path(rep_dir) / "footprint_pads.txt").write_text(res.report() + "\n")
    return res
