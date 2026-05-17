"""Byte-exact format-preservation tests for sexpr emitters.

Each test renders a single emitter at a known position with a known
deterministic UUID and asserts the output matches the inline expected
string verbatim.

The deterministic UUID is provided by monkeypatching
``scripts.carrier.core.sexpr.make_uuid`` in the ``deterministic_uuid``
fixture below.
"""

from __future__ import annotations

import pytest

from scripts.carrier.core import sexpr
from scripts.carrier.core.sexpr import (
    Point,
    SExp,
    at,
    effects,
    global_label,
    hierarchical_label,
    junction,
    local_label,
    property_,
    sheet_pin,
    text_label,
    wire,
    xy,
)


ZERO_UUID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def deterministic_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sexpr, "make_uuid", lambda: ZERO_UUID)


class TestPrimitiveSExpRendering:
    def test_empty_atom_node(self) -> None:
        node = SExp("foo")
        assert node.dumps() == "(foo)"

    def test_atomic_node_with_int(self) -> None:
        node = SExp("version", atoms=[20250114])
        assert node.dumps() == "(version 20250114)"

    def test_atomic_node_with_float_uses_4_significant_digits(self) -> None:
        node = SExp("size", atoms=[1.27, 2.54])
        assert node.dumps() == "(size 1.27 2.54)"

    def test_atomic_node_with_string_quotes(self) -> None:
        node = SExp("paper", atoms=["A1"])
        assert node.dumps() == '(paper "A1")'

    def test_atomic_node_with_bool_renders_yes_no(self) -> None:
        assert SExp("hide", atoms=[True]).dumps() == "(hide yes)"
        assert SExp("hide", atoms=[False]).dumps() == "(hide no)"

    def test_nested_node_with_indent(self) -> None:
        outer = SExp("outer")
        outer.add(SExp("inner", atoms=[1]))
        assert outer.dumps() == "(outer\n\t(inner 1)\n)"

    def test_raw_passthrough_preserves_text_with_indent(self) -> None:
        raw = SExp.raw("(symbol \"foo\"\n  (pin 1)\n)")
        outer = SExp("kicad_sch")
        outer.add(raw)
        rendered = outer.dumps()
        assert rendered == (
            "(kicad_sch\n"
            "\t(symbol \"foo\"\n"
            "\t  (pin 1)\n"
            "\t)\n"
            ")"
        )


class TestAtAndXy:
    def test_at_with_point(self) -> None:
        assert at(Point(1.27, 2.54)).dumps() == "(at 1.27 2.54 0)"

    def test_at_with_floats_and_angle(self) -> None:
        assert at(1.27, 2.54, 90).dumps() == "(at 1.27 2.54 90)"

    def test_xy_with_point(self) -> None:
        assert xy(Point(1.27, 2.54)).dumps() == "(xy 1.27 2.54)"

    def test_xy_with_floats(self) -> None:
        assert xy(1.27, 2.54).dumps() == "(xy 1.27 2.54)"


class TestEffectsAndProperty:
    def test_effects_default(self) -> None:
        assert effects().dumps() == (
            "(effects\n"
            "\t(font\n"
            "\t\t(size 1.27 1.27)\n"
            "\t)\n"
            ")"
        )

    def test_effects_with_justify_and_bold(self) -> None:
        rendered = effects(justify="left", bold=True).dumps()
        assert "(bold yes)" in rendered
        assert "(justify left)" in rendered

    def test_effects_with_multi_keyword_justify(self) -> None:
        rendered = effects(justify="left bottom").dumps()
        assert "(justify left bottom)" in rendered

    def test_property_renders_at_and_effects(self) -> None:
        prop = property_("Reference", "U1", x=10.16, y=5.08, font_size=1.524, bold=True)
        rendered = prop.dumps()
        assert rendered.startswith('(property "Reference" "U1"')
        assert "(at 10.16 5.08 0)" in rendered
        assert "(size 1.524 1.524)" in rendered


class TestWireRendering:
    def test_wire_byte_exact(self, deterministic_uuid: None) -> None:
        rendered = wire(Point(0.0, 0.0), Point(2.54, 0.0)).dumps()
        expected = (
            "(wire\n"
            "\t(pts\n"
            "\t\t(xy 0 0)\n"
            "\t\t(xy 2.54 0)\n"
            "\t)\n"
            "\t(stroke\n"
            "\t\t(width 0)\n"
            "\t\t(type default)\n"
            "\t)\n"
            "\t(uuid \"00000000-0000-0000-0000-000000000000\")\n"
            ")"
        )
        assert rendered == expected

    def test_wire_off_grid_endpoint_raises(self) -> None:
        with pytest.raises(ValueError, match="not on .*mm grid"):
            wire(Point(0.0, 0.0), Point(2.5, 0.0))


