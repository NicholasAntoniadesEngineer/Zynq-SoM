"""Persistent build log for the hierarchical carrier schematic generator.

The log file lives next to the generated schematic and contains one section
per build step (io assignment, BOM, reference-circuits doc, per-block sheet,
root sheet, validation, artefact list). The compliance rule "Logs exclusively
in ``*_logs`` files: Separate from logic code" requires logging to live
outside business logic, so this module is the only place that formats the
file.

Per-block stats include ``wires``, ``hierarchical_labels`` and ``local_labels``
so the build log makes it visible when the new pipeline starts emitting real
wire connectivity (the legacy generator wrote 0 wires and only global labels).

Usage:

    log = CarrierBuildLog(carrier_dir / "carrier_build_logs.txt")
    log.start_run()
    log.log_io_assignment(rows=300, sections=18)
    log.log_bom(parts=147, distinct_tokens=42, total_usd=33.78)
    log.log_refcircuits_doc(line_count=635, ic_count=15)
    log.log_block(block_name="som", ...)
    log.log_root_sheet(child_sheet_count=2, hierarchical_pin_count=300)
    log.log_validation(strict_failures=0, warning_count=0, report_path=...)
    log.finish(artifact_paths=[...])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class BlockStats:
    """Per-block emission counters produced by ``emit/kicad_sch.py``."""

    block_name: str
    schematic_path: Path
    placed_symbol_count: int
    wire_count: int
    junction_count: int
    local_label_count: int
    hierarchical_label_count: int
    sheet_pin_count: int

    def __post_init__(self) -> None:
        if not self.block_name:
            raise ValueError("BlockStats.block_name must be non-empty")
        if not isinstance(self.schematic_path, Path):
            raise TypeError(
                "BlockStats.schematic_path must be a Path, got "
                f"{type(self.schematic_path).__name__}"
            )
        for counter_name in (
            "placed_symbol_count",
            "wire_count",
            "junction_count",
            "local_label_count",
            "hierarchical_label_count",
            "sheet_pin_count",
        ):
            counter_value = getattr(self, counter_name)
            if not isinstance(counter_value, int) or counter_value < 0:
                raise ValueError(
                    f"BlockStats.{counter_name} must be a non-negative int, "
                    f"got {counter_value!r}"
                )


@dataclass
class CarrierBuildLog:
    """Append-only writer for the per-build log file.

    The file is opened in ``w`` mode on ``finish()``/``write_partial()`` so
    each build overwrites the previous log; downstream tooling reads only the
    latest run.
    """

    log_path: Path
    _lines: list[str] = field(default_factory=list)
    _started: bool = False

    def _require_started(self, method_name: str) -> None:
        if not self._started:
            raise RuntimeError(
                f"CarrierBuildLog.{method_name}: call start_run() first"
            )

    def line(self, message: str) -> None:
        if not isinstance(message, str):
            raise TypeError(
                "CarrierBuildLog.line: message must be str, got "
                f"{type(message).__name__}"
            )
        self._lines.append(message)

    def blank(self) -> None:
        self._lines.append("")

    def start_run(self) -> None:
        timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._lines = []
        self._started = True
        self.line(f"=== carrier build {timestamp_iso} ===")

    def log_io_assignment(self, rows: int, sections: int) -> None:
        self._require_started("log_io_assignment")
        self.line("io_assignment.csv:")
        self.line(f"  rows: {rows}")
        self.line(f"  sections covered: {sections}")
        self.blank()

    def log_bom(self, parts: int, distinct_tokens: int, total_usd: float) -> None:
        self._require_started("log_bom")
        self.line("carrier_BOM.csv:")
        self.line(f"  total parts: {parts}")
        self.line(f"  distinct tokens: {distinct_tokens}")
        self.line(f"  total board cost: ${total_usd:.2f}")
        self.blank()

    def log_refcircuits_doc(self, line_count: int, ic_count: int) -> None:
        self._require_started("log_refcircuits_doc")
        self.line("reference_circuits.md:")
        self.line(f"  lines: {line_count}")
        self.line(f"  ICs documented: {ic_count}")
        self.blank()

    def log_block(self, stats: BlockStats) -> None:
        self._require_started("log_block")
        self.line(f"block: {stats.block_name} -> {stats.schematic_path.name}")
        self.line(f"  placed symbols: {stats.placed_symbol_count}")
        self.line(f"  wires: {stats.wire_count}")
        self.line(f"  junctions: {stats.junction_count}")
        self.line(f"  local labels: {stats.local_label_count}")
        self.line(f"  hierarchical labels: {stats.hierarchical_label_count}")
        self.line(f"  sheet pins (on parent reference): {stats.sheet_pin_count}")
        self.blank()

    def log_root_sheet(
        self,
        child_sheet_count: int,
        hierarchical_pin_count: int,
        root_path: Path,
    ) -> None:
        self._require_started("log_root_sheet")
        self.line(f"root sheet: {root_path.name}")
        self.line(f"  child sheets: {child_sheet_count}")
        self.line(f"  total hierarchical pins: {hierarchical_pin_count}")
        self.blank()

    def log_validation(
        self,
        strict_failures: int,
        warning_count: int,
        report_path: Path,
    ) -> None:
        self._require_started("log_validation")
        self.line("validation:")
        self.line(f"  strict failures: {strict_failures}")
        self.line(f"  warnings: {warning_count}")
        self.line(f"  report: {report_path.name}")
        self.blank()

    def log_erc(self, error_count: int, warning_count: int) -> None:
        self._require_started("log_erc")
        self.line("kicad-cli sch erc:")
        self.line(f"  errors: {error_count}")
        self.line(f"  warnings: {warning_count}")
        self.blank()

    def finish(self, artifact_paths: list[Path]) -> None:
        self._require_started("finish")
        self.line("artefacts:")
        for artefact_path in artifact_paths:
            self.line(f"  {artefact_path.name}")
        self.blank()
        try:
            self.log_path.write_text("\n".join(self._lines) + "\n", encoding="utf-8")
        except OSError as write_error:
            raise RuntimeError(
                f"CarrierBuildLog.finish: failed to write {self.log_path}: "
                f"{write_error}"
            ) from write_error

    def write_partial(self) -> None:
        """Flush whatever has been logged so far (used after a failure)."""
        self._require_started("write_partial")
        try:
            self.log_path.write_text("\n".join(self._lines) + "\n", encoding="utf-8")
        except OSError as write_error:
            raise RuntimeError(
                f"CarrierBuildLog.write_partial: failed to write {self.log_path}:"
                f" {write_error}"
            ) from write_error
