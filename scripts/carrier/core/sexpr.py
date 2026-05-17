"""S-expression emitter for KiCad 9.0 schematic files.

KiCad uses a Lisp-style S-expression format. This module emits well-formed
S-expressions with KiCad-style tab indentation, plus the typed coordinate
primitives, grid utilities, Y-axis-aware screen helpers, and the public
emitter functions used throughout the carrier generator.

Design intent (kicad-sch-api compatible):
    - All coordinates expressed as Point in millimetres (KiCad native unit)
    - All positions assumed grid-aligned (1.27mm = 50 mil); off-grid fails hard
    - KiCad schematic space has inverted Y-axis (+Y = visually DOWN); the
      screen_above/below/left/right helpers encode this so call sites are
      self-documenting
    - SExp supports a raw-text passthrough mode for dropping in legacy
      symbol-library blocks verbatim without re-parsing them

Public API (used by sheet_emitter and generator):
    Point, KICAD_GRID_MM, snap_to_grid, assert_on_grid
    screen_above, screen_below, screen_left, screen_right
    SExp, SExp.raw, make_uuid, quote
    at, xy, effects, property_
    wire, junction, global_label, local_label, hierarchical_label,
    sheet_pin, sheet_instance, text_label
"""

from __future__ import annotations

import math
import uuid as uuid_module
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Literal, Union


KICAD_GRID_MM: float = 1.27
"""KiCad default schematic grid (50 mil / 1.27 mm)."""

GRID_TOLERANCE_MM: float = 1e-4
"""Numeric tolerance for grid-alignment checks (0.0001 mm)."""

LabelShape = Literal["input", "output", "bidirectional", "tri_state", "passive"]


# ---------------------------------------------------------------------------
# Coordinate primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    """A 2D coordinate in KiCad schematic space (millimetres).

    KiCad schematic space has an inverted Y-axis: lower Y values appear
    visually HIGHER on screen. Use screen_above/below/left/right helpers to
    avoid sign mistakes at call sites.

    Implements __iter__ so callers can spread a Point into existing
    tuple-based APIs: ``xy(*point)`` and ``at(*point, angle)`` both work.
    """

    x: float
    y: float

    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y

    def offset(self, dx: float = 0.0, dy: float = 0.0) -> "Point":
        return Point(self.x + dx, self.y + dy)

    def snap(self, grid: float = KICAD_GRID_MM) -> "Point":
        return Point(snap_to_grid(self.x, grid), snap_to_grid(self.y, grid))

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


PointLike = Union[Point, tuple[float, float]]


def to_point(value: PointLike) -> Point:
    """Coerce a (x, y) tuple or Point into a Point."""
    if isinstance(value, Point):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return Point(float(value[0]), float(value[1]))
    raise TypeError(
        f"Expected Point or (x, y) tuple, got {type(value).__name__}: {value!r}"
    )


def snap_to_grid(value: float, grid: float = KICAD_GRID_MM) -> float:
    """Round a coordinate to the nearest grid increment."""
    if grid <= 0:
        raise ValueError(f"Grid step must be positive, got {grid}")
    return round(value / grid) * grid


def assert_on_grid(
    position: PointLike,
    grid: float = KICAD_GRID_MM,
    tolerance: float = GRID_TOLERANCE_MM,
) -> None:
    """Fail hard if a point is not on the given grid.

    Per project compliance rules, off-grid coordinates are an error rather
    than a warning - they cause silent KiCad connectivity failures.
    """
    point = to_point(position)
    snapped_x = snap_to_grid(point.x, grid)
    snapped_y = snap_to_grid(point.y, grid)
    if (
        abs(point.x - snapped_x) > tolerance
        or abs(point.y - snapped_y) > tolerance
    ):
        raise ValueError(
            f"Point ({point.x}, {point.y}) is not on {grid}mm grid; "
            f"would snap to ({snapped_x}, {snapped_y})"
        )


# ---------------------------------------------------------------------------
# Y-axis-aware screen direction helpers
# ---------------------------------------------------------------------------
#
# KiCad schematic space has +Y pointing DOWN on the rendered page. These
# helpers encode the inversion so call-site code reads naturally:
#
#     decoupling_position = screen_above(ic.vdd_pin_position, 5.08)
#
# is unambiguously "5.08 mm visually higher on the page than the VDD pin",
# regardless of whether you remember which axis sign points where.


def screen_above(position: PointLike, distance_mm: float) -> Point:
    """Return a Point displaced visually upward on screen (smaller Y in KiCad)."""
    point = to_point(position)
    return Point(point.x, point.y - distance_mm)


def screen_below(position: PointLike, distance_mm: float) -> Point:
    """Return a Point displaced visually downward on screen (larger Y in KiCad)."""
    point = to_point(position)
    return Point(point.x, point.y + distance_mm)


def screen_left(position: PointLike, distance_mm: float) -> Point:
    point = to_point(position)
    return Point(point.x - distance_mm, point.y)


def screen_right(position: PointLike, distance_mm: float) -> Point:
    point = to_point(position)
    return Point(point.x + distance_mm, point.y)


# ---------------------------------------------------------------------------
# UUID and string utilities
# ---------------------------------------------------------------------------


def make_uuid() -> str:
    """Generate a unique UUID string for use as a KiCad object identifier."""
    return str(uuid_module.uuid4())


def quote(value: str) -> str:
    """Quote a string for inclusion in an S-expression literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass(frozen=True)
