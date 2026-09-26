# Native authoring source-purity integration

Status: implementation and production entry points present; final frozen all-source
census follows actual legacy retirement. Do not interpret an earlier diagnostic
run or an edited-source run as a cutover proof.

## Sources and build boundary

Add `src/authoring_purity.cpp`, `src/authoring_purity_scope.cpp`, and
`src/authoring_purity_config.cpp` to the native core once. The scanner privately
includes `src/authoring_purity_clang.hpp`; public headers are
`schgen/authoring_purity.hpp` and `schgen/authoring_purity_config.hpp`.
Link `${CMAKE_DL_LIBS}` (empty on supported Apple toolchain); reuse core JSON.
Runtime dependency is the configured libclang shared library, not a Clang CLI
subprocess, Python, nanobind, libclang headers, or an AST JSON dump.

Also integrate Aristotle's authoring-context/split sources and header. Existing
project/library registry sources are edited in place; do not duplicate entries.
All private builds use C++17, `-Wall -Wextra -Wpedantic -Werror`, and
`-ffp-contract=off`. No shared builds or board artifacts are produced by worker.

## Mandatory pre-construction invocation

Create the native context with `make_authoring_context(repository)` (host metadata
setup, not circuit construction). Call:

```cpp
const auto purity = check_native_authoring_purity(repository, toolchain_file, context);
// Parent's atomic report publisher writes purity.report() to mandatory board report.
if (!purity.ok()) throw /* parent's gate failure */;
// Pass this exact context unchanged to all subsequent authoring operations.
```

Do this before `native_project_factories`, `author_project_subsystem`, library/example
factories, and any board authoring. Publish failures as well as success. No CLI
disable switch or `native_policy=false` bypass is provided. The public custom-provider
authoring API remains compatible; it is not a policy-checked board entry point.
Recheck after any context mutation. `require_native_authoring_context` verifies the
actual catalog function pointer and the private named pin-resolver owner without
executing unknown callbacks. The source graph follows both exact native targets
and the guard body. No other `std::function` dispatch is trusted.

Production checks the registered constructor modules and reachable provider
bodies afresh. A separate mandatory test calls
`check_native_authoring_purity_census(repository, toolchain_file)` to census **all**
C++ sources below `native/src`, including otherwise unrelated infrastructure.
Every source needs its compile command; every IR-producing/mutating definition
needs an explicitly reviewed constructor or non-authoring role. Non-authoring
classification never makes that implementation an allowed constructor dependency.
Do not exempt retiring binding files: retire them and run against the real tree.

## Toolchain configuration

Enable `CMAKE_EXPORT_COMPILE_COMMANDS`. Supply a JSON file with exactly:

```json
{
  "schema": "schgen.authoring-purity.toolchain.v1",
  "compiler": "/Library/Developer/CommandLineTools/usr/bin/clang++",
  "libclang": "/Library/Developer/CommandLineTools/usr/lib/libclang.dylib",
  "compile_commands": "/absolute/coherent/build/compile_commands.json",
  "production_targets": ["schgen_core", "schgen"],
  "system_include_directories": [
    "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1",
    "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include",
    "/Library/Developer/CommandLineTools/usr/lib/clang/21/include"
  ]
}
```

These are the locally tested toolchain paths, not portable discovery defaults.
Parent must configure installed paths and a coherent matching compiler/libclang.
Relative paths resolve against the configuration/database directories. The loader
accepts argv arrays or shell-quoted `command` strings but **never executes** either.
It rejects shell substitutions, response files, plugins/modules/PCH, unknown flags,
conflicting compile configurations, wrong compiler drivers, and configuration
scope/exemption/off fields. Include precedence is preserved; `-isystem` alone does
not confer trust. System declarations must physically reside in the reviewed
outside-repository system roots and have compiler system-header provenance.

`production_targets` is mandatory source authority: select CMake object-output
owners explicitly before parsing unrelated test/instrumentation commands. For
this repository use `schgen_core` and `schgen`; do not include instrumented
quantization/precision test-object targets. Selected argv `-o` must agree with
the declared output. Different commands for one source across selected targets
still fail; there is no first-command/first-target preference. All required
constructor/provider commands and full-census sources must remain covered.

## Contracts

- `authoring_purity_contracts REPOSITORY LIBCLANG --system DIRECTORY ...`:
  compiler-backed good/adversarial source fixtures, imports/macros/aliases,
  transitive/provider calls, templates, pointers/virtual/erased callbacks,
  new constructors, missing evidence, named capability sites/targets/guards,
  receiver mutation/escape, and private provider header boundaries.
- `authoring_purity_config_contracts REPOSITORY COMPILER LIBCLANG SYSTEM_INCLUDE ...`:
  offline private JSON/compile-command fixtures and real compiler invocation.
- `authoring_purity_dispatch_contracts`: rejects changed, wrapped, wrong-name,
  wrong-project and wrong-kind project registry targets without executing them.
- `authoring_purity_repository_contracts REPOSITORY CONFIGURATION closure|census`:
  production configuration/actual context and the separate all-source census.
- Mandatory frozen real-repository closure and full census through the production
  config loader. A private Python-free mirror is only an explicitly labelled interim
  proof. Final acceptance requires the actual retired repository.
- Existing immutable authoring fixture/gate tests verify parameterized output;
  changed project/registry sources passed 4,196 existing gate assertions privately.
- Aristotle's native context contracts verify rejection of foreign/wrapped/moved
  callbacks and live valid metadata behavior. Keep these mandatory.

## Reviewed scope and limitations

This is an architecture gate, not a security sandbox or a general C++ effects
system. Ordinary stdlib/I/O is not banned. Constructor modules cannot import
geometry/private-provider headers or directly reference their declarations.
Shared metadata providers are checked by reachable compiler bodies, not by all
unrelated operations in the same translation unit. Symbol resolution may read
symbol data internally, but constructors receive only pin-number sets.

The reviewed compiler identities are currently Apple Clang/libc++ canonical types;
a different toolchain must get a reviewed identity manifest, not erase overload
information. No compiler namespace filter is used. Parse errors and unsupported
indirection fail closed. Actual compiler buffers are compared across TUs and to
disk after inspection; edits during inspection invalidate evidence. A coherent
build/checkout and unchanged context remain host integration preconditions.

Configured subsystem extensions preserve their existing callback API. When
`SCHGEN_CONFIGURED_SUBSYSTEMS` is enabled, its current erased extension fallback
intentionally fails purity: the extension build must supply reviewed named direct
dispatch, its constructors and source/header scope. Default builtin registries
have checked direct dispatch. This is not a flag for bypassing the gate.

Measured diagnostic baseline: all-source 245 TUs took 115 seconds/~1.19 GiB peak;
constructor closure 56 TUs took 19.5 seconds/~507 MiB peak. Each TU is disposed
before parsing the next. No unfiltered AST JSON or duplicated multi-GB tree exists.
