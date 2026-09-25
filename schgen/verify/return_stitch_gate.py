from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from schgen.core import native
from schgen.core.project import PROJECT_ROOT
from schgen.verify._native_pcb import prepare, summary

RETURN_VIA_RADIUS_MM = 2.0
V1_PINNED = {"n_pairs": 69, "n_pair_contacts": 138, "n_fail": 29, "worst_distance": 4}
RULE_CLEARANCE = 0.15
RULE_HOLE_CLEARANCE = 0.2
RULE_HOLE_TO_HOLE = 0.25

@dataclass
class ReturnStitchResult:
    ok: bool = True
    radius: float = RETURN_VIA_RADIUS_MM
    n_contacts: int = 0
    n_covered: int = 0
    worst_mm: float = 0.0
    n_vias: int = 0
    violations: list[str] = field(default_factory=list)
    coverage: list[tuple] = field(default_factory=list)
    per_conn: dict[str, tuple[int, int]] = field(default_factory=dict)
    v1_verdict: str = ""
    hash_ok: bool = True
    file_parity: str = "not-checked"

    def summary(self) -> str:
        return summary("return-stitch", self)


def _som_interface_sha256() -> str:
    return hashlib.sha256((PROJECT_ROOT / "som_interface.json").read_bytes()).hexdigest()


def check(model, pcb_path: Path | None = None, *, prepared=None, return_path=None) -> ReturnStitchResult:
    from schgen.verify import return_path_gate as rpg, si_triage
    v1 = rpg.check() if return_path is None else return_path
    triage = {}
    for violation in v1.violations:
        if violation.net not in triage:
            klass = si_triage.classify(violation.net)
            triage[violation.net] = (si_triage.RANK[klass.klass], klass.klass, klass.function)
    path = Path(pcb_path) if pcb_path is not None else None
    pcb_bytes = path.read_text() if path is not None and path.exists() else None
    raw = native.module().pcb_return_stitch(
        (prepare(model) if prepared is None else prepared), asdict(v1), triage,
        (PROJECT_ROOT / "som_interface.json").read_bytes().decode("utf-8"),
        str(path) if path is not None else "", pcb_bytes, path is not None)
    return ReturnStitchResult(**raw)