class Keyword:
    """Wrapper for an unquoted keyword atom in S-expression output.

    KiCad's native ``.kicad_sch`` format uses bare keyword atoms for fields
    like ``(justify left)``, ``(shape input)``, ``(type default)``. Wrapping
    a string in ``Keyword`` instructs ``_render_atom`` to emit it without
    quotes, preserving byte-exact format compatibility with KiCad output.
    """

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Keyword.name must be non-empty")


# ---------------------------------------------------------------------------
# SExp - the canonical S-expression node
# ---------------------------------------------------------------------------


@dataclass
class SExp:
    """An S-expression node.

    Attributes:
        head: First token of the form (e.g. "symbol", "wire").
        atoms: Literal tokens (numbers, strings, bools) appearing right after head.
        children: Nested SExp child forms.
        raw_text: If set, ``dumps`` emits this text verbatim (with indentation
            applied per line) and ignores ``atoms``/``children``. Used to inline
            already-serialised KiCad library blocks without round-tripping them
            through the parser.
    """

    head: str
    atoms: list[Any] = field(default_factory=list)
    children: list["SExp"] = field(default_factory=list)
    raw_text: str | None = None

    @classmethod
    def raw(cls, text: str) -> "SExp":
        """Build an SExp that emits ``text`` verbatim from ``dumps()``."""
        return cls(head="__raw__", raw_text=text)

    def add(self, child: "SExp") -> "SExp":
        self.children.append(child)
        return self

    def add_all(self, *children_to_add: "SExp") -> "SExp":
        for child in children_to_add:
            self.children.append(child)
        return self

    def dumps(self, indent: int = 0) -> str:
        """Render this S-expression with KiCad-style tab indentation."""
        pad = "\t" * indent
        if self.raw_text is not None:
            lines = self.raw_text.splitlines()
            return "\n".join(pad + line if line else line for line in lines)
        atoms_str = ""
        if self.atoms:
            atoms_str = " " + " ".join(_render_atom(a) for a in self.atoms)
        if not self.children:
            return f"{pad}({self.head}{atoms_str})"
        rendered_lines = [f"{pad}({self.head}{atoms_str}"]
        for child in self.children:
            rendered_lines.append(child.dumps(indent + 1))
        rendered_lines.append(f"{pad})")
        return "\n".join(rendered_lines)


def _render_atom(value: Any) -> str:
    if isinstance(value, Keyword):
        return value.name
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                raise ValueError(f"Cannot render non-finite float: {value}")
            return f"{value:.4g}"
        return str(value)
    if isinstance(value, str):
        if value.startswith('"') and value.endswith('"'):
            return value
        return quote(value)
    raise TypeError(f"Cannot render atom of type {type(value).__name__}: {value!r}")


