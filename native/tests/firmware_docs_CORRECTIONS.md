# Bounded firmware documentation corrections — stable handoff

Only three existing files change:

- `native/src/firmware_docs_scfw.cpp`: remove the unsupported FMC EEPROM scan
  entry. The real hardware contract defines six baseline devices, not seven;
  `SC_I2C_DEV_COUNT` continues to derive from the actual emitted entries. Every
  address value resolves through the generated `zynq_carrier_contract.h`.
  No FMC address, replacement macro, conditional waiver, or hardware change is
  introduced.
- `native/src/firmware_docs_templates.hpp`: change only
  `manual_services_steps` from primary CR1220/charging OFF to rechargeable
  ML1220/charging enabled (TCE + approximately 3k series). Retain warnings against
  primary CR1220 and LIR Li-ion substitutions. This agrees with the existing
  board-services README, generated contract, and unchanged SC RTC implementation.
- `native/tests/firmware_docs_contracts.cpp`: apply exactly three guarded literal
  corrections to expected output: the conflicting manual paragraph, the phantom
  scan row, and the baseline count 7 -> 6. Full frozen mutant byte edits are
  applied first, then these explicit corrections, then whole-artifact comparison.
  Actual output is never normalized and expectations are not recomputed from it.

## Proof

The original implementation was first tested independently: 637 offline
assertions passed against its immutable legacy fixtures, and strict C11
compilation of its actual `sc_tables.c` failed on the documented undefined
`ZC_I2C_ADDR_FMC_EEPROM` identifier.

Corrected results:

- **1,070 offline assertions PASS.** Both board baselines and all twelve frozen
  mutation cases retain full output/error comparisons, with only the three
  explicit expected-output corrections above.
- **1,158 assertions PASS with `--live`.** This also exercises the real KiCad U9
  extraction and filesystem project loader for both boards.
- **54 generated portable-C translation units compile** with
  `cc -std=c11 -Wall -Wextra -Wpedantic -Werror -fsyntax-only`.
- **Nine linked generated-C address-map programs execute successfully**, checking
  every compiled table value against its actual generated contract. These cover
  the baseline, five compilable frozen mutants, and three additional live-input
  mutations: ID EEPROM strap 0x51 -> 0x50, INA3221 strap 0x41 -> 0x42, and removal
  of one monitor (device count becomes five). No baseline header is substituted
  for a mutant. Frozen SWD/address-collision cases intentionally reject contract
  generation; their complete surviving outputs and exact errors remain checked.
- SHA-256 comparison confirms **all 28 legacy fixture files unchanged**, including
  the historical defect report in `data/firmware_docs/README.md`.
- `git diff --check` passes. No checked-in generated artifact or hardware file
  was modified or regenerated. All generated test files reside in private scratch.

The corrected private executable is
`/private/tmp/firmware-docs-corrections.lDoQ2w/contracts`. Its original-output,
corrected-output, and live-output scratch directories are siblings under that
same private directory. C++ compilation used C++17, `-Wall -Wextra -Wpedantic
-Werror`, `-ffp-contract=off`, and the existing archive's macOS deployment target.

## Integration dependencies

No new translation units, module/CLI edits, loader fields, or CMake registration
are required. The template header change requires the normal recompilation of
`firmware_docs_manual.cpp`; the private proof explicitly compiled both that file
and `firmware_docs_scfw.cpp` before linking the existing archive.

The existing firmware contract test command remains
`firmware_docs_contracts REPOSITORY PRIVATE_SCRATCH [--live]`. It now requires a
real `cc` on PATH for mandatory generated-C compilation; there is no compiler
skip/waiver. The existing native process implementation provides shell-free
compiler execution. No production renderer invokes a compiler or subprocess.

The scaffold API/source/test handoff is separately frozen and unchanged by this
batch. All commits and shared builds belong to the parent.
