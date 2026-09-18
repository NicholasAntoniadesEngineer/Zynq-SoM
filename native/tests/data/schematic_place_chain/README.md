# Frozen placement-chain contracts

These 161 cases were captured on 2026-09-18 from the original Python
`schgen/layout/place.py` (SHA-256
`a9cee65a32d8e9ba3872d22bc0892e04ede9acb44232b54aa9661dbdc923091e`),
before its adapter replacement. The frozen oracle was loaded from a `/tmp`
copy, never reconstructed from native chain output. Existing expected records
were retained when later synthetic cases were added. Do not regenerate these
expectations when a board design changes.

The fixtures include all 36 nonempty carrier and 11 nonempty devkit core
circuits after splitting probes/mounting holes, plus expanded spacing and
focused rail/passive stacks, straps, pull ranks, pin dividers, rung islets,
orientation restoration/ties, missing-part rejection, pin lookup errors,
tip-group boundaries, channel jogs/wrapping and hidden/duplicate pins. The
standalone symbol snapshots contain the actual 94 resolved definitions and
three synthetic definitions. No installed KiCad library or live project IR
is used by the test. Synthetic all-passive multi-pin symbols also have
explicit shunt-list mutations to exercise the channel path independently
of the default classifier; initial and final state record that injection.

The harness compares complete initial/final Engine state and method results:
all placement primitives, ordered plans/boxes, orientations, counters,
classification tables, chains, trunks, deferred text and diagnostics. Numeric
coordinates are compared exactly, with no tolerance. Python assertion/index
errors become `SchematicPlaceError` with the same message; expected error
cases also compare the partially mutated state. No production gate waiver
or success fallback is installed.

Run the parent-integrated executable with this directory as its sole argument
(an optional second argument selects case names by substring):

```sh
schematic_place_chain_contracts native/tests/data/schematic_place_chain
```

Independent compilation, without editing CMake or building a shared module:

```sh
clang++ -std=c++17 -O1 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
  -ffp-contract=off -I native/include \
  native/tests/schematic_place_chain_contracts.cpp \
  native/src/schematic_place_chain.cpp native/src/schematic_place_core.cpp \
  native/src/schematic_place_fanout.cpp native/src/schematic_place_templates.cpp \
  native/src/symbols.cpp native/src/sexpr.cpp native/src/json.cpp native/src/circuit.cpp \
  native/src/atomic_file.cpp native/src/occupancy.cpp native/src/quantize.cpp \
  native/src/turn.cpp native/src/pack.cpp native/src/place_search.cpp \
  native/src/place_geom.cpp native/src/pcb_scan.cpp native/src/seat.cpp \
  native/src/legalize.cpp native/src/emit.cpp native/src/embed_fp.cpp \
  -o /tmp/schematic_place_chain_contracts
```

For the instrumented run, replace `-DNDEBUG` with
`-g -fno-omit-frame-pointer -fsanitize=address,undefined`; instrument all sources.
The chain source implements every chain-seam Engine method and `Engine::run()`
from `schematic_place_internal.hpp`; it introduces no additional public API.
