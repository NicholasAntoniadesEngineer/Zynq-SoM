"""model3d — the 3D-MODEL COVERAGE gate (SOFT) for custom footprints.

The unfakeable hole this closes: every custom footprint at ``parts/<MPN>/
<MPN>.kicad_mod`` was converted from EasyEDA with a ``(model "<MPN>.wrl" ...)``
clause that points at a .wrl file THAT DOES NOT EXIST anywhere on disk. KiCad
silently shows nothing for a missing model, so the carrier's 3D viewer was
empty and there was no signal that coverage had rotted — a missing model is
neither an ERC error nor a DRC error nor a netlist defect, so no existing gate
ever saw it.

INVARIANT (reported, not enforced): every custom footprint either references a
3D model FILE THAT EXISTS on disk, or is explicitly accounted for as
"unmatched" (an exotic connector with no genuine stock body — a WRONG 3D model
is worse than none, so we leave those without one rather than fake it).

WHY SOFT (not HARD-FAIL): some bespoke parts (board-to-board mezzanines, a
discrete-magnetics RJ45 module, a specific RTC package) have NO faithful stock
KiCad body. Hard-failing the board on them would force either a fake model or a
permanent waiver list; instead this gate prints coverage + the exact gaps so
the number can only move DOWN visibly, never silently. It does NOT touch the
board's ok_all.

MODEL RESOLUTION: a footprint's ``(model "<path>" ...)`` path is taken, the
``${KICAD10_3DMODEL_DIR}`` env var (and ${KISYS3DMOD}, the legacy name) is
expanded to the macOS install's 3dmodels dir, and the resulting file is checked
for existence. A bare filename (the old EasyEDA ``MPN.wrl``) never resolves —
it is reported as a BROKEN ref. A footprint with no ``(model ...)`` at all is
reported as MISSING.

DETERMINISM: every list this gate prints is sorted by MPN, so the report and
the cmd_board line are byte-stable across runs.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"

# The KICAD10_3DMODEL_DIR env var the stock footprints (and now ours) reference.
# Resolved to the same macOS install layout the rest of schgen assumes; the
# legacy KISYS3DMOD name is honoured too. If the env var is set in the
# environment it wins (portable across a Linux/CI install).
_DEFAULT_3DMODEL_DIR = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels")

# parts whose package has NO faithful stock KiCad 3D body — left WITHOUT a model
# on purpose (a wrong body is worse than none). Listed here so the gate counts
# them as KNOWN gaps (not silent), with the reason. Keep sorted.
_KNOWN_UNMATCHED: dict[str, str] = {
    "DF40C-100DS-0.4V_51":
        "Hirose DF40 0.4mm board-to-board mezzanine — no DF40 stock model",
    "FUSB302BMPX":
        "MLP-14 2.5x2.5 P0.5 — stock DFN-14 bodies are 3x3/3x4, none matches",
    "HX5008NLT":
        "Ethernet magnetics module (SOP-24 13.2x15.1) — no discrete-magnetics "
        "stock body",
    "RV-3028-C7-32.768kHz-1ppm-TA-QC":
        "RTC OSC-SMD 8P 3.2x1.5 — no matching stock RTC/oscillator body",
}

# ``(model`` then (across optional whitespace/newlines) a quoted path.
_MODEL_RE = re.compile(r'\(model\s+"([^"]*)"')


@dataclass
class Model3dResult:
    ok: bool = True               # SOFT: True unless an UNEXPECTED gap appears
    total: int = 0                # custom footprints scanned
    covered: int = 0             # footprints whose model file resolves on disk
    # MPN -> reason, for every footprint WITHOUT a resolving model
    unmatched: dict[str, str] = field(default_factory=dict)
    # MPN -> the unresolved path string (broken/bare ref still in the file)
    broken: dict[str, str] = field(default_factory=dict)
    # MPN with no (model ...) clause at all
    missing: list[str] = field(default_factory=list)

    @property
    def n_unmatched(self) -> int:
        return len(self.unmatched)

    def line(self) -> str:
        """The one-line SOFT report for cmd_board. Deterministic."""
        gaps = sorted(self.unmatched)
        tail = f"; {len(gaps)} unmatched: [{', '.join(gaps)}]" if gaps else ""
        return f"3D MODELS: {self.covered}/{self.total} footprints{tail}"

    def report(self) -> str:
        lines = [
            "3D model coverage gate (custom footprints reference a stock "
            "KiCad 3D model that EXISTS on disk)",
            "=" * 72,
            "STATUS: SOFT — gaps are reported, never fail the board (some "
            "bespoke parts have no faithful stock body)",
            f"{self.covered}/{self.total} custom footprints have a resolving "
            f"3D model",
        ]
        if self.unmatched:
            lines.append("")
            lines.append(f"UNMATCHED ({len(self.unmatched)}) — no model (a "
                         f"wrong body is worse than none):")
            for mpn in sorted(self.unmatched):
                lines.append(f"  {mpn}: {self.unmatched[mpn]}")
        else:
            lines.append("unmatched: none — every custom footprint has a model")
        if self.broken:
            lines.append("")
            lines.append(f"BROKEN ({len(self.broken)}) — (model ...) path does "
                         f"not resolve to a file on disk:")
            for mpn in sorted(self.broken):
                lines.append(f"  {mpn}: {self.broken[mpn]}")
        if self.missing:
            lines.append("")
            lines.append(f"MISSING (model ...) clause ({len(self.missing)}):")
            lines += [f"  {m}" for m in sorted(self.missing)]
        return "\n".join(lines)


def _model_dir() -> Path:
    env = os.environ.get("KICAD10_3DMODEL_DIR") or os.environ.get("KISYS3DMOD")
    return Path(env) if env else _DEFAULT_3DMODEL_DIR


def _resolve_model_path(raw: str, model_dir: Path) -> Path | None:
    """Expand a footprint (model ...) path to a Path, or None if it cannot be
    resolved (an unexpanded env var other than the 3D-model one, etc.). The
    returned Path is NOT guaranteed to exist — the caller checks .is_file()."""
    s = raw.strip()
    s = s.replace("${KICAD10_3DMODEL_DIR}", str(model_dir))
    s = s.replace("${KISYS3DMOD}", str(model_dir))
    if "$" in s:                       # an env var we do not know -> unresolved
        return None
    p = Path(s)
    if not p.is_absolute():
        # a bare filename (the old EasyEDA "MPN.wrl") is relative -> never a
        # real on-disk model in this repo (we ship no .wrl). Resolve against
        # parts/<mpn> so .is_file() is a true negative, not a crash.
        return None
    return p


def _custom_footprints() -> list[Path]:
    if not _PARTS_DIR.is_dir():
        return []
    return sorted(_PARTS_DIR.glob("*/*.kicad_mod"))


def check(model_dir: Path | None = None) -> Model3dResult:
    """Scan every custom footprint; classify its 3D-model coverage. Pure and
    deterministic (sorted by MPN)."""
    md = model_dir if model_dir is not None else _model_dir()
    res = Model3dResult()
    for mod in _custom_footprints():
        mpn = mod.parent.name
        res.total += 1
        text = mod.read_text(errors="replace")
        m = _MODEL_RE.search(text)
        if m is None:
            # no (model ...): either a known-unmatched part or a true gap
            if mpn in _KNOWN_UNMATCHED:
                res.unmatched[mpn] = _KNOWN_UNMATCHED[mpn]
            else:
                res.missing.append(mpn)
                res.unmatched[mpn] = "no (model ...) clause"
            continue
        raw = m.group(1)
        p = _resolve_model_path(raw, md)
        if p is not None and p.is_file():
            res.covered += 1
        else:
            # a (model ...) is present but does not resolve to a file
            if mpn in _KNOWN_UNMATCHED:
                res.unmatched[mpn] = _KNOWN_UNMATCHED[mpn]
            else:
                res.broken[mpn] = raw
                res.unmatched[mpn] = f"model path does not resolve: {raw}"
    # SOFT: the verdict is OK as long as there is no UNEXPECTED gap — a footprint
    # that is missing a clause or has a broken ref AND is not on the documented
    # unmatched list. Documented-unmatched parts keep the gate green.
    res.ok = not res.broken and not res.missing
    return res


def run(rep_dir: Path | None = None,
        model_dir: Path | None = None) -> Model3dResult:
    """check() + write the report to rep_dir/model3d.txt (when given)."""
    res = check(model_dir=model_dir)
    if rep_dir is not None:
        rep_dir.mkdir(parents=True, exist_ok=True)
        (rep_dir / "model3d.txt").write_text(res.report() + "\n")
    return res
