"""Emit reference_circuits.md - the EE-reviewable design intent record.

For every IC on the carrier, lists:
    - Datasheet citation
    - External parts required (with quantity)
    - Strap pin states
    - Layout notes (PCB rules)
    - Pins explicitly requiring nothing external
"""

from __future__ import annotations

from pathlib import Path

from scripts.carrier.registry.parts_registry import REGISTRY
from scripts.carrier.refcircuits import IC_INSTANCE_COUNT, REFCIRCUITS

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
OUTPUT_PATH = SCRIPTS_DIR / "carrier_template" / "reference_circuits.md"


def emit_refcircuits_md(output_path: Path = OUTPUT_PATH) -> int:
    lines: list[str] = []
    lines.append("# Carrier Reference Circuits")
    lines.append("")
    lines.append(
        "Auto-generated design intent record. For every IC on the carrier, this "
        "document shows the manufacturer reference circuit applied: every external "
        "part required by the datasheet, strap pin states, layout notes, and "
        "explicit no-external-required pins."
    )
    lines.append("")
    lines.append(
        "This document is reviewed by the EE before PCB tape-out to confirm the "
        "carrier design follows each IC's reference design."
    )
    lines.append("")
    lines.append("## Contents")
    lines.append("")
    for name in REFCIRCUITS:
        lines.append(f"- [{name}](#{_anchor(name)})")
    lines.append("")
    lines.append("---")
    lines.append("")

    for name, circuit in REFCIRCUITS.items():
        # Look up BOM entry
        part = None
        for p in REGISTRY.values():
            if p.lcsc == circuit.lcsc:
                part = p
                break

        count = IC_INSTANCE_COUNT.get(name, 0)
        anchor = _anchor(name)
        lines.append(f"## {circuit.part_mpn}")
        lines.append("")
        lines.append(f"- **Function**: {circuit.description}")
        lines.append(f"- **LCSC**: [{circuit.lcsc}](https://www.lcsc.com/product-detail/{circuit.lcsc}.html)")
        if part is not None:
            lines.append(f"- **Footprint**: `{circuit.footprint}` ({part.package})")
            lines.append(f"- **Stock at LCSC**: {part.stock_at_lcsc:,}")
            lines.append(f"- **Unit price**: ${part.unit_price_usd:.4f}")
        lines.append(f"- **Datasheet**: [{circuit.datasheet_revision}]({circuit.datasheet_url})")
        if circuit.local_datasheet_path:
            lines.append(
                f"- **Local PDF**: `{circuit.local_datasheet_path}` "
                f"({circuit.app_circuit_page})"
            )
        lines.append(f"- **Reference design citation**: {circuit.app_circuit_figure}")
        lines.append(f"- **Instances on carrier**: {count}")
        lines.append("")

        if circuit.external_parts:
            lines.append("### External parts required by datasheet")
            lines.append("")
            lines.append("| IC pin / net | Other side | Part token | Qty | Justification |")
            lines.append("|---|---|---|---|---|")
            for ext in circuit.external_parts:
                lines.append(
                    f"| `{ext.from_pin}` | `{ext.to_net}` | `{ext.part_token}` | "
                    f"{ext.quantity} | {ext.justification} |"
                )
            lines.append("")

        if circuit.strap_pins:
            lines.append("### Strap pin configuration")
            lines.append("")
            lines.append("| Pin | Tied to | Purpose | Justification |")
            lines.append("|---|---|---|---|")
            for strap in circuit.strap_pins:
                lines.append(
                    f"| `{strap.pin}` | `{strap.tied_to}` | {strap.purpose} | "
                    f"{strap.justification} |"
                )
            lines.append("")

        if circuit.no_external_required:
            lines.append("### Pins requiring no external components (per datasheet)")
            lines.append("")
            for pin in sorted(circuit.no_external_required):
                lines.append(f"- `{pin}`")
            lines.append("")

        if circuit.layout_notes:
            lines.append("### PCB layout notes (carry forward to PCB stage)")
            lines.append("")
            for note in circuit.layout_notes:
                marker = {"rule": "**RULE**", "guideline": "_guideline_", "info": "info"}[
                    note.severity
                ]
                cite = f" ({note.justification})" if note.justification else ""
                lines.append(f"- {marker}: {note.text}{cite}")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    total_ext = sum(
        c.total_external_count() * IC_INSTANCE_COUNT.get(n, 0)
        for n, c in REFCIRCUITS.items()
    )
    lines.append(f"- ICs with reference circuits: **{len(REFCIRCUITS)}**")
    lines.append(f"- Total IC instances on carrier: **{sum(IC_INSTANCE_COUNT.values())}**")
    lines.append(f"- Total external supporting parts (sum across all IC instances): **{total_ext}**")
    lines.append("")
    lines.append(
        "Every supporting part on this carrier traces back to a specific section/figure of "
        "an IC datasheet. Review this document before PCB tape-out to validate design intent."
    )
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(lines)


def _anchor(name: str) -> str:
    return name.lower().replace(" ", "-").replace(".", "").replace("/", "")


if __name__ == "__main__":
    n = emit_refcircuits_md()
    print(f"Wrote {OUTPUT_PATH} ({n} lines)")
