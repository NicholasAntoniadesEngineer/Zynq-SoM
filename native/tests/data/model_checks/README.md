# Native model verification family

This is the complete data/model layer of `powertree.py`, `thermal.py`,
`ratings.py`, and `part_rules.py`, including reports, power-tree SVG, waivers,
and explicit report publication. It has no interpreter, authoring-module,
symbol-library, catalog-global, or implicit project-path dependency.

## Public interfaces and integration

Add these three sources to `schgen_core` (the shared analytic helper is
header-only):

- `native/src/power_checks.cpp`
- `native/src/thermal_checks.cpp`
- `native/src/part_checks.cpp`

Public declarations are in the corresponding `native/include/schgen/*_checks.hpp`
headers. Existing core dependencies are `CircuitSheetIr` / `ProjectCircuit`,
`JsonNode`, s-expression parsing, atomic-file publication, and the shared decimal
rounding kernel. Compile with `-ffp-contract=off`, as for the other migrated
analytical/geometry code. No CMake, module, CLI, or Python edits were made in
this batch.

The principal calls are:

```cpp
#include "schgen/power_checks.hpp"
#include "schgen/thermal_checks.hpp"
#include "schgen/part_checks.hpp"

auto power = schgen::analyze_power(sheets);
auto thermal = schgen::analyze_thermal(sheets, power, copper, evidence_source);
auto parts = schgen::analyze_part_rules(sheets, power);
```

`sheets` is `const std::vector<ProjectCircuit>&`; each caller-owned sheet name
is authoritative and need not equal its circuit's internal name. `copper` is
`const ThermalCopper*`, null when no scan is available. Inputs are never
modified, reloaded, or reparsed through canonical file-validation gates.
Policies and ratings can be passed explicitly as immutable typed metadata;
default policy tables are native, read-only, ordered copies of the old source
tables, including all citations and limits.

Both thermal and part analysis have overloads that compute power when omitted.
The overload accepting a `PowerCheckResult` **never recomputes it**. An edited
or independently constructed caller result remains authoritative. The same is
true of the optional power pointer supplied to the `run_*_checks` wrappers.

`detect_power_regulators(sheets, policy)` returns only `regs`, detection
`errors`, and `bridges` in a `PowerCheckResult`. Regulator `i_in`/`i_out` remain
zero and every other result field stays empty. It does not visit loads, tally
rails, assess budgets or run audits; it can replace the private Python detector
used by SPICE without paying for or changing behavior via full analysis. Its
outputs have separate frozen Python detector comparisons for every case and
both projects.

Default voltage expressions are compiled once and reused by **pattern content**,
not policy address. Copies, reordered patterns and changed voltage values still
retain first-match behavior. Nonstandard expressions use the explicit custom
policy fallback. Anchored/end-of-string and one-terminal-newline semantics are
covered, including the exact `+5V_SOM` rule ahead of generic `+5V`.

Bindings can use these symmetric data transports without duplicating analysis
or report formatting:

- `power_result_json` / `power_result_from_json`
- `thermal_result_json` / `thermal_result_from_json`
- `part_result_json` / `part_result_from_json`
- `thermal_copper_json` / `thermal_copper_from_json`

They preserve dataclass field names, map/list order, explicit numerical values,
notes, and verbatim waiver reasons. The strict inverses reject missing/unknown
or duplicate fields, wrong tuple lengths/types, nonfinite numbers, invalid
integer/count fields, and malformed nested records. They do not infer missing
values. `ok`, `over`, and `poured` remain derived properties, not transport keys.
`part_ratings_from_json` accepts the data-only `RATINGS` object, never a module;
unknown rating keys are ignored as before, absent/null optional fields use the
old defaults, and supplied typed fields are validated.

`power_report`, `thermal_report`, and `part_rules_report` return text without a
final newline, as before. `power_svg` returns exactly one final newline. The
`run_*_checks` wrappers publish reports with one final newline using explicit
destinations; power SVG is published to the explicit docs directory. Thermal's
wrapper also accepts an explicit repository root for relative evidence-path
display; an absent/nonexistent board withholds every pour credit.

The command-line orchestration, project discovery, and Python adapters belong
to the integration layer, not these algorithms. `copper_debt` source-anchor
analysis and its broader reporting are outside this family. Only the emitted
zone/via/footprint/net collector and thermal-credit queries have been ported.

## Frozen independent oracle

The fixtures were captured from preserved, unmodified Python verification
modules, with Python 3.14.3. The native analyses under test did not generate
their expected results. All relevant circuit IR and emitted copper evidence is
frozen; tests never read changing live project circuit/board outputs.

- `circuits.json`: all 49 current canonical circuits at capture time (37 carrier,
  12 devkit), including values, fields, pin aliases, ordered nets/loads, and
  waivers. Future inventory changes do not change these fixtures.
- `projects.json`: both complete project results, reports, and SVGs, each with
  and without the actual emitted-board copper evidence. Copper scans retain
  all zone, via, footprint/pad and net evidence used by the model.
