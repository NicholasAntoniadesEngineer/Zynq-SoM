from __future__ import annotations

import ast
import io
import math
import tokenize
from dataclasses import asdict, dataclass, field
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ZoneInfo:
    name: str
    net_name: str
    layers: tuple[str, ...]
    keepout: bool
    filled: bool
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class ViaInfo:
    x: float
    y: float
    net_name: str


@dataclass(frozen=True)
class PadInfo:
    name: str
    dx: float
    dy: float
    drill: float
    net_name: str


@dataclass(frozen=True)
class FpInfo:
    ref: str
    value: str
    x: float
    y: float
    layer: str
    pads: tuple[PadInfo, ...]


@dataclass
class BoardCopper:
    path: Path
    zones: list[ZoneInfo] = field(default_factory=list)
    vias: list[ViaInfo] = field(default_factory=list)
    segments: int = 0
    footprints: list[FpInfo] = field(default_factory=list)
    net_names: set[str] = field(default_factory=set)

    def fill_zones(self, net: str, layer: str) -> list[ZoneInfo]:
        return [z for z in self.zones
                if not z.keepout and z.filled and z.net_name == net
                and layer in z.layers]

    def gnd_plane(self, layer: str = "In1.Cu") -> bool:
        return bool(self.fill_zones("GND", layer))

    def instances(self, value_prefix: str) -> list[FpInfo]:
        return sorted((f for f in self.footprints
                       if f.value.startswith(value_prefix)),
                      key=lambda f: f.ref)

    def gnd_vias_within(self, x: float, y: float, r: float) -> int:
        return sum(1 for v in self.vias if v.net_name == "GND"
                   and math.hypot(v.x - x, v.y - y) <= r)

    def pour_at(self, x: float, y: float, layer: str,
                net: str = "GND") -> bool:
        return any(z.bbox[0] <= x <= z.bbox[2] and z.bbox[1] <= y <= z.bbox[3]
                   for z in self.fill_zones(net, layer))

    def zone_named(self, prefix: str) -> list[ZoneInfo]:
        return sorted((z for z in self.zones if z.name.startswith(prefix)),
                      key=lambda z: z.name)

    def net_copper(self, net_substr: str) -> tuple[int, int]:
        zs = sum(1 for z in self.zones
                 if not z.keepout and net_substr in z.net_name)
        vs = sum(1 for v in self.vias if net_substr in v.net_name)
        return zs, vs


def scan_board(pcb_path: Path) -> BoardCopper:
    """Native emitted-copper scan; dataclasses retain the compatibility API."""
    from schgen.core import native
    raw = native.module().copper_debt_scan(str(pcb_path))
    return BoardCopper(
        path=Path(raw["path"]),
        zones=[ZoneInfo(**{**z, "layers": tuple(z["layers"]),
                           "bbox": tuple(z["bbox"])}) for z in raw["zones"]],
        vias=[ViaInfo(**v) for v in raw["vias"]],
        segments=raw["segments"],
        footprints=[FpInfo(**{**f, "pads": tuple(PadInfo(**p) for p in f["pads"])})
                    for f in raw["footprints"]],
        net_names=set(raw["net_names"]))


class AnchorError(RuntimeError):
    pass


_ANCHOR_RULE = ("anchors bind to STRUCTURE — code, or a registered basis "
                "entry name — never to a sentence that a prose purge deletes")


def _prose_lines(src: str) -> set[int]:
    lines = {t.start[0] for t in tokenize.generate_tokens(
        io.StringIO(src).readline) if t.type == tokenize.COMMENT}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            end = node.end_lineno or node.lineno
            lines.update(range(node.lineno, end + 1))
    return lines


def _where(eid: str, rel_path: str, anchor: str) -> str:
    """Legacy source-helper API only; native claim provenance never calls it."""
    p = REPO_ROOT / rel_path
    if not p.exists():
        raise AnchorError(
            f"copper_debt {eid}: anchor file {rel_path} does not exist — the "
            f"claim is unmoored ({_ANCHOR_RULE})")
    src = p.read_text()
    prose = _prose_lines(src)
    for n, line in enumerate(src.splitlines(), 1):
        if anchor not in line:
            continue
        if n in prose:
            raise AnchorError(
                f"copper_debt {eid}: anchor {anchor!r} resolves to PROSE at "
                f"{rel_path}:{n} — {_ANCHOR_RULE}")
        return f"{rel_path}:{n}"
    raise AnchorError(
        f"copper_debt {eid}: anchor {anchor!r} is not in {rel_path} — "
        f"{_ANCHOR_RULE}")


@dataclass
class Entry:
    eid: str
    title: str
    assumes: str
    where: list[str]
    emits: str
    status: str
    risk: str


@dataclass
class Result:
    entries: list[Entry] = field(default_factory=list)
    inventory: str = ""

    @property
    def n_entries(self) -> int:
        return len(self.entries)

    def n_status(self, s: str) -> int:
        return sum(1 for e in self.entries if e.status == s)


def analyze(pcb_path: Path | None, *, sheets=None,
            project: str | None = None) -> Result:
    """Verify live native claims, then measure the actual emitted copper.

    A build pipeline supplies its netlisted sheets. Without a caller snapshot,
    all registered circuits are freshly authored by C++, never loaded from IR
    fixtures or Python constructors.
    """
    from schgen.core.authoring import _engine, audit_inputs
    from schgen.generate.constraints import GEOMETRY
    from schgen.generate.pcb._native_emit import policy
    from schgen.verify.thermal import _native_policy
    engine = _engine()
    copper = (engine.copper_debt_scan(str(pcb_path))
              if pcb_path and Path(pcb_path).exists() else None)
    raw = engine.copper_debt_analyze(
        copper, audit_inputs(sheets, project=project),
        _native_policy(), policy(), [asdict(v) for v in GEOMETRY.values()])
    return Result(entries=[Entry(**e) for e in raw["entries"]],
                  inventory=raw["inventory"])


def report(res: Result) -> str:
    from schgen.core import native
    return native.module().copper_debt_report(asdict(res))


def run(reports_dir: Path, pcb_path: Path | None, *, sheets=None,
        project: str | None = None) -> Result:
    res = analyze(pcb_path, sheets=sheets, project=project)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "copper_debt.txt").write_text(report(res) + "\n")
    return res


if __name__ == "__main__":
    _pcb = PROJECT_ROOT / "Zynq_Carrier.kicad_pcb"
    _res = run(PROJECT_ROOT / "reports", _pcb)
    print(report(_res))
