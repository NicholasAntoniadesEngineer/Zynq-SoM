from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "lcsc_values.json"

_INLINE_PASSIVE = {"Device:R": "R", "Device:C": "C", "Device:L": "L"}

_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
           "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
_PREFIX_CHARS = "pnuµmkKMG"


@dataclass
class BomValueResult:
    ok: bool = True
    checked: int = 0
    mismatches: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    catalog_size: int = 0

    def report(self) -> str:
        lines = ["bom value gate (LCSC actual value == declared value)",
                 "=" * 60,
                 f"catalog: {self.catalog_size} LCSC codes; "
                 f"{self.checked} inline-passive checks"]
        if self.mismatches:
            lines.append("")
            lines.append(f"MISMATCH ({len(self.mismatches)}) — FAIL:")
            lines += [f"  {m}" for m in self.mismatches]
        else:
            lines.append("mismatches: none")
        if self.unverified:
            lines.append("")
            lines.append(f"UNVERIFIED — reported, NOT failing "
                         f"({len(self.unverified)}):")
            lines += [f"  {u}" for u in sorted(set(self.unverified))]
        return "\n".join(lines)


def _norm(value: str, cls_hint: str | None) -> tuple[str, float] | None:
    s = value.strip()
    if not s:
        return None
    cls = cls_hint
    low = s.lower()
    if low.endswith("ohm"):
        cls, s = "R", s[:-3]
    elif s.endswith("Ω"):
        cls, s = "R", s[:-1]
    elif s.endswith("F"):
        cls, s = "C", s[:-1]
    elif s.endswith("H"):
        cls, s = "L", s[:-1]
    elif s.endswith("R") or s.endswith("r"):
        if re.fullmatch(r"[0-9.]+[pnuµmkKMG]?[Rr]", s):
            cls, s = "R", s[:-1]
    if cls is None:
        return None
    s = s.strip()
    m = re.fullmatch(r"(\d+)([pnuµmkKMG])(\d+)", s)
    if m:
        mag = float(f"{m.group(1)}.{m.group(3)}") * _PREFIX[m.group(2)]
        return (cls, mag)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([pnuµmkKMG]?)", s)
    if not m:
        return None
    mag = float(m.group(1)) * (_PREFIX[m.group(2)] if m.group(2) else 1.0)
    return (cls, mag)


def _equal(a: tuple[str, float], b: tuple[str, float]) -> bool:
    if a[0] != b[0]:
        return False
    hi = max(abs(a[1]), abs(b[1]))
    return hi == 0 or abs(a[1] - b[1]) <= 0.005 * hi


def load_catalog() -> dict[str, dict]:
    return json.loads(_DATA.read_text())


def run(sheets, rep_dir: Path | None = None,
        catalog: dict | None = None) -> BomValueResult:
    cat = catalog if catalog is not None else load_catalog()
    res = BomValueResult(catalog_size=len(cat))
    for sc in sheets:
        for ref, part in sc.circuit.parts.items():
            lcsc = part.fields.get("LCSC", "")
            if not lcsc:
                continue
            cls_hint = _INLINE_PASSIVE.get(part.lib_id)
            entry = cat.get(lcsc)
            if entry is None:
                res.unverified.append(
                    f"{sc.name}:{ref} {part.value!r} LCSC {lcsc} "
                    f"(not in catalog)")
                continue
            if cls_hint is None:
                continue
            decl = _norm(part.value, cls_hint)
            real = _norm(str(entry.get("value", "")), None)
            if decl is None or real is None:
                continue
            res.checked += 1
            if not _equal(decl, real):
                res.ok = False
                note = entry.get("note", "")
                res.mismatches.append(
                    f"{sc.name}:{ref} declares {part.value!r} but LCSC {lcsc} "
                    f"is {entry.get('value')!r} "
                    f"({decl[1]:g} vs {real[1]:g} {decl[0]})"
                    + (f" — {note}" if note else ""))
    if rep_dir is not None:
        (Path(rep_dir) / "bom_values.txt").write_text(res.report() + "\n")
    return res
