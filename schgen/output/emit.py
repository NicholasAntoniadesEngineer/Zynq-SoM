from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from schgen.core import native as _nat
from schgen.core.model import Circuit
from schgen.core.symbols import Library

PAPER_DEFAULT = "A4"


@dataclass
class PlacedPart:
    ref: str
    lib_id: str
    value: str
    x: float
    y: float
    rotation: int = 0
    footprint: str = ""
    ref_pos: tuple[float, float, int] | None = None
    val_pos: tuple[float, float, int] | None = None


@dataclass
class PlacedPower:
    lib_id: str
    value: str
    ref: str
    x: float
    y: float
    rotation: int = 0
    net: str = ""
    val_pos: tuple[float, float, int] | None = None
    show_value: bool = False

    @property
    def net_name(self) -> str:
        return self.net or self.value


@dataclass
class Wire:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Junction:
    x: float
    y: float


@dataclass
class HierLabel:
    name: str
    x: float
    y: float
    rotation: int = 0
    shape: str = "bidirectional"


@dataclass
class LocalLabel:
    name: str
    x: float
    y: float
    rotation: int = 0


@dataclass
class NoConnect:
    x: float
    y: float


@dataclass
class SheetPin:
    name: str
    x: float
    y: float
    rotation: int = 180
    shape: str = "bidirectional"


@dataclass
class SheetSymbol:
    name: str
    file: str
    x: float
    y: float
    w: float
    h: float
    uuid: str
    pins: list[SheetPin] = field(default_factory=list)
    page: str = "2"


@dataclass
class PlacedDesign:
    circuit: Circuit
    parts: list[PlacedPart] = field(default_factory=list)
    powers: list[PlacedPower] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    junctions: list[Junction] = field(default_factory=list)
    hlabels: list[HierLabel] = field(default_factory=list)
    llabels: list[LocalLabel] = field(default_factory=list)
    no_connects: list[NoConnect] = field(default_factory=list)
    sheets: list[SheetSymbol] = field(default_factory=list)
    paper: str = PAPER_DEFAULT
    standalone: bool = True


def stable_uuid(*parts: object) -> str:
    return _nat.module().schematic_stable_uuid([str(p) for p in parts])


class _IdFactory:
    def __init__(self, scope: str) -> None:
        self._native = _nat.module().SchematicIdFactory(scope)

    def __call__(self, kind: str) -> str:
        return self._native(kind)


def emit(design: PlacedDesign, out_path: Path, lib: Library, *,
         instance_path: str | None = None,
         project: str | None = None,
         sheet_uuid: str | None = None) -> Path:
    """Transport placed data to the native emitter and publish its exact text."""
    placement = {
        name: [asdict(item) for item in getattr(design, name)]
        for name in ("parts", "powers", "wires", "junctions", "hlabels",
                     "llabels", "no_connects", "sheets")
    }
    placement.update(paper=design.paper, standalone=design.standalone)
    text = _nat.module().emit_schematic(
        design.circuit.to_ir(), placement, lib.get,
        instance_path=instance_path, project=project, sheet_uuid=sheet_uuid)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return out_path
