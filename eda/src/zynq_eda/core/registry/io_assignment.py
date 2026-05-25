"""IO-assignment CSV emitter.

For every :class:`ConnectorInstance` on every block, one row per
``(pin_id, net_name)`` is written. This is the connector-pin → carrier-net
contract: layout review reads this CSV to confirm pin assignments match
the carrier's interface plan (USB-C VBUS to +VIN, HDMI TMDS to the right
lanes on the right bank, etc.).
"""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

from zynq_eda.core.model.block import Block


def emit_io_assignment(
    *,
    blocks: list[Block],
    output_path: Path,
) -> None:
    """For each block's :class:`ConnectorInstance`, emit one row per pin.

    Args:
        blocks: The carrier's blocks.
        output_path: Where to write the CSV. Atomic write via tempfile.

    Columns:
        Block, Connector Ref, Connector MPN, Pin, Net
    """
    if output_path.suffix != ".csv":
        raise ValueError(f"output_path must end in .csv, got {output_path}")

    rows: list[dict[str, str]] = []
    for block in blocks:
        for connector in block.connectors:
            mpn = connector.refcircuit.part_mpn
            for pin_id, net_name in connector.pin_to_net:
                rows.append({
                    "Block": block.name,
                    "Connector Ref": connector.reference,
                    "Connector MPN": mpn,
                    "Pin": pin_id,
                    "Net": net_name,
                })

    _atomic_write_csv(
        output_path=output_path,
        fieldnames=["Block", "Connector Ref", "Connector MPN", "Pin", "Net"],
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
