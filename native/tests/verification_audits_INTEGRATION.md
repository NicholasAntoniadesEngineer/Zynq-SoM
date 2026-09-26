# Native policy/state audits — parent integration handoff

## Final path (no Python inputs, interpreter, or Python parser)

Include `native/cmake/native_audits.cmake` and call
`schgen_add_native_audits(schgen_core)` from the parent-owned build. It adds:

- `native_audit_state.cpp`: build-owned ledger, fallback event log, quantization registry/counters.
- `native_audit_accounting.cpp`: checked measured-count imports, event/checkpoint state and atomic replay-safe receipts.
- `native_audit_registry.cpp`: ten actual fallback declarations and twenty executable transform registrations.
- `native_audit_quantize.cpp`: the three previously adapter-only transforms, refit rounding and checked integer argument boundary.
- `native_cpp_audits.cpp`: live C++ compiler/preprocessor source auditing.
- `verification_audits_counts.cpp`: lossless baseline integer handling and exact fallback ratchet publication.

Public entry points are in `include/schgen/native_audit_state.hpp` and the shared
count/result declarations in `include/schgen/verification_audits.hpp`.
The final target does **not** compile `verification_audits.cpp`,
`verification_audits_syntax.cpp`, or link tree-sitter. It needs only the existing
core archive and a Clang driver supporting `-ast-dump=json` at audit time.
The production algorithms never load test fixtures. Source audit invokes only
the supplied native compiler through the existing shell-free process boundary.

### Required wiring (parent-owned files were not changed)

1. Own `NativeLedger`, `NativeFallbacks`, and `NativeQuantizations` in the native
   build context. Register fallback/quantization metadata once with
   `register_native_fallbacks` / `register_native_quantizations`.
2. Populate ledger declarations from the reviewed native decision metadata,
   retaining kind, step, ordered inputs, expression, repeated flag and live
   assumption resolvers. The existing `floorplan_ledger.cpp` declaration table is
   parent-owned; this change does not duplicate or silently replace it. Replace
   old `alias.CONSTANT` covers with actual C++ symbol keys, e.g.
   `native/src/quantize.cpp::schgen::kGridMm`. Do **not** manufacture declarations
   from scanner results: an unregistered constant must fail the gate.
3. Route real step entry/exit and calculations through `NativeLedger`; route
   actual fallback firings through `NativeFallbacks::record`. Snapshot/restore
   fallback state around rejected exploratory passes. Restore/reset requires a
   quiescent build; the ledger itself is single-owner, while fallback record and
   quantization engagement operations are mutex-protected.
4. Import existing measured `plan.accounting`, zone and stage result deltas via
   `NativeAccountingInbox::merge_once`, without replaying the math. Follow the
   exact emitted-label/parent-child ownership boundaries in
   [native_accounting_INTEGRATION.md](native_accounting_INTEGRATION.md).
   Only for an execution not already counted by its producer, route transform
   entry through `NativeQuantizations::invoke(name, arguments)`.
   Registration names retain the original census
   names (`outline_grow_step`, `outline_fine_grid`); the callbacks invoke the
   existing native functions with the caller's actual origin, base, step, unit,
   and value. Three grid helpers and the exact integer-step boundary have
   additional native registrations. Nonintegral/nonfinite/out-of-range steps
   throw rather than silently narrow. Evaluation errors propagate.
