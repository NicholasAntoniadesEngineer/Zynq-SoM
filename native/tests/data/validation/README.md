# Validation contracts

Run `schgen_validation_contracts REPOSITORY_ROOT` for the electrical and visual
contracts, or add `--electrical` to run only the electrical contracts. The CTest
entry is `native_validation_contracts`. The executable writes no project outputs
and requires no Python interpreter, precompiled catalog, or schematic emitter.
Real-project checks use the installed KiCad symbol libraries plus the repository
symbol paths resolved by `SymbolLibrary`.

The electrical census covers all 37 carrier and 12 devkit circuits. Each part is
resolved from its actual symbol; every unique library pin, including hidden and
multi-unit pins, must be connected or explicitly NC. Coverage is reconciled with
the source JSON connections and NC declarations. Actual pin tables are never
inferred from incomplete IR metadata. Missing symbols are fatal. Driver checks
retain all seven Python driver etypes and the POWER/GROUND/PORT exemptions.
Caller-edited invalid NC pins and cross-net ownership also fail completeness.

`Validation.kicad_sym` exercises all driver types, non-drivers, hidden pins,
multiple units/styles, repeated pin numbers with different etypes, pinless
symbols, malformed pins, and symbol geometry errors. Negative tests also remove
connections from real inline-symbol parts whose IR pin tables are empty.

`visual_cases.json` records complete ordered findings for every gate stage and
the owner/label/junction exceptions. Additional C++ contracts exercise all five
text kinds, numeric boundaries, geometry errors, and required box identity.
The public `SheetGeometry` uses page-space millimetres and has no emitter
dependency. Supplied boxes must have finite ordered bounds and nonempty kind
and owner; wires must be finite, orthogonal, nonzero-length, and name their net.
Malformed geometry throws `ValidationError`; valid geometry preserves Python
gate behavior, including errors for same-net crossings and wire overlaps.

The retained regression artifacts are the frozen `visual_cases.json` data and
the C++ contracts. No Python reference or runtime fallback is included in this
fixture directory. The original visual gate used for differential testing is
recoverable from Git with this provenance:

- Source: `schgen/verify/visual_gate.py`
- Commit: `7dfe953e6457be5aac62ade28bc8e20f77f8a43d`
- Git blob: `25b3f8be2f1258751cc784b0de69d27d4f724056`
- SHA-256:

```text
a4a1e32db440732d461be96290905db79bba5aff2648ad2263af106aefbd4b3e
```

For independent differential testing, extract that revision into an external
temporary directory, load it under a unique module name, and replace
`Box.intersects` with
`Box.intersects_py`, and `_cross`, `_collinear_overlap`, `_point_on_seg`, and
`_foreign_t_touch` with their `_py` counterparts. Compare its `check()` result
against the binding `check_visual_geometry(box_rows, wire_rows, junction_rows,
clearance)`. This compares Python predicates and complete finding order against
the native implementation. The migration was checked on the 27 fixtures,
10,000 deterministic randomized sheets (seed `0x5C4E2026`), 14 epsilon cases,
and six decimal formatting cases: 10,047 exact matches. External differential
scripts and source snapshots are not required by the native contract suite.

Integration uses `validation.hpp` and `validation.cpp`, linked to the existing
symbol and geometry implementations. `validate_circuit(sheet, library)` is the
throwing completeness gate used before link. `check_inputs_driven` is separate,
as in Python. `check_circuit_electrical` combines both with per-part coverage.
`check_visual_geometry` returns `VisualResult` and its Python-compatible
`summary()`. It checks supplied geometry; it does not perform placement/routing
or replace the separate connectivity and KiCad ERC gates.
