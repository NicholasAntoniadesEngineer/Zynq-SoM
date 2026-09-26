# Local native build, dependency bootstrap and verification

This path configures the existing C++ engine and **all** its CTest contracts,
plus native bootstrap/CLI smoke checks. It never discovers Python, invokes pip,
builds nanobind, runs pytest, downloads a dependency or blesses golden output.
Independent original-output fixtures remain required during migration; a CTest
pass alone does not represent complete migration or full-board acceptance.

## Local/native runner prerequisites

- CMake **3.28+** for the CI wrapper (cross-directory CTest fixture properties),
  Ninja or Make, a C++17 compiler, and a C compiler for upstream zlib-ng.
- Matching Clang/libclang for mandatory source verification. Configure
  `SCHGEN_LIBCLANG` if discovery cannot find it. The currently reviewed semantic
  identities use Apple Clang/libc++; other toolchains need a reviewed manifest.
  Each build exports its production compile commands and generates
  `native-authoring-toolchain.json`; missing evidence fails before construction.
- libxml2 development headers/library; native Poppler C++ headers/library;
  libpng 1.6+ with its simplified API. No Python wheel libraries.
- Installed static/PIC **zlib-ng 2.3.3**, `ZLIB_COMPAT=ON`; provide its absolute
  prefix. `ManufacturingCompression.cmake` verifies header/runtime versions and
  exact compressed bytes. System zlib is not an interchangeable replacement.
- **KiCad 10.0.2** CLI and matching complete symbols, footprints and 3D libraries.
  Original installed dependency versions also include Poppler 26.03.0 and
  libpng 1.6.58. Real gate/render tests, not version strings alone, prove output.
- Some native tests still need installed stock libraries even without the
  `live-kicad` label. Excluding that label is **not** a KiCad-free test suite.
  Full native CI deliberately runs all registered tests without that exclusion.

The repository requires local verification and prohibits hosted CI. The `ci/`
directory is a local aggregate check entry point, not a hosted service.
No workflow is installed or dispatched. Use a dedicated checkout, **not the active multi-worker
checkout**: the parent build still publishes `native/bin/schgen`, `catalog.bin`
and `circuits.bin` into its source directory. Different binary directories alone
do not isolate those outputs. Do not run parallel configurations in one checkout.
No PR/push workflow is enabled.

## Explicit offline compressor bootstrap

Obtain the upstream `zlib-ng` **2.3.3 tag source archive** through the dependency
provisioning process. The archive SHA256 is
`f9c65aa9c852eb8255b636fd9f07ce1c406f061ec19a2e7d508b318ca0c907d1`.
This is the same independently verified archive in the manufacturing handoff.
With it already present locally, use fresh work/install paths:

```sh
cmake -DSCHGEN_ZLIB_ARCHIVE=/absolute/zlib-ng-2.3.3.tar.gz \
  -DSCHGEN_DEPENDENCY_WORK=/absolute/new-zlib-build \
  -DSCHGEN_DEPENDENCY_PREFIX=/absolute/new-zlib-prefix \
  -P native/ci/BootstrapZlib.cmake
```

The CMake script verifies the archive before extraction, refuses to overwrite
either path, builds upstream C code and installs it. It has no network branch,
vendored binary, Python or shell subprocess. It leaves failed partial builds for
diagnosis. A completed install must still pass the consuming compression probe.
Do not use a dependency prefix inside a Python environment or silently upgrade
the compressor to make a build convenient; all 52 PNG contracts must remain exact.

## Native build and full native contracts

From a dedicated checkout with dependencies installed:

```sh
cmake -S native/ci -B native/build/ci -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DSCHGEN_BUILD_PYTHON=OFF -DBUILD_TESTING=ON \
  -DSCHGEN_MANUFACTURING_ZLIB_PREFIX=/absolute/installed/zlib-ng
cmake --build native/build/ci --parallel 4
ctest --test-dir native/build/ci --output-on-failure --no-tests=error \
  --parallel 1 --timeout 1200 --output-junit native/build/ci/native-results.xml
```

No engine CMake changes are required: `native/ci/CMakeLists.txt` adds the normal
native build as a subdirectory, then registers its extra checks. Every engine
contract requires the cache/environment preflight fixture. Missing tools,
incorrect KiCad release, missing stock assets, Python-enabled/discovered cache,
missing tests, compiler errors or CTest failures are failures, never skips.
The native CLI smoke executes real kernel self-checks, tests rejection of bad
arguments and compiles part/circuit catalogs twice into private scratch for exact
comparison. It does not regenerate a board or write production catalogs itself.
The cache/magic checks are scoped evidence, not a claim to intercept every child
process: native implementation ownership and normal contracts remain necessary.

