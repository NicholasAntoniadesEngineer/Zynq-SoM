# Native compose repair handoff

This slice ports `schgen/generate/compose_repair.py` and the `compose` command's
remaining orchestration. It does **not** reimplement Aristotle's independent
contract, coverage, composition-report or flow gates, and does not change the
parent's board pipeline, module, CLI, CMake or shared build outputs.

## Integration

Add these translation units to the native core:

```
native/src/compose_repair_json.cpp
native/src/compose_repair_edits.cpp
native/src/compose_repair_measure.cpp
native/src/compose_repair_driver.cpp
```

Public API: `native/include/schgen/compose_repair.hpp`.
Private helper: `native/src/compose_repair_internal.hpp`. The implementation
reuses the existing PCB JSON/format helpers and gallery/diagram UTF-8/file
helpers; keep `pcb_emit_internal.hpp` and `gallery_diagram_internal.hpp` available
beside these sources. No new external dependency is introduced.

The core must already contain placement/floorplan, the three
`pcb_placement_*_gate.cpp` units, and ratsnest gates. It also needs the parent's
coordinated `legalize.cpp` precision change and `accurate_norm.hpp`:

- Compile `legalize.cpp` and the four new units with `-ffp-contract=off`.
- `bbox_gap` and predictor distances use `accurate_hypot2`.
- `evaluate_terms` uses `accurate_facing_dot` for prediction.
- Public `facing_dot` and `flow_budget` retain their historical gate arithmetic.
  Prediction and final independent gate results are deliberately separate.

Do not call Python from the command adapter. Wire the explicit native host:

```cpp
schgen::ComposeCommandOptions options;
options.repair = args.repair;
options.dry_run = args.dry_run;
options.allow_intent = args.allow_intent;
options.max_steps = args.max_steps;

schgen::ComposeCommandPaths paths{
    project_root / "floorplan.json",
    project_root / "reports/compose_ledger.json",
    project_root / "reports/compose_ledger.md"};
schgen::ComposeCommandHost host;
host.build_model = [&]() -> schgen::ComposeBoardSnapshot {
    // Parent's native loader + build_pcb_model, with current spec and evidence.
    // Return both the exact PcbPlacementInput and the freshly placed PcbModel.
    // This callback must not publish the board, schematic, reports or sidecars.
    return build_fresh_native_compose_snapshot();
};
host.run_board = [&]() -> schgen::ComposeBoardRun {
    // Parent's COMPLETE native `board` command, including publication and all
    // mandatory verification. Capture its stdout and exit code. Never equate
    // build_pcb_model/prepare_board_pcb success alone with this command passing.
    return run_complete_native_board_command();
};
host.output = [](const std::string &text) { std::cout << text; };
return schgen::run_compose_command(options, paths, host).exit_code;
```

The two illustrative parent adapter names above are intentionally not supplied
by this slice: the parent owns `board_pcb.cpp` and full board-command execution.
They are **orchestration** hooks, not substitutes for solvers, term evaluators or
gates. The driver always measures final geometry itself with existing native
gate APIs; no callback can inject a compose ledger or accepted verdict.
The callback must reload the edited floorplan for the rebuild and subsequent
measurement. Reusing the initial input/model would be stale evidence.

For a CLI with both `--measure` and `--repair`, `repair` takes precedence, as in
the original. Otherwise measurement is the default; the `--measure` flag need
not be represented separately. CLI repair applies by default; `--dry-run`
prevents the spec write and board-command call. `max_steps` remains a reserved,
unused integer: **one selected edit per invocation**, even for zero, negative or
large values. Do not add an outer retry loop.

## Boundaries and failure semantics

The lower-level APIs parse, edit, measure, predict, rank and render without I/O.
They accept invocation-owned circuit, footprint, contract and spec snapshots.
`compose_plan_replica` forces the original two-side planning convention, selects
the actual chosen-shape metrics, and delegates to native floorplan and term
evaluation. Existing legalizer budgets remain unchanged: eight median passes
and the existing 16-repair budget; the Python `CUT_MAX` constant is unused.

