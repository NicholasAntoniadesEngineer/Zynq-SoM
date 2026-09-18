# Native hierarchical board schematic contracts

This batch implements the complete `schgen/generate/board.py` stage in
`board_schematic.hpp/.cpp`: reference-band renaming, copied circuit/design
uniquification, safe duplicate-power-flag pruning, deterministic child/root
hierarchy generation, ordered board connectivity diagnostics, project JSON
merge, root ERC execution and timestamp normalization. It is a schematic-board
stage, not the entire board/PCB command pipeline.

## Typed integration

`BoardSheetInput` takes caller-owned `CircuitSheetIr`, a persistent reference
band from the project's sheet index, and optional `BoardPreparedSheet` containing
`SchematicPlacement` and `SchematicRoutedSheet`. A `ProjectCircuit::circuit`
can be passed directly; a `SchematicPlacedPage` supplies the prepared fields.
Missing preparation invokes the real `place_and_route_schematic` implementation.
There is no source-file reload, interpreter fallback or hand-placement branch.

`build_board_schematic(inputs, library, outdir, options)` performs completeness,
input-driver and visual checks, copies every child primitive, applies the routed
wires/junctions, uniquifies the circuit and emitted references, emits all children
and independently netlist-checks each uniquified standalone copy. It then emits
and checks the actual root hierarchy. Prepared placements do not bypass gates.
The result retains individual electrical, visual and netlist results and includes
their failures in its ordered report; a connectivity PASS cannot conceal a
visual/electrical failure from `result.ok()`.

Child instance paths are `/{board_uuid}/{sheet_symbol_uuid}`. Root, sheet-symbol
and child document UUIDs use the original distinct stable-UUID scopes. Sheet
ordering affects page order, not assigned bands or stable UUIDs. All ports are
sorted for root pin layout; child label shape selection and root global-label
binding retain the original rules. A3/A2/A1 packing, root title, sheet-relative
paths, spacing and primitive ordering are byte-contracted.

Emission and symbol-library access are sequential. Independent per-sheet KiCad
exports use bounded native workers: by default at most eight, limited by hardware
concurrency and sheet count; `netlist_workers` can request another bound. Results
are collected in input order. All workers join before the first input-ordered
exception is rethrown, irrespective of completion order. Each export owns a
different private scratch directory; the standalone verification documents also
live in a private RAII directory, not alongside user outputs.

The pure helpers (`board_renamed_ref`, `uniquify_board_design`,
`strip_duplicate_board_flags`, `make_board_hierarchy`, `check_board_netlist`) are
available independently. Pure assembly is not a successful-gates claim. The live
board-netlist overload always extracts the supplied root and runs root ERC.

Root ERC is **informational in the original board gate**. Its status/report are
explicit in `BoardNetlistResult`; it is not silently folded into connectivity.
Link/SoM policy, whole-command CC/symbol/model checks, manufacturing outputs,
rendering and PCB verification remain orchestration responsibilities.

## Shared process boundary

The only changes to existing shared core files are in `som_interface.hpp/.cpp`:
the existing argv-only launcher was factored into one private `run_kicad` helper,
and `run_kicad_erc` exposes the same redirection, wait, private scratch and cleanup
behavior. It returns the ERC exit code (negative signal number if signalled),
report and stderr; spawn/I/O failures throw. A claimed successful ERC without a
report throws. Existing netlist-export error wording and secure XML parsing are
unchanged. No shell execution or second XML/process implementation was added.

Retesting this refactor passed all 27 SoM interface contracts and all 92 netlist
gate contracts, including real KiCad exports/mutations and process failures.

## Frozen independent fixtures

`cases.json` contains typed inputs, immutable resolved symbol definitions,
reference results and exact ordered report strings. The adjacent schematics
are byte-for-byte expected emitter outputs. Three `board.xml` files are actual
KiCad 10.0.2 exports of those frozen hierarchies; timestamps/source paths are
retained as capture evidence but are not used as connectivity semantics.

- Eleven reference-renaming cases cover zero-padding, pseudo references,
  underscore prefixes, stride boundaries, invalid names and exact errors.
- Eight hierarchies cover the original M1 RC example as two connected sheets;
  carrier `board_qwiic`, `power_som`, `som_j1`; devkit `mechanical`, `power_som`,
  `usb_uart_connector`; A3/A2/A1 multi-column packing; no-port children; and
  markup, Unicode and quoted port names. Circuit IR, placements and definitions
  are frozen; later design-worker changes cannot invalidate these expectations.
