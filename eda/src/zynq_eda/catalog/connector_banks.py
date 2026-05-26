"""Generate per-bank sub-symbols from a parent high-pin-count connector.

A single 168-pin FX10A or 160-pin FMC LPC connector dropped onto one sheet
crams its pin labels into illegible density. The pragmatic fix used here is
to split the connector across multiple sub-sheets, each rendering a pin
subset (a "bank"). Each bank is a distinct KiCad symbol (e.g.
``FX10A_168P_J1A_MIO``) carved out of the parent's pin list — same pin
NAMES + NUMBERS as the parent (so the footprint mapping is preserved),
but only the bank's pins are drawn.

Multi-unit KiCad symbols would be the textbook solution; we use distinct
sub-symbols + a small BOM-emitter tweak instead (grouping by value+footprint
collapses the per-bank symbols to one BOM line per physical connector).

Generator output goes to ``shared/symbols/generated/connector_banks/``.
"""

from __future__ import annotations

from pathlib import Path

import sexpdata


def _is_token(item, name: str) -> bool:
    return isinstance(item, list) and item and getattr(item[0], "value", lambda: None)() == name


def _find_symbol(parsed, symbol_name: str):
    """Locate the ``(symbol "<symbol_name>" ...)`` block in a parsed .kicad_sym."""
    for top in parsed[1:]:
        if not isinstance(top, list) or not top:
            continue
        head = top[0]
        if getattr(head, "value", lambda: None)() != "symbol":
            continue
        if len(top) < 2:
            continue
        name = top[1]
        if isinstance(name, str) and name == symbol_name:
            return top
    return None


def _find_unit_subsymbol(parent_symbol_block, suffix: str = "_1_1"):
    """Find the ``(symbol "Parent_1_1" ...)`` block holding the pin definitions."""
    for item in parent_symbol_block[2:]:
        if not isinstance(item, list) or not item:
            continue
        head = item[0]
        if getattr(head, "value", lambda: None)() != "symbol":
            continue
        if len(item) < 2:
            continue
        name = item[1]
        if isinstance(name, str) and name.endswith(suffix):
            return item
    return None


def _find_unit_zero(parent_symbol_block):
    """Find the ``(symbol "Parent_0_1" ...)`` graphics-only block (body rectangle)."""
    for item in parent_symbol_block[2:]:
        if not isinstance(item, list) or not item:
            continue
        head = item[0]
        if getattr(head, "value", lambda: None)() != "symbol":
            continue
        if len(item) < 2:
            continue
        name = item[1]
        if isinstance(name, str) and name.endswith("_0_1"):
            return item
    return None


def _extract_pin_blocks(unit_subsymbol) -> list[list]:
    """Return every ``(pin ...)`` block inside the given _1_1 symbol unit."""
    pins: list[list] = []
    for item in unit_subsymbol[2:]:
        if not isinstance(item, list) or not item:
            continue
        if getattr(item[0], "value", lambda: None)() == "pin":
            pins.append(item)
    return pins


def _pin_number(pin_block) -> str:
    for item in pin_block[1:]:
        if not isinstance(item, list) or not item:
            continue
        if getattr(item[0], "value", lambda: None)() == "number":
            value = item[1] if len(item) > 1 else None
            if isinstance(value, str):
                return value
    return ""


def _pin_y(pin_block) -> float:
    """Y coordinate of the pin's tip (in symbol-local mm)."""
    for item in pin_block[1:]:
        if not isinstance(item, list) or not item:
            continue
        if getattr(item[0], "value", lambda: None)() == "at":
            if len(item) >= 3:
                try:
                    return float(item[2])
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def _hide_pin_name(pin_block, hide: bool) -> None:
    """Toggle (hide yes) inside the pin's (name ...) effects block."""
    for item in pin_block[1:]:
        if not isinstance(item, list) or not item:
            continue
        if getattr(item[0], "value", lambda: None)() != "name":
            continue
        # find (effects ...) inside the (name ...) block
        for subitem in item[1:]:
            if isinstance(subitem, list) and subitem \
               and getattr(subitem[0], "value", lambda: None)() == "effects":
                # find existing (hide ...) toggle; otherwise append.
                hide_token = sexpdata.Symbol("hide")
                yes_token = sexpdata.Symbol("yes") if hide else sexpdata.Symbol("no")
                for effect in subitem[1:]:
                    if isinstance(effect, list) and effect \
                       and getattr(effect[0], "value", lambda: None)() == "hide":
                        effect[1] = yes_token
                        break
                else:
                    subitem.append([hide_token, yes_token])
                return


def _set_pin_at(pin_block, x: float, y: float, rotation: float) -> None:
    for item in pin_block[1:]:
        if isinstance(item, list) and item \
           and getattr(item[0], "value", lambda: None)() == "at":
            # (at x y rot)
            if len(item) >= 4:
                item[1] = x
                item[2] = y
                item[3] = rotation
            return


