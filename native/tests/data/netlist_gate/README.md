# Native netlist verification contracts

These fixtures are data only: frozen circuit IR, self-contained KiCad
schematics, actual KiCad XML exports, and exact ordered reference reports.
There is no Python source, interpreter dependency, or runtime fallback here.
Tests do not load changing project circuits, rebuild boards, or write shared
repository outputs.

## API and integration

`schgen/netlist_gate.hpp` exposes:

- `ExtractedNetlist`: ordered `(name, vector<KicadNetlistPin>)` records; pins
  retain their separate reference/number strings, including empty attributes.
- `NetlistGateResult`: `ok`, `shorts`, `opens`, `nc_cheats`, `part_mismatches`,
  `name_mismatches`, and the exact original `summary()` text.
- `parse_netlist_xml(xml, source)` and `extract_netlist(schematic, options)`.
- `check_netlist(circuit, extracted, schematic_text)` for in-memory checking.
- `check_netlist(circuit, schematic_path, options)` for live export + checking.
- `normalize_netlist_name`, `dead_two_terminal`, and `emitted_nc_cheats`.

The live gate always exports the supplied schematic. `NetlistExtractOptions`
has `kicad_cli` (PATH name or literal executable path, not a shell command).
Failures throw `NetlistGateError`; malformed XML/NC geometry never yields PASS.
Shared transport diagnostics remain those of the existing SoM exporter.

The only existing implementation changes are narrow public wrappers in
`som_interface.hpp/.cpp`: `export_kicad_netlist_xml` and
`parse_kicad_netlist_xml`. All consumers share the existing argv-only process,
private RAII temporary directory, stderr capture and secure libxml2 parser.
DTDs are forbidden, with no external entities or network loading. No second
process launcher or XML parser was introduced.

The offline/process contracts are registered in CMake. Run the optional live
contracts explicitly with `--kicad /path/to/kicad-cli` in an environment that
permits KiCad subprocess execution. Equivalent registration:

```cmake
target_sources(schgen_core PRIVATE src/netlist_gate.cpp)
add_executable(schgen_netlist_gate_contracts tests/netlist_gate_contracts.cpp)
target_link_libraries(schgen_netlist_gate_contracts PRIVATE schgen_core)
target_compile_options(schgen_netlist_gate_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror)
add_test(NAME native_netlist_gate_contracts
    COMMAND schgen_netlist_gate_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/netlist_gate")
add_test(NAME native_netlist_gate_live_contracts
    COMMAND schgen_netlist_gate_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/netlist_gate"
    --kicad kicad-cli)
```

`schgen_core` already includes the required `som_interface`, `symbols`,
`sexpr`, `occupancy`, `turn`, circuit/JSON and libxml2 dependencies. No binding,
main or module is required by the standalone contracts. The transitional adapter
now dispatches extraction and all netlist decisions to this same core. Call
`validate_circuit(circuit, library)` separately: the netlist gate deliberately
exempts only NC-only missing parts and is not a
substitute for symbol-backed pin completeness, visual validation or ERC.

## Intentional correction after the parity baseline

The legacy gate exempted any missing part with at least one NC declaration,
even when another pin carried a declared internal signal. That could return
PASS for a completely absent component. The native gate now requires an exempt
part to have no netted pins. A regression first reproduced the false PASS;
another retains the legitimate NC-only exemption. NC and netted reference sets
are indexed once, replacing the per-part scan through NC declarations.

The frozen source reports remain untouched. `empty_export` and
`power_pseudo_ref` now additionally require `U1: missing from extracted netlist`;
tests assert that diagnostic separately and compare every original category.
The 12,000-case parity result below records the pre-correction baseline, not a
claim that this intentional behavior change matches the old implementation.

## Provenance

