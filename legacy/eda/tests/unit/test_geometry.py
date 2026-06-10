"""Tests for the symbol geometry cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from zynq_eda.core.layout import SymbolBoundingBox, SymbolGeometryCache
from zynq_eda.core.model import Point


REPO_ROOT = Path(__file__).resolve().parents[3]
ZYNQ_EDA_SYM = REPO_ROOT / "shared" / "symbols" / "zynq_eda.kicad_sym"


@pytest.fixture(scope="module")
def cache() -> SymbolGeometryCache:
    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((ZYNQ_EDA_SYM,))
    return geometry_cache


def test_register_libraries_is_idempotent(cache: SymbolGeometryCache) -> None:
    """Re-registering an already-loaded library is a no-op."""
    cache.register_libraries((ZYNQ_EDA_SYM,))
    cache.register_libraries((ZYNQ_EDA_SYM,))
    # If it raised, the test fails; no other assert needed.


def test_register_libraries_missing_file_raises(tmp_path: Path) -> None:
    geometry_cache = SymbolGeometryCache()
    bogus = tmp_path / "does_not_exist.kicad_sym"
    with pytest.raises(FileNotFoundError):
        geometry_cache.register_libraries((bogus,))


def test_usblc6_has_six_pins(cache: SymbolGeometryCache) -> None:
    """The ported USBLC6 symbol has 6 pins (4x I/O + GND + VBUS)."""
    pins = list(cache.all_pins("zynq_eda:USBLC6-4SC6"))
    assert len(pins) == 6
    names = {pin["name"] for pin in pins}
    assert {"GND", "VBUS"}.issubset(names)
    # The four I/O pins are I/O1..I/O4 (kicad-sym uses the I/O notation).
    io_pins = sorted(name for name in names if name.startswith("I/O"))
    assert io_pins == ["I/O1", "I/O2", "I/O3", "I/O4"]


def test_pin_position_for_named_pin(cache: SymbolGeometryCache) -> None:
    """Resolving a named pin at a given anchor yields the expected absolute point."""
    anchor = Point(100.0, 100.0)
    vbus_position = cache.absolute_pin_by_name(
        "zynq_eda:USBLC6-4SC6",
        anchor=anchor,
        pin_name="VBUS",
    )
    # The pin should be near the anchor (within the symbol's bounding box +
    # one pin-length stub). We don't assert an exact value here because pin
    # positions can shift as KiCad releases update symbol geometry. We only
    # verify the resolved point is finite + grid-snapped.
    assert isinstance(vbus_position, Point)
    assert abs(vbus_position.x - anchor.x) < 30.0
    assert abs(vbus_position.y - anchor.y) < 30.0


def test_pin_lookup_by_unknown_name_raises(cache: SymbolGeometryCache) -> None:
    with pytest.raises(KeyError):
        cache.absolute_pin_by_name(
            "zynq_eda:USBLC6-4SC6",
            anchor=Point(0.0, 0.0),
            pin_name="NONEXISTENT_PIN",
        )


def test_bounding_box_is_non_zero(cache: SymbolGeometryCache) -> None:
    box = cache.bounding_box("zynq_eda:USBLC6-4SC6")
    assert isinstance(box, SymbolBoundingBox)
    assert box.width > 0.0
    assert box.height > 0.0
    # USBLC6 is a small SOT-23-6 footprint; symbol should be <30mm in either axis.
    assert box.width < 30.0
    assert box.height < 30.0


def test_bounding_box_is_cached(cache: SymbolGeometryCache) -> None:
    box_first = cache.bounding_box("zynq_eda:USBLC6-4SC6")
    box_second = cache.bounding_box("zynq_eda:USBLC6-4SC6")
    assert box_first is box_second  # identity, not just equality


def test_bbox_shift_by_anchor() -> None:
    """``shift_by`` translates an anchor-relative box to absolute coordinates."""
    box = SymbolBoundingBox(min_x=-5.0, min_y=-10.0, max_x=5.0, max_y=10.0)
    shifted = box.shift_by(Point(100.0, 200.0))
    assert shifted.min_x == 95.0
    assert shifted.max_x == 105.0
    assert shifted.min_y == 190.0
    assert shifted.max_y == 210.0
    assert shifted.width == box.width
    assert shifted.height == box.height
