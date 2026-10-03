# carrier — project HISTORY (archived planning logs)

## 2026-10-03 — compact query reuse and complete post-pipe validation

(Autonomous, per full-autonomy directive.) Reuse exact duplicate occupancy
queries only inside a single compact seat-search invocation. The occupancy,
anchor and board are invariant there; the key preserves every varying geometry
field, ordered children and scalar bits. All estimator alternatives and their
shape-key operations remain. Malformed inputs bypass reuse, exceptions are not
cached, and counter-overflow risk re-executes the real query. No saved-work counts
are injected into the ledger. Public/default searches retain their old behavior.
Seven integrated contract groups passed, including both-board exact output,
frozen floorplan/occupancy precision and independent query-accounting oracles.
The private pre-strict-facing carrier census removed 288,715,276 actual cell
checks with byte-identical PCB output; a fresh latest-state profile is separate
evidence, not implied by that older run. Raw cell-counter microbenchmark pairs
and their slower null-sink cases are preserved in native/benchmarks.

Complete no-render board runs at 821226b5 prove the transactional AST auditor
passes both 68-file source audits. Devkit passes all mandatory gates. The compact
carrier remains rejected: SW7002 has 1.320 mm fanout clearance against 2 mm, and
154 interior reseats exceed the ceiling of 18. Its experimental 170x165 mm board
does not replace the accepted 168x163 mm incumbent. Power-facing and non-unrouted
DRC pass; advisory findings and skipped rendering remain explicitly reported.
The receipt in native/benchmarks/2026-10-03-ast-pipe-board-validation.json records
hashes and timings. Concurrent validation timings are not a controlled speed
comparison; no historical Python result was relabeled or remeasured.

Latest-state follow-up at 51ba61d8 reproduced the exact experimental PCB hash
and 170x165 mm outline. Actual cell calls fell from 10,312,518,948 to
9,502,591,256 (809,927,692 fewer; 7.85%), while every successful shape-key call
remained (410,359). The recorded model times, 362.07 and 341.50 seconds, used
different harnesses under concurrent load and are not a controlled speedup.
See native/benchmarks/2026-10-03-compact-seat-memo-latest.json for full scope.

The SW7002 failure was independently reproduced from the exact saved plan and
final PCB hash. Its 1.32 mm gap to C10005 exists at initial emission and is
unchanged through every subsequent movement stage. The bottom-primary mixed
shape carries the top minority face as a child reservation with zero fanout
reach/inset; the actual occupancy predicate therefore accepts this illegal
pair. Correcting child geometry transport, rather than a hand-tuned component
translation or disabling the owned alternative, is the next implementation.

Documentation provenance is also corrected at its C++ producers: fresh output
cites native sources and describes the outline as the smallest feasible result
found by the bounded aspect/grid search and greedy order, not a global minimum.
Only exact prose and embedded Markdown length fields changed in reference
fixtures; geometry, operation receipts and historical timing provenance remain.

## 2026-10-03 — overlap compiler output with transactional AST parsing

The source auditor now parses through a bounded stdout pipe while Clang emits
its AST. The existing generic post-exit stdout consumer is unchanged. Parsed
state stays private until complete output validation and successful child exit;
parser errors cannot mask later invalid UTF-8, compiler failure or timeout.
Early parser return/failure still drains output and joins the child reaper.
The compiler worker count remains two. One per-scan projection slot limits
simultaneously retained ASTs through semantic visitation; waiting compilers use
pipe backpressure. No AST fields, semantic checks, macro preprocessing, manifest
coverage, registry checks or ledger checks were removed or cached.

Parent integration repeated three alternating-order pairs on four actual source
files. All six full ordered censuses are byte-identical (4 files, 218 function
identities, 32 quantization sites). Median elapsed time was 20.845902 s before
and 13.539726 s after, a 35.05% reduction; the largest paired sampled aggregate
RSS increase was 171.86 MiB. Raw rows, census hash, baseline hash, reproduction
target and limitations are recorded in
`native/benchmarks/2026-10-03-ast-pipe-subset.json`. The independent pre-pipe C++
auditor is vendored and hash-checked at configure time, with no build-time Git
or network dependency. These are subset measurements under a concurrent host,
not full-audit/board or historical-Python speed claims.

Transport proofs cover error precedence, malformed/partial output, child/parser
overlap, draining, timeout, reaping, closed stdio and concurrent descriptor
inheritance. Linux uses atomic close-on-exec pipe creation to close a potential
older-glibc inheritance race; its runtime branch remains unverified on this Mac.
The isolated transport suite also passed ASan/UBSan. Whole-board validation and
timings remain separate from these focused source/transport contracts.

## 2026-10-03 — owned-quality selection, inter-stage protection and strict facing

Compact packing now transports actual zone-quality evidence and considers the
complete set of equally ranked feasible shapes. It removes strictly dominated
per-capacitor gap vectors, then selects the lowest surviving stable shape index.
Primary dimensions, estimator, anchor distance and face must match exactly;
ownership identities, pin/net roles, sides, bulk gap and fanout evidence must
remain compatible. Missing/rejected evidence is not a zero score. Dominance is
not used as a sort comparator or a running-incumbent fold, both of which can
give inconsistent three-way results. Sheets without quality evidence skip the
additional ranking work. No hardware distance limit or movement permission is
inferred from these optimization measurements.

Actual-engine regressions cover dominated originals, invalid/missing evidence,
default parity and the three-way frontier. The two-pilot complete pack proof
elects a bringup_rails owned alternative (34 -> 60) with unchanged dimensions;
board_aux retains shape 11. This is not a smaller accepted carrier. Compact L4
pull and reorder now exclude declared ownership endpoints from independent
movement or interchangeable-capacitor swaps; unrelated parts in the same sheet
remain eligible. Corridor eviction still needs a separate ownership correction.

An archived failing carrier proved the selected power shape's metrics exactly
match the actual seed, breathed and guarded-refit poses. Its negative facing
dot was nevertheless accepted by the composer's L4-deferral rule. Compact
compiled hard-facing terms now explicitly require the normal facing check,
including legalize(false) fallback. Other guard semantics and default behavior
remain unchanged. The reproduced term rejects with unchanged geometry; this
does not assert that the full search has found a legal replacement.

Occupancy cell-index accounting now borrows a lazy counter slot for one four-call
query/update scope. Every actual scalar entry still performs its checked increment
before validation. No query, count, geometry or candidate is fabricated or cached.
Independent entry, overflow-prefix, map-lifetime and threaded tests pass, as do
the 3,381 frozen occupancy contracts and geometry digest. Six interleaved counted
query microbenchmark pairs measured 0.250–0.261 s before and 0.109–0.111 s after,
with identical geometry and 10,006,324 entries each; the null-sink control was
1–5% slower. These concurrent-host microbenchmarks are not board-build speedups.

The stage profiler previously loaded default-only inputs before toggling compact
search, which would omit the new owned alternatives. It now resolves compact
inputs for on/both mode, labels that preparation, and has a loader regression
requiring both ownership groups and all 56 alternatives. Earlier profiles from
before owned-group integration must not be used as measurements of that workload.

The current default carrier PCB independently matches the previously validated
8509 build byte-for-byte (SHA-256 8437ddd4fbcf012c800bed70a1b6968c0d09444b00c9e816390dfc5946360633).
The live-reference mismatch was traced completely to the earlier `529c196a`
RV-3028 footprint fix: restoring only that old footprint reproduces every byte
of the old board. The reference now removes its three zero-length courtyard
segments and updates seven consequent graphic UUIDs. No placement, electrical,
outline or valid graphical geometry changed; devkit and all sixteen strict
report references already matched. The unchanged two-board live test passed
against this isolated artifact correction. No new
whole-board compact acceptance, audited timing comparison or rendered finalist
is claimed by this implementation batch.

Integrated validation: a full ABI rebuild completed; all 22 selected ownership,
quality, profile-input, strict-facing, compose, occupancy, precision-source and
frozen-placement CTests passed (168.60 s concurrent wall time, not a benchmark).
The unchanged two-board live-reference test then passed in the shared checkout
(32.03 s). The archived actual-carrier strict-facing replay also passed. The
complete compact search remains a separate construction/acceptance exercise.

## 2026-10-03 — standalone compact input catalog isolation

The first integrated standalone compact `pcb-stage` invocation exposed a hidden
global-catalog precondition in the ownership adapter: circuit JSON loading does
not open the authoring catalog. Unit tests had inadvertently satisfied that
precondition. The adapter now reads independently scoped, owned catalog snapshots
from the project paths; it neither depends on nor replaces the caller's global
authoring session. The existing mapped-file reader and decoder are shared, not
duplicated. Closed-session loader regression and catalog lifecycle tests pass,
including missing/malformed files, failed partial batches, preserved existing
mapped readers and fresh reads after atomic replacement. No board geometry or
hardware requirement was changed by this correction.

The earlier default devkit validation at `a14031a1` is recorded separately in
`native/benchmarks/2026-10-03-owned-adapter-devkit-validation.json`: 12 sheets,
successful no-render board aggregation, zero non-unrouted DRC errors and a passing
68-file source audit. Advisory failures and skipped outputs remain explicit;
this is not compact-carrier acceptance or a controlled performance comparison.

## 2026-10-03 — production owned-group alternatives and bounded copy removal

Wired the validated pilot ownership into compact board inputs and zone generation
(autonomous, per full-autonomy directive). Missing manifests or disagreement
with independent compiled requirements, live circuits, catalog pins or extracted
hierarchy connectivity reject the input. Opaque immutable evidence grants no
new side or movement permission. Every original shape/index is retained; local
owned alternatives are appended without recursively searching their outputs.

Integrated adapter tests pass 2,702 checks: 76 original pilot shapes retained,
56 alternatives appended, all 132 shapes measured, and exactly 160,480 additional
registered pose operations counted, including rejected searches. Shape metadata
distinguishes measured/rejected/not-applicable evidence and retains named-terminal
roles and sides. Same-size quality selection remains a separate integration.

A new real-input/synthetic-pose regression first proved that breathing attached
a declared bypass capacitor to a nearer wrong owner. Compact breathing now
preserves declared membership across faces and propagates existing fixed-member
constraints through the group. Twelve movement/fixed-face cases pass, together
with default pose/count parity and partial/null evidence rejection. Other stages
must still be reviewed for independent capacitor movement or slot exchange;
this change alone does not guarantee final near-pin placement.

Removed redundant occupancy-grid copies from compact shape seating. The public
resizing adapters retain their copies; the internal synchronous read-only path
borrows the grid already constructed with the current board dimensions. A shared
internal declaration prevents signature drift. Isolated paired profiling on
base `4df6db6e` removed 11,619 copies / 1,423,407 rectangle-record copies while
retaining identical PCB bytes, receipts, candidate outcomes and fallback sequence.
This is operation-count evidence, not a latency claim under concurrent workload.
The 2.961 billion cell-index operations and 139-versus-18 reseat failure remain;
the newer owned-alternative workload has not yet been profiled end to end.

Nine integrated CTests passed after rebuilding affected consumers: owned adapter,
adapter compiler census, owned breathing, through-hole/rounding breathing,
borrowed-grid differential contracts, retry receipts, frozen default placement,
policy closure and placement precision census. No full compact build acceptance,
rendered-board improvement, new hardware limit or routing completion is claimed.

## 2026-10-03 — compact placement clearance and owned-group foundations

Follow-up: the committed foundation at `8509df14` passed a complete default
carrier build with `--no-render`: 37 sheets, all mandatory gates PASS, zero
non-unrouted DRC errors, zero starved fanout subjects, fallback ratchet PASS,
and the expanded 67-file source audit PASS. Its separate validation receipt is
`native/benchmarks/2026-10-03-placement-foundation-validation.json`. Existing
advisory return-path/golden/coverage findings remain, and images were skipped.
Measured scopes under concurrent work are not a controlled speed comparison.

Traced the compact USB JTAG regression to `refit_facing`, not breathing: rotating
power moves D20001 near U28002, changing its gap from 2.9263347 to 1.8700 mm
against a 2.0 mm requirement. Compact refits now compare each subject using the
unchanged final fanout checker on actual emitted/rounded coordinates. A repaired
subject cannot compensate for newly starving another. Failed trials preserve
all incumbent poses and actual work counts. Four integrated CTests pass (fanout
policy/projection, existing facing tests, frozen placement and compiler precision
census), and the archived candidate replay passes on the combined breathe fixes.
Rejecting this turn leaves the candidate's power-facing requirement unresolved;
the candidate is still rejected until a compatible seat/shape is found.

Continued the existing optimisation goal (autonomous, per full-autonomy
directive). The accepted default remains unchanged; these compact-mode fixes
are not a new whole-board acceptance or a board-area improvement.

