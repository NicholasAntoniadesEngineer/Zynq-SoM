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
        pin_rotation: The pin's intrinsic rotation in the KiCad symbol library
            (0/90/180/270 degrees). Per KiCad convention, this rotation
            indicates the direction from the pin's wire-end (tip) INTO the
            symbol body — so a pin with rotation=0 sits on the LEFT edge of
            the body (tip on the left, body extends to the right).
        symbol_rotation: The placement rotation of the parent symbol on the
            schematic page (0/90/180/270 degrees). Combined with
            ``pin_rotation`` and the symbol-to-page Y-flip, this determines
            the page-side a pin sits on.
    """

    anchor: Point
    connection: Point
    relative: Point
    pin_rotation: float = 0.0
    symbol_rotation: float = 0.0


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


def _flip_y_then_rotate(symbol_relative: Point, rotation_deg: float) -> Point:
    """Convert a symbol-local pin offset to a page-local offset.

    KiCad symbols use +Y up (math convention); schematic pages use +Y down.
    The placement transform is (verified empirically against the
    netlist KiCad produces from ``connect_pins_with_wire`` + power symbols):

        1. Y-flip in symbol coords: (x, y) → (x, -y)
        2. Rotate by ``rotation_deg`` *clockwise* in page coords:
             90  CW: (x, y) → (y, -x)
             180:    (x, y) → (-x, -y)
             270 CW: (x, y) → (-y, x)

    The CW direction matches what you see in the schematic editor (where
    +Y is down) when you press R to rotate. Counterintuitively, this is
    different from what ``kicad-sch-api.get_pin_position()`` returns —
    that API has its own bug where it returns symbol-frame coords without
    the flip.

    Rotation values are KiCad-canonical: 0, 90, 180, 270.
    """
    flipped_x = symbol_relative.x
    flipped_y = -symbol_relative.y
    if rotation_deg == 0.0:
        rotated_x, rotated_y = flipped_x, flipped_y
    elif rotation_deg == 90.0:
        rotated_x, rotated_y = flipped_y, -flipped_x
    elif rotation_deg == 180.0:
        rotated_x, rotated_y = -flipped_x, -flipped_y
    elif rotation_deg == 270.0:
        rotated_x, rotated_y = -flipped_y, flipped_x
    else:
        raise ValueError(
            f"Unsupported rotation {rotation_deg!r}; KiCad allows 0/90/180/270 only"
        )
    return Point(rotated_x, rotated_y)


# Backward-compatible alias kept for any external imports.
_rotate_then_flip_y = _flip_y_then_rotate


def _pin_rotation_from_symbol(lib_id: str, pin_number: str) -> float:
    """Look up a pin's library-defined rotation (0/90/180/270)."""
    symbol_def = ksa.get_symbol_cache().get_symbol(lib_id)
    if symbol_def is None:
        return 0.0
    for pin in symbol_def.pins:
        if pin.number == pin_number:
            return float(pin.rotation)
    return 0.0