Captured 2026-09-18 with KiCad CLI 10.0.2. The reference was
`schgen/verify/netlist_gate.py` at commit
`15f4f83d3e8dde012606c9565e4dd0e18cec40c4`, Git blob
`a4a66d794ae33d336222d69007f4fc4c635b2a5d`, SHA-256
`007389fa5046a1a6f2ac9dcd4c288f2654d06f8cb0790d29b0255957e4f2abae`.
All capture/differential scripts and reference source were external to the
repository, in `/private/tmp/schgen-netlist-GEb7dn` during migration.

For an independent oracle, the frozen reference used the same commit's pure
Python `sexpr._loads_py` and `symbols.pin_page_position_py`, not their current
native-dispatch replacements. Their source Git blobs are respectively
`f92e1cc0f3211cf718c3cc229fa1c64acda3db39` and
`1a61c062110fd1d8aa44fccf740b9e819c583569`.

- `carrier_board_services`: snapshot of `carrier/schematic/board_services.kicad_sch`
  and `carrier/subsystems/board_services/circuit.json` (9 parts, 9 declared nets).
- `devkit_uart_bridge`: snapshot of `devkit_mini/schematic/uart_bridge.kicad_sch`
  and `devkit_mini/subsystems/uart_bridge/circuit.json` (10 parts, 11 declared nets).
- The board snapshots retain all original symbol definitions, placements,
  wires, labels and NC markers. To export a child independently, only instance
  project/path metadata was changed to its own root UUID, and a root
  `sheet_instances` record was added. Without this adaptation KiCad omits
  anonymous internal nets when exporting a child out of its board context.
- Their frozen IR uses board-annotated references, using the original
  `board._renamed_ref` rule (`index * 1000 + local number`), with bands 3 and 11.
  Part refs, net pin refs and NC refs were transformed; the gate does not
  normalize or waive reference mismatches. Original board source Git blob:
  `5ccfc1dbe81a1bc6bf73b36fda679d1dbce7e054`.
- `m1_rc`: the existing `schgen.tests.m1_rc.build()` design, copied from the
  independently captured native schematic-emitter fixtures. Its full IR and
  schematic are frozen here, not imported from another changing test suite.
- `m1_short.xml`: actual KiCad export after adding the original test's wire
  `(101.6,77.47)` to `(101.6,85.09)`.
- `m1_open.xml`: actual export after deleting the original test's wire
  `(101.6,91.44)` to `(101.6,97.79)`.

All XML bytes are retained, including KiCad's capture timestamps and source
paths. Tests compare every extracted name/pin and their order, not volatile
metadata. `cases.json` contains 47 exact report cases and 9 extraction cases;
SHA-256 `9d1c4c0451f9d1b7b0caf7f7c128e3497be8661484cf4eae00e5b43b4cb9084a`.

## Verification

Standalone C++17 release build (`-O2 -DNDEBUG`, warnings as errors): 85
offline/process contracts, or 91 with `--kicad /path/to/kicad-cli`.
The 91-contract live suite also passed ASan, UBSan and float-cast-overflow
instrumentation. Assertions remain active under `NDEBUG`.

The frozen cases cover shorts, split/stranded/missing/empty-name opens, all
public net classes, lost labels, missing refs and explicit NC, dead C/R/L
prefixes, duplicate last-write semantics, XML ordering/missing fields/namespaces,
quoted names, rotations, recursive embedded units, coincident pins, rounding,
stray/forbidden/valid NC markers, and combined five-category report ordering.
Additional native cases exercise secure XML rejection, malformed NC geometry,
literal argv boundaries, spawn failures/signals/missing output, scratch cleanup,
and large process output without pipe deadlock. The transport probe is not a
connectivity oracle: physical short/open/NC tests invoke real KiCad.

A separate external differential run compared all five ordered finding arrays
and complete summaries for 10,000 randomized connectivity cases plus 2,000
randomized NC geometry cases, seed `0x4e45544c`: all 12,000 matched the frozen
pure-Python reference. The existing 27 SoM extraction contracts also passed
after factoring the shared boundary. No full-board regeneration or shared
build output was used.
