"""footprint_pads — the symbol-pin vs footprint-pad COVERAGE gate (LAW 0).

The unfakeable hole this closes: every electrical gate in schgen — netlist
equivalence, ERC, the connected-components short/open detector — reasons about
the SYMBOL. None of them ever checks that the symbol's pin NUMBERS actually
exist as PADS in the part's assigned FOOTPRINT. A symbol pin with no pad is a
GUARANTEED OPEN at assembly: the netlist says "net X lands on U1.25", the
fabricated board has no pad 25 to land on, and the connection silently
vanishes. This is exactly the hole that let the Ethernet magnetics symbol
(ethernet:T1, schgen-local HX5008NLT) use pins 25/26 on a 24-pad SOIC-24W
footprint — the 4th gigabit pair (ETH_PHY_MDI3_P/N) had no copper and was a
dead OPEN, with ERC=0, overlap=0 and the netlist gate all green.

INVARIANT: for every part on every sheet, every symbol pin NUMBER must exist as
a pad NUMBER in that part's assigned footprint. A symbol pin not in the pad set
is a VIOLATION (a guaranteed open).

FOOTPRINT RESOLUTION (covers every part on the board):
  * KiCad standard libs:    "<nick>:<name>"  -> <KICAD_FP_ROOT>/<nick>.pretty/<name>.kicad_mod
  * per-part dossiers:       "<MPN>:<MPN>"    -> parts/<MPN>/<MPN>.kicad_mod
  * repo fp-lib-table libs:  "<nick>:<name>"  -> the .pretty dir the table maps <nick> to
A footprint that resolves to no file is reported as "unresolved" (informational,
never a violation and never a crash) — a visible resolution backlog, not a
silent pass.

PAD PARSING: a footprint is a KiCad .kicad_mod s-expression. Pad numbers appear
as ``(pad "<n>" ...)`` (single-line) or ``(pad\n  "<n>"\n  ...)`` (the newer
multi-line dump). One regex matches both. Pads with an EMPTY number ("" — NPTH
mounting drills, fiducials) carry no electrical number and are skipped: a symbol
never references them.

HARD-FAIL. The defect that motivated this gate — ethernet:T1 (the schgen-local
HX5008NLT) using pins 25/26 on a 24-pad footprint — is fixed (faithful 24-pad
HX5008NL dossier), so the board has zero pin-without-pad. The gate ANDs its
verdict into the board's ok_all in cmd_board: any future symbol pin with no
footprint pad fails the build. Footprints are resolved through the PCB
generator's alias map (cross-KiCad-version names like C_1206_3225Metric ->
C_1206_3216Metric) so a board-valid aliased footprint is not a false unresolved.

LAW 4: strict. A genuine pin-with-no-pad is fixed (correct the symbol pin
number or the footprint) — never suppressed, exempted, or relaxed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.symbols import Library

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"

# KiCad standard footprint library root (macOS install layout). Same convention
# as schgen/core/symbols.py's symbol search path; one resolvable location.
_KICAD_FP_ROOT = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

# Repo fp-lib-table(s): map a library NICKNAME to its .pretty directory. The
# carrier currently has som/fp-lib-table (nick "fp" -> som/lib/zynq_som.pretty);
# no board footprint uses it today, but honouring it keeps resolution complete
# for any future fp: footprint without another code change.
_FP_LIB_TABLES = (_REPO_ROOT / "som" / "fp-lib-table",)

# ``(pad`` then (across optional whitespace/newlines) a quoted number. Matches
# both the single-line ``(pad "1" smd ...`` and the multi-line dump where the
# number sits on its own line. An empty number ("" — NPTH/fiducial) is captured
# as "" and dropped by the caller (never electrically referenced by a symbol).
_PAD_RE = re.compile(r'\(pad\s+"([^"]*)"')

# ``(lib (name "fp")(type "KiCad")(uri "${KIPRJMOD}/lib/zynq_som.pretty") ...``
_LIBROW_RE = re.compile(
    r'\(lib\s+\(name\s+"([^"]+)"\).*?\(uri\s+"([^"]+)"\)', re.DOTALL)


@dataclass
class FootprintPadsResult:
    ok: bool = True
    checked: int = 0                                 # parts with a resolved fp
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
    """Pad NUMBERS in a .kicad_mod. Empty-string pad numbers (NPTH drills,
    fiducials) are dropped — a symbol never references them."""
    text = mod_path.read_text(errors="replace")
    return {n for n in _PAD_RE.findall(text) if n != ""}


def _fp_lib_uri(uri: str) -> Path | None:
    """Resolve an fp-lib-table URI (``${KIPRJMOD}/lib/x.pretty``) to a Path.
    ${KIPRJMOD} is the directory holding the table; other vars are unsupported
    (returns None -> the lib is simply not used for resolution)."""
    for tbl in _FP_LIB_TABLES:
        s = uri.replace("${KIPRJMOD}", str(tbl.parent))
        if "$" in s:                       # unresolved env var -> give up
            continue
        p = Path(s)
        if p.exists():
            return p
    return None


def _load_fp_lib_table() -> dict[str, Path]:
    """nickname -> .pretty directory for every repo fp-lib-table row."""
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
    """The PCB generator's footprint alias map (a project-authored name that a
    given KiCad install ships under a near-identical dimensional name, e.g.
    C_1206_3225Metric -> C_1206_3216Metric). Resolving through it keeps THIS
    gate consistent with the footprint the board actually fabricates — a
    board-valid aliased footprint must not read as 'unresolved'. Lazy import
    avoids a verify->generate import-time coupling."""
    try:
        from schgen.generate.pcb import _FOOTPRINT_ALIASES
        return dict(_FOOTPRINT_ALIASES)
    except Exception:
        return {}


def _resolve_footprint(fp: str, fp_libs: dict[str, Path],
                       aliases: dict[str, str]) -> Path | None:
    """The .kicad_mod for a ``<lib>:<name>`` (or bare-path) footprint, or None.

    Resolution order: per-part dossier (parts/<name>/<name>.kicad_mod, the
    "<MPN>:<MPN>" form) -> repo fp-lib-table nickname -> KiCad standard
    <nick>.pretty/<name>.kicad_mod -> the PCB generator's alias. A bare path
    (no colon) is taken verbatim."""
    if ":" not in fp:
        p = Path(fp)
        return p if p.is_file() and p.suffix == ".kicad_mod" else None
    nick, _, name = fp.partition(":")
    # per-part dossier: FOOTPRINT="<MPN>:<MPN>" -> parts/<MPN>/<MPN>.kicad_mod
    dossier = _PARTS_DIR / nick / f"{name}.kicad_mod"
    if dossier.is_file():
        return dossier
    # repo fp-lib-table nickname
    pretty = fp_libs.get(nick)
    if pretty is not None:
        cand = pretty / f"{name}.kicad_mod"
        if cand.is_file():
            return cand
    # KiCad standard library
    cand = _KICAD_FP_ROOT / f"{nick}.pretty" / f"{name}.kicad_mod"
    if cand.is_file():
        return cand
    # cross-version alias (resolve as the PCB generator does), once
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
    # Cache resolution + pad parse per footprint string (many parts share one).
    pad_cache: dict[str, set[str] | None] = {}
    for sc in sheets:
        for ref, part in sorted(sc.circuit.parts.items()):
            fp = part.footprint
            if not fp:
                # un-footprinted parts are the BOM-footprint gate's domain;
                # here a missing footprint is simply unresolvable.
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
