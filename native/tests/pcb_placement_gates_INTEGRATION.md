# Independent native placement gates

This handoff supersedes the missing-gates section of the earlier placement
handoff. Independent final-model contract, flow, compose and coverage checks
are now implemented. It does not change shared CMake, bindings, CLI, the live
loader, placement algorithms, or other workers' files.

## Parent integration

Add to the native core target:

```text
native/src/pcb_placement_contract_gate.cpp
native/src/pcb_placement_flow_gate.cpp
native/src/pcb_placement_compose_gate.cpp
```

Public header: `native/include/schgen/pcb_placement_gates.hpp`.
Private helper: `native/src/pcb_placement_gates_internal.hpp`.
Contract executable: `native/tests/pcb_placement_gates_contracts.cpp`, with the
repository root as its sole argument. It shares the existing
`pcb_placement_fixture.hpp` test loader and the existing placement/emission/
floorplan fixtures, plus the new immutable `data/pcb_placement_gates/` fixtures.

The production call is:

```cpp
#include "schgen/pcb_placement_gates.hpp"

const auto checks = schgen::check_pcb_placement_gates(live_input, placed.model);
// Mandatory contract and flow exit policy:
const bool placement_ok = checks.ok();
// Preserve all four output/report surfaces:
const auto contract_report = checks.placement_contract.summary();
const auto flow_report = checks.placement_flow.summary();
const auto coverage_report = checks.coverage_report.text;
const auto composition_report = checks.composition.text();
```

This overload derives policy from the actual input snapshot, validates contract
pin IDs afresh, prepares actual final geometry, constructs the final compose
index with **placed-sheet discovery scope**, and uses current-model escape/T2
evidence. It does not run placement or floorplan again. The index reuses
`prepare_pcb_floorplan`'s existing term builder with empty geometry: only its
policy/ref-dependent index is consumed, not metrics or a solve. Fallback sheet
reference bands are fixed before narrowing discovery scope. This avoids
duplicating the authored term builder and avoids confusing predictive scope
with the original final-report default when an entire sheet is absent.

If the caller already owns a freshly prepared `PcbCheckInput`, policy, final
index, evidence and optionally current ratsnest nets/MST, the lower-level
`check_pcb_placement_gates(prepared, policy, index, evidence, &nets, &mst)`
avoids repeated preparation. Do not reuse a prepared model or ratsnest after
moving/removing parts or replacing footprints. These are value-owned snapshots,
not live views. Supplied MST indices are checked before access.

Dependencies: integrated placement term preparation, PCB model/check geometry,
board reference renaming, native legalize/pack geometry and ratsnest/MST. The
private helper reuses existing PCB-check formatting functions. No third-party
dependency, process runner, filesystem loader, Python callback or fixture
dependency is introduced in production.

## Exact loader/evidence contract

The parent's existing `PcbPlacementInput` is sufficient; no new loader/schema
is needed beyond the already added `prior_escape_sidecar`:

- `floorplan.sheets`: all ordered canonical circuits, with original local refs,
  declared footprint IDs and nets. Do not filter this input to placed parts.
- `floorplan.sheet_index`: stable board-ref bands. Missing entries use original
  canonical circuit order plus one. The gate's policy adapter derives board refs.
- `contracts`: all discovered project contracts, including inert and currently
  absent sheets. Keep the original JSON structure and footprint pad-ID fields.
- `footprints` and `floorplan.footprint_of`: exact pre-placement snapshots for
  pin validation, not substituted/mirrored final instance documents. A missing
  source footprint retains the original unresolved/skip pin-validation policy.
  Placed-pad measurements independently use `model.insts[*].mod`.
- `floorplan.project.wired_sheets`: the actual enforcement set. Project zone
  membership comes from the canonical circuits, not just currently placed refs.
- `floorplan.spec`: current authored near-intent terms, including advisory ones.
- `prior_escape_sidecar`: immutable raw parsed `escape_block.json`, or JSON null
  when absent. It must not be replaced with the new model's result before the
  floorplan solve.

`pcb_compose_evidence(sidecar, origin)` parses the following exact fields:

```text
t1_constraints.corridors.<name>.rect = [x0, y0, x1, y1]  (board-page frame)
escape_meta.coexistence[*].ref       = board ref
escape_meta.coexistence[*].sheet     = sheet name
escape_meta.coexistence[*].verdict   = diagnostic verdict string
```

Corridors are sorted by name, prefixed with `escape:`, and translated by
`(-origin.x, -origin.y)`; the default origin is `(25,25)` mm. Missing sections
are empty. Coexistence order is retained: the last duplicate `(ref,sheet)` wins.
Missing ref/sheet default to an empty string; missing verdict defaults to `?`,
as in Python. A malformed/nonfinite/inverted rectangle is rejected explicitly.
No `conn` or `basis` coexistence fields are needed for this reporter.

The parent loader should retain the raw prior sidecar **and** provide its sorted
translated corridors in `floorplan.compose.corridors` for solving. Final
generation has different timing: original `emit.py` writes the newly generated
escape sidecar before calling `compose_report`. Therefore the production
overload uses `pcb_compose_evidence(model)`, combining
`model.escape_plan_record.t1_constraints` and `model.escape_meta.coexistence`
without writing a file. For a deliberate report against prior evidence use
`pcb_compose_evidence(live_input.prior_escape_sidecar)` and the explicit overload.

## Preserved enforcement semantics

- `placement_contract`: merge configured wired-sheet verdicts, including wired
  sheets with no placed instances. Multi-sheet summary bytes retain the original
  blank-line-separated sheet reports. Empty wired policy retains the original
  vacuous `power`/no-contract result.
