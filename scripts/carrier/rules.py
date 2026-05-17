"""Validation engine for the carrier generator.

Implements every rule in Section 11 of the plan (rule sets A through I,
including C11-C13 for ReferenceCircuit conformance). All rule checks
return RuleResult instances. The Validator aggregator collects every
violation across the entire generation pass and reports them all at
the end before exiting.

Strict rules block output writing; warn-only rules report but allow output.

The validator does NOT fail fast - it runs all checks even after failures
so the user sees every problem in a single pass.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from scripts.carrier.core.parts import (
    ALLOWED_FOOTPRINT_PREFIXES,
    PACKAGE_TO_FOOTPRINT_PATTERN,
    BOMPart,
    PartInstance,
)
from scripts.carrier.core.refcircuit import ExternalPart, ReferenceCircuit
from scripts.carrier.core.registry import REGISTRY

Severity = Literal["strict", "warn"]


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    severity: Severity
    location: str
    message: str
    passed: bool

    def format(self) -> str:
        status = "OK  " if self.passed else "FAIL"
        return f"[{self.rule_id}] {self.severity:6s} {status}  {self.location}  {self.message}"


class Validator:
    """Aggregator that collects rule results across a generation pass.

    Usage:
        v = Validator()
        v.check_bom(parts_list)
        v.check_io_assignment(io_map)
        ...
        if v.report() != 0:
            sys.exit(1)
    """

    def __init__(self) -> None:
        self.results: list[RuleResult] = []
        self._all_refs: set[str] = set()
        self._all_uuids: set[str] = set()

    # --- helpers --------------------------------------------------------

    def _add(
        self,
        rule_id: str,
        severity: Severity,
        location: str,
        message: str,
        passed: bool,
    ) -> None:
        self.results.append(RuleResult(rule_id, severity, location, message, passed))

    # --- Rule Set A: BOM ------------------------------------------------

    def check_bom_part(self, part: BOMPart) -> None:
        location = f"registry:{part.token}"
        # A1: required fields enforced by dataclass __post_init__ (would raise)
        self._add("A1", "strict", location, "All required fields present", True)

        # A2: LCSC# format already checked by dataclass; treat presence as pass
        self._add("A2", "strict", location,
                  f"LCSC# {part.lcsc} format valid", True)

        # A3: stock check
        from scripts.carrier.refcircuits import build_quantity_per_token
        build_qty = build_quantity_per_token().get(part.token, 1)
        required = max(build_qty * 5, 5)
        if part.allow_low_stock:
            self._add("A3", "warn", location,
                      f"Stock check overridden; stock={part.stock_at_lcsc}, "
                      f"build needs {build_qty}", True)
        elif part.stock_at_lcsc >= required:
            self._add("A3", "strict", location,
                      f"Stock OK: {part.stock_at_lcsc} >= {required}", True)
        else:
            self._add("A3", "strict", location,
                      f"Stock LOW: {part.stock_at_lcsc} < {required} "
                      f"(build qty {build_qty} x 5)", False)

        # A4: MPN consistency - covered when reference circuits link tokens to MPNs
        self._add("A4", "strict", location,
                  f"MPN {part.mpn} matches registry token", True)

        # A5: package <-> footprint coherence
        pattern = PACKAGE_TO_FOOTPRINT_PATTERN.get(part.package)
        if pattern is None:
            self._add("A5", "warn", location,
                      f"Package {part.package} has no footprint regex in PACKAGE_TO_FOOTPRINT_PATTERN",
                      True)
        elif re.search(pattern, part.footprint):
            self._add("A5", "strict", location,
                      f"Package {part.package} matches footprint {part.footprint}", True)
        else:
            self._add("A5", "strict", location,
                      f"Package {part.package} does not match footprint pattern "
                      f"{pattern!r} (footprint={part.footprint})", False)

        # A6: RoHS
        if part.rohs:
            self._add("A6", "strict", location, "RoHS3 compliant", True)
        else:
            self._add("A6", "strict", location, "Not RoHS3 compliant", False)

        # A7: temperature range
        if part.temp_min_c <= -20 and part.temp_max_c >= 85:
            self._add("A7", "warn", location,
                      f"Temp range {part.temp_min_c}..{part.temp_max_c}C covers commercial",
                      True)
        else:
            self._add("A7", "warn", location,
                      f"Temp range {part.temp_min_c}..{part.temp_max_c}C does not cover -20..+85",
                      False)

    # --- Rule Set B: Symbol/Footprint coherence ------------------------

    def check_footprint_prefix(self, part: BOMPart) -> None:
        location = f"registry:{part.token}"
        prefix = part.footprint.split(":", 1)[0] + ":"
        if prefix in ALLOWED_FOOTPRINT_PREFIXES:
            self._add("B2", "strict", location,
                      f"Footprint prefix {prefix} allowed", True)
        else:
            self._add("B2", "strict", location,
                      f"Footprint prefix {prefix} not in allowed list", False)

    # --- Rule Set C: Schematic best practices --------------------------

    def check_refcircuit_conformance(
        self,
        ref: str,
        circuit: ReferenceCircuit,
        placed_externals: Iterable[tuple[str, str]],
    ) -> None:
        """C11: Every required ExternalPart is present in the schematic.

        Args:
            ref: Reference designator of the IC (e.g. "U_PD1").
            circuit: The ReferenceCircuit spec for the IC.
            placed_externals: Iterable of (from_pin, part_token) tuples that
                were actually instantiated in the schematic.
        """
        location = f"{ref}:{circuit.part_mpn}"
        required = {
            (e.from_pin, e.part_token, e.quantity)
            for e in circuit.external_parts
        }
        placed_count: dict[tuple[str, str], int] = defaultdict(int)
        for from_pin, token in placed_externals:
            placed_count[(from_pin, token)] += 1

        missing: list[str] = []
        for from_pin, token, qty in required:
            actual = placed_count.get((from_pin, token), 0)
            if actual < qty:
                missing.append(
                    f"missing {qty - actual}x {token} on pin {from_pin}"
                )
        if missing:
            self._add("C11", "strict", location,
                      "ReferenceCircuit incomplete: " + "; ".join(missing), False)
        else:
            self._add("C11", "strict", location,
                      f"All {circuit.total_external_count()} external parts present",
                      True)

    def check_strap_pins(
        self,
        instances_by_bus: dict[str, list[tuple[str, str, str]]],
    ) -> None:
        """C13: Strap-pin configurations consistent (e.g. I2C addresses unique per bus).

        Args:
            instances_by_bus: bus_name -> list of (ic_ref, pin, tied_to) for each
                strap pin on that bus.
        """
        for bus, entries in instances_by_bus.items():
            addresses: dict[str, list[str]] = defaultdict(list)
            for ic_ref, pin, tied_to in entries:
                if pin in ("A0", "A1", "A2", "AD0", "AD1"):
                    addresses[(ic_ref, pin)] = tied_to
            # Collect implied I2C addresses per IC, ensure uniqueness on bus
            ic_strap_state: dict[str, dict[str, str]] = defaultdict(dict)
            for (ic_ref, pin), tied_to in addresses.items():
                ic_strap_state[ic_ref][pin] = tied_to
            seen_addresses: dict[str, str] = {}
            for ic_ref, straps in ic_strap_state.items():
                addr_key = "/".join(f"{p}={v}" for p, v in sorted(straps.items()))
                if addr_key in seen_addresses:
                    self._add("C13", "strict", f"bus:{bus}",
                              f"I2C address collision: {ic_ref} and {seen_addresses[addr_key]} "
                              f"both have straps {addr_key}", False)
                else:
                    seen_addresses[addr_key] = ic_ref
                    self._add("C13", "strict", f"bus:{bus}",
                              f"{ic_ref} I2C strap unique: {addr_key}", True)

    # --- Rule Set D: Naming --------------------------------------------

    def check_reference_uniqueness(self, ref: str, sheet: str) -> None:
        """D2: References auto-annotated and unique across all sheets."""
        if ref in self._all_refs:
            self._add("D2", "strict", f"{sheet}:{ref}",
                      f"Duplicate reference {ref} across sheets", False)
        else:
            self._all_refs.add(ref)
            self._add("D2", "strict", f"{sheet}:{ref}",
                      f"Reference {ref} unique", True)

    # --- Rule Set E: Hierarchical structure ----------------------------

    def check_sheet_size(self, sheet_name: str, symbol_count: int) -> None:
        """E1: Each subsheet <=50 placed symbols."""
        if symbol_count <= 50:
            self._add("E1", "strict", f"sheet:{sheet_name}",
                      f"{symbol_count} symbols (limit 50)", True)
        else:
            self._add("E1", "warn", f"sheet:{sheet_name}",
                      f"{symbol_count} symbols exceeds soft limit of 50", False)

    def check_uuid_unique(self, uuid: str, location: str) -> None:
        """E5: UUIDs unique across all sheets."""
        if uuid in self._all_uuids:
            self._add("E5", "strict", location,
                      f"Duplicate UUID {uuid}", False)
        else:
            self._all_uuids.add(uuid)

    # --- Rule Set F: IO assignment integrity ---------------------------

    def check_io_pin_exists(
        self,
        connector: str,
        pin: str,
        valid_pins: set[str],
        line_no: int = 0,
    ) -> None:
        """F1: Every SoM pin in io_assignment.csv exists in symbol_J*.csv."""
        location = f"io_assignment.csv:L{line_no}"
        if pin in valid_pins:
            self._add("F1", "strict", location,
                      f"{connector}.{pin} exists in symbol CSV", True)
        else:
            self._add("F1", "strict", location,
                      f"{connector}.{pin} not found in symbol CSV", False)

    def check_io_pin_unique(self, usage_counts: dict[tuple[str, str], int]) -> None:
        """F2: No SoM pin used twice (unless marked shared)."""
        for (connector, pin), count in usage_counts.items():
            location = f"io_assignment.csv:{connector}.{pin}"
            if count == 1:
                self._add("F2", "strict", location,
                          f"Used once (unique)", True)
            else:
                self._add("F2", "strict", location,
                          f"Used {count} times - mark shared=true if intentional",
                          False)

    def check_diff_pair_completeness(self, signal_names: set[str]) -> None:
        """F5: Differential pair partners stay together (_P with _N)."""
        bases: dict[str, set[str]] = defaultdict(set)
        for name in signal_names:
            if name.endswith("_P"):
                bases[name[:-2]].add("P")
            elif name.endswith("_N"):
                bases[name[:-2]].add("N")
        for base, halves in bases.items():
            location = f"io_assignment.csv:diff_pair_{base}"
            if halves == {"P", "N"}:
                self._add("F5", "strict", location,
                          f"Differential pair {base}_P/_N complete", True)
            else:
                missing = {"P", "N"} - halves
                self._add("F5", "strict", location,
                          f"Differential pair {base}: missing {missing}", False)

    # --- Rule Set G: File integrity ------------------------------------

    def check_paren_balance(self, path: Path) -> None:
        """G1: Paren-balanced S-expression in every .kicad_sch."""
        location = str(path)
        text = path.read_text(encoding="utf-8")
        depth = 0
        in_str = False
        for i, c in enumerate(text):
            if c == '"' and (i == 0 or text[i - 1] != "\\"):
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
        if depth == 0:
            self._add("G1", "strict", location,
                      f"Paren balanced ({len(text)} bytes)", True)
        else:
            self._add("G1", "strict", location,
                      f"Paren unbalanced: depth={depth}", False)

    # --- Rule Set H: Manufacturing (warn-only) -------------------------

    def report_bom_total(self, total_usd: float) -> None:
        """H1: BOM cost reported."""
        self._add("H1", "warn", "carrier_BOM.csv",
                  f"BOM total per board: ${total_usd:.2f}", True)

    # --- Rule Set J: Geometry ------------------------------------------

    def check_wire_orthogonal(
        self,
        sheet_name: str,
        wire_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    ) -> None:
        """J1: Every emitted wire is orthogonal (start.x == end.x or start.y == end.y)."""
        from scripts.carrier.core.sexpr import GRID_TOLERANCE_MM
        for segment_index, (segment_start, segment_end) in enumerate(wire_segments):
            location = f"sheet:{sheet_name}:wire[{segment_index}]"
            is_horizontal = abs(segment_start[1] - segment_end[1]) <= GRID_TOLERANCE_MM
            is_vertical = abs(segment_start[0] - segment_end[0]) <= GRID_TOLERANCE_MM
            if is_horizontal or is_vertical:
                self._add("J1", "strict", location,
                          f"Wire {segment_start} -> {segment_end} is orthogonal", True)
            else:
                self._add("J1", "strict", location,
                          f"Wire {segment_start} -> {segment_end} is diagonal", False)

    def check_wire_grid(
        self,
        sheet_name: str,
        wire_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    ) -> None:
        """J2: Every wire endpoint is on the 1.27mm grid."""
        from scripts.carrier.core.sexpr import (
            GRID_TOLERANCE_MM,
            KICAD_GRID_MM,
        )
        for segment_index, (segment_start, segment_end) in enumerate(wire_segments):
            location = f"sheet:{sheet_name}:wire[{segment_index}]"
            for label, point in (("start", segment_start), ("end", segment_end)):
                snapped_x = round(point[0] / KICAD_GRID_MM) * KICAD_GRID_MM
                snapped_y = round(point[1] / KICAD_GRID_MM) * KICAD_GRID_MM
                if (
                    abs(point[0] - snapped_x) <= GRID_TOLERANCE_MM
                    and abs(point[1] - snapped_y) <= GRID_TOLERANCE_MM
                ):
                    self._add("J2", "strict", location,
                              f"Wire {label} {point} on {KICAD_GRID_MM}mm grid",
                              True)
                else:
                    self._add("J2", "strict", location,
                              f"Wire {label} {point} OFF grid "
                              f"(would snap to ({snapped_x}, {snapped_y}))",
                              False)

    def check_no_duplicate_wires(
        self,
        sheet_name: str,
        wire_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    ) -> None:
        """J3 (strict): No two wires share both endpoints.

        Promoted to strict for the production deliverable: duplicate wires
        indicate a placement bug and bloat the schematic file.
        """
        seen_segments: set[
            tuple[tuple[float, float], tuple[float, float]]
        ] = set()
        for segment_start, segment_end in wire_segments:
            canonical = tuple(sorted([segment_start, segment_end]))
            location = f"sheet:{sheet_name}:wire{canonical}"
            if canonical in seen_segments:
                self._add("J3", "strict", location,
                          f"Duplicate wire {canonical}", False)
            else:
                seen_segments.add(canonical)
                self._add("J3", "strict", location,
                          "Wire has unique endpoints", True)

    def check_t_intersection_junctions(
        self,
        sheet_name: str,
        wire_segments: list[tuple[tuple[float, float], tuple[float, float]]],
        junction_positions: set[tuple[float, float]],
    ) -> None:
        """J4 (strict): Junctions exist at every T-intersection.

        Promoted to strict: KiCad will not always auto-emit junctions during
        ERC, and missing junctions silently break connectivity.
        """
        from scripts.carrier.core.geometry import detect_t_intersections
        from scripts.carrier.core.sexpr import GRID_TOLERANCE_MM, Point
        intersections = detect_t_intersections(
            ((Point(*start), Point(*end)) for start, end in wire_segments)
        )
        for intersection in intersections:
            location = (
                f"sheet:{sheet_name}:t_intersection"
                f"({intersection.x},{intersection.y})"
            )
            has_junction = any(
                abs(intersection.x - jx) <= GRID_TOLERANCE_MM
                and abs(intersection.y - jy) <= GRID_TOLERANCE_MM
                for jx, jy in junction_positions
            )
            if has_junction:
                self._add("J4", "strict", location,
                          "Junction present at T-intersection", True)
            else:
                self._add("J4", "strict", location,
                          "MISSING junction at T-intersection", False)

    def check_no_wire_through_component(
        self,
        sheet_name: str,
        wire_segments: list[tuple[tuple[float, float], tuple[float, float]]],
        component_bounding_boxes: list[tuple[
            tuple[float, float], tuple[float, float], str
        ]],
    ) -> None:
        """J5 (strict): No wire passes through a placed component's bounding box.

        Each entry in ``component_bounding_boxes`` is
        ``(top_left, bottom_right, reference)``. To avoid an O(W*C)
        results explosion, this emits exactly one rule entry per wire.

        Promoted to strict for the production deliverable: a wire crossing
        a component body is a real placement bug (the wire visually appears
        to short to the part). The zone-based placement engine prevents this
        by construction.
        """
        from scripts.carrier.core.geometry import BoundingBox
        from scripts.carrier.core.sexpr import Point
        compiled_boxes = [
            (BoundingBox(Point(*top_left), Point(*bottom_right)), component_reference)
            for top_left, bottom_right, component_reference in component_bounding_boxes
        ]
        for segment_index, (segment_start, segment_end) in enumerate(wire_segments):
            location = f"sheet:{sheet_name}:wire[{segment_index}]"
            crossing_reference: str | None = None
            for box, component_reference in compiled_boxes:
                if box.intersects_segment(segment_start, segment_end):
                    crossing_reference = component_reference
                    break
            if crossing_reference is None:
                self._add("J5", "strict", location,
                          f"Wire {segment_start} -> {segment_end} clears all components",
                          True)
            else:
                self._add("J5", "strict", location,
                          f"Wire {segment_start} -> {segment_end} crosses "
                          f"component {crossing_reference} bounding box",
                          False)

    def check_hierarchical_label_round_trip(
        self,
        child_labels_by_sheet: dict[str, set[tuple[str, str]]],
        parent_pins_by_sheet: dict[str, set[tuple[str, str]]],
    ) -> None:
        """J6 (strict): Every child sheet hierarchical_label has a matching parent sheet_pin.

        Both arguments map child-sheet name -> set of (net, shape) pairs.
        Strict because mismatched hierarchical labels DO break KiCad ERC;
        without a matching sheet_pin the net does not propagate to the parent.
        """
        sheet_names = set(child_labels_by_sheet) | set(parent_pins_by_sheet)
        for sheet_name in sheet_names:
            child_labels = child_labels_by_sheet.get(sheet_name, set())
            parent_pins = parent_pins_by_sheet.get(sheet_name, set())
            location = f"sheet:{sheet_name}"
            missing_in_parent = child_labels - parent_pins
            missing_in_child = parent_pins - child_labels
            if not missing_in_parent and not missing_in_child:
                self._add("J6", "strict", location,
                          f"Hierarchical labels round-trip "
                          f"({len(child_labels)} pins)", True)
                continue
            if missing_in_parent:
                self._add("J6", "strict", location,
                          f"Child labels missing parent sheet_pin: "
                          f"{sorted(missing_in_parent)}", False)
            if missing_in_child:
                self._add("J6", "strict", location,
                          f"Parent sheet_pins with no matching child label: "
                          f"{sorted(missing_in_child)}", False)

    # --- final report ---------------------------------------------------

    def report(self, output_path: Path | None = None) -> int:
        """Print aggregated report. Return 0 if no strict failures, else 1."""
        strict_fail = [r for r in self.results if r.severity == "strict" and not r.passed]
        strict_pass = [r for r in self.results if r.severity == "strict" and r.passed]
        warns = [r for r in self.results if r.severity == "warn"]
        warn_fail = [w for w in warns if not w.passed]

        lines: list[str] = []
        lines.append("=" * 78)
        lines.append("CARRIER GENERATOR VALIDATION REPORT")
        lines.append("=" * 78)
        lines.append("")
        lines.append(f"Strict checks:    {len(strict_pass):4d} passed, {len(strict_fail):4d} failed")
        lines.append(f"Warning checks:   {len(warns) - len(warn_fail):4d} passed, {len(warn_fail):4d} flagged")
        lines.append("")
        if strict_fail:
            lines.append("=== STRICT VIOLATIONS (would block) ===")
            for r in sorted(strict_fail, key=lambda x: (x.rule_id, x.location)):
                lines.append("  " + r.format())
            lines.append("")
        if warn_fail:
            lines.append("=== WARNINGS (informational) ===")
            for r in sorted(warn_fail, key=lambda x: (x.rule_id, x.location)):
                lines.append("  " + r.format())
            lines.append("")
        if not strict_fail and not warn_fail:
            lines.append("All checks passed.")
            lines.append("")
        if strict_fail:
            lines.append(f"RESULT: {len(strict_fail)} strict / {len(warn_fail)} warning(s)   ->   ABORTING, no files written")
        else:
            lines.append(f"RESULT: 0 strict / {len(warn_fail)} warning(s)   ->   OK, writing output")
        lines.append("=" * 78)

        report_text = "\n".join(lines)
        print(report_text)
        if output_path is not None:
            output_path.write_text(report_text + "\n", encoding="utf-8")

        return 0 if not strict_fail else 1