Through-hole reservations now occupy the opposite face symmetrically, including
bottom-mounted parts. Moving groups remove and restore both reservations with
counted ownership. Dispersion rejection restores the entire compact breathing
pass: restoring only one sheet could place it into space another sheet had
legitimately entered. Real Placer tests cover both directions, fixed/moving THT,
vacated/new shadows, mixed-side groups, rejection and atomic rollback.

An additional reproduced defect showed a legal 0.500001 mm internal gap becoming
0.499960 mm after final per-member rounding. Compact commits now stage the actual
rounded poses and recheck occupancy, fanout protection, leash and internal
same-face/THT separation before accepting any member. Rejected commits retain
all actual-work counts. Opposite-face SMD pairs do not gain a false coupling.
Frozen default placement still matches its independent reference exactly.

Integrated a bounded, explicitly owned capacitor-group constructor and its unit
and live-footprint contracts. It preserves owners, fixed members, output bulk,
existing sides/rotations and nets; only explicitly permitted bypass capacitors
move. Final geometry, not translated cached boxes, determines acceptance and
reported pad gaps. Six live pilot declarations yield three local alternatives;
mechanical and fanout nonregression checks pass in the original board context.
The local extents do not shrink. This constructor is not yet selected by the
production zone search, and qualitative proximity/access remain UNVERIFIED.

Added the constructor to both independently declared source-audit manifests;
the policy contract first exposed the missing second entry and then passed.
Compiler census confirms no unregistered precision or policy storage in the
new constructor. Six focused CTests passed (clearance, occupancy, constructor,
live pilots, frozen placement and precision census); policy and strengthened
rounding regressions are separately checked. Full board gates/renders must be
rerun on the integrated search changes before replacing the incumbent.

## 2026-10-01 — calculation and model-identity corrections

Found and reproduced inherited SPICE validation false passes (autonomous, per
full-autonomy directive): non-finite numbers could satisfy comparisons; a zero
analytic prediction accepted a 99 V simulator result; nonzero process exits or
missing measurements could leave apparently successful analytic checks. The new
regression failed against the prior implementation before correction.

The gate now rejects non-finite values/limits and reversed intervals, enforces
agreement at zero, requires successful simulator execution and exactly one valid
node-voltage row, and retains simulator precision rather than rounding it before
validation. Missing, ambiguous, malformed, overflowed and substring-only readings
are rejected. Frozen fixtures remain unchanged: the one historical zero-vs-99 V
false pass is explicitly rejected, and live simulator comparisons distinguish
old four-decimal presentation from the full-precision validation result.
Fifty frozen cases, nine tolerance vectors and seven live ngspice cases pass.
Live carrier/devkit SPICE gates pass 17/11 checks with 7/5 simulated dividers.
This is focused calculation validation, not a new complete board/render acceptance.

Also corrected board_aux.cir's stale C3/C4/C5 identities to match the live C++
factory: C3 is 10u AUX bulk, C4 is 100n VREF1 bypass and C5 is 100n VREF2 bypass.
The eleven-resistor/capacitor identity test first rejected the old model at C3,
then passed the correction and ownership mutations. Its independent aggregate
comparison confirms the passive network is electrically unchanged by relabeling.
The board's analytic gate uses live C++ circuits, not this passive reference deck;
the identity test does not claim full active-device simulation coverage.

## 2026-10-01 — two-sided placement sprint started

Owner requested execution on `codex/two-sided-layout`, explicitly including
placement/orientation algorithms and excluding routing. Autonomous decision:
introduce `--compact-placement` as a controlled board/pcb-stage experiment,
retaining the verified default solver as the comparison. New search work must
pass independent emitted-board gates before any smaller result is accepted.
The first candidate-retention/face-area-bound experiment constructed all 569
carrier footprints in 18.68 s at the unchanged 168 x 163 mm outline; this is
construction evidence only, not a size improvement or complete board verdict.
Orientation, hardware requirements and independent verification are separate
workstreams. No electrical requirements or mechanical gates are relaxed.

Integrated opt-in rigid group turns and independently observed retry contracts
(autonomous, per full-autonomy directive). Existing shape indices and default
geometry remain intact. The carrier gains 22 legal orientation alternatives;
connector-locked/external-direction groups remain excluded. Four integrated
CTest contracts pass: orientation/chirality, bounded retry/rollback accounting,
frozen placement precision, and frozen floorplan. Removing the unused per-face
shortlist from all-shape mode avoids redundant member-vector copies; focused
retention/rejection contracts pass. The combined construction experiment still
produces 569 footprints on 168 x 163 mm. These are not whole-board acceptance or
performance-improvement claims; full independent gates and rendered review are
still required before publishing a replacement layout.

Integration correction: the early `pcb-stage --compact-placement` runs above
accepted but did not forward the flag. Their 168 x 163 mm outputs and timings
are default-construction observations, NOT compact-algorithm experiments.
Forwarding is now corrected. The actual compact full pipeline constructs
169 x 162 mm but FAILS acceptance: power_som facing, fanout, and reseat fallback
ratchet regress. Sandboxed KiCad DRC crashed; an unsandboxed rerun completed and
identified seven malformed-courtyard errors on U3002. This candidate is rejected;
the 168 x 163 mm accepted baseline remains the incumbent. Source/ledger checks
completed; this run deliberately omitted final image rendering.
Independent exception injection also exposed partially retained layout/offers
after a throw. Compact attempts now restore entry state while preserving exact
failed-prefix accounting and the original exception, without retrying it.

The corrected standalone CLI now emits the same PCB SHA-256 as the full compact
pipeline (`8cfe52cd653ad3faf6f4646d09d341e17f5e1d3ebd05c221f084374bd416544f`).
Subsequent eligibility corrections distinguish the exact stock probe pad from
mating connectors and deduplicate absent/zero effective rotations without
rewriting incumbents. Orientation and frozen-regression tests pass. The broader
105-orientation candidate constructs 168 x 163 mm in 108.00 s (construction-only,
concurrent engineering workload, not a controlled performance comparison); its
PCB differs from baseline and has not passed full acceptance. More alternatives
alone have not improved area or speed, so profiling and constraint-aware search
remain required.

Added explicit supply-pin/capacitor ownership and top-switch requirements for
board_aux/bringup_rails, with an integrated mandatory pipeline hook and
missing-gate closure. Focused checker, real-hook synthetic integration and
aggregation closure tests pass. Qualitative proximity and access envelopes
remain UNVERIFIED in a separate report, never new movement permissions.
Whole-board no-render validation of this hook passed for carrier (37 sheets)
and devkit (12 sheets). Measured pipeline scopes were 272.38 s and 271.38 s,
including source audit 203.52 s and 235.01 s respectively; these are not process
wall timings or controlled benchmark comparisons. Existing advisory return-path,
golden and coverage findings remain. Hard ownership checks are not a proximity
approval: bringup U1.24 to C1.1 measures 39.76 mm on opposite faces; the five
board_aux owned pad gaps range from 4.13 to 15.74 mm.

Integrated narrowly tested corrections (autonomous, per full-autonomy directive):
reject ambiguous physical catalog pin numbers; omit exactly zero-length imported
courtyard edges; resolve the compact refit's virtual @som target and preserve
the asymmetric courtyard reservation during its turn. Independent KiCad tests
of the courtyard correction cover eight face/quarter-turn combinations. A matched
copy of the rejected candidate changes from seven malformed-courtyard errors to
zero, with all other violations and 499 unconnected items identical. This does
not resolve its other placement failures or make it an accepted candidate.

Added a reproducible construction-only profiler. Two prepared-input runs measured
baseline model construction at 15.90/15.63 s and compact at 111.41/110.75 s, both
168 x 163 mm. Occupancy cell-index calls rose from approximately 470 million to
2.961 billion; search optimisation is necessary, not an optional polish.
Added counted occupancy in the compact spacing pass: removing a group's raster
halo must retain overlapping keepouts and other component reservations. The
legacy assignment API/default placement remains available for baseline comparison.
Focused overlap/multiplicity/atomic-removal tests accompany this change; combined
validation and complete compact acceptance are still pending. An early whole
CTest run was deliberately interrupted for integration after six successful tests;
it is not recorded as a complete suite pass.

Committed/pushed hard requirement integration as `558f99c6` and the courtyard
repair as `529c196a`. Parent correction tests passed 6/6, requirement pipeline
and closure tests 2/2, importer tests 2/2, and changed packing/placement source
contracts 2/2. Counted-grid copy isolation and observed quantizer accounting also
pass. Fresh combined compact reports now show zero non-unrouted DRC errors and
placement-flow PASS at 168 x 163 mm. The candidate remains rejected: U28002 has
1.870 mm foreign-part gap against a 2 mm requirement, and interior_reseat_retry
fires 139 times against the existing ceiling of 18. The complete no-render run
finished with BOARD FAIL for these fanout/aggregate-geometry/fallback gates;
source/ledger and quantization census pass. Its measured scope was 364.78 s,
including 202.66 s source audit (not process wall or a controlled benchmark).
The four search/retry/orientation/frozen-floorplan contracts also pass after
integration. Experimental opt-in code is retained as an explicitly unaccepted
search workbench, not a promoted default or an area/performance improvement.

Retired three staged-only migration worker leftovers after matching their
documented provenance: verification-audit Python sample JSONs and the private
component-basis shell runner. They were not part of the merged migration.
Exact backups remain in `/private/tmp/schgen-sprint-retired.YTkF4n`; the two JSON
hashes match `verification_audits_INTEGRATION.md`. Native component-basis,
copper-debt, policy-audit and Python-free-tree tests pass after removal (4/4).

## 2026-10-01 — clean C++ migration acceptance

Completed isolated fresh Release compilation and sequential full-render board
acceptance at `29d43472`, without bypassing mandatory gates or blessing golden
drift. Compilation took 132.17 s (two workers, no compiler/object cache, existing
zlib-ng dependency). Carrier passed all mandatory gates in 326.69 s and devkit
in 275.11 s; source/ledger audits both pass with 155 registered transforms.
All 226 tests have successful final coverage as detailed below. No tracked
Python source remains. Required hardware formats and historical reference data
are retained. See the new migration-acceptance benchmark receipt; the older
failed-build receipt is preserved without relabeling its results.

Against the requested Python revision `0e9bbc913bab77f9cd228940db2a332d25d6bfa1`,
carrier wall time decreases 56.87%; devkit increases 255.95%. These are complete
revision workloads, not isolated language speedups: the Python devkit fails its
design gates and native runs stronger mandatory source audits. Native auditing
alone takes 218.84/206.34 s. No claim is made that the queue change reduced
whole-board wall time. Both boards retain advisory return-path, golden-render
drift and contract-coverage findings, plus 499/413 unrouted connections. They
are not fabrication-ready. Generated evidence is preserved in the managed
`migration-acceptance` worktree; private raw logs are not published.

## 2026-10-01 — complete rendered baseline comparison

Integrated the remaining Plain18/Grid6 precision boundaries (autonomous, per
full-autonomy directive). Combined source proof closes all original 14/34/16
reported sites, checks 155 registrations and rejects all 33 missing-registration
mutations. Independent board output remains byte-identical to its immutable
3,450,788-byte reference. The private combined batch passed 28 contracts; parent
all-target compilation also passed. An older projection test now initializes the
new line index while retaining explicit frozen-visitor compatibility. Two exact
partitioner identities were updated for their new accounting parameter, without
changing authoring roles or weakening closure checks. Compose ledger measurement
can now expose invocation-owned counts for its three final-model measurement
calls, including initial/rebuilt driver measurements; this is not an assertion
that those counts include candidate planning or the entire CLI.

Parent full validation ran all 226 CTests, including ten live-KiCad tests:
222 passed, four failed (1019.07 seconds, two workers). The failures were traced
to three older accounting harnesses and a hardcoded scaffold build-cache path.
Corrections preserve complete map/output comparisons: assert two ledger calls
then one per-net call; replay the actual final escape stage; apply only the
independently proven two-entry correction to complete legalization plan/aggregate
fixture views; pass the owning build cache explicitly. All four corrected tests
then passed in 49.76 seconds with no production-engine changes between runs.
Thus all 226 tests have successful final coverage, not one claimed 226/226 run.
Existing reference files remain unchanged. Three documented XML fixtures omitted
by the blanket ignore rule are now included unchanged; their README distinguishes
current packaging fingerprints from unavailable historical capture hashes.
Complete rendered board acceptance and new timings remain the next gate.

Integrated invocation-owned schematic and failed-model accounting (autonomous,
per full-autonomy directive). Schematic retries and shared geometry helpers now
record actual grid calls; independent traces and complete schematic bytes match
for all 49 sheets (3,442 sheet-placement entries, not the whole-board total).
Model failures retain executed prefixes through stage, floorplan and placement
ownership boundaries. Independent review found and corrected constructor-seed
loss and partial publication after merge overflow; unavailable receipts now
propagate explicitly instead of appearing complete. Parent failure, schematic
and board-pipeline contracts passed 3/3 in 58.17 seconds. No reference fixtures
were regenerated. Project-aware title blocks correct devkit branding while
preserving carrier output; the private title/render proof covers all 12 devkit
sheets and two carrier sheets. Broader combined acceptance remains pending.
Current build/import/scaffold documentation now uses implemented native commands;
historical examples are distinguished from current instructions.