5. Call the production overload
   `check_native_audits(root, manifest, ledger, quantizations, compiler_options)`.
   Supply the complete reviewed C++ decision-file/header manifest and the real
   build's include paths, defines, target/sysroot flags. Use absolute flag paths
   (driver flags retain the caller's working-directory semantics). The audit
   forces C++17, disables contraction, and does a live syntax-only AST scan plus
   preprocessing. It does not build binaries or write into shared build paths.
6. Call `check_fallback_ratchet(fallbacks.census(), caller_baseline_path)` and
   honor `ok`. Missing/corrupt baselines retain the original first-run pin;
   regressions never modify the file; passing ceilings only decrease. This
   function **does** publish the authorized baseline, so keep the caller path.

All twenty transform definitions are covered by these two decision files:
`native/src/quantize.cpp` and `native/src/native_audit_quantize.cpp`. The native
contracts audit those real files and eight real constants. This is **not** a
claim that every floorplan/PCB native file already has registered coverage.
Expanding the pipeline manifest requires genuine policy registration and will
surface any remaining raw operations; there is no baseline waiver in this mode.
Calling the committed low-level quantize functions directly still executes the
math; import the producer's existing counters rather than calling it again.
The subsequent producer instrumentation and exact ownership aggregate are
documented in `producer_accounting_INTEGRATION.md`.

### C++ audit rules and boundaries

- Namespace/file numeric definitions (including lowercase/camelCase), enum
  constants, and arithmetic object-like numeric macros require exact covers.
  Anonymous namespaces are elided in keys; macro keys are `path::macro::NAME`.
- Numeric local constant initializers, uppercase mutable local policies
  (including Unicode uppercase names), and class/member defaults are buried
  decisions. Ordinary runtime-derived local temporaries are not hoisted by fiat.
- Raw rounding functions, taking their addresses, floating-to-integral casts,
  geometry-related `+/- 0.05`, and legacy banned constants/calls are detected.
  The compiler resolves casts, includes and macro expansions; comments/string
  contents are not interpreted as code.
- A registered transform covers raw quantization only inside its exact named
  implementation function, not a whole file. Banned legacy forms still fail.
  Deleted constants/transforms leave stale covers. Missing required ledger
  entries, unclosed steps, duplicate nonrepeated calculations and divergent
  replay are failures.
- Missing/duplicate/empty manifests, empty censuses, invalid C++, missing
  compiler, malformed compiler output, and read/process errors do not pass.
  Headers must be explicitly in the manifest (and independently compilable);
  included definitions are not silently attributed to the including `.cpp`.
- This is a source-policy audit, not a proof of arbitrary C++ program behavior.
  It uses the selected build configuration, not disabled preprocessor branches.
  Object-like macro analysis recognizes numeric arithmetic/known numeric macro
  references; arbitrary type-producing/preprocessor metaprograms are not treated
  as scalar constants. Overloaded implementation names are rejected rather than
  granting ambiguous coverage. Policy registration itself still needs review.

## Independent contracts and isolated reproduction

`verification_audits_build/` is a **source-only test project**, containing one
`CMakeLists.txt`; it is not an in-repository build directory. All outputs used
for this handoff are under `/private/tmp/schgen-audits-native.a2hr42/`.
No temporary `.py` capture scripts or generated binary products are deliverables.

From the repository root (substitute the existing archive path if necessary):

```sh
cmake -S native/tests/verification_audits_build \
  -B /private/tmp/schgen-audits-native.a2hr42/native-release \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_DEPLOYMENT_TARGET=26.6 \
  -DSCHGEN_CORE_ARCHIVE=/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM/native/build/standalone/libschgen_core.a
cmake --build /private/tmp/schgen-audits-native.a2hr42/native-release -j4
ctest --test-dir /private/tmp/schgen-audits-native.a2hr42/native-release --output-on-failure
```

Strict handwritten C++ compilation is C++17 with
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`.
The default target has **666 passing contracts**, including nineteen real C++
source mutations, a live audit of both native quantization implementation files,
concurrent counters, exact ledger replay/divergence, caller argument variations,
and sixty independently captured fallback baseline cases. Another eighty-two
independent integer cases cover every Unicode 16 decimal-digit block and the
whitespace error boundary (ASCII control separators must not become valid
counts). The baseline cases cover
missing/corrupt baselines, regressions, lowering, Unicode escaping, signed and
arbitrarily large ceilings, and exact publication bytes. The added accounting
test TU executes a real zone solve and needs the existing core's LibXml2 link
dependency; the accounting production source adds no library dependency.
The previous 604-contract target also passed with `PATH=/usr/bin:/bin` and had
no undefined Python or tree-sitter symbols.

Set `-DSCHGEN_AUDIT_SANITIZERS=ON -DCMAKE_BUILD_TYPE=Debug` in a **different**
temporary build directory for AddressSanitizer + UndefinedBehaviorSanitizer.
Do not mix sanitized and unsanitized standard-library container producers:
instrument the loaded core provider translation units as well. Do not invoke
shared CMake build trees.
The earlier combined ASan/UBSan run passed both suites (604 native contracts and
867 transitional contracts), with no sanitizer diagnostics, in 77.33 seconds.
The expanded 666-contract target also passed with ASan/UBSan after rebuilding
all loaded provider translation units consistently under
`/private/tmp/schgen-audits-native.a2hr42/full-sanitizer-build/`; no suppression
was applied. Its latest run took 188.99 seconds. That sanitizer run predates the
final spatial/fanout producer-counter additions; the final producer stage has
the separate strict release proof recorded in its handoff.

## Retired transitional parity (historical evidence, not a build path)

The Python-source parser, its compatibility APIs and opt-in build helper are
retired. The C++ compiler-backed audit is the production source gate. The
unbounded integer, ledger-state and fallback-ratchet implementations remain.
The original compatibility fixture bytes below remain historical evidence.

The retired helper previously built its parser against pinned source checkouts:

- tree-sitter `da6fe9beb4f7f67beb75914ca8e0d48ae48d6406` (v0.25.10).
- tree-sitter-python `293fdc02038ee2bf0e2e206711b69c90ac0d413f` (v0.25.0).

Its **867 passing contracts** are historical transitional proof. The checkouts
used for that proof were respectively
`/private/tmp/schgen-audits-native.a2hr42/tree-sitter` and `tree-sitter-python`.
That path was bounded to the frozen compatibility corpus, not a replacement
for the whole Python compiler. The five staged-only parser/build/test files
were backed up under `/private/tmp/schgen-retired-python-audit-parser` before
retirement; final native checks have no tree-sitter or Python grammar dependency.

## Fixture provenance (immutable bytes)

The Python reference outputs were captured from the unchanged original audit
implementations **before** their native implementations. The base fixture
records the original auditor source hashes. Synthetic ledger samples explicitly
supply known-name inputs; real-file samples use actual module symbols. Native
production code never reads these expected verdicts. State output was captured
independently before writing `NativeLedger`; native registry metadata is a port
of declarations, not a frozen computed board result. `fallback_reference.json`
is a byte-stable JSON projection of the original sixty fallback cases, so the
default native test target needs no Python-source samples or parser dependency.

SHA-256:

```text
d01e4d34727eed4d38c7bd68c09bccac1402a8822c13c834764f48ffed16c083  python_reference.json
a065cd3ed13e2b8f1b50a3464d63d8f75c02244bc5c872388ab0d2201a210e84  python_edges.json
9402fdc19afc69210ed143bd8d41acc8a29a117fedd9723147a166acb16991d3  python_state.json
4e2d166d077d2d26d07b584581a926906f2aa5008bc6a734fb7abfc74ede2f66  fallback_reference.json
cd0a085b5d35b58ccf7f39b2da4b3dc2a1f0c4d95dc86de579531fa628e95ded  integer_reference.json
5d883519261aeb59ce2ea4374c42fff51b218c1c33a44253ba3551639978302c  native_producer_counts.json
```

The initial audit stage changed only new audit files/tests. Its explicitly
authorized producer follow-up also changes the placement/stage/floorplan and
supporting counted kernels listed in the producer handoff. No parent
board_pcb/pcb_verification, shared CMake/module/CLI, Python adapter or other
worker's files were edited. No commits were made; parent owns integration,
final whole-pipeline proof and commits.
