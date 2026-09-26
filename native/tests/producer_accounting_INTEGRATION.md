# Producer accounting — stable parent handoff

This supersedes the producer-gap list in `native_accounting_INTEGRATION.md`.
No parent `board_pcb`, `pcb_verification`, shared CMake, module, CLI or Python
adapter was edited. All build products and temporary oracle sources are under
`/private/tmp/schgen-producer-accounting.WKP8HR/`.

## Consume exactly one owned aggregate

```cpp
const PcbPlacementResult placement = build_pcb_model(input);
inbox.merge_once(build_invocation_id + "/pcb", pcb_placement_accounting(placement));
const auto emission = render_pcb(placement.model, caller_emission_policy);
inbox.merge_once(build_invocation_id + "/emission",
    NativeAccountingBatch{{}, emission.fallback_events});
```

The result is a computed live solve, not fixture output. Aggregation performs
only checked integer additions and ordered event concatenation. It neither
executes math nor invokes a registry evaluator. Do not also import its plan,
zones, nested stages, legacy event vector or placement-only delta.

New fields appended to `PcbPlacementResult`:

- `placement_accounting`: `ExecutionAccounting` with placement-only
  `quantization_engagements` and `fallback_events`, including refit trials.
- `zone_accounting`: the actual placement-zone invocation's observations.
- `zone_accounting_ownership`: `PcbZoneAccountingOwnership`.
  `IncludedInFloorplan` means that exact zone execution is already in
  `floorplan.plan.accounting`; `SeparateFromFloorplan` means a distinct
  placement-zone execution must also count. `Unspecified` rejects aggregation.

`build_pcb_model` sets the ownership explicitly: normal two-side builds include
their one zone solve in the plan; top-preferred (`two_side=false`) builds execute
placement zones and separate two-side planning zones. The aggregate includes
both actual executions once, in execution order, then placement events.

The unchanged `place_pcb_model(input, zones, stage)` remains source-compatible
and sets ownership to `Unspecified`: it cannot infer the ancestry of a supplied
solve. Use `place_pcb_model_accounted(input, zones, stage, ownership)` when that
ancestry is known, or consume only `placement_accounting` when the caller has
already imported all upstream observations. Do not guess ancestry from equal
numeric totals. The old `fallback_events` still equals the zone prefix followed
by placement events; it is retained for compatibility, not a new delta.

Rebuild consumers after the appended public fields; do not relink stale objects
compiled against the old result layout. Registry API signatures are unchanged.

## Actual call boundaries now instrumented

- `instantiate`: `fixed_part_grid`, once per actually snapped coordinate;
  already-grid-placed parts do not acquire synthetic snap counts.
- Breathe A/B: `breathe_anchor_grid`, once per actual attempted anchor coordinate,
  including reduced-step retries and candidates later rejected/reverted.
- L4/corridor geometry: `quant_credit`; corridor x/y snaps: `evict_corridor_grid`.
  Its nested `fixed_part_grid` implementation is **not** counted a second time.
- Facing refit: new registry label `refit_pose_precision`. Each coordinate of an
  attempted exact half-turn is rounded to four decimals using the same original
  `2*center - old_pad_center - new_pad_center` expression and order. Rejected
  candidates retain their calls. Early no-output exits report zero work.
  Ordinary stage-template turns retain their original census; this new label
  is explicitly scoped to facing refit, not retroactively attached to templates.
- Legalization: `legalize_pose_quantum` at the actual kernel call, including
  unchanged/clamped coordinates, no-motion termination passes, rejected solves
  and reverted compaction. A plan's counter is not rolled back with trial poses.
- Floorplan fanout and spatial bounds: native `quant_credit` calls were also
  previously invisible. Counted kernel variants now record them at the call,
  preserving pin thresholds, need tiers and caller arguments.
