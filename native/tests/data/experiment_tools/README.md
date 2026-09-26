# Native repository experiment utilities — integration handoff

Status: sources and contracts complete. Shared floorplan/placement hook files
are frozen at the validated checkpoint. No shared build, commit, CMake, main
CLI, project CLI, legalizer, emitter, board-pipeline or ledger edit was made by
this worker. The parent owns command integration and complete board validation.

## Sources and linkage

Public interfaces:

- `native/include/schgen/experiment_observers.hpp`
- `native/include/schgen/experiment_tools.hpp`

Observer sources (already added to the parent's CMake):

- `native/src/experiment_observers.cpp`
- `native/src/experiment_floorplan_probe.cpp`
- `native/src/pcb_placement_observer.cpp`

Add these four utility sources to `schgen_core`:

- `native/src/experiment_tools_json.cpp`
- `native/src/experiment_tools_board.cpp`
- `native/src/experiment_tools_probe.cpp`
- `native/src/experiment_tools_catalog.cpp`

`experiment_tools_internal.hpp` is private. Utilities reuse the integrated
`compose_repair_json.cpp` JSON type/spelling transport, native authoring,
floorplan cross estimator, PCB placement, pad projection, MST and quantizers.
They do not duplicate gate algorithms. The probe's length accumulation uses
`accurate_hypot2`, matching the original probe's Python `math.hypot` path;
public legacy gate arithmetic is unchanged.

The only shared hook edits are append-only observer fields in `FloorplanInput`
and `PcbPlacementInput`, plus `floorplan_{internal,geometry,cross,pack}` and
`pcb_placement_{internal,build,model}`. The fields are default-null
`shared_ptr<const ...>`, not raw pointers. A **coherent rebuild of every
dependent translation unit** is mandatory after these object-size changes.
Do not mix old/new ABI objects, even though existing field offsets are intact.
The parent separately added `BoardInputOptions.experiment` forwarding.

## Concrete CLI dispatch

Include `schgen/experiment_tools.hpp`. Existing project-selection and native
catalog lifetime rules apply. All returned output already ends in LF; emit it
without adding another newline.

1. `chir-rung TAG [SHEET ...]`:
   call `run_chir_rung(paths, host, tag, sheets)` and print `.output`.
2. `w11-sweep MM [SHEET ...]`:
   call `run_w11_sweep(paths, host, mm_argument, sheets)` and print `.output`.
   The decimal/scientific argument is retained verbatim in the report. It must
   parse to a representable finite nonnegative value; source expressions are
   deliberately not executable. Zero is allowed. No quantize source is opened.
3. `w12-bound TAG [SHEET ...]`:
   obtain fresh native-authored/netlist-extracted `PcbPlacementInput`, call
   `run_w12_bound(input, tag, sheets)`, print `.output`. No board publication.
4. `w12-stageprobe TAG [SHEET ...] [--cons-only]`:
   use the same fresh input provider and call
   `run_w12_stageprobe(input, tag, sheets, conservative_only)`.
   To exactly retain the historical argument filter, exclude all `--...`
   arguments from the sheet list and test presence of `--cons-only`; other
   `--...` arguments were ignored by the original script.
5. `dump-circuits`:
   call `run_dump_circuits(project_paths, native_authoring_project)` and print
   the returned string. This command is an explicit publication boundary.
   For a read-only preview, call `prepare_native_circuit_dumps` instead.
   `native_authoring_project` is the registered identity (`carrier` or
   `devkit_mini`), not the human-readable project title. Open/retain the native
   part catalog first. Circuit authoring uses live C++ factories, not saved IR.

For commands 1/2 use the parent-owned dedicated native measurement document:

```cpp
ExperimentBoardPaths paths{
    project.project_root / "floorplan.json",
    project.reports_dir / "fallback_baseline.json",
    project.project_root / "Zynq_Carrier.kicad_pcb",
    project.reports_dir / "experiment_verdicts.json"
};
ExperimentBoardHost host;
host.run_board = [&](const ExperimentBoardRequest &request) {
    auto options = board_options; // parent's complete native board options
    options.no_render = request.no_render;
    if (request.ordinary_via_mm) {
        auto experiment = std::make_shared<FloorplanExperiment>();
        experiment->ordinary_via_mm = request.ordinary_via_mm;
        options.pcb.experiment = std::move(experiment);
    }
    // Capture the complete native command's stdout/stderr, including progress;
    // return its actual status. Do not turn placement success into BOARD PASS.
    return run_complete_native_board_and_capture(project, options);
};
```

`run_complete_native_board_and_capture` above denotes the parent's existing
full-board orchestration adapter, not a provided function or permission to
skip gates. It returns `ExperimentBoardRun {exit_code, stdout_text, stderr_text}`.
Use the parent-wired `BoardInputOptions.experiment -> FloorplanInput.experiment`.
If the base options already contain an observer, preserve its configuration
when installing the explicit ordinary override.

Successful utility return maps to exit zero, even if the historical diagnostic
prints `pass=False`; input/build/publication exceptions remain failures. The
separate `.board_exit_code` is preserved. Historical `pass` means only that the
captured stdout contains `BOARD: PASS`, regardless of subprocess status. It is
not an independently computed gate verdict or an approval to publish hardware.

## Required native board measurement transport (parent-owned)

The parent added typed optional measurements to `BoardPipelineResult` and a
dedicated `board_pipeline_experiment_json` serializer. The main
`board_verdicts.json` schema stays unchanged; the host selects
`experiment_verdicts.json` through `ExperimentBoardPaths.verdict`. The original
scripts read the following keys from the historical verdict document:

- Root `board_w`, `board_h`: actual final `PcbModel.board_w/board_h`, no display
  rounding or inference from human reports.
- `ratsnest.cross_mm`: final-model `RatsnestGateResult.cross_mm`, already
  rounded to one decimal. Preserve float spelling, including `.0`.
- `ratsnest.n_top`, `ratsnest.n_bottom`: integer `PcbModel.n_top/n_bottom`.
  Top count **includes emitted fiducials**. These are the same counts returned
  by native ratsnest-document generation, not counts of MST endpoints.
- `fallbacks`: actual build census. W11 reads `punch_free_plan_rejected`, with
  missing entry printed as `None`; CHIR prints the entire dictionary.
- Red names are top-level objects whose `ok` member is the boolean `false`.
  Zero, null, absent `ok`, and nested gate statuses are not equivalent.
  Historical verdict publication sorted keys, so retain sorted top-level keys
  for historical red-name order. `ratsnest` itself is measurement-only;
  `ratsnest_gate` was the separate hard-gate verdict.

The dedicated serializer also exposes native-only board gates and uses
`fallback_gate` to avoid colliding with the numeric `fallbacks` census. This is
an expanded diagnostic scope: when such a gate fails, its name can now appear
in `reds`. Strict historical red-name parity would instead require a selected
legacy PCB-verdict subset; the full native board gate result must stay intact
either way. The utility itself faithfully scans whichever document is passed.

Never synthesize zeros for missing measurements. If the native run did not
produce live model/geometry evidence, omit unavailable measurements and let
the experiment fail explicitly while restoring its input files.

## Write and measurement boundaries

- CHIR/W11 read original spec and baseline before any write. Sheet candidates
  temporarily set only the requested `interior[SHEET].layer` to `either`, using
  original indent-1/ASCII JSON. Both originals are restored byte-for-byte on
  success, gate failure, host exception and malformed measurement output.
  Board artifacts produced by the host are intentionally not rolled back.
  Restore/publication errors propagate; this is not a filesystem transaction.
- W12 commands modify only a private typed input copy and construct a native
  model. They write no spec, baseline, PCB, catalog, sidecar or render artifact.
- W12BOUND records *every normally completed* attempt, including `packed=false`.
  It records no thrown attempt. An unscoped estimate updates the latest
  completed row—even while a subsequent attempt is running. Outline dedup and
  equal-area stable ties match the original script; no aggregate reconstruction.
- Stage observations run at actual zone completion, plan selection, shape
  binding and each placement checkpoint. Instances are projected from current
  positions, side/fixed/grid/rotation/mirror state and current immutable mods.
  Emission checkpoints still exclude synthetic fiducials, as `_insts_now` did;
  only `FINAL_MODEL` includes them. Observer measurements do not increment
  production quantization accounting or fabricate stage movement counts.
- Conservative-only throws at entry to an actual punch-free attempt and uses
  the solver's normal conservative fallback. It does not rewrite the winner.
- Dump publication authors, validates roundtrip and writes each sheet in sorted
  registry order. Later failures leave earlier writes, matching the script.
  Preparation is pure; no stored `circuit.json` becomes a production generator.
- The original five scripts remain unchanged. `dump_circuits 2.py` was inspected
  only and is byte-identical to `dump_circuits.py`; it has not been deleted.

## Independent evidence

`SHA256SUMS` pins every fixture. No Python capture script is delivered.
Captures were run only from `/private/tmp/native-experiments.LfDTUF`; footprint
mirrors were checked read-only and shared source/artifact writes were avoided.

- `observer_reference.json`: original W12 callback ordering/dedup, three
  independently mutated projection frames, forced-rejection string, and proof
  that assigning the old Python W11 constant to 987.25 still returned native
  2.2. This no-op is replaced by the approved explicit override.
- `driver_reference.json`: unmodified CHIR/W11 scripts executed with isolated
  in-memory filesystem/process transport. Eight exact report/candidate cases
  cover nonzero status with PASS token, zero status without token, Unicode
  tails, line boundaries, missing sheet insertion and exact restore bytes.
  Also includes independently serialized circuit IR cases.
- `carrier_stageprobe.json`, `devkit_mini_stageprobe.json`: original probe over
  actual Python placement execution, not reconstructed final poses.
- `devkit_mini_bound.json`: all candidate outlines and selected estimates from
  2,170 actual original packing attempts.
- `devkit_mini_conservative.json`, `devkit_mini_mutation.json`: original forced
  conservative and candidate-layer/ordinary-cost runs. These particular devkit
  winners are unchanged; equality is a measured result, not an assumed waiver.
- `carrier_via_vectors.json`: 13 genuine bottom-shape estimator candidates at
  0, 2.2, 5 mm ordinary via cost, independently evaluated through the original
  estimator with only its cost provider overridden. All 39 measurements match.
  Example `board_aux` shape 3: 16075.1 / 16152.1 / 16250.1 mm. The knob is
  demonstrably effective, while controlled-impedance costs remain unchanged.
- `devkit_mini_via_vectors.json`: independently records that this spec offers
  no bottom variants; it is not used as a vacuous passing vector contract.
- `catalog_reference.json`: exact byte lengths/SHA256 for all 37 carrier and
  12 devkit dumps. Expected bytes were independently formatted from immutable
  original-Python authoring-gate IR, whose source hashes are recorded.
- `probe_format_reference.json`: independent complete stdout byte hashes.

## Validation and test integration

Strict flags: `-std=c++17 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off`.
Isolated macOS builds additionally used `-mmacosx-version-min=26.6`.

- `experiment_observer_contracts ROOT --live`: **121,982 assertions PASS** in
  strict and full-closure ASan/UBSan builds. Full carrier/devkit null, empty and
  recording-observer solves have exact complete models, stage poses, fallback
  sequences and production accounting. Default observers invoke zero snapshot
  factories. Attempt counts are 2196 carrier / 2170 devkit.
- `experiment_tools_contracts ROOT --live`: **24,392 assertions PASS** in
  strict and full-closure ASan/UBSan builds, including complete report bytes,
  live native catalog authoring/publication, restore/failure boundaries and
  independent effective override measurements. No tolerances or waivers.

Add an executable for `native/tests/experiment_tools_contracts.cpp`, link
`schgen_core`, apply the strict flags, and register the test with `ROOT --live`.
The observer target has already been added by the parent.

Proof executables are `/private/tmp/native-experiments.LfDTUF/observers-strict`,
`observers-asan`, `tools-strict`, `tools-asan`. The sanitizer executable links
only fully instrumented objects (140 units), no uninstrumented core archive;
`tools-asan.map` records the closure. Build scripts are in the same private
directory. No shared native build/output directory was used.
