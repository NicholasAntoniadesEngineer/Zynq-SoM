# Native net-contract header: stable handoff

New files only: `include/schgen/net_contract.hpp`, `src/net_contract.cpp`,
`tests/net_contract_contracts.cpp`, and `tests/data/net_contract/legacy_reference.json`.
No firmware, CMake, main, project CLI, registry, shared build, or Python file changed.

## Usable production path

```cpp
#include "schgen/net_contract.hpp"
const auto paths = schgen::resolve_project_paths(repository, project);
const auto input = schgen::load_net_contract_input(paths);
const auto document = schgen::write_net_contract_header(input, output_header);
// document.som / document.rails contain original names and emitted identifiers.
```

The loader reads actual canonical authored IR and the selected SoM JSON through
the existing native loaders. A caller with freshly authored C++ IR can construct
`NetContractInput` directly. Pure rendering never reopens files or invokes an
authoring process. The explicit writer renders fully before atomic publication.
There is no hard-coded net inventory, Python import/subprocess, snapshot lookup,
implicit carrier output, or modification of circuit/package inputs.

Generated C++17 headers expose `schgen_nets::SOM::<identifier>` and
`schgen_nets::RAILS::<identifier>` as inline constexpr string_views, plus sorted
`som_names` / `rail_names` arrays. A validated alternative namespace, including
`board::nets`, is supported. Fully qualified `::std` avoids a net named `std`
shadowing the implementation's types. Repeated inclusion and multiple translation
units are tested by actual compile/link/execution.

All SoM connector pin-net names are deduplicated. Rails are exactly POWER-class
names beginning with `+`, deduplicated across sheets. No ground, signal, port, or
unprefixed POWER net is silently promoted to a rail. The two namespaces are
independent, so `+3V3` can occur in both.

## Explicit identifier policy

Safe ASCII legacy identifiers are unchanged: `+` becomes `P`; punctuation and
`-` become `_`. Empty names become `net_empty`. Keywords, leading-underscore or
double-underscore identifiers, non-ASCII names, and the standard `NULL` macro
name use `net_x` followed by lowercase hex of every original name byte. The
original value is never changed: explicit-length string_views preserve UTF-8,
embedded NUL, quotes, backslashes, control bytes, and arbitrary byte values.
Fixed-width octal literals cannot absorb adjacent digits; question marks are
escaped to avoid compiler trigraph diagnostics.

Distinct names that map to one identifier fail explicitly within their domain;
there is no last-writer-wins, dropping, or unreviewed suffixing. This includes
`A-B`/`A_B`, `+3V3`/`P3V3`, and escaped names colliding with literal `net_x...`
names. Invalid namespace/collision failures preserve existing output bytes.
Output must have a C++ header extension. Symlinks and non-file destinations are
refused; publication uses the existing atomic native writer.

## Independent capture and proof

The immutable JSON reference was captured before implementation by executing
the **unmodified AST** of `_net_ident` and `cmd_nets` from `schgen/__main__.py`.
Only input transport was isolated: actual project canonical JSON was read
independently, and legacy `nets.py` outputs were written under private scratch.
The native generator and Python extension were not used for this capture.
Both captured function hashes are retained in the fixture. There are 35 original
identifier edge cases, independently reviewed native expected identifiers, and
full legacy project name/identifier inventories:

- carrier: **213 SoM names, 27 rails**;
- devkit_mini: **213 SoM names, 11 rails**.

Reference SHA-256:
`996638fbd98dd94aa72ef8798f6f94ef76076b57d9e716550de7784cc3764669`.

**1,334 assertions PASS. Six generated C++17 headers compile/link/execute across
two translation units each; 964 exported names are checked byte-for-byte with
independent numeric static_asserts.** Cases include both live projects, two
live-input mutations, adversarial names, and an empty inventory. Both projects
are also authored afresh using every registered native factory and compared to
the independent legacy inventories. A JSON-only private mirror proves that
Python constructors/catalog discovery are not required by the loader.

Additional checks: shuffled order and duplicates, new live rails and SoM names,
class/prefix exclusion, collision errors in both domains, no Python output,
missing/malformed SoM input, invalid namespaces, safe explicit replacement,
symlink/directory rejection, and preservation on I/O failure. The test uses a
unique private child directory on every invocation and requires a real C++
compiler (`CXX` executable or `c++`); no compiler skip is permitted.

Private executable: `/private/tmp/net-contract.1kEC29/contracts`.
Command: `contracts REPOSITORY PRIVATE_SCRATCH`. C++ compilation used C++17,
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`, macOS deployment 26.6,
the existing archive, libxml2, and pthread. No shared build was run.

## Exact parent integration

Add `src/net_contract.cpp` to `schgen_core`, with the normal strict options.
The existing project, circuit, SoM, authoring, and atomic-writer implementations
supply all dependencies; no schema/public-layout change is required.

```cmake
add_executable(schgen_net_contract_contracts tests/net_contract_contracts.cpp)
target_link_libraries(schgen_net_contract_contracts PRIVATE schgen_core)
target_compile_options(schgen_net_contract_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_net_contract_contracts COMMAND schgen_net_contract_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/.."
    "${CMAKE_CURRENT_BINARY_DIR}/net-contract-contract-output")
```

Parent CLI hookup: add `nets` with existing project/repository selection and
explicit `-o HEADER` (recommended required, avoiding unexpected source writes),
then call the production path above. Report the returned domain counts; exceptions
must produce nonzero status. No new module binding is necessary for native use.
Do not advertise a native `nets` command until this hookup is present. Do not
delete the old Python command or `carrier/nets.py` before integrated proof.

## Remaining old CLI inventory (excluding already-owned families)

Most old commands already have native cores/frontends. Remaining name/entry-point
differences are integration edges, not reasons to duplicate them:

- `floorplan [--export]`: native floorplan construction/report/export APIs exist;
  standalone publication/round-trip CLI remains to be wired with its owner.
- `pcb [--no-drc]`: native `pcb-stage`, DRC, and full-board paths exist; old-command
  compatibility/output policy belongs with parent/board ownership.
- `subsystem new`: native `subsystem-new` is integrated; only alias/help policy.
- `subsystem-check [--strict]` / `carrier-check`: native structure APIs already
  exist in `authoring_gates.hpp`; legacy package-policy CLI wiring belongs with
  parent/Copernicus and must account for the C++ package transition.

Firmware/manual/scfw/testplan, BOM, preflight, link, constraints, power/thermal/
part/design/SPICE checks, XDC/Vivado/devicetree, gallery/manifest/ratsnest/render,
SoM extraction, and selftest have native implementations. CLI help/check and
source-purity work are reserved to the parent; board/compose/experiments/build/
devkit/part/CI are excluded from this worker's inventory scope. The next assigned
independent family is the nine authored-document consistency contract groups.
