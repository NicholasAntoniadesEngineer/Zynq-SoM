# Frozen verification-family contracts

Captured 2026-09-18 from the original Python `bom_values.py`,
`footprint_pads.py`, `pin_completeness.py`, and `symbol_law.py`. Exact source
SHA-256 hashes are in `manifest.json`; captures used copies in `/tmp`, not
native outputs. The 18 cases include canonical carrier/devkit IR, exact
reports and every result field, and board mutations for wrong declared BOM
values, removed symbol connections, removed footprint pads and forbidden
schgen-local real-part symbols. Expected records must not be regenerated
when production boards change.

The capture contains 67 actual resolved symbol definitions, real resolved pad
sets, catalog and NC allowlist data. Tests never reload project source files
or require installed KiCad libraries. The original Python tests' normalization,
LCSC C25750 poison/correct/unknown cases, silent-float and NC seed/new behavior
are retained. The suite adds ordering, unknown NC numbers, repeated pending
symbol IDs, 195 parser vectors, inclusive tolerance, Unicode/multiline/empty
pad cases, strict direct-child power tags and resolver exception propagation.

The initial standalone result is 18 frozen cases + 195 normalization vectors,
1,814 exact checks (including filesystem resolution/report contracts), passing
both release and fully instrumented ASan/UBSan builds. Carrier baselines:
354 BOM checks, 502 completeness checks,
564 resolved footprint checks. Devkit: 106, 136 and 158 respectively. Both
boards pass; each targeted mutation fails its intended check.

Run without a shared CMake build:

```sh
clang++ -std=c++17 -O1 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off \
  -I native/include native/tests/verification_contracts.cpp \
  native/src/bom_values.cpp native/src/pin_completeness.cpp \
  native/src/footprint_pads.cpp native/src/symbol_law.cpp \
  native/build/standalone/libschgen_core.a -o /tmp/verification_contracts
/tmp/verification_contracts native/tests/data/verification
```

APIs accept ordered `ProjectCircuit` sheets (symbol law accepts circuits),
explicit typed catalog/allowlist/pending policy and native library or resolver
inputs. No Python fallback, semantic IR parser, project reload or gate waiver
is embedded. Report writers take explicit directories and preserve final LF.
Footprint resolution remains dossier -> fp-lib-table -> installed library ->
one alias hop. Unresolved footprints and catalog entries remain non-failing;
pin completeness still sets `ok=false` on floats despite its legacy
REPORT-FIRST report wording. Only `SymbolError` is caught by symbol-law power
lookup; arbitrary exceptions are not swallowed.
