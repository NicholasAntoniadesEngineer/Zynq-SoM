# Tracked Python retirement inventory and independent SI-unit contracts

The original SI/inventory batch consists of these NEW files:

- `native/tests/si_units_contracts.cpp`
- `native/tests/data/retirement_readiness/tracked_python.json`
- this handoff

Parent subsequently approved the exact deletion plan in
`native/tests/data/retirement_readiness/approved_batch.json`: retire **389** of
the 393 tracked Python paths now, while preserving the four explicitly listed
build-twice/render/downstream-I2C/SI tests until their native proof/registration
is accepted. This is a plan only; this worker executed no deletion. The SI test
below is frozen for registration; the next approved new-only test closes the
downstream-I2C join. Parent owns the other two acceptance boundaries.

No production source, existing test, CMake, CLI, shared build, Python file or
previous oracle was changed. Previous regression/authoring/placement-metadata
files remain byte-identical to their accepted hashes. No commits or Python
processes were run.

## Complete bounded inventory

The JSON inventory maps **all 393 tracked Python files**, with individual source
SHA-256, role, native-family references and explicit exceptions. There are
**151 test modules**, **173 production modules**, **61 package entrypoints**, two
pytest infrastructure modules, two RC smoke helpers, two SoM generation tools,
one basis-audit tool and one CLI module. All 393 paths are unique and match the
sorted `git ls-files '*.py'` census exactly. The map names 48 native families and
126 existing evidence files. Snapshot HEAD:
`567621c9e75522a30e88a10e48537d6c29365f2d`; hashes describe its working-tree files.

Of the 151 test modules, 146 have existing native-family evidence, one Python
extension/import-only module retires with the extension, one gap is closed by
this SI test, and three carry explicit remaining join/acceptance/baseline work
below. This is a family-level retirement map, **not** a claim of a literal native
twin for every Python assertion or that pending parent acceptance has passed.

The inventory reuses port handoffs, immutable fixtures and native registrations.
Original tests were inspected selectively where mappings were ambiguous; the
entire redundant ported suite was not reread or executed.

Condensed mapping:

- 66 library/project subsystem test modules plus project-twin parity:
  fresh native authoring, independent complete IR oracles, invalid-meta/helper
  mutations and native-assets package gates. Literal Python module shape and
  textual twin-source identity disappear with those adapters.
- Model, symbols, netlist, schematic, route, pagination and part import:
  circuit/model/validation, symbols, schematic-place/route, netlist and importer
  contracts (including exposed-pad construction, not just part metadata).
- PCB, mirror, packing, stages, floorplan, compose, placement/flow and return
  checks: existing primitive/placement/emitter/gate families and precision
  fixtures. Fresh placement-metadata policy is the previous accepted batch;
  register it as planned. No geometry algorithm was duplicated here.
- Electrical, power, SI, procurement, firmware and outputs: verification,
  design-rules, SPICE, BOM/procurement, constraints/manufacturing, firmware/docs
  and rendering families; the new SI policy closes the research-unit join.
- Governance/ledger/purity/docs/CLI: native accounting and producer accounting,
  C++/AST/precision audits, authoring-boundary work, doc consistency, command help,
  regression and RC smoke. Other owners' pending registrations remain necessary.

There are **no tracked `scripts/*.py` or `tools/*.py`** among the 393 files.
The earlier chir_rung/w11/w12/dump utilities have native experiment-tools and
observer contracts, but ignored/cloud duplicates are outside this census and
are not deletion targets. `testplan.py` and `verify/testpoints.py` are correctly
classified as production modules, not tests.

## Remaining actionable work (do not disguise as a missing whole core port)

