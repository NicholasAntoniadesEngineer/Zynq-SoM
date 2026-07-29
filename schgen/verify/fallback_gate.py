"""FALLBACK RATCHET GATE — no placement fallback may fire more often than its
committed per-project baseline (governance U2, the D13-style ratchet over
``schgen/core/fallbacks.py``).

The census (``{name: count}`` read after board emission) is compared against
``<project>/reports/fallback_baseline.json``. A name absent from the baseline
is allowed ZERO firings — a NEW fallback path must start clean or have its
measured debt explicitly committed. First run with no baseline file pins the
live counts honestly (reviewable in git); a PASS ratchets each ceiling DOWN to
the live count (never up), so retired debt can never regrow. Any count over
its ceiling FAILS the board loudly, naming the fallback — a sheet silently
dropping to a degraded path becomes a same-day build failure. This bounds how
often the pipeline may degrade; it never relaxes any per-part rule (LAW 4).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

_BASELINE_PATH = PROJECT_ROOT / "reports" / "fallback_baseline.json"


@dataclass
class FallbackResult:
    ok: bool = True
    pinned: bool = False
    n_names: int = 0
    n_fired: int = 0
    regressions: list[str] = field(default_factory=list)

    def summary(self) -> str:
        head = (f"FALLBACK RATCHET: {'PASS' if self.ok else 'FAIL'} — "
                f"{self.n_names} registered paths, {self.n_fired} firing"
                + (" (baseline PINNED this build)" if self.pinned else ""))
        return "\n".join([head] + [f"  REGRESSION: {r}"
                                   for r in self.regressions])


def _load(path: Path) -> dict[str, int] | None:
    try:
        raw = json.loads(path.read_text())
        return {str(k): int(v) for k, v in raw["counts"].items()}
    except Exception:  # noqa: BLE001 — absent/corrupt => first-run pin
        return None


def _write(path: Path, counts: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "counts": {k: counts[k] for k in sorted(counts)},
        "note": "fallback ratchet ceilings — a build whose count EXCEEDS its "
                "ceiling FAILS; ceilings only ever DECREASE (pinned from a "
                "measured build, reviewed in git). A name absent here is "
                "allowed zero firings.",
    }, indent=1) + "\n")


def check(census: dict[str, int],
          baseline_path: Path | None = None) -> FallbackResult:
    p = baseline_path or _BASELINE_PATH
    baseline = _load(p)
    res = FallbackResult(n_names=len(census),
                         n_fired=sum(1 for v in census.values() if v))
    if baseline is None:
        _write(p, census)
        res.pinned = True
        return res
    for name in sorted(census):
        ceiling = baseline.get(name, 0)
        if census[name] > ceiling:
            res.ok = False
            res.regressions.append(
                f"{name}: fired {census[name]} > baseline {ceiling} — a "
                f"degraded path bound more often than the committed ceiling")
    if res.ok:
        lowered = {k: min(census.get(k, 0), v) for k, v in baseline.items()}
        if lowered != baseline:
            _write(p, lowered)
    return res