For the smoke tool's **own** small contract suite, independently of the engine:

```sh
cmake -S native/ci/smoke -B /absolute/scratch/ci-smoke
cmake --build /absolute/scratch/ci-smoke --parallel 2
ctest --test-dir /absolute/scratch/ci-smoke --output-on-failure --no-tests=error
```

That test is not a substitute for building/testing the generator. CI uses the
full wrapper, not this smoke-only entry point. Parent-owned full board CLI
acceptance and Python parity remain separate until the migration is complete.

## Removal-ready infrastructure map

There was no hosted pipeline, Makefile, setup.py, setup.cfg or installable Python
package at inventory time. The retired `pyproject.toml` contained only tooling
configuration, not packaging metadata. This local wrapper does not add a hosted pipeline.

- `scripts/build_native.sh` and `scripts/check.sh`: retired. Use the CMake path
  above and native `schgen check --tests-dir BUILD`, which runs complete board
  generation, mutation/determinism selftest and all CTests. This command retains
  mandatory audit failures; retirement is not a claim of full-board acceptance.
- `requirements.txt`, `pyproject.toml`, and `.pre-commit-config.yaml`: retired
  with the 393 inventoried Python files. Native compiler flags are C++17 plus
  `-Wall -Wextra -Wpedantic -Werror`; numeric smoke uses `-ffp-contract=off`.
  Do not replace checks with hooks that swallow failures.
- Both `conftest.py` files are retired. Explicit CMake source/test registration
  replaces collection. Native tests own isolated C++ fixtures and output
  directories; independent reference JSON stays tracked and immutable.
- `native/CMakeLists.txt`: Python/nanobind discovery and extension targets are
  removed, along with the binding-only sources/headers. The compatibility cache
  option remains explicitly OFF; attempting ON fails before dependency discovery.
- `native/CMakePresets.json`: existing fast/offline presets remain unchanged.
  Its offline label exclusion does not prove a library-free host. The new wrapper
  registers full CI preflight without changing developer build preferences.
- `native/tests/run_*contracts.sh`: historic isolated convenience wrappers, not
  used by this native CI path. Remove only once each owner's equivalent CTest
  registration is proven. Experiment/importer/helper ports belong to their owners.
- README commands: native build entry points are linked prominently; legacy
  authoring and parity examples remain explicitly migration-era documentation.
  Generated board documentation is not rewritten by this worker.

Do not remove required KiCad/STEP/WRL/JSON assets, captured independent fixtures,
FPGA HDL/XDC/Tcl or generated firmware C while retiring Python infrastructure.
Hosted Linux/Windows portability and provisioning are not proven by this patch;
some existing native fixture paths reflect the original macOS installation.

## Worker verification and parent handoff

Verified under `/private/tmp/native-ci-proof.TXSWZ2`, with no shared engine build:

- Native smoke executable compiled with strict C++17 flags; **3/3 CTests passed**
  (15 internal positive/negative contracts plus invalid-argument rejection).
- Full wrapper configured successfully; after the parent's project-base test
  registration it exposes **98 tests**, including **92 engine tests**, all 92
  requiring the cache/environment preflight fixture. Its **5/5 cache/environment
  and smoke CTests passed** using only the isolated smoke target (no engine build).
  This is **not a claim that those 92 engine tests were run here**.
- Actual installed KiCad 10.0.2/library preflight passed. Native cache check passed.
  A frozen copy of the parent's CLI passed real kernel/self-check, malformed-args
  rejection and twice-compiled, byte-identical part/circuit catalogs in scratch.
- Verified upstream archive built/installed to an isolated prefix; configuring
  the full wrapper against that new prefix passed the existing independent
  compression known-answer test. The bootstrap rejected a wrong hash, relative
  or missing source and a preexisting install prefix without writing outputs.
- Wrapper rejects `SCHGEN_BUILD_PYTHON=ON` and `BUILD_TESTING=OFF` explicitly.
  The existing shell wrappers still pass `bash -n`.

The full aggregate engine build/CTest run is left to coordinated integration.
There is no remote dispatch. No main CMake/module/CLI/core edit was needed
for this CI path; no shared executable, extension or catalogs were rebuilt here.
The separate bounded render fix/proof is documented in
[`PROJECT_BASE_HANDOFF.md`](../tests/data/render_models/PROJECT_BASE_HANDOFF.md).

The former FUSB-model fixture mismatch has been resolved with an exact,
single-model-block migration check against the unchanged historical hash.
The live renderer contract now requires both boards to render all eight real
views; the missing-model exception has been removed. Both passed in the parent
integration run. This local wrapper runs that contract without exclusions.