Optimized cold source auditing (autonomous, per full-autonomy directive): a
bounded dynamic queue replaces fixed worker batches, and each source file's
newline offsets are indexed once. All manifest entries are still scanned;
census publication and error selection retain manifest order, with workers
joined before return. There is no cache, skipped validation or changed detector.
An immutable copy of the prior auditor provides independent exact serial and
parallel comparisons, including malformed input, timeouts, source mutations,
line boundaries and a scheduling regression that rejects the old batch barrier.
The integrated queue proof passed (13.96 seconds), followed by the existing
parallel/auditor contracts (2/2, 29.13 seconds). Full-board speedup is not yet
measured; these tests do not establish whole-board migration acceptance.

After the pinned benchmark, corrected two accounting defects (autonomous,
per full-autonomy directive): `ledger_initial` now records its two actual
via-cost scalar executions, and packing executes the registered tolerance
function rather than counting an event while passing a copied literal.
Independent function-entry instrumentation verifies both, including counter
overflow and retained prefixes. Five integrated accounting/floorplan/packing/
geometry/output tests passed in 78.71 seconds. Historical fixture files are
unchanged; full-output comparisons adjust only the independently verified
two-entry receipt correction and reject missing/typo entries. This is not
closure of the remaining source-policy findings or full-board acceptance.
The same bounded receipt correction was then applied to the older placement,
stage, precision-accounting, connector and floorplan comparison harnesses;
all five passed (95.21 seconds), with every historical data file preserved.

Integrated Search9 (autonomous, per full-autonomy directive): nine genuine
scalar boundaries close the fourteen fallback-via/seat-band source findings,
with checked narrowing, allocation products, inclusive endpoints and recursion
depth. Invocation receipts include rejected trials and recursive work. The
private exact-base integration passed 25 tests, including source mutations,
UBSan and frozen compatibility. Parent full two-board output/negative contracts
passed in 18.91 seconds with the separate two-entry ledger correction retained.
The three newly imported independent fixture hashes match their original proof
artifacts; no existing fixture was changed. Registry cardinality is now 131.
Fifty other reported sites remain assigned to the next two integration batches;
this is not a claim of combined whole-board acceptance.

Measured pinned C++ `1ad3a40a85e98d481e22f00bdeacac86582c4356` against the
owner's sole Python baseline `0e9bbc913bab77f9cd228940db2a332d25d6bfa1`,
in isolated source checkouts (autonomous, per full-autonomy directive).
All four commands ran sequentially with full renders and mandatory checks;
agent builds/tests were paused. C++ carrier/devkit took 323.79/273.73 seconds;
Python carrier/devkit took 757.53/77.29 seconds. Changes are -57.26%/+254.16%,
respectively. Fresh Release CLI compilation was 115.80 seconds separately,
with two jobs and an existing zlib-ng dependency, not included per board.

These are revision/workload comparisons, not same-input language speedups.
Python carrier passed; Python devkit retained its test-point/design failures.
Both C++ commands completed their renders but failed quantize_census/ledger:
the same 64 unregistered sites, with 122 registered transforms. Their source
audits took 215.354667/217.499183 seconds. No checks were bypassed or goldens
blessed. All 65 expected PNGs per implementation were freshly regenerated;
49 native schematic pages were visually inspected at whole-page scale.
Native DRC reported zero non-unrouted errors, but 499/413 unrouted connections
remain; this is not fabrication-ready PCB approval. Devkit title-block
branding was flagged for correction, not silently accepted.

Full provenance, raw-log hashes, paths and limitations are recorded in
`native/benchmarks/2026-10-01-full-render.json`. Later migration fixes are not
represented by this pinned benchmark.

## 2026-09-27 — rendered verification and truthful DRC process diagnostics

Applied improvements (autonomous, per full-autonomy directive): the 39 output,
pack and geometry scalar counter keys now reuse immutable strings inside the
counted branch. Private warmed-call measurement fell from 37,000 allocations
to zero while exact results and observed receipts matched; this is not a board
wall-time speedup claim. Integrated CLI/target builds and nine runtime/source
contracts passed (122.18 seconds).

Schematic generation now wraps long worksheet titles without altering circuit
intent and separates wrapped capacitor buses from preceding ground artwork.
Original historical fixtures remain unchanged; three named corrected states
are checked in full against independent rigid-row/contact invariants and
mutation rejection. Eleven integrated schematic tests passed (8.80 seconds),
including actual title rendering. Fresh shared-executable carrier builds for
bringup_en_modules, fmc and mechanical passed connectivity, netlist, ERC and
visual gates; their PNGs were inspected. Private nine-sheet proof is additional
coverage, not whole-board acceptance. No golden-render baselines were blessed.

Output/packing/geometry integration (autonomous, per full-autonomy directive):
39 additional exact scalar boundaries and invocation-owned receipts advance
the registry from 83 to 122. Emission, publication, ratsnest, packing and geometry
consumers preserve independently captured output/board fixtures and old counts;
new actual-entry observers verify the additional work, including failure prefixes.
No broad source exemption or unknown-counter filtering is introduced. Four new
reference files are copied verbatim from independently captured pre-change runs.

Review also corrected valid fractional integer endpoints in SVG narrowing and
prevented an import failure from being retried and masking its original error.
The full integrated build exposed four old test calls missing the explicit
geometry accounting sink; those now pass a local sink without changing assertions.
The rebuilt combined implementation passed all 25 selected runtime, source-audit,
registry, pipeline and numeric checks (412.44 seconds, serial). An earlier
108-operation integration separately passed 18 runtime checks (226.78 seconds).
These are bounded integration proofs, not a claim that every remaining live
board audit finding or reported visual/manufacturing defect is closed.

Exact numeric kernel correction (autonomous, per full-autonomy directive):
binary64 significands are decoded exactly rather than recovered with floating
rounding/conversion, and the tiny-input norm uses a restoring integer square
root. This removes internal audit findings through exact arithmetic, not new
registry exemptions. Decimal ties-to-even, supported digit range/cap, errors,
signed zero, nonfinite behavior and existing corrected norm values are retained.
Private proof passed 4.5 million rounding parity cases, 250,000 norm parity
cases, independent MPFR oracles and sanitizers. The integrated CLI build plus
numeric, occupancy-precision, placement-search and full placement contracts all
pass (four tests, 53.18 seconds). Whole-board/source-manifest acceptance remains
pending; the earlier rendered images are still explicitly from 372f9563.

Autonomous, per full-autonomy directive: rendered both boards from 372f9563
without overwriting tracked generated artifacts. Carrier took 321.72 seconds
and devkit 273.85 seconds, with rendering enabled; these are not comparable to
the earlier no-render timing rows. Both full runs failed source accounting and
ledger acceptance, plus a sandbox-only KiCad DRC crash. All 49 sheets passed
automated netlist/ERC/visual checks and all sixteen 3D views were produced.
Manual image inspection nevertheless found title-block overflow and a visual
supply-bus/ground-symbol contact; these remain open, not blessed golden changes.

The same independent KiCad checks outside the sandbox returned zero
non-unrouted errors for both boards, but carrier has 197 warnings and 499
unrouted connections; devkit has 59 warnings and 413 unrouted connections.
These are layout starting points, not fabrication-ready routed boards.

DRC report loading now checks the child exit status before opening its output,
preserving crash status/stdout/stderr instead of hiding them behind a missing
report error. Pipeline and standalone CLI use the same loader. Regression
contracts cover failed children, absent/malformed reports, successful reads and
stale reports after failure. Native build and DRC contracts pass; both actual
generated boards were checked through the rebuilt CLI outside the sandbox.
No DRC severity, acceptance predicate, or source-audit requirement was weakened.

## 2026-09-26 — tracked Python retirement (acceptance in progress)

Placement and allocation batch (autonomous, per full-autonomy directive):
nineteen placement scalar boundaries now have explicit invocation-owned
accounting and exact registry entries (64 -> 83). Original geometry, legacy
counts and output fixtures are retained; rejected eviction and duplicate shape
work is independently counted. Scalar keys reuse immutable strings rather than
allocating a temporary string on every recorded call. The full shared build,
fourteen placement/compatibility contracts and two real-source audit contracts
pass on the integrated snapshot. This is not whole-board acceptance.

Occupancy now reuses one empty failed-bucket vector's capacity per search,
without retaining coordinates/results or changing traversal, sorting or checks.
Private allocation instrumentation measured carrier calls to allocation falling
from 32,422,620 to 8,295,528 (74.41% fewer); four variant outputs and ordered
traversal remain identical. Current integrated occupancy and full placement
contracts also pass. This allocation result is not a measured runtime speedup.

Owner baseline correction: the sole performance comparison baseline is now
`0e9bbc913bab77f9cd228940db2a332d25d6bfa1`. Previous `4bd47c33` measurements
are historical observations only, not the requested comparison. The exact
baseline is run unchanged in a separate managed worktree, without later native
extensions or copied design inputs. See native/benchmarks/BASELINE.md.

Combined integration (autonomous, per full-autonomy directive): seven legalizer and seventeen PCB
stage scalar boundaries now retain their actual invocation accounting, including
rejected trials, with immutable prior geometry/output evidence. Eleven supplied
buried-constant findings are addressed by nine real policy owners and removal
of two unused aggregate defaults; existing physical values are retained. The
source registry contains 64 exact scalar declarations. Numerical corrections
remove undefined outline narrowing and fix subnormal norm double-rounding and
finite-overflow facing angles. The integrated numeric tests, sanitizers and
MPFR oracle pass; the first combined production build and seven focused
math/policy tests passed. The final combined build and eleven serial contracts
now pass, including full authoring closure/census, C++ auditor, board policy,
independently observed legalizer/stage/occupancy counters, pipeline timing and
Python-free tree. Wider placement/floorplan/producer/migration/numeric checks
also passed. An initial census correctly rejected a concurrent source edit;
two compiler subprocesses timed out under concurrent load. All three checks
passed on the final frozen source with serial execution and unchanged limits.
Whole-board acceptance remains outstanding.
No whole-migration acceptance or runtime speedup is inferred from those checks.

Frontier accounting optimization (autonomous): bind the actual map node lazily
within one place_near invocation, retaining one real scalar function and exact
overflow/error/counter semantics. This removes repeated map lookups from the
carrier's 142,413,444 frontier operations without changing candidate traversal.
Four private placement variants retain byte-exact output and prior accounting;
the integrated occupancy contracts pass. Seven legalizer and seventeen stage
counter keys use immutable strings; stage vectors reserve known capacities.
No isolated speedup is claimed for these changes yet.

Timing reliability (autonomous): exclusive nested scopes now separate actual
source/authoring audits from generation and mixed validation stages. Timers
cannot be copied/moved; early closure or destruction of a parent safely unlinks
it without interrupting its child or resuming a dead scope. Fake-clock contracts
cover nesting, repeated closure, exceptions, disabled timing and early parent
destruction; the standalone suite passes ASan/UBSan. Full process time remains
distinct from the reported pipeline scope, which excludes final summary writes.

Allocation reduction (autonomous, per full-autonomy directive): retain three
immutable occupancy counter key strings instead of allocating them per call;
counts remain invocation-owned with unchanged overflow behavior. The AST parser
stores the first eight decoded duplicate-check keys inline and spills wider
objects without dropping checks or fields. Private exact four-board output and
counter comparisons and complete real-AST projection/census comparisons pass.
Private profiling removed 142,503,424 carrier allocations and 56.52% of parser
allocations; wall observations were shared-machine, not isolated speed claims.
The integrated full build and five focused CTests passed (33.42 s), covering
placement, occupancy accounting, parser validation, census and parallel audits.
The devkit Python baseline completed at 20.78 s (PASS, 12 sheets), versus the
earlier C++ 395.91 s source-audit-failing baseline. Both-board comparisons now
have measured Python observations, not approximate README estimates. The C++
baseline predates current optimization work; no end-to-end speed-up is claimed.

Bounded audit parallelism (autonomous): the source audit now defaults to two
independent translation-unit workers, with an explicit supported range of one
to four. It validates the manifest first, preserves manifest ordering and all
duplicate census tuples, and propagates compiler/parser/timeout failures without
returning a partial census. Futures are joined before captured inputs expire.
The full 57-file ordered census matched the frozen pre-change serial scanner
byte-for-byte. Observed wall time was 417.81 s serial versus 330.50 s parallel;
other agent work was active, so this is not an isolated performance benchmark.
Four integrated audit/policy tests passed (37.70 s), including macro ordering,
partial final batches, error precedence and worker timeout. No detector, source
scope, policy cover, required gate or cache validity rule was relaxed.

