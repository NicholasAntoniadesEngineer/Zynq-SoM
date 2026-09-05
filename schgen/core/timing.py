from __future__ import annotations

import os
import time
from collections import defaultdict
from contextlib import contextmanager

_ENABLED = os.environ.get("SCHGEN_TIMING", "") == "1"
_SPANS: dict[str, list[float]] = defaultdict(list)
_STACK: list[tuple[str, float]] = []


def enable() -> None:
    global _ENABLED
    _ENABLED = True


def enabled() -> bool:
    return _ENABLED


def reset() -> None:
    _SPANS.clear()
    _STACK.clear()


@contextmanager
def span(name: str):
    t0 = time.perf_counter()
    _STACK.append((name, t0))
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        _STACK.pop()
        _SPANS[name].append(dt)


def report() -> str:
    rows: list[tuple[str, int, float]] = []
    for name, samples in _SPANS.items():
        rows.append((name, len(samples), sum(samples)))
    rows.sort(key=lambda r: -r[2])
    total = sum(s for _n, _c, s in rows)
    lines = ["=== phase timing (wall s, this process) ==="]
    for name, n, s in rows:
        pct = (100.0 * s / total) if total else 0.0
        extra = f" n={n}" if n > 1 else ""
        lines.append(f"  {s:7.3f}  ({pct:5.1f}%)  {name}{extra}")
    lines.append(f"  {total:7.3f}  SUM OF NAMED SPANS")
    return "\n".join(lines)
