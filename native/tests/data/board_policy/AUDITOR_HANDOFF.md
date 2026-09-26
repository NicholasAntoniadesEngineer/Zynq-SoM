# C++ source-auditor correction checkpoint

This change fixes census identity/coverage, not the remaining board precision
policy. It does not declare providers, register non-scalar callbacks, exempt
files, alter board arithmetic, or make the complete board audit pass.

## Owned integration surface

- `native/src/native_cpp_audits.cpp`: implementation only; public ABI unchanged.
- `native/tests/native_cpp_auditor_contracts.cpp`: new independent executable.
- `native/tests/native_audits_contracts.cpp`: retain all existing source mutation
  tests and explicitly scan the new `quantize.hpp` policy-storage owner. Its
  production census remains eight constants and twenty implemented functions.
  Optional `--sources-only` runs only this existing source-audit suite; the
  default full-suite behavior remains unchanged.

Parent can add the new test using the existing core target and test conventions:

```cmake
add_executable(schgen_native_cpp_auditor_contracts
    tests/native_cpp_auditor_contracts.cpp)
target_link_libraries(schgen_native_cpp_auditor_contracts PRIVATE schgen_core)
add_test(NAME schgen_native_cpp_auditor_contracts
    COMMAND schgen_native_cpp_auditor_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
```

Apply the project's strict compiler flags to this target as usual. The optional
repository argument adds actual floorplan/header/breathe scans to the synthetic
compiler mutation suite. No argument runs only the self-contained fixtures.
Clang remains a real runtime dependency of these compiler tests. Nothing was
added to main CMake, module/CLI, shared builds, or commits by this worker.

## Identity and storage contract

Unambiguous function keys keep their existing spelling, e.g.
`policy.cpp::policy::snap`. Overloaded functions have exact compiler type
signatures, e.g. `policy.cpp::policy::snap [double (double)]` and
`policy.cpp::policy::snap [double (int)]`. Equal type spellings belonging to
different compiler entities also retain their mangled identity. An ambiguous
short registration is stale and cannot cover any overload. Out-of-line methods
use Clang's semantic class context, including a declaration from a header.

Nested lambda bodies do not inherit the enclosing scalar operation's
registration. They have `<lambda@BYTE_OFFSET>` keys. Distinct block-local
constants sharing a name gain `[at BYTE_OFFSET]` suffixes. Residual ambiguous
constant identities fail coverage explicitly. Source offsets are deliberately
not an invitation to register a mutating/non-scalar function: extract the actual
precision operation or specify a genuine compiled non-scalar proof contract.

Mutable, non-uppercase instance fields with literal zero/value initialization
are ordinary state. This rule does not exempt nonzero engineering defaults,
const/constexpr zero, uppercase locals, static locals, enums, or namespace
policy storage. Numeric typedefs preserve this distinction. A declaration's
exact reviewed cover now satisfies a buried constant; absence of live ledger
recording, a renamed/deleted declaration, uncovered siblings, and all raw or
banned precision operations still fail independently.

The coordinated board-policy test now accepts its exact covered-buried census
entry and separately rejects an uncovered buried engineering entry. That edit
belongs to the board-policy owner, not this tranche.

## Independent proof

Scratch directory: `/private/tmp/native-auditor-proof.kHBwrB`.
Preserved dependency archive:
`/private/tmp/schgen-board-policy.4YFXrh/libschgen_core.a`.
The updated auditor object is linked before this archive. No shared build output
is read as a mutable linker input or written.

- Original archive with the new adversarial test fails on the first unrelated
  overload, proving the pre-fix defect (`before`).
- `after REPO`: **40 checks PASS**, including four real-source assertions.
- `existing REPO --sources-only`: **55 checks PASS**, retaining all nineteen
  original source mutations plus actual quantize source/header coverage.
- `sanitized`: **36 fixture checks PASS**, with ASan/UBSan on the auditor and new
  test translation units. The preserved supporting archive is not instrumented;
  this is not a claim of whole-engine sanitizer coverage.

All new compilation uses C++17, `-Wall -Wextra -Wpedantic -Werror` and
`-ffp-contract=off`; the proof target also uses the archive's macOS deployment
target, `-mmacosx-version-min=26.6`. The existing combined audit-test executable
additionally links `native/tests/native_accounting_contracts.cpp` and `-lxml2`.
Only its source-audit mode was executed against the preserved archive, avoiding
unrelated producer ABI drift.

`production.log` is a real compiler scan of `floorplan_internal.hpp`,
`floorplan_cross.cpp`, and `pcb_placement_breathe.cpp`. Both `Engine::estimate`
bodies scan without aborting. `Engine::raw_area` is correctly absent from policy
constants. With intentionally empty policy registries, the report is **FAIL**:
37 constants and sixteen unique raw-precision diagnostic lines. In particular,
the report retains `Placer::breathe::eps` and `::step`, ten rounding lines in the
vector-argument `Engine::estimate`, two rounding lines in breathe's pair-returning
lambda, two float-to-integer lines, and two final-coordinate rounding lines.
The four `CrossPart::Owner` enum tags also remain conservatively visible; no enum
waiver was introduced. These are scan facts, not inferred declarations.

Source SHA-256 at the frozen compile checkpoint:

```text
69e7c084e6c0bf919f51c5e39245ffb8572dc47a32c696cc971b6ceda4b1461a  native/src/native_cpp_audits.cpp
8506f92b2ca595d100ac30ab4e15848a5ae3a3021420812a9e573c877180198f  native/tests/native_audits_contracts.cpp
8c489b8a85f1fe45a9d0e7944cec26d5a116a3645ea2f54fa68214f4118ebd6b  native/tests/native_cpp_auditor_contracts.cpp
```
