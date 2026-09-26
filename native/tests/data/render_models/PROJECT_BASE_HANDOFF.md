# External-output project model base — stable native checkpoint

New trailing field in `Render3dOptions`:

```cpp
std::optional<std::filesystem::path> source_project_directory;
```

This is an ABI layout change: rebuild all consumers coherently. No Python binding
signature, module, main CMake or board-pipeline file was changed by this worker.
Parent renderer wiring is:

```cpp
ro.source_project_directory = c.paths.project_root;
```

The explicit source directory is canonicalized and required to exist. It drives
required-model preflight, plain-relative model absolutization in the private PCB
copy, and KiCad `-D KIPRJMOD`. Both `render_board_3d` and `export_board_step` use it.
An unset option retains the input PCB's project as the base. The input PCB/model
clauses remain byte-unchanged; no copying/guessing model libraries or success
waivers are introduced. Absolute model paths and installed KiCad model-directory
variables continue to work independently of the project base.

Proof: `native/tests/render_project_base_contracts.cpp`, strict C++17
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`, isolated executable
`/private/tmp/native-render-project-base.57lYJw/contracts`.
**18,566 assertions passed**: 24 actual KiCad views, two full component STEP
exports, and tile comparisons against an actual absolute-model control render.
Both `${KIPRJMOD}/../parts/AO3400A/AO3400A.wrl` and plain `../parts/...` are tested
from copied PCBs in unrelated scratch roots using genuine source WRL/STEP files.
No model assets are copied into scratch. Unset/wrong/missing source bases fail;
stale output is not credited. Copied PCB/project and source model bytes remain
unchanged. The source files were frozen before the parent's coherent clean build.

Parent CMake registration (not applied by this worker):

```cmake
add_executable(schgen_render_project_base_contracts tests/render_project_base_contracts.cpp)
target_include_directories(schgen_render_project_base_contracts PRIVATE src)
target_link_libraries(schgen_render_project_base_contracts PRIVATE schgen_core)
target_compile_options(schgen_render_project_base_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_render_project_base_contracts COMMAND schgen_render_project_base_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_tests_properties(native_render_project_base_contracts PROPERTIES LABELS live-kicad)
```

This small genuine-model fixture establishes model-base correctness; it is not
claimed to replace the parent's full external-output board acceptance test.