Occupancy precision accounting (autonomous): six actual scalar operations now
own component/reach precision, frontier/shape ranking and bucket/axis narrowing.
Invocation-owned counters flow explicitly through copies, rejected searches,
refinement and every floorplan packing trial; geometry stores no accounting
sink. The registry now has 40 operations, and the reviewed source manifest adds
the real implementation file. Invalid cell conversion precedes single-rectangle
mutation; inclusive bucket loops use wide counters to avoid INT_MAX overflow.
Ten focused CTests passed (383.79 s), including independent function-entry counts
on carrier, devkit, single-side and fixed-outline paths, immutable prior output
and counter fixtures, source audits, replay and ownership checks. Historical
fixture files were not regenerated. This is not whole-board gate closure: the
remaining source-policy findings and full native acceptance are still pending.
Clang's test-only post-inlining instrumentation reduced the same independent
occupancy proof from 284.41 s to 23.96 s; all assertions passed again. External
operation calls remain in separate translation units. This measures test
instrumentation overhead, not a production board-generation speed-up.

Silk spatial-index correction (autonomous): reject nonfinite/nonpositive cell
sizes and unordered/nonfinite/out-of-range boxes before insertion. Check the
floating-to-integer cell conversion, use wide inclusive loop counters at
INT_MAX, and remove the unused member default (the explicit constructor always
owns the supplied cell size). The original implementation fails the new NaN
constructor regression. Private strict and ASan/UBSan/float-cast-overflow runs
pass the new boundary tests and all 181 unchanged silk-oracle fields. Sanitizer
coverage here is the changed pack translation unit plus test, not every core
archive object. Fresh devkit timing observations, including the still-failing
mandatory source audits, are recorded in `native/benchmarks/2026-09-26-cutover.json`.
Integrated verification: all five focused CTests passed (29.15 s): pack silk,
live board, PCB placement, placement gates and PCB emission. The matched carrier
run also passed its sheet, electrical and geometry gates; quantization/ledger
audits still failed. This fix is not full migration acceptance.

Native acceptance update: all 184 existing CTests passed after Python retirement
(587.00 s), including live KiCad, source closure and complete source census.
The added Python-free-tree CTest passed separately and its hidden-source
negative fixture failed as intended. Public package gate/result defaults now
select native assets, with explicit legacy-only fixture dispatch and new
empty/missing/default-mode regressions. Six actual floorplan rounding operations
now carry invocation-owned accounting; independent function-entry observation
verifies new counts while preserving all 83 policy rows, complete plan/ledger
bytes and prior counters. Seven affected integration tests passed. This does
not waive the still-open complete board source-policy audit.

Autonomous, per full-autonomy directive: removed all 393 inventoried tracked
Python files after validating each original SHA-256 and accepting the remaining
native SI-unit, downstream-I2C, repeated-build/thermal and committed-render
regression replacements. Removed Python requirements, pytest/lint configuration
and pre-commit Python hooks. Hardware assets and independent fixtures remain.
Deleted tracked content is recoverable from Git. The complete native suite is
being rerun against the retired tree; this is not full-board acceptance or a
claim of complete migration. The unused ignored virtual environment, compiled
Python extension and two sync-copy tests were moved recoverably outside the
repository to `/private/tmp/zynq-retired-python.iyilwa`; the subsequent tree scan
found no `.py` files (including ignored/hidden files, excluding Git internals).
Fixed pipeline exception classification: a child gate verdict is not proof
that its parent stage completed. Both ordinary and live pipeline tests pass.
Follow-up cleanup deleted generated Python bytecode directories, pytest/Ruff
caches, the unused Python-enabled Make/CMake build metadata and nanobind archive.
These ignored caches are not recoverable from Git; they contained no source
of truth. Active `native/build/fast`, compiler cache and native dependencies
were retained. A C++ working-tree test now rejects reintroduced Python source,
bytecode and retired dependency configuration, including hidden/ignored paths.
The root README now documents native commands rather than retired Python entry
points; historical independent parity fixtures remain as regression evidence.

This is the **archive** of the hand-written planning / decision / run logs that
drove the carrier rebuild. The content below is preserved verbatim under dated
section headers; it is no longer the living source of truth, but it is the
durable record of *why* the design is the way it is.

For the **current** state, read instead:

- [`carrier/README.md`](README.md) — the carrier's architecture, the
  subsystem/adapter pattern, the dossier index, the build/gate process.
- [root `README.md`](../README.md) — the three layers + how to generate.
- [`schgen/DESIGN.md`](../schgen/DESIGN.md) — the engine architecture contract.
- [`carrier/subsystems/README.md`](subsystems/README.md) — authoring an adapter.
- [`subsystems/README.md`](../subsystems/README.md) — the reusable library index.
- [`WORKING_GUIDELINES.txt`](../WORKING_GUIDELINES.txt) — the living
  human-readable rules/process contract (kept in place, not archived).

The still-true distillation of the locked design decisions and process
discipline has been folded into the READMEs above; everything below is the
full original log for audit.

---

# 2026-09-26 — Native CLI cutover and strict local regression

Implementation decisions (autonomous, per full-autonomy directive):

- Expose existing composition, drawing and escape constants through their
  actual shared C++ storage and additive ledger provenance, preserving literal
  values and output. Correct the compiler auditor's numeric JSON character-zero
  handling; nonzero and immutable character policies remain audited.
- Retire the unused Python extension source, 27 binding headers and two
  binding-only compile probes after native replacement contracts. Remove the
  CMake Python/nanobind discovery/download path; the old option now rejects ON
  explicitly. Preserve Git history and independent reference fixtures.
- Retire the obsolete staged Python-source audit parser and its build/test
  helper only after reference inspection, retaining a recoverable external
  backup of all five files. Preserve native integer/fallback/ledger-state code
  and immutable fixtures. Move the uncompiled, ignored old `circuit 2.cpp`
  sync copy outside the source tree with its SHA-256 verified; do not hide it
  from the compiler census through an exemption.
- Retire the five tracked Python experiment scripts only after native contracts
  and actual CLI checks. W12 probes use fresh native authoring and real KiCad
  extraction in private scratch; native dump publication reproduces all 49
  carrier/devkit circuit files without content changes. The local sync duplicate
  was byte-identical and backed up outside the repository before removal.
- Native `check` runs complete board generation, mutation/determinism selftest,
  and every configured CTest. Require nonempty enabled/built inventories and
  matching JUnit results, rejecting skips and fabricated PASS text. Retain logs
  and propagate failures/timeouts. Independent driver tests are not substitutes
  for final full-board acceptance.
- Add native authored-document validation with independent mutation fixtures,
  and a real KiCad RC smoke test that distinguishes open/short faults from an
  ERC-only undriven fault. Keep the source-audit and Python-removal goal open
  until the clean native path passes all required checks.
- Keep all checks local under the standing no-hosted-CI directive. Discard an
  uncommitted agent-proposed manual GitHub workflow; retain only the local
  native build/preflight wrapper. No hosted workflow was installed or run.
- The owner's current instructions supersede the old Python-only design-source
  convention and three-agent ceiling: tooling and tests migrate to C++, required
  hardware formats remain, and at most five agents work concurrently. Verified
  commits stay on the existing `perf-native` branch; no history rewrite.

---

# 2026-09-18 — Native schematic stages and devkit electrical corrections

Implementation decisions (autonomous, per full-autonomy directive):

- Migrate complete symbol-loading, routing, schematic-emission and visual-gate
  stages into the independently buildable C++ core, retaining only temporary
  interpreter transport for the not-yet-migrated board orchestration. Frozen
  data fixtures, mutation tests and real KiCad extraction remain the proof;
  replacing a Python reference with an alias to C++ is not a parity test.
- Preserve symbol-library snapshots through copy/deepcopy, including independent
  mutable adapter metadata. File changes must not silently alter an existing
  library. Preserve expression grouping where floating-point rounding affects
  pin positions and generated bytes.
- Add the devkit's absent STM32 I2C2 pull-ups to always-on +3V3_SC on debug_boot
  (two 4.7k 0603 C23162 parts, 1.5 mA budget). Add nine physical probe pads on
  debug_boot, power_mon and power; retain existing waivers unchanged. SDIO probe
  ports retain the SoM's 1.8 V domain. Verify I2C rise time during hardware bring-up.
- Probe-only ports require hierarchical labels: a locally correct sheet is not
  proof of a connected board. Add an actual two-sheet KiCad regression. Probe
  pads are observers, not regulator stages. Connector-sheet auxiliaries belong
  in the normal PCB packing path, while DF40 geometry remains fixed; placement
  exceptions must unwind the build ledger.
- Move complete netlist verification into C++, sharing the hardened KiCad
  process/XML boundary with SoM extraction. Preserve frozen reference reports
  first, then independently correct the legacy missing-part exemption: a part
  with any declared netted pin cannot be excused merely because another pin is
  NC. A regression reproduced the false PASS before the correction; NC-only
  components remain exempt. Index NC/netted references once instead of scanning
  every NC declaration for every part.
- Move the five design-rule checks, probe coverage and report formatting into
  C++, including standalone `design-rules` and `testpoints` commands. Index
  connectivity and resolve each unique symbol once per immutable snapshot.
  Retain finding/waiver order and byte-identical reports; use real pull-up/probe
  removal mutations to prove failures remain failures. Propagate cancellation,
  allocation and system failures instead of treating them as unresolved symbols.
  The transitional report command now writes to the selected project, not always
  to carrier. Both full board builds pass with unchanged generated artifacts.

The complete devkit build now passes all 12 sheets and board-level checks.
The complete carrier build passes all 37 sheets with the native schematic
stages; its electrical/PCB outputs are unchanged. Full C++ placement, board
orchestration and the remaining tooling/tests are still migration work, not done.

---

# 2026-06-10 .. 2026-06-13 — carrier/PLAN.md (the locked decision record)

# Carrier + toolchain plan (locked with user 2026-06-10)

## Decisions (user)
- **No CI.** Every local `schgen build` enforces ALL gates (non-zero exit on any failure).
- **Parts library**: top-level `parts/`, STRICT one folder per part — passives included
  (`parts/R_0603_10k/`, `parts/C_0603_100n_25V/`), named by MANUFACTURER PART NUMBER.
  Each folder is self-contained: `part.py` (pins, LCSC, MPN, datasheet URL, electrical
  rules), symbol, footprint, 3D model. Adding a part = adding a folder. `shared/` is
  DELETED (vague); the SoM project's lib-tables point at libs AGGREGATED from `parts/`.
- **Assets always GENERATED, no manual overrides**: `schgen part add <LCSC-id>` fetches
  EasyEDA/LCSC data and generates the folder. Footprint + 3D are converted faithfully
  (must match the physical JLC part); the SYMBOL is generated by OUR layout rules
  (on-grid pins, functional grouping) from the pin data — clean renders stay possible
  without hand-curation.
- **Bring-up architecture (replaces generic 'features')**: the board must be testable in
  stages using switches only — (1) enable power supplies rail-by-rail (DIP switches on
  regulator ENs + per-rail power-good LEDs), (2) enable user LEDs, (3) every module
  individually power-gated (load switch per module + enable switch + status LED).
  User LEDs + buttons included. RTC/QWIIC/CAN: not now.

## Phases
- **P0 (in flight)**: wave 1 subsystems → harvest, eyeball, commit, push.
- **P1**: `parts/` restructure + migration script; kill `shared/`; schgen loads symbols
  from `parts/**`; aggregated KiCad libs generated for the SoM project.
- **P2**: LCSC pipeline — `schgen part add C#####` (folder generation), `schgen preflight`
  (live stock / Basic-vs-Extended / cost rollup; fails on ghosts).
- **Wave 2** (on parts/ layout): lvds_lcd, mipi_camera, pmod, jtag_swd, boot_switches,
  user_io (LEDs+buttons), **bringup** (rail-EN DIP switches, per-module load switches
  TPS22918/SY6280-class, PG LEDs) — module rails become gated nets (+3V3_HDMI, …).
- **Wave 3**: FMC; J1/J2/J3 sheets GENERATED from carrier/som_interface.json.
- **P3**: linker + typed ports (`diff_pair`, `i2c`, `sd_bus(level=…)`) — board-level
  netlist gate, undefined-port/name-drift/level-mismatch errors, KiCad layout-constraints
  export (impedance/pair/length-match), block diagram generated from the port graph.