1. **Small I2C cross-consumer join** — `test_downstream_i2c.py`.
   Firmware/test-plan address and collision mutants already exist in
   `firmware_docs_contracts.cpp:377` onward. Manufacturing checks exact original
   manifest bytes (`manufacturing_contracts.cpp:59`), but that is not a dedicated
   fresh `board_services`-only join. Add a native test feeding one freshly
   authored circuit to `bringup_id_eeprom_addr`, `testplan_i2c_devices` and the
   manufacturing manifest. Pin EEPROM 0x51 / RTC 0x52, AUX bus/conditional flags
   and part identity, then rewire straps and require all consumers to observe
   the same address. No new production algorithm appears needed.
2. **Same-project double-build acceptance** — `test_build_twice.py`.
   `board_live_contracts.cpp` genuinely does live extraction -> native placement
   -> exact PCB and reports, once for each project; it is not merely schematic
   coverage. It does not build the *same* project twice in one process, the old
   global-state/race contract. Parent should add/run that acceptance after the
   coherent full-board audit is green, comparing dimensions and complete emitted
   bytes, without suppressing any live gate. Separately retain the module's
   warning-only thermal-evidence mutation: raising
   `PcbEmitPolicy::thermal_credit_needs` must change the shortfall diagnostics
   while leaving PCB bytes identical. Native `pcb_embed.cpp:180` consumes that
   policy and copper-debt tests mutate provenance; neither alone proves this
   specific output/diagnostic separation.
3. **Official render-baseline policy** — `test_render_baseline.py`.
   New native model/render fixtures and real KiCad views do not reproduce the
   original tracked-artifact union against `origin/master`, approved FUSB302
   model-repair normalization, PCB digest and zero-distance golden aHash bar.
   Preserve that as a native artifact policy contract, or obtain explicit
   approval for a new baseline if the historical baseline has been superseded.
   Do not silently equate a successful renderer with passing this policy.

These are evidenced uncovered **test boundaries**, not evidence that their
production implementations are still Python. The SI gap below was the highest
independent, cheap-to-run policy gap that could close here without entering the
parent's full-board/render acceptance or another owner's production source.

Final retirement also requires parent integration/green native CTest and actual
native `check` acceptance; this batch does not claim those. CMake now rejects
`SCHGEN_BUILD_PYTHON=ON`. Python lint/pytest configuration and requirements still
need parent cleanup with deletion. Both `scripts/build_native.sh` and
`scripts/check.sh` are already deleted in the current working tree. CMake builds
only C++; the old option is solely a fatal compatibility guard, not a Python
build branch. Native regression/selftest/RC/CTest replace the old check driver.
The remaining `native/tests/run_authoring_contracts.sh` and
`run_component_basis_contracts.sh` are private worker build recipes, not unique
production behavior or CTest dependencies: their subsystem-authoring,
authoring-gates, component-basis and copper-debt executables are registered
natively. They can retire with the old orchestration; preserve the C++ sources,
fixtures, CTest registrations and recorded sanitizer proof instead.
Do **not** delete the whole `schgen/` directory: native symbols still read
`schgen/lib`, and board checks still read `schgen/verify/data/lcsc_values.json`
and `nc_allowlist.json`. Preserve or explicitly relocate those non-Python assets.

## New SI coverage and independent expectations

The existing constraints/manufacturing tests compare immutable output bytes and
exercise missing research/impedance errors. The missing layer was the full
repository research-unit policy joined across *fresh native authoring* and all
three native consumers, from `schgen/tests/test_si_units.py`.

The new contract authors all 37 carrier circuits through the real registry and
catalog. It reads actual `carrier/research/si_spec.json`; it never loads saved
circuit IR, PCB snapshots or generated golden outputs. Independent literal
expectations are transcribed from the original test, not generated by C++:

- FMC 5 mil / 0.127 mm; MIPI 20 / 0.508; BASE-T 50 / 1.27;
  HDMI 118 / 2.9972; USB 150 / 3.81, with ten exact cited-net examples.
- HDMI's 0.15 bit-period fraction is not a length; one `diff_pair` kind carries
  three distinct budgets, precluding a kind-wide default.
- Group policy reuses the conservative pair skew, and actual heterogeneous group
  construction takes the minimum; SD remains the explicit uncited 2.5 mm policy.