- Sixteen flag-pruning cases cover global duplicates, real power-out drivers,
  per-sheet SIGNAL scope, absent/multiple stubs and anchors, other incident
  wires, actual symbol pins, both label kinds and junctions. Unsafe pruning is
  rejected by retaining the original flag island.
- Eleven ordered gate snapshots cover connected/split/missing/misnamed nets,
  `unconnected-` names, slash normalization, pseudo refs, silent single-sheet
  input opens, explicit `expect` deferral and real carrier/devkit/RC XML.
- Project merge snapshots preserve unrelated fields and insertion order while
  replacing `meta` and `erc`; timestamp tests preserve the rest of the report.

The reference was `schgen/generate/board.py` at commit
`93f1527ded042e51c5ad8bb283807301166d096b`, Git blob
`5ccfc1dbe81a1bc6bf73b36fda679d1dbce7e054`, SHA-256
`8b623f2f3282a940604cf57bccea3fd4d2faade086983530e06dc2433f468ec8`.
Capture executed the original root-assembly statements and board-gate decision
body as pure reference functions, plus the original rename/uniquify/flag helpers.
The actual hierarchical exports and ERC used KiCad. Native board decisions were
not used to generate expected values.

The emitter reference was the independently preserved pre-adapter source with
SHA-256 `cbb6f6cc3e5a934d8f609d69f839c4c53f554e29b0cdb5443bbe648c1df8f655`;
its already-migrated low-level emission primitives were unchanged. Symbol and
S-expression reference readers came from commit
`15f4f83d3e8dde012606c9565e4dd0e18cec40c4`, blobs respectively
`1a61c062110fd1d8aa44fccf740b9e819c583569` and
`f92e1cc0f3211cf718c3cc229fa1c64acda3db39`. Root text measurement and pin geometry
used their pure reference implementations. Capture scripts and source snapshots
remained outside the repository under `/private/tmp/schgen-board-bAvxx0`.
No Python source or runtime dependency is delivered with these fixtures.

## Verification and deliberate error hardening

The C++ runner compares emitted bytes, UUIDs, page geometry, renamed circuit
pins/NC and exact ordered reports. It also exercises immutable input copies,
stable UUIDs under reordered pages, preserved metadata, reference collisions,
unknown references, negative/overflowing bands, unsafe path components, empty
boards and oversized roots. Empty/oversized hierarchies now fail explicitly;
the Python implementation could raise an incidental `max()` error or silently
emit an unusable/omitted hierarchy. Numeric fields in existing project JSON
retain their typed values; integral `JsonNode` numbers are written canonically
without a fractional suffix.

Process-only fault injection launches the C++ test executable as a child and
checks exact argv, bounded workers, actual concurrency, input-ordered exception
propagation, joined tasks, separate scratch directories, cleanup, stderr,
nonzero/signal ERC statuses and missing reports. It never supplies a successful
netlist or substitutes a connectivity oracle. Live tests additionally generate
with the actual native placer, repeat deterministic builds, check frozen real
project subsets, and reject actual short/open/missing-part/NC/root-port mutations.
Electrical-only and visual-only failures must be visible in the result report.

C++17 release (`-DNDEBUG`, warnings as errors): **8,371 checks** offline/process,
or **8,427 checks** with real KiCad. Runtime checks are not compiled-out assertions.
The same **8,427-check live suite** also passed with ASan, UBSan and
float-cast-overflow instrumentation applied to every linked native source.
All build and live-output paths are private temporary directories.

## Build/test invocation

Add `src/board_schematic.cpp` to `schgen_core`, with `-ffp-contract=off`, retaining
the full native placement/router/emitter dependencies and the shared SoM export
source. Link `Threads::Threads` and the existing `LibXml2::LibXml2`. Add executable
`schgen_board_schematic_contracts` from `tests/board_schematic_contracts.cpp` and
link it to `schgen_core`. The tests take a fixture directory and optional KiCad
executable:

```sh
schgen_board_schematic_contracts native/tests/data/board_schematic
schgen_board_schematic_contracts native/tests/data/board_schematic \
  --kicad /opt/homebrew/bin/kicad-cli
```

Neither command reads current project circuits, regenerates a full board,
modifies shared outputs, or requires installed symbol libraries. The live form
requires KiCad itself and permission to launch its subprocesses.
