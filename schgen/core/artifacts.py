from __future__ import annotations

import re
from pathlib import Path

SYNC_DUPLICATE_SUFFIX = re.compile(r" \d+$")


def is_sync_duplicate(path: Path) -> bool:
    return bool(SYNC_DUPLICATE_SUFFIX.search(path.stem))


def generated_pngs(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.png") if not is_sync_duplicate(p))
