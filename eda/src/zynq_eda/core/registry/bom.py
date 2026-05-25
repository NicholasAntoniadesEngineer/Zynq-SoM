"""BOM CSV emitter.

Walks every :class:`PlacedSymbol` across all block sub-sheets and the root
sheet, aggregates by ``(lib_id, value, footprint)``, and writes a CSV with
one row per unique part. References are merged into a comma-separated list.

Symbols whose ``lib_id`` starts with ``power:`` are skipped — those are
KiCad's hierarchical-power markers, not real BOM items.

Parts-catalog lookup is keyed on the symbol ``value`` field. The catalog
maps a part token (e.g. ``"100n_0402_X7R"``) to a :class:`BOMPart` with
``lcsc`` / ``mpn`` / ``description`` / ``datasheet_url``. The placement
engine writes the catalog's ``value`` (e.g. ``"100n"``) into the symbol,
so we secondary-index the catalog by ``value`` + ``footprint`` to recover
the LCSC/MPN. If a value+footprint pair doesn't resolve, ``"?"`` is
written for LCSC/MPN rather than crashing — keeps the pipeline robust to
parts the catalog doesn't yet know about.
"""

from __future__ import annotations

import csv
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from zynq_eda.core.model.block import Block
from zynq_eda.core.model.sheet import PlacedSymbol, Sheet


_POWER_LIB_PREFIX = "power:"


def _natural_ref_key(ref: str) -> tuple[str, int, str]:
    """Sort references like ``C100, C2, C10`` → ``C2, C10, C100``."""
    prefix = "".join(c for c in ref if c.isalpha())
    digits = "".join(c for c in ref if c.isdigit())
    suffix = ref[len(prefix) + len(digits):]
    return prefix, int(digits) if digits else 0, suffix


def _collect_symbols(
    *,
    blocks: list[Block],
    root_sheet: Sheet,
    sub_sheets: list[Sheet],
) -> Iterable[tuple[Block | None, PlacedSymbol]]:
    """Yield ``(owning_block, symbol)`` pairs across every sheet.

    ``owning_block`` is ``None`` for symbols on the root sheet
    (cross-block power drivers).
    """
    for block, sheet in zip(blocks, sub_sheets, strict=True):
        for sym in sheet.symbols:
            yield block, sym
    for sym in root_sheet.symbols:
        yield None, sym


def _build_catalog_indexes(
    parts_catalog,
) -> tuple[dict[tuple[str, str], object], dict[tuple[str, str], object]]:
    """Build two secondary indexes over the parts catalog.

    The catalog's primary key is the part token; placed symbols don't
    carry the token (only ``value`` + ``footprint``), so we build:

      * ``by_value_footprint``: ``(value, footprint)`` → part. Matches
        most passives + ICs (the placer copies the catalog's ``value``
        into the symbol).
      * ``by_mpn_footprint``: ``(mpn, footprint)`` → part. Fallback for
        connectors and other items whose placed-symbol value is the
        refcircuit's ``part_mpn`` rather than the catalog's value.

    First-wins on duplicates — duplicate (value, footprint) or
    (mpn, footprint) pairs in the catalog would already be a registry bug.
    """
    by_value_footprint: dict[tuple[str, str], object] = {}
    by_mpn_footprint: dict[tuple[str, str], object] = {}
    if parts_catalog is None:
        return by_value_footprint, by_mpn_footprint
    try:
        parts = parts_catalog.all_parts()
    except AttributeError:
        parts = list(parts_catalog.values()) if hasattr(parts_catalog, "values") else []
    for part in parts:
        by_value_footprint.setdefault((part.value, part.footprint), part)
        by_mpn_footprint.setdefault((part.mpn, part.footprint), part)
    return by_value_footprint, by_mpn_footprint


def _lookup_part(
    *,
    value: str,
    footprint: str,
    by_value_footprint: dict[tuple[str, str], object],
    by_mpn_footprint: dict[tuple[str, str], object],
):
    """Resolve the catalog entry for a placed symbol, or ``None``."""
    part = by_value_footprint.get((value, footprint))
    if part is not None:
        return part
    return by_mpn_footprint.get((value, footprint))


def emit_bom(
    *,
    blocks: list[Block],
    root_sheet: Sheet,
    sub_sheets: list[Sheet],
    parts_catalog,
    output_path: Path,
) -> None:
    """Aggregate every PlacedSymbol across blocks + root → CSV.

    Args:
        blocks: The carrier's blocks, in the same order as ``sub_sheets``.
        root_sheet: The root index :class:`Sheet`.
        sub_sheets: One placed :class:`Sheet` per block (parallel to ``blocks``).
        parts_catalog: Catalog exposing either ``.all_parts()`` or a dict
            mapping tokens → ``BOMPart``. Used to resolve LCSC / MPN /
            datasheet URL / description from the symbol's value + footprint.
        output_path: Where to write the BOM CSV. Atomic write via tempfile.
    """
    if output_path.suffix != ".csv":
        raise ValueError(f"output_path must end in .csv, got {output_path}")

    by_value_footprint, by_mpn_footprint = _build_catalog_indexes(parts_catalog)

    # Aggregate: (lib_id, value, footprint) → list of references
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    seen_refs: set[tuple[tuple[str, str, str], str]] = set()
    for _block, sym in _collect_symbols(
        blocks=blocks, root_sheet=root_sheet, sub_sheets=sub_sheets,
    ):
        if sym.lib_id.startswith(_POWER_LIB_PREFIX):
            continue
        key = (sym.lib_id, sym.value, sym.footprint)
        # Same reference can legitimately appear once per sheet — but if a
        # block reuses U1 on both power and usb_pd, that's already validated
        # as distinct designators upstream. Dedupe defensively here.
        ref_key = (key, sym.reference)
        if ref_key in seen_refs:
            continue
        seen_refs.add(ref_key)
        groups[key].append(sym.reference)

    rows: list[dict[str, str]] = []
    for (lib_id, value, footprint), refs in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]),
    ):
        refs_sorted = sorted(refs, key=_natural_ref_key)
        part = _lookup_part(
            value=value,
            footprint=footprint,
            by_value_footprint=by_value_footprint,
            by_mpn_footprint=by_mpn_footprint,
        )
        rows.append({
            "Reference": ", ".join(refs_sorted),
            "Qty": str(len(refs_sorted)),
            "Value": value,
            "Footprint": footprint,
            "LCSC": part.lcsc if part is not None else "?",
            "MPN": part.mpn if part is not None else "?",
            "Description": part.description if part is not None else "",
            "Datasheet": part.datasheet_url if part is not None else "",
        })

    _atomic_write_csv(
        output_path=output_path,
        fieldnames=[
            "Reference", "Qty", "Value", "Footprint",
            "LCSC", "MPN", "Description", "Datasheet",
        ],
        rows=rows,
    )


def _atomic_write_csv(
    *,
    output_path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    """Write a CSV file via tempfile + os.replace (atomic on POSIX)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(
        prefix=output_path.stem + ".",
        suffix=output_path.suffix + ".tmp",
        dir=str(output_path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_path_str)
    try:
        with temp_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
