"""Root-sheet builder: arranges sub-sheet symbols on an A4 carrier index.

The root sheet is the carrier's table-of-contents page. It contains one
``PlacedSheet`` per block, with one sheet pin per cross-block net the
block exposes (i.e. one pin per hierarchical label in the sub-sheet).

Cross-block nets are driven on the root sheet via power symbols, so that
ERC sees a real driver for every power/ground rail that flows between
blocks. Signal nets crossing blocks (e.g. STM32_I2C2_SDA) merge by
shared sheet-pin name across the index page — KiCad nets them
automatically through the hierarchical scope.

Layout strategy (simple grid; pagination across multiple A4 indices
lands in a follow-up if 20 blocks won't fit on a single A4):

  * Two columns. Left column: power-producing blocks (power, power_mon).
    Right column: I/O and peripheral blocks.
  * Each sheet symbol is sized for its pin count + a 30 mm minimum.
  * Pins are placed on the left or right edge based on the sub-sheet's
    hierarchical-label X position (left-edge label → left-edge sheet pin).
"""

from __future__ import annotations

from dataclasses import dataclass

from zynq_eda.core.layout._constants import (
    INTERIOR_MARGIN_MM,
    POWER_SYMBOL_LIB_IDS,
    POWER_SYMBOL_OFFSET_MM,
)
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import (
    PAPER_DIMENSIONS_MM,
    PlacedHierarchicalLabel,
    PlacedLabel,
    PlacedNoConnect,
    PlacedSheet,
    PlacedSheetPin,
    PlacedSymbol,
    PlacedWire,
    Sheet,
)


_ROOT_PAPER_SIZE = "A2"
"""Root sheet is A2 (594×420 mm). With 18 block sheet symbols arranged
3 columns × 6 rows, each row consumes ~50 mm of height (sheet body +
inter-row gap), so the column overruns A3's 297 mm height. A2 gives
420 mm headroom and keeps the index legible at print size."""

_SHEET_SYMBOL_MIN_WIDTH_MM = 50.8
_SHEET_SYMBOL_MIN_HEIGHT_MM = 38.1
_SHEET_PIN_PITCH_MM = 5.08
_SHEET_PIN_TOP_INSET_MM = 7.62  # space at the top for the sheetname/file labels
_SHEET_COLUMN_GAP_MM = 25.4
_SHEET_ROW_GAP_MM = 12.7
_ROOT_TOP_MARGIN_MM = 25.4
_ROOT_COLUMN_COUNT = 3
"""Three columns of sheet symbols across the A3 root.

A3 width (420 mm) / 3 columns ≈ 140 mm per column — comfortably wider
than the widest sheet symbol's typical 50–80 mm pin-name extent."""


@dataclass(frozen=True)
class _BlockSheetSpec:
    """One block's contribution to the root sheet (block + its sub-sheet path)."""

    block: Block
    sub_sheet: Sheet
    filename: str  # path relative to the root .kicad_sch, e.g. "sheets/power.kicad_sch"


def build_root_sheet(
    *,
    title: str,
    block_specs: list[_BlockSheetSpec],
) -> Sheet:
    """Render the root index sheet.

    Args:
        title: Title-block string (e.g. ``"Zynq SoM Carrier"``).
        block_specs: Each block with its emitted sub-sheet plus the file
            path (relative to the root .kicad_sch) where its sub-sheet
            was written.
    """
    paper_w, paper_h = PAPER_DIMENSIONS_MM[_ROOT_PAPER_SIZE]

    sheets, sheet_pin_index, spec_pins = _place_sheet_symbols(
        block_specs, paper_w=paper_w,
    )
    symbols, wires, labels, no_connects = _connect_cross_block_nets(
        block_specs, sheet_pin_index, spec_pins,
    )

    return Sheet(
        name="carrier_root",
        title=title,
        paper_size=_ROOT_PAPER_SIZE,
        symbols=tuple(symbols),
        wires=tuple(wires),
        labels=tuple(labels),
        junctions=(),
        no_connects=tuple(no_connects),
        hierarchical_labels=(),
        sheets=tuple(sheets),
        description=(
            "Carrier index: each rectangle is one functional block. "
            "Cross-block power rails are driven from this page; "
            "signal pins exposed on a single block are marked NC until "
            "more blocks land that consume them."
        ),
    )


