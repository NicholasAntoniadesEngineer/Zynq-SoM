# PCB placement, stage templates and escape: native integration handoff

## Scope and readiness

The implementation is a live, input-driven C++17 port of PCB `placement.py`,
`stage_templates.py`, escape planning, SI triage and return-path copper
orchestration. It does not load a saved placed board, read test fixtures, invoke
Python, run a subprocess or write files. Mirrored footprints are invocation-owned
in-memory snapshots. The parent owns the live input loader, shared build/module/
CLI wiring, independent gate migration and commits; none were changed here.

Public entry points are in `schgen/pcb_placement.hpp`,
`schgen/pcb_stage_templates.hpp` and `schgen/pcb_escape.hpp`.

1. `build_pcb_zone_geometry(input)` derives the complete zone and shape offers.
2. `prepare_pcb_floorplan(input, zones)` derives the live compose term index,
   local/per-shape metrics, channel demands, impedance classes and participants.
   It retains the caller's prior escape corridors, not precomputed compose data.
3. `build_pcb_model(input)` owns that preparation, the native floorplan solve,
   shape binding and every subsequent placement stage through escape copper.
4. `place_pcb_model(input, zones, stage)` is the lower-level alternative when
   the caller already owns the corresponding native floorplan solve.
5. Pass the returned model to the existing emitter and independent gates.
   `render_pcb_escape_block(plan, metadata)` emits exact sorted/indented JSON
   when the caller separately uses the escape APIs.

`PcbPlacementResult` carries the final model, owned floorplan solve/documents,
checkpoint poses and placement fallback events. Floorplan accounting, including
zone quantization/fallback events, is in `result.floorplan.plan.accounting`;
`result.fallback_events` is not an aggregate verification status. Zone and stage
results also expose actual per-call quantization counts and ordered events.

## Mandatory gates not implemented by this family

**A constructed model is not a successful full-board verification verdict.**
The parent must retain these independent operations in native orchestration,
with their original wired/gated versus inert/advisory/not-applicable policy:

- `placement_contract_gate.py`: footprint-ID pin validation, independent final
  placed-pad checks, all structure kinds, unknown-structure rejection,
  `check_all`, and coverage/reporting for every authored contract. Solver/refit
  constraints are not a replacement for measuring the final moved model.
- `placement_flow_gate.py`: independent final-model flow, facing, far and
  `near_max` checks, scoped not-applicable handling, missing-endpoint failures,
  counters, diagnostics and report.
- `floorplan_compose.py`: final-model `measure_terms`, `compose_report`, hard/
  soft/NA coverage, escape corridor intrusion reporting (including T2-managed
  versus unmanaged classification) and cross-airwire/channel hotspot reporting.

What **is** covered from compose: live `build_term_index` semantics (merge,
tightest bounds, enforcement status, output refs, advisory near intent, scoped
NA and unknown external-key rejection), zone/shape metrics, channel demand and
wired-participant derivation. The integrated floorplan library consumes these
for predictive terms/legalization. Reuse
`prepare_pcb_floorplan(input, zones).compose.index` for the final compose gate;
do not maintain a second independently drifting index builder.

The independent gate inputs are already available from authored contracts,
canonical circuits plus stable sheet-index board refs, exact placed footprint
snapshots and the final model. Existing native pad-box, gap, flow-budget,
facing and MST primitives can be reused. Compose intrusion reporting additionally
needs the prior sidecar's coexistence records, not just corridor rectangles.
Do not replace any of these gates with an unconditional success, frozen result
or baseline parity test.

## Parent-owned live input requirements

`load_board_inputs` in `board_inputs.hpp/.cpp` is the sole live loader. This
family neither duplicates nor modifies it. Populate `PcbPlacementInput` with:

- Actual ordered circuits, validated link, stable sheet-index mapping and
  independently extracted ordered board netlist. Preserve authoring/net/pin
  order where represented as vectors: order breaks solver and MST ties.
- Current project policy (wired sheets, pilot sheets, board/SoM options),
  optional floorplan intent, regulator analysis, signal specs, SoM scan,
  source labels and footprint courtyard dimensions used for area estimation.
- Every discovered contract for the selected project, including inert ones.
  Preserve JSON object order. Contract pin names are footprint pad IDs.
- Exact immutable footprint bytes/documents and `footprint_of` entries that
  agree with their opaque pool keys, including the fiducial. Unresolved ordinary
  parts follow the original skip policy; mandatory contract members reject.
  Source paths are meaningful: connector templates inspect filename stems,
  mirroring uses library/source identity and equivalent-part reorder sorts
  source paths. Do not replace source paths with arbitrary hashes; pool keys
  may be opaque and need not equal the source path.
- Parsed SoM interface, its exact unmodified source bytes (for SHA-256),
  connector return-path dossier snapshots, and the actual function map with
  PUDC strap overrides applied. Do not reserialize the interface before hashing.
- Optional prior `escape_block.json` corridors: sorted
  `t1_constraints.corridors` entries become `{ "escape:" + name, rect }`,
  with 25 mm subtracted from all four board-frame coordinates. A missing
  sidecar means no prior corridors. Both frozen boards have six. These are
  genuine solve inputs, not a saved solve. Pass coexistence records separately
  to the independent compose reporter when it is implemented.

