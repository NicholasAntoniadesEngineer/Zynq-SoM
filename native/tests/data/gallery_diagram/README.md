# Gallery and block-diagram native handoff

## Scope and source provenance

New files only:

- public APIs: `native/include/schgen/gallery.hpp`, `native/include/schgen/diagram.hpp`;
- implementation: `native/src/gallery.cpp`, `native/src/diagram.cpp`,
  `native/src/gallery_diagram_internal.hpp`;
- contracts: `native/tests/gallery_diagram_contracts.cpp` and this fixture directory.

The native implementation owns the complete SVG layout, edge aggregation,
routing, label placement, serialization, Markdown rendering, render discovery,
README splicing/publication, and gallery command-summary formatting. It reads
live typed inputs/canonical JSON, not committed diagrams, frozen expected
outputs, Python sources, interpreter state, or subprocess results. No Python
deliverable, CMake/module/CLI edit, shared build, or commit is part of this slice.

`load_gallery_input(paths)` uses the existing native canonical circuit JSON
loader; `load_gallery_input(paths, project_circuits)` reuses an already loaded
native design. It consumes current names/titles, render-file presence, and
wired-sheet configuration. It never executes retained authoring files or
opens/compiles a circuit catalog. `render_block_diagram` consumes the existing
native `LinkResult` and `LinkSomNets`: bindings, targets, rails, and unbound ports.

Output bytes deliberately retain the original gallery prose about passed
gates, and the original diagram's "Zynq carrier" title even for devkit_mini.
Those strings are presentation, not new gate results. Integrators must retain
existing gate/build ordering; these document APIs do not certify a board.

## Parent integration

