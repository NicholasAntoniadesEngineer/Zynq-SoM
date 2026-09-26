# Native component basis and copper provenance

Worker scope: new audit sources, native contracts and authoring adapter cleanup.
Parent owns CMake, module, CLI, catalogs, shared builds and commits.

## Parent integration

Add exactly these new sources to `schgen_core`:

* `src/component_basis.cpp`
* `src/component_basis_registry.cpp`
* `src/copper_debt.cpp`

Use strict C++17 and `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`.
No third-party dependency, subprocess, Python interpreter or source parser is
needed by these production sources. Existing thermal/PCB/authoring core APIs
are reused. Do not add `circuit_helpers.cpp` or other authoring sources again.

Transitional extension: include `schgen/authoring_audit_bindings.hpp` in module.cpp
and call `schgen::bind_authoring_audits(m)` once. The header reuses existing
thermal/emitter policy transports; it does not register those bindings twice.
It exposes `component_basis_policy`, `component_basis_inputs`,
`component_basis_audit`, `copper_debt_scan`, `copper_debt_analyze`, and
`copper_debt_report`.

Add contract executables from `tests/component_basis_contracts.cpp` and
`tests/copper_debt_contracts.cpp`, linked to schgen_core. Both take one argument:
the absolute repository path. Register as CTest tests with the same strict
flags. The worker-only runner `run_component_basis_contracts.sh` builds private
executables against a copied archive; `AUTHORING_AUDIT_UBSAN=1` instruments the
new audit sources and contracts without modifying shared binaries.

## Native pipeline calls

Open the current part catalog through the normal explicit boundary. Build the
66 live circuits using `author_component_basis_inputs(repository)`, or supply
caller-owned `ComponentBasisInput {scope, sheet, circuit}` records.
Call `audit_component_basis(inputs)`; a false `ok()` must fail the component
basis gate. Publish `component_basis_report(result)` if desired.

The scopes library/carrier/devkit_mini are independently manifested. Missing,
extra or duplicate sheets fail. For a selected scope, pass its explicit set;
include every sheet expected by that scope. No empty/unrecognized-scope PASS.
The default registry contains 214 declarations and 685 expanded obligations.
The obligations are independent of the authoring functions: changing a builder
does not silently update its expectations.

For copper provenance, `author_copper_debt_sources(repository)` creates the live
global claim universe plus native policies. Before analysis, replace matching
project circuits with the actual IR sent to netlisting, and supply the actual
board's `ThermalPolicy`, `PcbEmitPolicy`, and researched differential geometry.
Do not overwrite caller edits by reloading circuit snapshots.

Scan actual output with `scan_thermal_copper(pcb_path)`, then call
`analyze_copper_debt(&scan, sources)`; a null scan preserves UNMEASURED status.
`CopperProvenanceError` is a hard provenance failure; emitted/partial/nothing
debt remains report-only. Write `copper_debt_report(result) + "\n"` to the normal
report location using the pipeline's atomic publication helper.

This is a global claim ledger: a claim can describe a component absent on one
board (e.g. FMC on devkit). Its native library/project definition is still
verified, and the actual PCB scan determines the reported copper evidence.
The provenance never searches C++ strings or trusts a source filename as proof.
Native claim lines are diagnostic source links only.

## Compatibility and rollout

The parent has integrated the sources, contract targets and extension bindings.
The Python adapters now use them: native component basis replaces the default
repository census, and native copper scanning/analysis/reporting replaces the
production Python ledger. Explicit custom-Python-package source census and
`_where` helper APIs retain compatibility for existing callers/tests; neither
is a fallback after native failure, and standalone gates never call them.
Public Python component constants/registrations remain API-compatible.
The 64 inactive constructor/helper bodies (2,044 lines) have been removed
without deleting their modules or changing immutable fixtures.

Parent-owned Python CLI wiring: change the ledger call to
`copper_debt.run(rep_dir, _pcb_file, sheets=sheets)`. The optional `project=`
argument identifies the project scope when it differs from PROJECT_ROOT.name.
The entire supplied project replaces its native default scope, so missing/extra
sheets cannot be concealed by filling gaps from factory defaults. Mutations in
the actual netlisted connections are verified before copper reporting.

Copper report titles, assumptions, statuses, emitted evidence, risks and
inventory remain Python-equivalent. Native source locations and the provenance
introduction intentionally change, so both copper_debt reports and their
manifest hashes need the parent's normal artifact-validation/commit workflow.

## Current stable handoff

The native audit suites pass 1,936 component-basis and 1,522 copper-debt
contracts with strict C++17 and again with UBSan. Binding-header syntax was
checked with the same warning policy. All three fixture hashes are unchanged.
Audit adapters and legacy-constructor cleanup are now implemented and tested.

The separate twin-parity fix is ready: all 43 Python project adapters obtain
`PROJECT` from their owning project's basis module, whose key is derived from
its own file location. Detached gate copies retain their owner through that
import; their asset root still comes from the adapter's own location.
No process-selected project or original-root fallback is used.

Ten actual source twins retain the original verbatim parity check. Power,
debug_boot and power_mon deliberately differ between boards and now have
complete independent pre-migration IR comparisons instead of a false claim of
source identity. Equivalent fixture checks also cover the shared circuits.
The post-cleanup authoring suite passes 991 existing focused tests: all library
and project package tests, twin/variant parity, detached adapters, Circuit
model/IR/meta helpers, structure, component basis, copper and thermal gates.
New `schgen/tests/test_authoring_native_audits.py` covers every original library
parameter case through both dict and Meta transport, all 49 project circuits,
eight dynamic connector cases, live registration/constant/component drift,
actual netlisted connection edits and policy drift. It also proves production
audits do not call the retained Python-source compatibility helpers.
No board artifacts were rewritten. Use fresh pytest processes after import
changes; a process that cached the old basis module lacks its PROJECT export.
