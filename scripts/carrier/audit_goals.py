"""Audit carrier implementation against original plan goals."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.carrier.blocks import BLOCK_FACTORIES, all_block_factories
from scripts.carrier.blocks._block_common import INTERIOR_MARGIN_MM
from scripts.carrier.model.block import Block
from scripts.carrier.datasheets.fetch_datasheets import (
    CARRIER_DIR,
    _is_acceptable_datasheet_pdf,
    collect_datasheet_entries,
)
from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.sheets.layout import A1_HEIGHT_MM, A1_PAGE_MARGIN_MM, A1_WIDTH_MM, pack_sheet_placements, sheet_symbol_size
from scripts.carrier.validate.canonical.registry import CANONICAL_VALIDATORS
from scripts.carrier.validate.canonical import run_canonical_validation
from scripts.carrier.validate.refcircuit import run_refcircuit_validation


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parent
BLOCKS_DIR = SCRIPTS_DIR / "carrier" / "blocks"
PIPELINE_PATH = SCRIPTS_DIR / "carrier" / "pipeline.py"

MIN_WIRE_COUNTS: dict[str, int] = {
    "usb_pd": 50,
    "som_j1": 100,
    "som_j2": 100,
    "som_j3": 100,
}


def _check_hier_pins_wired() -> list[str]:
    """Every hierarchical pin must sit on a wire endpoint."""
    failures: list[str] = []
    for name, factory in all_block_factories().items():
        block = factory()
        wire_endpoints: set[tuple[float, float]] = set()
        for wire in block.wires:
            wire_endpoints.add((wire.start.x, wire.start.y))
            wire_endpoints.add((wire.end.x, wire.end.y))
        for hierarchical_pin in block.hierarchical_pins:
            label_point = hierarchical_pin.label_position
            if label_point is None:
                failures.append(
                    f"{name}: hierarchical pin {hierarchical_pin.net_name!r} "
                    "missing label_position"
                )
                continue
            if (label_point.x, label_point.y) not in wire_endpoints:
                failures.append(
                    f"{name}: unwired hierarchical pin {hierarchical_pin.net_name!r}"
                )
    return failures


def _check_legacy_deleted() -> list[str]:
    failures: list[str] = []
    legacy = [
        SCRIPTS_DIR / "carrier" / "generator.py",
        SCRIPTS_DIR / "carrier" / "sheet_emitter.py",
        SCRIPTS_DIR / "carrier" / "blocks" / "placeholder.py",
        SCRIPTS_DIR / "carrier" / "blocks" / "_section_builder.py",
        SCRIPTS_DIR / "carrier" / "blocks" / "_connector_block.py",
    ]
    for path in legacy:
        if path.exists():
            failures.append(f"legacy still exists: {path.relative_to(REPO_ROOT)}")
    return failures


def _check_pipeline_erc() -> list[str]:
    failures: list[str] = []
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    if "skip_erc=True" in source:
        failures.append("pipeline.py hardcodes skip_erc=True in run_all()")
    return failures


def _check_no_section_builder_imports() -> list[str]:
    failures: list[str] = []
    for block_path in BLOCKS_DIR.glob("*.py"):
        if block_path.name.startswith("_"):
            continue
        source = block_path.read_text(encoding="utf-8")
        if "_section_builder" in source or "build_refcircuit_section" in source:
            failures.append(
                f"{block_path.name} still imports build_refcircuit_section"
            )
    return failures


def _check_canonical_registry() -> list[str]:
    failures: list[str] = []
    missing = set(REFCIRCUITS.keys()) - set(CANONICAL_VALIDATORS.keys())
    extra = set(CANONICAL_VALIDATORS.keys()) - set(REFCIRCUITS.keys())
    if missing:
        failures.append(f"canonical registry missing: {sorted(missing)}")
    if extra:
        failures.append(f"canonical registry extra: {sorted(extra)}")
    return failures


def _check_blocks() -> list[str]:
    failures: list[str] = []
    expected = {
        "som_j1", "som_j2", "som_j3",
        "usb_pd", "power", "power_mon", "aux_io", "usbc_otg", "uart_bridge",
        "jtag_swd", "boot_switches", "ethernet", "microsd", "hdmi_tx", "hdmi_rx",
        "lvds_lcd", "mipi_camera", "fmc_lpc", "pmod", "xadc_clk",
    }
    actual = set(BLOCK_FACTORIES.keys())
    missing = expected - actual
    extra = actual - expected
    if missing:
        failures.append(f"missing block factories: {sorted(missing)}")
    if extra:
        failures.append(f"unexpected block factories: {sorted(extra)}")
    for name, factory in all_block_factories().items():
        block = factory()
        if len(block.components) == 0:
            failures.append(f"{name}: zero components")
        if len(block.wires) == 0:
            failures.append(f"{name}: zero wires")
        if "carrier:BLOCK" in str(block.components):
            failures.append(f"{name}: uses carrier:BLOCK")
        min_wires = MIN_WIRE_COUNTS.get(name)
        if min_wires is not None and len(block.wires) < min_wires:
            failures.append(
                f"{name}: wire count {len(block.wires)} < minimum {min_wires}"
            )
    return failures


def _check_hier_pin_layout(blocks: dict[str, Block]) -> list[str]:
    """Hier pin metadata must fit sheet symbols and avoid duplicate positions."""
    failures: list[str] = []
    for block_name, block in blocks.items():
        if block_name.startswith("som_j"):
            continue
        seen_positions: dict[tuple[float, float], str] = {}
        for hierarchical_pin in block.hierarchical_pins:
            if hierarchical_pin.label_position is None:
                continue
            label_point = hierarchical_pin.label_position
            position_key = (label_point.x, label_point.y)
            existing_net = seen_positions.get(position_key)
            if existing_net is not None and existing_net != hierarchical_pin.net_name:
                failures.append(
                    f"{block_name}: duplicate hier label position "
                    f"{position_key} for {existing_net!r} and "
                    f"{hierarchical_pin.net_name!r}"
                )
            seen_positions[position_key] = hierarchical_pin.net_name

        _, sheet_height = sheet_symbol_size(block)
        for hierarchical_pin in block.hierarchical_pins:
            if hierarchical_pin.position_along_edge > sheet_height + 0.01:
                failures.append(
                    f"{block_name}: {hierarchical_pin.net_name!r} "
                    f"position_along_edge {hierarchical_pin.position_along_edge} "
                    f"> sheet height {sheet_height}"
                )
    return failures


def _check_som_positive_coords(blocks: dict[str, Block]) -> list[str]:
    failures: list[str] = []
    for block_name, block in blocks.items():
        if not block_name.startswith("som_j"):
            continue
        for hierarchical_pin in block.hierarchical_pins:
            label_point = hierarchical_pin.label_position
            if label_point is None:
                continue
            if label_point.y < 0.0:
                failures.append(
                    f"{block_name}: hier pin {hierarchical_pin.net_name!r} "
                    f"has negative Y {label_point.y}"
                )
        for wire in block.wires:
            for point in (wire.start, wire.end):
                if point.y < 0.0:
                    failures.append(
                        f"{block_name}: wire endpoint at negative Y {point.y}"
                    )
                    break
    return failures


def _check_root_sheet_bounds(blocks: dict[str, Block]) -> list[str]:
    failures: list[str] = []
    max_y = A1_HEIGHT_MM - A1_PAGE_MARGIN_MM
    max_x = A1_WIDTH_MM - A1_PAGE_MARGIN_MM
    for placement in pack_sheet_placements(blocks):
        bottom_edge = placement.origin.y + placement.height_mm
        right_edge = placement.origin.x + placement.width_mm
        if bottom_edge > max_y + 0.01:
            failures.append(
                f"root placement {placement.block_name!r} extends to "
                f"y={bottom_edge:.2f} (max {max_y:.2f})"
            )
        if right_edge > max_x + 0.01:
            failures.append(
                f"root placement {placement.block_name!r} extends to "
                f"x={right_edge:.2f} (max {max_x:.2f})"
            )
    return failures


def _check_hier_edge_label_consistency(blocks: dict[str, Block]) -> list[str]:
    failures: list[str] = []
    for block_name, block in blocks.items():
        label_positions = [
            hierarchical_pin.label_position
            for hierarchical_pin in block.hierarchical_pins
            if hierarchical_pin.label_position is not None
        ]
        if not label_positions:
            continue
        min_label_y = min(label_point.y for label_point in label_positions)
        for hierarchical_pin in block.hierarchical_pins:
            label_point = hierarchical_pin.label_position
            if label_point is None:
                continue
            expected_edge = label_point.y - min_label_y + INTERIOR_MARGIN_MM
            if abs(hierarchical_pin.position_along_edge - expected_edge) > 0.02:
                failures.append(
                    f"{block_name}: {hierarchical_pin.net_name!r} "
                    f"position_along_edge {hierarchical_pin.position_along_edge:.2f} "
                    f"!= label-derived {expected_edge:.2f}"
                )
    return failures


def _check_visual_routing(blocks: dict[str, Block]) -> list[str]:
    failures: list[str] = []
    som_block = blocks.get("som_j3")
    if som_block is not None:
        vertical_x_values = {
            wire.start.x
            for wire in som_block.wires
            if abs(wire.start.x - wire.end.x) < 0.01
        }
        if len(vertical_x_values) > 2:
            failures.append(
                f"som_j3: expected one route bus, found spines at {sorted(vertical_x_values)}"
            )

    hdmi_block = blocks.get("hdmi_tx")
    if hdmi_block is not None:
        for wire in hdmi_block.wires:
            if abs(wire.start.y - wire.end.y) >= 0.01:
                continue
            min_x = min(wire.start.x, wire.end.x)
            max_x = max(wire.start.x, wire.end.x)
            if min_x < 80.0 and max_x > 250.0:
                failures.append(
                    "hdmi_tx: colinear wire spans IO to hier without visible jog"
                )
                break

    return failures


def _check_refcircuits() -> list[str]:
    failures: list[str] = []
    if len(REFCIRCUITS) < 29:
        failures.append(f"REFCIRCUITS count {len(REFCIRCUITS)} < 29")
    for key, rc in REFCIRCUITS.items():
        if not rc.minimum_circuit_verified:
            failures.append(f"{key}: minimum_circuit_verified=False")
        if not rc.local_datasheet_path:
            failures.append(f"{key}: no local_datasheet_path")
        if not rc.app_circuit_page:
            failures.append(f"{key}: no app_circuit_page")
        for ext in rc.external_parts:
            if not ext.justification:
                failures.append(f"{key}: {ext.part_token} missing justification")
    datasheets_dir = CARRIER_DIR / "datasheets"
    for entry in collect_datasheet_entries():
        pdf_path = datasheets_dir / entry.local_filename
        if not pdf_path.exists():
            failures.append(f"datasheet missing: {entry.part_mpn}")
        elif not _is_acceptable_datasheet_pdf(pdf_path.read_bytes()):
            failures.append(f"datasheet invalid: {entry.part_mpn}")
    return failures


def _check_validation() -> list[str]:
    failures: list[str] = []
    for result in run_canonical_validation() + run_refcircuit_validation():
        if result.severity == "error":
            failures.append(f"{result.rule_id}: {result.message}")
    return failures


def main() -> int:
    built_blocks = {
        name: factory()
        for name, factory in all_block_factories().items()
    }
    sections: list[tuple[str, list[str]]] = [
        ("Legacy removed", _check_legacy_deleted()),
        ("Pipeline ERC gate", _check_pipeline_erc()),
        ("No section_builder imports", _check_no_section_builder_imports()),
        ("Canonical registry (29)", _check_canonical_registry()),
        ("20 block factories", _check_blocks()),
        ("Hierarchical pins wired", _check_hier_pins_wired()),
        ("Hier pin layout metadata", _check_hier_pin_layout(built_blocks)),
        ("Hier edge/label consistency", _check_hier_edge_label_consistency(built_blocks)),
        ("Visual routing checks", _check_visual_routing(built_blocks)),
        ("Root sheet A1 bounds", _check_root_sheet_bounds(built_blocks)),
        ("SoM positive coordinates", _check_som_positive_coords(built_blocks)),
        ("29 refcircuits + PDFs", _check_refcircuits()),
        ("Validation rules", _check_validation()),
    ]
    total_fail = 0
    for title, failures in sections:
        status = "PASS" if not failures else "FAIL"
        print(f"\n## {title}: {status}")
        if failures:
            total_fail += len(failures)
            for item in failures[:20]:
                print(f"  - {item}")
            if len(failures) > 20:
                print(f"  ... and {len(failures) - 20} more")
    print(f"\nTotal audit failures: {total_fail}")
    return 1 if total_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
