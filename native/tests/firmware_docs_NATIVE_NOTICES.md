# Native firmware notices: frozen handoff

This follow-on to `06224ad2` changes four existing files only:

- `src/firmware_docs_templates.hpp`: replace Python regeneration instructions
  and authored-source citations with the actual native CLI, C++ implementation
  files, and canonical `circuit.json` files. Each regeneration notice states
  that commands run from the repository root and `PROJECT_DIR` is a project-path
  placeholder. Preserve hardware prose, including the committed ML1220/charging
  correction. Manual prose points to the hardware contract's builder inventory.
- `src/firmware_docs_manual.cpp`: replace the one remaining `power.py` citation
  in the generated PG-LED explanation with `power/circuit.json`.
- `src/firmware_docs_scfw.cpp`: use the supplied `FirmwareDocsInput` provenance
  in all twelve portable SC file headers, retaining relative references to the
  generated hardware contract and staged manual. Native regeneration text uses
  the already-integrated `firmware_native_regeneration_command("scfw")` API.
- `tests/firmware_docs_contracts.cpp`: migrate expected bytes through explicit
  independent literal replacements. Canonical source comments use the separately
  reviewed, committed `data/firmware_provenance/*_sources.txt` inventories.
  Assertions check exact occurrence counts, complete generated artifacts, and
  every surviving output/error from all twelve frozen mutant cases. Expected
  mutant byte edits run before reviewed corrections; actual output is never
  normalized and production templates are never used as an expectation oracle.

## Verified snapshot

Before editing, current committed sources passed 1,160 assertions with `--live`,
including 54 strict C11 compilations and nine executed address maps. The default
`build/libschgen_core.a` still contained the old Python-based discovery, so the
private proof explicitly compiled current firmware/provenance sources over that
archive; it did not rebuild or mutate any shared artifact.

Final private executable:
`/private/tmp/firmware-native-notices.s3AufY/contracts`.

Run:

```sh
/private/tmp/firmware-native-notices.s3AufY/contracts \
  /Users/nicholasantoniades/Documents/GitHub/Zynq-SoM \
  /private/tmp/firmware-native-notices.s3AufY/final --live
```

- **1,788 assertions PASS**, both boards and live KiCad U9 extraction.
- **1,698 offline assertions PASS** against the same immutable fixtures.
- **54 generated C11 translation units compile** with
  `-std=c11 -Wall -Wextra -Wpedantic -Werror`.
- **Nine generated address-map programs execute**, verifying every scan-table
  address against its same-input generated hardware contract.
- A supplied-source mutation checks all twelve portable SC headers and the
  hardware header, proving source provenance is not hard-coded to the carrier.
- All generated artifacts and frozen mutant outputs reject remaining `.py`,
  `PYTHONPATH`, or `python -m` references.
- SHA-256 comparison confirms all **28 legacy fixture files unchanged**.
- `git diff --check` passes. No hardware, canonical circuit, checked-in generated
  document, source registry, public API layout, or shared binary was changed.

C++ compilation uses C++17, `-Wall -Wextra -Wpedantic -Werror`,
`-ffp-contract=off`, and `-mmacosx-version-min=26.6`. The private executable
compiles the contract test, `firmware_docs.cpp`, `firmware_docs_manual.cpp`,
`firmware_docs_scfw.cpp`, `firmware_docs_testplan.cpp`, and
`firmware_provenance.cpp`, then links the existing archive, libxml2 and pthread.

## Parent integration

No CMake, module, CLI, registry, loader, or public-ABI edit is needed.
Recompile all users of `firmware_docs_templates.hpp` normally; do not reuse
objects containing earlier prose. The test command is unchanged. All generated
proof outputs live in the private directory above; checked-in generated docs
have deliberately not been republished. Existing firmware sources/tests are
were frozen through the parent's successful clean-first build and remain
unchanged at this handoff.

## Read-only follow-on inventory

Concrete remaining edges found by tracing Python entry points and native code:

- `schgen/__main__.py:cmd_nets` still generates `carrier/nets.py` from the SoM
  contract and live POWER-class `+` rails. No native constants-header renderer or
  publication command was found. Native circuit/SoM loaders already exist;
  reuse them, preserve identifier/collision behavior explicitly, and generate
  C++ rather than another Python file.
- `_purity_violations` in that same file bans subsystem geometry imports and
  definitions/bindings of `placer`. Native authoring is implemented, but no
  equivalent source-boundary validation was found. Quantization/ledger syntax
  audits cover different rules and must not be mistaken for this policy.
- `schgen/tests/test_doc_consistency.py` still owns authored DESIGN_SPEC and
  COMPLIANCE validation: real rail names, mandatory rails/interfaces, existing
  sheet citations, and diagram references. Native power/sequence analysis
  already exists; the missing family is document validation, not another power
  solver. Native manufacturing currently lists those files in the manifest
  without performing these content checks.
- `schgen/tests/test_cli_help.py` requires successful per-subcommand `--help`.
  Native main has top-level help, but the project-command parser rejects
  `--help`. Parent-owned CLI integration is required; no parser edits made here.
- `cmd_check` is still a Python subprocess driver for board, selftest, M1 RC,
  and pytest. Native board/selftest/M1 and CTest contracts exist; remaining work
  is orchestration, already reserved to parent/Zeno, not a missing core.
- `scripts/dump_circuits.py` still explicitly publishes canonical JSON using
  Python constructors. Native authors and `authored_circuit_json` already exist;
  publication policy/CLI is an authoring integration edge for Copernicus/parent.

Do not duplicate active experiment-observer, verification-audit, part-import,
compose, rendering, or board-pipeline work. This is a bounded inventory, not a
claim that every Python test assertion already has a native equivalent.
