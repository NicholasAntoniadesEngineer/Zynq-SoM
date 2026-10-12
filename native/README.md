# Native migration

The target is a complete C++ generator, including design loading, placement,
routing, emission, verification, CLI, and tests. The Python extension and the
393 inventoried Python sources/tests are retired. Native kernels alone do not complete the port.
Final acceptance requires zero repository-owned Python sources, tests, helpers,
bindings, or runtime dependencies. KiCad/design data, FPGA HDL, and generated
XDC/Tcl remain in their required hardware formats; generator/tooling code is C++.

## Build without Python

For the native-only full CTest workflow and offline dependency bootstrap, see
[`ci/README.md`](ci/README.md). That additive entry point needs CMake 3.28+ and
explicitly checks installed KiCad libraries. Native contracts retain independent
parity fixtures; no Python test runtime is required.

Install the pinned native zlib-ng compressor using the instructions in
[the manufacturing handoff](tests/data/manufacturing/README.md#explicit-native-installation-and-parent-wiring).
It must be the tested static/PIC compatibility build so existing PNG bytes remain
identical. Supply its installed prefix explicitly; CMake verifies the version
and a compression known-answer test rather than silently selecting system zlib.
The example below uses the local dependency installation under the ignored build
directory. From the repository root:

```sh
cmake -S native -B native/build/standalone -DSCHGEN_BUILD_PYTHON=OFF -DCMAKE_BUILD_TYPE=Release \
  -DSCHGEN_MANUFACTURING_ZLIB_PREFIX="$PWD/native/build/deps/zlib-ng"
cmake --build native/build/standalone --parallel
ctest --test-dir native/build/standalone --output-on-failure
native/bin/schgen --help
```

For repeated local C++ development with Ninja and ccache installed, run these
from `native/` (CMake 3.20+ for presets): `cmake --preset native-fast`, then
`cmake --build --preset native-fast` and `ctest --preset native-fast-offline`.
The preset keeps compiler caches under ignored `native/build/`; it neither
downloads dependencies nor enables Python. Ninja avoids Make's broad object
rebuilds when unrelated per-source compilation options change. Do not build
different build directories concurrently: they currently publish the same CLI
and catalogs in the source tree.

This is also the default configuration: enabling retired Python bindings is an error. The build
uses C++17, libxml2 (for KiCad netlists), native zlib-ng (for exact manufacturing PNGs),
and Poppler C++/libpng (for schematic rasterization), without discovering Python,
installing nanobind, or fetching dependencies. Live SoM extraction requires
`kicad-cli` on PATH; it is invoked directly, never through a shell.

The native CLI supports `self-check`, `catalog-compile`, `circuit-compile`,
`project-check`, `circuit-check`, `som-interface`, `link`, `bom`, `xdc`, `vivado`, `fpga`, and
`devicetree`, `design-rules`, `testpoints`, `constraints`, `powertree`, `thermal`,
`part-rules`, `bom-values`, `footprint-pads`, `pin-completeness`, `symbol-law`,
`spice`, `firmware`, `manual`, `scfw`, `testplan`, `power-sequence`, and `selftest`.
The native `board` command performs full generation with mandatory native audit
providers; its complete source-audit acceptance is still in progress. Other
integrated commands include `build`, the four-sheet `devkit` example, `nets`,
`subsystem-check`, `carrier-check`, and the native experiment commands.
`check --tests-dir BUILD` runs full board generation, mutation/determinism
selftest and every configured native CTest, requiring complete passing JUnit
evidence. It does not build its selected test directory or waive failing gates.
Unsupported commands fail.

The `spice` command requires at least one supported analytic check before it
can pass. Empty coverage reports `UNVERIFIED (0 checks)` and exits nonzero;
the mandatory board SPICE gate also fails closed for that case. A nonempty
passing report proves only its listed spot checks, not coverage of every
selected circuit or signal-integrity behavior. Dedicated native identity
contracts cover retained passive models such as HDMI termination separately.
For the existing named-divider contracts, a present net with unextractable
topology or the wrong source rail is an error even if other checks pass.
Likewise, detected regulators with missing feedback/current-setting topology,
an unsupported feedback reference, or an unmodelled enable-clamp zener fail
extraction with `SPICE unverified`. Other passing checks cannot certify these
missing models; the diagnostic is not a claim that the physical circuit fails.
Enable equations are device-specific: the existing TPS54302 model must not
qualify LM61460 or another buck family. Unsupported enable networks are retained
as explicit `unverified` reasons in the result/JSON and test plan, with a nonzero
CLI exit and failed mandatory board gate, while other completed checks remain
available. The former `power_som` clamp network remains **UNVERIFIED** in the
historical fixtures; current authoring uses the direct-enable arrangement below.
A separately supported LM61460AANRJRR self-start topology requires uniquely
netted pins 7 (EN/SYNC), 8 (VIN1) and 12 (VIN2) on the same power net. Its check
is explicitly a connectivity result, not a voltage-envelope, startup-timing or
transient claim. Missing regulator-detection evidence also makes the aggregate
unverified instead of disappearing behind unrelated checks. Both live boards
use this direct connection without the old R12/D5/C20 clamp/filter. Input
envelope, startup timing and transient qualification remain separate obligations.
Analytic checks retain full calculated precision for acceptance, JSON and
simulator comparisons, including dividers, RC timing, current setting,
regulator feedback, enable clamps and boot straps. Decimal display rounding
must not hide violations.

`subsystem-new NAME` creates a C++ source/header/test package with retained
README, SPICE and JSON metadata. It never overwrites an existing destination.
New packages are opt-in with `-DSCHGEN_SUBSYSTEM_PACKAGES='name;another'`;
the generated CMake registration connects real factories to the immutable
native registry. The initial unimplemented builder deliberately fails its test.

The PCB verification aggregate now shares one geometry snapshot and MST across
the real placement, connector, ratsnest, fanout, return-stitch and escape gates.
Both live projects are checked against independent committed reports. This is
not yet the full-board verdict: external DRC and non-PCB gates remain separate.
The native DRC runner invokes KiCad directly with a bounded timeout and private
report directory. Missing/malformed reports and nonzero tool exits are errors,
not empty successful findings. Its transitional adapter contains no DRC logic.
Use `native/bin/schgen pcb-drc --project NAME` to check an existing board. The
full build reuses validated severity counts from its first DRC report instead
of refilling and checking the same board twice. Reports lacking severity retain
an explicit errors-only fallback; warning and unrouted findings remain visible.

`selftest` runs the complete 63-mutation suite through real KiCad exports, ERC,
native gates, geometry checks, and fresh native worker processes. It does not
invoke Python. Worker failures and missing footprint libraries fail the run;
they cannot count as mutation kills. The separate `self-check` remains only a
small kernel smoke test. Live contract tests carry the `live-kicad` CTest label.

The native core includes complete floorplan search/compose/export, immutable
PCB-check snapshots, and board/project/design-rule emission. Frozen independent
fixtures verify both projects' exact outputs and mutation/error cases. The
transitional PCB pipeline now uses the native writers and shares one prepared
snapshot across its PCB gates, avoiding repeated source parsing. Standalone gate
calls still prepare fresh inputs; no global cache hides placement or file edits.
The original return-path-v1 failures remain separate from return-stitch coverage;
this migration does not waive them. Standalone `floorplan` and `compose` are
registered native commands: floorplan writes documents or exports a spec;
compose measures, ranks repairs with `--repair --dry-run`, or applies a repair
subject to full board gates and rollback on failure. Their ordinary, live-KiCad
and apply contracts are registered in CTest. This is not a claim of complete
source-audit or whole-board acceptance.

For faster automatic outline iteration, `board --multiscale-outline` opts into
bounded power-of-two axis/diagonal refinement instead of the complete fine-grid
scan. It can miss smaller solutions and is deliberately not the default. Supply
a known good starting size with `--initial-outline-mm`; that candidate is
revalidated, never treated as cached acceptance. Fixed outlines conflict with
this option. Actual attempts, retries and fallbacks remain accounted, and no
acceptance gate or retry limit is relaxed. For example:

```sh
native/bin/schgen board --project carrier --compact-placement --interior-order 3 --initial-outline-mm 168x160 --multiscale-outline --timing -o /tmp/carrier-multiscale
native/bin/schgen board --project devkit_mini --multiscale-outline --timing -o /tmp/devkit-multiscale
```

These are experiment configurations, not fabrication-readiness claims. See
`benchmarks/2026-10-08-multiscale-outline-qualification.json` for qualification,
timing scope, and the rejected unseeded carrier area regression.

```sh
native/bin/schgen project-check --project carrier
native/bin/schgen project-check --project devkit_mini
native/bin/schgen circuit-check --project devkit_mini
native/bin/schgen design-rules --project devkit_mini
native/bin/schgen testpoints --project devkit_mini
native/bin/schgen fpga --project carrier --output /tmp/carrier-fpga
native/bin/schgen devicetree --project carrier --output /tmp/carrier_pl.dtsi
native/bin/schgen bom --project carrier --qualified-refs --output /tmp/carrier-bom.csv
```

`fpga` generates XDC and Vivado Tcl from one live extraction, validating both
before publication. Each output is atomically replaced. Project selection is
explicit (`--project`), then `SCHGEN_PROJECT`, then `carrier`; use `--repo` when
running outside the repository root. Circuit discovery and loading require
canonical `<project>/subsystems/<name>/circuit.json`, not authoring Python.
Function/rail/strap policy is in each project's `som_mapping.json`.

`circuit-check` resolves actual library symbols and checks every pin and internal
input driver; JSON pin metadata is not a substitute for physical symbol pins.
`link` also enforces symbol-backed completeness before linking. The native core
now includes complete symbol loading, schematic emission, routing, netlist and visual
validation stages, tested against frozen inputs and output bytes. Netlist verification
shares the hardened KiCad process/XML boundary with SoM extraction, and checks
connectivity plus NC markers against embedded symbol geometry. Full board
orchestration is native; complete acceptance is tracked below.
The hierarchical schematic stage is independently available as
`native/bin/schgen board-schematic --project NAME -o DIRECTORY`. It generates
the real routed sheets and root hierarchy, preserves persistent reference bands,
and runs live KiCad connectivity checks. Per-sheet exports use bounded workers
with deterministic result collection. This command is not a substitute for the
remaining PCB, manufacturing and complete-board verification stages. Both
supported projects' native root and child schematics match the committed bytes.

The complete schematic placer now runs natively: topology classification,
fanout, regulator templates, chain layout, probe rows, retry expansion and
pagination all use the same typed engine and router. Frozen full-board and
isolated topology contracts cover ordered geometry and page boundaries. The
legacy Python engine is removed; remaining adapters preserve caller-owned
symbol snapshots and intermediate page metadata without reloading sources.
Native mutation proofs exercise missing-decoupler and incorrect clamp-layout
failures through the real completeness, routing and visual gates.

Design-rule verification (decoupling, I2C pull-ups, reset RC, configuration straps,
exposed pads), test-point coverage and their reports also run in C++. The native
commands print diagnostics, return nonzero on findings, and write a report only
when `--output` is supplied. They accept subsystem selection; board-wide pull-ups
outside the selected sheets are intentionally absent from that check.
Symbol-backed completeness remains a separate mandatory gate (`circuit-check`).
Power-tree analysis and SVG, thermal analysis with emitted-copper evidence, and
part-rating checks now execute in C++. Frozen report contracts cover both projects,
policy mutations and supplied power results. Thermal credit requires real copper
evidence; an absent PCB does not silently grant cooling credit. Transitional
adapters preserve caller-owned policy tables and typed numeric fields.
BOM-value normalization, footprint-pad coverage, pin/NC completeness, symbol
provenance and analytic/SPICE checks also run natively. Their frozen contracts
include poisoned values, disconnected pins and malformed geometry. Optional
ngspice cross-checks use a shell-free bounded process with private temporary
decks and real measurements; absence of ngspice retains the analytic gate.
Connectivity and symbol metadata are indexed once per snapshot. Mutable caller
inputs require a new snapshot; caches never silently reuse a previous board.

Bring-up facts, firmware contracts, SC scaffolds, the manual, test plan and
power-sequence SVG now use native typed inputs. Independent fixtures cover both
projects and changes to GPIOs, feedback values, addresses and required sheets.
Live U9 extraction remains authoritative. The sequence walker rejects reachable
cycles instead of looping indefinitely. Generated SC code still has a known
undefined FMC EEPROM macro, and RTC battery/charging guidance is inconsistent;
these pre-existing output defects are not treated as successful compile checks.

Carrier and devkit XDC/Tcl, and carrier BOM, match the established output bytes.
Device-tree output changes only generator/source provenance comments. Native
contract tests cover extraction, mapping, linking, project isolation, rendering
and validation failures. Clean native full-render acceptance passed for both
boards at `29d43472` on October 1, including the source and ledger audits
(66 C++ files, 155 registered transforms). The devkit's two missing
I2C pull-ups and nine uncovered probe requirements are corrected with physical
parts, without new waivers. Probe-only ports now export hierarchical sheet
connections; regulator discovery excludes measurement pads, and PCB placement
handles connector-sheet auxiliaries without moving the fixed mezzanines.

The transitional Python bindings and build script are retired. The standalone
CLI and native tests link the same `schgen_core` library; engine sources compile
once per build directory. Preserve the per-source floating-point settings:
these are part of the deterministic-output contract.

Build catalogs depend on their JSON inputs and regenerate when those inputs change.
Compilers publish complete catalogs by atomic replacement, so existing mapped
readers retain their snapshot during a rebuild. Close and reopen a catalog to
read its new version. Failed publication leaves the previous file untouched.
The transitional circuit adapter uses project-scoped `native/circuits.bin`
outputs under each project, while the parts catalog is shared. Native project
commands read validated JSON directly and do not depend on interpreter caches.
Build directories share the in-tree binary and catalog outputs, so build them
sequentially.

## Migration acceptance and remaining design work

`run_board_pipeline` is now compiled into the native library, with composed
schematic, electrical, PCB, document and audit stages. Its contracts compare
all 49 live-authored carrier/devkit circuit snapshots with canonical hardware IR,
exercise real KiCad connectivity/ERC, and reject missing mandatory stages.
The caller must open the part catalog before authoring. The native full-board
CLI installs reviewed ledger providers after loading actual board inputs.
Missing declarations or manifests fail explicitly. Clean full-render acceptance
now passes, with all 226 CTests having successful final coverage (222 from the
full run plus four corrected harness reruns, not a single 226/226 run).
See `benchmarks/2026-10-01-migration-acceptance.json` for pinned timings and scope.
Source auditing remains the dominant runtime cost. Advisory return-path,
golden-drift and coverage findings remain visible; neither board is fully routed
or claimed fabrication-ready. Coverage lint uses every wired-sheet part,
including unplaced parts. Successful migration does not certify every historical
hardware or generated-firmware design decision.

`board --audit-projections 2` opts into two simultaneous source-audit AST
projections; the default is one to retain the lower-memory path. Both settings
scan the complete manifest and retain dependency-change detection, deterministic
census order and failure propagation. In a paired 49-file measurement, audit time
fell from 130.07 s to 88.05 s while sampled process-tree peak memory rose from
2.87 GB to 4.32 GB. These are single-run audit measurements, not whole-build or
Python-comparison speedups. Use `--audit-projections 1` on memory-constrained runs.
That paired benchmark uses the 49-file pipeline manifest; the integrated native
policy audit includes additional sources (69 files in the qualified builds).

The qualified 165x158 carrier alternative is reproducible with
`benchmarks/carrier-165x158-continuation.floorplan.json`, compact placement,
interior order 3, edge feasibility, owned quality/face cohesion, USB-JTAG
contract-group candidates, `--joint-separation-states 1024 --reseat-poses 8
--reseat-frontier 4096 --reseat-continuations 3`, and **no** pinned `--owned-shape`.
Both reseat pose/frontier limits are required; continuation replays require an
explicit interior order and cannot be combined with failed-first retry. These
limits control computation, not physical feasibility. The 165x159 reference is
retained: the smaller alternative uses more search and has a higher cross-wire
estimate. See `benchmarks/2026-10-12-carrier-165x158-qualification.json` for the
full gate, rendering, quality and unresolved-risk evidence.

`--reseat-victim-shapes` is an opt-in additional recovery strategy for `board`
(profiler: `--reseat-victim-shapes on`). It requires compact placement, an explicit
interior order, and both pose/frontier limits. The unchanged original strategy,
including its configured continuation attempts, runs first. Only after failure
does one separate full attempt allow a displaced subsystem to try its other
registered shapes when its existing shape cannot be reseated. Explicit shape
selections and final hardware checks still apply. Rejected attempts restore the
entry layout and offers but retain actual operation and fallback receipts.
After the original victim/position trials are exhausted for an incoming block,
the extra strategy also tries the nearest legal pose of its other registered
shapes, with the same explicit shape-selection restrictions. Incoming-shape
queries have a separate `interior_reseat_incoming_shape_trial` receipt. This
does not enumerate all positions for all shapes or displace multiple victims.
Alternative incoming shapes now also try legal alternative displaced shapes;
previously that phase held the displaced shape fixed. Every additional query
retains its existing shape-trial receipt. Interaction contracts include a
fixture where either strategy alone fails but their combination succeeds,
plus a mutation test that detects removal of paired exploration. The current
150-case set has no additional recoveries from the paired-query extension;
it adds ten exercised queries, not a demonstrated board-size improvement.
Eight carrier factorial screens and two paired extensions are recorded in
`benchmarks/2026-10-12-shape-interaction-screening.json`. All smaller-board
screens failed under their tested settings; that does not establish that
other combinations cannot help. Keep correctness tests distinct from search
experiments, and retain configuration-specific negative results for reuse.
Continuation retries can now be combined with `--failed-first-retry`. After
the original, continuation, failed-first and shape-only attempts fail, enabling
both failed-first and shape recovery also tries shapes in the failure-directed
order. This extra full attempt records both existing strategy events; they
describe two enabled strategy dimensions, not two solver invocations. Actual
solver work remains independently counted. This is not a complete Cartesian
search: continuation replay still applies to the original-order strategy.
The 300-case composition tests compare independent attempts, enforce geometry,
check reproducibility, and verify failed/exception rollback without dropping
executed work. See `benchmarks/2026-10-12-composed-recovery.json` for the current
negative carrier screens and explicit qualification limits.
Scarcity order (`--interior-order 2`) counts permitted shapes rather than the
entire registry: a pinned group has one choice, even if many unselected shapes
exist. Property and placement-level contracts cover this distinction; restoring
the previous registry-size comparison fails the integration test. Six further
order/recovery screens and the corrected screens remain unsuccessful at
165x156, so this is a correctness fix to the search heuristic, not an area win.
The integrated code passed a fresh full 166x156 carrier build and source audit;
see `benchmarks/2026-10-12-permitted-shape-scarcity.json` for scope and timings.
This is not exhaustive shape/pose search: the additional strategy currently
selects the first locally valid victim shape. It preserves the 165x158 carrier
candidate in screening but has not recovered 164x159; leave it off for the
qualified recipe above to avoid extra search cost without a demonstrated gain.

`benchmarks/carrier-166x156.floorplan.json` is a **trade-off candidate, not a
replacement for the retained carrier**. Using the original continuation recipe
without `--reseat-victim-shapes`, the initial build passed the full mandatory
pipeline at 25,896 mm² and an estimated cross-wire length of 15,822.8 mm, but
bringup_rails U1.24–C1.1 planar pad gap increased from 8.03 to 39.76 mm.
The quality-first selector now compares existing opposite-face pairs when
their owner/cap faces, pose, envelope, bulk gaps and fanout remain identical.
It reduces that gap to 17.38 mm (still bottom/top), with a 15,826.8 mm estimate
and another full mandatory-gate PASS. The bypass requirement still remains
UNVERIFIED; this is planar proximity, not proof of routed loop quality. Lower
aggregate area/wire length does not establish acceptable bypass placement.
See `benchmarks/2026-10-12-incoming-shapes-and-aspect-ratio.json` for the
qualification, unresolved trade-off and separately tested recovery change.
The subsequent selector correction and validation are recorded in
`benchmarks/2026-10-12-unchanged-face-planar-quality.json`.

The subsequent **two-pilot 166x156 candidate** passes the full mandatory
pipeline with bringup_rails U1.24–C1.1 at 6.8006 mm, bottom/bottom, while
preserving the five rounded board_aux proximity measurements of the retained
165x158 board. Reproduce with the continuation recipe above, replacing its
floorplan spec with `benchmarks/carrier-166x156.floorplan.json` and adding
`--owned-shape bringup_rails=bottom-a2.2/r270/owned-pins-forward`
and `--owned-shape board_aux=owned-face-a1.000000` (no victim-shapes option).
These are explicit experimental selections, not new mandatory shape rules.
The profiler's owned-selection trace now includes a read-only catalog of
registered, measured shape tags; registration does not imply board feasibility.
Evidence: `benchmarks/2026-10-12-two-pilot-carrier-qualification.json`.
This is 0.6674% less area than 165x158, but 1 mm wider; retain both incumbents.
Qualitative bypass/access requirements remain UNVERIFIED, and the three
existing advisory failures remain. No routing or fabrication readiness is implied.
Search caps, discrete shape portfolios and shrink-only refinement neighborhoods
are algorithm choices to challenge, not evidence of physical impossibility.
Next selection work must explore area-improving aspect-ratio trades and measured
pilot quality without requiring these hand-selected tags or relaxing hardware gates.

An additional multiscale aspect-trade stage was tested and **not retained**:
the original coarse search already discovers 166x156 from a 165x158 seed with
`benchmarks/carrier-two-pilot-auto.floorplan.json` and the two tags above.
The extra stage added 56 failed packing attempts with the same PCB. See
`benchmarks/2026-10-12-aspect-trade-screening.json` and its archived experiment
patch. This rejects redundant work, not alternative aspect ratios: portrait
156x165 and 152x168 probes failed at rail-group seating, not a proven physical
limit. Future algorithms need not preserve historical outputs, search ceilings,
or implementation choices. Historical boards remain comparison evidence;
acceptance rests on hardware correctness, quality, reliability and measured work.

Firmware source provenance now reads canonical circuit JSON and compiled factory
registrations rather than checking for Python constructors. Independent source
inventories cover both projects, reject damaged/missing registered inputs, and
remain identical in a Python-free fixture tree. Live contracts separately check
the new provenance and unchanged generated hardware logic.

`part-import --parts-root DIRECTORY --from-json FILE` converts recorded EasyEDA
responses entirely in C++; offline mode never calls a transport. Use `--lcsc ID`
instead for an explicitly online import, `--name NAME` to override the part name,
and `--overwrite` only when replacing existing files is intended. Catalog refresh
is separate and opt-in via `--catalog FILE`. Publication validates all targets
first and replaces each file atomically, but is not a multi-file transaction.
The native tests compare 62 recorded parts (three model variants each) byte for
byte, exercise the real offline CLI and reject malformed input, HTTP failures,
oversized/truncated responses, duplicate models and symlink output targets.

The native `pcb-stage --project NAME -o DIRECTORY` command now performs live
KiCad netlist extraction, immutable input loading, floorplanning, placement,
escape planning and PCB/project/rules emission. It is a construction stage,
not a replacement for the independent full-board gates. Live contracts compare
both project PCBs byte-for-byte with their existing generated references.
Native manufacturing contracts cover assembly planning, Markdown and all 52
reference PNGs. Assembly rendering uses at most four workers with stable output
ordering; a measured 38-image carrier run improved from approximately 0.97 s to
0.39 s, including transitional transport and file publication. This is an image
stage measurement, not an end-to-end board-build speedup claim.
The equivalent ratsnest run (36 PNGs plus SVG) measured approximately 1.79 s
through the previous renderer and 0.68 s through the bounded parallel C++
renderer, with all output bytes unchanged.

Standalone `assembly`, `ratsnest`, `si-constraints`, `fab-profile` and `manifest`
commands now use native implementations. Explicit output directories retain the
project layout (`docs/`, `renders/`, `manufacturing/`). `preflight` uses native
stock/price/alternate analysis and a shell-free HTTPS-only `curl` subprocess;
it requires network access only when that optional command is invoked. Transport
errors fail explicitly instead of being reported as a confirmed missing part.
Its offline contracts use injected provider responses and never contact vendors.

Remaining work is native source-purity/audit integration, standalone geometry
commands, final Python consumer removal and clean-tree full-board acceptance.
The standalone Python experiment scripts are retired; use `chir-rung`,
`w11-sweep`, `w12-bound`, `w12-stageprobe` and `dump-circuits` on the native CLI.
Independent native contracts retain captured reference logic and negative cases.

Each stage must preserve electrical connectivity and its relevant gates, then
compare generated artifacts against the established reference. Record measured
end-to-end performance separately from kernel benchmarks. Remove Python source,
bindings, and Python build dependencies only once their consumers have moved.
Final acceptance requires generating both supported projects and running their
verification from a clean build without Python; pre-existing failures must be
reported, not suppressed.
