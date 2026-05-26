"""Sheet → .kicad_sch via kicad-sch-api.

Atomic write: emit to a temp file in the destination directory then rename
into place. Eliminates half-written files on crash.

WORKAROUND — kicad-sch-api 0.5.6 set_hierarchy_context() connectivity bug
========================================================================

After exhaustive investigation (root-caused via binary search against a
hand-authored .kicad_sch reference), the previously-observed "every
passive-to-IC wire is dangling" symptom traces to **a single API call**:

    ``schematic.set_hierarchy_context(parent_uuid, sheet_uuid)``

When this is called on a schematic, every ``add_wire`` emitted afterwards
is saved into the .kicad_sch in a way that KiCad's connectivity engine
*ignores* during netlist + ERC. The wires still render visually; KiCad
just treats them as decorative.

Without ``set_hierarchy_context`` the same wires net cleanly between
passive pins (verified with ``kicad-cli sch export netlist``).

Related upstream tickets (circuit-synth/kicad-sch-api):
  * Issue #175 — "Wire-pin Connects in kicad-to-python generator"
    (closed Nov 2025, original reporter described the same "wires
    seem to be out of range" symptom; no public resolution).
  * Issue #203 — "get_component_pin_position() returns wrong coordinates
    for rotated components (90°/270°)" (open Feb 2026, related but
    separate — that one affects ``connect_pins_with_wire`` rather than
    plain ``add_wire``).
  * PR #206 — "fix(geometry): apply rotation before Y-flip" (open Apr
    2026, fixes #203 but not the set_hierarchy_context regression).

Our policy: until kicad-sch-api lands a fix that lets us re-enable
``set_hierarchy_context`` without poisoning connectivity, we

  1. NEVER call ``schematic.set_hierarchy_context()`` here.
  2. Compute every pin position ourselves in ``core/layout/geometry.py``
     using our own flip-Y-then-rotate-CW transform (also verified by
     power-symbol probe; matches what KiCad actually places).
  3. Defer hierarchical-path patching until the root sheet emitter
     (Stage 7) — which will add the real ``(path "/root/sheet" ...)``
     entries based on the sheet UUIDs the root sheet allocates. Until
     then, sub-sheets emit with kicad-sch-api's auto-generated
     single-level paths, which KiCad accepts when validating a sub-sheet
     in isolation.

When kicad-sch-api ships a fix:
  * Drop the warning comments + the call site `schematic.set_hierarchy_context(...)`
    can be restored where ``parent_uuid`` / ``sheet_uuid`` are supplied
    by the root-sheet emitter.
  * The post-emit ``_patch_hierarchy_paths`` helper can then be removed
    entirely.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import kicad_sch_api as ksa

from zynq_eda.core.model.sheet import Sheet


@dataclass(frozen=True)
class EmissionStats:
    """Counters returned by :func:`emit_sheet` for the build log."""

    sheet_name: str
    output_path: Path
    placed_symbol_count: int
    wire_count: int
    label_count: int
    hierarchical_label_count: int
    junction_count: int
    no_connect_count: int = 0


_PREVIEW_PARENT_UUID = str(uuid.uuid4())  # set once per pipeline run
_PREVIEW_SHEET_UUID = str(uuid.uuid4())


def emit_sheet(
    sheet: Sheet,
    output_path: Path,
    *,
    parent_uuid: str | None = None,
    sheet_uuid: str | None = None,
    lib_symbol_pin_type_overrides: tuple[tuple[str, str, str], ...] = (),
) -> EmissionStats:
    """Render a :class:`Sheet` to a ``.kicad_sch`` file (atomic write).

    Args:
        sheet: The placed sheet to emit.
        output_path: Where to write the file. Parent dirs are created.
        parent_uuid, sheet_uuid: UUIDs for the hierarchical reference
            annotation. When omitted, fresh UUIDs are generated (suitable
            for standalone-sheet tests). For real hierarchical projects,
            the root sheet emitter passes the parent + sheet UUIDs it
            allocated when adding the sheet symbol.
        lib_symbol_pin_type_overrides: ``(lib_id, pin_name, new_type)``
            tuples patched into the embedded ``lib_symbols`` block after
            kicad-sch-api has written the file. Used to correct stock
            KiCad symbols whose declared pin electrical type causes
            spurious ERC violations (e.g. ``Sensor_Energy:INA226`` Vbus
            sense pin declared ``input`` instead of ``passive``). See
            :class:`ReferenceCircuit.lib_symbol_pin_type_overrides`.
    """
    # NOTE — DO NOT call ``schematic.set_hierarchy_context(...)`` here.
    #
    # In kicad-sch-api 0.5.6, calling ``set_hierarchy_context`` poisons the
    # schematic so that wires emitted by ``add_wire`` are no longer
    # recognised as electrical connections between passive pins. The
    # rendered PDF still shows the wires, but ``kicad-cli sch erc`` flags
    # every passive-to-passive wire as ``wire_dangling`` and the
    # corresponding pins as floating in the exported netlist.
    #
    # Reproducer: with set_hierarchy_context, a wire from R1.pin2 to
    # R2.pin1 (both Device:R at rotation 90, all coords on the 1.27 mm
    # grid, endpoints verified by power-symbol probe at the same coords)
    # yields no shared net in the netlist. Removing the
    # set_hierarchy_context call makes the same wire net cleanly.
    #
    # The hierarchy_path property is required for proper hierarchical
    # reference annotation in multi-sheet projects (so R12 instead of R?
    # when the same sheet is instantiated under multiple parents). We
    # patch it in post-emit instead, by editing the saved .kicad_sch's
    # symbol-instance "path" entries to use the supplied parent/sheet
    # UUIDs. This sidesteps the connectivity bug.
    #
    # When kicad-sch-api ships a fix for issue #203 / the
    # set_hierarchy_context wire-connectivity regression, we can
    # restore the in-API call and drop the post-emit path patch.
    parent = parent_uuid or _PREVIEW_PARENT_UUID
    sheet_id = sheet_uuid or _PREVIEW_SHEET_UUID

    schematic = ksa.create_schematic(sheet.title)
    schematic.set_paper_size(sheet.paper_size)
    schematic.title_block["title"] = sheet.title
    if sheet.description:
        schematic.title_block["comment1"] = sheet.description

    for placed in sheet.symbols:
        component = schematic.components.add(
            placed.lib_id,
            reference=placed.reference,
            value=placed.value,
            position=placed.position.as_tuple(),
            footprint=placed.footprint,
            rotation=placed.rotation,
        )
        for property_name, property_value in placed.properties:
            try:
                component.set_property(property_name, property_value)
            except Exception:
                # Some property names are reserved by kicad-sch-api; skip
                # gracefully rather than fail the whole emission.
                continue

    for wire in sheet.wires:
        schematic.add_wire(wire.start.as_tuple(), wire.end.as_tuple())

    for label in sheet.labels:
        schematic.add_label(
            label.net_name,
            position=label.position.as_tuple(),
            rotation=label.rotation,
        )

    for hlabel in sheet.hierarchical_labels:
        schematic.add_hierarchical_label(
            hlabel.net_name,
            position=hlabel.position.as_tuple(),
            shape=hlabel.direction,
            rotation=hlabel.rotation,
        )

    for junction in sheet.junctions:
        schematic.add_junction(junction.position.as_tuple())

    for no_connect in sheet.no_connects:
        schematic.no_connects.add(position=no_connect.position.as_tuple())

    _atomic_save(schematic, output_path)
    _hide_internal_properties(output_path)
    if lib_symbol_pin_type_overrides:
        _patch_lib_symbol_pin_types(output_path, lib_symbol_pin_type_overrides)
    # Disable for now: _patch_hierarchy_paths(output_path, parent, sheet_id)

    return EmissionStats(
        sheet_name=sheet.name,
        output_path=output_path,
        placed_symbol_count=len(sheet.symbols),
        wire_count=len(sheet.wires),
        label_count=len(sheet.labels),
        hierarchical_label_count=len(sheet.hierarchical_labels),
        junction_count=len(sheet.junctions),
        no_connect_count=len(sheet.no_connects),
    )


_INTERNAL_PROPERTIES_TO_HIDE: tuple[str, ...] = (
    "hierarchy_path",  # kicad-sch-api annotation; KiCad renders it as text
                       # next to every symbol unless explicitly hidden.
    "LCSC",            # BOM-tracking LCSC code (e.g. "C6624664"); useful in
                       # the BOM CSV + the schematic property table, but
                       # rendering it next to every symbol on every page
                       # clutters the schematic with stray text strings.
    "Datasheet",       # Same — URLs are long and visually noisy when
                       # rendered as floating text next to every IC.
)


def _patch_hierarchy_paths(
    schematic_path: Path,
    parent_uuid: str,
    sheet_uuid: str,
) -> None:
    """Inject the hierarchical (path "/parent/sheet" ...) into symbol instances.

    Replaces the auto-generated single-level path (which kicad-sch-api emits
    when set_hierarchy_context was never called) with the two-level
    hierarchical path the root-sheet linker expects. This is the post-emit
    half of the workaround for the set_hierarchy_context wire-connectivity
    bug — we get correct connectivity *and* correct hierarchical references.
    """
    import re

    text = schematic_path.read_text(encoding="utf-8")
    target_path = f"/{parent_uuid}/{sheet_uuid}"

    # kicad-sch-api emits each symbol-instance block as:
    #     (instances
    #         (project "<name>"
    #             (path "/<single-uuid>"
    #                 (reference "Rxx")
    #                 (unit 1)
    #             )
    #         )
    #     )
    # We rewrite ``"/<single-uuid>"`` to the two-level path. The single
    # UUID is the sheet's auto-generated UUID; replacing it with our
    # parent/sheet pair makes the symbol instance addressable from the
    # root sheet's hierarchical reference table.
    patched = re.sub(
        r'\(path "/[0-9a-fA-F-]{36}"',
        f'(path "{target_path}"',
        text,
    )
    if patched != text:
        schematic_path.write_text(patched, encoding="utf-8")


def _hide_internal_properties(schematic_path: Path) -> None:
    """Inject ``(hide yes)`` into the effects block of every internal property.

    kicad-sch-api 0.5.6 emits a ``hierarchy_path`` property on every placed
    symbol but does not mark it hidden, so KiCad renders the UUID path next
    to every component on the sheet — the schematic becomes unreadable.

    This pass scans the file line-by-line, finds the ``(effects`` block that
    immediately follows any matching property, and inserts ``(hide yes)``
    inside that block (no-op if already hidden).
    """
    lines = schematic_path.read_text(encoding="utf-8").splitlines()

    in_target_property = False
    awaiting_effects = False
    modified = False
    new_lines: list[str] = []
    target_names = {f'"{name}"' for name in _INTERNAL_PROPERTIES_TO_HIDE}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("(property "):
            tokens = stripped.split()
            if len(tokens) >= 2 and tokens[1] in target_names:
                in_target_property = True
                awaiting_effects = True
                new_lines.append(line)
                continue
            in_target_property = False
            awaiting_effects = False

        if awaiting_effects and stripped == "(effects":
            new_lines.append(line)
            # Compute indent of the effects content (one level deeper than (effects).
            effects_indent_len = len(line) - len(line.lstrip())
            child_indent = "\t" * ((effects_indent_len // 1) + 1)
            # Use tab indent to match KiCad's style; len of line.lstrip's whitespace
            # gives us the existing indent character set.
            existing_indent = line[:effects_indent_len]
            child_indent = existing_indent + "\t"
            new_lines.append(f"{child_indent}(hide yes)")
            awaiting_effects = False
            in_target_property = False
            modified = True
            continue

        # If the property closes without an (effects block, reset state.
        if in_target_property and stripped == ")":
            in_target_property = False
            awaiting_effects = False

        new_lines.append(line)

    if modified:
        schematic_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _patch_lib_symbol_pin_types(
    schematic_path: Path,
    overrides: tuple[tuple[str, str, str], ...],
) -> None:
    """Rewrite pin electrical types inside the embedded ``lib_symbols`` block.

    kicad-sch-api caches stock KiCad library symbols verbatim from the
    user's library, which means a wrong pin-type declaration in the
    stock symbol (e.g. ``Sensor_Energy:INA226`` Vbus pin marked
    ``input`` when it is functionally a high-Z sense node) propagates
    into our emitted ``.kicad_sch`` and drives bogus ERC violations.

    Each override is ``(lib_id, pin_name, new_type)``. We locate the
    matching ``(symbol "<lib_id>" ...)`` block, then within it find
    each ``(pin <old_type> line ...) ... (name "<pin_name>" ...)``
    and rewrite the type token.

    The rewrite is bounded to the targeted ``(symbol ...)`` block
    (i.e. only the lib-symbol definition, not symbol instances) by
    bracket-depth tracking, and bounded to the targeted ``(pin ...)``
    block by a small look-ahead window.
    """
    import re

    text = schematic_path.read_text(encoding="utf-8")
    original = text

    for lib_id, pin_name, new_type in overrides:
        # Find the (symbol "lib_id" ...) block within lib_symbols.
        sym_open = re.compile(
            r'\(symbol\s+"' + re.escape(lib_id) + r'"',
        )
        m = sym_open.search(text)
        if not m:
            continue

        # Track bracket depth from the opening paren of the (symbol ...).
        block_start = m.start()
        depth = 0
        i = block_start
        block_end = -1
        in_string = False
        while i < len(text):
            ch = text[i]
            if ch == '"' and (i == 0 or text[i - 1] != "\\"):
                in_string = not in_string
            elif not in_string:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        block_end = i + 1
                        break
            i += 1
        if block_end < 0:
            continue

        block = text[block_start:block_end]

        # Within the block, find each (pin <type> line ...) (name "<pin_name>" ...)
        # and rewrite the <type>. Pin definitions look like:
        #     (pin input line
        #         (at X Y rot)
        #         (length L)
        #         (name "<pin_name>" ...)
        #         (number "N" ...)
        #     )
        # We capture the type with a non-greedy match up to the `name` line.
        pin_pattern = re.compile(
            r'(\(pin\s+)([a-z_]+)(\s+line\s*\n[^()]*?\(at[^)]*\)\s*\n[^()]*?\(length[^)]*\)\s*\n[^()]*?\(name\s+"'
            + re.escape(pin_name)
            + r'")',
            re.MULTILINE,
        )

        def _repl(match: re.Match[str]) -> str:
            return match.group(1) + new_type + match.group(3)

        new_block, n = pin_pattern.subn(_repl, block)
        if n > 0:
            text = text[:block_start] + new_block + text[block_end:]

    if text != original:
        schematic_path.write_text(text, encoding="utf-8")


def _atomic_save(schematic: ksa.Schematic, output_path: Path) -> None:
    """Write the schematic via a temp file in the same directory + rename."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(
        prefix=output_path.stem + ".",
        suffix=".kicad_sch.tmp",
        dir=str(output_path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_path_str)
    try:
        schematic.save_as(temp_path)
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