# ---------------------------------------------------------------------------
# Common nested forms used across emitters
# ---------------------------------------------------------------------------


def at(x_or_point: Union[float, PointLike], y: float | None = None,
       angle: float = 0.0) -> SExp:
    """Build an ``(at x y angle)`` form. Accepts either ``at(point, angle=...)``
    or the legacy ``at(x, y, angle)`` form for backward compatibility."""
    if isinstance(x_or_point, (Point, tuple)):
        point = to_point(x_or_point)
        x_value, y_value = point.x, point.y
    else:
        if y is None:
            raise ValueError("at() requires either a Point or (x, y) numerics")
        x_value, y_value = float(x_or_point), float(y)
    return SExp("at", atoms=[x_value, y_value, float(angle)])


def xy(x_or_point: Union[float, PointLike], y: float | None = None) -> SExp:
    """Build an ``(xy x y)`` form. Accepts a Point/tuple or (x, y) floats."""
    if isinstance(x_or_point, (Point, tuple)):
        point = to_point(x_or_point)
        return SExp("xy", atoms=[point.x, point.y])
    if y is None:
        raise ValueError("xy() requires either a Point or (x, y) numerics")
    return SExp("xy", atoms=[float(x_or_point), float(y)])


def effects(
    font_size: float = 1.27,
    bold: bool = False,
    italic: bool = False,
    justify: str | None = None,
    hide: bool = False,
) -> SExp:
    font = SExp("font").add(SExp("size", atoms=[font_size, font_size]))
    if bold:
        font.add(SExp("bold", atoms=[True]))
    if italic:
        font.add(SExp("italic", atoms=[True]))
    body = SExp("effects").add(font)
    if justify:
        justify_atoms = [Keyword(token) for token in justify.split()]
        body.add(SExp("justify", atoms=justify_atoms))
    if hide:
        body.add(SExp("hide", atoms=[True]))
    return body


def property_(
    name: str,
    value: str,
    x: float,
    y: float,
    font_size: float = 1.27,
    hide: bool = False,
    justify: str | None = None,
    bold: bool = False,
) -> SExp:
    prop = SExp("property", atoms=[name, value])
    prop.add(at(x, y, 0))
    prop.add(effects(font_size=font_size, bold=bold, justify=justify, hide=hide))
    return prop


# ---------------------------------------------------------------------------
# Public emitters: wires, junctions, labels, sheet pins, text
# ---------------------------------------------------------------------------
#
# These were previously underscore-prefixed private helpers in
# scripts/carrier/sheet_emitter.py. Per the project compliance rule "No
# unnecessary function wrappers", they are promoted to public API here so
# every caller (sheet_emitter, placement, geometry) reaches them by the
# same public name.


def wire(start: PointLike, end: PointLike, stroke_width: float = 0.0,
         stroke_type: str = "default") -> SExp:
    """Emit a (wire ...) form, asserting both endpoints are grid-aligned."""
    start_point = to_point(start)
    end_point = to_point(end)
    assert_on_grid(start_point)
    assert_on_grid(end_point)
    body = SExp("wire")
    pts = SExp("pts").add(xy(start_point)).add(xy(end_point))
    body.add(pts)
    stroke = SExp("stroke")
    stroke.add(SExp("width", atoms=[stroke_width]))
    stroke.add(SExp("type", atoms=[Keyword(stroke_type)]))
    body.add(stroke)
    body.add(SExp("uuid", atoms=[make_uuid()]))
    return body


def junction(position: PointLike, diameter: float = 0.0) -> SExp:
    """Emit a (junction ...) form at the given grid-aligned position."""
    point = to_point(position)
    assert_on_grid(point)
    body = SExp("junction")
    body.add(at(point, 0, 0))
    body.add(SExp("diameter", atoms=[diameter]))
    body.add(SExp("color", atoms=[0, 0, 0, 0]))
    body.add(SExp("uuid", atoms=[make_uuid()]))
    return body


