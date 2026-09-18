# Schematic emission contracts

These are byte-for-byte Python emission snapshots. `cases.json` contains the
complete circuit IR, placed design, immutable symbol trees, ordered symbol pins,
emission options, expected instance metadata, and 209 UUIDv5 reference vectors.
The adjacent `.kicad_sch` files are the expected output, including final newlines.
The native tests do not require Python or a KiCad library installation.

The baseline was captured from `schgen/output/emit.py` with SHA-256
`cbb6f6cc3e5a934d8f609d69f839c4c53f554e29b0cdb5443bbe648c1df8f655`.
Each case also records its golden SHA-256. The temporary baseline generator and
its frozen Python source were retained in `/tmp/schgen-schematic-I8bmrP` during
the migration; no Python test/generator was added to the repository.

- Synthetic fixtures cover every placed primitive, input ordering, embedded
  symbol sorting, non-unique/empty pin numbers, unknown circuit references,
  footprint precedence, Datasheet/custom-field ordering, power value visibility,
  explicit/default text positions, rotations, numeric rounding, escaping, UTF-8,
  standalone/hierarchical labels, and independent root/symbol/sheet instance paths.
- `empty` covers the empty design and empty project name.
- `m1-rc` is the existing `schgen.tests.m1_rc.build()` design.
- Carrier fixtures are actual `Circuit.from_ir(circuit.json)` designs placed and
  routed with `place.place_and_route`: `board_qwiic`, `power_som`, and `som_j1`.
  No board build or shared output was produced to generate them.

Run the native executable with this directory as its sole argument. An optional
`--emit-dir TEMP_OUTPUT_DIR` writes native outputs for independent KiCad checks.
Tests also exercise the typed API, placement JSON validation, immutable library
trees, resolver call order, and UUID independence from unrelated primitive kinds.
