from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from schgen.core import native
from schgen.core.project import PROJECT_ROOT
from schgen.verify._native_pcb import summary

K = 2
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"
_INTERFACE_JSON = PROJECT_ROOT / "som_interface.json"
_ROW_TOL = 0.05

@dataclass(frozen=True)
class Contact:
    ref: str
    pad: str
    row: int
    index: int
    x: float
    y: float
    net: str
    klass: str


@dataclass
class Violation:
    ref: str
    base: str
    net: str
    pad: str
    distance: int | None

    def _dist_str(self) -> str:
        return "none-on-connector" if self.distance is None else str(self.distance)

    def as_line(self) -> str:
        return native.module().pcb_return_violation_line(asdict(self))


@dataclass
class ReturnPathResult:
    ok: bool = True
    k: int = K
    n_pairs: int = 0
    n_pair_contacts: int = 0
    violations: list[Violation] = field(default_factory=list)
    dist_hist: dict[int, int] = field(default_factory=dict)
    per_conn: dict[str, tuple[int, int]] = field(default_factory=dict)
    pairs_per_conn: dict[str, int] = field(default_factory=dict)
    worst_distance: int | None = None
    connectors: list[str] = field(default_factory=list)

    @property
    def n_fail(self) -> int:
        return len(self.violations)

    def summary(self) -> str:
        return summary("return-path", self)


def classify_net(net: str) -> str:
    return native.module().pcb_classify_net(net)


def pair_partner(net: str) -> str | None:
    return native.module().pcb_pair_partner(net)


def pair_base(net: str, partner: str) -> str:
    return native.module().pcb_pair_base(net, partner)


def hs_pairs_in(nets: set[str]) -> dict[str, str]:
    return native.module().pcb_hs_pairs(nets)


def hs_pair_bases(nets: set[str]) -> list[str]:
    return sorted({n[:-2] for n in nets if n.endswith("_P")} &
                  {n[:-2] for n in nets if n.endswith("_N")})


def _resolve_footprint(value: str, footprint: str) -> Path | None:
    cand = _PARTS_DIR / value / f"{value}.kicad_mod"
    if cand.is_file():
        return cand
    _, _, name = footprint.partition(":")
    name = name.strip("_")
    if name.startswith("HRS_"):
        name = name[4:]
    if name:
        cand = _PARTS_DIR / name / f"{name}.kicad_mod"
        if cand.is_file():
            return cand
    return None



def _parse_pad_positions(mod_path: Path) -> dict[str, tuple[float, float]]:
    return native.module().pcb_return_pad_positions(str(mod_path), mod_path.read_text())


def build_contacts(ref: str, pins: dict[str, str],
                   positions: dict[str, tuple[float, float]]) -> list[Contact]:
    return [Contact(**row) for row in native.module().pcb_return_contacts_positions(ref, pins, positions)]


def check_map(contacts_by_ref: dict[str, list[Contact]], k: int = K):
    raw = native.module().pcb_return_path_map(
        {ref: [asdict(c) for c in contacts] for ref, contacts in contacts_by_ref.items()}, k)
    raw["violations"] = [Violation(**v) for v in raw["violations"]]
    return ReturnPathResult(**raw)


def check(
    interface_json: Path | None = None,
    k: int = K,
):
    path = interface_json or _INTERFACE_JSON
    data = json.loads(Path(path).read_text())
    connectors = data["connectors"]

    contacts_by_ref: dict[str, list[Contact]] = {}
    for ref in sorted(connectors):
        conn = connectors[ref]
        pins: dict[str, str] = conn["pins"]
        mod = _resolve_footprint(conn.get("value", ""), conn.get("footprint", ""))
        if mod is None:
            raise FileNotFoundError(
                f"{ref}: cannot resolve footprint dossier "
                f"(value={conn.get('value')!r}, "
                f"footprint={conn.get('footprint')!r})")
        positions = _parse_pad_positions(mod)
        contacts_by_ref[ref] = build_contacts(ref, pins, positions)

    return check_map(contacts_by_ref, k=k)
