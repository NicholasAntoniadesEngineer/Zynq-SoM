from __future__ import annotations

from dataclasses import dataclass, field
from schgen.core import native
from schgen.core.project import PROJECT_ROOT, spec as _project_spec
from schgen.verify._native_pcb import prepare, summary

GENUINE_DLANE_MAX = 2
RULE_CLEARANCE = 0.15
PITCH = 0.4


@dataclass
class EscapeLaneResult:
    ok: bool = True
    n_lanes: int = 0
    n_pairs: int = 0
    n_genuine: int = 0
    violations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return summary("escape-lanes", self)


def _population_pins() -> tuple[dict[str, int] | None, int | None]:
    esc = _project_spec().escape
    netted = esc.get("netted_contacts")
    genuine = esc.get("genuine_pairs")
    return (({str(k): int(v) for k, v in netted.items()}
             if isinstance(netted, dict) else None),
            (int(genuine) if genuine is not None else None))


def check(model, *, prepared=None) -> EscapeLaneResult:
    path = PROJECT_ROOT / "som_interface.json"
    return EscapeLaneResult(**native.module().pcb_escape_lanes(
        (prepare(model) if prepared is None else prepared), dict(_project_spec().escape), path.read_bytes().decode("utf-8")))
