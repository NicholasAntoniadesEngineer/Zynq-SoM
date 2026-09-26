# Runtime-proven binding and adapter handoff

## Ready for parent integration

The parent binding-ready signal was received and the three authorized adapters
are migrated. No shared build, CMake, module, CLI, model policy, board, project,
STEP or WRL file was changed by this cleanup. The shared extension remained
SHA256 `7d48e34b71dcb18abb9cc2e85775dfda261a748f1e2c60b83e492bdb5a713bda`.

Adapter changes:

- `schgen/output/render.py`: native rendering and coordinate conversion, frozen
  `PageRaster` and `Path` transport retained; no fitz or subprocess implementation.
- `schgen/output/render3d.py`: native discovery/eight-view execution, `list[Path]`
  return retained; incomplete output raises with native diagnostics and `cmd`
  returns failure. Missing-file native exceptions propagate as `RuntimeError`.
- `schgen/verify/model3d_gate.py`: native checks, measurements, publication and
  result text; `invalid` is exposed and result mutation is reflected in reports.
  Compatibility `_KNOWN_UNMATCHED` remains empty and cannot grant waivers.

Focused runtime tests: `schgen/tests/test_native_render_models.py` plus
`schgen/tests/test_model3d_gate.py`: **319 passed in 10.21 seconds**. This covers
288 independent geometry cases, five byte-exact OBJ conversions, eight real PDF
rotation/crop/first-page cases, real schematic export, real eight-view KiCad
rendering, actual STEP export, exact 62/62 repository gate/report, publication,
source preservation, stale-output rejection and explicit error propagation.
The five existing model3d PCB mutation tests separately **passed in 0.03 seconds**
with `-k model3d`: **324 focused tests passed in total**.
Two old tests were corrected to require hard failure for garbage geometry and
an attempted missing-hardware waiver. Valid geometry coverage remains independently
proven; no gate was weakened. All five edited/new Python files pass Ruff.

Reproduce without relying on the unavailable pytest-xdist plugin in this venv:

```sh
.venv/bin/python -m pytest -o addopts='' schgen/tests/test_native_render_models.py schgen/tests/test_model3d_gate.py -q
.venv/bin/python -m pytest -o addopts='' schgen/tests/test_pcb_gate_mutation.py -k model3d -q
```

All test publication is to pytest temporary directories. Both live PCB/project
pairs and all 154 captured hardware assets remain unchanged. No full Carrier
render was attempted against the pre-repair board. Parent owns regeneration and
the part-plus-exact-footprint policy. Worker pauses after this handoff.

## Parent integration

New data-only header: `native/include/schgen/native_render_bindings.hpp`.
Parent adds its include and calls `schgen::bind_native_render(m)` once in the
existing module initializer. No new `.cpp` source or extra binding dependency
is needed beyond the render core's previous handoff. This header includes its
own nanobind/STL casters; it does not assume other binding headers ran first.
It registers **13 functions**, no Python classes, imports, callbacks, expressions,
fallback engines or subprocess implementation. Filesystem/render/measurement
operations release the GIL; conversion back to Python data occurs with it held.

Exports (all paths are plain strings at this boundary):

- `render_sheet_to_png(schematic_path, png_path, dpi=300, kicad_cli="kicad-cli", timeout_ms=300000)`
- `render_pdf_to_png(pdf_path, png_path, dpi=300)`
- `render_mm_to_px(width_px, height_px, page_w_mm, page_h_mm, x_mm, y_mm)`
- `render3d_find_model_dir()` → string or `None`.
- `render3d_run(pcb, out_dir, quality="high", width=1600, height=1200, model_dir=None, kicad_cli="kicad-cli", timeout_ms=300000)`
- `render3d_export_step(pcb, output, model_dir=None, kicad_cli="kicad-cli", timeout_ms=300000)`
- `model3d_default_directory()`
- `model3d_resolve_path(raw, model_dir, project_root)` → string or `None`.
- `model3d_measure(footprint_text, clause_body, model_text, extension)`
- `model3d_check(parts_directory, project_root, model_dir=None)`
- `model3d_run(parts_directory, project_root, report_directory, model_dir=None)`
- `model3d_result_text(result)` → current native `line` and `report` strings.
- `model3d_obj_to_wrl(obj)` → string or `None`.

Page results contain the six original `PageRaster` fields. Geometry results
contain `model_xy`, `fab_xy`, `model_box`, `pad_box`, `misfit`, `misplaced`.
Gate results contain original fields plus `invalid`, `line`, `report`.
Render results contain `written`, `views` (`view`, `path`, `width`, `height`),
`failures` (`view`, `diagnostic`), `ok`, `summary`. Exceptions are not swallowed.

Compile-only test: `native/tests/native_render_bindings_compile.cpp`, verified
with strict C++17 `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`, repository
headers, installed nanobind headers and Python 3.14 C headers. Object:
`/private/tmp/native-render-models.6MVTPP/native_render_bindings_compile.o`.
**This is not a runtime binding test.** No Python tests, interpreter invocations,
shared `.so` builds, `module.cpp`, or main CMake edits were performed in this stage.

## Applied adapter contract

1. `schgen/output/render.py`: retain `DEFAULT_DPI`, public `PageRaster` data shape,
   `Path` conversions and public signature. Delegate `mm_to_px` and render calls.
   Remove `fitz`, subprocess, executable lookup, temporary PDF handling and pixel
   geometry computation. Native exceptions propagate; no Python fallback.
2. `schgen/output/render3d.py`: retain public `find_model_dir`, `render`, CLI-shaped
   entry point and path/list transport. Delegate discovery and all eight views.
   Print native diagnostics/summary as appropriate, but do not present a partial
   result as successful completion. Missing required assets remain explicit
   failures. Remove Python version probing, per-view process loop, project-byte
   restoration and capability guessing. No Python subprocess remains.
3. `schgen/verify/model3d_gate.py`: retain public result dataclass and path constants
   needed by callers/test injection. Delegate check/run/resolve and formatting;
   include `invalid`. `line()`/`report()` must format current fields via native
   `model3d_result_text`, not cache stale text after result mutation. Preserve
   `_fit_ok`/`_placed_ok` test-facing names as file-data transport to
   `model3d_measure`; remove regex/geometry/threshold implementations. Native
   `project_root` is the active project directory, not repo root.
4. The part-library `_obj_to_wrl` adapter is **outside the three requested adapter
   files**. Binding is ready for that owner's eventual importer cleanup; do not
   edit `part_gen.py` opportunistically or claim its HTTP downloader is ported.

The dirty state was inspected before changes. Runtime binding/adapter tests above
use immutable independent JSON fixture bytes. Broader tests belong to the parent.

Two old Python test assumptions deliberately conflict with the accepted stricter
native gate: a STEP file containing only `"x"` cannot be a valid measurable model,
and monkeypatched `_KNOWN_UNMATCHED` entries must not waive missing hardware.
Update those tests to assert real geometry or hard rejection, not add fallback
logic to satisfy them. `_KNOWN_UNMATCHED` is empty in production. Ordinary
coverage/fit/placement parity must remain exact against captured references.

The preceding compile-only-stage restriction ended with the binding-ready signal.
No additional work is undertaken until the parent's integration is stable.
