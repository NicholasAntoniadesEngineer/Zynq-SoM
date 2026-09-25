# Manufacturing migration contracts and parent integration

These fixtures were captured from the independent Python assembly, manifest,
SI, pipeline-document, fabrication and fallback implementations before their
native replacements were written. `provenance.json` records the starting commit
and source hashes. No production source reads this directory. No Python
interpreter is invoked by the native implementation or contract executable.

The parent owns the main CMake integration, CLI, module bindings, Python adapters
and commits. The scoped `native/cmake/ManufacturingCompression.cmake` helper is
part of this slice; the main build files and generated project docs are untouched.

## Coverage

The compiled contract executable checks both projects: full assembly membership,
ordering, checkpoints, notes and Markdown; full manifest bytes from native live
power/testpoint analysis; SI rules, Markdown and verdicts; fabrication reports;
and the pipeline document. It checks all 52 real assembly PNGs (38 carrier,
14 devkit_mini) against independently captured PNG and decoded RGB SHA-256s.

`mutations.json` contains independent expected strings and image digests for six
assembly cases (including a duplicate-ref rejection) and six SI cases. These
exercise changed power dependencies, shunt equivalence, missing SoM keepout,
side and connector rotation, empty boards, uncovered/differently impedanced
pairs, minimum group tolerance, duplicate declarations and 80-character Unicode
note truncation. `fallback.json` freezes seven complete baseline/verdict cases.
Additional tests exercise fresh poses, invalid indices/unresolved footprints,
write failures, stale-image cleanup, missing input, idempotent SI append,
no-change document timestamps, strict fab thresholds, actual board extraction,
live artifact selection and binary hashing, manifest rehashing and exact signed
64-bit BOM counts.

## Add to the shared native target

Add these eight translation units to `schgen_core` (the other new files are
private headers or public API headers):

```cmake
target_sources(schgen_core PRIVATE
    src/manufacturing_assembly_plan.cpp
    src/manufacturing_assembly_documents.cpp
    src/manufacturing_assembly_images.cpp
    src/manufacturing_checks.cpp
    src/manufacturing_exports_manifest.cpp
    src/manufacturing_exports_si.cpp
    src/manufacturing_pipeline.cpp
    src/manufacturing_runs.cpp)
set_source_files_properties(
    src/manufacturing_assembly_plan.cpp
    src/manufacturing_assembly_documents.cpp
    src/manufacturing_assembly_images.cpp
    src/manufacturing_checks.cpp
    src/manufacturing_exports_manifest.cpp
    src/manufacturing_exports_si.cpp
    src/manufacturing_pipeline.cpp
    src/manufacturing_runs.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/ManufacturingCompression.cmake")
schgen_require_manufacturing_compression()
target_link_libraries(schgen_core PUBLIC schgen::manufacturing_compression)
add_executable(schgen_manufacturing_contracts tests/manufacturing_contracts.cpp)
target_link_libraries(schgen_manufacturing_contracts PRIVATE schgen_core)
target_compile_options(schgen_manufacturing_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_manufacturing_contracts
    COMMAND schgen_manufacturing_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.."
        "${CMAKE_CURRENT_BINARY_DIR}/manufacturing-contract-results")
```

These sources also use the existing native bring-up, power, testpoint, circuit,
constraint, atomic-file and PCB model/check/emission APIs. In particular,
`pcb_checks_model.cpp`, `pcb_checks_escape.cpp`, `pcb_model.cpp` and the PCB
emission slice must already be in the shared target. Do not duplicate the
default emit policy or geometry implementation in an adapter.

### Exact PNG compression dependency