`run_compose_command` is the explicit write boundary:

1. Parse repair intent, build the initial model and measure independent gates.
2. Generate edits in source order. Intent authorization is required for edge
   moves; duplicate authorization names use the last entry. The pull ladder is
   exactly `2, 5, 10, 20, 40, 60`; no extra weights are invented.
3. Predict every candidate. Invalid edits, spills and predicted hard RED are
   rejected. Sort by `(soft_red_count, -hard_margin_sum, area, description)`,
   stably, and print only the first ten ranked entries.
4. Measurement/no candidates/dry-run append ledger history but never edit the
   floorplan or call the board command. Diagnostic measurement returns zero
   even when the measured gates or repair triggers are red.
5. Apply only the top candidate, run the complete native board command once,
   then build a fresh native model and measure again. A nonzero board exit
   cannot be accepted; only the final 2,000 Unicode codepoints of its stdout
   are printed. There is no fallback to the second-ranked candidate.
6. Apply the original banded policy: rebuilt flow and LAW-5 must pass, area must
   not grow, target RED must improve, GREEN cannot become RED, fragile or
   non-target RED margins cannot worsen, and existing contract-violation counts
   cannot increase. Keep original epsilon boundaries, duplicate-term last-wins,
   missing-term/null-margin skips, and target exemptions. Advisory gate status
   is not silently promoted to a new mandatory gate.
7. Reject by restoring the original spec bytes and appending a `rejected:`
   ledger entry. Intent-only area growth still escalates and rejects; it is not
   auto-approved. Success leaves the spec edit and appends `applied:`. Neither
   branch commits to Git. Board artifacts from the host are not rolled back,
   matching the original command.

Additional safe boundaries: refusing a missing apply host before writing;
refusing to overwrite a concurrent spec edit; and restoring the tentative spec
on rebuild/measurement exceptions. A concurrent human edit is preserved even
while unwinding an exception. This is not a crash-recovery transaction.
Once the independent decision accepts, report-publication errors propagate
without undoing the accepted spec, so a published `applied` JSON entry cannot
be left describing a spec that the driver rolled back. Ledger JSON and Markdown
are atomic per-file replacements, not a multi-file transaction.

The JSON adapter preserves original integer/float spelling, large integer
tokens beyond binary64's exact range, object order, unrelated metadata, ASCII
escaping and final LF. Ledger JSON uses one-space indentation and sorted keys;
Markdown and diagnostics preserve the original bytes. Parser/schema errors
retain native strict validation. Spec validation names the deterministic
`floorplan.json` source rather than a random Python temporary filename.

## Independent contracts and provenance

All fixture JSON is immutable and hashed in `SHA256SUMS`. Verify from the repo
root with `shasum -a 256 -c native/tests/data/compose_repair/SHA256SUMS`.
No Python source or Python test runner is delivered. Capture scripts remain
only under `/private/tmp/compose-repair.hnNAox`.

- `python.json`: 112 acceptance mutations; ten edit/error cases; eight intent
  parsing cases; eleven proposal/ladder cases; byte-exact history JSON/Markdown.
- `carrier_strict.json`, `devkit_mini_strict.json`: original Python ledgers for
  both frozen real boards, a moved power part and a missing power sheet. The
  channel-demand wrapper is replaced with its independent Python body to avoid
  recording the old extension's FMA drift as a new specification. Final gates
  otherwise retain their original APIs.
- `predictions_strict.json`: real native-input-compatible candidate predictions
  captured with the Python evaluator and its pure Python numeric references,
  including edge movement, changed pull weight and invalid edits. Native tests
  compare every raw measured value, bound, margin, verdict and note exactly.
- `workflow_strict.json`: original repair driver with real frozen before/after
  board geometry and real Python candidate planning; captured dry-run, success,
  reserved zero/negative/large budgets, failed board exit and independent
  post-rebuild rejection. Only the external command transport is stubbed during
  capture. This is a transport/orchestration contract, **not** a claim that a
  stubbed board command passed physical verification.