Defaults are `two_side=true`, placement clearance `0.5` mm and emission origin
`(25,25)` mm; this implementation rejects another origin and nonpositive/nonfinite
clearance. Optional `module_offset` retains existing floorplan semantics.
`two_side=false` preserves the original *top-preferred* behavior, not a guarantee
of an all-top board: floorplan sizing still uses normal two-face offers. The
devkit result has 145 top and 18 bottom parts. Carrier rejects binding shape 8
for `bringup_rails`, whose top-preferred geometry registers seven shapes. This
is the independently captured original rejection, not a native waiver/fallback.

## Exact source/dependency integration

Add these sources to the parent's core target; no build files were edited:

```text
native/src/pcb_escape_model.cpp
native/src/pcb_escape_triage.cpp
native/src/pcb_escape_plan.cpp
native/src/pcb_escape_copper.cpp
native/src/pcb_escape_json.cpp
native/src/pcb_stage_geometry.cpp
native/src/pcb_stage_search.cpp
native/src/pcb_stage_power.cpp
native/src/pcb_stage_zone.cpp
native/src/pcb_placement_inputs.cpp
native/src/pcb_placement_pack.cpp
native/src/pcb_placement_variants.cpp
native/src/pcb_placement_zones.cpp
native/src/pcb_placement_model.cpp
native/src/pcb_placement_moves.cpp
native/src/pcb_placement_breathe.cpp
native/src/pcb_placement_build.cpp
```

Keep `pcb_escape_internal.hpp`, `pcb_stage_internal.hpp` and
`pcb_placement_internal.hpp` private. Dependencies are the existing core/pack,
PCB model and check geometry, return-path and escape checks, ratsnest, native
floorplan and emission libraries. The public result additions require rebuilding
consumers, not only relinking stale objects. No extra third-party library is
introduced. Maintain `-ffp-contract=off` on this family and existing numeric
dependencies: algebraically equivalent arithmetic can change exact ties.

Register separate executable contracts (each takes the repository root):

```text
native/tests/pcb_escape_contracts.cpp
native/tests/pcb_stage_contracts.cpp
native/tests/pcb_placement_contracts.cpp
```

The placement contract also includes `pcb_placement_fixture.hpp`. Its default
mode is `--production`: live authored/footprint inputs go through the actual
native floorplan and every placement stage. `--placed-only` uses an independently
frozen solve for diagnosis; it is not the production proof. `--zones-only` and
`--single` are focused diagnostics. Tests never bless/update expected bytes.

For an isolated manual build, first obtain an archive containing the dependencies
above, but not necessarily these new sources. Use a fresh `mktemp -d` directory
under `/private/tmp`; compile the listed translation units there, then link
each test with those objects and the existing archive. The tested compile flags
on this host are:

```text
-std=c++17 -O2 -mmacosx-version-min=26.6
-Wall -Wextra -Wpedantic -Werror -ffp-contract=off -I native/include
```

Link with the existing `native/build/libschgen_core.a`, `-lxml2 -pthread` and the
same deployment target. Do not launch a shared native build from a worker:
configured build trees share outputs/catalogs. All development builds here
used an isolated `/private/tmp` executable/object directory.

## Independent reference evidence

Reference data lives in `data/pcb_placement/` and `data/pcb_escape/`; these are
test-only inputs/expected results, never production data. Existing
`data/pcb_emit/` and `data/floorplan/` supply independently captured model,
footprint, emitted-board and floorplan reference bytes. `pcb_placement_SHA256SUMS`
records the delivered immutable fixture bytes.

`capture_pcb_placement_reference.py` and `capture_pcb_stage_mutations.py` document
the original-Python capture procedure. They print to stdout and do not generate
mirrored files; existing mirror bytes must agree with the original transform.
Their recorded Python source SHA-256 values are:

```text
placement.py       472fb6ae85c1201d1371f80a6e66992dea5c0016ef7faeeb47ef2354c57d903e
stage_templates.py 87607e7b9f303a4afc723fa4df0e669c3c27069a2c18f9a9adf5a3309548aeec
```

Together the contracts check all 39 board zones, 27 original stage invocations,
29 independently captured stage mutations, both full default boards and the
two top-preferred outcomes. It compares exact physical/model data and all
placement checkpoints, and exact emitted PCB/design-rule plus floorplan SVG,
Markdown and decision-ledger bytes. Only provider-owned `mod_path` strings are
removed from model JSON comparison; exact footprint document bytes and all
other instance/model fields are separately compared. Negative oracle cases
match policy-rejection reasons, not Python/C++ exception class or list-repr
spelling. Additional typed C++ input guards are tested separately; they are
not presented as Python-oracle cases.

Escape contracts recompute copper, metadata, plans and full sidecar bytes for
both supplied boards plus independent policy/adversarial cases. Stage contracts
check complete offsets, extents, rotations, ordered fallback events and actual
quantization counts. Runtime proof does not need a Python executable.

Final strict-build rerun, with `PATH=/nonexistent` for all three executables:

- PCB placement: **124,437 assertions passed** (default production mode).
- PCB stage templates: **2,787 assertions passed**.
- PCB escape: **20,290 assertions passed**.
- All 14 delivered fixture SHA-256 entries verified unchanged.

No shared build was run and no commit was created by this worker.
