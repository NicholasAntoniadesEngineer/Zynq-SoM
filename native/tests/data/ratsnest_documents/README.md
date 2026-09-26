# Native ratsnest documents: contracts and integration

This slice replaces the rendering and publication logic in
`schgen/generate/ratsnest.py`, not the already-native MST or ratsnest gate.
The parent owns main CMake, CLI, module bindings, Python adapters and commits.
No existing manufacturing implementation/header was edited for this slice.

## Parent integration

Add exactly these three translation units to the existing core target:

```cmake
target_sources(schgen_core PRIVATE
    src/ratsnest_documents.cpp
    src/ratsnest_images.cpp
    src/ratsnest_raster.cpp)
set_source_files_properties(
    src/ratsnest_documents.cpp
    src/ratsnest_images.cpp
    src/ratsnest_raster.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
```

They use the existing `pcb_model`/`pcb_checks_model` geometry, `ratsnest.cpp`,
`ratsnest_gate.cpp` (`ratsnest_net_pad_positions`), `legalize.cpp` (MST), numeric
formatting/rounding, and atomic-file APIs. No new external dependency is needed
beyond the proven `schgen::manufacturing_compression` target already used by
assembly. Its explicit installed prefix must contain zlib-ng 2.3.3 in compatible
mode; retain the existing helper/probe and never substitute stock zlib.

`ratsnest_raster.cpp` reads the reusable glyph atlas in
`manufacturing_assembly_font.hpp`. It does not include or call an assembly stage
renderer. Raster/PNG primitives remain local in these new files while the parent
integrates assembly; there is no ownership conflict or dependency on unpublished
assembly wrappers. A future shared-raster extraction must retain both families'
exact independent contracts.

Include `schgen/ratsnest_documents.hpp` in the parent-owned callers:

- `ratsnest_palette(sheets)` corresponds to `_palette`.
- `ratsnest_airwires(model, nets, edges, optional_side)` corresponds to `_airwires`.
- `render_ratsnest_svg(model, palette, nets, edges)` corresponds to `_svg`.
- `render_ratsnest_board_image(model, palette, side, nets, edges)` corresponds to
  `_png`; it returns filename, PNG bytes and dimensions without publishing.
- `render_ratsnest_sheet_image(model, sheet, refs, nets, edges, som_refs)`
  corresponds to `_png_sheet`, also as a pure byte renderer.
- `render_ratsnest_subsystem_images(model, nets, edges)` returns the sorted
  per-subsystem images, excluding `som_*` sheets and appending the combined SoM
  image if present. Returned sheet filenames start with `ratsnest/`.
- `render_ratsnest_images(...)` returns top, bottom and all subsystem images.
- `render_ratsnest_documents(model, optional_nets, optional_edges)` computes the
  complete document/image bundle and length/count metrics. Omitted inputs use
  current placed-model geometry and the existing native MST. Supplied inputs are
  validated and used without silently recomputing them.
- `run_ratsnest_documents(model, project_root, optional_nets, optional_edges)` is
  the actual production wrapper. It renders first, publishes
  `renders/ratsnest_top.png`, `renders/ratsnest_bottom.png`,
  `renders/ratsnest/*.png`, and `docs/RATSNEST.svg`, then removes stale regular
  `.png` entries only inside the dedicated subsystem image directory.
- `ratsnest_document_summary(publication, repository_root)` returns the exact
  three-line CLI output, including its final newline. Paths must be underneath
  the specified repository root. Exit success only after the actual wrapper
  succeeds; propagate publication/render failures.

Publication is atomic per file, not a multi-file transaction. All rendering and
destination-directory creation precede file writes, and stale cleanup happens
only after successful writes. A later disk/write failure can leave a mixture of
old and newly published complete files, so callers must not report success.

## Independent reference and output coverage

`reference.json` was captured before native renderer implementation, from the
original Python `ratsnest.py` and Pillow 12.2.0. It includes source SHA-256s.
The capture explicitly used the retained Python S-expression parser, footprint
bounds, transforms, pad positioning and Manhattan MST reference, not the new
native renderer. Inputs are immutable `pcb_emit` model/footprint snapshots;
synthetic mutation models and footprint bytes are embedded here.

The contracts check:

- Both projects: exact palettes, SVG bytes by SHA-256, Euclidean length/count
  metrics, complete image inventory, dimensions, decoded RGB hashes and PNG
  byte hashes. Carrier has 36 images; devkit_mini has 11.
- Five frozen mutation models: base, no-module, side/rotation change, upstream
  change and empty board; 34 PNGs and five SVGs in total.
- An independent raster-only probe with 30 lines: all octants, horizontal,
  vertical, diagonal, degenerate lines, clipped endpoints, fractional inputs,
  widths one/two and translucent overlap.
- `summary.json`: the original Python CLI formatter on the independently
  captured mutation results, including the zero-length case.
- Live pose/origin and supplied-graph mutations; individual/aggregate image
  API agreement; actual publication, exact persisted bytes and scoped cleanup;
  failed-render/write preservation; invalid dimensions/coordinates, missing
  geometry/nets, out-of-range edges, duplicate refs, unsafe names, colliding
  SoM filenames, empty/unknown sheet selection and allocation/text bounds.

