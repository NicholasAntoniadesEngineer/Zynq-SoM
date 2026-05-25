"""Symbol geometry: pin positions + bounding boxes from ``.kicad_sym`` files.

The layout engine reads pin coordinates from real symbol definitions instead
of hand-coded offsets. This module wraps ``kicad-sch-api``'s symbol cache and
exposes:

    - :meth:`SymbolGeometryCache.register_libraries` — register ``.kicad_sym``
      paths (idempotent; safe to call repeatedly).
    - :meth:`SymbolGeometryCache.absolute_pin_by_name` — resolve a named pin
      to its absolute wire-attachment coordinate when the symbol is placed
      at a given anchor with a given rotation.
    - :meth:`SymbolGeometryCache.bounding_box` — compute the symbol's
      bounding box (min/max x/y) relative to its anchor.
    - :meth:`SymbolGeometryCache.all_pins` — enumerate every pin on a symbol
      (name, number, position relative to anchor).

Implementation: ``kicad-sch-api`` exposes pin positions only via a *placed*
component on a *schematic*. We create a throw-away in-memory schematic per
query (the schematic is never saved). Results are cached by
``(lib_id, rotation)`` so repeated lookups for the same symbol are cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import kicad_sch_api as ksa

from zynq_eda.core.model.grid import KICAD_GRID_MM, Point, snap_to_grid


DEFAULT_PIN_LENGTH_MM = KICAD_GRID_MM
"""Length of the visible pin stub outside the symbol body (KiCad default: 1.27 mm)."""


@dataclass(frozen=True)
class PinGeometry:
    """Resolved geometry for a single pin instance.

    Attributes:
        anchor: Absolute coordinate where the pin's electrical endpoint sits
            (where wires terminate). On the schematic this is the "tip" of
            the visible pin stub.
        connection: Same as ``anchor`` for KiCad; kept distinct in case future
            engines want to differentiate (e.g. an off-symbol "via" point).
        relative: Position of the pin relative to the symbol's anchor (before
            rotation/translation). Used to determine which side of the body
            the pin is on (left/right/top/bottom).
    """

    anchor: Point
    connection: Point
    relative: Point


@dataclass(frozen=True)
class SymbolBoundingBox:
    """Bounding box of a symbol, derived from its pin extents + body padding.

    All coordinates are relative to the symbol's anchor (centre/origin in
    KiCad's symbol model).
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def shift_by(self, anchor: Point) -> "SymbolBoundingBox":
        """Translate from anchor-relative to absolute coordinates."""
        return SymbolBoundingBox(
            min_x=self.min_x + anchor.x,
            min_y=self.min_y + anchor.y,
            max_x=self.max_x + anchor.x,
            max_y=self.max_y + anchor.y,
        )


def pin_connection_from_anchor(
    anchor: Point,
    relative: Point,
    pin_length: float = DEFAULT_PIN_LENGTH_MM,
) -> Point:
    """Compatibility alias: with the corrected geometry, the connection IS
    the anchor (no extra pin-length offset). Kept for any external callers."""
    return anchor


def _rotate_then_flip_y(symbol_relative: Point, rotation_deg: float) -> Point:
    """Convert a symbol-local pin offset to a page-local offset.

    KiCad symbols use +Y up (math convention); schematic pages use +Y down.
    Placing a symbol applies a Y-flip to the symbol's coordinates. We must
    therefore:

        1. Rotate ``symbol_relative`` by ``rotation_deg`` *in symbol coords*
           (CCW about origin), then
        2. Negate the Y component to go from symbol-local to page-local.

    Rotation values are KiCad-canonical: 0, 90, 180, 270.
    """
    x, y = symbol_relative.x, symbol_relative.y
    if rotation_deg == 0.0:
        rotated_x, rotated_y = x, y
    elif rotation_deg == 90.0:
        rotated_x, rotated_y = -y, x
    elif rotation_deg == 180.0:
        rotated_x, rotated_y = -x, -y
    elif rotation_deg == 270.0:
        rotated_x, rotated_y = y, -x
    else:
        raise ValueError(
            f"Unsupported rotation {rotation_deg!r}; KiCad allows 0/90/180/270 only"
        )
    return Point(rotated_x, -rotated_y)


