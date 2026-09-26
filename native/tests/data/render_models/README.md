# Native schematic rendering, board 3D rendering and model coverage

Follow-up handoffs: [runtime-proven bindings and adapters](ADAPTER_HANDOFF.md),
[proven genuine U30001 model-only repair](FUSB302B_REPAIR.md). The repair is
proven on a scratch Carrier (8/8 views) but not applied to production files.

Worker-owned source handoff. Parent owns main CMake/module/CLI integration.
The three authorized Python adapters are now migrated; see the runtime handoff.
No shared builds, hardware asset changes, downloads, vendored
binaries, embedded Python, shell commands or Python subprocesses were introduced.

## Add exactly these sources

- `native/src/model3d_gate.cpp`
- `native/src/model3d_assets.cpp`
- `native/src/native_render.cpp`

Public headers: `native/include/schgen/model3d.hpp` and
`native/include/schgen/native_render.hpp`. Private header:
`native/src/render_models_internal.hpp`.

Existing core dependencies: `process.cpp` / `process.hpp` and
`atomic_file.cpp` / `atomic_file.hpp`. Gate and OBJ conversion need only the
standard library and atomic-file publisher; rendering additionally needs
**Poppler C++ and libpng**, not PyMuPDF. Do not link a Python wheel's libraries.

Compile C++17 with `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`.
Add the three sources to `schgen_core`; add the parent include directory
containing `poppler/cpp/poppler-document.h` and `png.h`; propagate link
dependencies `poppler-cpp` and `PNG::PNG` to core consumers. No additional
manufacturing compressor dependency is needed by this family. Poppler/libpng
are system-native dependencies, separate from byte-exact manufacturing PNGs.

Verified local dependencies:

- KiCad CLI `/opt/homebrew/bin/kicad-cli`, version **10.0.2** (9+ API required).
- `/opt/homebrew/include/poppler/cpp`, Poppler **26.03.0**;
  `/opt/homebrew/lib/libpoppler-cpp.dylib`.
- `/opt/homebrew/include/png.h`, libpng **1.6.58**;
  `/opt/homebrew/lib/libpng.dylib` (simplified read API required).
- KiCad bundles OpenCascade **7.9.3**, including STEP and VRML libraries; its
  CLI is the available native CAD entry point. OCCT development headers,
  standalone MuPDF/`mutool`, FreeCAD, Blender and POV-Ray were not available.
  Assimp 5.4.3 is installed but is not needed or substituted for a CAD kernel.
- Poppler header version macros are in `poppler/cpp/poppler-version.h`;
  runtime `poppler::version_string()` is available for parent dependency checks.
  Existing CMake minimum is 3.18: `find_path`/`find_library` plus `find_package(PNG
  1.6 REQUIRED)` work without `pkg-config`, which is absent on this host.

