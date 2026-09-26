# Native migration

The target is a complete C++ generator, including design loading, placement,
routing, emission, verification, CLI, and tests. The Python extension is a
temporary migration interface. Native kernels alone do not complete the port.
Final acceptance requires zero repository-owned Python sources, tests, helpers,
bindings, or runtime dependencies. KiCad/design data, FPGA HDL, and generated
XDC/Tcl remain in their required hardware formats; generator/tooling code is C++.

## Build without Python

Install the pinned native zlib-ng compressor using the instructions in
[the manufacturing handoff](tests/data/manufacturing/README.md#explicit-native-installation-and-parent-wiring).
It must be the tested static/PIC compatibility build so existing PNG bytes remain
identical. Supply its installed prefix explicitly; CMake verifies the version
and a compression known-answer test rather than silently selecting system zlib.
The example below uses the local dependency installation under the ignored build
directory. From the repository root:

```sh
cmake -S native -B native/build/standalone -DSCHGEN_BUILD_PYTHON=OFF -DCMAKE_BUILD_TYPE=Release \
  -DSCHGEN_MANUFACTURING_ZLIB_PREFIX="$PWD/native/build/deps/zlib-ng"
cmake --build native/build/standalone --parallel
ctest --test-dir native/build/standalone --output-on-failure
native/bin/schgen --help
```

For repeated local C++ development with Ninja and ccache installed, run these
from `native/` (CMake 3.20+ for presets): `cmake --preset native-fast`, then
`cmake --build --preset native-fast` and `ctest --preset native-fast-offline`.
The preset keeps compiler caches under ignored `native/build/`; it neither
downloads dependencies nor enables Python. Ninja avoids Make's broad object
rebuilds when unrelated per-source compilation options change. Do not build
different build directories concurrently: they currently publish the same CLI
and catalogs in the source tree.

This is also the default configuration: Python bindings are opt-in. The build
uses C++17, libxml2 (for KiCad netlists), native zlib-ng (for exact manufacturing PNGs),
and Poppler C++/libpng (for schematic rasterization), without discovering Python,
installing nanobind, or fetching dependencies. Live SoM extraction requires
`kicad-cli` on PATH; it is invoked directly, never through a shell.

The native CLI supports `self-check`, `catalog-compile`, `circuit-compile`,
`project-check`, `circuit-check`, `som-interface`, `link`, `bom`, `xdc`, `vivado`, `fpga`, and
`devicetree`, `design-rules`, `testpoints`, `constraints`, `powertree`, `thermal`,
`part-rules`, `bom-values`, `footprint-pads`, `pin-completeness`, `symbol-law`,
`spice`, `firmware`, `manual`, `scfw`, `testplan`, `power-sequence`, and `selftest`.
It does not yet generate a complete board.
Unsupported commands fail.

`subsystem-new NAME` creates a C++ source/header/test package with retained
README, SPICE and JSON metadata. It never overwrites an existing destination.
New packages are opt-in with `-DSCHGEN_SUBSYSTEM_PACKAGES='name;another'`;
the generated CMake registration connects real factories to the immutable
native registry. The initial unimplemented builder deliberately fails its test.

The PCB verification aggregate now shares one geometry snapshot and MST across
the real placement, connector, ratsnest, fanout, return-stitch and escape gates.
Both live projects are checked against independent committed reports. This is
not yet the full-board verdict: external DRC and non-PCB gates remain separate.
The native DRC runner invokes KiCad directly with a bounded timeout and private
report directory. Missing/malformed reports and nonzero tool exits are errors,
not empty successful findings. Its transitional adapter contains no DRC logic.
Use `native/bin/schgen pcb-drc --project NAME` to check an existing board. The
full build reuses validated severity counts from its first DRC report instead
of refilling and checking the same board twice. Reports lacking severity retain
an explicit errors-only fallback; warning and unrouted findings remain visible.

`selftest` runs the complete 63-mutation suite through real KiCad exports, ERC,
native gates, geometry checks, and fresh native worker processes. It does not
invoke Python. Worker failures and missing footprint libraries fail the run;
they cannot count as mutation kills. The separate `self-check` remains only a
small kernel smoke test. Live contract tests carry the `live-kicad` CTest label.

The native core includes complete floorplan search/compose/export, immutable
PCB-check snapshots, and board/project/design-rule emission. Frozen independent
fixtures verify both projects' exact outputs and mutation/error cases. The
transitional PCB pipeline now uses the native writers and shares one prepared
snapshot across its PCB gates, avoiding repeated source parsing. Standalone gate
calls still prepare fresh inputs; no global cache hides placement or file edits.
The original return-path-v1 failures remain separate from return-stitch coverage;
this migration does not waive them. Floorplan and placement orchestration still
need their final native CLI integration before the full-board command is native.

```sh
native/bin/schgen project-check --project carrier
native/bin/schgen project-check --project devkit_mini
native/bin/schgen circuit-check --project devkit_mini
native/bin/schgen design-rules --project devkit_mini
native/bin/schgen testpoints --project devkit_mini
native/bin/schgen fpga --project carrier --output /tmp/carrier-fpga
native/bin/schgen devicetree --project carrier --output /tmp/carrier_pl.dtsi
native/bin/schgen bom --project carrier --qualified-refs --output /tmp/carrier-bom.csv
```

`fpga` generates XDC and Vivado Tcl from one live extraction, validating both
before publication. Each output is atomically replaced. Project selection is
explicit (`--project`), then `SCHGEN_PROJECT`, then `carrier`; use `--repo` when
running outside the repository root. Circuit discovery and loading require
canonical `<project>/subsystems/<name>/circuit.json`, not authoring Python.
Function/rail/strap policy is in each project's `som_mapping.json`.

`circuit-check` resolves actual library symbols and checks every pin and internal
input driver; JSON pin metadata is not a substitute for physical symbol pins.
`link` also enforces symbol-backed completeness before linking. The native core
now includes complete symbol loading, schematic emission, routing, netlist and visual
validation stages, tested against frozen inputs and output bytes. Netlist verification
shares the hardened KiCad process/XML boundary with SoM extraction, and checks
connectivity plus NC markers against embedded symbol geometry. Full board
orchestration remains transitional.
The hierarchical schematic stage is independently available as
`native/bin/schgen board-schematic --project NAME -o DIRECTORY`. It generates
the real routed sheets and root hierarchy, preserves persistent reference bands,
and runs live KiCad connectivity checks. Per-sheet exports use bounded workers
with deterministic result collection. This command is not a substitute for the
remaining PCB, manufacturing and complete-board verification stages. Both
supported projects' native root and child schematics match the committed bytes.

The complete schematic placer now runs natively: topology classification,
fanout, regulator templates, chain layout, probe rows, retry expansion and
pagination all use the same typed engine and router. Frozen full-board and
isolated topology contracts cover ordered geometry and page boundaries. The
legacy Python engine is removed; remaining adapters preserve caller-owned
symbol snapshots and intermediate page metadata without reloading sources.
Native mutation proofs exercise missing-decoupler and incorrect clamp-layout
failures through the real completeness, routing and visual gates.

Design-rule verification (decoupling, I2C pull-ups, reset RC, configuration straps,
exposed pads), test-point coverage and their reports also run in C++. The native
commands print diagnostics, return nonzero on findings, and write a report only
when `--output` is supplied. They accept subsystem selection; board-wide pull-ups
outside the selected sheets are intentionally absent from that check.
Symbol-backed completeness remains a separate mandatory gate (`circuit-check`).
Power-tree analysis and SVG, thermal analysis with emitted-copper evidence, and
part-rating checks now execute in C++. Frozen report contracts cover both projects,
policy mutations and supplied power results. Thermal credit requires real copper
evidence; an absent PCB does not silently grant cooling credit. Transitional
adapters preserve caller-owned policy tables and typed numeric fields.
BOM-value normalization, footprint-pad coverage, pin/NC completeness, symbol
provenance and analytic/SPICE checks also run natively. Their frozen contracts
include poisoned values, disconnected pins and malformed geometry. Optional
ngspice cross-checks use a shell-free bounded process with private temporary
decks and real measurements; absence of ngspice retains the analytic gate.
Connectivity and symbol metadata are indexed once per snapshot. Mutable caller
inputs require a new snapshot; caches never silently reuse a previous board.

Bring-up facts, firmware contracts, SC scaffolds, the manual, test plan and
power-sequence SVG now use native typed inputs. Independent fixtures cover both
projects and changes to GPIOs, feedback values, addresses and required sheets.
Live U9 extraction remains authoritative. The sequence walker rejects reachable
cycles instead of looping indefinitely. Generated SC code still has a known
undefined FMC EEPROM macro, and RTC battery/charging guidance is inconsistent;
these pre-existing output defects are not treated as successful compile checks.

Carrier and devkit XDC/Tcl, and carrier BOM, match the established output bytes.
Device-tree output changes only generator/source provenance comments. Native
contract tests cover extraction, mapping, linking, project isolation, rendering
and validation failures. Full board orchestration remains transitional.
The full transitional carrier and devkit builds pass. The devkit's two missing
I2C pull-ups and nine uncovered probe requirements are corrected with physical
parts, without new waivers. Probe-only ports now export hierarchical sheet
connections; regulator discovery excludes measurement pads, and PCB placement
handles connector-sheet auxiliaries without moving the fixed mezzanines.

`scripts/build_native.sh` still builds the transitional Python bindings. Both
executables link the same `schgen_core` library; the engine sources compile
once per build directory. Preserve the per-source floating-point settings:
these are part of the deterministic-output contract.

Build catalogs depend on their JSON inputs and regenerate when those inputs change.
Compilers publish complete catalogs by atomic replacement, so existing mapped
readers retain their snapshot during a rebuild. Close and reopen a catalog to
read its new version. Failed publication leaves the previous file untouched.
The transitional circuit adapter uses project-scoped `native/circuits.bin`
outputs under each project, while the parts catalog is shared. Native project
commands read validated JSON directly and do not depend on interpreter caches.
Build directories share the in-tree binary and catalog outputs, so build them
sequentially.

## Remaining migration

The native `pcb-stage --project NAME -o DIRECTORY` command now performs live
KiCad netlist extraction, immutable input loading, floorplanning, placement,
escape planning and PCB/project/rules emission. It is a construction stage,
not a replacement for the independent full-board gates. Live contracts compare
both project PCBs byte-for-byte with their existing generated references.
Native manufacturing contracts cover assembly planning, Markdown and all 52
reference PNGs. Assembly rendering uses at most four workers with stable output
ordering; a measured 38-image carrier run improved from approximately 0.97 s to
0.39 s, including transitional transport and file publication. This is an image
stage measurement, not an end-to-end board-build speedup claim.
The equivalent ratsnest run (36 PNGs plus SVG) measured approximately 1.79 s
through the previous renderer and 0.68 s through the bounded parallel C++
renderer, with all output bytes unchanged.

Standalone `assembly`, `ratsnest`, `si-constraints`, `fab-profile` and `manifest`
commands now use native implementations. Explicit output directories retain the
project layout (`docs/`, `renders/`, `manufacturing/`). `preflight` uses native
stock/price/alternate analysis and a shell-free HTTPS-only `curl` subprocess;
it requires network access only when that optional command is invoked. Transport
errors fail explicitly instead of being reported as a confirmed missing part.
Its offline contracts use injected provider responses and never contact vendors.

Move complete pipeline stages into the native library and CLI. The remaining
work includes full-board orchestration, remaining independent verification and
reporting, system outputs, authoring commands and removal of transitional adapters.
Replace Python tests with native tests before removing their reference logic.

Each stage must preserve electrical connectivity and its relevant gates, then
compare generated artifacts against the established reference. Record measured
end-to-end performance separately from kernel benchmarks. Remove Python source,
bindings, and Python build dependencies only once their consumers have moved.
Final acceptance requires generating both supported projects and running their
verification from a clean build without Python; pre-existing failures must be
reported, not suppressed.