Use **zlib-ng 2.3.3, built with the zlib-compatible API**, whose `zlibVersion()` is
`1.3.1.zlib-ng`. These are different version identifiers: checking only the latter
does not pin the implementation release. Stock system zlib produces identical
image pixels but different deflate bytes; the contract intentionally fails that
difference. Do not disable the PNG hash assertion. Pillow is not a production
or dependency-discovery requirement. The reusable Aileron 10px bitmap font is embedded in
`manufacturing_assembly_font.hpp` (font attribution and source hash included).
Images are freshly rendered from actual placed geometry and text; there are no
stored board images or output lookup tables in production.

#### Explicit native installation and parent wiring

The helper accepts one cache setting:
`-DSCHGEN_MANUFACTURING_ZLIB_PREFIX=/absolute/installed/prefix`. It requires
`include/zlib.h`, `include/zconf.h`, and a static `lib/libz.a` (also checks
`lib64` and `lib/<architecture>`; MSVC uses `zlibstatic.lib`). Keep the other
upstream installed headers with these files. It imports the archive and headers
as `schgen::manufacturing_compression`, without setting `ZLIB::ZLIB`, searching
system/Python paths, changing global search variables, or downloading anything.
Do not also link a stock `-lz`/`ZLIB::ZLIB` directly into the same engine target.

The static/PIC requirement is intentional: the native executable and transitional
module use the same checked compressor without a Python wheel, dylib install-name
rewrite, or separately deployed compression DLL. Provision the prefix outside
the repository and retain upstream licensing in the dependency package. Build
the dependency once, then reuse its installation across build directories.

