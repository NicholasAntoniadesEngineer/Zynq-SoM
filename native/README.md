# Native migration

The target is a complete C++ generator, including design loading, placement,
routing, emission, verification, CLI, and tests. The Python extension is a
temporary migration interface. Native kernels alone do not complete the port.

## Build without Python

From the repository root:

```sh
cmake -S native -B native/build/standalone -DSCHGEN_BUILD_PYTHON=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build native/build/standalone --parallel
ctest --test-dir native/build/standalone --output-on-failure
native/bin/schgen --help
```

This builds the C++ engine, command-line program, and part/circuit catalogs
without discovering Python, installing nanobind, or fetching dependencies.
The current CLI supports `self-check`, `catalog-compile`, and `circuit-compile`.
It does not yet generate a board. Unsupported commands fail.

`scripts/build_native.sh` still builds the transitional Python bindings. Both
executables link the same `schgen_core` library; the engine sources compile
once per build directory. Preserve the per-source floating-point settings:
these are part of the deterministic-output contract.

Catalogs depend on their JSON inputs and regenerate when those inputs change.
Build directories share the in-tree binary and catalog outputs, so build them
sequentially.

## Remaining migration

Move complete pipeline stages into the native library and CLI. The remaining
work includes board orchestration, schematic placement, full board/schematic
emission, verification/reporting, system outputs, and authoring commands.
Replace Python tests with native tests before removing their reference logic.

Each stage must preserve electrical connectivity and its relevant gates, then
compare generated artifacts against the established reference. Record measured
end-to-end performance separately from kernel benchmarks. Remove Python source,
bindings, and Python build dependencies only once their consumers have moved.
Final acceptance requires generating both supported projects and running their
verification from a clean build without Python; pre-existing failures must be
reported, not suppressed.
