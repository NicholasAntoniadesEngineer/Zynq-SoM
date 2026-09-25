from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from schgen.core import native


@dataclass
class RefdesOverlapResult:
    ok: bool = True
    n_top: int = 0
    n_bottom: int = 0
    top_pairs: list = field(default_factory=list)
    bottom_pairs: int = 0


def check(pcb_path, enforce_bottom: bool = False) -> RefdesOverlapResult:
    return RefdesOverlapResult(**native.module().pcb_refdes_overlap(
        Path(pcb_path).read_text(), enforce_bottom))
