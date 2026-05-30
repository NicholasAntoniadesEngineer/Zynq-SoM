"""Unit tests for plan_lane_widths (Phase 2 — anchor-relative lane widths).

Tests cover:
- Per-role width formulas (CLUSTER, EDGE_LABEL, LOCAL_LABEL, GND,
  POWER_SYMBOL, NC).
- The 27-char ZYNQ_FMC name → ~21.6 mm hier-label lane width assertion
  (this is the design's stress-case constant).
- PWR_FLAG synthetic-lane emission for input-power nets.
- Cross-block invariant: every non-zero-width PinSpec produces exactly
  one LaneAllocation.
"""

from __future__ import annotations

import pytest

from zynq_eda.core.layout.bbox import (
    DEFAULT_TEXT_SIZE_MM,
    DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO,
)
from zynq_eda.core.layout._constants import (
    FLG_BODY_EXTENT_MM,
    GND_SYMBOL_HALF_EXTENT_MM,
    HLABEL_ANCHOR_OFFSET_MM,
    PASSIVE_OFFSET_MM,
    PASSIVE_PITCH_MM,
    POWER_SYMBOL_OFFSET_MM,
    VISUAL_CLEARANCE_MM,
)
from zynq_eda.core.layout.plan import (
    LaneAllocation,
    PinSpec,
    _hlabel_text_width_mm,
    _input_pwr_flag_nets,
    _label_text_width_mm,
    _lane_kind_for_role,
    _lane_width_for_spec,
    plan_lane_widths,
    plan_pin_specs,
)
from zynq_eda.core.model.grid import Point


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(**overrides) -> PinSpec:
    base = dict(
        owner_kind="ic",
        owner_ref="U1",
        owner_lib_id="lib:Sym",
        pin_name="P1",
        pin_number="1",
        role="LOCAL_LABEL",
        net_name="N",
        page_side="right",
        pin_relative=Point(0.0, 0.0),
    )
    base.update(overrides)
    return PinSpec(**base)


def _carrier_blocks_and_geometry():
    from zynq_eda.core.layout.geometry import SymbolGeometryCache
    from zynq_eda.projects.carrier.board import (
        SHARED_SYMBOL_LIBRARIES,
        build_blocks,
    )
    cache = SymbolGeometryCache()
    cache.register_libraries(SHARED_SYMBOL_LIBRARIES)
    blocks = {b.name: b for b in build_blocks()}
    return blocks, cache


# ---------------------------------------------------------------------------
# Text-width predictions
# ---------------------------------------------------------------------------


def test_hlabel_text_width_adds_decoration_space():
    # Hier-label adds a trailing space (the arrow decoration) on top of
    # the faithful per-glyph width.
    from zynq_eda.core.layout.bbox import text_width
    assert _hlabel_text_width_mm("X") == pytest.approx(text_width("X "))


def test_label_text_width_no_decoration():
    from zynq_eda.core.layout.bbox import text_width
    assert _label_text_width_mm("ABC") == pytest.approx(text_width("ABC"))


def test_hlabel_text_width_27_char_stress_case():
    # The plan's stress case — a 27-char FMC lane net. With KiCad's
    # faithful per-glyph widths (mean ~1.0x the 1.27 mm size) it lands
    # around 28-32 mm; the exact value comes from the per-glyph table.
    from zynq_eda.core.layout.bbox import text_width
    name = "ZYNQ_FMC_LA00_P_2_LANE_2_RD"  # exactly 27 chars
    assert len(name) == 27
    width = _hlabel_text_width_mm(name)
    assert width == pytest.approx(text_width(name + " "))
    assert 26.0 <= width <= 34.0


# ---------------------------------------------------------------------------
# _lane_width_for_spec — per-role formula
# ---------------------------------------------------------------------------


def test_lane_width_cluster_one_slot():
    spec = _spec(
        role="CLUSTER", net_name="GND",
        cluster_slot_count=1, cluster_destinations=("GND",),
    )
    # LEFT/RIGHT pins include max stagger 4×10.16 mm.
    expected = (
        PASSIVE_OFFSET_MM
        + 0 * PASSIVE_PITCH_MM
        + 4 * 10.16
        + POWER_SYMBOL_OFFSET_MM
        + _hlabel_text_width_mm("GND")
    )
    assert _lane_width_for_spec(spec) == pytest.approx(expected)


def test_lane_width_cluster_multi_slot_uses_longest_dest():
    spec = _spec(
        role="CLUSTER", net_name="GND",
        cluster_slot_count=3,
        cluster_destinations=("GND", "+3V3", "VERY_LONG_DESTINATION_NAME"),
    )
    expected = (
        PASSIVE_OFFSET_MM
        + 2 * PASSIVE_PITCH_MM
        + 4 * 10.16  # max stagger for LEFT/RIGHT
        + POWER_SYMBOL_OFFSET_MM
        + _hlabel_text_width_mm("VERY_LONG_DESTINATION_NAME")
    )
    assert _lane_width_for_spec(spec) == pytest.approx(expected)


def test_lane_width_edge_label():
    spec = _spec(role="EDGE_LABEL", net_name="STM32_I2C2_SDA")
    expected = (
        HLABEL_ANCHOR_OFFSET_MM
        + _hlabel_text_width_mm("STM32_I2C2_SDA")
        + 2 * VISUAL_CLEARANCE_MM
    )
    assert _lane_width_for_spec(spec) == pytest.approx(expected)