- `cases.json`: 118 independently captured cases, including all individual
  frozen sheets and targeted mutations: missing regulator pins/inductor hops,
  alias resolution, last-match ISET/inductor selection, ILIM failures,
  regulator/source overruns, zero loads, rail orientation and deferrals,
  reachable/unreachable cycles, pre-contract capacitance and slew, SoM rail
  conflicts, rating gaps, advisory resistor power, stress and thermal waivers,
  missing/partial/mirrored/keepout copper, and all-instance credit withholding.
- `copper_cases.json`: 10 complete emitted s-expression scanner snapshots and
  their per-policy credit decisions. These include quoted/unquoted atoms,
  last reference property, single/multiple layers, numeric/oval drills,
  net definitions after vias, unknown net numbers, and non-xy polygon children
  that the baseline collector accepts.
- `policies.json`: every LCSC ratings row, SI/resistance parser goldens, voltage
  precedence, Unicode digits/whitespace, invalid values, and source hashes.

In addition, the C++ contract independently exercises caller-edited power
results, separate sheet identity, immutable inputs, last-wins/unused waivers,
explicit policy overrides, zero-efficiency diagnostics, transport round trips
and rejection cases, inclusive Euclidean via radius and pour-bbox boundaries,
front/back layer swapping, file parsing, exact publication bytes, absent-board
credit withholding, and explicit repository-root path handling.

All numeric fixture comparisons use **exact double equality**, not tolerances.
All report and SVG comparisons are byte-for-byte, including order and newline
semantics. Golden tests at the exact 10 uF inlet boundary and a cancellation/
rounding boundary require Python's compensated floating-point `sum` behavior;
plain left-to-right accumulation gives a different policy decision there.

Preserved source SHA-256:

- `powertree.py`: `a22c89263dbd4db60c5b8e8212f868654524165a893a1f19283bbdaeb0c57e67`
- `thermal.py`: `cf25773849e07f311fedeadf54e7ccc5d8eb21faf2fa6be52aa3aac8247ac863`
- `ratings.py`: `82a19036664ca27c2f9666d7c0965b960a336c6da919f1353691bd8e830f7eed`
- `part_rules.py`: `3704f31eb3cdea566a0d4e0f1992b7d1ba809e72a65e7e7ca99888c87b67b268`
- `copper_debt.py`: `0c2ee5cb1f8bc0f2baac63bd1e2a2b15cfe8dec22b370575b90c3b6833f12f68`

## Policy boundaries deliberately preserved

No hardware limits or specifications were guessed or upgraded. In particular:

- Power-tree findings do not become errors; thermal unspecified devices do not
  fail that gate; part rules fail on findings but not advisory/unspecified rows.
- Bridge discovery retains the existing two-POWER-net incidence rule, even
  though its report calls them series resistors. Ambiguous bridge orientation
  and unsourced/deferred semantics are unchanged.
- Rail voltage is still first-match name policy, not inferred from geometry or
  net class. Buck input budgeting keeps its 0.90 policy; thermal keeps 0.85.
- Pour credit requires the existing filled GND plane, via count/radius and
  local layer bounding boxes. It does not claim polygon-area, electrical
  connectivity or complete thermal-layout validation. One insufficient
  matching instance withholds that prefix's credit, matching the old model.
- Resistor parsing intentionally retains `M` as milli and the old `/10`
  infix fractional rule (`4k70` means 11 kOhm there). SI parsing has different
  semantics. The advisory threshold remains **greater than 2x** rated power.
- Every cited default thermal/rating/current limit and author waiver remains
  unchanged. Unknown data stays unknown rather than gaining a guessed rating.

One intentional termination improvement: rendering a source-reachable regulator
cycle throws `ModelCheckError` instead of looping forever in the SVG depth
relaxation. Analysis still reports the same cycle results/errors. Publication
computes the SVG before replacing either power artifact, so that error cannot
leave a newly published partial result.

## Verification and standalone build

Both strict Release and a fully instrumented ASan/UBSan build passed **96,508
checks**. All builds and generated test outputs were isolated in temporary
directories; no shared CMake build or board generation was run.

CTest integration: link `native/tests/model_checks_contracts.cpp` to
`schgen_core` and invoke the executable with the repository root argument:

```sh
model_checks_contracts /absolute/path/to/Zynq-SoM
```

Standalone equivalent, from the repository root:

```sh
clang++ -std=c++17 -O3 -DNDEBUG -ffp-contract=off \
  -Wall -Wextra -Wpedantic -Werror -Inative/include \
  native/tests/model_checks_contracts.cpp \
  native/src/power_checks.cpp native/src/thermal_checks.cpp \
  native/src/part_checks.cpp native/src/circuit.cpp native/src/json.cpp \
  native/src/atomic_file.cpp native/src/sexpr.cpp native/src/occupancy.cpp \
  native/src/quantize.cpp -Wl,-dead_strip -o /private/tmp/model_checks_contracts
```

For the sanitizer run, replace `-O3 -DNDEBUG` with
`-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` and compile **all**
listed sources with those flags. The executable itself allocates an isolated
temporary directory for publication tests and removes that directory on success.