def page_side_from_pin(
    pin_rotation: float,
    symbol_rotation: float = 0.0,
) -> str:
    """Determine which page-edge (left/right/top/bottom) a pin sits on.

    KiCad pin convention: ``pin.rotation`` indicates the direction from the
    pin's tip (electrical endpoint) INTO the symbol body. So:

        rotation   0 → body to the +X of tip → pin on LEFT edge of body
        rotation  90 → body to the +Y of tip → pin on BOTTOM edge of body
                       (in symbol coords where +Y is up; "bottom" means
                       smallest symbol-y; after Y-flip the pin still sits
                       at the body's bottom edge in PAGE coords since
                       smallest-symbol-y maps to largest-page-y, and on
                       the page +y is down → "bottom" visually).
        rotation 180 → body to the -X of tip → pin on RIGHT edge of body
        rotation 270 → body to the -Y of tip → pin on TOP edge of body

    The Y-flip just changes the SIGN of pin y-coordinates; it does NOT
    change which physical body edge a pin sits on. A pin at the "top"
    of the body in symbol frame (largest symbol-y) is still at the
    "top" of the body visually on the page (smallest page-y, i.e. above
    the anchor).

    If the placed symbol has its own rotation (0/90/180/270), the resulting
    page side rotates by that many CW quarter-turns on the page.

    Returns the page-relative side: ``"left"``, ``"right"``, ``"top"``,
    ``"bottom"``.
    """
    # Step 1: pin rotation → which body edge the pin sits on. The Y-flip
    # preserves edge identity (a top-edge pin is still a top-edge pin on
    # the page; the y SIGN flips but the body's edges keep their labels).
    pin_rotation_canonical = float(pin_rotation) % 360.0
    page_side_before_symrot = {
        0.0:   "left",    # pin tip on left edge, body to the right
        90.0:  "bottom",  # pin tip below body, body above
        180.0: "right",   # pin tip on right edge, body to the left
        270.0: "top",     # pin tip above body, body below
    }.get(pin_rotation_canonical, "left")

    # Step 2: rotate by symbol_rotation clockwise on the page.
    # A pin on "left" rotated 90° CW ends up on "top"; another 90° CW → "right"; etc.
    symbol_rotation_canonical = float(symbol_rotation) % 360.0
    cw_rotations = int(symbol_rotation_canonical // 90) % 4
    rotation_table = ["left", "top", "right", "bottom"]
    start_index = rotation_table.index(page_side_before_symrot)
    final_side = rotation_table[(start_index + cw_rotations) % 4]
    return final_side


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
    _bbox_cache: dict[tuple[str, float, bool], SymbolBoundingBox] = field(default_factory=dict)
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

        The pin's own ``rotation`` (the direction the pin's tip-to-body
        stub extends in the KiCad symbol library) is also recovered from
        the underlying ``SchematicPin`` so callers can determine the
        page-side a pin sits on without resorting to position-axis
        heuristics. For ICs with densely-packed pins on a single edge
        (e.g. FUSB302's 7 left-column pins spanning ±7.62 mm in y), the
        axis-dominance heuristic mis-classifies the corner pins as top/
        bottom, which collapses unrelated nets onto the same coordinate.
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
        page_relative = _flip_y_then_rotate(symbol_relative, component_rotation)
        anchor = Point(
            snap_to_grid(component_position.x + page_relative.x),
            snap_to_grid(component_position.y + page_relative.y),
        )
        # Recover the pin's own (library-level) rotation. ``list_pins`` flattens
        # SchematicPin fields into a dict but currently omits ``rotation``,
        # so we read it directly from the cached SymbolDefinition.
        pin_rotation = _pin_rotation_from_symbol(
            preview_component.lib_id,
            pin_number,
        )
        return PinGeometry(
            anchor=anchor,
            connection=anchor,
            relative=symbol_relative,
            pin_rotation=pin_rotation,
            symbol_rotation=component_rotation,
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
        tight_body: bool = True,
    ) -> SymbolBoundingBox:
        """Return the bounding box of a symbol relative to its anchor.

        Two modes:

          * ``tight_body=True`` (default — used by the overlap validator
            and by occupancy-aware placement). Returns the VISIBLE body
            box: the convex hull of pin body-side endpoints (= pin tips
            walked INWARD by one pin length toward the body centroid).
            Pin stubs themselves are NOT included, so wires terminating
            at a pin tip don't read as "wire crosses the body".
          * ``tight_body=False`` (legacy). Returns the OUTER hull: pin
            tips PLUS ``body_padding_mm``. Useful for placement spacing
            calculations where the pin stubs must clear the next
            symbol's stubs too.

        The default flipped from the legacy outer hull to the visible
        body in Wave B because the outer hull caused ~700 false-positive
        overlap warnings (every wire that legitimately terminated on a
        pin was reported as wire×symbol; every label at a wire endpoint
        was reported as label×symbol). The visible body matches what
        the user actually sees on the page.
        """
        cache_key = (lib_id, rotation, tight_body)
        cached = self._bbox_cache.get(cache_key)
        if cached is not None:
            return cached

        preview = self._preview_component(lib_id, Point(0.0, 0.0), rotation)
        # Collect pin tips. ``list_pins()`` returns positions in the symbol's
        # LIBRARY frame (no rotation), with +Y up. The same flip-Y-then-rotate
        # transform used in :meth:`_resolve_pin_geometry` converts these to
        # PAGE-relative coords (relative to the symbol anchor at the origin).
        pin_tips: list[Point] = []
        for pin_info in preview.list_pins():
            position = pin_info["position"]
            symbol_relative = Point(float(position.x), float(position.y))
            page_relative = _flip_y_then_rotate(symbol_relative, rotation)
            pin_tips.append(page_relative)

        if not pin_tips:
            # A symbol with no pins is unusual but possible (e.g. mounting hole);
            # return a small box so downstream layout still has dimensions.
            box = SymbolBoundingBox(
                min_x=-body_padding_mm,
                min_y=-body_padding_mm,
                max_x=body_padding_mm,
                max_y=body_padding_mm,
            )
        elif tight_body:
            # Tight body: walk each pin tip INWARD by one pin length
            # (toward the centroid of all pin tips). The result is a
            # box around the visible symbol outline, with pin stubs
            # excluded. We use the bbox of pin tips as a stand-in for
            # the centroid because that gives a consistent inset on
            # all four sides for rectangular pin arrangements.
            min_x = min(p.x for p in pin_tips)
            max_x = max(p.x for p in pin_tips)
            min_y = min(p.y for p in pin_tips)
            max_y = max(p.y for p in pin_tips)
            inset = DEFAULT_PIN_LENGTH_MM
            # Only inset on axes where the bbox span is wider than 2*inset
            # — for short symbols (e.g. a 2-pin passive 2.54mm tall) we
            # can't safely inset on the long axis without collapsing.
            x_inset = inset if (max_x - min_x) > 2.0 * inset else 0.0
            y_inset = inset if (max_y - min_y) > 2.0 * inset else 0.0
            box_min_x = min_x + x_inset
            box_min_y = min_y + y_inset
            box_max_x = max_x - x_inset
            box_max_y = max_y - y_inset
            # Ensure a minimum BODY extent (~1 mm) on each axis so that
            # 2-pin passives (Device:R / Device:C) whose pin tips lie
            # on a single line still register a non-zero body in the
            # transverse direction. Without this minimum, the tight
            # bbox collapses to a line and the body becomes invisible
            # to the overlap validator — wires passing PERPENDICULAR
            # through a passive's body get a false "no overlap"
            # because the bbox has zero width.
            MIN_BODY_HALF_EXTENT_MM = 0.635
            if (box_max_x - box_min_x) < 2.0 * MIN_BODY_HALF_EXTENT_MM:
                center_x = (box_min_x + box_max_x) / 2.0
                box_min_x = center_x - MIN_BODY_HALF_EXTENT_MM
                box_max_x = center_x + MIN_BODY_HALF_EXTENT_MM
            if (box_max_y - box_min_y) < 2.0 * MIN_BODY_HALF_EXTENT_MM:
                center_y = (box_min_y + box_max_y) / 2.0
                box_min_y = center_y - MIN_BODY_HALF_EXTENT_MM
                box_max_y = center_y + MIN_BODY_HALF_EXTENT_MM
            box = SymbolBoundingBox(
                min_x=box_min_x,
                min_y=box_min_y,
                max_x=box_max_x,
                max_y=box_max_y,
            )
        else:
            min_x = min(p.x for p in pin_tips)
            max_x = max(p.x for p in pin_tips)
            min_y = min(p.y for p in pin_tips)
            max_y = max(p.y for p in pin_tips)
            box = SymbolBoundingBox(
                min_x=min_x - body_padding_mm,
                min_y=min_y - body_padding_mm,
                max_x=max_x + body_padding_mm,
                max_y=max_y + body_padding_mm,
            )

        self._bbox_cache[cache_key] = box
        return box