def emit_bank_symbol(
    *,
    parent_lib_path: Path,
    parent_symbol_name: str,
    bank_symbol_name: str,
    pin_numbers: tuple[str, ...],
    output_path: Path,
    reference_prefix: str = "J",
    value_text: str = "",
    footprint: str = "",
    show_pin_names: bool = True,
    box_half_width: float = 5.08,
) -> Path:
    """Write a sub-symbol containing only the listed pin_numbers.

    The parent's per-pin pin NAMES and NUMBERS are preserved (so the
    footprint mapping is identical), but pins are re-laid in a compact
    two-column layout sized to the bank's pin count. Pins whose original
    x was negative go on the LEFT edge of the new body; positive-x pins
    go on the RIGHT edge.
    """
    text = parent_lib_path.read_text(encoding="utf-8")
    parsed = sexpdata.loads(text)

    parent_symbol = _find_symbol(parsed, parent_symbol_name)
    if parent_symbol is None:
        raise KeyError(f"Symbol {parent_symbol_name!r} not found in {parent_lib_path}")

    unit_block = _find_unit_subsymbol(parent_symbol)
    if unit_block is None:
        raise KeyError(f"_1_1 sub-unit not found in {parent_symbol_name!r}")

    pin_blocks = _extract_pin_blocks(unit_block)
    pin_set = set(pin_numbers)
    surviving = [p for p in pin_blocks if _pin_number(p) in pin_set]
    if not surviving:
        raise ValueError(
            f"emit_bank_symbol({bank_symbol_name!r}): no pin from "
            f"{sorted(pin_set)} matched any pin in {parent_symbol_name}"
        )

    missing = sorted(pin_set - {_pin_number(p) for p in surviving})
    if missing:
        raise ValueError(
            f"emit_bank_symbol({bank_symbol_name!r}): pins {missing!r} "
            f"not found in {parent_symbol_name}"
        )

    # Pin original side: negative-x → left side, positive-x → right side.
    def _orig_side(pin_block) -> str:
        for item in pin_block[1:]:
            if isinstance(item, list) and item \
               and getattr(item[0], "value", lambda: None)() == "at":
                if len(item) >= 4:
                    try:
                        x = float(item[1])
                    except (TypeError, ValueError):
                        return "left"
                    return "left" if x < 0 else "right"
        return "left"

    left_pins  = [p for p in surviving if _orig_side(p) == "left"]
    right_pins = [p for p in surviving if _orig_side(p) == "right"]
    left_pins.sort(key=_pin_y, reverse=True)
    right_pins.sort(key=_pin_y, reverse=True)

    # Pin pitch + body width tuned for VISIBLE pin names. At the default
    # 2.54 mm pitch, pin name text (e.g. "FMC_LA00_P", "ZYNQ_PS_MIO0")
    # at 1.27 mm font height ≈ 1.9 mm row + 1.5 mm intra-name kerning
    # crowds adjacent rows on KiCad's rendered PDF (the user's screenshot
    # showed rows visually stacked). Bumping pitch to 5.08 mm (2 KiCad
    # grid units) gives 3.18 mm clear vertical gap between text rows so
    # each pin's intrinsic name is readable on its own line. Body
    # half-width of 12.7 mm leaves room for the longest typical pin
    # name (~12 chars ≈ 9 mm) plus 3.7 mm padding inside the body.
    pitch = 5.08
    box_half_width = 12.7
    max_col = max(len(left_pins), len(right_pins), 1)
    box_height = max(5.08, (max_col + 1) * pitch)
    box_top = box_height / 2.0
    box_bottom = -box_height / 2.0

    left_x  = -box_half_width - 2.54  # pin tip 2.54 mm outside body (one stub)
    right_x =  box_half_width + 2.54
    cursor = box_top - pitch
    for pin in left_pins:
        # Left-side pins have rotation 0 (tip facing right, body to its right).
        _set_pin_at(pin, left_x, cursor, 0)
        _hide_pin_name(pin, hide=not show_pin_names)
        cursor -= pitch
    cursor = box_top - pitch
    for pin in right_pins:
        # Right-side pins have rotation 180 (tip faces left, body to its left).
        _set_pin_at(pin, right_x, cursor, 180)
        _hide_pin_name(pin, hide=not show_pin_names)
        cursor -= pitch

    new_pins = left_pins + right_pins
    sym = sexpdata.Symbol
    lib = [
        sym("kicad_symbol_lib"),
        [sym("version"), 20241209],
        [sym("generator"), "connector-bank-extractor"],
        [sym("generator_version"), "1.0"],
        [
            sym("symbol"),
            bank_symbol_name,
            [sym("pin_numbers"), [sym("hide"), sym("no")]],
            [sym("pin_names"),
             [sym("offset"), 1.016],
             [sym("hide"), sym("yes" if not show_pin_names else "no")]],
            [sym("exclude_from_sim"), sym("yes")],
            [sym("in_bom"), sym("yes")],
            [sym("on_board"), sym("yes")],
            [
                sym("property"),
                "Reference",
                reference_prefix,
                [sym("at"), 0, box_top + 2.54, 0],
                [sym("effects"), [sym("font"), [sym("size"), 1.27, 1.27]]],
            ],
            [
                sym("property"),
                "Value",
                value_text or bank_symbol_name,
                [sym("at"), 0, box_bottom - 2.54, 0],
                [sym("effects"), [sym("font"), [sym("size"), 1.27, 1.27]]],
            ],
            [
                sym("property"),
                "Footprint",
                footprint,
                [sym("at"), 0, 0, 0],
                [sym("effects"), [sym("font"), [sym("size"), 1.27, 1.27]], sym("hide")],
            ],
            [
                sym("symbol"),
                f"{bank_symbol_name}_0_1",
                [
                    sym("rectangle"),
                    [sym("start"), -box_half_width, box_top],
                    [sym("end"), box_half_width, box_bottom],
                    [sym("stroke"), [sym("width"), 0.254], [sym("type"), sym("default")]],
                    [sym("fill"), [sym("type"), sym("background")]],
                ],
            ],
            [sym("symbol"), f"{bank_symbol_name}_1_1", *new_pins],
            [sym("embedded_fonts"), sym("no")],
        ],
        [sym("embedded_fonts"), sym("no")],
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        sexpdata.dumps(lib, pretty_print=True, indent_as="\t"),
        encoding="utf-8",
    )
    return output_path.resolve()