def _place_sheet_symbols(
    block_specs: list[_BlockSheetSpec],
    *,
    paper_w: float,
) -> tuple[
    list[PlacedSheet],
    dict[tuple[str, str], Point],
    dict[str, list[PlacedSheetPin]],
]:
    """Place each block as a sheet symbol; index pin (block_name, pin_name) → page pt.

    Returns:
        ``(placed_sheets, pin_index, spec_pins)``.
        ``pin_index`` lets cross-block routers ask "where does block
        ``power``'s ``+VIN`` pin land on the page?". ``spec_pins`` maps
        ``block.name`` → its list of :class:`PlacedSheetPin`.
    """
    usable_w = paper_w - 2 * INTERIOR_MARGIN_MM
    column_pitch = usable_w / _ROOT_COLUMN_COUNT
    column_x_values = tuple(
        snap_to_grid(INTERIOR_MARGIN_MM + column_pitch * i + 10.16)
        for i in range(_ROOT_COLUMN_COUNT)
    )

    placed: list[PlacedSheet] = []
    pin_index: dict[tuple[str, str], Point] = {}
    spec_pins: dict[str, list[PlacedSheetPin]] = {}

    y_cursor = [snap_to_grid(_ROOT_TOP_MARGIN_MM)] * len(column_x_values)
    for index, spec in enumerate(block_specs):
        column = index % len(column_x_values)
        anchor_x = column_x_values[column]
        anchor_y = y_cursor[column]

        pins_by_edge = _derive_sheet_pin_layout(spec.sub_sheet)
        sheet_size = _size_for_pin_layout(pins_by_edge)
        sheet_pins = _build_sheet_pins(pins_by_edge)

        sheet = PlacedSheet(
            name=_pretty_sheet_name(spec.block),
            filename=spec.filename,
            position=Point(anchor_x, anchor_y),
            size=sheet_size,
            pins=tuple(sheet_pins),
        )
        placed.append(sheet)
        spec_pins[spec.block.name] = sheet_pins

        for sheet_pin in sheet_pins:
            pin_index[(spec.block.name, sheet_pin.name)] = _sheet_pin_page_position(
                sheet_position=sheet.position,
                sheet_size=sheet_size,
                pin=sheet_pin,
            )

        y_cursor[column] = snap_to_grid(
            anchor_y + sheet_size[1] + _SHEET_ROW_GAP_MM
        )

    return placed, pin_index, spec_pins


def _derive_sheet_pin_layout(
    sub_sheet: Sheet,
) -> dict[str, list[PlacedHierarchicalLabel]]:
    """Group a sub-sheet's hierarchical labels by sheet-symbol edge.

    A hierarchical label whose X coordinate sits in the LEFT half of the
    sub-sheet's page becomes a LEFT-edge sheet pin on the index symbol;
    RIGHT-half labels become RIGHT-edge pins. Same name appearing on
    different edges (rare) is deduped — first wins.
    """
    half = sub_sheet.paper_width_mm / 2
    by_edge: dict[str, list[PlacedHierarchicalLabel]] = {"left": [], "right": []}
    seen_names: set[str] = set()
    for hlabel in sub_sheet.hierarchical_labels:
        if hlabel.net_name in seen_names:
            continue
        seen_names.add(hlabel.net_name)
        edge = "left" if hlabel.position.x < half else "right"
        by_edge[edge].append(hlabel)
    # Stable Y order so power rails (lower Y) appear at the top of the pin column.
    for edge_labels in by_edge.values():
        edge_labels.sort(key=lambda lab: lab.position.y)
    return by_edge


def _size_for_pin_layout(
    pins_by_edge: dict[str, list[PlacedHierarchicalLabel]],
) -> tuple[float, float]:
    """Pick (w, h) large enough for the per-edge pin column + labels + sheetname."""
    max_pin_count = max(
        len(pins_by_edge.get("left", ())),
        len(pins_by_edge.get("right", ())),
        1,
    )
    pin_height = max_pin_count * _SHEET_PIN_PITCH_MM
    height = snap_to_grid(max(_SHEET_SYMBOL_MIN_HEIGHT_MM, pin_height + _SHEET_PIN_TOP_INSET_MM * 2))

    # Width: enough for the longest pin label on each side + the sheetname.
    longest_left = _longest_label_chars(pins_by_edge.get("left", ()))
    longest_right = _longest_label_chars(pins_by_edge.get("right", ()))
    char_width_mm = 1.27 * 0.6
    text_padding_mm = 5.08
    width_for_labels = (
        longest_left * char_width_mm
        + longest_right * char_width_mm
        + text_padding_mm * 2
    )
    width = snap_to_grid(max(_SHEET_SYMBOL_MIN_WIDTH_MM, width_for_labels))
    return (width, height)


