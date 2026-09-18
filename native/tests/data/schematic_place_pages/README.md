# Native schematic pages

`schematic_place_pages.cpp` implements the complete page layer from the frozen
Python placement baseline: auxiliary split, test-point/mounting-hole rows,
translation, A4 centering, Engine build, expanded-spacing retries, native routing
and visual validation, A3 promotion, signal islands, metadata-preserving subset,
greedy bin packing and congestion-only pagination. Public entry points take
`CircuitSheetIr`, `SymbolLibrary` and `SchematicSpacing`; they never run Python,
read authoring sources or supply manually placed board geometry.

## Fixtures and independent coverage

`pages.json` records:

- Auxiliary order, split snapshots and signal islands for all 49 circuits
  frozen in `../schematic_place/classifications.json`. The live inventory may
  change without invalidating this deterministic baseline.
- Five probe-row cases: ordinary horizontal, tall vertical, exactly 244 mm
  horizontal boundary, previously exported port and initially empty core.
  Complete placements before/after centering cover ground/chassis ground,
  power, SIGNAL, duplicate PORT probes and mounting holes.
- Exact translation of every primitive/text/box/path field at rounding ties.
- Subset metadata and ordering, greedy-fit call order and bins at four size
  budgets, exact SIGNAL-cut diagnostic and structural/congestion markers.

`full_pages.json` records real `build` and `place_and_route` results for five
cases: a probe-only PORT sheet, passive cluster, and the frozen devkit
mechanical, power_som and USB-UART connector circuits. Contracts call the
complete public C++ entry points and compare every placement primitive, box,
ordered plan, routed segment, junction, paper selection and geometry field.
All five also pass the actual native visual gate. The probe-only case exercises
the public pagination entry point and must retain its hierarchical label.

The unchanged Python page/Engine algorithms were the fixture oracle, using
the preserved pre-adapter Python symbol library and frozen KiCad symbols from
`../symbols/kicad`. Probe-row and transform capture explicitly used Python
textmetrics/geometry and the Python s-expression parser, with native geometry
branches disabled. Full-page capture used the previously validated router and
visual gate; native page decisions and placements were not used as expected
values.

Source SHA-256 values:

- `place.py`: `a9cee65a32d8e9ba3872d22bc0892e04ede9acb44232b54aa9661dbdc923091e`
- `testpoints.py`: `505c536d68fe73c7e9d17c361157599e64646b3b7e765450f88d32c71e8dbc3c`
- Preserved Python symbols: `6865dc11b46fdd51d9495dafbf3aa9f473743d819bbe71763a8b34c7dba140bc`

The C++ test also independently exercises retry order and budgets, propagation
of non-placement errors, exact inclusive A4/A3 bounds, A3 routed-coordinate
rounding and refreshed geometry, zero/negative attempt counts, failure summary
selection, no-split rethrow, and real native routing for an all-auxiliary sheet.
Internal `PageOperations` permits deterministic failure injection for policy
tests without replacing `Engine::run`. Public entry points unconditionally
supply the real native build/router/visual gate; no production fallback exists.

## Integration and boundary semantics

Add `schematic_place_pages.cpp` beside the core/fanout/templates/chain sources in
`schgen_core`, with `-ffp-contract=off`, and link
`schematic_place_pages_contracts.cpp` to that library. Run:

```sh
schematic_place_pages_contracts /absolute/path/to/repository
```

Release (`-O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror`) and fully instrumented
ASan/UBSan (`-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer`) each
passed 95,094 checks. Builds/executables were isolated below the system temp
directory. The sanitizer run compiled all linked C++ dependencies with matching
instrumentation; mixing instrumented libc++ vector templates with a prebuilt
uninstrumented archive is not a valid container-poisoning test.

Page operations preserve caller-owned typed IR without canonical re-parsing.
`split_auxiliary` intentionally retains empty nets, NC and metadata records,
matching the intermediate Python snapshot. `subset_page` keeps selected PORT
metadata verbatim even if its differential mate lives on a different page.
SIGNAL nets cannot be cut; that is a structural exception, not retryable
congestion. The only intentional empty-input diagnostic improvement is an
explicit placement error when no geometry exists to center/size, rather than an
accidental Python `min()`/`max()` exception.

An adapter must distinguish shape-preserving in-memory transport from strict
canonical circuit-file semantic validation. Do not discard port/NC/waiver/load
metadata to force intermediate circuits through the canonical loader. For
Python `Library.paths`, use the exact ordered `SymbolLibrary(vector<path>)`
constructor; the repository-root overload intentionally adds search defaults.
