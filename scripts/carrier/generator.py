"""Carrier schematic generator (zone-based, multi-instance, fail-hard).

Produces ``carrier_template.kicad_sch`` containing every IC instance on the
carrier board, each with its own dedicated rectangular zone, every
datasheet-required external part placed inside the zone via a non-colliding
free-space scan, and every SoM-connector pin labelled with its carrier-side
net name (per ``io_assignment.csv``).

Design rules (no shortcuts):
    1. Every IC instance from ``IC_INSTANCES`` (matching ``IC_INSTANCE_COUNT``)
       gets placed - no skip-on-missing-symbol.
    2. Every wire is grid-aligned and orthogonal (Rule J1, J2 strict).
    3. No wires share both endpoints (Rule J3 strict).
    4. Every T-intersection has a junction (Rule J4 strict).
    5. No wire passes through any placed component (Rule J5 strict).
    6. Hierarchical-label round-trip enforced (Rule J6 strict).
    7. SoM connector pins are labelled per ``io_assignment.csv``.

Run with:
    python scripts/create_carrier_template_schematic.py
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from scripts.carrier.core.geometry import BoundingBox
from scripts.carrier.core.layout import (
    IC_BODY_INSET_MM,
    IcZone,
    SECTION_LAYOUT,
    compute_zones,
)
from scripts.carrier.core.refcircuit import ExternalPart, ReferenceCircuit
from scripts.carrier.core.registry import REGISTRY
from scripts.carrier.core.sexpr import (
    GRID_TOLERANCE_MM,
    KICAD_GRID_MM,
    Point,
    SExp,
    global_label,
    junction,
    local_label,
    make_uuid,
    property_,
    snap_to_grid,
    text_label,
    wire,
)
from scripts.carrier.core.symbols import (
    PlacedSymbol,
    SymbolDef,
    SYMBOL_LIBRARY,
)
from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.rules import Validator
from scripts.carrier.sheet_emitter import (
    build_lib_symbol_sexp,
    build_symbol_instance_sexp,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER_DIR = REPO_ROOT / "scripts" / "carrier_template"
SCH_PATH = CARRIER_DIR / "carrier_template.kicad_sch"
PROJECT_PATH = CARRIER_DIR / "carrier_template.kicad_pro"
SYMBOL_LIB_PATH = CARRIER_DIR / "symbol_Zynq_SoM.kicad_sym"
VALIDATION_REPORT_PATH = CARRIER_DIR / "validation_report.md"
IO_ASSIGNMENT_PATH = CARRIER_DIR / "io_assignment.csv"

PAPER_SIZE: str = "A1"
PROJECT_NAME: str = "carrier_template"
SCHEMATIC_FORMAT_VERSION: int = 20250114
SCHEMATIC_GENERATOR_NAME: str = "eeschema"
SCHEMATIC_GENERATOR_VERSION: str = "9.0"
KICAD_PROPERTY_FONT_MM: float = 1.27
JUNCTION_DOT_DIAMETER_MM: float = 0.0

SOM_CONNECTOR_NAMES: tuple[str, ...] = ("J1", "J2", "J3")


_REF_PREFIX_BY_FOOTPRINT_BUCKET: dict[str, str] = {
    "Capacitor_SMD:": "C",
    "Resistor_SMD:": "R",
    "Inductor_SMD:": "L",
    "LED_SMD:": "D",
    "Diode_SMD:": "D",
}


# ---------------------------------------------------------------------------
# Schematic-construction container
# ---------------------------------------------------------------------------


@dataclass
class SchematicBuild:
    """Accumulates all schematic objects emitted during generation."""

    placed_symbols: list[PlacedSymbol]
    geometry_objects: list[SExp]
    decorative_objects: list[SExp]
    label_objects: list[SExp]
    used_lib_ids: set[str]

    @classmethod
    def empty(cls) -> "SchematicBuild":
        return cls(
            placed_symbols=[],
            geometry_objects=[],
            decorative_objects=[],
            label_objects=[],
            used_lib_ids=set(),
        )


# ---------------------------------------------------------------------------
# Embedded SoM connector library access
# ---------------------------------------------------------------------------


def _read_existing_symbol_lib() -> str:
    """Read the J1/J2/J3 connector symbol definitions from the original lib."""
    if not SYMBOL_LIB_PATH.exists():
        raise FileNotFoundError(
            f"Missing {SYMBOL_LIB_PATH}; run scripts/symbol_creation.bash first"
        )
    return SYMBOL_LIB_PATH.read_text(encoding="utf-8")


def _extract_named_symbol(lib_text: str, symbol_name: str) -> str:
    """Extract one ``(symbol "name" ...)`` block from the lib text."""
    pattern = re.compile(r'\(symbol\s+"' + re.escape(symbol_name) + r'"')
    match = pattern.search(lib_text)
    if not match:
        raise KeyError(f"Symbol {symbol_name!r} not in lib")
    start_index = match.start()
    paren_depth = 0
    in_string = False
    for char_index in range(start_index, len(lib_text)):
        current_char = lib_text[char_index]
        if current_char == '"' and lib_text[char_index - 1] != "\\":
            in_string = not in_string
        elif not in_string:
            if current_char == "(":
                paren_depth += 1
            elif current_char == ")":
                paren_depth -= 1
                if paren_depth == 0:
                    return lib_text[start_index:char_index + 1]
    raise ValueError(f"Unbalanced parens while extracting symbol {symbol_name!r}")


def _rename_symbol(body_text: str, original_name: str, qualified_name: str) -> str:
    return body_text.replace(
        f'(symbol "{original_name}"',
        f'(symbol "{qualified_name}"',
        1,
    )


@dataclass(frozen=True)
class SomLibrarySymbol:
    """A J1 / J2 / J3 connector symbol parsed from the existing kicad_sym."""

    qualified_name: str
    body_text: str
    pin_records: tuple[tuple[str, Point, float], ...]


def _extract_pin_records(body_text: str) -> tuple[tuple[str, Point, float], ...]:
    """Parse ``(pin <type> <shape> (at x y angle) ... (number "N") ...)`` blocks.

    Returns a tuple of (pin_number, position_in_symbol_local_space, angle).
    """
    records: list[tuple[str, Point, float]] = []
    pattern = re.compile(
        r'\(pin\s+\S+\s+\S+\s+\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s*\)'
        r'(?:.*?)\(number\s+"([^"]+)"',
        re.DOTALL,
    )
    for match in pattern.finditer(body_text):
        pin_x = float(match.group(1))
        pin_y = float(match.group(2))
        pin_angle = float(match.group(3))
        pin_number = match.group(4)
        records.append((pin_number, Point(pin_x, pin_y), pin_angle))
    if not records:
        raise ValueError("_extract_pin_records: no pins found in symbol body")
    return tuple(records)


def _load_som_library() -> tuple[SomLibrarySymbol, ...]:
    """Parse J1/J2/J3 from the existing symbol library file."""
    library_text = _read_existing_symbol_lib()
    parsed: list[SomLibrarySymbol] = []
    for connector_name in SOM_CONNECTOR_NAMES:
        original_symbol_name = f"Zynq_SoM_{connector_name}"
        qualified_name = f"Zynq_SoM:{original_symbol_name}"
        body = _extract_named_symbol(library_text, original_symbol_name)
        renamed = _rename_symbol(body, original_symbol_name, qualified_name)
        pin_records = _extract_pin_records(body)
        parsed.append(SomLibrarySymbol(
            qualified_name=qualified_name,
            body_text=renamed,
            pin_records=pin_records,
        ))
    return tuple(parsed)


# ---------------------------------------------------------------------------
# IO assignment loading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IoAssignmentRow:
    som_connector: str
    som_pin: str
    som_net: str
    side: str
    destination: str
    carrier_signal: str
    interface: str
    notes: str
    shared: bool


def _load_io_assignment() -> tuple[IoAssignmentRow, ...]:
    if not IO_ASSIGNMENT_PATH.exists():
        raise FileNotFoundError(
            f"Missing {IO_ASSIGNMENT_PATH}; run bom_io.emit_io_assignment_csv first"
        )
    rows: list[IoAssignmentRow] = []
    with open(IO_ASSIGNMENT_PATH, encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append(IoAssignmentRow(
                som_connector=row["som_connector"],
                som_pin=row["som_pin"],
                som_net=row["som_net"],
                side=row["side"],
                destination=row["destination"],
                carrier_signal=row["carrier_signal"],
                interface=row["interface"],
                notes=row.get("notes", ""),
                shared=(row.get("shared", "false").lower() == "true"),
            ))
    return tuple(rows)


# ---------------------------------------------------------------------------
# Reference designator counter
# ---------------------------------------------------------------------------


_external_ref_counter: Counter[str] = Counter()


def _reset_external_refs() -> None:
    _external_ref_counter.clear()


def _ref_prefix_for(footprint: str) -> str:
    for footprint_bucket, prefix in _REF_PREFIX_BY_FOOTPRINT_BUCKET.items():
        if footprint.startswith(footprint_bucket):
            return prefix
    raise ValueError(
        f"_ref_prefix_for: no reference designator prefix mapped for footprint "
        f"{footprint!r}"
    )


def _allocate_external_reference(footprint: str) -> str:
    prefix = _ref_prefix_for(footprint)
    _external_ref_counter[prefix] += 1
    return f"{prefix}{_external_ref_counter[prefix]:03d}"


def _generic_symbol_for(footprint: str) -> SymbolDef:
    if footprint.startswith("Capacitor_SMD:"):
        return SYMBOL_LIBRARY["C"]
    if footprint.startswith("Resistor_SMD:"):
        return SYMBOL_LIBRARY["R"]
    if footprint.startswith("Inductor_SMD:"):
        return SYMBOL_LIBRARY["L"]
    if footprint.startswith("LED_SMD:"):
        return SYMBOL_LIBRARY["LED"]
    if footprint.startswith("Diode_SMD:"):
        return SYMBOL_LIBRARY["D_Schottky"]
    raise ValueError(
        f"_generic_symbol_for: no generic symbol for footprint {footprint!r}"
    )


# ---------------------------------------------------------------------------
# IC + external placement (zone-based, free-space packing)
# ---------------------------------------------------------------------------


def _resolve_ic_symbol(circuit: ReferenceCircuit) -> SymbolDef:
    candidate = (
        SYMBOL_LIBRARY.get(circuit.part_mpn)
        or SYMBOL_LIBRARY.get(circuit.symbol_token)
    )
    if candidate is None:
        raise KeyError(
            f"_resolve_ic_symbol: no SYMBOL_LIBRARY entry for refcircuit "
            f"{circuit.part_mpn!r} (symbol_token={circuit.symbol_token!r})"
        )
    return candidate


def _place_ic_in_zone(zone: IcZone, symbol_def: SymbolDef,
                      reference: str, value: str, footprint: str) -> PlacedSymbol:
    ic_origin = Point(
        snap_to_grid(zone.origin.x + IC_BODY_INSET_MM),
        snap_to_grid(zone.origin.y + IC_BODY_INSET_MM + symbol_def.height_mm() / 2),
    )
    return PlacedSymbol(
        reference=reference,
        symbol=symbol_def,
        value=value,
        footprint=footprint,
        origin=ic_origin,
    )


def _free_space_scan(
    target_box: BoundingBox,
    zone: IcZone,
    obstacles: list[BoundingBox],
    step_mm: float = KICAD_GRID_MM,
) -> Point | None:
    """Find a grid-aligned offset that places ``target_box`` inside ``zone``
    without overlapping any obstacle. Returns the offset to apply to
    ``target_box`` origin; None if no slot exists.

    Scans column-major, top-to-bottom within the zone interior, starting
    from the top-left.
    """
    target_width_mm = target_box.bottom_right.x - target_box.top_left.x
    target_height_mm = target_box.bottom_right.y - target_box.top_left.y
    scan_origin_x = snap_to_grid(zone.origin.x + ZONE_INNER_MARGIN_MM)
    scan_origin_y = snap_to_grid(zone.origin.y + ZONE_INNER_MARGIN_MM)
    scan_max_x = snap_to_grid(
        zone.origin.x + zone.width_mm - ZONE_INNER_MARGIN_MM - target_width_mm
    )
    scan_max_y = snap_to_grid(
        zone.origin.y + zone.height_mm - ZONE_INNER_MARGIN_MM - target_height_mm
    )
    candidate_x = scan_origin_x
    while candidate_x <= scan_max_x + GRID_TOLERANCE_MM:
        candidate_y = scan_origin_y
        while candidate_y <= scan_max_y + GRID_TOLERANCE_MM:
            candidate_box = BoundingBox(
                top_left=Point(candidate_x, candidate_y),
                bottom_right=Point(
                    candidate_x + target_width_mm,
                    candidate_y + target_height_mm,
                ),
            )
            if not any(_boxes_overlap(candidate_box, obstacle) for obstacle in obstacles):
                return Point(
                    candidate_x - target_box.top_left.x,
                    candidate_y - target_box.top_left.y,
                )
            candidate_y += step_mm
        candidate_x += step_mm
    return None


ZONE_INNER_MARGIN_MM: float = KICAD_GRID_MM


def _ic_has_pin(ic_symbol: PlacedSymbol, name_or_number: str) -> bool:
    return any(
        pin.number == name_or_number or pin.name == name_or_number
        for pin in ic_symbol.symbol.pins
    )


def _ic_pin_net_name(ic_reference: str, pin_name: str) -> str:
    """Synthesise a unique label-friendly net name for an IC pin."""
    sanitised = (pin_name
        .replace(" ", "_")
        .replace("/", "_")
        .replace("+", "P")
        .replace("-", "N"))
    return f"NET_{ic_reference}_{sanitised}"


def _pack_external_in_zone(
    ic_symbol: PlacedSymbol,
    external: ExternalPart,
    ext_symbol_def: SymbolDef,
    ext_reference: str,
    ext_value: str,
    ext_footprint: str,
    zone: IcZone,
    obstacles: list[BoundingBox],
) -> tuple[PlacedSymbol, list[SExp]]:
    """Place an external part anywhere free in the zone and emit two labels.

    Connectivity is by net label (no in-zone wire routing). The
    IC-facing pin (pin 1) is labelled with the synthesised IC pin net
    name (``_ic_pin_net_name``); the outer pin (pin 2) is labelled with
    ``external.to_net``. The IC pin itself is labelled separately by
    ``_place_zone`` so all three points share the same net.

    For "virtual node" externals (``from_pin`` not an IC pin), the
    label is taken verbatim from ``from_pin`` instead of being
    synthesised. This is how the Bob Smith common cap on HX5008NLT
    connects to the BS_COMMON node fed by the four 75R resistors.
    """
    target_local_box = ext_symbol_def.bounding_box
    placement_offset = _free_space_scan(
        target_box=target_local_box,
        zone=zone,
        obstacles=obstacles,
    )
    if placement_offset is None:
        raise RuntimeError(
            f"_pack_external_in_zone: no free space in zone "
            f"({zone.bounding_box.top_left.x:.2f},"
            f"{zone.bounding_box.top_left.y:.2f})-"
            f"({zone.bounding_box.bottom_right.x:.2f},"
            f"{zone.bounding_box.bottom_right.y:.2f}) for {ext_reference} "
            f"({ic_symbol.reference}.{external.from_pin} -> "
            f"{external.to_net}); enlarge the section in SECTION_LAYOUT"
        )
    ext_origin = Point(
        snap_to_grid(placement_offset.x),
        snap_to_grid(placement_offset.y),
    )
    ext_symbol = PlacedSymbol(
        reference=ext_reference,
        symbol=ext_symbol_def,
        value=ext_value,
        footprint=ext_footprint,
        origin=ext_origin,
    )

    if _ic_has_pin(ic_symbol, external.from_pin):
        source_label = _ic_pin_net_name(ic_symbol.reference, external.from_pin)
    else:
        source_label = external.from_pin

    schematic_objects: list[SExp] = [
        _label_for_net(source_label, ext_symbol.pin_position("1")),
        _label_for_net(external.to_net, ext_symbol.pin_position("2")),
    ]
    return ext_symbol, schematic_objects


def _label_for_net(net_name: str, position: Point) -> SExp:
    if not net_name:
        raise ValueError("_label_for_net: net_name must be non-empty")
    if net_name.upper() == "GND" or net_name.startswith("+") or net_name.startswith("CHASSIS"):
        return global_label(net_name, position)
    return local_label(net_name, position)


def _boxes_overlap(box_a: BoundingBox, box_b: BoundingBox) -> bool:
    if box_a.bottom_right.x <= box_b.top_left.x:
        return False
    if box_a.top_left.x >= box_b.bottom_right.x:
        return False
    if box_a.bottom_right.y <= box_b.top_left.y:
        return False
    if box_a.top_left.y >= box_b.bottom_right.y:
        return False
    return True


def _place_zone(
    zone: IcZone,
    validator: Validator,
) -> tuple[list[PlacedSymbol], list[SExp], list[tuple[str, str]]]:
    """Place an IC + all its externals in its dedicated zone.

    Returns:
        (placed_symbols, schematic_objects, externals_for_validation)
    """
    instance = zone.instance
    circuit = REFCIRCUITS.get(instance.ic_name)
    if circuit is None:
        raise KeyError(
            f"_place_zone: no REFCIRCUITS entry for {instance.ic_name!r} "
            f"(reference {instance.reference!r})"
        )
    ic_symbol_def = _resolve_ic_symbol(circuit)
    ic_symbol = _place_ic_in_zone(
        zone=zone,
        symbol_def=ic_symbol_def,
        reference=instance.reference,
        value=circuit.part_mpn,
        footprint=circuit.footprint,
    )
    placed_symbols: list[PlacedSymbol] = [ic_symbol]
    schematic_objects: list[SExp] = []
    externals_for_validation: list[tuple[str, str]] = []
    obstacles_in_zone: list[BoundingBox] = [ic_symbol.bounding_box]

    validator.check_reference_uniqueness(instance.reference, instance.section)
    validator.check_uuid_unique(
        ic_symbol.uuid, f"{instance.section}:{instance.reference}",
    )

    ic_pin_labels_emitted: set[str] = set()

    for external in circuit.external_parts:
        for _ in range(external.quantity):
            ext_part = REGISTRY.get(external.part_token)
            if ext_part is None:
                raise KeyError(
                    f"_place_zone: ExternalPart token {external.part_token!r} "
                    f"on {instance.reference}.{external.from_pin} not in BOM "
                    f"REGISTRY"
                )
            ext_reference = _allocate_external_reference(ext_part.footprint)
            ext_symbol_def = _generic_symbol_for(ext_part.footprint)
            ext_symbol, ext_schematic_objects = _pack_external_in_zone(
                ic_symbol=ic_symbol,
                external=external,
                ext_symbol_def=ext_symbol_def,
                ext_reference=ext_reference,
                ext_value=ext_part.value,
                ext_footprint=ext_part.footprint,
                zone=zone,
                obstacles=obstacles_in_zone,
            )
            placed_symbols.append(ext_symbol)
            schematic_objects.extend(ext_schematic_objects)
            obstacles_in_zone.append(ext_symbol.bounding_box)
            externals_for_validation.append((external.from_pin, external.part_token))
            validator.check_uuid_unique(
                ext_symbol.uuid, f"{instance.section}:{ext_symbol.reference}",
            )
            validator.check_reference_uniqueness(
                ext_symbol.reference, instance.section,
            )

            if (
                _ic_has_pin(ic_symbol, external.from_pin)
                and external.from_pin not in ic_pin_labels_emitted
            ):
                pin_label_position = ic_symbol.pin_position(external.from_pin)
                pin_net_name = _ic_pin_net_name(
                    ic_symbol.reference, external.from_pin,
                )
                schematic_objects.append(
                    _label_for_net(pin_net_name, pin_label_position),
                )
                ic_pin_labels_emitted.add(external.from_pin)

    validator.check_refcircuit_conformance(
        instance.reference, circuit, externals_for_validation,
    )
    return placed_symbols, schematic_objects, externals_for_validation


# ---------------------------------------------------------------------------
# SoM connector placement and pin labelling
# ---------------------------------------------------------------------------


SOM_CONNECTOR_FOOTPRINT: str = "fp:HRS_DF40C-100DP-0.4V_51_"
SOM_CONNECTOR_DESCRIPTION: str = "Zynq SoM mating connector (100 pin)"


def _place_som_connectors(
    som_library: tuple[SomLibrarySymbol, ...],
    schematic_uuid: str,
    project_name: str,
    io_assignment: tuple[IoAssignmentRow, ...],
    validator: Validator,
) -> tuple[list[SExp], list[SExp]]:
    """Emit the J1/J2/J3 connector instances and one global label per pin.

    Returns:
        (instance_sexps, label_sexps)
    """
    io_lookup: dict[tuple[str, str], IoAssignmentRow] = {
        (row.som_connector, row.som_pin): row for row in io_assignment
    }

    instance_sexps: list[SExp] = []
    label_sexps: list[SExp] = []
    for connector_name, som_symbol in zip(SOM_CONNECTOR_NAMES, som_library):
        section_spec = SECTION_LAYOUT[f"som_{connector_name.lower()}"]
        placement_x = snap_to_grid(section_spec.origin.x + IC_BODY_INSET_MM)
        placement_y = snap_to_grid(section_spec.origin.y + IC_BODY_INSET_MM)
        connector_uuid = make_uuid()
        validator.check_uuid_unique(
            connector_uuid, f"carrier_template:{connector_name}",
        )
        validator.check_reference_uniqueness(connector_name, "carrier_template")

        instance_sexps.append(_build_som_instance_sexp(
            qualified_name=som_symbol.qualified_name,
            connector_name=connector_name,
            placement=Point(placement_x, placement_y),
            connector_uuid=connector_uuid,
            schematic_uuid=schematic_uuid,
            project_name=project_name,
            pin_records=som_symbol.pin_records,
        ))

        for pin_number, pin_local_position, _ in som_symbol.pin_records:
            io_row = io_lookup.get((connector_name, pin_number))
            if io_row is None:
                raise KeyError(
                    f"_place_som_connectors: no io_assignment row for "
                    f"{connector_name}.{pin_number}; regenerate "
                    f"io_assignment.csv"
                )
            label_position = Point(
                snap_to_grid(placement_x + pin_local_position.x),
                snap_to_grid(placement_y + pin_local_position.y),
            )
            label_sexps.append(_label_for_net(
                io_row.carrier_signal, label_position,
            ))
    return instance_sexps, label_sexps


def _build_som_instance_sexp(
    qualified_name: str,
    connector_name: str,
    placement: Point,
    connector_uuid: str,
    schematic_uuid: str,
    project_name: str,
    pin_records: tuple[tuple[str, Point, float], ...],
) -> SExp:
    body = SExp("symbol")
    body.add(SExp("lib_id", atoms=[qualified_name]))
    body.add(SExp("at", atoms=[placement.x, placement.y, 0]))
    body.add(SExp("unit", atoms=[1]))
    body.add(SExp("exclude_from_sim", atoms=[False]))
    body.add(SExp("in_bom", atoms=[True]))
    body.add(SExp("on_board", atoms=[True]))
    body.add(SExp("dnp", atoms=[False]))
    body.add(SExp("fields_autoplaced", atoms=[True]))
    body.add(SExp("uuid", atoms=[connector_uuid]))
    body.add(property_(
        "Reference", connector_name,
        x=placement.x + 2.54, y=placement.y - 6.0,
        font_size=1.778, bold=True, justify="left",
    ))
    body.add(property_(
        "Value", f"Zynq_SoM_{connector_name}",
        x=placement.x + 2.54, y=placement.y - 3.0,
        font_size=KICAD_PROPERTY_FONT_MM, justify="left",
    ))
    body.add(property_(
        "Footprint", SOM_CONNECTOR_FOOTPRINT,
        x=placement.x, y=placement.y, hide=True,
    ))
    body.add(property_(
        "Datasheet", "", x=placement.x, y=placement.y, hide=True,
    ))
    body.add(property_(
        "Description", SOM_CONNECTOR_DESCRIPTION,
        x=placement.x, y=placement.y, hide=True,
    ))
    for pin_number, _, _ in pin_records:
        pin_entry = SExp("pin", atoms=[pin_number])
        pin_entry.add(SExp("uuid", atoms=[make_uuid()]))
        body.add(pin_entry)
    instances = SExp("instances")
    project = SExp("project", atoms=[project_name])
    path = SExp("path", atoms=[f"/{schematic_uuid}"])
    path.add(SExp("reference", atoms=[connector_name]))
    path.add(SExp("unit", atoms=[1]))
    project.add(path)
    instances.add(project)
    body.add(instances)
    return body


# ---------------------------------------------------------------------------
# IO assignment validation (rule sets F)
# ---------------------------------------------------------------------------


def _validate_io_assignment(
    io_assignment: tuple[IoAssignmentRow, ...],
    validator: Validator,
) -> None:
    valid_pins_per_connector: dict[str, set[str]] = {
        connector_name: set() for connector_name in SOM_CONNECTOR_NAMES
    }
    for connector_name in SOM_CONNECTOR_NAMES:
        symbol_csv_path = CARRIER_DIR / f"symbol_{connector_name}.csv"
        if not symbol_csv_path.exists():
            raise FileNotFoundError(f"Missing {symbol_csv_path}")
        with open(symbol_csv_path, encoding="utf-8") as csv_file:
            reader = csv.reader(csv_file)
            next(reader)
            next(reader)
            for row in reader:
                if row:
                    valid_pins_per_connector[connector_name].add(row[0])

    usage_counts: Counter[tuple[str, str]] = Counter()
    diff_signal_names: set[str] = set()
    for line_number, row in enumerate(io_assignment, start=2):
        validator.check_io_pin_exists(
            row.som_connector, row.som_pin,
            valid_pins_per_connector.get(row.som_connector, set()),
            line_number,
        )
        usage_counts[(row.som_connector, row.som_pin)] += 1
        if row.interface != "POWER":
            diff_signal_names.add(row.som_net)
    validator.check_io_pin_unique(usage_counts)
    validator.check_diff_pair_completeness(diff_signal_names)


# ---------------------------------------------------------------------------
# Wire/junction post-processing
# ---------------------------------------------------------------------------


def _deduplicate_wires_and_emit_junctions(
    schematic_objects: list[SExp],
) -> list[SExp]:
    """Collapse exact-duplicate wires and add junctions at every T-intersection.

    Wire deduplication: two wires sharing both endpoints (in either order)
    are collapsed to one. Ensures Rule J3 passes strictly.

    Junction emission: any endpoint of any wire that lies in the strict
    interior of another wire's segment gets a junction. Ensures Rule J4
    passes strictly.
    """
    from scripts.carrier.core.geometry import detect_t_intersections

    deduped_wires_by_endpoints: dict[
        tuple[tuple[float, float], tuple[float, float]], SExp
    ] = {}
    junctions_by_position: dict[tuple[float, float], SExp] = {}
    other_objects: list[SExp] = []
    for sexp in schematic_objects:
        if sexp.head == "wire":
            start_position, end_position = _extract_wire_segment(sexp)
            canonical = tuple(sorted([start_position, end_position]))
            if canonical not in deduped_wires_by_endpoints:
                deduped_wires_by_endpoints[canonical] = sexp
        elif sexp.head == "junction":
            junction_position = _extract_junction_position(sexp)
            junctions_by_position.setdefault(junction_position, sexp)
        else:
            other_objects.append(sexp)

    deduped_wires = list(deduped_wires_by_endpoints.values())
    wire_segments_for_t_check = [
        (Point(*start), Point(*end))
        for start, end in (
            _extract_wire_segment(sexp) for sexp in deduped_wires
        )
    ]
    intersections = detect_t_intersections(wire_segments_for_t_check)
    for intersection_point in intersections:
        position_key = (intersection_point.x, intersection_point.y)
        if position_key in junctions_by_position:
            continue
        junctions_by_position[position_key] = junction(
            intersection_point, diameter=JUNCTION_DOT_DIAMETER_MM,
        )

    return deduped_wires + list(junctions_by_position.values()) + other_objects


def _extract_wire_segment(
    wire_sexp: SExp,
) -> tuple[tuple[float, float], tuple[float, float]]:
    pts_child = next(child for child in wire_sexp.children if child.head == "pts")
    xy_children = [child for child in pts_child.children if child.head == "xy"]
    return (
        (float(xy_children[0].atoms[0]), float(xy_children[0].atoms[1])),
        (float(xy_children[1].atoms[0]), float(xy_children[1].atoms[1])),
    )


def _extract_junction_position(junction_sexp: SExp) -> tuple[float, float]:
    at_child = next(child for child in junction_sexp.children if child.head == "at")
    return (float(at_child.atoms[0]), float(at_child.atoms[1]))


# ---------------------------------------------------------------------------
# Geometry validation pass
# ---------------------------------------------------------------------------


def _validate_geometry(
    validator: Validator,
    placed_symbols: list[PlacedSymbol],
    geometry_objects: list[SExp],
) -> None:
    wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    junction_positions: set[tuple[float, float]] = set()
    for sexp in geometry_objects:
        if sexp.head == "wire":
            wire_segments.append(_extract_wire_segment(sexp))
        elif sexp.head == "junction":
            junction_positions.add(_extract_junction_position(sexp))

    component_boxes: list[tuple[
        tuple[float, float], tuple[float, float], str
    ]] = []
    for placed in placed_symbols:
        bounding_box = placed.bounding_box
        component_boxes.append((
            (bounding_box.top_left.x, bounding_box.top_left.y),
            (bounding_box.bottom_right.x, bounding_box.bottom_right.y),
            placed.reference,
        ))

    sheet_label = "carrier_template"
    validator.check_wire_orthogonal(sheet_label, wire_segments)
    validator.check_wire_grid(sheet_label, wire_segments)
    validator.check_no_duplicate_wires(sheet_label, wire_segments)
    validator.check_t_intersection_junctions(
        sheet_label, wire_segments, junction_positions,
    )
    validator.check_no_wire_through_component(
        sheet_label, wire_segments, component_boxes,
    )


# ---------------------------------------------------------------------------
# Main generator entry point
# ---------------------------------------------------------------------------


def generate(validate_only: bool = False) -> int:
    validator = Validator()
    _reset_external_refs()

    for part in REGISTRY.values():
        validator.check_bom_part(part)
        validator.check_footprint_prefix(part)

    io_assignment = _load_io_assignment()
    _validate_io_assignment(io_assignment, validator)

    schematic_uuid = make_uuid()
    build = SchematicBuild.empty()

    for section_name, section_spec in SECTION_LAYOUT.items():
        build.decorative_objects.append(
            text_label(
                section_spec.label or section_name,
                Point(
                    section_spec.origin.x,
                    snap_to_grid(section_spec.origin.y - 2.54),
                ),
                font_size=2.54,
                bold=True,
            )
        )

    for zone in compute_zones():
        zone_placed, zone_objects, _ = _place_zone(zone, validator)
        build.placed_symbols.extend(zone_placed)
        build.geometry_objects.extend(
            sexp for sexp in zone_objects
            if sexp.head in {"wire", "junction"}
        )
        build.label_objects.extend(
            sexp for sexp in zone_objects
            if sexp.head in {"label", "global_label", "hierarchical_label"}
        )

    section_symbol_counts: Counter[str] = Counter()
    for placed in build.placed_symbols:
        for section_name, section_spec in SECTION_LAYOUT.items():
            if section_spec.bounding_box.contains(placed.origin):
                section_symbol_counts[section_name] += 1
                break
    for section_name, symbol_count in section_symbol_counts.items():
        validator.check_sheet_size(section_name, symbol_count)

    som_library = _load_som_library()
    som_instances, som_pin_labels = _place_som_connectors(
        som_library=som_library,
        schematic_uuid=schematic_uuid,
        project_name=PROJECT_NAME,
        io_assignment=io_assignment,
        validator=validator,
    )
    build.label_objects.extend(som_pin_labels)

    build.geometry_objects = _deduplicate_wires_and_emit_junctions(
        build.geometry_objects,
    )

    _validate_geometry(validator, build.placed_symbols, build.geometry_objects)

    total_cost_usd = _compute_bom_total(build.placed_symbols)
    validator.report_bom_total(total_cost_usd)

    schematic_root = _assemble_root(
        schematic_uuid=schematic_uuid,
        som_library=som_library,
        som_instances=som_instances,
        build=build,
    )

    rendered_schematic = schematic_root.dumps() + "\n"
    temp_path = SCH_PATH.with_suffix(".kicad_sch.tmp")
    if validate_only:
        print(rendered_schematic[:500])
    else:
        temp_path.write_text(rendered_schematic, encoding="utf-8")
        validator.check_paren_balance(temp_path)

    exit_code = validator.report(output_path=VALIDATION_REPORT_PATH)
    if exit_code != 0:
        if not validate_only and temp_path.exists():
            temp_path.unlink()
        print(f"\nValidation failed - {SCH_PATH} NOT updated")
        return exit_code

    if not validate_only:
        temp_path.replace(SCH_PATH)
        print(f"\nWrote {SCH_PATH}")
        _update_project_uuid(schematic_uuid)
        for lock_file in CARRIER_DIR.glob("*.lck"):
            lock_file.unlink()
    return 0


def _compute_bom_total(placed_symbols: list[PlacedSymbol]) -> float:
    counts_per_token: Counter[str] = Counter()
    for placed in placed_symbols:
        for token, registry_part in REGISTRY.items():
            if registry_part.value == placed.value or registry_part.mpn == placed.value:
                counts_per_token[token] += 1
                break
    total_usd = 0.0
    for token, count in counts_per_token.items():
        total_usd += REGISTRY[token].unit_price_usd * count
    return total_usd


def _assemble_root(
    schematic_uuid: str,
    som_library: tuple[SomLibrarySymbol, ...],
    som_instances: list[SExp],
    build: SchematicBuild,
) -> SExp:
    root = SExp("kicad_sch")
    root.add(SExp("version", atoms=[SCHEMATIC_FORMAT_VERSION]))
    root.add(SExp("generator", atoms=[SCHEMATIC_GENERATOR_NAME]))
    root.add(SExp("generator_version", atoms=[SCHEMATIC_GENERATOR_VERSION]))
    root.add(SExp("uuid", atoms=[schematic_uuid]))
    root.add(SExp("paper", atoms=[PAPER_SIZE]))

    title = SExp("title_block")
    title.add(SExp("title", atoms=["Zynq SoM Carrier - Full Eval Board"]))
    title.add(SExp("date", atoms=[""]))
    title.add(SExp("rev", atoms=["A"]))
    title.add(SExp("company", atoms=["Zynq-SoM"]))
    title.add(SExp("comment", atoms=[
        1, "Auto-generated; all parts derived from datasheet reference circuits"
    ]))
    title.add(SExp("comment", atoms=[
        2, "Sections organized by function; rearrange visually after generation"
    ]))
    root.add(title)

    lib_symbols = SExp("lib_symbols")
    for som_symbol in som_library:
        lib_symbols.add(SExp.raw(som_symbol.body_text))
    for placed in build.placed_symbols:
        if placed.lib_id in build.used_lib_ids:
            continue
        build.used_lib_ids.add(placed.lib_id)
        symbol_def = next(
            (sym for sym in SYMBOL_LIBRARY.values() if sym.lib_id == placed.lib_id),
            None,
        )
        if symbol_def is None:
            raise KeyError(
                f"_assemble_root: lib_id {placed.lib_id!r} placed on schematic but "
                f"missing from SYMBOL_LIBRARY"
            )
        lib_symbols.add(build_lib_symbol_sexp(symbol_def))
    root.add(lib_symbols)

    for som_instance_sexp in som_instances:
        root.add(som_instance_sexp)

    for placed in build.placed_symbols:
        root.add(build_symbol_instance_sexp(placed, schematic_uuid, PROJECT_NAME))

    for sexp in build.geometry_objects:
        root.add(sexp)

    for sexp in build.label_objects:
        root.add(sexp)

    for sexp in build.decorative_objects:
        root.add(sexp)

    sheet_instances = SExp("sheet_instances")
    sheet_path = SExp("path", atoms=["/"])
    sheet_path.add(SExp("page", atoms=["1"]))
    sheet_instances.add(sheet_path)
    root.add(sheet_instances)

    root.add(SExp("embedded_fonts", atoms=[False]))
    return root


def _update_project_uuid(schematic_uuid: str) -> None:
    if not PROJECT_PATH.exists():
        return
    project_data = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    schematic_section = project_data.setdefault("schematic", {})
    schematic_section["top_level_sheets"] = [{
        "filename": SCH_PATH.name,
        "name": SCH_PATH.stem,
        "uuid": schematic_uuid,
    }]
    PROJECT_PATH.write_text(
        json.dumps(project_data, indent=2) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    import sys
    raise SystemExit(generate(validate_only="--check" in sys.argv))
