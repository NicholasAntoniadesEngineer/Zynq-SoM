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

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.config import MISPLACED_OVERLAP
from schgen.core.project import PROJECT_ROOT

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
    # EMPTY — every footprint now references a RESOLVING 3D model (real EasyEDA
    # .wrl, stock Samtec FMC, stock bucks, and the ESC 3x8 header now uses 3x the
    # stock PinHeader_1x08_P2.54mm_Vertical.step tiled per row). A NEW unmatched
    # part must be modeled (preferred) or listed here with the reason.
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
    # MPN -> reason, for a model that resolves but does NOT fit the footprint
    misfit: dict[str, str] = field(default_factory=dict)
    # MPN -> reason, for a model whose body bbox does NOT overlap its pads (HARD:
    # the body is planted off the footprint — an EasyEDA c_origin unit mismatch).
    misplaced: dict[str, str] = field(default_factory=dict)

    @property
    def n_unmatched(self) -> int:
        return len(self.unmatched)

    def line(self) -> str:
        """The one-line report for cmd_board. Deterministic."""
        gaps = sorted(self.unmatched)
        tail = f"; {len(gaps)} unmatched: [{', '.join(gaps)}]" if gaps else ""
        mis = (f"; {len(self.misfit)} MISFIT: [{', '.join(sorted(self.misfit))}]"
               if self.misfit else "")
        mp = (f"; {len(self.misplaced)} MISPLACED: "
              f"[{', '.join(sorted(self.misplaced))}]" if self.misplaced else "")
        return f"3D MODELS: {self.covered}/{self.total} footprints{tail}{mis}{mp}"

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
        if self.misfit:
            lines.append("")
            lines.append(f"MISFIT ({len(self.misfit)}) — model resolves but does "
                         f"NOT match the footprint body (LAW):")
            for mpn in sorted(self.misfit):
                lines.append(f"  {mpn}: {self.misfit[mpn]}")
        if self.misplaced:
            lines.append("")
            lines.append(f"MISPLACED ({len(self.misplaced)}) — HARD: model body "
                         f"planted off its pads (offset bug, LAW 5/6):")
            for mpn in sorted(self.misplaced):
                lines.append(f"  {mpn}: {self.misplaced[mpn]}")
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
    # our part .wrl models reference ${KIPRJMOD}/../parts/<MPN>/<MPN>.wrl, where
    # KIPRJMOD is the carrier project dir; resolve it to the repo's carrier/.
    s = s.replace("${KIPRJMOD}", str(PROJECT_ROOT))
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


# per-axis size-fit band: the placed model's XY bounding box must be within
# [_FIT_LO, _FIT_HI] x the footprint's F.Fab body box on BOTH axes. A real part
# body matches ~1x; the generic-stock-model disaster (a 90deg-rotated FFC, a
# wrong-size connector) flips the aspect ratio or scale clean outside this band.
_FIT_LO, _FIT_HI = 0.5, 2.0
_CART_RE = re.compile(
    r"CARTESIAN_POINT\('[^']*',\(([-\d.E+]+),([-\d.E+]+),([-\d.E+]+)\)\)")


def _clause_xfrm(body: str) -> tuple[tuple[float, float], float]:
    """(scale_xy, rotate_z_deg) from a (model ...) clause body."""
    def xyz(tag, dflt):
        m = re.search(rf"\({tag}\s*\(xyz\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)",
                      body)
        return (float(m.group(1)), float(m.group(2)), float(m.group(3))) \
            if m else dflt
    sx, sy, _ = xyz("scale", (1.0, 1.0, 1.0))
    _, _, rz = xyz("rotate", (0.0, 0.0, 0.0))
    return (sx or 1.0, sy or 1.0), rz % 360


