# Native schematic placement contracts

The core is the bounded foundation of the full placement migration, not an
alternative board generator. `schematic_place.hpp` reserves typed public entry
points; `schematic_place_internal.hpp` shares the Engine with the fanout,
templates, chain and pages translation units. End-to-end entry points must not
be advertised until all those slices are implemented and validated.

## Frozen independent oracles

- `classifications.json`: all 49 project circuit snapshots at capture time,
  with complete canonical input IR, the explicit excluded auxiliary references,
  and Python Engine classification outputs in insertion order. This covers
  135 multi-pin parts, 72 rail clusters, 98 pull groups, 97 hang groups,
  42 remaining series legs, 52 trunks, 15 shunts and 43 floating chains.
  These are provenance counts, not assertions against the changing live boards.
- `primitives.json`: operation sequence and complete emitted primitive/box/plan
  state; 25 symbol/rotation geometry cases; collision/extent/band queries;
  initial spacing and eight successive expansions. Includes negative angles,
  half-rounding boundaries, empty/single-point paths, NC/value-label avoidance,
  generated rail symbols, and hidden power values.
- `chains.json`: 13 focused Python `_linearise` results/errors covering end
  priority, stable tail ordering, ground hangs, reversed port straps, cycles,
  dangling internal nets, extra legs and shared trunk-chain ownership.

Placement source SHA-256:
`a9cee65a32d8e9ba3872d22bc0892e04ede9acb44232b54aa9661dbdc923091e`.
The preserved pre-adapter Python symbol loader has SHA-256:
`6865dc11b46fdd51d9495dafbf3aa9f473743d819bbe71763a8b34c7dba140bc`.
It was loaded from an external temporary baseline during capture. Fixtures
reuse `../symbols/kicad` frozen symbol blocks, repository-generated part
libraries, and `schgen/lib` rail templates. No installed KiCad is required.

The complete primitive/helper/spacing fixture was additionally replayed with
all geometry native branches disabled: original Python symbol loader and pin
transform, `sexpr._loads_py`, Python textmetric functions, and the independent
`_stem_dir_py` from `44b76af6^:schgen/layout/route.py`. Every value matched exactly.
No C++ result is used to manufacture an expected placement value.

An explicit diagnostic improvement is recorded in `chains.json`: a chain with
only ground ends still fails, but reports `no rail/pin end` instead of the
baseline's accidental `KeyError('gnd')`. Duplicate typed-IR part/net names also
fail explicitly; first pin ownership otherwise retains Python `setdefault`
semantics. No source/structure gate is bypassed.

## Integration and execution

Add `schematic_place_core.cpp` to the existing native library and compile it
with `-ffp-contract=off`. Link `schematic_place_core_contracts.cpp` against that
library, then run `schematic_place_core_contracts <repository-root>`. Neither
the future `Engine::run` nor the page entry points are used by this executable.
It tests exact doubles, complete ordered records, error messages, repeat
classification, caller-IR snapshot isolation, and stable shared/index handles
through 1,024 container insertions. It never dereferences invalidated vector
references. Later workers must copy shared pointers by value or reacquire
OrderedMap values after insertions; deferred parts use indices.

Standalone macOS build used while the shared outputs were busy:

```sh
clang++ -std=c++17 -O3 -DNDEBUG -ffp-contract=off \
  -Wall -Wextra -Wpedantic -Werror -Inative/include \
  native/tests/schematic_place_core_contracts.cpp \
  native/src/schematic_place_core.cpp native/src/symbols.cpp \
  native/src/sexpr.cpp native/src/turn.cpp native/src/occupancy.cpp \
  native/src/quantize.cpp native/src/pack.cpp native/src/place_search.cpp \
  native/src/seat.cpp native/src/circuit.cpp native/src/json.cpp \
  native/src/atomic_file.cpp -Wl,-dead_strip -o /path/to/temp/contracts
```

`-dead_strip` excludes unused helper-kernel functions in this ad hoc link; it is
not required when linking the complete native library. The same source set is
also tested with `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer`.
No repository Python files, shared build outputs, catalogs, or boards are
created or modified by the contracts.