- **P4**: rule engine as 4th gate (cap derating vs rail, pull-up windows, regulator
  feedback math, per-rail current budgets — rules live in each part's `part.py`).
- **P5**: SPICE spot-checks (dividers, ramps) from the same netlist.

## Standing rules
Netlist-first; gates immutable; wire-heavy datasheet style; everything programmatically
generated (no hand-assembled implementations, no hand-copied pinouts); commit AND push
after every verified step.

## Decisions round 2 (user, 2026-06-10)
- **Power input**: USB-C PD ONLY, 20V/3A (60W) via FUSB302. No barrel jack.
- **Carrier rails**: +5V (buck from VIN), +3V3 (buck from +5V), +1V8 (for SD/peripherals).
  FMC VADJ = FIXED 2.5V from a local LDO inside the FMC subsystem (not a global rail).
- **Bring-up**: DIP switches + STM32 override (switch OR/AND GPIO into every regulator
  EN and module load-switch EN); per-rail PG LEDs.
- **HDMI**: BOTH TX and RX on rev A. **LCD**: generic 40-pin TTL RGB888 FFC (0.5mm) +
  touch I2C + on-carrier backlight boost. **Camera**: RPi 15-pin FFC, 2-lane MIPI CSI-2.
- **microSD**: VERIFIED 2026-06-10 against the SoM netlist: SDIO_CLK/CMD/D0..D3 run
  J1 -> Zynq U2 directly (no SoM-side translator), and the SoM README declares these
  pins 1.8V. Standard SD cards initialize at 3.3V (1.8V only after the UHS-I switch),
  so a 1.8V-only slot cannot enumerate cards. DECISION (flag resolved): the carrier
  microSD subsystem MUST include an SDIO level translator (TXS02612-class): 1.8V on
  the SoM side, 3.3V card side, powered from +3V3/+1V8.
- **Form factor**: free, connector-driven (~120x100 class expected; user owns outline).
- **Stackup**: JLCPCB 4-layer JLC04161H-7628 — constraints export uses its impedance
  geometry tables (90R USB, 100R TMDS/LVDS/MIPI diff).
- **Assembly**: prefer JLC Basic; Extended where design quality demands; preflight
  reports Extended-reel count + total cost.
- **Debug**: Zynq JTAG on Xilinx 2x7 2mm (14-pin) header; STM32 SWD on ARM 10-pin
  1.27mm. Both probe-standard.

## ARCHITECTURE CORRECTION (user-caught, 2026-06-11) — NO MANUAL PLACEMENT
VIOLATION FOUND: per-subsystem `placer()` hooks with literal coordinates (power.py 37
geometry calls, hdmi_tx.py 33, ethernet.py 18). This is manual placement and is BANNED.
THE RULE: a subsystem .py contains the NETLIST (+ optional DECLARATIVE hints, e.g.
"net X is a trunk bus" — never coordinates, never wire plans, never text positions).
ALL geometry comes from schgen/place.py deriving patterns from circuit TOPOLOGY:
- trunk-bus/ladder (N same-structure taps onto one net — Bob-Smith, rail buses)
- regulator stage (IN caps + IC + L + FB divider + OUT caps, from part roles)
- dual-IC passthrough (protection/level-shift IC between port group and connector)
- connector fan (ports from pin table — som sheets' generator folds INTO the engine)
- existing: decoupling rows, pull-up ranks, port fans, dividers
ENFORCEMENT (after migration): the build FAILS if a subsystem module defines `placer`
or touches geometry APIs — purity is a gate, not a convention.
MIGRATION: engine v2 in schgen/place.py; ALL subsystem placer()s deleted; som_conn_gen
geometry folded into the engine; every sheet re-verified (all gates + render eyeball).
STATUS (2026-06-11): DONE. Engine v2 templates: signal-flow chain (multi-IC channel
runs — hdmi_tx, hdmi_rx), trunk-bus/ladder detection (ethernet Bob-Smith, hdmi_rx
cable-5V trunk), regulator stage rows (power), connector fan (som_j1/j2/j3, folded
from som_conn_gen), divider stacks (m1_rc), plus the shared fan/attachment/cluster/
flag machinery. Subsystems import schgen.model ONLY; `c.hint(net, style)` is the sole
declarative extra. The PURITY GATE in `schgen build` AST-scans the subsystem source
BEFORE executing it and fails on `placer` (def/assign/runtime) or any geometry import.
All 10 sheets (m1_rc usb_pd uart_bridge ethernet power hdmi_tx hdmi_rx som_j1 som_j2
som_j3) all-gates PASS; `schgen link` BOARD GATE PASS; hdmi_rx builds for the first
time — from nothing but its netlist.

## Decisions round 3 (user, 2026-06-11) — UX, layout, robustness
- **Authoring v2 (user-friendly subsystems)**: library-first `use_part("FUSB302BMPX",
  ref="U1")` pulling lib_id/footprint/LCSC/pins from parts/ (inline metadata illegal for
  generated parts); pin-by-NAME `U1.SDA` validated against the part's pin table (numbers
  ok for bare-number connector pins); missing passive folder = build error printing the
  exact `schgen part add C...` fix; GENERATED net-contract module carrier/nets.py (from
  som_interface.json + gated rails) so cross-sheet port names are Python attrs, not strings.
- **Repo cleanup**: DELETE tools/ and scripts/ (git history keeps them); docs/ keeps the
  hand block diagram + the auto-generated block_diagram.svg, stale old-generator renders
  deleted; shared/ DIES: SoM 3D/footprints -> som/lib/ (lib-tables updated), generator-owned
  symbols -> schgen/lib/; m1_rc.py moves out of carrier/subsystems into schgen tests.
- **Outputs COMMITTED**: carrier/sheets/*.kicad_sch + carrier/renders/*.png tracked in git
  (deterministic regen; renders reviewable on GitHub); out/ scratch stays ignored.
- **READMEs**: compact root + per-dir (carrier/, schgen/, parts/); quickstart = 2 lines.
- **`schgen board`**: ONE command = every sheet gated + link + openable carrier.kicad_pro
  hierarchy + constraints + diagram + preflight + JLC BOM.
- **Golden render snapshots**: perceptual hash per sheet committed; drift warns,
  `--bless` accepts intentional changes.
- **Rule engine pulled FORWARD (P4 now)**: rules live in each parts/<MPN>/<MPN>.py;
  retrofit existing sheets; remaining subsystems authored under it.
- **Declined**: parts.lock snapshot (preflight on demand only).

## Documentation spec (user, 2026-06-11) — three-level READMEs
1. **parts/README.md** — compact framework: how to add a component from LCSC
   (find C-number → `schgen part add C…` → what gets generated → verify → commit).
2. **carrier/subsystems/README.md** — the equivalent for subsystems: how to compose
   a subsystem FROM parts (use_part + named pins + ports/nets contract + hints),
   build it, read the gates, review the render. Written by the authoring-v2 agent
   AGAINST the new API (not the current one).
3. **Root README.md** — high level only: what the repo is, the three layers
   (parts → subsystems → board), and how to generate the schematics/projects
   (`schgen build <name>`, `schgen board`). Compact; defers detail to the layer READMEs.

## Output taxonomy (user, 2026-06-11) — carrier/out/ DIES, mirror som/
```
carrier/
  Zynq_Carrier.kicad_pro   # generated KiCad project — double-click to open (like som/Zynq_SoM.kicad_pro)
  Zynq_Carrier.kicad_sch   # generated root sheet
  schematic/               # generated sub-sheets (*.kicad_sch), committed
  renders/                 # flat <name>.png per sheet, committed (GitHub-reviewable)
  reports/                 # ERC / link / gate verdicts, committed (proof travels with design)
  manufacturing/           # bom_jlc.csv, layout_constraints.*, preflight report
  subsystems/              # authored netlists (*.py) — the only hand-written layer
  som_interface.json, nets.py (generated contract), PLAN.md, README.md
```
No scratch dir; everything regenerated in place, deterministic. The authoring-v2/refactor
agent implements this (CLI output paths + .gitignore + README references).

## GAP REGISTRY (audit 2026-06-11 — decided but not yet owned)
1. **pd_input sheet MISSING**: the USB-C PD *receptacle* itself (VBUS -> +VIN path,
   CC1/CC2 wiring to the FUSB302 sheet's STM32_USB_CC1/2 ports, shield). usb_pd has
   only the FUSB302. Without it the board has no power inlet. Owner: next free agent.
2. **Passive part folders (round-1 decision)**: passives still inline c.part(...,
   LCSC=...) — round 1 says EVERY part incl. passives gets a folder. Authoring v2's
   missing-passive error implies the folders; VERIFY at M3 harvest that R/C/L folders
   actually exist and subsystems reference them, else it silently stays inline.
3. **Rule engine P4**: in M3 scope via round 3, but VERIFY at harvest it landed
   (rules in parts/<MPN>/<MPN>.py + retrofit) — not silently dropped.
4. **SC firmware contract**: BOOTSEL decode + BMODE drive + PA13/14 reserved (debug
   dossier "firmware contract") — needs a tracked note in som/ before rev-A bring-up.

## Decisions round 4 (user, 2026-06-11) — SYSTEM GENERATOR: ALL APPROVED
The netlist becomes the single source of truth for the whole SYSTEM, not just the sheets.
All emitted by `schgen board`; none add authoring burden.
- **Generated .xdc**: Vivado constraints for every carrier net through J2/J3 -> Zynq ball
  (LOC from som_interface.json, IOSTANDARD from the VCCO rail map, diff-pair constraints
  from typed ports). The PL design starts with zero pin-mapping work and CANNOT drift.
- **Generated SC-firmware header**: C header for the SoM STM32 system controller —
  pin/function map, BOOTSEL decode table, rail-sequencing order, I2C address map
  (FUSB302 + power monitor + IO expander). debug_boot dossier's "firmware contract"
  becomes code, not prose.
- **Generated bring-up manual**: ordered rail-by-rail checklist from the power tree +
  bringup netlists (close DIP n -> expect rail V at TP x, current limit, PG LED state).
  Testing doc that cannot drift from the board.
- **Power-tree budget gate**: subsystems declare draw; build proves regulator headroom
  through the gate tree; emits numbered power-tree diagram.
- **Test-point coverage rule**: every rail + key bus owns a TP or the build FAILS.
- **SPICE spot-checks pulled forward (P5 -> now)**: ngspice on auto-extracted dividers/
  RC/FB loops (incl. BOOT0 1k5/100R divider) with pass thresholds, gated.
- **`schgen selftest`**: gate mutation testing — injected pin-swaps/dropped wires/net
  aliases MUST be caught by the gates (the no-CI answer to "who watches the watchmen")
  + build-twice byte-compare determinism check.
- **README gallery**: auto-generated render thumbnails + inline block diagram; the repo
  demos itself on GitHub.
SEQUENCE: after M3 harvest + camera/FMC/pd_input sheets; selftest + .xdc first (trust +
immediate user value), then power-tree/TP/SPICE gates, then SC header + bring-up manual
+ gallery.

## Flags from subsystems-research harvest (2026-06-11)
- **DECISION NEEDED — bank 13 oversubscribed**: lcd(34 IO) + pmod(16) + user_io(8) = 58
  signals > 43 available bank-13 IOs. Agent proposal: move LCD to J3 bank 34 (untouched).
- **Camera requires +VCCO_35 = 2.5V** (XAPP894 D-PHY on HR bank) — new rail-map entry +
  LP-RX pin reservation; carrier dossier carrier/research/camera_csi.md has the lane map.
- **POWER_LIBS generalization (engine)**: fixed rail->symbol name map must accept arbitrary
  rails (+VIN_SYS, +5V_REG, gated rails). BLOCKS: power.py shunt rail split (held out of
  harvest to keep power green — power_mon cannot LINK until the split lands).
- **Stock risks for preflight**: DS1024-2x6R2 (45 units!), INA3221 C181255 (2.4k),
  RPi FFC SFW15R-1STE1LF picked over -2STE1LF (111, ghost-risk). Re-verify at BOM time.
- **RESOLVED (user, 2026-06-11): LCD -> J3 bank 34** (+VCCO_34 = 3.3V rail-map entry);
  pmod + user_io + LCD touch I2C keep bank 13. lcd.py expect targets updated.

## Flags from board-completion harvest (2026-06-11 evening)
- **RESOLVED (2026-06-11): fmc all-gates GREEN** — engine extended generically for
  160-pin connector scale (aux body-head budget + new-column overflow, EN-strap onto
  the stage in-rail, GROUND comb trunk outside connector fans = the som x_g idiom,
  rails placed after labels on connector-scale sides, pull/hang rank rows, attach-band
  probes covering passive texts). Board: 23 sheets, BOARD GATE PASS; render eyeballed
  (A3); goldens blessed. Inspected drift: power_mon shunt rank one row (A3->A4),
  bringup_rails/bringup_en_modules spacing — all clean.
- **DECISION at power-tree gate: VBUS pre-contract capacitance** — board total ~30uF
  nominal (pd_input 10u + power.py 2x10u unswitched) vs ~10uF PD sink guidance:
  inrush limiter OR trim buck input bulk.
- **Rail map for wave-3 J-sheet regen**: +VCCO_35 = +2V5_VADJ (SHARED camera/FMC 2.5V);
  FMC budgets into power-tree gate: VADJ 0.4A (TLV75725 DBV thermal), 3P3V 1A.
- **part_gen gap**: cannot traverse EasyEDA multi-unit 'subparts' symbols (ASP-134603-01
  generated via verbatim flatten + --from-json; regen online for 3D once fixed).
- **Procurement**: ASP-134603-01 stock 282/Extended/$17.75 — order early; TLV75725PDRVR
  alternate is ghost-risk (16 units). 31 BOM lines still missing LCSC ids.

## Flags from mechanical-debt harvest (2026-06-12)
- **RESOLVED (2026-06-11): use_part lib-override landed** — `use_part(mpn,
  lib_id=..., footprint=...)` keeps the deliberate drawing while sourcing
  MPN/LCSC/datasheet from parts/ (hidden MPN+Datasheet fields in the emitted
  file; pin-by-NAME disabled under override — numeric pins validated against
  the actual symbol). All 8 migrated (power TPS54302 x2/AP2112K/AO3400A;
  hdmi_tx TPD12S016+HDMI-019S; hdmi_rx HDMI_A_RX+M24C02; usb_pd FUSB302);
  renders byte-identical, goldens untouched, graph identity proven.
- **RESOLVED (2026-06-12, round-5 decision): ethernet Bob-Smith 1n caps** — all 5
  (4 ladder + the C5 chassis barrier) now 1nF/2kV X7R 1206, live-verified C9196
  (FH 1206B102K202NT, JLC Basic, stock 1.37M); alternates in ethernet.py docstring.
- **PROCUREMENT CRITICAL**: HX5008NLT C962544 stock=10 (clone C47575004 @419 noted in
  ethernet.py); DS1024-2x6R2 @45; TPD6E001RSER @216; ASP-134603-01 @282. 43 Extended
  reels, $43.30/board @qty1 (preflight_report.txt in manufacturing/).

## Decisions round 5 (user, 2026-06-12) — power-tree findings resolved
- **+5V_HDMI_TX / +5V_LCD**: ADD two SY6280 gate cells to bringup (fed from +5V,
  per-module switchable like everything else; EN cells + DIP/override + status LEDs
  per the existing pattern; power tree updated).
- **Carrier-vs-SoM rails**: ISOLATE — carrier bucks win; SoM's exported +3V3/+1V8 on
  J1 become explicit no-connects (or TP-only) on the carrier side; nets stay distinct.
- **VBUS pre-contract**: eFuse soft-start (TPS25940-class, 24V, live-verified LCSC)
  between PD receptacle and bulk on +VIN — controlled dV/dt + inlet OVP/OCP.
- **Ethernet Bob-Smith**: 1000pF 2kV 1206/1808 (live-verified) replaces 0603/50V x4.

## P0 + wave-3 decisions (AUTONOMOUS, per full-autonomy directive, 2026-06-12)
- **P0 — SoM VIN OVERVOLTAGE (netlist-proven, wave3_function_map.md)**: the SoM is a
  4.2-5V-input module (TPS7A20/MPM3834/MPM3822/TPSM82864 all 6V-class; SoM sheet says
  "4.2-5V") but the carrier nets J1.1-14 to the 20V PD rail +VIN. FIRST PD CONTRACT
  DESTROYS THE SoM. DECISION: always-on +5V_SOM buck (TPS54302, third instance) from
  +VIN -> J1 VIN pins; always-on because PD negotiation is circular (the SoM SC hosts
  nothing pre-PD here — FUSB302 is carrier-side on +3V3_SC — but the SoM must boot
  with the 5V default-USB contract too). Power tree re-rooted accordingly.
- Wave-3 binding plan ADOPTED as specified in carrier/research/wave3_function_map.md:
  GPIO1/2/3 rail-EN vetoes; GPIO4 = SC_INT_N wire-OR (TCA9535 INT# + FUSB302 INT, usb_pd
  R1 dropped); STM32_I2C2 bit-banged on DAC1/DAC2 J1.49/55 (hardware I2C proven
  impossible); USBOTG_FLT_N -> TCA9535 P12 with pull-up re-railed +3V3_SC (abs-max fix);
  PMON_ALERT_N -> P11; SD_CARD_DETECT -> bank-13 EMIO; VCCO 13/33/34=+3V3, 35=+2V5_VADJ
  (FMC mezzanine share 0.40->0.35A); EN_HDMI_TX drives both HDMI switches (no free DIP);
  PUDC_34 strap added carrier-side; powertree +3V3_SC source model corrected to TPS7A20
  300mA (gate must re-verify the always-on budget).
- **RECONCILIATION with the round-5 5V-gate landing (2026-06-12)**: the adoption above
  was written concurrently with the round-5 bringup commits and two of its assumptions
  are now stale against the committed netlists: (a) TCA9535 P12/P13 are TAKEN by
  BU_OVR_HDMI_TX_5V / BU_OVR_LCD_5V (bringup_rails round-5 extension; P11 stays
  reserved for PMON_ALERT_N) — USBOTG_FLT_N must land on the next free port (P14;
  P14..P17 currently 100k-to-GND spares). (b) "EN_HDMI_TX drives both HDMI switches
  (no free DIP)" is superseded: SW6 (DSHP04, round-5 extension DIP) provides a
  dedicated HDMI_TX_5V position, so +5V_HDMI_TX has its OWN EN_HDMI_TX_5V cell.
  The generated firmware header / BRINGUP.md are netlist-derived — the wave-3
  binding agent must read the current port map from those, not from this prose.

## Electrical-review findings (deep audit, 2026-06-12, autonomous triage)
- **PWR-1 [CRITICAL] — power.py +5V_SOM (U4) EN over-stress**: R12/R13=22k/10k from
  +VIN puts 6.25V on the TPS54302 EN at the 20V PD contract (rec-max 5.5V, abs-max 7V);
  the "internal EN clamp" the P0 work assumed does NOT exist (live TI SLVSDG6C: EN abs
  7V, I_hys 1.55uA). FIX (autonomous): EN zener clamp (5.1V) + bypass cap, divider kept
  for reliable turn-on at the 5V default contract; remove the false docstring claim. A
  plain re-ratio cannot satisfy both turn-on-at-5V and <=5.5V-at-21V, so the clamp is
  required. Verify EN voltage in the SPICE gate. -> dedicated fix agent NOW (power.py
  free; no function-map collision).
- **PD-1 [low] — pd_input eFuse OVP window tight** (trip min 21.9V vs 21.0V legal max
  contract): widen R4 ~5.36k -> ~23.4V typ, stay below SMBJ22A VBR-min 24.4V. Bundle
  with PWR-1 (pd_input free).
- RESOLVED (2026-06-13, post function-map harvest — round 6 electrical-audit fixes):
  - **SD-1 [med] — RESOLVED**: microsd TPD6E001 U2.VCC was floating (worst-case clamp);
    now biased to the card rail +3V3_SD + local 100n (C14663). U2.NC is the only NC.
  - **HDMIRX-1 [med] — RESOLVED as documented DNP**: RX TMDS had no ESD. Researched +
    LIVE-verified a real in-spec part (TI TPD4E02B04DQAR, LCSC C106794, 39,617 stock,
    0.2 pF/line << 0.5 pF budget, 8 kV). A POPULATED 2x 4-ch shunt array cannot be
    auto-placed on this dense sheet under the immutable zero-crossing visual gate (the
    TMDS sink is off-sheet, so the placer's shunt-cell idiom is not triggered and an
    in-line array crosses other lanes). Per the finding's explicit fallback, carried as
    a DOCUMENTED DNP STUFFING OPTION (camera FFC ESD precedent) with the verified part id
    + layout note in the hdmi_rx docstring — NOT a ghost.
  - **HDMIRX-2 [low] — RESOLVED**: EDID WC# was hard-grounded (write-enabled); now a 10k
    write-protect strap pulls WC# HIGH to +3V3_HDMI_RX on the labeled jumper net
    HDMI_RX_EDID_WP (default write-protected; jumper to GND to program). E0/E1/E2 kept.
  - **LCD-1 [low] — RESOLVED**: SY7201 boost out cap C2 1u -> 2.2u/50V X7R, LIVE-verified
    CC0805KKX7R9BB225 (LCSC C125847, 72,946 stock); footprint corrected to 0805.

---

# 2026-06-13/14 — carrier/OVERNIGHT_PLAN.md (the autonomous overnight run tracker)

# OVERNIGHT IMPLEMENTATION PLAN — 2026-06-13/14

Durable execution record for the autonomous overnight run. The user approved
the **entire** investigation backlog (8-thread investigation, ~50 proposals)
via 12 decision questions, then went to bed with: *"work aggressively through
the night."* This file is the source of truth across context compactions —
update the checkboxes as units land.

## STATUS @ overnight (newest commits on master, fast-forwarded)

LANDED ON MASTER (each: full regression — board PASS 26 sheets + selftest
44/44 + m1 + determinism — before commit):
- PERF-2 parallel kicad-cli (172s→142s) · PERF-1 PinRef→Net index
- DEF-1 3D-model-offset bug (4 parts) · DEF-2 thermal-pad paste relief (5) ·
  DEF-3 default footprints + BOM footprint gate · DEF-4 link clobber guard ·
  DEF-6 HDMI-RX TMDS termination (new hdmi_rx_term sheet)
- BLOCK DIAGRAM full rewrite (the acute item) — layered DAG, clusters, legend,
  landscape; the unreadable strip is gone
- DOWNSTREAM: 4 new generators (Vivado TCL, PS device-tree, manifest.json,
  TEST_PLAN.md) + CLI subcommands
- DEVEX: pytest unit-test layer (147 cases) · DEBT-3 constant rename

ALSO LANDED: verification gates — design-rule completeness + per-device
thermal Tj (both hooked into `schgen board`, waivable, with CLI).

⚠ REVIEW ITEMS FOR YOU (surfaced by the new gates / deferred work):
1. THERMAL — the 3 TPS54302 bucks (U1/U2/U4, SOT-23-6 no exposed pad) are
   thermally layout-critical: Tj over the guard under the conservative model;
   waived + documented in carrier/research/thermal_bucks.md. Confirm RθJA by
   thermal sim / bench at bring-up, or move U1 (the hottest, 20 V→5 V @ 2.8 A)
   to an exposed-pad buck. This is a genuine margin call worth your eyes.
2. DEF-5 power_mon shunt split still deferred (telemetry reads across an open
   until the firmware shunt-walk + power-sheet decongest land).
3. RTC backup cell — DECIDED (your call): RECHARGEABLE ML1220 (Mn-Li). BT1 is
   now an ML1220 (charges to ~3.1 V from 3.3 V); firmware ENABLES the RV-3028
   trickle charger (TCE + ~3k series) for a maintenance-free RTC. Holder
   unchanged (KH-CR1220-2 fits 12.5 mm). Do NOT fit a primary CR1220 or a LIR
   Li-ion (4.2 V target > 3.3 V). Firmware contract + ASSEMBLY_NOTES updated.
4. Coin-cell silk polarity (audit-2). KH-CR1220-2 marks polarity on Cmts.User,
   not F.SilkS — add a silk `+` by pad 1 at layout (noted in ASSEMBLY_NOTES).
5. LCD-FFC ESD (audit-4). The 40-pin LCD FFC is user-touchable; lcd_backlight.md
   section 7 DEFERS ESD as "optional later hardening" — a documented choice, not
   a bug. If you want it consistent with the protect-every-connector philosophy,
   add a low-cap ESD array on the touch-I2C pair (CTP_SDA/SCL) at least; left to
   you (the LCD sheet is dense, so weigh the layout cost). NOT auto-applied.
6. FMC ESD (audit-4). An auditor flagged no ESD on the FMC LVDS lines — but FMC
   is a board-to-board MEZZANINE (not a cabled/user connector) and ESD arrays
   add capacitance that degrades LVDS SI, so omitting them is STANDARD FMC
   practice. Treated as a design choice (no change); flagged only for awareness.

DEFERRED / BIG-ROCKS still to do: DEF-5 power_mon shunt split (needs firmware
shunt-walk + power-sheet decongest), DS-1 BOM+CPL, bus notation, place.py
split, per-part rule engine, board HW (EEPROM/RTC/QWIIC/supervisor — all C1
gated), sourcing (HX5008 2nd-src/ALT_LCSC), GENPOLISH (title block/net-class
cues/sizing), remaining DFM docs, mutation classes + cc-gate.

## MANDATE (12 answers, 2026-06-13)

1. **Block diagram** → FULL professional rewrite (BD-1..8 + GAL-1).
2. **Tier-0 defects** → FIX ALL, including the 2 netlist/topology promotions
   (power_mon shunt split + HDMI-RX TMDS termination).
3. **Board HW** → ALL FOUR: board-ID EEPROM, RTC, QWIIC, supervisor+watchdog.
4. **Domains** → ALL FOUR: verification gates, generator+visual polish,
   developer experience, downstream/FPGA outputs.
5. **Big rocks** → ALL FOUR: bus notation (BUS-1), per-part rule engine,
   independent short/open CC proof gate, place.py split (ARCH-1).
6. **Commit policy** → commit+push every verified unit to
   `holistic-placement-rebuild`; fast-forward merge to `master` per completed
   track.
7. **Verify bar** → FULL regression before EVERY commit (board regen +
   selftest 44/44 + m1_rc + render eyeball + goldens).
8. **Strategy** → DEPTH-FIRST per track (finish+polish a track before next).
9. **Downstream artifacts** → ALL: BOM+CPL, Vivado TCL, PS device-tree,
   manifest.json.
10. **DFM/test docs** → ALL: TEST_PLAN.md, fiducials/tooling/ASSEMBLY_NOTES,
    chassis-GND star-bond, rev-A ICT plan.
11. **Sourcing** → ALL: HX5008 2nd-source, ALT_LCSC+stock-floor gate,
    lifecycle/EOL snapshot, inline-parts→folders + symbol fixes + part_gen
    regression tier.
12. **When done** → KEEP GOING: Tier-3 polish, then re-investigate, then keep
    implementing. Don't stop until the user is back.

## STANDING CONSTRAINTS (must hold for every relevant unit)

- **C1 — manual power enable on ALL new HW.** Every new hardware block
  (EEPROM, RTC, QWIIC, supervisor) sits behind a manual/DIP power enable using
  the existing gated-module idiom (SY6280 / module-gate), exactly like the
  current gated rails. No always-on additions without a gate.
- **C2 — watchdog must NOT reset during power-up.** The supervisor/watchdog is
  armed only AFTER rails are stable; its RESET must never fire during the
  bring-up ramp. Gate it + sequence its arm so a cold boot is never reset by
  it.
- **C3 — Zynq SoM chip may change later** (availability). Do NOT build
  chip-swap machinery now (carrier must be fully defined first), but avoid
  hard-coupling to XC7Z020 in ways that are painful to undo. Keep the device
  id sourced live from the SoM project (already the case in xdc.py), don't
  scatter the literal.
- **C0 — the LAWS still rule.** LAW 0 electrical integrity (prove the netlist,
  no shorts/opens), LAW 1 visual correctness (zero overlap/crossing), LAW 4
  never soften a gate. New geometry (bus notation) merges electrically only via
  alias labels proven by the kicad-cli netlist gate.

## EXECUTION DISCIPLINE

- Single writer to the working tree (me). Parallel agents/workflows only for
  DISJOINT add-only work (new subsystems, new generator modules, new gates,
  new parts/ folders, docs) in isolated worktrees, harvested sequentially.
  NEVER blind `git diff | apply`; NEVER `find -print0 | grep -z | xargs` on
  macOS.
- Full regression before every commit. Commit+push per unit. Merge to master
  per completed track (fast-forward).
- Depth-first: finish a track to 100% (incl. render eyeball for visual work)
  before starting the next.

## BUILD-SPEED NOTE (why PERF goes first)

Baseline: `selftest` ~68s, `board` ~172s (mostly serial kicad-cli + an
hdmi_rx escape-router quadratic). With full-regression-every-commit across
dozens of units, this dominates the night. **PERF-2 (parallelize kicad-cli) +
PERF-1 (memoize the hdmi_rx hotspot) are done FIRST** so every later
regression is fast (target board <60s). Both behavior-preserving — verified by
byte-identical goldens + the determinism check.

---

## TRACKS (priority order; depth-first)

### TRACK 0 — SETUP
- [x] Baseline selftest PASS 44/44 + determinism
- [x] Baseline board build green + timing (~172s) ; plan + memory ; commit plan (94a2c4e)

### TRACK PERF — build speed (do first)  [DONE]
- [x] PERF-2 parallelize per-sheet kicad-cli (ThreadPool, names-order verdicts) — 172s→142s (e7eebbf)
- [x] PERF-1 PinRef→Net index in _Engine (kills net_of quadratic; modest wall-time, kept) (8ea4542)

### TRACK DEFECTS — Tier-0 (fix all)
- [x] DEF-1 3D model offset unit bug — implausible offset reset to 0 + regen 4 parts (d576e26)
- [x] DEF-2 thermal/EP-pad windowed paste relief ~60% (5 footprints) (2399432)
- [ ] DEF-3 forbid footprint-less BOM parts (gate) + backfill (model/__main__)
- [x] DEF-4 `schgen link` clobber guard — partial link -> tempdir (186d87b) [== DX-2 P3]
- [~] DEF-5 DEFERRED to a big-rock effort. The 12-rename shunt split is
      electrically correct (net membership verified) but breaks two consumers:
      (1) the power-sheet ROUTER fails — the 4 new *_REG/+VIN_SYS rail symbols
      over-densify the most complex sheet (54 parts/29 nets), router exhausts 8
      expansions on an EN_5V_SOM vs GND contention (NOT a fit/size issue, so
      SIZE-1/A2 won't help); (2) firmware.py power-tree walk gets stuck — it
      chains regs directly and does not traverse the INA3221 series shunts.
      UNBLOCK PLAN: (a) firmware.py walk must hop through RS1-RS4 shunts;
      (b) decongest power.py by splitting the +5V_SOM/U4 always-on buck into
      its own sheet (power_som.py) — frees ~12 parts AND removes the contention
      region; (c) then land the 12 renames + power_mon waiver text. Reverted to
      green (186d87b).
- [x] DEF-6 HDMI-RX TMDS sink termination — NEW sheet hdmi_rx_term.py: 8×49.9R
      (C114625) from HDMI_RX_*_P/N to AVCC=+3V3. LINK PASS (3-way TMDS merge
      with hdmi_rx + som_j2), powertree +64mA OK, render clean. The 100n/1u
      AVCC bypass is a documented LAYOUT NOTE (not netlisted): the placer
      cannot anchor a rail-to-rail cap with no host part on an IC-less sheet
      ("no topology pattern matched"). >>> PLACER FINDING (-> GENPOLISH/ARCH):
      the placer has no pattern for standalone rail-decoupling caps (cap whose
      both pins are power rails, no IC). A small robustness fix (place such
      caps on the rail trunk / next to the rail power-symbol) would let DEF-6
      carry its bypass caps AND helps any future rail-bypass-only content.

### TRACK BLOCKDIAG — full rewrite (acute)  [DONE — worktree agent, 8 iters]
- [x] BD-1..8 + GAL-1 ALL landed in one diagram.py rewrite: layered L→R DAG with
      barycentre crossing reduction, peer-edge aggregation (per-pair count +
      dominant-kind), tall central SoM spine with distinct per-edge anchors,
      orthogonal gutter routing with unique per-edge lanes, ptype.kind colour +
      legend, fixed label grammar ('N nets · group'), subsystem clusters,
      landscape 2348×716 canvas (was 860×2580 strip), README embeds capped at
      width=900. Render rasterised + eyeballed — clean, readable, professional;
      the acute "unreadable" complaint is resolved.

### TRACK VERIFY — gates + automated testing  [VER-1/2 done, worktree agents]
- [x] VER-1 design-rule completeness gate (verify/design_rules.py): decoupling
      per IC supply pin / i2c pull-up / reset-RC / floating-strap, pin function
      inferred by NAME, model-only, waivable + board hook + `schgen design-rules`
      CLI. Findings on the current board: 0 missing decap, 2 hdmi_tx DDC pulls
      (waived: TPD12S016-integrated), 2 GPIO/internal-pull resets (waived).
- [x] VER-2 per-device thermal Tj gate (schgen/thermal.py): Tj=Ta+Pd*RthJA per
      device + waivable + board hook + `schgen thermal` CLI. >>> SURFACED A REAL
      ITEM: the 3 TPS54302 bucks (U1/U2/U4, SOT-23-6 no-EP) exceed the Tj guard
      under the conservative bare-package model — WAIVED as layout-critical +
      REVIEW-FLAGGED in carrier/research/thermal_bucks.md (confirm RthJA by
      thermal sim/bench at bring-up, else switch U1 to an exposed-pad buck).
- [ ] VER-3 mutation classes for new + untested gates (selftest.py)
- [x] VER-4 independent connected-components short/open gate (verify/cc_gate.py)
      — a SECOND oracle disjoint from kicad-cli: net-blind union-find over the
      emitted geometry vs the declared nets. Board: 0 shorts/0 opens on all 26
      sheets AND agrees with kicad-cli PIN-FOR-PIN 26/26 (full equivalence-
      relation cross-check). Net-blindness + synthetic short/open proven by the
      builder. Hooked into board. >>> VERIFY TRACK COMPLETE.

### TRACK DEVEX — dev experience + automated testing
- [x] DX-1 pytest unit-test layer (schgen/tests/, 147 cases ~8s, worktree agent) — c92d7c4 [HIGH — user emphasis]
- [ ] DX-2 authoring UX: P1 clean CLI errors, P2 unassigned-by-name, P4 list/pins, P5 bulk-NC, P6 footprint-validate, P7 build-time link check, P8 scaffolder+DESIGN.md path, P10 unify loaders
- [ ] DX-3 DEBT-1 PlacedDesign.from_placement factory + DEBT-3 rename _DRIVER_ETYPES
- [ ] DX-4 [BIG] place.py split into template modules behind registry (AFTER DX-1)

### TRACK GENPOLISH — visual fidelity
- [x] GP-1 TITLE-1 populated title block (emit.py) — title=circuit title, company
      "Zynq SoM Carrier", generated-by comment, NO date (determinism); all 26
      sheets, render-verified (A4 + A3), goldens re-blessed
- [ ] GP-2 CUE-1 net-class stroke cues
- [ ] GP-3 SIZE-1 A2/A1 sheet-size ladder
- [ ] GP-4 LABEL-1 directional label shapes
- [ ] GP-5 IDIOM-1 broaden templates / relax regulator shared_ok
- [ ] GP-6 [BIG] BUS-1+BUS-2 bus notation (RGB888/FMC/SDIO) — alias-merge, LAW 0
- [ ] GP-7 MULTIUNIT-1 multi-unit symbols

### TRACK DOWNSTREAM  [3/4 + TEST_PLAN done via parallel worktree workflow]
- [ ] DS-1 assembly-ready BOM enrich (MPN/datasheet/Basic-Ext) + JLC CPL cpl_jlc.csv  <-- still TODO
- [x] DS-2 Vivado create_project.tcl (schgen/vivado.py; device live-extracted via extract_zynq) + CLI + board hook
- [x] DS-3 Zynq PS device-tree fragment (schgen/devicetree.py -> carrier/firmware/carrier_pl.dtsi) + CLI + hook
- [x] DS-4 manifest.json integration spine (schgen/manifest.py; 24 rails/i2c/gpio + 43 artifact sha256) + CLI + hook
- [x] DOC-1 TEST_PLAN.md (schgen/testplan.py; spice limits + TP pads + DIP stages) + CLI + hook  [also a DFMDOCS item]
      All 4 built by a worktree-isolated parallel workflow, content harvested,
      hooked into cmd_board + registered as `schgen vivado|devicetree|manifest|
      testplan` CLI subcommands. board PASS, deterministic, selftest 44/44.

### TRACK SOURCING
- [x] SRC-1 HX5008 second-source committed (ethernet T1 ALT_LCSC=C47575004)
- [x] SRC-2 ALT_LCSC + stock-floor in preflight (assess_stock pure fn +
      STOCK_FLOOR + --min-stock + alternate fallback) + pytest test_preflight.
      NOTE: the live JLC-query fallback path needs network to fully exercise;
      the pure stock-verdict logic is unit-tested offline (incl the HX5008
      stock-10 landmine -> LOW warning).
- [ ] SRC-3 lifecycle/EOL + stock/price snapshot capture (part_gen)
- [ ] SRC-4 inline 5 schgen: parts → parts/ folders + symbol-name preservation (P5) + part_gen regression tier (P6)

### TRACK BOARDHW — new hardware (C1 gated; C2 watchdog post-stable) >>> DONE
All four blocks landed on TWO new sheets — board_aux (the gate + PCA9306 I2C
isolator) and board_services (the peripherals) — split so neither defeats the
placer's rail-stub router. board PASS @ 28 sheets, all gates green, preflight
PASS (+$4.56/board), determinism PASS.
- [x] HW-1 board-ID EEPROM 24AA025E48 (SOT-23-6, C129895) — EUI-48 MAC for the
      RJ45/LAN8720, strapped **0x51** (A0=1; 0x50 is the FMC EEPROM). On the
      gated +3V3_AUX rail behind the PCA9306 isolator.
- [x] HW-2 RTC RV-3028-C7 (C3019759) — integrated DTCXO (no crystal), CR1220
      coin cell (KH-CR1220-2) auto-switchover, **0x52**, gated rail.
- [x] HW-3 QWIIC / STEMMA-QT (ZX-SH1.0-4PWT, C7430446) on the isolated AUX I2C
      + gated 3V3 — external modules never touch the always-on management bus.
- [x] HW-4 supervisor + watchdog TPS3823-33 (C7719). **C1**: on default-OFF
      +3V3_AUX (DSHP04 SW1). **C2** (no power-up reset) THREE ways: rail OFF at
      power-up (unpowered), WDI-float-disables-watchdog until firmware drives
      WATCHDOG_KICK, and RESET# is a firmware-mediated PL event (J3.31), never a
      hard POR. **C3**: watchdog signals ride PL bank-35 (IO_L16_N/P_35), xdc-
      sourced — no Zynq hard-coupling.
- [x] HW-* 6 parts/ folders (part add) + downstream regen (xdc picks up the 2
      watchdog PL pins, firmware/nets/manifest/BOM all updated).
- LAW 0: PCA9306 EN tied to +3V3_AUX auto-isolates the gated peripherals from
      the always-on STM32_I2C2 bus (no back-powering through ESD diodes).
  REVIEW NOTE (low): QWIIC J10 pad-1 location must be verified against the
  footprint silk before fab (power/I2C order); flagged in the sheet docstring.

### TRACK RULE-ENGINE — [BIG] large capability
- [ ] RE-1 part_gen captures RATINGS (V/I/P/tol/dielectric/temp)
- [ ] RE-2 per-part RULES (derate / pullup_window / fb math)
- [ ] RE-3 `schgen rulecheck` gate (net voltage from power tree × rules) + board hook
- [ ] RE-4 seed MLCC derating ≥50% + pull-up window + buck FB; + mutants

### TRACK DFMDOCS
- [x] DOC-1 TEST_PLAN.md (done in DOWNSTREAM via schgen/testplan.py)
- [x] DOC-2 fiducials + tooling + carrier/manufacturing/ASSEMBLY_NOTES.md
      (static requirements doc; a floorplan-driven coord generator is a noted
      follow-on)
- [x] DOC-3 chassis-GND star-bond explicit requirement (in ASSEMBLY_NOTES.md:
      single-point GND<->CHASSIS_GND stitch at the RJ45/HDMI shield entry)
- [ ] DOC-4 rev-A ICT / flying-probe plan (TEST_PLAN.md covers most of this)

### TRACK TIER3 — polish then re-investigate (keep going)
- [ ] symbol quality P5 deepening, datasheet bundle PARTS.md, PCB stub, boot/heartbeat LEDs, FILL-1, FP-1/2, RND-1, GAL-2, REUSE-1
- [ ] fresh investigation round → next wave → keep implementing

---

## PROGRESS LOG (newest first)
- 2026-06-14: AUDIT-3 (engine / gate-soundness / generators / determinism — the
  surfaces audits 1-2 did not touch). 19 confirmed of 26; re-verified each.
  The headline "CRITICAL determinism bug" (unsorted set iteration) was proven a
  FALSE ALARM by a definitive test: two full builds with PYTHONHASHSEED 0 vs
  12345 -> byte-identical. Still hardened the latent fragility: route.py emits
  junctions + splits legs in sorted order (canonical; renders unchanged, 14
  .kicad_sch reordered) AND a NEW cross-seed determinism gate in the selftest
  builds each sheet in two subprocesses with different hash seeds — this
  PERMANENTLY guards ALL the determinism findings (emit/place/manifest unsorted
  iterations) at once. Downstream completeness: the board-HW I2C devices
  (0x51/0x52) now appear in testplan (Stage 6 + the isolator ACK-proof) and
  manifest (bus AUX_I2C), single-sourced from firmware._id_eeprom_addr.
  Commits 2151a9c (determinism), 6057e3c (testplan), 3fc5973 (manifest).
  DOCUMENTED-SKIP (re-verified as non-issues / caught elsewhere): visual_gate
  junction-degree validation — the proposed fix is naive (would false-flag
  valid junctions at pins; degree needs wire+pin geometry the visual gate
  lacks), and missing/spurious junctions are already caught electrically by the
  CC + netlist gates; design_rules STRAP-on-undriven-rail — caught by ERC +
  powertree; manifest missing-subsystem guard — firmware already fails loudly
  on a missing ID-EEPROM. Several "confirmed" findings were over-confirmations
  whose fixes would not have improved correctness (see memory note).

- 2026-06-14: RE-INVESTIGATION (mandate "polish then re-investigate"). Ran a
  7-dimension / 14-agent adversarial audit of the 28-sheet board + the new
  board-HW. Every finding independently re-verified before action. 2 confident
  "HIGH" FALSE POSITIVES rejected with proof (their fixes would have introduced
  bugs: a DSHP04 mis-wire that never enables the rail; a non-existent PCA9306 EN
  float). 3 REAL findings fixed: (a) QWIIC ESD — moved to its own sheet
  board_qwiic + USBLC6 array (29 sheets); (b) firmware I2C-map completeness —
  board_aux/services added to SOURCES, ID-EEPROM 0x51 strap-DERIVED so a
  mis-strap trips the collision check, +RTC 0x52 +FMC 0x50 (117 #defines);
  (c) docstring clarity. board PASS @29, determinism PASS, pytest 168->170.
  Commits 72b87ce (audit fixes), ed92cb5 (board-HW invariant tests).
- 2026-06-14: BOARDHW done — all 4 blocks (EEPROM/RTC/QWIIC/watchdog) on the
  gated +3V3_AUX across board_aux/board_services, C1/C2/C3 honoured. cfabd8a.
- 2026-06-14: VERIFY done — independent CC short/open gate (2nd oracle). d846368.
- 2026-06-13: investigation complete (8 threads); 12 decisions captured; baseline green; plan written. Starting TRACK PERF.

---

# 2026-06-14 — MORNING_REPORT.md (overnight run summary)

# Overnight run — morning report (2026-06-14)

Autonomous overnight session summary. Detailed tracker:
[carrier/OVERNIGHT_PLAN.md](carrier/OVERNIGHT_PLAN.md) (now archived above).
**Everything below was on `master`** (fast-forwarded, ~33 commits), each gated
by a full regression — board PASS **29 sheets** + selftest **53/53** + m1 +
byte-determinism (now also cross-PYTHONHASHSEED) + pytest **181** — before it
landed. Working tree clean.

## Continuation tracks (after the first draft)

1. **VERIFY — independent CC short/open gate.** A 2nd oracle, disjoint from
   kicad-cli (net-blind union-find over the emitted geometry); agrees pin-for-
   pin on all sheets. The board is now electrically proven by two code paths.
2. **Board HW — ALL FOUR blocks** (see the dedicated section below).
3. **Four adversarial re-investigation audits** (19 dimensions, ~77 agents) —
   electrical defects ×2, engine/gate-soundness + determinism, and a
   completeness critic (what's *missing*). The last found two real
   dossier-mandated **bulk caps** absent on gated rails (+3V3_HDMI_TX,
   +3V3_LCD) — now added; LCD-FFC + FMC ESD were re-verified as a documented
   deferral / a board-to-board-mezzanine design choice and left as review items.
   Every finding independently re-verified — several confident "HIGH/CRITICAL"
   findings were FALSE POSITIVES whose fixes would have *introduced* bugs, and
   are documented-rejected (a DSHP04 mis-wire that never enables the rail; a
   non-existent PCA9306 EN float; an ~11 µA EN back-feed; an over-stated USBLC6
   "ineffective" claim; a "CRITICAL determinism bug" disproved by a definitive
   cross-PYTHONHASHSEED build test). REAL fixes landed:
   - **firmware I2C-map completeness** — ID-EEPROM (strap-derived so a mis-strap
     trips the collision check) / RTC / FMC, now also in the **testplan** (Stage
     6 + an isolator ACK-proof) and **manifest** (bus AUX_I2C), single-sourced.
   - a **VCCO bank-rail drift gate** (xdc IOSTANDARD map vs som_conn_gen — a C3
     safety net) and a **cross-PYTHONHASHSEED determinism gate** in the selftest
     (plus canonical sorted junction emission) — the determinism invariant is
     now bulletproof and permanently gated.
   - QWIIC ESD on its own sheet, clamp referenced to always-on +3V3; the RTC
     primary-cell/trickle-charger safeguard elevated into the firmware contract;
     DFM/assembly notes; a derived bring-up "Stage 6 — board services".
   ~40 new pytest cases lock it all. The board-HW now appears in EVERY
   downstream artifact (firmware / manual / testplan / manifest / xdc).

## What landed (by track)

| Track | What |
|------|------|
| **Block diagram (your #1)** | Full rewrite — the unreadable 860×2580 strip → a clean **layered landscape system map**: subsystem clusters, a tall central SoM spine, a legend, per-edge type-colouring + counts. |
| **Tier-0 defects** | **DEF-1** 3D-model-offset bug (4 parts a metre off); **DEF-2** thermal-pad **paste relief** (5 parts); **DEF-3** default footprints + a **BOM footprint gate**; **DEF-4** `schgen link` clobber guard; **DEF-6** **HDMI-RX TMDS termination** (new sheet). |
| **Downstream** | 4 new generators + CLI: **Vivado `create_project.tcl`**, **PS device-tree** `carrier_pl.dtsi`, **`manifest.json`** spine, **`TEST_PLAN.md`**. |
| **Verification** | **pytest** unit layer (154 cases, ~8 s) · **design-rule completeness** gate · **per-device thermal Tj** gate · **+9 mutation classes** proving the model-only gates bite (44→53). |
| **Generator polish** | **Title block** populated on every sheet (was blank). |
| **Sourcing** | `ALT_LCSC` second sources + a **procurement stock-floor** in preflight (the HX5008 stock-10 landmine now WARNs); unit-tested. |
| **Build/engine/DFM** | `schgen board` parallelised (172→142 s); `_DRIVER_ETYPES` footgun renamed; `ASSEMBLY_NOTES.md` (fiducials/tooling/chassis-GND star/silkscreen). |

## ⚠ Review items — your eyes wanted

1. **TPS54302 buck thermals (real, surfaced by the new thermal gate).** U1/U2/U4
   (SOT-23-6, no exposed pad) exceed the Tj guard under the conservative
   bare-package model. Waived as layout-critical + documented in
   [carrier/research/thermal_bucks.md](research/thermal_bucks.md):
   confirm RθJA by thermal sim / bench at bring-up, or move U1 (hottest, 20 V→5 V
   @ 2.8 A) to an exposed-pad buck. A genuine margin call.
2. **DEF-5 power_mon shunt split — deferred.** Per-rail telemetry reads across an
   open until two coupled changes land (firmware power-tree walk must traverse
   the INA3221 shunts; the power sheet must be decongested, cleanest by splitting
   the +5V_SOM/U4 buck to its own sheet). A 3-part big-rock, not a quick fix.

## Board HW — ALL FOUR landed (was deferred; now done)

Two new sheets, **board_aux** (gate + PCA9306 I2C isolator) and **board_services**
(EEPROM + RTC + watchdog + QWIIC), split so neither defeats the placer. board
PASS @ **28 sheets**, every gate green, determinism + preflight PASS (+$4.56/bd).

- **ID-EEPROM** 24AA025E48 — factory **EUI-48 MAC** for the RJ45 (0x51).
- **RTC** RV-3028-C7 — integrated DTCXO (no crystal) + CR1220 backup (0x52).
- **Watchdog** TPS3823-33 + **QWIIC** expansion.
- **C1**: all on the default-OFF, DIP-gated +3V3_AUX (SY6280). **C2**: watchdog
  unpowered at power-up + WDI-float-disable + RESET# as a firmware-mediated PL
  event — *three* guards, never a hard POR. **C3**: watchdog rides PL bank-35,
  xdc-sourced. **LAW 0**: PCA9306 isolates the gated bus from always-on I2C.
- ⚠ low review: verify QWIIC J10 pad-1 vs silk before fab (noted in docstring).

- Device id stays **live-sourced** from the SoM project (C3).

## Deferred (big-rocks / risk — better with your review, not done overnight)

Bus notation, per-part rule engine, `place.py` split, BOM+CPL (DS-1), part
lifecycle/EOL snapshot, inline-parts→folders. All tracked with rationale in the
plan above.

## How to verify

```
python3 -m schgen board          # all sheets, every gate PASS
python3 -m schgen selftest       # mutants killed + byte-determinism
python3 -m pytest schgen/tests/  # unit cases
python3 -m schgen thermal        # the Tj gate (the buck review item)
python3 -m schgen design-rules   # the completeness gate
```
</content>
</invoke>