- Zero single-ended maximum length requires an explicit `n/a` note.
- All 148 emitted pair rows carry the researched length and citation; both
  halves appear in the SI model, and each pair's own DRU condition and Markdown
  row carry the same physical length. Empty SI output cannot pass vacuously.
- Missing research is rejected by the real CSV generator and SI gate; impedance
  drift fails the real gate. Changed live research reaches all three consumers.

**49 negative mutations** exercise the independent research and consumer checks,
including uniformly wrong units across otherwise self-consistent outputs,
citations, missing rows/halves, model population, per-kind collapse, SD policy,
group minimum and dimensionless/length confusion. Copied mutations never alter
the original inputs. A heterogeneous 4-mil live row is a positive parameter
control, not permission to change repository policy.

Original Python AST literal-spelling assertions are not recreated against C++.
Their semantic no-default policy is exercised here; native via-cost literal-bit
and structured physical-provenance contracts remain in board-policy migration
and native audits. This adds no production validator, geometry or quantization
implementation.

Independent source hashes (unchanged):

```text
2b66c0a7cf0abc6c26b706d9a2bda8dcb4903341691de618fd58de7b0a974aff  schgen/tests/test_si_units.py
185ce61dc07aac0f96cdf8cddd86c55dee61af7b0938f0a796473d6bf626a0a4  carrier/research/si_spec.json
```

## Parent registration

```cmake
add_executable(schgen_si_units_contracts tests/si_units_contracts.cpp)
target_link_libraries(schgen_si_units_contracts PRIVATE schgen_core)
target_compile_options(schgen_si_units_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_si_units_contracts
    COMMAND schgen_si_units_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_tests_properties(native_si_units_contracts PROPERTIES TIMEOUT 120)
```

Exactly one argument: repository/input-tree root. Requires the actual native
part catalog, project mapping/interface data and researched SI JSON. Missing
inputs fail; no skip, fixture-fallback, external process or repository write.

## Isolated proof / source freeze

- **212 assertions, 49 rejected mutations PASS** with strict C++17.
- Same counts PASS with **ASan + UBSan**, all 61 repository translation units
  in the actual link-map closure instrumented, no uninstrumented core archive
  in that sanitizer executable. System LibXml2/OS libraries remain system code;
  no LeakSanitizer claim on this macOS host.
- Both strict and sanitizer binaries also PASS against a private **246-file
  asset tree containing no `.py`, `.pyc` or `.so`**, with every canonical
  `circuit.json` deliberately invalid. That proves fresh native circuit
  provenance without deleting anything in the checkout.
- Current repository headers pass a separate strict `-fsyntax-only` check.

Proof directory: `/private/tmp/native-si-retirement.PuFQ4a`.
Executables: `si-strict`, `si-asan`; reproducible private `build-asan.sh` and
`strict.map` retained. Python-free poisoned input:
`/private/tmp/native-si-assets.LPr9ZJ`.

Strict linking used the accepted private frozen core archive from the previous
authoring/metadata proof, SHA-256
`e26211c85bc7434300e96d5f0be26db2fa71998f32aaf2ffdf26eda9e8832786`.
Sanitizer linking reused that proof's instrumented source snapshot objects and
compiled its additional constraints/manufacturing-SI closure privately. This is
not a claim to have rebuilt the concurrently edited shared authoring core;
parent's next coherent build remains the integration check.

Flags: `-std=c++17 -O1 -g -Wall -Wextra -Wpedantic -Werror -ffp-contract=off`;
sanitizer adds `-fsanitize=address,undefined -fno-omit-frame-pointer`.
Runtime: `ASAN_OPTIONS=abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1`.

Frozen new test SHA-256:
`48429a6fcf695d773f3291e29629f5097d371935d42475dc75a9509fead23d4f`.
Inventory SHA-256:
`86679c056141c5e2899184036652fe2d9586ece0a6e4c79459453cacd5241b38`.
