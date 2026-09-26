# Native precision extraction and breathe-policy checkpoint

Production contains six real pure scalar implementations in
`native/src/precision_ops.cpp`, declared by `schgen/precision_ops.hpp`.
`native_audit_registry.cpp` binds their actual compiled functions with arities
one/one/one/one/two/two. No complete placement/estimator function is registered,
and no callback merely returns a dummy value. Production never reads these
fixtures and has no Python/subprocess dependency for the operations.

## Parent integration requirements

1. Add `src/precision_ops.cpp` to the main core source list.
2. Add `precision_ops.cpp` to the **explicit** source list in
   `native_board_policy_audit_sources()` (`board_policy_metadata.cpp`). This
   increases the 55-file manifest to 56; do not remove an existing entry. The
   constant owner `board_decision_policy.hpp` is already included.
3. Add ordinary core-linked tests for `tests/precision_ops_contracts.cpp` and
   `tests/native_cpp_enum_contracts.cpp` (neither takes arguments).
4. Add `tests/precision_accounting_contracts.cpp`, taking the repository root.
   Compile **only** `src/precision_ops.cpp` a second time as a private test object
   with `-finstrument-functions -fno-inline`. Link that object before the core
   archive, so it supplies these six symbols instead of the ordinary archive
   object. Do not instrument the test TU, other core objects, or production.
   The observer must see a real function entry; its first registry test fails
   if the special object is missing. Use normal public/private include paths
   and strict C++17 flags for all targets.

No main CMake, module, CLI, process implementation, AST projector, shared build
or commit was changed by this tranche. Parent owns the CMake/manifest integration.
Until step 2 is applied, full policy auditing correctly reports the new transform
implementations as absent from its manifest; this must not be suppressed.

## Exact operations and accounting boundaries

`estimate_position_precision(value)` preserves `py_round(value,4)`;
`estimate_pad_precision(value)` preserves `py_round(value,3)`. The zone-position
formula retains both inner and outer rounds, separately counted, with the same
addition order. The ten prior estimator diagnostic lines contain twelve scalar
round expressions, because two lines have nested rounds.

`breathe_delta_precision` and `breathe_commit_precision` preserve the existing
four-decimal rounds. Delta evaluation still does page translation, the existing
`breathe_anchor_grid` call, subtraction of page origin, subtraction of the old
coordinate, and only then the delta round. Commit still adds before rounding.
Existing grid engagement counts are unchanged.

`breathe_forward_steps(distance,step)` preserves truncating
`int(distance / step) + 1`. It remains evaluated at every original forward-loop
condition; it is not hoisted or replaced with ceil. `breathe_retreat_steps`
preserves `int(distance / step)` at retreat initialization. Both now reject
nonfinite inputs/quotients, nonpositive step, and unrepresentable narrowing.
Forward also checks the final addition for overflow. Range validation considers
the truncated result, preserving defined fractional inputs near int limits.

Call sites record once in the existing invocation-owned maps. Immutable label
strings avoid constructing a string on each coordinate; map allocation happens
only for the first occurrence of a new label. There are no global production
counters. The independent function-entry observer exists solely in the test.
Importing a completed accounting aggregate executes no math and counts it once.
Standalone observational measurements use their existing private engine copy;
they execute measurable operations without mutating solver or input census.

## Explicit policy exposure, not changed engineering values

The producer now reads `board_decision_policy::breathe_epsilon_mm` (1e-4) and
`breathe_step_mm` (.25) directly at every former local-epsilon/search-step use.
The step is the displacement-search increment; unrelated occupancy-cell literals
were not conflated with it. Registry providers and the producer ledger resolve
the same storage through authored `breathe_epsilon`/`breathe_search_step` entries.

The factory now has **66 declarations: 48 assumptions and 18 calculations**.
The two policies are explicitly marked `exposed` by
`floorplan_ledger_migrations()`. They retain the original values and arithmetic.
`policy_additions.json` is a separately authored two-row ledger provenance delta.
The test-only reference helper inserts those rows after `d13_df40_min_pins`;
historical Python reference bytes and the previous provenance fixture are intact.
No geometry/event/counter field is changed by the ledger helper.

## Independent evidence

Isolated directory: `/private/tmp/schgen-precision-proof.s83e64`.
The copied coherent pre-change archive `baseline_core.a` has SHA-256
`864b93a466a940426aef10e18a809641ea517aaea5690e3f9c2fa7d1d90dfbd7`.
The baseline capture executable was linked before producer rewrites. It captured
the original twenty-label populations for both boards and supported devkit
single-side operation. A repeat capture compares byte-identically.

`additive_counts.json` contains only the six new labels. Its aggregate values
were independently observed at compiled function entry, and matched against
producer-exported counts before capture. Fixture ownership separates floorplan
and placement counts. The default test requires this fixture; its explicit
`--capture-additive` maintenance mode is not the integration/acceptance command.

Final isolated strict C++17 proofs (`-Wall -Wextra -Wpedantic -Werror
-ffp-contract=off`, matching macOS deployment target 26.6):

- Pure operation tests: **48,320 PASS**, also with ASan/UBSan on the new test and
  operation TUs. Supporting archive objects are not sanitizer-instrumented.
- Independent accounting: **82 PASS**, original twenty counters exactly
  unchanged in each ownership layer; new counts equal independently observed
  entries; repeated import and observer-neutrality checked.
- Placement: **124,437 PASS**, both boards/supported variant, all historical
  stage/model geometry and full PCB/design-rule bytes exact.
- Floorplan: **17,322 PASS**, independent geometry/outputs, unchanged old counts,
  explicit additive counts and independently authored ledger additions.
- Null/empty/recording observer parity: **121,982 PASS** on both boards.
- Board-policy contracts: **721 PASS** (non-compiler mode).
- Board-policy migration: **37,205 PASS**.
- Existing C++ source-audit mutation suite: **55 PASS**, now scanning the eight
  quantizer constants and all 26 actual transform implementation functions.
- Auditor identity/storage fixtures: **36 PASS**; enum correction: **22 PASS**.

These do not claim a completed whole-board source audit. That requires the
parent's complete manifest plus Zeno's independently proven AST projection.

A small mixed-build timing check over the same three fixture solves recorded
12.61 versus 12.72 user CPU seconds (old archive versus new producers/ops);
wall time was 12.73 versus 13.43 seconds. Other workers were active and compiler
optimization settings differ, so this is only a sanity check, not a release
performance claim.

Fixture SHA-256:

```text
2f054c5ec92c0f25851f8c26bc21b02e2ad867029fbeb24ce3a32ee0dad9e01e  legacy_counts.json
4569c5ac68d1a199c3d53dfae10723e1ee2165c5791ee30ea5ca9dd9ab39ce72  additive_counts.json
5ad66542f5ff7989a81b0a41ed8aacdb34e8ce781f72b9498890a5d23c3c21c0  policy_additions.json
```

## Enum auditor semantics

Only entirely unseeded enum ordinals are identity state. Any explicit initializer
makes the entire enum numeric policy, including implicit successors and explicit
zero. Scoped/unscoped/underlying-type category enums are covered by tests.
Ordinal IDs remain compile-time dependencies so derived engineering arithmetic
cannot disappear from the census. The pre-correction test passed all twelve
physical-value checks, then failed its first ordinary-category assertion; the
corrected auditor passes all 22. No file exemption, generated declaration or
precision waiver is involved.
