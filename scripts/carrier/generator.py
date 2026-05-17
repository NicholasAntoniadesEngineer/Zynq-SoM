"""Main carrier schematic generator.

Produces a single comprehensive A1 schematic file containing every
component the carrier needs. Sections are organized by function with
text-banner titles. Each IC's ReferenceCircuit is placed adjacent to
the IC, with the required external parts wired up - decoupling caps via
``place_decoupling`` (Manhattan-routed with junctions), pull-ups and
other externals via direct routing with global labels at the network
endpoint.

Run with:
    python -m scripts.carrier.generator
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

from scripts.carrier.core.geometry import BoundingBox
from scripts.carrier.core.parts import DECOUPLING_REQUIRED_PIN_TYPES
from scripts.carrier.core.placement import can_place_decoupling, place_decoupling
from scripts.carrier.core.refcircuit import ExternalPart, ReferenceCircuit
from scripts.carrier.core.registry import REGISTRY
from scripts.carrier.core.sexpr import (
    KICAD_GRID_MM,
    Point,
    SExp,
    global_label,
    local_label,
    make_uuid,
    property_,
    screen_left,
    screen_right,
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

PAPER_SIZE: str = "A1"
PROJECT_NAME: str = "carrier_template"
DECOUPLING_STACK_PITCH_MM: float = 7.62
EXTERNAL_PART_HORIZONTAL_OFFSET_MM: float = 7.62
EXTERNAL_PART_LABEL_GAP_MM: float = 5.08


SECTION_LAYOUT: dict[str, tuple[float, float, str]] = {
    "som_j1":        (10.0,   20.0, "SoM J1 - Power + USB + JTAG + SDIO + Ethernet MDI"),
    "som_j2":        (75.0,   20.0, "SoM J2 - Bank 13 + Bank 33 IO"),
    "som_j3":        (140.0,  20.0, "SoM J3 - Bank 33/34/35 IO"),
    "power":         (205.0,  20.0, "Power: VIN + VCCO LDOs + Indicators"),
    "usbc_stm32":    (310.0,  20.0, "USB-C #1 (STM32 PD/Data)"),
    "usbc_otg":      (310.0, 130.0, "USB-C #2 (Zynq OTG via USB3318)"),
    "ethernet":      (410.0,  20.0, "Ethernet: RJ45 + HX5008 Magnetics + ESD"),
    "microsd":       (410.0, 130.0, "microSD Card Socket"),
    "uart_bridge":   (410.0, 200.0, "USB-UART Bridge (CP2102N)"),
    "jtag_swd":      (410.0, 280.0, "JTAG + SWD Headers"),
    "hdmi_tx":       (510.0,  20.0, "HDMI TX (Source)"),
    "hdmi_rx":       (510.0, 130.0, "HDMI RX (Sink)"),
    "lvds_lcd":      (510.0, 240.0, "LVDS LCD Connector"),
    "mipi_camera":   (510.0, 320.0, "MIPI CSI-2 Camera"),
    "fmc_lpc":       (640.0,  20.0, "FMC-LPC Expansion"),
    "pmod":          (640.0, 170.0, "PMOD Headers x4"),
    "aux":           (640.0, 300.0, "Aux: RTC + EEPROM + Power Monitoring"),
    "xadc_clk":      (760.0, 300.0, "XADC + MRCC Clock SMAs"),
    "boot_switches": (760.0, 400.0, "Boot Mode + Reset"),
}


_REF_PREFIX_BY_FOOTPRINT_BUCKET: dict[str, str] = {
    "Capacitor_SMD:": "C",
    "Resistor_SMD:": "R",
    "Inductor_SMD:": "L",
    "LED_SMD:": "D",
    "Diode_SMD:": "D",
}


def _read_existing_symbol_lib() -> str:
    """Read the J1/J2/J3 connector symbol definitions from the original lib."""
    if not SYMBOL_LIB_PATH.exists():
        raise FileNotFoundError(
            f"Missing {SYMBOL_LIB_PATH}; run symbol_creation.bash first"
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
    raise ValueError("Unbalanced parens in symbol library")


def _rename_symbol(body_text: str, original_name: str, qualified_name: str) -> str:
    return body_text.replace(
        f'(symbol "{original_name}"',
        f'(symbol "{qualified_name}"',
        1,
    )


def _extract_pin_numbers(body_text: str) -> list[str]:
    return re.findall(r'\(number\s+"([^"]+)"', body_text)


# ---------------------------------------------------------------------------
# Reference designator counter (per generator pass)
# ---------------------------------------------------------------------------


def _make_ref_counter() -> Counter[str]:
    return Counter()


_ref_counter: Counter[str] = _make_ref_counter()


def _synthesize_reference(part_token: str, ref_prefix: str) -> str:
    _ref_counter[ref_prefix] += 1
    return f"{ref_prefix}{_ref_counter[ref_prefix]:03d}"


def _ref_prefix_for(footprint: str) -> str:
    for footprint_bucket, prefix in _REF_PREFIX_BY_FOOTPRINT_BUCKET.items():
        if footprint.startswith(footprint_bucket):
            return prefix
    return "X"


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
    return SYMBOL_LIBRARY["R"]


def _is_decoupling(external: ExternalPart, footprint_bucket: str) -> bool:
    """Heuristic: a capacitor whose ``to_net`` is GND."""
    return (
        footprint_bucket == "Capacitor_SMD:"
        and external.to_net.upper() == "GND"
    )


def _ic_pin_supports_decoupling(ic: PlacedSymbol, pin_name: str) -> bool:
    for pin in ic.symbol.pins:
        if pin.number == pin_name or pin.name == pin_name:
            return pin.electrical_type in DECOUPLING_REQUIRED_PIN_TYPES
    return False


# ---------------------------------------------------------------------------
# Reference circuit placement + wiring
# ---------------------------------------------------------------------------


def _place_refcircuit(
    ic_name: str,
    circuit: ReferenceCircuit,
    ref_des: str,
    origin: Point,
    validator: Validator,
    sheet_name: str,
) -> tuple[list[PlacedSymbol], list[SExp], list[tuple[str, str]]]:
    """Place an IC, its external parts, and the wires that connect them.

    Returns:
        (placed_symbols, schematic_objects, externals_for_validation)
        where ``schematic_objects`` includes wires, junctions, labels, and
        any text annotations emitted by this refcircuit.
    """

    placed_symbols: list[PlacedSymbol] = []
    schematic_objects: list[SExp] = []
    externals_for_validation: list[tuple[str, str]] = []

    ic_symbol_def = (
        SYMBOL_LIBRARY.get(circuit.part_mpn)
        or SYMBOL_LIBRARY.get(circuit.symbol_token)
    )
    if ic_symbol_def is None:
        validator._add(
            "C11", "warn", f"{sheet_name}:{ref_des}",
            f"No SYMBOL_LIBRARY entry for {circuit.part_mpn}; skipping IC placement",
            True,
        )
        return placed_symbols, schematic_objects, externals_for_validation

    ic_origin = Point(
        snap_to_grid(origin.x),
        snap_to_grid(origin.y + 15.0),
    )
    ic_symbol = PlacedSymbol(
        reference=ref_des,
        symbol=ic_symbol_def,
        value=circuit.part_mpn,
        footprint=circuit.footprint,
        origin=ic_origin,
    )
    placed_symbols.append(ic_symbol)
    validator.check_reference_uniqueness(ref_des, sheet_name)
    validator.check_uuid_unique(ic_symbol.uuid, f"{sheet_name}:{ref_des}")

    obstacles: list[BoundingBox] = [ic_symbol.bounding_box]
    decoupling_index_per_pin: Counter[str] = Counter()
    horizontal_index_per_pin: Counter[str] = Counter()

    for external in circuit.external_parts:
        for _ in range(external.quantity):
            ext_part = REGISTRY.get(external.part_token)
            if ext_part is None:
                validator._add(
                    "C11", "strict", f"{sheet_name}:{ref_des}",
                    f"Unknown external part token {external.part_token!r}", False,
                )
                continue
            footprint_bucket = ext_part.footprint.split(":", 1)[0] + ":"
            ref_prefix = _ref_prefix_for(ext_part.footprint)
            ext_reference = _synthesize_reference(external.part_token, ref_prefix)
            generic_symbol = _generic_symbol_for(ext_part.footprint)

            decoupling_distance_mm = (
                KICAD_GRID_MM * 4
                + decoupling_index_per_pin[external.from_pin]
                * DECOUPLING_STACK_PITCH_MM
            )
            attempt_decoupling = (
                _is_decoupling(external, footprint_bucket)
                and _ic_pin_supports_decoupling(ic_symbol, external.from_pin)
                and can_place_decoupling(
                    ic=ic_symbol,
                    vdd_pin_name=external.from_pin,
                    cap_symbol_def=generic_symbol,
                    obstacles=tuple(obstacles),
                    distance_mm=decoupling_distance_mm,
                )
            )

            placed_external_symbols, placed_objects = _wire_external_part(
                ic=ic_symbol,
                external=external,
                ic_pin_name=external.from_pin,
                cap_symbol_def=generic_symbol,
                ext_reference=ext_reference,
                ext_value=ext_part.value,
                ext_footprint=ext_part.footprint,
                obstacles=tuple(obstacles),
                decoupling_distance_mm=decoupling_distance_mm,
                horizontal_index=horizontal_index_per_pin[external.from_pin],
                use_decoupling=attempt_decoupling,
            )

            placed_symbols.extend(placed_external_symbols)
            schematic_objects.extend(placed_objects)
            for placed in placed_external_symbols:
                obstacles.append(placed.bounding_box)
                validator.check_uuid_unique(
                    placed.uuid, f"{sheet_name}:{placed.reference}"
                )
                validator.check_reference_uniqueness(
                    placed.reference, sheet_name
                )
            externals_for_validation.append((external.from_pin, external.part_token))

            if attempt_decoupling:
                decoupling_index_per_pin[external.from_pin] += 1
            else:
                horizontal_index_per_pin[external.from_pin] += 1

    validator.check_refcircuit_conformance(ref_des, circuit, externals_for_validation)
    return placed_symbols, schematic_objects, externals_for_validation


def _wire_external_part(
    ic: PlacedSymbol,
    external: ExternalPart,
    ic_pin_name: str,
    cap_symbol_def: SymbolDef,
    ext_reference: str,
    ext_value: str,
    ext_footprint: str,
    obstacles: tuple[BoundingBox, ...],
    decoupling_distance_mm: float,
    horizontal_index: int,
    use_decoupling: bool,
) -> tuple[list[PlacedSymbol], list[SExp]]:
    """Place one external part and wire it from the IC pin to its target net.

    The caller is expected to have validated feasibility via
    ``can_place_decoupling`` before passing ``use_decoupling=True``. If
    ``place_decoupling`` raises after that precheck it is a programmer
    error and the exception propagates rather than being swallowed.
    """

    if use_decoupling:
        result = place_decoupling(
            ic=ic,
            vdd_pin_name=ic_pin_name,
            gnd_net=external.to_net,
            cap_symbol_def=cap_symbol_def,
            cap_reference=ext_reference,
            cap_value=ext_value,
            cap_footprint=ext_footprint,
            obstacles=obstacles,
            distance_mm=decoupling_distance_mm,
        )
        return [result.cap_symbol], list(result.schematic_objects)

    return _place_horizontal_external(
        ic=ic,
        external=external,
        ic_pin_name=ic_pin_name,
        ext_symbol_def=cap_symbol_def,
        ext_reference=ext_reference,
        ext_value=ext_value,
        ext_footprint=ext_footprint,
        horizontal_index=horizontal_index,
    )


def _place_horizontal_external(
    ic: PlacedSymbol,
    external: ExternalPart,
    ic_pin_name: str,
    ext_symbol_def: SymbolDef,
    ext_reference: str,
    ext_value: str,
    ext_footprint: str,
    horizontal_index: int,
) -> tuple[list[PlacedSymbol], list[SExp]]:
    """Place an external part horizontally outward from the IC pin's side
    and label its far pin with the target net name.

    "Outward" means: if the IC pin is on the left side of the IC body, the
    external part lands further LEFT (away from the IC), and similarly for
    right-side pins. This keeps wires from crossing the IC body.
    """
    pin_side = _ic_pin_side(ic, ic_pin_name)
    if pin_side is None:
        return [], []
    try:
        ic_pin_position = ic.pin_position(ic_pin_name)
    except KeyError:
        return [], []

    pin_pitch_per_index_mm = (
        EXTERNAL_PART_HORIZONTAL_OFFSET_MM + ext_symbol_def.width_mm
    )
    base_offset_mm = (
        EXTERNAL_PART_HORIZONTAL_OFFSET_MM
        + horizontal_index * pin_pitch_per_index_mm
    )

    if pin_side == "R":
        ext_pin_1_target = screen_right(ic_pin_position, base_offset_mm)
        ext_pin_1_local = ext_symbol_def.pin_position("1")
    else:
        ext_pin_1_target = screen_left(
            ic_pin_position, base_offset_mm + ext_symbol_def.width_mm,
        )
        ext_pin_1_local = ext_symbol_def.pin_position("2")

    ext_origin = Point(
        snap_to_grid(ext_pin_1_target.x - ext_pin_1_local.x),
        snap_to_grid(ext_pin_1_target.y - ext_pin_1_local.y),
    )
    ext_symbol = PlacedSymbol(
        reference=ext_reference,
        symbol=ext_symbol_def,
        value=ext_value,
        footprint=ext_footprint,
        origin=ext_origin,
    )

    if pin_side == "R":
        ic_facing_pin_position = ext_symbol.pin_position("1")
        outer_pin_position = ext_symbol.pin_position("2")
        label_position = screen_right(outer_pin_position, EXTERNAL_PART_LABEL_GAP_MM)
    else:
        ic_facing_pin_position = ext_symbol.pin_position("2")
        outer_pin_position = ext_symbol.pin_position("1")
        label_position = screen_left(outer_pin_position, EXTERNAL_PART_LABEL_GAP_MM)

    schematic_objects: list[SExp] = []
    schematic_objects.append(wire(ic_pin_position, ic_facing_pin_position))
    schematic_objects.append(wire(outer_pin_position, label_position))
    if external.to_net.upper() == "GND" or external.to_net.startswith("+"):
        schematic_objects.append(global_label(external.to_net, label_position))
    else:
        schematic_objects.append(local_label(external.to_net, label_position))

    return [ext_symbol], schematic_objects


def _ic_pin_side(ic: PlacedSymbol, name_or_number: str) -> str | None:
    for pin in ic.symbol.pins:
        if pin.number == name_or_number or pin.name == name_or_number:
            return pin.side
    return None


# ---------------------------------------------------------------------------
# IC layout map - which sections hold which ICs
# ---------------------------------------------------------------------------

IC_TO_SECTION: dict[str, tuple[str, str]] = {
    "FUSB302BMPX":         ("usbc_stm32",  "U_PD1"),
    "USBLC6-4SC6":         ("usbc_stm32",  "U_ESD_USB1"),
    "TPS2051CDBVR":        ("usbc_otg",    "U_LS1"),
    "CP2102N-A02-GQFN24R": ("uart_bridge", "U_UART"),
    "TPD12S016PWR_TX":     ("hdmi_tx",     "U_HDMITX"),
    "TPD12S016PWR_RX":     ("hdmi_rx",     "U_HDMIRX"),
    "INA226AIDGSR":        ("aux",         "U_INA1"),
    "DS3231SN#":           ("aux",         "U_RTC"),
    "24LC256T-I/SN":       ("aux",         "U_EEP"),
    "TLV75733PDBVR":       ("power",       "U_LDO_VCCO13"),
    "TLV75718PDBVR":       ("power",       "U_LDO_18V_ALT"),
    "TLV75725PDBVR":       ("power",       "U_LDO_25V_ALT"),
    "HX5008NLT":           ("ethernet",    "T_ETH"),
    "USBC_SINK":           ("usbc_stm32",  "J_USBC1"),
    "HDMI_A":              ("hdmi_tx",     "J_HDMITX"),
    "DM3AT-SF-PEJM5":      ("microsd",     "J_SD"),
    "RJHSE5380":           ("ethernet",    "J_RJ45"),
}


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate(validate_only: bool = False) -> int:
    validator = Validator()
    project_name = PROJECT_NAME
    _ref_counter.clear()

    for part in REGISTRY.values():
        validator.check_bom_part(part)
        validator.check_footprint_prefix(part)

    _validate_io_assignment(validator)

    schematic_uuid = make_uuid()
    placed_all: list[PlacedSymbol] = []
    used_lib_ids: set[str] = set()
    decorative_objects: list[SExp] = []
    geometry_wires: list[SExp] = []

    for section_name, (section_x, section_y, section_label) in SECTION_LAYOUT.items():
        decorative_objects.append(
            text_label(section_label, Point(section_x, section_y - 4.0),
                       font_size=2.54, bold=True)
        )

    for ic_name, circuit in REFCIRCUITS.items():
        section_assignment = IC_TO_SECTION.get(ic_name)
        if section_assignment is None:
            continue
        section_name, base_reference = section_assignment
        if section_name not in SECTION_LAYOUT:
            continue
        section_x, section_y, _ = SECTION_LAYOUT[section_name]
        section_origin = Point(section_x, section_y)
        placed_for_circuit, objects_for_circuit, _ = _place_refcircuit(
            ic_name=ic_name,
            circuit=circuit,
            ref_des=base_reference,
            origin=section_origin,
            validator=validator,
            sheet_name=section_name,
        )
        placed_all.extend(placed_for_circuit)
        for emitted_object in objects_for_circuit:
            if emitted_object.head in {"wire", "junction"}:
                geometry_wires.append(emitted_object)
            else:
                decorative_objects.append(emitted_object)

    som_lib_text = _read_existing_symbol_lib()
    som_symbol_definitions: list[tuple[str, str, list[str]]] = []
    som_positions = {
        "J1": SECTION_LAYOUT["som_j1"][:2],
        "J2": SECTION_LAYOUT["som_j2"][:2],
        "J3": SECTION_LAYOUT["som_j3"][:2],
    }
    for j_name in ("J1", "J2", "J3"):
        symbol_name = f"Zynq_SoM_{j_name}"
        symbol_body = _extract_named_symbol(som_lib_text, symbol_name)
        qualified_name = f"Zynq_SoM:{symbol_name}"
        body_renamed = _rename_symbol(symbol_body, symbol_name, qualified_name)
        pin_numbers = _extract_pin_numbers(symbol_body)
        som_symbol_definitions.append((qualified_name, body_renamed, pin_numbers))

    section_symbol_counts: Counter[str] = Counter()
    for placed in placed_all:
        for section_name, (section_x, section_y, _) in SECTION_LAYOUT.items():
            if (
                abs(placed.origin.x - section_x) < 80
                and abs(placed.origin.y - section_y) < 100
            ):
                section_symbol_counts[section_name] += 1
                break
    for section_name, symbol_count in section_symbol_counts.items():
        validator.check_sheet_size(section_name, symbol_count)

    _validate_geometry(validator, placed_all, geometry_wires)

    total_cost_usd = 0.0
    cost_seen: Counter[str] = Counter()
    for placed in placed_all:
        for token, registry_part in REGISTRY.items():
            if registry_part.value == placed.value or registry_part.mpn == placed.value:
                cost_seen[token] += 1
                break
    for token, count in cost_seen.items():
        total_cost_usd += REGISTRY[token].unit_price_usd * count
    validator.report_bom_total(total_cost_usd)

    schematic_root = _build_root_sexp(
        schematic_uuid=schematic_uuid,
        project_name=project_name,
        placed_all=placed_all,
        som_symbol_definitions=som_symbol_definitions,
        som_positions=som_positions,
        used_lib_ids=used_lib_ids,
        decorative_objects=decorative_objects,
        geometry_wires=geometry_wires,
        validator=validator,
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


def _validate_geometry(
    validator: Validator,
    placed_symbols: list[PlacedSymbol],
    geometry_objects: list[SExp],
) -> None:
    """Run Rule Set J across all emitted wires and junctions on the sheet."""
    wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    junction_positions: set[tuple[float, float]] = set()
    for emitted_object in geometry_objects:
        if emitted_object.head == "wire":
            wire_segments.append(_extract_wire_segment(emitted_object))
        elif emitted_object.head == "junction":
            junction_positions.add(_extract_junction_position(emitted_object))

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


def _validate_io_assignment(validator: Validator) -> None:
    io_csv = CARRIER_DIR / "io_assignment.csv"
    valid_pins_per_connector: dict[str, set[str]] = {
        "J1": set(), "J2": set(), "J3": set(),
    }
    for connector_name in valid_pins_per_connector:
        symbol_csv_path = CARRIER_DIR / f"symbol_{connector_name}.csv"
        if not symbol_csv_path.exists():
            continue
        with open(symbol_csv_path, encoding="utf-8") as csv_file:
            reader = csv.reader(csv_file)
            next(reader)
            next(reader)
            for row in reader:
                if row:
                    valid_pins_per_connector[connector_name].add(row[0])

    if not io_csv.exists():
        return

    usage_counts: Counter[tuple[str, str]] = Counter()
    diff_signal_names: set[str] = set()
    with open(io_csv, encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for line_number, row in enumerate(reader, start=2):
            connector_name = row["som_connector"]
            pin_number = row["som_pin"]
            validator.check_io_pin_exists(
                connector_name, pin_number,
                valid_pins_per_connector.get(connector_name, set()),
                line_number,
            )
            usage_counts[(connector_name, pin_number)] += 1
            if row["interface"] not in {"POWER"}:
                diff_signal_names.add(row["som_net"])
    validator.check_io_pin_unique(usage_counts)
    validator.check_diff_pair_completeness(diff_signal_names)


def _build_root_sexp(
    schematic_uuid: str,
    project_name: str,
    placed_all: list[PlacedSymbol],
    som_symbol_definitions: list[tuple[str, str, list[str]]],
    som_positions: dict[str, tuple[float, float]],
    used_lib_ids: set[str],
    decorative_objects: list[SExp],
    geometry_wires: list[SExp],
    validator: Validator,
) -> SExp:
    root = SExp("kicad_sch")
    root.add(SExp("version", atoms=[20250114]))
    root.add(SExp("generator", atoms=["eeschema"]))
    root.add(SExp("generator_version", atoms=["9.0"]))
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
    for qualified_name, body_text, _ in som_symbol_definitions:
        lib_symbols.add(SExp.raw(body_text))
    for placed in placed_all:
        if placed.lib_id in used_lib_ids:
            continue
        used_lib_ids.add(placed.lib_id)
        symbol_def = next(
            (sym for sym in SYMBOL_LIBRARY.values() if sym.lib_id == placed.lib_id),
            None,
        )
        if symbol_def is None:
            continue
        lib_symbols.add(build_lib_symbol_sexp(symbol_def))
    root.add(lib_symbols)

    for j_name in ("J1", "J2", "J3"):
        qualified_name = f"Zynq_SoM:Zynq_SoM_{j_name}"
        pin_numbers = next(p for q, _, p in som_symbol_definitions if q == qualified_name)
        section_x, section_y = som_positions[j_name]
        som_uuid = make_uuid()
        validator.check_uuid_unique(som_uuid, f"carrier_template:{j_name}")
        validator.check_reference_uniqueness(j_name, "carrier_template")
        som_instance = SExp("symbol")
        som_instance.add(SExp("lib_id", atoms=[qualified_name]))
        som_instance.add(SExp("at", atoms=[section_x, section_y, 0]))
        som_instance.add(SExp("unit", atoms=[1]))
        som_instance.add(SExp("exclude_from_sim", atoms=[False]))
        som_instance.add(SExp("in_bom", atoms=[True]))
        som_instance.add(SExp("on_board", atoms=[True]))
        som_instance.add(SExp("dnp", atoms=[False]))
        som_instance.add(SExp("fields_autoplaced", atoms=[True]))
        som_instance.add(SExp("uuid", atoms=[som_uuid]))
        som_instance.add(property_(
            "Reference", j_name,
            x=section_x + 2.54, y=section_y - 6.0,
            font_size=1.778, bold=True, justify="left",
        ))
        som_instance.add(property_(
            "Value", f"Zynq_SoM_{j_name}",
            x=section_x + 2.54, y=section_y - 3.0,
            font_size=1.27, justify="left",
        ))
        som_instance.add(property_(
            "Footprint", "fp:HRS_DF40C-100DP-0.4V_51_",
            x=section_x, y=section_y, hide=True,
        ))
        som_instance.add(property_(
            "Datasheet", "", x=section_x, y=section_y, hide=True,
        ))
        som_instance.add(property_(
            "Description", "Zynq SoM mating connector (100 pin)",
            x=section_x, y=section_y, hide=True,
        ))
        for pin_number in pin_numbers:
            pin_entry = SExp("pin", atoms=[pin_number])
            pin_entry.add(SExp("uuid", atoms=[make_uuid()]))
            som_instance.add(pin_entry)
        instances = SExp("instances")
        project = SExp("project", atoms=[project_name])
        path = SExp("path", atoms=[f"/{schematic_uuid}"])
        path.add(SExp("reference", atoms=[j_name]))
        path.add(SExp("unit", atoms=[1]))
        project.add(path)
        instances.add(project)
        som_instance.add(instances)
        root.add(som_instance)

    for placed in placed_all:
        root.add(build_symbol_instance_sexp(placed, schematic_uuid, project_name))

    for wire_or_junction in geometry_wires:
        root.add(wire_or_junction)

    for decorative in decorative_objects:
        root.add(decorative)

    power_rail_names = (
        "+VIN", "+3V3", "+1V8", "+3V3_SC",
        "+VCCO_13", "+VCCO_33", "+VCCO_34", "+VCCO_35",
        "GND", "CHASSIS_GND",
    )
    power_rail_origin_x: float = snap_to_grid(5.0)
    power_rail_origin_y: float = snap_to_grid(20.0)
    power_rail_pitch_mm: float = 5.08
    for rail_index, rail_name in enumerate(power_rail_names):
        rail_position = Point(
            power_rail_origin_x,
            power_rail_origin_y + rail_index * power_rail_pitch_mm,
        )
        root.add(global_label(rail_name, rail_position))

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
