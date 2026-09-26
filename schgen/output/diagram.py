"""Transitional transport for the native block-diagram renderer."""
from dataclasses import asdict
from pathlib import Path
from schgen.core import native


def render(link_result, som_nets, out: Path) -> Path:
    raw = {
        "sheets": [sheet.name for sheet in link_result.sheets],
        "bindings": [asdict(binding) for binding in link_result.bindings],
        "rail_bindings": link_result.rail_bindings,
        "errors": link_result.errors,
        "warnings": link_result.warnings,
        "unbound_som": link_result.unbound_som,
        "deferred": link_result.deferred,
    }
    return Path(native.module().block_diagram_write(raw, som_nets, str(out)))
