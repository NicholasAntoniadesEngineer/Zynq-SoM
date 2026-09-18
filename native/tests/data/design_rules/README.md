# Design-rule and testpoint coverage contracts

Frozen 2026-09-18 from the original Python algorithms. Do not regenerate expected
results when canonical designs change. No Python runtime fallback is involved.

## Fixtures

- `contracts.json`: 56 named policy cases and 219 power-pin vectors, including the
  three real STM32 cases from `schgen/tests/test_design_rules.py`.
- `carrier.json`: all 37 canonical sheets, ordered symbol pins, complete results
  and report text; eight individual physical I2C pull-up removal expectations.
- `devkit_mini.json`: all 12 current canonical sheets, pins, complete results and
  reports; two pull-up and nine individual probe removal expectations.
- Each board fixture retains all source IR metadata and source SHA-256 hashes.
  Every removal fails exactly its intended I2C/coverage gate.

Original Python source hashes:

- design_rules.py: `48f47a75f87b96689e4daffa963b18baba13d7cb9fd72724c6e42c7ecc4e2cec`
- testpoints.py: `d9d518db1c5dad294ed8bf71ca973ff7305f643b56a939a5fccc851058b3818e`

Only coverage/report, not testpoint geometry, is in scope. Capture scripts and
original source copies are in `/tmp/schgen-design-rules-RLXYai`. Its supplemental
`fuzz.json` has 420 seeded differential cases; `classifiers.json` covers 854 pin
names, 1176 net names and 2694 Unicode power-name vectors. All properties,
collection ordering and report bytes matched. Repository JSON files are exact
copies of captured originals, and tests never regenerate them.

## Standalone build and verification

Run from the repository root (no shared CMake/module build):

```sh
clang++ -std=c++17 -O2 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
  -ffp-contract=off -pthread -I native/include \
  native/tests/design_rules_contracts.cpp native/src/design_rules.cpp \
  native/src/circuit.cpp native/src/json.cpp native/src/atomic_file.cpp \
  native/src/symbols.cpp native/src/sexpr.cpp native/src/occupancy.cpp \
  native/src/turn.cpp native/src/quantize.cpp \
  -o /tmp/schgen-design-rules-contracts
/tmp/schgen-design-rules-contracts native/tests/data/design_rules
/tmp/schgen-design-rules-contracts native/tests/data/design_rules --live "$PWD"
/tmp/schgen-design-rules-contracts native/tests/data/design_rules --live "$PWD" --benchmark
```

Default tests need neither Python nor KiCad libraries. `--live` additionally
loads current canonical JSON through the production parser and uses native
SymbolLibrary, then repeats every mutation. It requires normal symbol libraries
but performs no schematic/board generation. `--corpus <json>` adds a captured
differential corpus. Replace `-O2 -DNDEBUG` with
`-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined` for sanitizers.
Release/NDEBUG assertions remain active; release and ASan/UBSan runs passed.

After parent binding integration:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -o addopts='' -q \
  -p no:cacheprovider schgen/tests/test_design_rules.py
```

## API and semantics

`schgen/design_rules.hpp` declares `check_design_rules`,
`check_testpoint_coverage`, result/report/JSON helpers, and `DesignRuleIndex`.
Inputs are typed CircuitSheetIr plus supplied SymbolDefs or a resolver. Coverage
needs no symbols. No core file reload, semantic parser, catalog or interpreter.
The immutable index owns input snapshots and supports concurrent reads. Rebuild
it after mutations. Reports have no trailing newline. Vector maps preserve Python
insertion order. Coverage's legacy `extras` field remains unused by reporting.

Each library ID resolves once. Ordinary resolver exceptions retain the old
unresolved-symbol skip; std::bad_alloc, std::system_error and non-std exceptions
propagate. Pin-copy/index/report allocations occur outside the compatibility
catch. Tests cover missing symbols, runtime/cast-style failures, resource/system
errors, resolver lifetime, source mutation, copied indexes and concurrent reads.
Python adapters must likewise preserve cancellation/resource/system exceptions.
UnnettedTestpoint maps to Python StopIteration; its native diagnostic identifies
the sheet/ref. Coverage failure is deferred and cannot alter design-only checks.

Preserved policy details include sheet-local decoupling, board-wide I2C/reset RC,
ground names rather than classes for bypass/EP, POWER-class I2C opposite rails,
any resistor for reset, sheet-local strap drivers, all symbols for EP checks,
waiver precedence and verbatim reasons, duplicate symbol pin styles, first-net
resolution and lexical output order. Unicode 16.0 property ranges reproduce
Python decimal/digit/printable behavior without locale/ICU dependencies.

Model part metadata and ratings/datasheet helpers were inspected. Completeness
does not gate resistor/capacitor values or LCSC ratings: those remain separate
part-rules checks. No rating assumptions, waivers or weakened gates were added.

## Representative timing evidence

Local macOS arm64, clang C++17 -O2, Python 3.14. Measurements include both checks,
exclude fixture parsing, report formatting, binding overhead and board generation.
Cleared symbol cache means process symbol caches, not the OS file cache.

- Supplied-pins fresh index/check medians: carrier 1.325 ms, devkit 0.4117 ms.
- Reused index/check medians: carrier 0.0344 ms, devkit 0.00913 ms.
- Native cleared symbol cache + fresh Library/index/checks: 334.238 / 183.133 ms
  (carrier/devkit, five samples). Warm Library + fresh index/checks:
  1.3122 / 0.4149 ms (101 samples).
- Frozen Python gate with the same native-backed Library: cleared cache + fresh
  Library/checks 413.248 / 231.966 ms (five samples); warm Library/checks
  12.1548 / 1.8597 ms (101 samples).

Index timing medians use 101 samples. Cold symbol loading remains dominant;
these numbers are not full-build speed claims. Replacing general regex dispatch
with equivalent finite classifiers reduced measured native fresh-index medians
from 5.465 / 1.956 ms while preserving the full differential results.