Add exactly these production sources and compile without FP contraction
(Python's layout expression evaluation must remain separate):

~~~cmake
target_sources(schgen_core PRIVATE src/gallery.cpp src/diagram.cpp)
set_source_files_properties(src/gallery.cpp src/diagram.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")

add_executable(schgen_gallery_diagram_contracts tests/gallery_diagram_contracts.cpp)
target_link_libraries(schgen_gallery_diagram_contracts PRIVATE schgen_core)
target_compile_features(schgen_gallery_diagram_contracts PRIVATE cxx_std_17)
target_compile_options(schgen_gallery_diagram_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_gallery_diagram_contracts COMMAND schgen_gallery_diagram_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/gallery_diagram"
    "${CMAKE_CURRENT_BINARY_DIR}/gallery-diagram-contract-output"
    "${CMAKE_CURRENT_SOURCE_DIR}/..")
~~~

The contract makes a unique child under its output parent, so repeated/parallel
CTest runs do not overwrite one another. Its only repository reads are canonical
JSON/project inputs and frozen fixtures; generated output goes to that child.

Native gallery command body, after native project resolution/loading:

~~~cpp
const auto input = schgen::load_gallery_input(paths, project_circuits);
const auto changed = schgen::write_gallery(input);
std::cout << schgen::gallery_summary(input, changed) << '\n';
return 0; // only after successful publication
~~~

Or call `generate_gallery(paths)` if the command does not already hold circuits.
The default project updates root README first, then project README; other projects
update only their own README. Sections have no trailing newline; new README
publication adds one exactly as before. Outside-marker text and unchanged raw
CRLF bytes survive. Publication is atomic per file, not a multi-file transaction.
Absent README parent directories remain an error.

For the native link command/pipeline, reuse its existing linker result and
parse the same selected contract into `LinkSomNets`:

~~~cpp
const auto som_nets = schgen::link_som_nets_from_json(contract_json);
schgen::write_block_diagram(link_result, som_nets, diagram_output_path);
~~~

`diagram_output_path` is the existing selected override path, or
`paths.project_root / "docs/block_diagram.svg"`. Rendering completes before
directory creation/publication, so render failure preserves an existing file.
In-memory `render_block_diagram`, `render_gallery_full`,
`render_gallery_compact`, and `splice_gallery` are available for bindings.
The parent owns replacing Python bodies with thin native transport adapters.
No Python sorting, layout, arithmetic, or Markdown construction is needed.

Dependencies are existing core APIs: project/circuit JSON loading, linking,
atomic publication, occupancy's `py_round`, and the tracked Unicode decimal
classification header `native/src/bringup_unicode.hpp`. The test additionally
uses existing `pcb_sha256` to enforce fixture integrity.

## Independent immutable Python oracle

`python.json` was captured before adding native renderer sources. Expected
SVG/Markdown/splice bytes came from the unmodified Python modules. The native
linker supplied real graph inputs only, never rendered expected output.
Gallery discovery used canonical circuit JSON and captured filesystem listings;
original Python sorting, filtering, formatting, layout, and splicing functions
generated every expectation.

It contains:

- nine diagrams: carrier, devkit_mini, empty graph, isolated Unicode sheets,
  all roles/edge kinds/highways/deferred ports, input permutation, XML escaping
  and dominant-kind ties, crowded split columns, duplicate peer/self-loop;
- seven galleries: both real projects, empty, mixed/missing thumbnails,
  all board views, nested/external project paths, and ratsnest-only sheets;
- twelve splices: missing/empty files, trailing newlines, ASCII/Unicode whitespace,
  existing/unchanged markers, CRLF, missing/reversed/multiple markers.

`SHA256SUMS` pins exact fixture bytes. Recorded source hashes:

- `schgen/output/diagram.py`:
  `96df41b7b38155bd83f24f52f9cabfbb97e7c13a1efa3c13b3b6d392bf755f77`;
- `schgen/generate/gallery.py`:
  `a90652b7f8bc9563ddde694eb0429d93a5732dd15e677a8f8f28f71889c3bc1d`;
- `schgen/core/artifacts.py`:
  `1704d19cce83fc328f9325e9fe06165722c632bbc54b3c43e35d1718456f8771`.

All three hashes still match; no Python source was changed or delivered.

## Verification and reproduction

Final result: **136 checks, zero failures**, strict optimized C++17 and full
ASan+UBSan. Carrier and devkit_mini also pass live native
JSON loader -> linker -> SVG and JSON loader -> gallery -> README paths with
exact frozen bytes. Separate clones contain canonical JSON only: no authoring
Python or catalogs. Fresh typed graph/circuit mutations change output.
The executable passes with `PATH=/nonexistent`; linked libraries contain no
Python runtime.

Additional checks cover changed-path ordering and summary text, idempotent
publication, Unicode decimal sync-duplicate filtering, dangling SoM-image
handling, lazy wired-sheet configuration, invalid UTF-8 rejection, and
render/missing-parent failure preservation.

Artifacts: `/private/tmp/gallery-diagram.Lb98LY`. From repository root:

~~~sh
(cd native/tests/data/gallery_diagram && shasum -a 256 -c SHA256SUMS)
doc_build=$(mktemp -d /private/tmp/gallery-diagram-contracts.XXXXXX)
clang++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off \
  -mmacosx-version-min=26.6 -O3 -g -I native/include \
  native/src/gallery.cpp native/src/diagram.cpp \
  native/tests/gallery_diagram_contracts.cpp native/build/libschgen_core.a \
  -lxml2 -pthread -o "$doc_build/contracts"
PATH=/nonexistent "$doc_build/contracts" native/tests/data/gallery_diagram \
  "$doc_build/output" /Users/nicholasantoniades/Documents/GitHub/Zynq-SoM
~~~

For the fully instrumented run, compile the complete linked project closure
explicitly before the archive:

~~~sh
clang++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off \
  -mmacosx-version-min=26.6 -O1 -g -fsanitize=address,undefined \
  -fno-omit-frame-pointer -I native/include \
  native/src/gallery.cpp native/src/diagram.cpp native/src/occupancy.cpp \
  native/src/quantize.cpp native/src/json.cpp native/src/circuit.cpp \
  native/src/atomic_file.cpp native/src/project.cpp native/src/project_catalog.cpp \
  native/src/link.cpp native/src/pcb_checks_escape.cpp \
  native/tests/gallery_diagram_contracts.cpp native/build/libschgen_core.a \
  -lxml2 -pthread -Wl,-map,"$doc_build/asan-link-map.txt" \
  -o "$doc_build/contracts-asan"
ASAN_OPTIONS=halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  "$doc_build/contracts-asan" native/tests/data/gallery_diagram \
  "$doc_build/asan-output" /Users/nicholasantoniades/Documents/GitHub/Zynq-SoM
~~~

The deployment flag matches the supplied macOS archive; omit it on Linux.
The sanitizer link map confirms no uninstrumented project archive objects were
pulled in. No shared CMake/build/catalog/module output was touched.