# UUID constants for the ephemeral preview schematic kicad-sch-api requires.
_PREVIEW_PARENT_UUID = "00000000-0000-0000-0000-000000000001"
_PREVIEW_SHEET_UUID = "00000000-0000-0000-0000-000000000002"


@dataclass
class SymbolGeometryCache:
    """Resolve pin positions + bounding boxes by querying ``kicad-sch-api``.

    Workflow::

        cache = SymbolGeometryCache()
        cache.register_libraries((Path("shared/symbols/zynq_eda.kicad_sym"),))
        pin = cache.absolute_pin_by_name("zynq_eda:FUSB302BMPX",
                                          anchor=Point(100, 100),
                                          pin_name="VBUS")
        bbox = cache.bounding_box("zynq_eda:FUSB302BMPX")

    Library registration is idempotent. Pin-position lookups create a small
    throwaway schematic that is never saved.
    """

    _loaded_library_paths: set[Path] = field(default_factory=set)
    _bbox_cache: dict[tuple[str, float], SymbolBoundingBox] = field(default_factory=dict)
    _pins_cache: dict[tuple[str, float], tuple[dict[str, object], ...]] = field(
        default_factory=dict,
    )

    def register_libraries(self, library_paths: tuple[Path, ...]) -> None:
        symbol_cache = ksa.get_symbol_cache()
        for library_path in library_paths:
            resolved_path = library_path.resolve()
            if resolved_path in self._loaded_library_paths:
                continue
            if not resolved_path.exists():
                raise FileNotFoundError(
                    f"SymbolGeometryCache: library not found: {resolved_path}"
                )
            symbol_cache.add_library_path(resolved_path)
            self._loaded_library_paths.add(resolved_path)

    # ----- private: preview-component construction --------------------------

    def _preview_component(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float,
    ):
        preview_schematic = ksa.create_schematic("_geometry_preview")
        preview_schematic.set_hierarchy_context(
            parent_uuid=_PREVIEW_PARENT_UUID,
            sheet_uuid=_PREVIEW_SHEET_UUID,
        )
        return preview_schematic.components.add(
            lib_id,
            reference="TP1",
            value="_PREVIEW",
            position=anchor.as_tuple(),
            rotation=rotation,
        )

    def _list_pin_infos(self, lib_id: str, rotation: float) -> tuple[dict[str, object], ...]:
        cache_key = (lib_id, rotation)
        cached = self._pins_cache.get(cache_key)
        if cached is not None:
            return cached
        # Pins are anchor-invariant under translation; query at origin.
        preview = self._preview_component(lib_id, Point(0.0, 0.0), rotation)
        infos = tuple(preview.list_pins())
        self._pins_cache[cache_key] = infos
        return infos

    def _resolve_pin_geometry(
        self,
        preview_component,
        pin_number: str,
    ) -> PinGeometry:
        """Return the pin's PAGE-coordinate position.

        ``kicad-sch-api``'s ``get_pin_position`` does NOT apply the Y-flip
        between symbol-local coords (+Y up, KiCad symbol editor convention)
        and schematic-page coords (+Y down). It returns
        ``component.position + symbol_relative_pin_position`` directly,
        which puts the pin on the wrong side of the symbol vertically.

        We recompute manually: use the placed component's position as the
        anchor, take the pin's symbol-relative position from ``list_pins``,
        and apply the symbol-to-page Y-flip ourselves. Rotation is currently
        passed through to kicad-sch-api (only rotation 0 confirmed affected;
        rotations 90/180/270 will be handled when the layout engine starts
        using non-zero rotations on ICs).
        """
        component_position = preview_component.position
        component_rotation = float(getattr(preview_component, "rotation", 0.0))
        pin_info = next(
            item
            for item in preview_component.list_pins()
            if item["number"] == pin_number
        )
        symbol_relative = Point(
            float(pin_info["position"].x),
            float(pin_info["position"].y),
        )
        page_relative = _rotate_then_flip_y(symbol_relative, component_rotation)
        anchor = Point(
            snap_to_grid(component_position.x + page_relative.x),
            snap_to_grid(component_position.y + page_relative.y),
        )
        return PinGeometry(
            anchor=anchor,
            connection=anchor,
            relative=symbol_relative,
        )

    # ----- public API -------------------------------------------------------

    def absolute_pin_by_name(
        self,
        lib_id: str,
        anchor: Point,
        pin_name: str,
        rotation: float = 0.0,
    ) -> Point:
        """Return the absolute wire-attachment point for the named pin.

        Pin matching tries ``pin_name`` against the symbol's pin *names* first,
        then its pin *numbers* (so callers can pass either).
        """
        preview_component = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview_component.list_pins():
            if pin_info["name"] == pin_name or pin_info["number"] == pin_name:
                return self._resolve_pin_geometry(
                    preview_component,
                    pin_info["number"],
                ).connection
        raise KeyError(
            f"Symbol {lib_id!r} has no pin named {pin_name!r}"
        )

    def pin_geometry_by_name(
        self,
        lib_id: str,
        anchor: Point,
        pin_name: str,
        rotation: float = 0.0,
    ) -> PinGeometry:
        """Full geometry (anchor + connection + relative) for the named pin."""
        preview_component = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview_component.list_pins():
            if pin_info["name"] == pin_name or pin_info["number"] == pin_name:
                return self._resolve_pin_geometry(
                    preview_component,
                    pin_info["number"],
                )
        raise KeyError(
            f"Symbol {lib_id!r} has no pin named {pin_name!r}"
        )

    def all_pins(
        self,
        lib_id: str,
        rotation: float = 0.0,
    ) -> Iterator[dict[str, object]]:
        """Yield every pin's info dict (name, number, position, ...)."""
        for pin_info in self._list_pin_infos(lib_id, rotation):
            yield pin_info

    def absolute_pin_positions(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float = 0.0,
    ) -> dict[str, Point]:
        """Return pin-number → absolute wire connection point."""
        preview_component = self._preview_component(lib_id, anchor, rotation)
        positions: dict[str, Point] = {}
        for pin_info in preview_component.list_pins():
            positions[pin_info["number"]] = self._resolve_pin_geometry(
                preview_component,
                pin_info["number"],
            ).connection
        return positions

    def bounding_box(
        self,
        lib_id: str,
        rotation: float = 0.0,
        body_padding_mm: float = DEFAULT_PIN_LENGTH_MM,
    ) -> SymbolBoundingBox:
        """Return the bounding box of a symbol relative to its anchor.

        The box spans:

            - horizontally: from ``min(pin.relative.x) - body_padding_mm``
              to ``max(pin.relative.x) + body_padding_mm``
            - vertically:   from ``min(pin.relative.y) - body_padding_mm``
              to ``max(pin.relative.y) + body_padding_mm``

        ``body_padding_mm`` accounts for the visible symbol outline that
        extends slightly beyond the pin endpoints. ``DEFAULT_PIN_LENGTH_MM``
        (1.27 mm) is a reasonable default for most ICs.
        """
        cache_key = (lib_id, rotation)
        cached = self._bbox_cache.get(cache_key)
        if cached is not None:
            return cached

        preview = self._preview_component(lib_id, Point(0.0, 0.0), rotation)
        xs: list[float] = []
        ys: list[float] = []
        for pin_info in preview.list_pins():
            position = pin_info["position"]
            xs.append(float(position.x))
            ys.append(float(position.y))

        if not xs:
            # A symbol with no pins is unusual but possible (e.g. mounting hole);
            # return a small box so downstream layout still has dimensions.
            box = SymbolBoundingBox(
                min_x=-body_padding_mm,
                min_y=-body_padding_mm,
                max_x=body_padding_mm,
                max_y=body_padding_mm,
            )
        else:
            box = SymbolBoundingBox(
                min_x=min(xs) - body_padding_mm,
                min_y=min(ys) - body_padding_mm,
                max_x=max(xs) + body_padding_mm,
                max_y=max(ys) + body_padding_mm,
            )

        self._bbox_cache[cache_key] = box
        return box
