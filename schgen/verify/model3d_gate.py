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

_DEFAULT_3DMODEL_DIR = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels")

_KNOWN_UNMATCHED: dict[str, str] = {
}

_MODEL_RE = re.compile(r'\(model\s+"([^"]*)"')


@dataclass
class Model3dResult:
    ok: bool = True
    total: int = 0
    covered: int = 0
    unmatched: dict[str, str] = field(default_factory=dict)
    broken: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    misfit: dict[str, str] = field(default_factory=dict)
    misplaced: dict[str, str] = field(default_factory=dict)

    @property
    def n_unmatched(self) -> int:
        return len(self.unmatched)

    def line(self) -> str:
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
    s = raw.strip()
    s = s.replace("${KICAD10_3DMODEL_DIR}", str(model_dir))
    s = s.replace("${KISYS3DMOD}", str(model_dir))
    s = s.replace("${KIPRJMOD}", str(PROJECT_ROOT))
    if "$" in s:
        return None
    p = Path(s)
    if not p.is_absolute():
        return None
    return p


def _custom_footprints() -> list[Path]:
    if not _PARTS_DIR.is_dir():
        return []
    return sorted(_PARTS_DIR.glob("*/*.kicad_mod"))


_FIT_LO, _FIT_HI = 0.5, 2.0
_CART_RE = re.compile(
    r"CARTESIAN_POINT\('[^']*',\(([-\d.E+]+),([-\d.E+]+),([-\d.E+]+)\)\)")


def _clause_xfrm(body: str) -> tuple[tuple[float, float], float]:
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


_MISPLACED_OVERLAP = MISPLACED_OVERLAP


def _offset_xy(body: str) -> tuple[float, float]:
    m = re.search(r"\(offset\s*\(xyz\s+(-?[\d.]+)\s+(-?[\d.]+)", body)
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def _model_box(path: Path, scale: tuple[float, float], rot_z: float,
               off: tuple[float, float]) -> tuple[float, float, float, float] | None:
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
    rcx = cx * math.cos(th) + cy * math.sin(th)
    rcy = -cx * math.sin(th) + cy * math.cos(th)
    if rot_z % 180 == 90:
        w, h = h, w
    ox, oy = off
    return (ox + rcx - w / 2, oy + rcy - h / 2, ox + rcx + w / 2, oy + rcy + h / 2)


def _pad_bbox(text: str) -> tuple[float, float, float, float] | None:
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
    scale, rz = _clause_xfrm(clause_body)
    mxy = _model_xy(model_file, scale, rz)
    fxy = _fab_xy(mod_path.read_text(errors="replace"))
    if not mxy or not fxy or fxy[0] <= 0 or fxy[1] <= 0:
        return None
    rw, rh = mxy[0] / fxy[0], mxy[1] / fxy[1]
    if _FIT_LO <= rw <= _FIT_HI and _FIT_LO <= rh <= _FIT_HI:
        return None
    return (f"model {mxy[0]:.1f}x{mxy[1]:.1f} mm vs footprint body "
            f"{fxy[0]:.1f}x{fxy[1]:.1f} mm (ratio {rw:.2f},{rh:.2f} outside "
            f"[{_FIT_LO},{_FIT_HI}])")


def check(model_dir: Path | None = None) -> Model3dResult:
    md = model_dir if model_dir is not None else _model_dir()
    res = Model3dResult()
    for mod in _custom_footprints():
        mpn = mod.parent.name
        res.total += 1
        text = mod.read_text(errors="replace")
        m = _MODEL_RE.search(text)
        if m is None:
            if mpn in _KNOWN_UNMATCHED:
                res.unmatched[mpn] = _KNOWN_UNMATCHED[mpn]
            else:
                res.missing.append(mpn)
                res.unmatched[mpn] = "no (model ...) clause"
            continue
        raw = m.group(1)
        p = _resolve_model_path(raw, md)
        if p is None or not p.is_file():
            if mpn in _KNOWN_UNMATCHED:
                res.unmatched[mpn] = _KNOWN_UNMATCHED[mpn]
            else:
                res.broken[mpn] = raw
                res.unmatched[mpn] = f"model path does not resolve: {raw}"
            continue
        res.covered += 1
        clause = text[m.end():m.end() + 500]
        reason = _fit_ok(mod, clause, p)
        if reason is not None:
            res.misfit[mpn] = reason
        bad = _placed_ok(mod, clause, p)
        if bad is not None:
            res.misplaced[mpn] = bad
    res.ok = not res.broken and not res.missing and not res.misplaced
    return res


def run(rep_dir: Path | None = None,
        model_dir: Path | None = None) -> Model3dResult:
    res = check(model_dir=model_dir)
    if rep_dir is not None:
        rep_dir.mkdir(parents=True, exist_ok=True)
        (rep_dir / "model3d.txt").write_text(res.report() + "\n")
    return res
