# Native package retirement and placement-metadata contracts

Owned files only: the existing `authoring_gates_contracts.cpp`, new
`placement_metadata_contracts.cpp`, and this handoff. No production authoring,
geometry, gates, regression sources, CMake, main/CLI, shared builds or commits
were changed. The metadata checker is test-local repository policy, replacing
the corresponding pytest assertions, not a new production geometry validator.

## Parent registration

The existing `schgen_authoring_gates_contracts` / `native_authoring_gates_contracts`
target, registration and REPOSITORY argument are unchanged. Rebuild it coherently.
Add only this new family:

```cmake
add_executable(schgen_placement_metadata_contracts tests/placement_metadata_contracts.cpp)
target_link_libraries(schgen_placement_metadata_contracts PRIVATE schgen_core)
target_compile_options(schgen_placement_metadata_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_placement_metadata_contracts
    COMMAND schgen_placement_metadata_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_tests_properties(native_placement_metadata_contracts PROPERTIES TIMEOUT 120)
```

Both commands require the built native part catalog and actual repository data.
They require no Python, shell, KiCad subprocess, rendering or cached board. Missing
catalogs, contracts, factories, metadata or policy evidence fail; there are no
skip paths or expected-failure waivers.

## Existing authoring gate cleanup

Actual repository checks now explicitly use `AuthoringPackageMode::native_assets`
for all 17 library and 49 project packages, using the real native registry.
Canonical JSON companions are still compared against freshly authored circuits,
and original independently captured circuit expectations remain intact.

Legacy layout/discovery and exact report checks now run only in an inert private
fixture tree. The immutable oracle chooses its package population and adapter/
local shape; `.py` names contain a deliberately non-executable marker, never a
copy of a retained Python implementation. Actual native factories still produce
the circuits. Independent companion JSON bytes are copied as test input, not
used as constructor implementations. Legacy summary comparisons are exact;
published bytes must also match exactly including the final newline. Only the
expected package path prefix is relocated, as in the original contract helper.

Existing isolated mutation cases are retained. The no-Python native asset tests
still exercise missing files/factories, malformed or changed companions, changed
factory output, duplicate registrations/interfaces, missing adapters, bad
metadata, exceptions and unregistered folders.

The three independent report/circuit oracle files were not edited. SHA-256:

```text
810621d8f44e273ee946683a3af9cb7b714e26ab3f1378c4e2db5c499c213703  gate_library.json
8690dccb5809506c3e7b9ebe5948635e90bf57fc5867c662da2f47907fe3a57a  gate_carrier.json
56c12f2515b40d63e3a67adac60734b8c679bbcebbc9c9a7ee5aa8b33976ed75  gate_devkit_mini.json
```

## New metadata coverage

Original non-geometric policy sources were inspected in full before the port:

```text
d30bd37ed723b8e1979159de88b548b700887096f543095368a56628d3695beb  schgen/tests/test_lightweight_contracts.py
3d2eeb47434f384cb99706fd6ee2e0ac5ab366b126168bee9b78517889c48239  schgen/tests/test_hs_family_contracts.py
```

The native test constructs ten fresh carrier circuits through
`native_project_factories`, consuming the live part catalog. It reads actual
library-first placement-contract JSON and native project configuration. It never
loads a circuit catalog or `circuit.json` for these circuits.

- Lightweight: `lcd`, `microsd`, `uart_bridge`, `usb_jtag`, `usbc_otg`,
  `pd_input`, `pmod`. Covers sheet/subsystem identity, lightweight tier,
  external near-max-only policy, allowed structure types, judgment/nonblank basis,
  proximity anchor/members/positive distance, same-side IC population, references,
  roles, dossier anchor-pin membership and configured wiring.
- Critical: `hdmi_tx`, `camera`, `hdmi_rx_term`. Covers placement/v2,
  non-lightweight status, citations, every structure and near/far threshold basis,
  known structure types, authored references and configured wiring.
- USB-JTAG: exactly one proximity structure whose members are exactly `Y1`,
  anchored at `U1`, pins exactly `19`/`20` (order-independent), exactly 5.0 mm,
  and crystal-specific basis. A one-ULP distance mutation fails.
- Additional defensive assertions reject malformed typed JSON shapes, nonfinite
  distances and blank evidence. They do not change any production gate/API.

Every named policy has a negative mutation; an explicit 33-policy census catches
missing mutation coverage. The 696 negative cases mutate JSON and separately
remove authored parts/pin tables, proving that fresh IR matters. Every original
input is rechecked after its copied mutations. Valid swapped crystal pins and
evidenced external terms are positive controls. Existing placement/flow geometry,
footprint-pad, real-board discovery and report contracts remain the responsibility
of their existing native families; none of those algorithms is duplicated here.

## Isolated proof

- Authoring: **4,196 assertions PASS**, strict and ASan/UBSan.
- Metadata: **1,563 assertions PASS**, strict and ASan/UBSan; ten fresh circuits,
  696 rejected mutations, 33 policies.
- Both suites also pass with identical counts against a private 245-file asset
  tree containing **no `.py`, `.pyc` or `.so` files**. This proves Python-file
  deletion readiness without changing the user's checkout.
- Metadata additionally passes strict and sanitized with every canonical
  `circuit.json` in a second Python-free asset tree deliberately invalid. Thus a
  cached circuit snapshot cannot be its circuit source.

Proof directory: `/private/tmp/native-retirement-contracts.XgEtuG`.
Executables: `authoring-strict`, `metadata-strict`, `authoring_gates-asan`,
`placement_metadata-asan`.
Python-free input tree: `/private/tmp/schgen-no-python-assets-hEsZHK`.
Python-free poisoned-circuit tree: `/private/tmp/schgen-no-python-assets-KDEv1Y`.
The C++ asset-copy proof helper and sanitizer build script are retained privately.

Strict tests used a private immutable copy of the existing core archive, SHA-256
`e26211c85bc7434300e96d5f0be26db2fa71998f32aaf2ffdf26eda9e8832786`.
Sanitizer tests freshly compiled **all 60 repository sources in the union of
their link-map closures**, plus each test, from a private source/header snapshot.
No uninstrumented repository archive was used for sanitizer proof. System LibXml2
and OS libraries remain system binaries. The source snapshot also includes the
concurrent production author's header separation; no edits to it were needed.

Compiler flags: C++17, `-O1 -g -Wall -Wextra -Wpedantic -Werror -ffp-contract=off`,
with `-fsanitize=address,undefined -fno-omit-frame-pointer` for sanitizer builds.
Runtime options: `ASAN_OPTIONS=abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1`.
This macOS proof does not claim unsupported LeakSanitizer coverage.

Run either test executable with exactly one argument: repository/input-tree root.
Do not run the authoring companion-consistency suite against the deliberately
poisoned metadata-only tree; rejecting those companions is its correct behavior.
None of these focused results claims full-board pipeline acceptance.

Frozen source SHA-256:

```text
2a423fa07ea6279897c2018c10ed5b83309a8960b072e84a5fd985ed2288bb35  authoring_gates_contracts.cpp
c2e440c1e96a614b3f9aef68c3dfb3bc35b815434af53805dd69acf310f96bf4  placement_metadata_contracts.cpp
```