Both fixture files have SHA-256 pins enforced by the executable. Expected PNG
or RGB hashes are never recalculated from native output, and production reads
none of this test directory. No native code invokes Python or a subprocess.
The one-shot capture script and original rendered diagnostic artifacts remain
only under `/private/tmp/ratsnest-documents.ziE1Rd/`; no Python file was added
to the repository.

Intentional hardening/generalization beyond the legacy renderer: unsafe path
segments and ambiguous `som.png` collisions fail; duplicate/unresolved refs and
nonfinite inputs fail before publication; unsupported control-character labels
fail rather than silently changing text layout; SVG text escapes XML markup;
the board origin comes from the placed model rather than fixed global 25 mm
constants. Default project output remains byte-identical. The legacy redundant
mounting-hole filter is preserved semantically: holes are still drawn only on
their actual side, not both sides.

### Pixel arithmetic compatibility

The two-pixel RGBA lines follow Pillow's polygon scan-conversion, including
single-precision slope arithmetic and asymmetric half-pixel tie rounding.
The reference arm64 Pillow build fuses the slope multiply/add. An explicit
single-precision `std::fma` models that operation; all translation units still
compile with `-ffp-contract=off`, with no implicit contraction or fast-math
waiver. This was required for two otherwise missing carrier pixels and is
covered by the unchanged real-board hashes.

The glyph atlas, source-over glyph masks, FreeType fractional-origin rounding,
adaptive PNG filters and zlib-ng parameters retain the already-proven assembly
contracts. These are reusable font data and algorithms, not stored board images.

## Build and run the contracts

Parent-owned main CMake integration:

```cmake
add_executable(schgen_ratsnest_documents_contracts
    tests/ratsnest_documents_contracts.cpp)
target_include_directories(schgen_ratsnest_documents_contracts PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_compile_options(schgen_ratsnest_documents_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
target_link_libraries(schgen_ratsnest_documents_contracts PRIVATE schgen_core)
add_test(NAME native_ratsnest_documents_contracts
    COMMAND schgen_ratsnest_documents_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.."
        "${CMAKE_CURRENT_BINARY_DIR}/ratsnest-document-results")
```

The isolated harness is `/private/tmp/ratsnest-documents.ziE1Rd/CMakeLists.txt`.
It builds only scratch executables and uses the previously copied core archive,
not shared native build outputs. The ASan/UBSan build script is
`/private/tmp/ratsnest-documents.ziE1Rd/sanitize.sh`; it uses the fully
instrumented native dependency closure from the prior isolated verification,
plus freshly instrumented ratsnest and MST sources. The link map shows no
uninstrumented core archive members; the external native zlib-ng archive is a
normal third-party dependency. No sanitizer suppression is used.

Final verification: optimized and ASan/UBSan executables each passed **67,941
assertions**, including all 81 document PNGs, the raster-probe PNG, seven SVGs
and five CLI summaries. Retained output directories:

- `/private/tmp/ratsnest-documents.ziE1Rd/results/run-ZBLVlo`
- `/private/tmp/ratsnest-documents.ziE1Rd/sanitizer-results/run-drUvva`

After parent commit `042888ec`, a fresh isolated rebuild against the current
headers and the parent's durable
`native/build/deps/zlib-ng` prefix also passed all **67,941 assertions**. Its
artifacts are
`/private/tmp/ratsnest-documents.ziE1Rd/post-042888ec-results/run-d5Ovxh`.
The compression helper's runtime/byte probe passed for that installed archive.
This recheck still used the harness's prior copied core/geometry objects; parent
integration should compile and test the complete current shared target.

The native executable has no Python or compression dylib dependency. No shared
build, generated project document, main CMake file, adapter or commit was changed
by this slice.

## Raster attribution (retain in supporting distribution documentation)

The scan converter is adapted from [Pillow 12.2.0 Draw.c](https://github.com/python-pillow/Pillow/blob/12.2.0/src/libImaging/Draw.c),
Copyright (c) 1996-2006 Fredrik Lundh and (c) 1997-2006 Secret Labs AB.
PIL is Copyright 1997-2011 Secret Labs AB, and Copyright 1995-2011 Fredrik Lundh
and contributors. Pillow is Copyright 2010 Jeffrey 'Alex' Clark and contributors.
The following MIT-CMU license is retained in the source and here:

By obtaining, using, and/or copying this software and/or its associated
documentation, you agree that you have read, understood, and will comply
with the following terms and conditions:

Permission to use, copy, modify and distribute this software and its
documentation for any purpose and without fee is hereby granted,
provided that the above copyright notice appears in all copies, and that
both that copyright notice and this permission notice appear in supporting
documentation, and that the name of Secret Labs AB or the author not be
used in advertising or publicity pertaining to distribution of the software
without specific, written prior permission.

SECRET LABS AB AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS.
IN NO EVENT SHALL SECRET LABS AB OR THE AUTHOR BE LIABLE FOR ANY SPECIAL,
INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