- `check_all_pcb_placement_contracts`: every **placed** authored sheet, including
  inert contracts. This is not the wired aggregate.
- `pcb_contract_coverage`: every **authored** sheet, even if absent/inert.
  The report distinguishes `WIRED-gated`, `inert-met`, `inert-VIOLATED`.
- Unknown structure types create violations, never an ignored success. All
  original hot-loop, bulk, switching-node, feedback, boot, VCC, bias, RT, LDO,
  proximity and same-side branches are independently measured after placement.
- Pin fields are validated against source footprint IDs, including nested pin
  pairs and `min_from.pin`. No global validated-sheet or pad-file cache exists.
- Preserve the original per-structure missing-reference behavior: missing refs
  are reported; some branches skip measurements, while hot-loop/no-candidate
  fails. `PlacementContractResult.ok` depends on violations, not merely on the
  missing-ref count. This is explicit compatibility, not a new waiver.
- Default flow selection is placed **wired external** contracts. Explicit
  selection can measure other contracts. Unknown-project endpoints are N/A;
  missing endpoints from this project fail. Facing uses strict positive dot,
  maximum/minimum distance comparisons have no added tolerance, and SoM/region
  resolution follows each original branch's behavior.
- Composition recomputes final centroid/pad bounds, hard/soft/NA measurements,
  finite-margin aggregates, strict corridor intrusions, T2-managed classification
  and cross-sheet MST airwire counts/lengths. The six-airwire threshold and
  `2 + 0.2/net` channel rule are retained. First-hit intrusion reporting preserves
  original footprint pad insertion order, including unioned duplicate pad IDs.
- **Coverage and the composition ledger remain advisory in the original CLI.**
  Hard RED counts remain visible in that ledger; they do not independently
  replace/add an exit gate. `checks.ok()` is exactly wired-contract OK AND flow
  OK. Run and publish all report surfaces, and retain other PCB verification
  families separately. This result is not a blanket whole-board verdict.

## Independent verification

Strict C++17 isolated build, no shared build invocation:

```sh
task_gate_build=$(mktemp -d /private/tmp/pcb-placement-gates.XXXXXX)
c++ -std=c++17 -O2 -mmacosx-version-min=26.6 \
  -Wall -Wextra -Wpedantic -Werror -ffp-contract=off -I native/include \
  native/tests/pcb_placement_gates_contracts.cpp \
  native/src/pcb_placement_contract_gate.cpp \
  native/src/pcb_placement_flow_gate.cpp \
  native/src/pcb_placement_compose_gate.cpp \
  native/build/libschgen_core.a -lxml2 -pthread \
  -o "$task_gate_build/pcb_placement_gates_contracts"
env PATH=/nonexistent "$task_gate_build/pcb_placement_gates_contracts" "$PWD"
shasum -a 256 -c native/tests/pcb_placement_gates_SHA256SUMS
```

The existing archive must include the previous placement handoff. The deployment
target shown is this host's target, not a new portable build requirement.

Current strict result: **55,851 assertions passed**. Independent Python references
cover 64 synthetic contract/flow cases, 25 hard/advisory/corridor/boundary cases,
175 real-contract pin mutations, both complete boards, reports and coverage,
explicit reused nets/MST, recomputed nets/MST after mutation, and final placed-
sheet index scope after removal. Additional native typed-input tests reject bad
corridor geometry, unknown direct term kinds and malformed MST endpoints, and
prove fresh source bytes invalidate prior pin-validation success.
Required structure keys are also checked: missing policy inputs cannot become
empty refs and silently skipped measurements.

The same **55,851 assertions pass under AddressSanitizer + UndefinedBehaviorSanitizer**
with the complete 76-translation-unit dependency closure rebuilt into
`/private/tmp/pcb-gates-sanitized.QRZVms/`, without linking the unsanitized archive.
An initial mixed-instrumentation attempt failed in the existing JSON parser's
libc++ container annotations; the full instrumented rebuild resolved it with no
container-overflow suppression. LeakSanitizer is unsupported on this macOS
runtime and is not claimed. The strict archive-linked test also passes with
`PATH=/nonexistent`; neither production nor tests require Python execution.

Expected values were captured from unchanged original Python before integration,
not generated from native output. Tests compare exact fields, numeric values,
ordered diagnostic lists, summaries and complete report bytes. All eight fixture
files are immutable, hashed in `pcb_placement_gates_SHA256SUMS`. Infinity is
encoded as a string only at the test-JSON boundary; public result fields retain
their original floating-point infinity semantics.

Source provenance is embedded in each fixture. The original gate SHA-256 values:

```text
placement_contract_gate.py 691b5ac8805ff730f6b3d47b598b8da675e7ed065d88ff4348240d11cb14345e
placement_flow_gate.py     64437e8b9041a5207d64e0ed4e5b881147d4dc22ce98b19aa66a89d045bc60f0
floorplan_compose.py       37527bfa3343730bb96381959760b2bc025bd7502648f266a05b9d58009699a3
pcb/emit.py                d6337063e556ddd29c7ea965be0b14e56e5878eb125e2cb2ba7b63d4f80e5ba9
```

No new Python deliverables remain. The earlier placement/stage capture scripts
were removed from `native/tests/` after byte-verified archival under
`/private/tmp/pcb-gates-native.6gpvwM/`; the new gate capture procedures also
exist only in that private scratch directory. Fixture bytes and source hashes
remain in the repository. No commit was created by this worker.
