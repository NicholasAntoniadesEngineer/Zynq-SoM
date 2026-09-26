# Importing actual native accounting — parent integration

Reviewed against the completed floorplan, PCB stage/zone/placement, escape and
emission sources on `perf-native` (parent HEAD `59a8aa3a` at review time).
The subsequent authorized producer stage closes the placement/floorplan counter
gaps identified here; see `producer_accounting_INTEGRATION.md` for its stable
source/API handoff. This remains a coverage migration plan, not a declaration
that every native decision already has reviewed ledger registration.

## APIs ready now

Add `src/native_audit_accounting.cpp` to the parent's native sources, or reuse
the updated `cmake/native_audits.cmake` helper. The public header remains
`schgen/native_audit_state.hpp`.

- `NativeQuantizations::record_count(name, count)` and `merge_counts(map)` add
  **measured deltas**, never execute `evaluate`, and retain integer precision.
- `NativeFallbacks::record_count`, `merge_counts`, and `merge_events` accept
  actual counted or ordered-event deltas. Large counts remain compact; they do
  not allocate one string per firing. Ordered event imports retain repetitions.
- Counts are checked unsigned 64-bit values. Signed negative inputs throw.
  Unknown labels, including unknown labels with zero counts, throw. Every batch
  checks all labels/overflow before committing any entry.
- `NativeAccountingInbox::merge_once(invocation_id, result)` directly accepts
  `FloorplanAccounting`, `PcbZoneResult`, and `PcbStageResult`. Its explicit
  `NativeAccountingBatch` overload also accepts event-only emission results.
  It validates and commits **both registries and its receipt atomically**.
- Repeating an identical ID/payload returns `false` without changing counts.
  A changed count, event order or payload under the same ID throws. IDs identify
  actual invocations/ownership aggregates, not project filenames. Two genuine
  identical solves have different IDs and both count.
- An inbox is build-owned. `inbox.reset()` clears receipts and both registries'
  build counters/logs together, retaining declarations. An independent reset
  or restore after receipt imports is detected and blocks further imports;
  it cannot silently desynchronize deduplication state.

For direct fallback rollback, legacy `snapshot()/restore(vector)` stays exact
for event-only state. Once compact count imports exist, `snapshot()` throws
instead of losing those counts. Use `checkpoint()/restore_checkpoint()` to
retain both counts and ordered logged events. Checkpoint restoration validates
labels and that totals include all logged events before changing state.

Do not call `invoke()` to "replay" results into the registry. Do not both wrap
an already-instrumented execution in `invoke()` and import that execution's
counts. Those would execute twice or count twice respectively.

## Actual labels: import verbatim, no alias guessing

The following emitted keys already have exact registry entries:

- Floorplan, `floorplan_geometry.cpp` / `floorplan_build.cpp` /
  `floorplan_cross.cpp` / `floorplan_pack.cpp`:
  `som_pose_half_mm`, `placeholder_zone_half_mm`, `fixed_part_grid`,
  `outline_snap_up`, `outline_grow_step`, `outline_fine_grid`, `est_via_cost`,
  `run_overflow_tol`.
- Stage engine, `pcb_stage_internal.hpp`: `quant_credit`,
  `snap_erosion_bound`, `snap_erosion_pad`, `seat_slide`.
- Zone context, `pcb_placement_internal.hpp`: `quant_credit`.
- Placement: `fixed_part_grid`, `breathe_anchor_grid`, `evict_corridor_grid`,
  `quant_credit`, and the newly registered `refit_pose_precision`.
- Floorplan legalizer: `legalize_pose_quantum`; spatial/fanout kernels:
  `quant_credit`. These are now measured at the actual native call sites.
- Floorplan fallback events: `legalize_only_compaction`,
  `punch_free_plan_rejected`, `interior_reseat_retry`.
- Stage search fallback events: `cand_cap_truncated`, `seat_node_budget`.
- Zone variants: `bottom_variant_contract_reject`.
- Placement corridor eviction: `corridor_evict_moved`,
  `corridor_stray_unmovable`.
- Emission, `pcb_embed.cpp::thermal_nodes`: `thermal_via_lattice`, once per
  selected fallback lattice via, exposed in `PcbEmissionResult::fallback_events`.

In particular, function `outline_grow` emits registry key `outline_grow_step`,
and `fine_shrink` emits `outline_fine_grid`. Do not rename these during import.
Missing registered keys mean zero, not an unregistered alternate spelling.
`assembly_generation_failed` remains registered but no native emitter of that
event was found; only an actual advisory generation failure may record it.

## Ownership boundary: import parents OR children, not both

The source ownership chain is explicit:

1. `build_pcb_stage_zone` returns one invocation's engine event log and counts.
2. `build_pcb_zone_geometry` collects templated stage results and its own
   `Context::quantization` into `PcbZoneResult`.
3. `prepare_pcb_floorplan` appends that zone accounting to the caller's
   `FloorplanInput::accounting`.