- `ranking.json`: original driver ranking of eighteen independent mutations,
  including invalid, spilled and hard-RED exclusions, advisory near-intent,
  scoring ties, lexicographic tie-breaks and the ten-line output limit.
- `kernel_regressions.json`: 101 independent Python channel-demand results and
  36 pure-Python facing vectors. Fourteen channel counts differed in the old
  FMA-enabled extension. Facing vectors target `accurate_facing_dot`, **not**
  the intentionally retained legacy public gate primitive.
- `bbox_regressions.json`: 84 Python bbox-gap vectors with exact input boxes,
  derived dx/dy and expected hexadecimal doubles. These exercise `bbox_gap`.
- `carrier.json`, `devkit_mini.json`, `predictions.json`, `workflow.json`: retained
  initial captures using the then-loaded extension. They document the observed
  historical arithmetic, are never overwritten, and are not used as a waiver
  for the explicitly corrected predictor kernels.

Source hashes are embedded in the captures. Original repair source SHA-256:
`b731d643c2aba92063bd2118238a73e4d1e08dea382eb35b3774c0ec5369a87b`.
Original compose source SHA-256:
`37527bfa3343730bb96381959760b2bc025bd7502648f266a05b9d58009699a3`.
Both-board geometry/footprints come from existing independently captured
`pcb_emit`, `pcb_placement` and `floorplan` fixture families; the tests reuse
`native/tests/pcb_placement_fixture.hpp` without changing it.

## Build and proof

Final strict C++17 result: **4,787 compose assertions passed**, with
`PATH=/nonexistent`. The complete ASan/UBSan dependency closure also passes
**4,787 assertions** after the parent's final split between accurate predictor
arithmetic and legacy public gate arithmetic. All JSON fixture hashes verify.
The additional focused kernel contract passes **257 exact comparisons**.

Contract sources:

```
native/tests/compose_repair_contracts.cpp
native/tests/compose_kernel_contracts.cpp
```

Both executables take the repository root as their sole argument. The focused
kernel test can be omitted from CTest if the parent includes its bbox vectors
in `legalize_precision_contracts`; it is an independent runnable handoff, not
an alternative gate or a relaxed test mode.

Isolated strict command (the extra legalizer/gate sources override any older
objects in the existing archive; remove those source arguments once the parent
has rebuilt that archive with the coordinated integration):

```sh
task_compose_build=$(mktemp -d /private/tmp/compose-repair.XXXXXX)
c++ -std=c++17 -O2 -mmacosx-version-min=26.6 \
  -Wall -Wextra -Wpedantic -Werror -ffp-contract=off -I native/include \
  native/tests/compose_repair_contracts.cpp \
  native/src/compose_repair_json.cpp native/src/compose_repair_edits.cpp \
  native/src/compose_repair_measure.cpp native/src/compose_repair_driver.cpp \
  native/src/pcb_placement_contract_gate.cpp native/src/pcb_placement_flow_gate.cpp \
  native/src/pcb_placement_compose_gate.cpp native/src/legalize.cpp \
  native/build/libschgen_core.a -lxml2 -pthread -o "$task_compose_build/contracts"
env PATH=/nonexistent "$task_compose_build/contracts" "$PWD"
```

The full contract includes a fresh native `build_pcb_model` after the applied
edit, not merely recorded final geometry, plus missing-host, early malformed
intent, host-exception rollback and concurrent-human-edit preservation cases.
For sanitizers, rebuild the entire dependency closure; mixing the instrumented
JSON/container code with old archive objects is not a valid sanitizer run.
The isolated 81-translation-unit ASan/UBSan build script and objects are under
`/private/tmp/compose-repair.hnNAox`, with no uninstrumented project archive
linked. LeakSanitizer is not claimed on this macOS runtime.

Final executables: `contracts-final`, `contracts-asan`,
`kernel-contracts-final` and `kernel-contracts-asan` in that scratch directory.
`strict-final.map` and `asan.map` record the linked object provenance.

No commit or staging was performed by this worker. All shared kernel/build
changes mentioned above belong to the parent; this worker only added the
compose header, four sources, private helper, two contract sources and data.