Native CLI interface reference:
[KiCad command-line documentation](https://docs.kicad.org/9.0/en/cli/cli.html).
The installed `pcb render --help` and `pcb export step --help` were also checked.

## Public integration contract

`check_model3d(parts_directory, project_root, model_directory)` is the actual
coverage/fit/placement gate. **project_root means the active project directory**
(`repo/carrier` or `repo/devkit_mini`), not the repository root: current custom
models use `${KIPRJMOD}/../parts/...`. `run_model3d` additionally publishes
`report_directory/model3d.txt` atomically. `Model3dResult` has the original fields,
`line()` and `report()`, plus `invalid` for genuinely unreadable/unmeasurable
geometry. No unmatched-part exemptions are introduced; the Python map is empty.

`measure_model3d(footprint_text, clause_body, model_text, extension)` exposes the
legacy gate's point envelopes, fabrication bounds, pad bounds and diagnostics.
It preserves WRL 2.54-mm units, absolute XY scales (zero maps to one), clockwise
center rotation, quarter-turn dimension swaps, 0.5..2.0 soft fit range and 20%
hard pad overlap. This is **not full STEP solid or VRML scene evaluation**;
arbitrary-angle AABB expansion/VRML transforms were not added under an exact
legacy-geometry contract. KiCad's renderer/exporter performs actual model import.

`model3d_obj_to_wrl(obj_text)` ports the repository-owned EasyEDA OBJ converter:
center XY, ground Z, /2.54 scaling, Python-equivalent four-decimal rounding,
material text and per-material face indexing. No OBJ/STEP download is performed.
The requested render/gate modules do not call the part-library HTTP downloader;
the new converter can be called directly by the parent’s eventual part importer.
Required STEP/WRL assets remain in `parts` and `som/lib/3d` unchanged.

`render_sheet_to_png(schematic, png, dpi=300, options)` invokes native KiCad
schematic PDF export then native Poppler; `render_pdf_to_png` exposes first-page
rasterization separately. Return `PageRaster` fields map directly to the Python
dataclass, including `mm_to_px`. Rotated CropBoxes and multipage-first-page
selection are tested. **Poppler pixels/PNG encoding are not MuPDF-byte-exact**;
physical dimensions/artwork location are independently checked. KiCad-exported
Qwiic schematic is 842x596 at 72 DPI in both captures.

`render_board_3d(pcb, output_directory, Render3dOptions)` invokes the actual
native KiCad ray tracer for top, bottom, left, right, front, back, perspective,
rear perspective, in that order and with the original view/quality options.
Default quality/high/1600x1200 are retained. `written` matches the original path
list; `views` records observed raster dimensions; `failures` records per-view
errors; `ok()` requires all eight outputs. `summary()` is the original success
line. Parent should expose failures and return failure if `!ok()`, not count one
image as complete success. Missing CLI/model library/required assets throw.
Required STEP/WRL files are checked for a measurable coordinate envelope before
rendering; nonempty garbage cannot silently produce a body-less success. This
preflight is deduplicated by model path, not repeated for every placed part.

KiCad's canvas can be smaller than its nominal requested size (this installed
version produces 224x168 for 240x180, and the existing checked-in board renders
are 1568x1176 for nominal 1600x1200). Preserve native bytes; don't rescale merely
to make the requested size exact. Full PNG decode verifies output validity and
bounds. Fresh staging prevents a preexisting output from being credited as a new
render. Caller PCB/project bytes are never edited: board/project copies live in
private staging, with original KIPRJMOD and absolute resolution for plain relative
model references. Each complete output is atomically published.

`export_board_step(pcb, step_path, Render3dOptions)` uses native KiCad/OpenCascade
with `--subst-models`; it requires adjacent `.step`/`.stp` substitutes for WRL
references and rejects absent assets, failed subprocesses, malformed STEP framing
and exporter error diagnostics. It does not use `--board-only` or omit components.
A 1,548,190-byte live export with the repository AO3400A component is proven.
Private output is precreated and `--force` used to avoid KiCad/macOS's erroneous
attribute-copy diagnostic for a nonexistent destination; no diagnostic is waived.

## Explicit changes and unresolved external gap

Missing/empty footprint inventory throws instead of returning vacuous success.
No coordinate envelope, unreadable model or nonfinite transformed geometry is a
hard `invalid` failure; the Python gate silently accepted unmeasurable assets.
The historical report's `STATUS: SOFT` sentence is retained for exact text
compatibility, but **it is not the verdict**: missing/broken/misplaced/invalid
are hard failures; `misfit` alone remains soft.

**Carrier's complete 3D render is blocked by one actual missing installed asset:**

```
/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step
```

Its PCB references that path. The Python baseline produces eight PNGs while
omitting that missing body. The native wrapper refuses that incomplete rendering;
no replacement body, exemption or false success was introduced. Parent must
resolve the correct asset/reference separately. Devkit Mini's eight-view render
is complete. The live contract allows only this exact known Carrier dependency
failure (prints `FULL BOARD RENDER BLOCKED (not a render pass)`); any other missing
asset is a test failure. If the asset becomes available, the same test must
actually render Carrier and compare its imagery. This negative contract does
not count as a successful Carrier render or board gate.
The emitted reference is at `carrier/Zynq_Carrier.kicad_pcb:104141`; the footprint
choice originates in `native/src/subsystem_authoring_usb_pd.cpp:11`. Neither was
edited by this worker.