def _label_body(head: str, net: str, position: PointLike, angle: float,
                shape: LabelShape | None) -> SExp:
    point = to_point(position)
    assert_on_grid(point)
    body = SExp(head, atoms=[net])
    if shape is not None:
        body.add(SExp("shape", atoms=[Keyword(shape)]))
    body.add(at(point.x, point.y, angle))
    body.add(effects(justify="left"))
    body.add(SExp("uuid", atoms=[make_uuid()]))
    return body


def global_label(net: str, position: PointLike, angle: float = 0.0,
                 shape: LabelShape = "input") -> SExp:
    """Emit a (global_label ...) form. Visible on every sheet that uses ``net``."""
    body = _label_body("global_label", net, position, angle, shape)
    intersheet = SExp("property", atoms=["Intersheetrefs", ""])
    intersheet.add(at(0, 0, 0))
    intersheet.add(effects(hide=True))
    body.add(intersheet)
    return body


def local_label(net: str, position: PointLike, angle: float = 0.0) -> SExp:
    """Emit a (label ...) form local to one sheet."""
    return _label_body("label", net, position, angle, shape=None)


def hierarchical_label(net: str, position: PointLike, angle: float = 0.0,
                       shape: LabelShape = "bidirectional") -> SExp:
    """Emit a (hierarchical_label ...) form for sheet-to-sheet net traversal.

    The matching parent-side ``sheet_pin`` must have the same ``net`` and
    ``shape`` for the connection to be valid (enforced by Rule J6).
    """
    return _label_body("hierarchical_label", net, position, angle, shape)


def sheet_pin(net: str, position: PointLike, angle: float = 0.0,
              shape: LabelShape = "bidirectional") -> SExp:
    """Emit a (pin ...) entry that goes inside a (sheet ...) instance."""
    point = to_point(position)
    assert_on_grid(point)
    body = SExp("pin", atoms=[net, Keyword(shape)])
    body.add(at(point.x, point.y, angle))
    body.add(effects(justify="left"))
    body.add(SExp("uuid", atoms=[make_uuid()]))
    return body


def sheet_instance(name: str, file_path: str, position: PointLike,
                   size_mm: tuple[float, float],
                   pins: Iterable[SExp]) -> SExp:
    """Emit a (sheet ...) instance that references a child .kicad_sch file."""
    point = to_point(position)
    assert_on_grid(point)
    width_mm, height_mm = size_mm
    body = SExp("sheet")
    body.add(at(point.x, point.y, 0))
    body.add(SExp("size", atoms=[width_mm, height_mm]))
    body.add(SExp("exclude_from_sim", atoms=[False]))
    body.add(SExp("in_bom", atoms=[True]))
    body.add(SExp("on_board", atoms=[True]))
    body.add(SExp("dnp", atoms=[False]))
    body.add(SExp("fields_autoplaced", atoms=[True]))
    stroke = SExp("stroke")
    stroke.add(SExp("width", atoms=[0.1524]))
    stroke.add(SExp("type", atoms=[Keyword("solid")]))
    body.add(stroke)
    body.add(SExp("fill").add(SExp("color", atoms=[0, 0, 0, 0])))
    body.add(SExp("uuid", atoms=[make_uuid()]))
    body.add(property_("Sheetname", name, x=point.x, y=point.y - 0.508,
                       font_size=1.27, justify="left bottom", bold=True))
    body.add(property_("Sheetfile", file_path,
                       x=point.x, y=point.y + height_mm + 0.508,
                       font_size=1.27, justify="left top"))
    for pin_entry in pins:
        body.add(pin_entry)
    return body


def text_label(text: str, position: PointLike, font_size: float = 2.54,
               bold: bool = True, justify: str = "left bottom") -> SExp:
    """Emit a (text ...) form for free-text annotations / section banners."""
    point = to_point(position)
    body = SExp("text", atoms=[text])
    body.add(at(point.x, point.y, 0))
    body.add(effects(font_size=font_size, bold=bold, justify=justify))
    body.add(SExp("uuid", atoms=[make_uuid()]))
    return body