Obtain and verify the pinned upstream source through the package/release process.
The verified source here was the [upstream 2.3.3 tag archive](https://github.com/zlib-ng/zlib-ng/archive/refs/tags/2.3.3.tar.gz),
downloaded from GitHub codeload; its observed SHA-256 is
`f9c65aa9c852eb8255b636fd9f07ce1c406f061ec19a2e7d508b318ca0c907d1`.
With that source already available locally, these commands need no network:

```sh
cmake -S /absolute/source/zlib-ng-2.3.3 -B /absolute/build/zlib-ng-2.3.3 \
  -DCMAKE_BUILD_TYPE=Release -DZLIB_COMPAT=ON -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_TESTING=OFF -DWITH_GTEST=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
  -DWITH_NEW_STRATEGIES=ON -DWITH_RUNTIME_CPU_DETECTION=ON \
  -DWITH_NATIVE_INSTRUCTIONS=OFF -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_INSTALL_PREFIX=/absolute/installed/prefix
cmake --build /absolute/build/zlib-ng-2.3.3 --parallel 4
cmake --install /absolute/build/zlib-ng-2.3.3
```

These are [upstream build options](https://github.com/zlib-ng/zlib-ng/blob/2.3.3/CMakeLists.txt).
The upstream C library uses its own compiler checks/options; the helper's probe
and native manufacturing sources use strict C++17 with
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`. Do not inject C++ flags into
upstream C feature checks. For a release, set the dependency's architecture and
deployment target consistently with the consuming native build.

At configuration, the helper checks both header versions, compiles and runs a
runtime-version/round-trip probe, and compares the SHA-256 of its compressed
hex output against the independently measured reference:
`03c433e6dad439ba633dd5e1cf22897379c8530ffaf4a9e0564655f00aafe576`.
The probe uses synthetic bands, gradients and noise across a 32 KiB history
boundary with the real PNG deflate parameters. It does not read production or
test board output. Checks rerun on every configure; cached success is not a
waiver. Cross builds require a working `CMAKE_CROSSCOMPILING_EMULATOR`. Full
PNG contracts remain required: this small probe is not a universal proof for
every platform, toolchain, or image.

#### Proven independent native prefix

A clean upstream source build (not a copied wheel library) is available now at
`/private/tmp/manufacturing-compression.mZB56C/prefix`:

```sh
-DSCHGEN_MANUFACTURING_ZLIB_PREFIX=/private/tmp/manufacturing-compression.mZB56C/prefix
```

Its static archive SHA-256 is
`f763ae0add57f3e0011abbf1d7b2f9fb4aec003ed4d331bac055809cd6d46525`.
This artifact hash describes the tested macOS arm64 build, not a portable
cross-platform archive pin. Parent can use this prefix immediately for
integration, then provision a durable prefix for normal builds.

The isolated CMake harness at
`/private/tmp/manufacturing-compression.mZB56C/harness/CMakeLists.txt` imports the
helper, recompiles the image renderer and manufacturing contracts against its
headers, and links the prior isolated native objects/core archive. It passed
**56,098 assertions**, including all **52 byte-identical project PNGs**, with
artifacts under
`/private/tmp/manufacturing-compression.mZB56C/contracts/run-gzuQKi` and the final
repeat run at `/private/tmp/manufacturing-compression.mZB56C/contracts-final/run-GqleAI`.
`otool -L` shows no Python or compression dylib dependency on the executable;
a shared-library/PIC link smoke test also passed. Repeated helper calls and an
installed prefix/build directory containing spaces were tested.

Negative configuration tests in
`/private/tmp/manufacturing-compression.mZB56C/failures.sh` cover absent/relative/
incomplete prefixes, stock headers, the wrong zlib-ng release, a missing or
corrupt archive, a mutated runtime-version result, altered deflate settings,
cross-compilation without an emulator, and conflicting repeated prefixes.
Reconfiguring a previously passing build with the altered compressor and forged
cached success was also correctly rejected; restoring the real prefix passed.
The mutated header tests use the genuine archive but change the observable
version or compression strategy; they prove the corresponding checks reject
the mismatch. No golden bytes, waivers, or native implementation settings were
changed to make the independent source build pass.

#### Earlier verification provenance

The original isolated verification used a copy of the already-installed zlib-ng C dylib,
with its install name changed to `@rpath/libz-ng.dylib`, at
`/private/tmp/manufacturing-native.EISPNz/libz-ng.dylib`. Its SHA-256 after the
install-name/ad-hoc-signing change is
`c7717856e8c5f0d255f694211b364aa277c01d21e4e35c7c3f1c836e17ebaf98`.
The existing core archive was copied to the same isolated directory; its SHA-256
is `a017239d7f1f31a346c49a5fd197b653795e77cabd1e64363932a946a7cc990c`.
No shared build was run by this slice.

## Entry-point integration

Include `schgen/assembly_documents.hpp`, `schgen/manufacturing_exports.hpp` and
`schgen/manufacturing_checks.hpp` from the parent-owned callers.

- Assembly: call `run_assembly_documents(model, power_result, config.name,
  project_root / "manufacturing/ASSEMBLY.md",
  project_root / "renders/assembly", pcb_emit_policy(config))` after actual PCB
  placement. It renders everything before publication, atomically writes each
  file, then removes stale PNGs only in the explicitly selected image directory.
  Feed the returned `JsonNode` to `assembly_verdict(result, repository_root)`.
  Propagate failures or record the actual `assembly_generation_failed` event and
  fail the build verdict; never manufacture a successful result. The pure plan,
  Markdown and image APIs also accept explicit caller-owned data.
- SI: call `run_si_constraints(sheets, project_root / "research/si_spec.json",
  project_root / "manufacturing/Zynq_Carrier_pcb.kicad_dru",
  project_root / "manufacturing/SI_CONSTRAINTS.md")`. It preserves the unrelated
  rules prefix and replaces only the SI suffix. Use `result.verdict.ok` for the
  exit status and `result.verdict.summary()` for reporting. A missing research
  file throws when any typed pair is declared; there are no invented targets.
- Manifest: call `prepare_manufacturing_manifest(sheets, stm32, xdc, device,
  preflight)` to run native power/testpoint analysis, or populate
  `ManufacturingManifestInput` with the already-computed live results. Construct
  `ManufacturingXdc` from the real XDC count/banks and
  `manufacturing_xdc_device(xdc_path)`. Then call
  `run_manufacturing_manifest(input, project_root, output_path)`. It always
  selects and hashes current artifact bytes, excludes its own output, and
  publishes the manifest atomically. `render_manufacturing_manifest` preserves
  signed 64-bit extended counts; `manufacturing_manifest` rejects counts that
  cannot be represented exactly by the shared `JsonNode` double storage.
- Fabrication: call `run_manufacturing_fab(reports_dir, pcb_path, dru_path,
  project_path)` and use `result.ok`. The wrapper measures the actual emitted
  board and writes `fab_profile.txt`. Unlike the legacy wrapper's empty-demand
  success, missing boards and wrong-root documents throw. The pure measurement
  overload retains the original absent-file result for compatibility; it is not
  sufficient to prove that a board was generated.
- Fallback ratchet: feed actual measured event counts to
  `run_manufacturing_fallbacks(census, baseline_path)`. It preserves the explicit
  legacy first-run/corrupt-baseline pin behavior, implicit zero ceiling for new
  names, and monotonic reductions. A regression does not write the baseline.
- Pipeline document: populate `ManufacturingPipelineInput` from the owning
  native stage/quantization/fallback registries, then call
  `run_manufacturing_pipeline(input, repository_root, output_path)`. That
  overload reads current per-project fallback baselines. The two-argument
  overload uses an explicitly prepared baseline snapshot. Both preserve the
  existing file's timestamp when bytes are unchanged. Registry fixtures in
  this directory are test inputs, not a production registry provider.

## Run the contracts

`manufacturing_contracts` takes the repository and a scratch parent directory:

```sh
/private/tmp/manufacturing-native.EISPNz/contracts \
  /Users/nicholasantoniades/Documents/GitHub/Zynq-SoM \
  /private/tmp/manufacturing-contract-review
```

Each run creates a unique child directory and prints its path, so repeat runs
preserve first-run pin/publication checks and keep their diagnostic artifacts.
The isolated build script
is `/private/tmp/manufacturing-native.EISPNz/build.sh`; the sanitizer executable
is `contracts_sanitized` alongside it. Both use C++17 and
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`. The sanitizer build script is
`/private/tmp/manufacturing-native.EISPNz/sanitize.sh`. It instruments the new
sources and the complete linked core/PCB dependency closure with
AddressSanitizer/UBSan, compiling into the isolated scratch directory. The link
map confirms no uninstrumented core archive members are used. This avoids the
libc++ vector-annotation mismatch encountered in the initial mixed build; no
sanitizer check or container-overflow detection is disabled.

The three temporary `native/tests/capture_manufacturing_*.py` scripts were
removed after capture and native verification. Immutable fixture bytes and
`provenance.json` remain; neither contracts nor production requires the scripts.
They can temporarily be recovered from
`/private/tmp/manufacturing-compression.mZB56C/retired-capture-scripts.tar`.
The original main capture restored `bringup_facts.py` and `firmware.py` from
`9f1fe2a4` in memory because the parent had already replaced those Python
implementations at capture time.

Final verification: both the optimized executable and fully instrumented
ASan/UBSan executable passed **56,098 assertions**. Their retained artifacts are
`/private/tmp/manufacturing-native.EISPNz/release-results/run-yY4egR` and
`/private/tmp/manufacturing-native.EISPNz/sanitizer-results/run-dnRXa3`, respectively.

## Shared JSON follow-up

The earlier shared decoder emitted separate invalid UTF-8 sequences for
`"\ud800\udc00"`. Parent commit `c6ec7657` now combines valid surrogate pairs
and rejects unpaired ones. The manufacturing Unicode mutant retains the exact
captured characters as literal UTF-8 and checks rendered output byte-for-byte.
The packaging harness above uses the previously copied core archive; parent
integration should also run the current shared JSON contracts. No shared JSON,
firmware RTC or FMC EEPROM document source was changed by this slice.
