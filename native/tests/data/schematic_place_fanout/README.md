# Native placement fanout contracts

`cases.json` freezes 86 independently computed geometry/error cases, including
their complete circuit IR and initial placement state. The three KiCad symbol
libraries here are synthetic, fixed geometry inputs; no installed KiCad library,
live project design, Python interpreter, or Python source is needed to run them.

The expected results were captured from the original pure-Python placement
implementation, not from the migrated fanout code. Reference capture and source
snapshots remained outside the repository under `/private/tmp`. Provenance:

- `schgen/layout/place.py` at commit
  `44b76af6fd59572ec9fe324a0bace49f6a109448`, blob
  `7a9bb64f4e1e9e0c34dd3903b720672713befdf2`;
  SHA-256 `a9cee65a32d8e9ba3872d22bc0892e04ede9acb44232b54aa9661dbdc923091e`.
- Original symbol and S-expression readers from commit
  `15f4f83d3e8dde012606c9565e4dd0e18cec40c4`; respective blobs
  `1a61c062110fd1d8aa44fccf740b9e819c583569` and
  `f92e1cc0f3211cf718c3cc229fa1c64acda3db39`.
- Capture explicitly disabled the native placement helper dispatch and selected
  the pure reference pin transformation, text measurement, box intersection,
  S-expression parser, and stem-direction implementations.

Coverage includes all four body rotations, hidden/coincident pins, NC ordering,
two-pin orientation and polarity, text fallback, label electrical types,
handled pins, internal runs, staggered fanouts, power/GND single and multi-pin
runs, rail combs/buses/stubs, pull-ups, capacitive hangs, dividers, inline series
parts, complete/deferred cells, stacked passives, left/right chain features,
trunk collection and construction, ladder rungs, obstacle escape and exhausted
searches. Invalid attachment, non-two-pin placement, duplicate attachment,
single-tap trunk, and blocked rail/lane diagnostics are exact ordered contracts.

The runner compares ordered records, plan vertices, labels, symbol instances,
bounding boxes, consumed jobs, deferred text state, and exception text.
Only numeric comparisons permit an absolute tolerance of `1e-9`; strings,
container sizes and array ordering are exact. Tests use explicit runtime checks,
so `-DNDEBUG` does not disable verification. No cases are skipped on errors.

## Integration

The existing internal `Engine` API is unchanged. Add
`src/schematic_place_fanout.cpp` to `schgen_core`, with `-ffp-contract=off`.
Link the completed core, template and chain translation units together. Fanout's
chain-owned dependencies are `_side_tips`, `_on_net` and `_rung_islet_drop`;
template-owned dependencies are `_glabel_len`, `_power_at` and `_needs_flag`.
All are implemented in the sibling translation units; no substitutes are needed.

Add executable `schgen_schematic_place_fanout_contracts` from
`tests/schematic_place_fanout_contracts.cpp`, link it to `schgen_core`, and register
the test with the single argument
`${CMAKE_CURRENT_SOURCE_DIR}/tests/data/schematic_place_fanout`.
Run it as:

```sh
schgen_schematic_place_fanout_contracts native/tests/data/schematic_place_fanout
```

Standalone temporary build, from the repository root (does not touch shared
build outputs):

```sh
fanout_build_dir=$(mktemp -d /private/tmp/schgen-fanout-XXXXXX)
clang++ -std=c++17 -O2 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
  -ffp-contract=off -I native/include \
  native/src/schematic_place_core.cpp native/src/schematic_place_fanout.cpp \
  native/src/schematic_place_templates.cpp native/src/schematic_place_chain.cpp \
  native/src/symbols.cpp native/src/sexpr.cpp native/src/occupancy.cpp \
  native/src/seat.cpp native/src/quantize.cpp native/src/turn.cpp \
  native/src/place_search.cpp native/src/place_geom.cpp native/src/legalize.cpp \
  native/src/pack.cpp native/src/pcb_scan.cpp native/src/emit.cpp \
  native/src/embed_fp.cpp native/src/circuit.cpp \
  native/src/json.cpp native/src/atomic_file.cpp \
  native/tests/schematic_place_fanout_contracts.cpp \
  -o "$fanout_build_dir/fanout_contracts"
"$fanout_build_dir/fanout_contracts" native/tests/data/schematic_place_fanout
```
