"""KiCad lib_symbols and symbol-instance emitters for the carrier generator.

Generic S-expression primitives (wire, junction, labels, text, sheet pins)
live in ``scripts.carrier.core.sexpr`` and are imported below for the
remaining call sites that still reference them by their old names.

The PlacedSymbol abstraction itself has moved to
``scripts.carrier.core.symbols`` (so it can carry its bounding box and
pin-position lookups alongside the SymbolDef registry); this module simply
re-exports it so existing imports from ``sheet_emitter`` keep working.
"""

from __future__ import annotations

from scripts.carrier.core.sexpr import (
    Keyword,
    SExp,
    at,
    effects,
    global_label,
    junction,
    local_label,
    property_,
    text_label,
    wire,
)
from scripts.carrier.core.symbols import (
    PlacedSymbol,
    SymbolDef,
    SymbolPin,
)

__all__ = [
    "PlacedSymbol",
    "SymbolDef",
    "SymbolPin",
    "build_lib_symbol_sexp",
    "build_symbol_instance_sexp",
    "global_label",
    "junction",
    "local_label",
    "text_label",
    "wire",
]


def build_lib_symbol_sexp(symbol: SymbolDef) -> SExp:
    """Convert a SymbolDef into a KiCad ``(symbol ...)`` library entry."""

    body = SExp("symbol", atoms=[symbol.lib_id])
    body.add(SExp("exclude_from_sim", atoms=[False]))
    body.add(SExp("in_bom", atoms=[True]))
    body.add(SExp("on_board", atoms=[True]))

    half_height_mm = symbol.height_mm() / 2
    body.add(property_("Reference", "U", x=0, y=half_height_mm + 1.27))
    body.add(property_("Value", symbol.lib_id.split(":", 1)[-1],
                       x=0, y=-half_height_mm - 1.27))
    body.add(property_("Footprint", "", x=0, y=0, hide=True))
    body.add(property_("Datasheet", "", x=0, y=0, hide=True))
    body.add(property_("Description", symbol.description, x=0, y=0, hide=True))

    sub = SExp("symbol", atoms=[f"{symbol.lib_id}_1_1"])
    left_x = 0.0
    right_x = symbol.width_mm
    top_y = half_height_mm
    bottom_y = -half_height_mm
    rect = SExp("rectangle")
    rect.add(SExp("start", atoms=[left_x, top_y]))
    rect.add(SExp("end", atoms=[right_x, bottom_y]))
    rect.add(
        SExp("stroke")
        .add(SExp("width", atoms=[0]))
        .add(SExp("type", atoms=[Keyword("default")]))
    )
    rect.add(SExp("fill").add(SExp("type", atoms=[Keyword("background")])))
    sub.add(rect)

    left_pins = [pin for pin in symbol.pins if pin.side == "L"]
    right_pins = [pin for pin in symbol.pins if pin.side == "R"]
    for index, pin in enumerate(left_pins):
        pin_y = top_y - (index + 1) * 2.54
        sub.add(_lib_pin_sexp(pin, x=left_x - 2.54, y=pin_y, angle=0))
    for index, pin in enumerate(right_pins):
        pin_y = top_y - (index + 1) * 2.54
        sub.add(_lib_pin_sexp(pin, x=right_x + 2.54, y=pin_y, angle=180))

    body.add(sub)
    body.add(SExp("embedded_fonts", atoms=[False]))
    return body


def _lib_pin_sexp(pin: SymbolPin, x: float, y: float, angle: int) -> SExp:
    body = SExp("pin", atoms=[Keyword(pin.electrical_type), Keyword("line")])
    body.add(at(x, y, angle))
    body.add(SExp("length", atoms=[2.54]))
    body.add(SExp("name", atoms=[pin.name]).add(effects()))
    body.add(SExp("number", atoms=[pin.number]).add(effects()))
    return body


def build_symbol_instance_sexp(
    placed: PlacedSymbol,
    schematic_uuid: str,
    project_name: str,
) -> SExp:
    """Emit a placed-symbol ``(symbol ...)`` instance with project path."""

    half_height_mm = placed.symbol.height_mm() / 2
    body = SExp("symbol")
    body.add(SExp("lib_id", atoms=[placed.symbol.lib_id]))
    body.add(at(placed.origin.x, placed.origin.y, 0))
    body.add(SExp("unit", atoms=[1]))
    body.add(SExp("exclude_from_sim", atoms=[False]))
    body.add(SExp("in_bom", atoms=[True]))
    body.add(SExp("on_board", atoms=[True]))
    body.add(SExp("dnp", atoms=[False]))
    body.add(SExp("fields_autoplaced", atoms=[True]))
    body.add(SExp("uuid", atoms=[placed.uuid]))
    body.add(property_(
        "Reference", placed.reference,
        x=placed.origin.x,
        y=placed.origin.y - half_height_mm - 2.54,
        font_size=1.524, bold=True, justify="left",
    ))
    body.add(property_(
        "Value", placed.value,
        x=placed.origin.x,
        y=placed.origin.y + half_height_mm + 1.27,
        font_size=1.27, justify="left",
    ))
    body.add(property_("Footprint", placed.footprint,
                       x=placed.origin.x, y=placed.origin.y, hide=True))
    body.add(property_("Datasheet", "",
                       x=placed.origin.x, y=placed.origin.y, hide=True))
    body.add(property_("Description", placed.symbol.description,
                       x=placed.origin.x, y=placed.origin.y, hide=True))
    for pin in placed.symbol.pins:
        pin_entry = SExp("pin", atoms=[pin.number])
        pin_entry.add(SExp("uuid", atoms=[placed.pin_uuids[pin.number]]))
        body.add(pin_entry)
    instances = SExp("instances")
    project = SExp("project", atoms=[project_name])
    path = SExp("path", atoms=[f"/{schematic_uuid}"])
    path.add(SExp("reference", atoms=[placed.reference]))
    path.add(SExp("unit", atoms=[1]))
    project.add(path)
    instances.add(project)
    body.add(instances)
    return body
