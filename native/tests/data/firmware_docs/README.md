# Firmware and bring-up migration contracts

This subgroup ports the decision logic from `schgen/generate/bringup_facts.py`,
`firmware.py`, `manual.py`, `testplan.py`, `scfw.py`, and `power_sequence.py`.
Production code never reads these fixtures, executes Python, changes the working
directory, or writes generated outputs. Hardware and HDL files are unchanged.

## Integration

Public APIs: `native/include/schgen/bringup_facts.hpp` and
`native/include/schgen/firmware_docs.hpp`.

Add these translation units to the core library:

- `native/src/bringup_facts.cpp`
- `native/src/firmware_docs.cpp`
- `native/src/firmware_docs_manual.cpp`
- `native/src/firmware_docs_testplan.cpp`
- `native/src/firmware_docs_scfw.cpp`
- `native/src/firmware_docs_power_sequence.cpp`

The private headers are `bringup_internal.hpp`, `bringup_unicode.hpp`, and
`firmware_docs_templates.hpp`. Unicode classification and decoding reuse the
verification subgroup's `verification_internal.hpp` and
`verification_unicode.hpp`. Fixed prose and portable-C source bodies are source
templates; they contain no frozen project-derived tables or lookup of fixtures.

`FirmwareDocsInput` contains caller-owned project circuits, an extracted STM32
map, and explicit firmware source provenance. `load_firmware_docs_input` is the
optional explicit filesystem/live-KiCad boundary. Firmware and manual renderers
return text; the SC renderer returns fourteen path/text artifacts.

The test-plan renderer accepts `SpiceResult` and a `ProjectStrings` probe index.
Join `check_testpoint_coverage(...).have` locations with `", "` to construct it.
The sequence builder accepts `PowerCheckResult` and `PowerPolicy`; its SVG
renderer accepts an explicit PASS/FAIL status. The parent owns publication,
CLI status/skip text, CMake registration, and transitional bindings.

## Standalone verification

Build `native/tests/firmware_docs_contracts.cpp` against the six translation
units and the existing core library, including the native spice implementation.
Use C++17 with `-Wall -Wextra -Wpedantic -Werror`. The test program takes:

```text
firmware_docs_contracts REPOSITORY_ROOT PRIVATE_SCRATCH_DIRECTORY [--live]
```

It changes its own working directory to the scratch directory to expose hidden
cwd dependencies. It publishes actual generated artifacts only under that
explicit scratch directory. `--live` also invokes KiCad for U9 and checks the
explicit project loader for both projects; the default contract run is offline.

The fixtures were captured from the six original generators before replacing
their implementation. `inputs.json` contains live U9 extraction, typed facts,
missing-input lists, analytic spice checks, probe locations, and power-tree
results. Full output artifacts are frozen separately. Both project baselines
are compared byte for byte, including PASS and FAIL SVGs. The native spice,
test-point and power-analysis joins must independently reproduce those outputs.

Verified on 2026-09-18: **721 assertions passed**, with `--live`, using a private
build at `/private/tmp/schgen-firmware-docs.NcItGx`. Both projects passed exact
output comparisons, all twelve frozen mutation cases, and the native analysis
joins. All six production translation units compiled with the strict C++17
flags above. Generated-C validation is reported separately below.

Carrier `mutants.json` stores nine independent legacy-generator cases: feedback
resistance, module current limit, shunt resistance, live GPIO, SWD drift, missing
expander sheet, changed expander address, address collision, and invalid monitor
strap. Byte edits reconstruct each **complete** expected artifact from its
baseline without recomputing expectations. Ordinary domain errors compare exact
messages. Missing required sheets use a descriptive native error in place of
Python's incidental KeyError; the ordered missing-sheet lists are unchanged.
The devkit fixture adds three independent frozen cases for GPIO changes, SWD
drift, and removal of the optional power sheet.

Additional contracts cover enable-net probes, floating EEPROM straps, EEPROM
address collisions, missing PD/watchdog/EEPROM parts, Unicode identifiers and
resistance values, optional test-plan sections, copied-input isolation, current
overloads, SVG escaping, and a reachable regulator cycle. The latter fails
explicitly; the original depth relaxation would never terminate on that input.

## Existing output defects retained and reported

These are not waivers or corrected hardware policies:

- The manual says CR1220 with trickle charging OFF, whereas the firmware
  contract and generated SC RTC code say rechargeable ML1220 with charging ON.
- The generated `sc_tables.c` references `ZC_I2C_ADDR_FMC_EEPROM`, which the
  firmware contract does not define. Its C11 syntax check fails with that exact
  undeclared-identifier error. The other five generated `.c` files pass strict
  C11 syntax checks. No replacement macro or compiler waiver is supplied.

The six Python source files, CMake, Python adapters, module registration and CLI
integration were intentionally not edited by this subgroup. Removing the legacy
files belongs to the parent integration after the complete migration passes.
