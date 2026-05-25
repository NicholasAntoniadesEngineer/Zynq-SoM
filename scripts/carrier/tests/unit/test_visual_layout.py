"""Visual layout invariants for schematic appearance."""

from __future__ import annotations

from collections import defaultdict

from scripts.carrier.blocks import all_block_factories
from scripts.carrier.blocks._block_common import INTERIOR_MARGIN_MM
from scripts.carrier.sheets.layout import pack_sheet_placements


def _min_label_y(block) -> float | None:
    label_positions = [
        hierarchical_pin.label_position
        for hierarchical_pin in block.hierarchical_pins
        if hierarchical_pin.label_position is not None
    ]
    if not label_positions:
        return None
    return min(label_point.y for label_point in label_positions)


def test_hier_edge_matches_label_y() -> None:
    for block_name, factory in all_block_factories().items():
        block = factory()
        min_label_y = _min_label_y(block)
        if min_label_y is None:
            continue
        for hierarchical_pin in block.hierarchical_pins:
            label_point = hierarchical_pin.label_position
            if label_point is None:
                continue
            expected_edge = label_point.y - min_label_y + INTERIOR_MARGIN_MM
            assert abs(hierarchical_pin.position_along_edge - expected_edge) < 0.02, (
                f"{block_name}: {hierarchical_pin.net_name!r} "
                f"position_along_edge {hierarchical_pin.position_along_edge} "
                f"!= expected {expected_edge}"
            )


def test_root_pin_order_matches_labels() -> None:
    built_blocks = {name: factory() for name, factory in all_block_factories().items()}
    for placement in pack_sheet_placements(built_blocks):
        block = built_blocks[placement.block_name]
        label_positions = [
            hierarchical_pin.label_position
            for hierarchical_pin in block.hierarchical_pins
            if hierarchical_pin.label_position is not None
        ]
        if len(label_positions) < 2:
            continue
        root_pin_ys = sorted(
            placement.origin.y + hierarchical_pin.position_along_edge
            for hierarchical_pin in block.hierarchical_pins
        )
        label_ys = sorted(label_point.y for label_point in label_positions)
        min_label = min(label_ys)
        expected_root_ys = sorted(
            placement.origin.y + (label_y - min_label + INTERIOR_MARGIN_MM)
            for label_y in label_ys
        )
        assert all(
            abs(actual - expected) < 0.02
            for actual, expected in zip(root_pin_ys, expected_root_ys, strict=True)
        ), (
            f"{placement.block_name}: root pin Y order does not match label Y order"
        )


def test_som_uses_single_route_bus() -> None:
    """SoM uses one routing bus, not per-net channel columns."""
    block = all_block_factories()["som_j3"]()
    vertical_x_values = {
        wire.start.x
        for wire in block.wires
        if abs(wire.start.x - wire.end.x) < 0.01
    }
    assert len(vertical_x_values) <= 2, (
        f"som_j3: expected one route bus, found vertical spines at {vertical_x_values}"
    )


def test_hdmi_no_colinear_bypass() -> None:
    block = all_block_factories()["hdmi_tx"]()
    for wire in block.wires:
        if abs(wire.start.y - wire.end.y) >= 0.01:
            continue
        min_x = min(wire.start.x, wire.end.x)
        max_x = max(wire.start.x, wire.end.x)
        if min_x < 80.0 and max_x > 250.0:
            raise AssertionError(
                "hdmi_tx: colinear wire spans IO region to hier edge without jog"
            )


def test_merged_sections_grouped_y() -> None:
    block = all_block_factories()["jtag_swd"]()
    zynq_ys = sorted(
        hierarchical_pin.label_position.y
        for hierarchical_pin in block.hierarchical_pins
        if hierarchical_pin.net_name.startswith("ZYNQ_")
        and hierarchical_pin.label_position is not None
    )
    gpio_ys = sorted(
        hierarchical_pin.label_position.y
        for hierarchical_pin in block.hierarchical_pins
        if hierarchical_pin.net_name.startswith("STM32_GPIO")
        and hierarchical_pin.label_position is not None
    )
    if zynq_ys and gpio_ys:
        assert max(zynq_ys) < min(gpio_ys) or max(gpio_ys) < min(zynq_ys), (
            "jtag_swd: ZYNQ and STM32_GPIO hier labels are interleaved"
        )


def test_all_hier_labels_wired() -> None:
    for block_name, factory in all_block_factories().items():
        block = factory()
        wire_endpoints = {
            (wire.start.x, wire.start.y) for wire in block.wires
        } | {
            (wire.end.x, wire.end.y) for wire in block.wires
        }
        for hierarchical_pin in block.hierarchical_pins:
            label_point = hierarchical_pin.label_position
            if label_point is None:
                continue
            assert (label_point.x, label_point.y) in wire_endpoints, (
                f"{block_name}: hier pin {hierarchical_pin.net_name!r} is unwired"
            )