def _model_xy(path: Path, scale: tuple[float, float], rot_z: float
              ) -> tuple[float, float] | None:
    """Placed model XY extent (mm): parse the file bbox, apply the VRML x2.54
    (.wrl) or mm (.step) unit, the footprint scale, and the 90/270 axis swap."""
    t = path.read_text(errors="replace")
    if path.suffix.lower() == ".wrl":
        pts = []
        for blk in re.findall(r"point\s*\[(.*?)\]", t, re.S):
            c = [float(x) for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", blk)]
            pts += [(c[i], c[i + 1]) for i in range(0, len(c) - 2, 3)]
        unit = 2.54
    else:
        pts = [(float(a), float(b)) for a, b, _ in _CART_RE.findall(t)]
        unit = 1.0
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w = (max(xs) - min(xs)) * unit * abs(scale[0])
    h = (max(ys) - min(ys)) * unit * abs(scale[1])
    if rot_z % 180 == 90:
        w, h = h, w
    return w, h


def _fab_elements(text: str):
    """Yield each (fp_line|fp_rect|fp_poly|fp_circle) s-expression block via
    BALANCED-PAREN scanning — robust to the real multi-line KiCad format (the
    old single-regex `(.*?)\\)` stopped at the first inner paren, e.g. the
    `(start x y)`, so it parsed NOTHING on real footprints and the fit check was
    silently vacuous)."""
    i = 0
    pat = re.compile(r"\(fp_(?:line|rect|poly|circle)\b")
    while True:
        m = pat.search(text, i)
        if not m:
            return
        start = m.start()
        depth = 0
        j = start
        while j < len(text):
            ch = text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield text[start:j + 1]
        i = j + 1


def _fab_xy(text: str) -> tuple[float, float] | None:
    """Footprint body (F.Fab) XY extent (mm)."""
    xs: list[float] = []
    ys: list[float] = []
    for block in _fab_elements(text):
        if '"F.Fab"' not in block:
            continue
        for a, b in re.findall(
                r"\((?:start|end|center|mid|xy)\s+(-?[\d.]+)\s+(-?[\d.]+)\)",
                block):
            xs.append(float(a))
            ys.append(float(b))
    if not xs:
        return None
    return max(xs) - min(xs), max(ys) - min(ys)


# HARD position check: the placed model body bbox must overlap the footprint's
# pad-copper bbox by at least this fraction (see config.MISPLACED_OVERLAP for the
# full rationale). Aliased to the historical local name to keep the call sites
# stable.
_MISPLACED_OVERLAP = MISPLACED_OVERLAP


def _offset_xy(body: str) -> tuple[float, float]:
    m = re.search(r"\(offset\s*\(xyz\s+(-?[\d.]+)\s+(-?[\d.]+)", body)
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def _model_box(path: Path, scale: tuple[float, float], rot_z: float,
               off: tuple[float, float]) -> tuple[float, float, float, float] | None:
    """Placed model XY bbox (mm) in the footprint frame: the file bbox * unit
    (.wrl x2.54 / .step mm) * scale, rotated about Z, translated by (offset)."""
    t = path.read_text(errors="replace")
    if path.suffix.lower() == ".wrl":
        pts: list[tuple[float, float]] = []
        for blk in re.findall(r"point\s*\[(.*?)\]", t, re.S):
            c = [float(x) for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", blk)]
            pts += [(c[i], c[i + 1]) for i in range(0, len(c) - 2, 3)]
        unit = 2.54
    else:
        pts = [(float(a), float(b)) for a, b, _ in _CART_RE.findall(t)]
        unit = 1.0
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) / 2 * unit * abs(scale[0])
    cy = (min(ys) + max(ys)) / 2 * unit * abs(scale[1])
    w = (max(xs) - min(xs)) * unit * abs(scale[0])
    h = (max(ys) - min(ys)) * unit * abs(scale[1])
    th = math.radians(rot_z)
    # kicad-cli applies a CW model rotation about Z (the same handedness the
    # emitted footprint pads use in _inst_pad_geom, "TRUE KiCad convention");
    # the old CCW form here disagreed at 90/270 and passed an off-board header
    # body (the 3x8 ESC PWM header, the only 90deg model-rotate on the board).
    # 0/180 are handedness-invariant, so this only changes 90/270 verdicts.
    rcx = cx * math.cos(th) + cy * math.sin(th)
    rcy = -cx * math.sin(th) + cy * math.cos(th)
    if rot_z % 180 == 90:
        w, h = h, w
    ox, oy = off
    return (ox + rcx - w / 2, oy + rcy - h / 2, ox + rcx + w / 2, oy + rcy + h / 2)


def _pad_bbox(text: str) -> tuple[float, float, float, float] | None:
    """Footprint pad-copper XY bbox (mm)."""
    xs: list[float] = []
    ys: list[float] = []
    for m in re.finditer(
            r"\(pad\s+\"[^\"]*\"\s+\S+\s+\S+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)"
            r"(?:\s+[-\d.]+)?\)\s+\(size\s+(-?[\d.]+)\s+(-?[\d.]+)\)", text):
        x, y, w, h = (float(g) for g in m.groups())
        xs += [x - w / 2, x + w / 2]
        ys += [y - h / 2, y + h / 2]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _placed_ok(mod_path: Path, clause_body: str, model_file: Path) -> str | None:
    """HARD: None if the model body bbox overlaps the pad bbox by
    >= _MISPLACED_OVERLAP, else a reason. Returns None when uncheckable (no pads /
    unparseable model) so it never false-fails on a parse gap."""
    scale, rz = _clause_xfrm(clause_body)
    body = _model_box(model_file, scale, rz, _offset_xy(clause_body))
    pad = _pad_bbox(mod_path.read_text(errors="replace"))
    if not body or not pad:
        return None
    ix = max(0.0, min(body[2], pad[2]) - max(body[0], pad[0]))
    iy = max(0.0, min(body[3], pad[3]) - max(body[1], pad[1]))
    pa = (pad[2] - pad[0]) * (pad[3] - pad[1])
    if pa <= 0:
        return None
    frac = ix * iy / pa
    if frac >= _MISPLACED_OVERLAP:
        return None
    ox, oy = _offset_xy(clause_body)
    return (f"body ({body[0]:.1f},{body[1]:.1f})..({body[2]:.1f},{body[3]:.1f}) mm "
            f"overlaps the pad area only {frac:.0%} (needs >="
            f"{_MISPLACED_OVERLAP:.0%}); model offset ({ox:.2f},{oy:.2f}) plants the "
            f"body off its pads")


def _fit_ok(mod_path: Path, clause_body: str, model_file: Path
            ) -> str | None:
    """SOFT size heuristic: None if the model's XY bbox is within the band of the
    footprint F.Fab body, else a human reason. Returns None (can't-check) if
    either box is unparseable. NOT a hard pass/fail — a connector housing legit
    exceeds its fab pin-outline; the render (LAW 5) is the true fit oracle."""
    scale, rz = _clause_xfrm(clause_body)
    mxy = _model_xy(model_file, scale, rz)
    fxy = _fab_xy(mod_path.read_text(errors="replace"))
    if not mxy or not fxy or fxy[0] <= 0 or fxy[1] <= 0:
        return None
    rw, rh = mxy[0] / fxy[0], mxy[1] / fxy[1]
    if _FIT_LO <= rw <= _FIT_HI and _FIT_LO <= rh <= _FIT_HI:   # inclusive band
        return None
    return (f"model {mxy[0]:.1f}x{mxy[1]:.1f} mm vs footprint body "
            f"{fxy[0]:.1f}x{fxy[1]:.1f} mm (ratio {rw:.2f},{rh:.2f} outside "
            f"[{_FIT_LO},{_FIT_HI}])")


def check(model_dir: Path | None = None) -> Model3dResult:
    """Scan every custom footprint; classify its 3D-model coverage. Pure and
    deterministic (sorted by MPN)."""
    md = model_dir if model_dir is not None else _model_dir()
    res = Model3dResult()
    for mod in _custom_footprints():
        mpn = mod.parent.name
        res.total += 1
        text = mod.read_text(errors="replace")
        m = _MODEL_RE.search(text)          # path-only: robust to 1-line/multiline
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
        if p is None or not p.is_file():
            # a (model ...) is present but does not resolve to a file
            if mpn in _KNOWN_UNMATCHED:
                res.unmatched[mpn] = _KNOWN_UNMATCHED[mpn]
            else:
                res.broken[mpn] = raw
                res.unmatched[mpn] = f"model path does not resolve: {raw}"
            continue
        res.covered += 1
        # SOFT size heuristic: warn if the model's XY bbox is grossly off the
        # footprint F.Fab body. It catches an extreme mismatch (e.g. a 90deg-
        # rotated FFC flips the aspect ratio clean outside the band) but is NOT
        # hard: a connector's 3D HOUSING legitimately exceeds its F.Fab pin-
        # outline, and F.Fab is format-fragile, so a hard size gate would
        # false-fail real parts. The DEFINITIVE fit/position/orientation oracle
        # is the rendered 3D (LAW 5, `schgen render3d` — open it and look).
        clause = text[m.end():m.end() + 500]
        reason = _fit_ok(mod, clause, p)
        if reason is not None:
            res.misfit[mpn] = reason
        # HARD position check: the body must sit ON its pads (catches the EasyEDA
        # offset bug the SOFT size check is blind to). Documented-unmatched parts
        # never reach here (they `continue` above).
        bad = _placed_ok(mod, clause, p)
        if bad is not None:
            res.misplaced[mpn] = bad
    # HARD: every custom footprint must reference a model that RESOLVES on disk
    # (or be documented-unmatched). That is the un-fakeable enforcement — it
    # catches the real bug (a bare/unresolvable .wrl path -> an empty 3D viewer).
    # The size MISFIT list is SOFT (reported, not failed): noise from connector
    # housings / fab-parse variance, with the render as the true oracle.
    # HARD: a resolving model is required, AND no model may be planted off its
    # pads. The size MISFIT list stays SOFT (connector-housing / fab-parse noise);
    # MISPLACED is hard because a 0%-overlap body is an unambiguous defect that
    # DRC/ratsnest cannot see and the render proved real (the SOT-23 offset bug).
    res.ok = not res.broken and not res.missing and not res.misplaced
    return res


def run(rep_dir: Path | None = None,
        model_dir: Path | None = None) -> Model3dResult:
    """check() + write the report to rep_dir/model3d.txt (when given)."""
    res = check(model_dir=model_dir)
    if rep_dir is not None:
        rep_dir.mkdir(parents=True, exist_ok=True)
        (rep_dir / "model3d.txt").write_text(res.report() + "\n")
    return res