def _longest_label_chars(labels: list[PlacedHierarchicalLabel]) -> int:
    return max((len(lab.net_name) for lab in labels), default=0)


def _build_sheet_pins(
    pins_by_edge: dict[str, list[PlacedHierarchicalLabel]],
) -> list[PlacedSheetPin]:
    """One :class:`PlacedSheetPin` per hierarchical label, evenly spaced down its edge."""
    sheet_pins: list[PlacedSheetPin] = []
    for edge, labels in pins_by_edge.items():
        for index, hlabel in enumerate(labels):
            sheet_pins.append(PlacedSheetPin(
                name=hlabel.net_name,
                direction=hlabel.direction,
                edge=edge,
                position_along_edge=snap_to_grid(
                    _SHEET_PIN_TOP_INSET_MM + index * _SHEET_PIN_PITCH_MM
                ),
            ))
    return sheet_pins


def _sheet_pin_page_position(
    *,
    sheet_position: Point,
    sheet_size: tuple[float, float],
    pin: PlacedSheetPin,
) -> Point:
    """Convert a sheet pin's edge + offset to an absolute page coordinate.

    Edge reference corners (from kicad-sch-api convention):
      * ``left``  : offset measured from the bottom-left corner upward.
      * ``right`` : offset measured from the top-right corner downward.
      * ``top``   : offset measured from the top-left corner rightward.
      * ``bottom``: offset measured from the bottom-left corner rightward.
    """
    width, height = sheet_size
    sx, sy = sheet_position.x, sheet_position.y
    if pin.edge == "left":
        return Point(sx, snap_to_grid(sy + height - pin.position_along_edge))
    if pin.edge == "right":
        return Point(snap_to_grid(sx + width), snap_to_grid(sy + pin.position_along_edge))
    if pin.edge == "top":
        return Point(snap_to_grid(sx + pin.position_along_edge), sy)
    return Point(snap_to_grid(sx + pin.position_along_edge), snap_to_grid(sy + height))


def _pretty_sheet_name(block: Block) -> str:
    """Friendly sheet-symbol label (visible on the root). Falls back to block.name."""
    return block.title or block.name