def test_lane_width_local_label():
    spec = _spec(role="LOCAL_LABEL", net_name="FB")
    expected = (
        HLABEL_ANCHOR_OFFSET_MM
        + _label_text_width_mm("FB")
        + 2 * VISUAL_CLEARANCE_MM
    )
    assert _lane_width_for_spec(spec) == pytest.approx(expected)


def test_lane_width_gnd():
    spec = _spec(role="GND", net_name="GND")
    # GND symbol sits at the pin tip (no outboard offset); lane reserves
    # only the symbol body half-extent + visual clearance.
    expected = GND_SYMBOL_HALF_EXTENT_MM + 2 * VISUAL_CLEARANCE_MM
    assert _lane_width_for_spec(spec) == pytest.approx(expected)


def test_lane_width_power_symbol_zero():
    spec = _spec(role="POWER_SYMBOL", net_name="+3V3")
    assert _lane_width_for_spec(spec) == 0.0


def test_lane_width_nc_zero():
    spec = _spec(role="NC", net_name="")
    assert _lane_width_for_spec(spec) == 0.0


# ---------------------------------------------------------------------------
# _lane_kind_for_role
# ---------------------------------------------------------------------------


def test_lane_kind_mapping():
    assert _lane_kind_for_role("CLUSTER") == "cluster"
    assert _lane_kind_for_role("EDGE_LABEL") == "hier_label"
    assert _lane_kind_for_role("LOCAL_LABEL") == "local_label"
    assert _lane_kind_for_role("GND") == "gnd_symbol"
    assert _lane_kind_for_role("POWER_SYMBOL") == "power_symbol"
    assert _lane_kind_for_role("NC") == "nc"


# ---------------------------------------------------------------------------
# _input_pwr_flag_nets
# ---------------------------------------------------------------------------


def test_input_pwr_flag_nets_returns_known_inputs():
    blocks, _ = _carrier_blocks_and_geometry()
    # usb_pd should emit a PWR_FLAG for +VIN (the connector sources it).
    flags = _input_pwr_flag_nets(blocks["usb_pd"])
    assert "+VIN" in flags
    # CHASSIS_GND is also flagged (ground variant != "GND").
    assert "CHASSIS_GND" in flags
    # Canonical GND is NOT flagged (driven by power:GND).
    assert "GND" not in flags


def test_input_pwr_flag_nets_power_block_outputs_no_driver_match():
    blocks, _ = _carrier_blocks_and_geometry()
    # power block: output nets like +3V3 have an IC driver
    # (TLV757P's power_output_net="+3V3"), so they should NOT need a
    # PWR_FLAG.
    flags = _input_pwr_flag_nets(blocks["power"])
    # +3V3 has a driver → not flagged.
    assert "+3V3" not in flags


# ---------------------------------------------------------------------------
# plan_lane_widths integration
# ---------------------------------------------------------------------------


def test_plan_lane_widths_one_lane_per_nonzero_pin():
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        specs = plan_pin_specs(block, geometry)
        lanes = plan_lane_widths(specs, block, geometry)

        # Every CLUSTER / GND / EDGE_LABEL / LOCAL_LABEL pin → one lane.
        per_pin_specs = [
            s for s in specs
            if s.role in ("CLUSTER", "GND", "EDGE_LABEL", "LOCAL_LABEL")
        ]
        per_pin_lanes = [l for l in lanes if l.lane_kind != "pwr_flag"]
        assert len(per_pin_lanes) == len(per_pin_specs), (
            f"block {block_name}: {len(per_pin_specs)} non-zero-width "
            f"pin specs but {len(per_pin_lanes)} non-pwr_flag lanes"
        )

        # NC / POWER_SYMBOL pins → no lane.
        nc_pwr_count = sum(
            1 for s in specs if s.role in ("NC", "POWER_SYMBOL")
        )
        # PWR_FLAG lanes count matches the input-net selector.
        pwr_flag_lanes = [l for l in lanes if l.lane_kind == "pwr_flag"]
        assert len(pwr_flag_lanes) == len(_input_pwr_flag_nets(block))

        # Sanity: lane widths are non-negative.
        for lane in lanes:
            assert lane.width_mm >= 0


def test_plan_lane_widths_pwr_flag_lane_owned_by_block():
    """PWR_FLAG synthetic lanes are owned by the block (not an IC or
    connector) and named ``pwr_flag:<net>``."""
    blocks, geometry = _carrier_blocks_and_geometry()
    block = blocks["usb_pd"]
    specs = plan_pin_specs(block, geometry)
    lanes = plan_lane_widths(specs, block, geometry)
    pwr_flag_lanes = [l for l in lanes if l.lane_kind == "pwr_flag"]
    assert pwr_flag_lanes
    for lane in pwr_flag_lanes:
        assert lane.owner_ref == block.name
        assert lane.pin_name.startswith("pwr_flag:")


def test_plan_lane_widths_row_index_unset():
    """Phase 2 produces lanes with row_index = -1 (unset). Phase 3
    will assign row indices via the row-packer."""
    blocks, geometry = _carrier_blocks_and_geometry()
    block = blocks["power"]
    lanes = plan_lane_widths(
        plan_pin_specs(block, geometry), block, geometry,
    )
    for lane in lanes:
        assert lane.row_index == -1