- Existing stage/floorplan/zone increment and merge sites now use checked
  `size_t` additions. Fine-outline scans increment at each actual call instead
  of a hard-coded post-hoc `+=82`. All batch merges validate overflow before
  changing the destination. The native registry still rejects unknown labels
  and checks its own exact uint64 import boundary.

New counted APIs preserve old entry points used by bindings:

- `refit_pcb_stage_facing_accounted` returns `PcbStageRefitResult` with optional
  `poses`, counts and events, even when the incumbent wins.
- `floorplan_legalize_compact_accounted` accepts a `QuantizationCounts&` sink.
- `legalize_descend_passes_accounted`, `zone_fanout_members_rows_accounted`, and
  `spatial_bounds_accounted` accept an explicit `QuantizationCounts*` sink.
  Existing functions delegate with no external sink; production floorplanning
  uses the counted variants. There is no process-global production counter.

`execution_accounting.hpp` is header-only. The refit rounding implementation is
in the already-integrated `native_audit_quantize.cpp`; register it through the
updated `register_native_quantizations` (20 entries). No new third-party
production dependency is introduced. No automatic ledger covers were added;
the reviewed declaration migration plan remains separate work.

## Independent proof and immutable geometry

`producer_accounting_contracts.cpp` installs compiler-generated function-entry
observers in **test-only** instrumented copies of `quantize.cpp` and
`native_audit_quantize.cpp`. It never derives expected counts from the producer
counter. It checks each placement phase and complete builds for both boards,
including the distinct two-zone top-preferred path. It also checks unchanged
and losing trials, compaction rollback, ownership rejection, duplicate registry
import and overflow at actual source call sites.

The original floorplan fixture recorded no native legalizer calls and only
input-zone credits. A separate observer linked the committed pre-change
floorplan/legalizer sources at `59a8aa3a93aa21bba5e471bb5d08c71812b74ad8`:

- Devkit: 480 missing legalizer calls and 172 missing floorplan credit calls.
- Carrier: 2,250 missing legalizer calls and 786 missing floorplan credit calls.
- Existing small automatic-outline synthetic case: 696 spatial credit calls.

Those independent deltas are in the new test-only
`data/verification_audits/native_producer_counts.json`. The floorplan assertion
adds them to the old reference counters; it does not ignore or remove any
accounting comparison. Every original geometry, stage, floorplan, emitted-board,
ledger and document byte fixture remains untouched. All 27 existing placement/
escape/floorplan manifest entries verify unchanged.

The final isolated strict C++17 run passed all four suites in 50.35 seconds:
124,437 placement assertions, 2,787 stage assertions, 17,388 floorplan checks,
and 167 independent producer-accounting contracts. The floorplan count includes
ten additional counter/provenance checks beyond its original 17,378 checks.

The parent's earlier `native_floorplan_contracts` failure was the stale
synthetic counter expectation, not changed geometry. Its subsequent C++17
compile failure was a structured-binding capture in the new expectation test;
the final source uses `[wanted=key]`. Rebuild parent target
`schgen_floorplan_contracts`, then rerun `native_floorplan_contracts`. Production
sources/API are frozen; this handoff does not require another production edit.

## Reproduce the new observer contract without shared builds

Use a completed, freshly rebuilt parent core archive and a private temporary
directory. On this host, compile with C++17, deployment target 26.6,
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`, and native include/src paths.
Compile **only** `src/quantize.cpp` and `src/native_audit_quantize.cpp` additionally
with `-finstrument-functions -fno-inline`, to two objects in that directory.
Compile `tests/producer_accounting_contracts.cpp` without those instrumentation
flags, then link its object and the two observed objects **before** the core
archive, with the existing LibXml2 and thread dependencies. Run the executable
with the repository root as its sole argument. Missing instrumentation fails
explicitly; it cannot silently produce a passing zero-count test.

The isolated source/project and binaries used here are respectively
`/private/tmp/schgen-producer-accounting.WKP8HR/source/` and `release/`.
No Python executable, subprocess, capture script or production callback is
needed by the implementation or these contracts.