def _connect_cross_block_nets(
    block_specs: list[_BlockSheetSpec],
    sheet_pin_index: dict[tuple[str, str], Point],
    spec_pins: dict[str, list[PlacedSheetPin]],
) -> tuple[
    list[PlacedSymbol],
    list[PlacedWire],
    list[PlacedLabel],
    list[PlacedNoConnect],
]:
    """Attach the right terminator to every sheet pin on the root.

    KiCad considers a sheet pin "unconnected" unless something attaches
    at its exact (x, y) on the parent sheet. Strategy per sheet pin:

      * **Power net** (lib_id in :data:`POWER_SYMBOL_LIB_IDS`): drop a
        power symbol of that name directly ON the sheet pin (the
        symbol's pin sits at its origin, so coincident coordinates
        means coincident connection — no intermediate wire needed).
        Power symbols globalise their named net across the whole
        hierarchy; multiple identical power_out drivers raise
        ``pin_to_pin`` *warnings* (the standard hierarchical-power
        pattern), not errors, since the project's ERC ``pin_map``
        downgrades Power-out × Power-out to a warning.
      * **Multi-block signal net**: wire same-named pins together at
        the root and put a label on the wire (the wire's component-pin
        anchors propagate through the sub-sheets so the label has real
        electrical content and isn't "dangling"). [TODO: implemented
        in a follow-up — current rollout has no multi-block signal
        nets, so this branch is unreachable today.]
      * **Single-block signal net** (every signal pin in the current
        2-block carrier): place a ``no_connect`` marker directly on
        the sheet pin. This tells ERC the pin is intentionally
        terminated until a future block consumes it. When that block
        lands, the NC is replaced with a real wire to the new sheet
        symbol's matching pin.

    PWR_FLAG: exactly one per power-input net that has no on-board
    producer (i.e. no block declares ``power_kind="output"`` for it),
    so ERC sees a real driver for rails that enter the board from
    an external source like USB-C VBUS.
    """
    symbols: list[PlacedSymbol] = []
    wires: list[PlacedWire] = []
    labels: list[PlacedLabel] = []
    no_connects: list[PlacedNoConnect] = []

    ref_counter = {"PWR": 200, "FLG": 200}

    def _next_ref(prefix: str) -> str:
        index = ref_counter[prefix]
        ref_counter[prefix] = index + 1
        return f"{prefix}{index}"

    nets_with_producer = _nets_with_producer(block_specs)
    flagged_nets: set[str] = set()

    # Count how many blocks expose each net to inform the multi-block-
    # vs-single-block branching above.
    net_block_count: dict[str, int] = {}
    for spec in block_specs:
        seen_on_block: set[str] = set()
        for sheet_pin in spec_pins.get(spec.block.name, ()):
            if sheet_pin.name in seen_on_block:
                continue
            seen_on_block.add(sheet_pin.name)
            net_block_count[sheet_pin.name] = net_block_count.get(sheet_pin.name, 0) + 1

    for spec in block_specs:
        for sheet_pin in spec_pins.get(spec.block.name, ()):
            net_name = sheet_pin.name
            pin_pt = sheet_pin_index[(spec.block.name, sheet_pin.name)]

            lib_id = POWER_SYMBOL_LIB_IDS.get(net_name)
            if lib_id is not None:
                symbols.append(PlacedSymbol(
                    lib_id=lib_id,
                    reference=_next_ref("PWR"),
                    value=net_name,
                    position=pin_pt,
                    footprint="",
                    rotation=0.0,
                ))

                # One PWR_FLAG per power rail that lacks an on-board
                # driver: this includes both "input" nets (USB-C VBUS,
                # external supplies) and "ground" nets — power:GND has
                # a power_input pin so it doesn't drive GND, and our
                # generated power symbols all consume rather than
                # produce. Without a PWR_FLAG the rail trips
                # ``power_pin_not_driven``. Skip when a sub-sheet IC
                # declares the net as ``power_kind="output"`` (e.g. an
                # LDO produces +3V3) — that IC's power_out pin is the
                # legitimate driver and an extra PWR_FLAG would conflict.
                needs_flag = (
                    net_name not in flagged_nets
                    and net_name not in nets_with_producer
                    and _net_needs_root_driver(spec, net_name)
                )
                if needs_flag:
                    flagged_nets.add(net_name)
                    flag_pt = _outboard_point(pin_pt, sheet_pin.edge, POWER_SYMBOL_OFFSET_MM)
                    wires.append(PlacedWire(start=pin_pt, end=flag_pt))
                    symbols.append(PlacedSymbol(
                        lib_id="power:PWR_FLAG",
                        reference=_next_ref("FLG"),
                        value=net_name,
                        position=flag_pt,
                        footprint="",
                        rotation=0.0,
                    ))
                continue

            # Signal pin terminating in NC for now (single-block exposure).
            # Multi-block signal nets need cross-block wires + labels;
            # that path lands in a follow-up when the carrier has more
            # blocks than just power + usb_pd.
            no_connects.append(PlacedNoConnect(position=pin_pt))

    return symbols, wires, labels, no_connects

    return symbols, wires, labels


def _is_power_input_net(spec: _BlockSheetSpec, net_name: str) -> bool:
    """True iff *net_name* is declared as ``power_kind="input"`` on this block."""
    for net in spec.block.external_nets:
        if net.name == net_name and net.power_kind == "input":
            return True
    return False


def _net_needs_root_driver(spec: _BlockSheetSpec, net_name: str) -> bool:
    """True iff *net_name* is a power rail consumed but not produced anywhere.

    Covers ``input`` (LDO inputs / external rails entering the board) and
    ``ground`` (every GND-family rail — chassis GND, signal GND). Either
    requires a PWR_FLAG to satisfy KiCad's ``power_pin_not_driven`` check
    when no on-board producer exists.
    """
    for net in spec.block.external_nets:
        if net.name == net_name and net.power_kind in ("input", "ground"):
            return True
    return False


def _nets_with_producer(block_specs: list[_BlockSheetSpec]) -> set[str]:
    """Return the set of net names that any block declares as ``power_kind="output"``.

    Used by the root-sheet driver pass to decide which nets *need* a
    synthesised PWR_FLAG (the ones with no on-board producer) and which
    are already driven by an LDO / regulator on a sub-sheet (no flag
    needed; adding one would cause Power-out × Power-out conflicts).
    """
    return {
        net.name
        for spec in block_specs
        for net in spec.block.external_nets
        if net.power_kind == "output"
    }


def _outboard_point(point: Point, edge: str, distance_mm: float) -> Point:
    """Return a point ``distance_mm`` outboard of ``point`` along ``edge``."""
    if edge == "left":
        return Point(snap_to_grid(point.x - distance_mm), point.y)
    if edge == "right":
        return Point(snap_to_grid(point.x + distance_mm), point.y)
    if edge == "top":
        return Point(point.x, snap_to_grid(point.y - distance_mm))
    return Point(point.x, snap_to_grid(point.y + distance_mm))