4. The floorplan engine copies input accounting into the plan and accumulates
   actual sizing work. Its final `plan.accounting` therefore already owns that
   input, zone, and nested stage accounting.
5. Separately, `Placer` initializes `PcbPlacementResult::fallback_events` with
   the zone event prefix, then appends corridor events. That vector is **not**
   a wholly new delta relative to `plan.accounting`.

The explicit result aggregate now handles both ordinary and top-preferred
builds. Import it once:

```cpp
NativeQuantizations quantizations;
NativeFallbacks fallbacks;
register_native_quantizations(quantizations);
register_native_fallbacks(fallbacks);
NativeAccountingInbox inbox(quantizations, fallbacks);

const auto placement = build_pcb_model(input);
inbox.merge_once("run-unique-id/pcb/1", pcb_placement_accounting(placement));
// Do NOT separately import plan, zones, nested stages, input accounting,
// placement_accounting, or the legacy fallback_events vector here.

const auto emission = render_pcb(placement.model, caller_emission_policy);
inbox.merge_once("run-unique-id/emission/1",
    NativeAccountingBatch{{}, emission.fallback_events});

// Consume once; render/write already-produced documents without another merge.
const auto ratchet = check_fallback_ratchet(fallbacks.census(), caller_baseline);
```

`two_side == false` is materially different: `build_pcb_model` runs actual
placement zones and a **separate** two-side planning-zone build. The latter is
already in the solved floorplan accounting; the former is additional work.
`zone_accounting_ownership` records this distinction, so the aggregate above
includes both executions once. If `two_side == true`, planning zones are a copy
of the same result: there is no second execution to import. A caller supplying
its own zone/floorplan results must specify known ownership through
`place_pcb_model_accounted`; the unchanged legacy entry point leaves ownership
unspecified and aggregation rejects it. Do not infer ownership from matching
totals or sort/deduplicate fallback events.

The inbox cannot infer an ancestor/child relationship from numeric totals.
Using different IDs for a child and its owning parent will double-count;
the integration boundary above is mandatory. Cached doc reuse keeps the same
ID and payload; a genuine second solve gets a new ID. Do not subtract a
conservative candidate's engagement totals from the winner: `floorplan_build`
intentionally retains quantization work across rejected trials while separately
rolling back fallback events. Import the final supplied event vector unchanged.
Use typed C++ results, not `floorplan_json` counts serialized through doubles.

## Producer gaps closed by the authorized follow-up

The placement-only result now exports instantiate, breathe, L4/corridor and
facing-refit counts/events, including losing trials. Floorplan owns actual
legalizer, spatial-bound and fanout observations. Producer additions and merges
are overflow-checked before mutation. The implementation and 167 independent
function-entry contracts are documented in `producer_accounting_INTEGRATION.md`.
Parent integration must consume the disjoint aggregate above; registration
alone cannot make an unconsumed producer result appear in the census. No broad
ledger covers or inferred fallback firings were added to conceal missing work.

## Ledger declared-coverage migration plan (reviewed, not auto-registered)

Use the original native floorplan declaration metadata as the provenance seed,
not scanner output as authority. Each migration needs the live consuming symbol,
unit, source class, basis, owning step, actual input resolver, and a mutation
contract. Keep derived quantities as `CALC` with the original ordered inputs.

### Straightforward named-symbol candidates

`native/src/floorplan_internal.hpp::schgen::floorplan_detail::` contains nineteen
named policy constants. Reviewed candidate bindings are:

- `block_clearance → clear`; `edge_margin → edge_margin`;
  `mh_corner_keepout → mh_corner`; `edge_inset → edge_inset`;
  `cable_neighbor_gap → cable_gap`; `som_halo → som_halo`;
  `perimeter_keepout → perimeter`; `pack_efficiency → fill`;
  `som_occ_pad → som_pad`; `som_seat_band → som_seat_band`;
  `som_decoupling_inset → dec_inset`; `mh_inset → mh_inset`;
  `edge_pad_clear → edge_pad_clear`; `occ_top_mask → occ_top`;
  `occ_bottom_mask → occ_bottom`; `d13_min_subject_pins → min_subject_pins`.
- Preserve calculations `overmold_side_gap → overmold_gap` (22/2−8),
  `edge_band → edge_band` (15−4), and `occ_punch_mask → occ_punch` (1|2).
  The header currently stores folded values. Do not relabel those calculations
  as independent assumptions, or record old inputs disconnected from actual
  code. Bind the native formulas to canonical named input policies first.

The eight constants in `native/src/quantize.cpp::schgen::` correspond to
`place_grid/kGridMm`, `half_grid/kHalfMm`, `quant_credit/kCreditMm`,
`snap_erosion/kSnapErosionMm`, `outline_snap/kOutlineSnapMm`,
`fine_snap/kFineSnapMm`, `est_via_ordinary/kViaOrdinaryMm` and the impedance row
`kViaImpedanceMm`. The two via costs are derived rows, not arbitrary fitted
constants; retain their physical input formulas. The old declaration table's
unused or renamed Python covers must not be declared resolved merely because
another C++ number happens to have the same value.

