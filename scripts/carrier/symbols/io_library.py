"""Generate per-block IO connector symbols with one pin per carrier signal."""

from __future__ import annotations

from pathlib import Path


def _sanitize_pin_name(net_name: str) -> str:
    return (
        net_name.replace("/", "_")
        .replace("+", "P")
        .replace("-", "N")
        .replace(" ", "_")
    )


def emit_io_connector_symbol(
    *,
    symbol_name: str,
    pin_names: tuple[str, ...],
    output_path: Path,
) -> Path:
    """Write a KiCad symbol with passive pins named after carrier signals."""
    if not pin_names:
        raise ValueError(f"{symbol_name}: pin_names must not be empty")

    unique_pins = tuple(dict.fromkeys(pin_names))
    pin_count = len(unique_pins)
    box_height_mm = max(5.08, pin_count * 2.54)
    box_top = box_height_mm / 2.0
    box_bottom = -box_height_mm / 2.0

    lines: list[str] = [
        "(kicad_symbol_lib",
        "\t(version 20241209)",
        "\t(generator \"carrier-io-library\")",
        "\t(generator_version \"1.0\")",
        f'\t(symbol "{symbol_name}"',
        "\t\t(exclude_from_sim no)",
        "\t\t(in_bom yes)",
        "\t\t(on_board yes)",
        '\t\t(property "Reference" "J"',
        "\t\t\t(at 0 0 0)",
        "\t\t\t(effects (font (size 1.27 1.27)))",
        "\t\t)",
        f'\t\t(property "Value" "{symbol_name}"',
        f"\t\t\t(at 0 {box_bottom - 2.54:.2f} 0)",
        "\t\t\t(effects (font (size 1.27 1.27)))",
        "\t\t)",
        '\t\t(property "Footprint" ""',
        "\t\t\t(at 0 0 0)",
        "\t\t\t(effects (font (size 1.27 1.27)) hide)",
        "\t\t)",
        f'\t\t(symbol "{symbol_name}_0_1"',
        "\t\t\t(rectangle",
        f"\t\t\t\t(start -5.08 {box_top:.2f})",
        f"\t\t\t\t(end 5.08 {box_bottom:.2f})",
        "\t\t\t\t(stroke (width 0.254) (type default))",
        "\t\t\t\t(fill (type background))",
        "\t\t\t)",
        "\t\t)",
        f'\t\t(symbol "{symbol_name}_1_1"',
    ]

    cursor_y = box_top - 1.27
    hide_pin_names = pin_count > 6
    for index, pin_name in enumerate(unique_pins, start=1):
        safe_name = _sanitize_pin_name(pin_name)
        name_effects = (
            "\t\t\t\t\t(effects (font (size 1.27 1.27)) hide)"
            if hide_pin_names
            else "\t\t\t\t\t(effects (font (size 1.27 1.27)))"
        )
        lines.extend(
            [
                "\t\t\t(pin passive line",
                f"\t\t\t\t(at 5.08 {cursor_y:.2f} 180)",
                "\t\t\t\t(length 2.54)",
                f'\t\t\t\t(name "{safe_name}"',
                name_effects,
                "\t\t\t\t)",
                f'\t\t\t\t(number "{index}"',
                "\t\t\t\t\t(effects (font (size 1.27 1.27)))",
                "\t\t\t\t)",
                "\t\t\t)",
            ]
        )
        cursor_y -= 2.54

    lines.extend(
        [
            "\t\t)",
            "\t\t(embedded_fonts no)",
            "\t)",
            "\t(embedded_fonts no)",
            ")",
            "",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path.resolve()


def pin_name_for_carrier_signal(carrier_signal: str) -> str:
    return _sanitize_pin_name(carrier_signal)
