# Native migration

The target is a complete C++ generator, including design loading, placement,
routing, emission, verification, CLI, and tests. The Python extension is a
temporary migration interface. Native kernels alone do not complete the port.
Final acceptance requires zero repository-owned Python sources, tests, helpers,
bindings, or runtime dependencies. KiCad/design data, FPGA HDL, and generated
XDC/Tcl remain in their required hardware formats; generator/tooling code is C++.

## Build without Python

From the repository root:

```sh
cmake -S native -B native/build/standalone -DSCHGEN_BUILD_PYTHON=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build native/build/standalone --parallel
ctest --test-dir native/build/standalone --output-on-failure
native/bin/schgen --help
```

This is also the default configuration: Python bindings are opt-in. The build
uses C++17 and libxml2 (for KiCad netlists), without discovering Python,
installing nanobind, or fetching dependencies. Live SoM extraction requires
`kicad-cli` on PATH; it is invoked directly, never through a shell.

The native CLI supports `self-check`, `catalog-compile`, `circuit-compile`,
`project-check`, `circuit-check`, `som-interface`, `link`, `bom`, `xdc`, `vivado`, `fpga`, and
`devicetree`, `design-rules`, and `testpoints`. It does not yet generate a board.
Unsupported commands fail.

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
connectivity plus NC markers against embedded symbol geometry. Schematic
placement and full board orchestration remain transitional.

Design-rule verification (decoupling, I2C pull-ups, reset RC, configuration straps,
exposed pads), test-point coverage and their reports also run in C++. The native
commands print diagnostics, return nonzero on findings, and write a report only
when `--output` is supplied. They accept subsystem selection; board-wide pull-ups
outside the selected sheets are intentionally absent from that check.
Symbol-backed completeness remains a separate mandatory gate (`circuit-check`).
Connectivity and symbol metadata are indexed once per snapshot. Mutable caller
inputs require a new snapshot; caches never silently reuse a previous board.

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

Move complete pipeline stages into the native library and CLI. The remaining
work includes board orchestration, schematic placement, full board/schematic
emission, verification/reporting, system outputs, and authoring commands.
Replace Python tests with native tests before removing their reference logic.

Each stage must preserve electrical connectivity and its relevant gates, then
compare generated artifacts against the established reference. Record measured
end-to-end performance separately from kernel benchmarks. Remove Python source,
bindings, and Python build dependencies only once their consumers have moved.
Final acceptance requires generating both supported projects and running their
verification from a clean build without Python; pre-existing failures must be
reported, not suppressed.