Also reconnect actual consumers: `som_pose_half_mm` currently encodes the half
grid as `* 2 / 2` instead of referencing `kHalfMm`. The snap-erosion threshold
`5.0`, outline/grid epsilon `1e-6`, and rounding precision arguments remain
inline algorithm policies. Registering the eight scalar definitions does not
establish provenance for those separate literals; review and bind them without
changing the existing arithmetic order or claiming unrelated symbol coverage.

`native/include/schgen/ratsnest_gate.hpp::schgen::ratsnest_dispersion_max` and
`ratsnest_small_n` have clear existing bindings `dispersion_max` and
`dispersion_small_n`. `cross_k` is a caller parameter: record the actual input,
not `default_engine_config.cross_k` when the caller overrides it.

### Review/consolidation required before registering

- `pcb_stage_internal.hpp` defines `clear=.5`, `zone_pad=.3`, `slide=1.2`.
  These correspond to template clearance, zone padding and seat-slide policy,
  but duplicate other native policies. Consolidate to canonical numeric
  definitions/derived rows and live values; do not grant all three the same
  unrelated declaration or substitute `in.place_clear` where code uses `clear`.
- `pcb_escape_internal.hpp` defines `radius=1.8`, `lattice=.05`,
  `lane_handle=1`, `hole_hole=.5`. Existing concepts are
  `escape_construct_radius`, `escape_lattice`, `lane_handle`, and derived
  `clr_hole_hole = thermal_via_h2h + relief`. Also review the via ladder array
  and the `.10/.30/.10` clearance return values; scalar-declaration scanning
  alone does not establish those array/literal policies have provenance.
- `floorplan_compose.cpp` has eight named controls: `guard_mm=4`,
  `repair_max=16`, `median_passes=8`, `channel_min_nets=6`, `channel_floor=2`,
  `channel_per_net=.2`, `hop_weight=1`, `seed_weight=.05`.
  They need new or explicitly matched reviewed policy entries;
  similarity to another clearance/weight name is not evidence of equivalence.
- `pcb_stage_search.cpp` embeds candidate radius 9, step .5, cap 400, maximum
  half-width 60 and DFS budget 300000. These have existing concepts
  `candidate_radius`, `candidate_step`, `candidate_cap`, `grid_max_steps`,
  `template_node_budget`; hoist and bind actual consumers. The cast, thresholds
  and net-alignment `.1` must retain their caller/math semantics.
- `pcb_placement_breathe.cpp` has buried `eps=1e-4` and `step=.25`, plus leash,
  dispersion, page-origin and keepout literals. Hoist only after identifying
  units and proof roles. `floorplan_pack/build` similarly contain reseat,
  shape/outline/refinement and acceptance thresholds needing named consumers.
- `EngineConfig` in `project.hpp` and `PcbEmitPolicy` in `pcb_emit.hpp` are
  caller-overridable policy objects. Their defaults are not the build's live
  decisions. Registry providers must capture the actual instance supplied to
  generation/checks; changing an override must change the recorded value.

The C++ scanner currently reports numeric class/member defaults conservatively,
including runtime state initialized to zero. Distinguish policy schema fields
from ordinary counters/cache/geometry state before broad header adoption; do
not invent ledger entries for every zero to make a scan green. Conversely,
inline numeric literals/arrays are not fully covered by scalar declaration
scanning, so manual consumer review is required during this migration.

Suggested proof order: canonical quantization and ratsnest policies → floorplan
header/formula consumers → stage search budgets and template policy → placement
and escape policies → caller-config/emission policy schemas. For each group,
add an unregistered constant mutation, stale-cover mutation, missing-record
mutation and caller-override contract. Only then extend the manifest. Keep the
gate failing on genuine unregistered/buried decisions; do not synthesize covers
from its census or waive entire functions/files.

Existing `FloorplanAccounting::decisions` already contains actual values and
ordered inputs. Preserve those observations when wiring the ledger; do not
rerun the sizing calculations just to populate its registry. A cached document
replay should validate the stored decisions, not create another physical solve.

## Current proof

The isolated default audit target now runs 666 contracts, including 62 new
accounting checks. It executes a real native devkit zone solve, compares its
emitted counts/events against the existing independently captured zone fixture,
and imports the actual `prepare_pcb_floorplan(...).accounting` aggregate once.
It also covers mixed event/compact state, unsigned maximum and overflow,
negative/unknown-zero rejection, whole-batch atomicity, conflicting replay,
independent reset detection, concurrent imports, and zero evaluator calls.
The live provider test now links the existing core's LibXml2 dependency; this
is not a new production dependency of the accounting APIs. Builds stay under
`/private/tmp/schgen-audits-native.a2hr42/`, with strict C++17 warning flags.
