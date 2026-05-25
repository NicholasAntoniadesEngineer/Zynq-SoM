"""Symbol pin-position resolver via kicad-sch-api.

Block builders use this to compute absolute pin coordinates for wire
routing without duplicating symbol-library geometry in Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import kicad_sch_api as ksa

from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid

DEFAULT_PIN_LENGTH_MM = KICAD_GRID_MM


@dataclass(frozen=True)
class PinGeometry:
    anchor: Point
    connection: Point
    relative: Point


def pin_connection_from_anchor(
    anchor: Point,
    relative: Point,
    pin_length: float = DEFAULT_PIN_LENGTH_MM,
) -> Point:
    """Return the schematic wire attachment point outside the symbol body."""
    if abs(relative.x) >= abs(relative.y):
        if relative.x > 0:
            return Point(snap_to_grid(anchor.x - pin_length), anchor.y)
        return Point(snap_to_grid(anchor.x + pin_length), anchor.y)
    if relative.y > 0:
        return Point(anchor.x, snap_to_grid(anchor.y - pin_length))
    return Point(anchor.x, snap_to_grid(anchor.y + pin_length))


@dataclass
class SymbolGeometryCache:
    """Registers ``.kicad_sym`` libraries once and resolves pin positions."""

    _loaded_library_paths: set[Path] = field(default_factory=set)

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

    def _preview_component(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float,
    ):
        preview_schematic = ksa.create_schematic("_pin_preview")
        preview_schematic.set_hierarchy_context(
            parent_uuid="00000000-0000-0000-0000-000000000001",
            sheet_uuid="00000000-0000-0000-0000-000000000002",
        )
        return preview_schematic.components.add(
            lib_id,
            reference="TP1",
            value="_PREVIEW",
            position=anchor.as_tuple(),
            rotation=rotation,
        )

    def _resolve_pin_geometry(
        self,
        preview_component,
        pin_number: str,
    ) -> PinGeometry:
        absolute_position = preview_component.get_pin_position(pin_number)
        anchor = Point(
            snap_to_grid(float(absolute_position.x)),
            snap_to_grid(float(absolute_position.y)),
        )
        pin_info = next(
            item
            for item in preview_component.list_pins()
            if item["number"] == pin_number
        )
        relative = Point(
            snap_to_grid(float(pin_info["position"].x)),
            snap_to_grid(float(pin_info["position"].y)),
        )
        return PinGeometry(
            anchor=anchor,
            connection=pin_connection_from_anchor(anchor, relative),
            relative=relative,
        )

    def absolute_pin_positions(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float = 0.0,
    ) -> dict[str, Point]:
        """Return pin-number -> absolute wire connection position."""
        preview_component = self._preview_component(lib_id, anchor, rotation)
        pin_positions: dict[str, Point] = {}
        for pin_info in preview_component.list_pins():
            pin_number = pin_info["number"]
            pin_positions[pin_number] = self._resolve_pin_geometry(
                preview_component,
                pin_number,
            ).connection
        return pin_positions

    def absolute_pin_by_name(
        self,
        lib_id: str,
        anchor: Point,
        pin_name: str,
        rotation: float = 0.0,
    ) -> Point:
        return self.absolute_pin_connection_by_name(
            lib_id,
            anchor,
            pin_name,
            rotation=rotation,
        )

    def absolute_pin_connection_by_name(
        self,
        lib_id: str,
        anchor: Point,
        pin_name: str,
        rotation: float = 0.0,
    ) -> Point:
        preview_component = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview_component.list_pins():
            pin_label = pin_info["name"]
            pin_number = pin_info["number"]
            if pin_label == pin_name or pin_number == pin_name:
                return self._resolve_pin_geometry(
                    preview_component,
                    pin_number,
                ).connection
        raise KeyError(
            f"Symbol {lib_id!r} has no pin named {pin_name!r} at {anchor}"
        )

    def pin_geometry_by_name(
        self,
        lib_id: str,
        anchor: Point,
        pin_name: str,
        rotation: float = 0.0,
    ) -> PinGeometry:
        preview_component = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview_component.list_pins():
            pin_label = pin_info["name"]
            pin_number = pin_info["number"]
            if pin_label == pin_name or pin_number == pin_name:
                return self._resolve_pin_geometry(preview_component, pin_number)
        raise KeyError(
            f"Symbol {lib_id!r} has no pin named {pin_name!r} at {anchor}"
        )