class TestJunctionRendering:
    def test_junction_byte_exact(self, deterministic_uuid: None) -> None:
        rendered = junction(Point(2.54, 2.54)).dumps()
        expected = (
            "(junction\n"
            "\t(at 2.54 2.54 0)\n"
            "\t(diameter 0)\n"
            "\t(color 0 0 0 0)\n"
            "\t(uuid \"00000000-0000-0000-0000-000000000000\")\n"
            ")"
        )
        assert rendered == expected


class TestLocalLabelRendering:
    def test_local_label_byte_exact(self, deterministic_uuid: None) -> None:
        rendered = local_label("VOUT", Point(5.08, 2.54)).dumps()
        expected = (
            "(label \"VOUT\"\n"
            "\t(at 5.08 2.54 0)\n"
            "\t(effects\n"
            "\t\t(font\n"
            "\t\t\t(size 1.27 1.27)\n"
            "\t\t)\n"
            "\t\t(justify left)\n"
            "\t)\n"
            "\t(uuid \"00000000-0000-0000-0000-000000000000\")\n"
            ")"
        )
        assert rendered == expected



class TestGlobalLabelRendering:
    def test_global_label_byte_exact(self, deterministic_uuid: None) -> None:
        rendered = global_label("+3V3", Point(0.0, 0.0)).dumps()
        expected = (
            "(global_label \"+3V3\"\n"
            "\t(shape input)\n"
            "\t(at 0 0 0)\n"
            "\t(effects\n"
            "\t\t(font\n"
            "\t\t\t(size 1.27 1.27)\n"
            "\t\t)\n"
            "\t\t(justify left)\n"
            "\t)\n"
            "\t(uuid \"00000000-0000-0000-0000-000000000000\")\n"
            "\t(property \"Intersheetrefs\" \"\"\n"
            "\t\t(at 0 0 0)\n"
            "\t\t(effects\n"
            "\t\t\t(font\n"
            "\t\t\t\t(size 1.27 1.27)\n"
            "\t\t\t)\n"
            "\t\t\t(hide yes)\n"
            "\t\t)\n"
            "\t)\n"
            ")"
        )
        assert rendered == expected


class TestHierarchicalLabelRendering:
    def test_hierarchical_label_default_bidirectional_shape(
        self, deterministic_uuid: None,
    ) -> None:
        rendered = hierarchical_label("USB_DP", Point(0.0, 0.0)).dumps()
        assert '(hierarchical_label "USB_DP"' in rendered
        assert '(shape bidirectional)' in rendered

    def test_hierarchical_label_explicit_input_shape(
        self, deterministic_uuid: None,
    ) -> None:
        rendered = hierarchical_label(
            "CLK_IN", Point(0.0, 0.0), shape="input",
        ).dumps()
        assert '(shape input)' in rendered


class TestSheetPinRendering:
    def test_sheet_pin_byte_exact(self, deterministic_uuid: None) -> None:
        rendered = sheet_pin("USB_DP", Point(2.54, 2.54)).dumps()
        expected = (
            "(pin \"USB_DP\" bidirectional\n"
            "\t(at 2.54 2.54 0)\n"
            "\t(effects\n"
            "\t\t(font\n"
            "\t\t\t(size 1.27 1.27)\n"
            "\t\t)\n"
            "\t\t(justify left)\n"
            "\t)\n"
            "\t(uuid \"00000000-0000-0000-0000-000000000000\")\n"
            ")"
        )
        assert rendered == expected


class TestTextLabelRendering:
    def test_text_label_byte_exact(self, deterministic_uuid: None) -> None:
        rendered = text_label("Power Section", Point(0.0, 0.0)).dumps()
        expected = (
            "(text \"Power Section\"\n"
            "\t(at 0 0 0)\n"
            "\t(effects\n"
            "\t\t(font\n"
            "\t\t\t(size 2.54 2.54)\n"
            "\t\t\t(bold yes)\n"
            "\t\t)\n"
            "\t\t(justify left bottom)\n"
            "\t)\n"
            "\t(uuid \"00000000-0000-0000-0000-000000000000\")\n"
            ")"
        )
        assert rendered == expected
