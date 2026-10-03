# Linux atomic pipe creation and frozen reference

Follow-up to the transactional AST pipe patch. On Linux, Pipe now creates both
original descriptors with `pipe2(fds, O_CLOEXEC)`. CLOEXEC therefore holds from
creation, including the interval before the existing F_DUPFD_CLOEXEC duplicates
are made. A sibling exec cannot inherit the transient originals even on glibc
before 2.34 without posix_spawn_file_actions_addclosefrom_np. `_GNU_SOURCE` was
already defined before includes for Linux in process.cpp.

The existing duplication loop is deliberately retained: both final descriptors
are moved above 2, originals are closed, and read-side O_NONBLOCK is set only
after creation. In particular, the child writer remains blocking. All pipe2
failures, including ENOSYS/EINVAL, fail closed with ProcessError; no pipe()+fcntl
fallback reintroduces the race. Linux with pipe2 support is required for this
transport. macOS retains pipe() plus its existing CLOEXEC-default spawn policy.
No generic-consumer semantics or production job cap changed.

New focused checks exercise all seven combinations of initially closed stdin,
stdout and stderr in isolated forked runners, verifying child output and no
unexpected inherited descriptors. Two concurrent loops run 128 sibling spawn
probes, checking descriptors 3 through 255 in exec'd children. The complete
transport suite passed 139 checks under ASan/UBSan on macOS after this change.
These macOS probes establish the unchanged remapping/transport behavior; they
do not execute the Linux pipe2 branch or constitute Linux race stress proof.
Docker is installed locally but its daemon is stopped, so no Linux runtime was
available. Linux behavior is supported here by the atomic syscall construction,
with runtime validation still to be run on Linux. No Docker daemon was started.

## Vendored C++ oracle for CMake

The file `tests/data/audit_ast_pipe/native_cpp_audits_reference.cpp` is a byte-exact
copy of native/src/native_cpp_audits.cpp at
`a14031a1fac9bc9929a3b8a838d8933eab44426c`, before pipe integration. It contains the
current streaming-file projection and dynamic queue, not the older batch backend.
It is 25,402 bytes; SHA-256:

```
b7aa4e0af628895093ffb1b2294088a227ef9833ce67aff3511cb61d214bd9d6
```

Compile the checked-in file directly. No git lookup, fetch, network or source
generation at build/configure time is needed. For a native/ CMake source root:

```cmake
set(pipe_reference "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/audit_ast_pipe/native_cpp_audits_reference.cpp")
file(SHA256 "${pipe_reference}" pipe_reference_sha256)
if(NOT pipe_reference_sha256 STREQUAL "b7aa4e0af628895093ffb1b2294088a227ef9833ce67aff3511cb61d214bd9d6")
    message(FATAL_ERROR "Frozen AST pipe reference changed")
endif()
add_library(schgen_audit_pipe_reference OBJECT "${pipe_reference}")
target_include_directories(schgen_audit_pipe_reference PRIVATE include src)
target_compile_definitions(schgen_audit_pipe_reference PRIVATE
    scan_cpp_audit_sources=scan_cpp_audit_sources_reference
    check_native_audits=check_native_audits_reference
    NativeAuditResult=NativeAuditResultReference)
target_compile_options(schgen_audit_pipe_reference PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
```

Link `$<TARGET_OBJECTS:schgen_audit_pipe_reference>` and schgen_core into the
audit_ast_pipe_census_contracts and audit_ast_pipe_census executables. The new
transport contract executable needs schgen_core but no reference object.
The object-target definitions rename exported entry points without editing the
oracle bytes. Existing native C++17 configuration applies to this target too.