## Independent fixtures and proof

Captured from untouched Python implementations before adapter integration:

- `reference.json`: exact repository verdict/line/report, 288 WRL/STEP geometry
  cases, OBJ conversion bytes, 154 hardware asset SHA-256s and source SHA-256s.
  SHA-256 `c233558629102d5885d7dd3ad845e2894ee9107794b3ab57fa08b8fac6968a2c`.
- `render_reference.json`: original Python/KiCad eight-view captures for both
  real boards and original PyMuPDF schematic geometry.
  SHA-256 `92c8f067a7937462b4235ee2dcb88c5ceaa7eda4b22caf2f5932f29b393c6ff8`.
- `asset_complete.kicad_pcb` + `asset_complete_reference.json`: isolated positive
  hardware-render fixture; only `@MODEL@` is replaced with AO3400A's actual path.
  Reference SHA-256 `2e4b5c6b812687c49f1d35d9d5104bfd38286252c0a78c5d92dd0ef8ee008830`.
- `raster_tiles.json`: immutable RGB hashes and 16x12 RGB mean tiles from those
  independent renders. Ray-tracer stochastic output is structurally compared:
  mean absolute tile-channel difference <2/255, maximum <20/255. A black-image
  mutation proves the comparison rejects wrong output. Exact RGB equality is
  logged separately, not asserted dishonestly for stochastic images.
  SHA-256 `93b0bd80feb38dc6d6d5218832cba80270d9e852a161c25102c260a94751971e`.
- `pdf_reference.json`: immutable actual PDF bytes (hex) and independent MuPDF
  dimensions/red-artwork bounds for 0/90/180/270-degree CropBox rotations at 72
  and 150 DPI, with a different second page to verify first-page selection.
  SHA-256 `b9b583687e7e19e9eb25ac1afc38b1f30411ccd5163295894ceebc4362a95fe5`.

Test target source: `native/tests/render_models_contracts.cpp`; link `schgen_core`
plus its propagated Poppler/libpng dependencies, and privately include `native/src`.
Invocation: `render_models_contracts REPO FRESH_SCRATCH --live`. Without `--live`,
pure/gate/error/PDF contracts still run; **that is not evidence of live rendering**.
Tests use a compiled native adversarial child only for negative subprocess cases.
All successful live render/STEP paths execute the actual KiCad binary.

Isolated proof directory `/private/tmp/native-render-models.6MVTPP` contains
`build.sh`, `contracts_normal`, `contracts_sanitized`, `normal/results`,
`sanitized/results`, and both link maps. Normal build uses immutable prior core
archive `/private/tmp/manufacturing-native.EISPNz/libschgen_core.a`; ASan/UBSan
build instruments all new sources, process/atomic/json sources and uses existing
instrumented SHA/occupancy/quantize objects. Its link map proves no uninstrumented
core archive was loaded. External Poppler/libpng/KiCad are installed native code.

Final verification: **5,001 assertions PASS in both normal and ASan/UBSan builds**,
including real native external capabilities; no sanitizer diagnostics. Logs:
`/private/tmp/native-render-models.6MVTPP/final-normal.log` and
`/private/tmp/native-render-models.6MVTPP/final-sanitized.log`. All 154 hardware
asset hashes remain exact. The explicitly reported Carrier render dependency
gap above remains unresolved, not reclassified as a successful render.

Proven coverage includes missing executables/directories, missing/broken model
clauses, real offset and soft-fit mutations, invalid model data, invalid PDFs/DPI,
stale output preservation, corrupt-success PNGs, timeout child termination,
all retained hardware hashes before/after, source project immutability and real
native rendering/STEP. Fontconfig emitted unwritable-cache notices inside the
sandbox; rendering and artwork-position checks nevertheless completed. Expected
invalid-PDF tests emit Poppler diagnostics. Neither is hidden.

Temporary Python capture scripts were removed after capture; recoverable provenance
is archived only outside the repository at
`/private/tmp/native-render-models.6MVTPP/oracle-capture-scripts.tar`. The final
production and contract execution paths contain no `.py` scripts or Python calls.
