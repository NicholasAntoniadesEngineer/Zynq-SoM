# Native symbol contracts

`python_metadata.json` is a frozen comparison against the unmodified
`schgen/core/symbols.py` authoring loader. It covers every distinct part library
ID in all 37 carrier and 12 devkit circuit JSONs, plus power/ground/flag symbols
used by schematic placement. It records ordered pin metadata, body bounds,
visibility, canonical raw-expression fingerprints, and page transforms.

`kicad/` contains the selected upstream symbol blocks from the installed KiCad
libraries used to capture that baseline. These are test snapshots, not a new
production symbol library. The default contract run uses them before installed
KiCad paths for reproducibility. Generated part symbols and `schgen` rail
templates are read from the repository itself. Run with `--installed` to test
the actual installed KiCad libraries against the same frozen baseline.

The baseline does not resolve `extends`. Inheritance therefore has separate
explicit contracts in `SymbolContracts.kicad_sym`: child property overrides,
inherited custom properties and empty overrides, renamed nested units,
unchanged physical pins and graphics, cycle/missing-parent rejection, and
rejection of child drawing overrides. This follows KiCad's same-library
derived-symbol model:
https://dev-docs.kicad.org/en/file-formats/sexpr-intro/index.html#_symbols

All tests are C++; the fixtures are data. Running them does not execute Python,
generate a board, alter project files, or use a precompiled part/circuit catalog.
Temporary cache/error fixtures are created below the system temp directory.
