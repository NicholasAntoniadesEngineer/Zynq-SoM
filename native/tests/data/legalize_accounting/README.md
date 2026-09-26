# Legalizer precision accounting proof

Prepared privately from `6a580efe447c2bf02f30a0ffe5fe54700a66e3ec`.
No shared checkout, registry, CMake, policy constants, or native/bin changes.

`legacy_output.txt` was captured BEFORE production edits by compiling the new
scenario with `LEGALIZE_LEGACY_PROBE` against the original legalize.cpp and
floorplan_compose.cpp. Both before and after executables link the same frozen
copy of the existing core archive for unchanged dependencies. quantize.cpp is
separately instrumented at function entry. This independently pins the old
legalize_pose_quantum counts, rather than deriving them from producer receipts.

Original source Git blobs:

- legalize.cpp: `120b80daf8a642ba97e202f2085b4338aab66960`
- floorplan_compose.cpp: `a2a11249a1e7459435af72f7f5d1fcb134a1f636`
- legalize.hpp: `fde2b3c4acbf94e736a2d3bba574d642a2d8e1a5`

Baseline SHA-256:
`f490998fde2b49b0ee9b14f879b7654dcdbf11c2edd489aaa41e35391b805f74`.

The contracts compare binary-round-trip geometry, term outputs, decision order,
rejection/rollback logs, all previous counts, board plans, ledger bytes and
exported specs. Scenarios include filtered/empty centroids, empty hulls, missing
pad exceptions after a valid prefix, every term kind, missing endpoints, SoM and
connector anchors, both facing guard branches, ten original composition fixtures,
and carrier/devkit/single-side devkit/fixed-outline devkit board solves.
Existing pose quantum counts remain respectively 2250/480/480/48 for those
boards. The new seven counts are independently observed at compiled scalar
entry and pinned explicitly in the test. All board entries are owned by the
floorplan invocation; no zone or downstream placement receipt duplicates them.
Cached ledger rendering executes none of these scalar operations.

Compile ONLY legalize_precision.cpp and quantize.cpp with Clang
`-finstrument-functions-after-inlining` for the contract executable. Compile the
test TU normally. The observer compares real function addresses and has no
production linkage/state. Separate translation units preserve the external
scalar entries without disabling optimizations across the rest of the engine.
Run `legalize_accounting_contracts REPO`; `REPO --kernels-only` verifies the
kernel/composer slice against the same immutable baseline. Compile legalize.cpp
with its existing `-ffp-contract=off`; do not move any policy/default arithmetic.

Scalar checks cover ties and neighboring representable inputs, signed zero,
large and nonfinite inputs, null sinks, sink isolation and checked overflow.
Failed pad lookup retains exactly the executed position-round prefix. The
compaction rollback fixture retains 12 trial/final coordinate rounds; the
hard-term rejection retains four trial coordinate rounds and its margin round.

## Parent integration (intentionally not edited here)

Add legalize_precision.cpp to the core and source-policy manifest, and add the
contract target with its two independently instrumented objects. Registry
bindings MUST target the exact scalar identity
`native/src/legalize_precision.cpp::schgen::<name>`; all seven have arity **1**,
expression `round(value, 4)`, and call the actual function with a null sink.
The optional accounting pointer is not a numeric registry argument.

Proposed declarations and proof rationale:

- `legalize_position_precision4dp`: round each selected component's absolute
  coordinate before centroid accumulation or pad-hull construction; preserve the
  subsequent independent centroid/hull rounding. Proof stage `pre-proof`.
- `legalize_centroid_precision4dp`: round each averaged coordinate only after
  accumulating already rounded positions. Proof stage `pre-proof`.
- `legalize_bbox_precision4dp`: round each nonempty accumulated hull bound after
  translated pad extrema have been selected. Proof stage `pre-proof`.
- `legalize_anchor_precision4dp`: round SoM/connector midpoint coordinates at
  their existing evaluation boundary. Proof stage `pre-proof`.
- `legalize_bound_precision4dp`: round the flow budget/effective bound stored in
  the term result, retaining comparisons against the original unrounded bound.
  Proof stage `pre-proof`.
- `legalize_margin_precision4dp`: round each evaluated term's reported margin,
  retaining the original unrounded feasibility/angle comparison and guard rule.
  Proof stage `pre-proof`.
- `legalize_trial_pose_precision4dp`: round each trial/final pose before term
  evaluation or final overlap checks. Count rejected and reverted work; retain
  whole-compaction rollback. Proof stage `re-validated`.

Do NOT register predicted_centroid, predicted_bbox, evaluate_terms or Composer
as covers. There are no remaining raw round/floor/float-narrow operations in
legalize.cpp or floorplan_compose.cpp. Integer-index casts are unchanged; there
were no genuine raw floor/narrow scalar boundaries in this legalizer slice.
legalize_pose_quantum's implementation and existing counting site are unchanged.

Existing registry cardinality expectations and historical count adapters need
the seven additive names incorporated centrally. Only separate the seven
independently proven additions; preserve every legacy expectation. The new
contract removes exactly these names from its immutable byte comparison and
independently verifies their exact entry counts and receipt ownership. No
coverage waivers or broad exclusions were added.

The standalone public floorplan_evaluate_terms remains a pure diagnostic API;
the production Composer passes its explicit invocation sink down through all
term evaluation, centroid, hull and coordinate boundaries. No sink is retained
in copied geometry or installed globally.

## Verification and limits

- Four real board scenarios and ten compose fixtures pass exact pre-change
  output/count comparison and independent scalar-entry accounting.
- Existing exact legalizer precision contracts pass.
- Existing floorplan geometry/estimator slice: 12,900 checks pass.
- ASan+UBSan kernel/composer slice passes, with the changed production TUs and
  test instrumented. Unchanged dependencies use the frozen release archive.
- A mixed-library full-board ASan attempt stopped in footprint_bbox_walk with
  a std::vector container-overflow report during fixture loading. This is outside
  the changed slice and mixes instrumented/uninstrumented libc++ containers;
  a consistent whole-engine sanitizer build is required to distinguish a real
  defect from annotation mismatch. No sanitizer option was disabled.
- Full registry/manifest gates and electrical/visual board generation remain
  parent integration work; this patch does not claim those gates were run.

Private executable/log paths and repeated release timings are documented in
the accompanying private handoff file.
