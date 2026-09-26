# Scoped stdout capture and bounded AST reader

## Ready parent-owned boundary wiring

All production implementation is in existing compiled sources:
`src/process.cpp` and `src/audit_ast_projection.cpp`. No new library dependency,
source registration, existing struct-layout change, CLI change or global hook.
The worker has **not edited** `native_cpp_audits.cpp`.

Replace its AST capture/parse boundary only; retain the current visitor (including
the parent's character-zero correction), macro pass, flags, gates and failures:

```cpp
JsonNode ast;
const auto compiled=run_process_consume_stdout(command,
    [&](std::istream& input){
        ast=parse_audit_ast_projection(input,path.string()+" compiler AST");
    },options.timeout);
if(compiled.exit_code!=0)
    throw AuditSyntaxError(path.string()+": C++ compiler failed ("+
        std::to_string(compiled.exit_code)+")\n"+compiled.stderr_text);
if(text(ast,"kind")!="TranslationUnitDecl")
    throw AuditSyntaxError(path.string()+": compiler did not return a translation-unit AST");
```

The callback runs exactly once **only on child exit 0**, after complete stdout
AND stderr strict UTF-8 validation. A nonzero/signal exit returns its signed code
and normalized stderr without trying to parse incomplete stdout. Spawn, stdin,
process-group isolation, timeout/killing/reaping and scratch RAII use the same
existing implementation path. Consumer exceptions propagate and scratch is still
removed. Validation happens before the callback even if it would ignore output.
The child timeout retains its existing meaning; it does not time the parser.

`ProcessConsumedResult` is a new type containing only `exit_code` and
`stderr_text`; there is intentionally no giant `stdout_text`. Its callback gets a
borrowed, read-only, non-seekable text stream, not a filename, ownership handle,
output mutator or global callback. Neither stream nor buffer may escape the call.
Universal-newline normalization is identical to `run_process`, including CRLF
crossing buffer boundaries, lone CR and embedded NUL. `run_process` and
`run_process_bytes` retain their old interfaces and behavior.

The AST overload takes `std::istream&` and has a 64 KiB input window. Memory and
stream overloads share **one grammar and validator**. All 28 projected fields and
every `inner` node remain, including included headers, global/anonymous namespaces,
semantic parent IDs and source locations. It consumes through EOF and rejects
I/O failures, malformed/truncated data, duplicate keys, invalid UTF-8/Unicode,
nonrepresentable numbers and excessive depth. Stats publish only on success.
The complete projected tree still occupies memory; this is not subtree pruning.

For strict UTF-8-before-callback semantics, stdout is validated in one bounded
read, then reread through the normalized stream. No full-input string, compacted
JSON intermediate, second compiler run or secondary stdout file is created.

## Independent tests and measured evidence

Scratch: `/private/tmp/schgen-stream-capture.YC742K`. All builds are isolated,
C++17, `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`. Supporting archive:
`/private/tmp/schgen-board-policy.4YFXrh/libschgen_core.a`.

- **70,171 parser contracts PASS**, strict and ASan+UBSan. They compare both
  overloads with the independent full JSON parser, exercise valid/invalid tokens,
  skipped payloads, surrogate pairs/raw UTF-8, numbers and duplicate keys crossing
  64 KiB boundaries, long retained/discarded strings, I/O failures, caller EOF
  exception masks, reversed field order and stats rollback.
- **37 live Clang census checks PASS**, including the real scoped consumer path,
  complete tuple/node equality, and independent unregistered-policy negatives.
- Real scoped-stream production captures also match the preserved full-parser
  censuses for `precision_ops.cpp` (321,958 nodes, six bodies, fourteen precision
  tuples) and `floorplan_internal.hpp` (1,061,418 nodes, 31 constants), not just
  the largest unit. They peak at 491,241,472 and 1,289,207,808 bytes respectively.
- Existing text/binary process contracts and **81 new consumer checks PASS** in
  strict and ASan+UBSan builds. New consumer tests cover
  full validation before callback, early consumer exit, UTF-8 boundaries,
  normalization/NUL, callback count/exception, private 0700/0600 permissions,
  scratch cleanup, signed signal exit, nonzero diagnostics, timeout/reaping and
  argument errors. Sanitizers instrument the process implementation and its test.

The preserved visitor is the enum-aware, **pre-character-zero-fix** snapshot
`/private/tmp/schgen-ast-projection.BgjhEZ/current-source/native/src/native_cpp_audits.cpp`
(SHA-256 `c170f19465bc172d4ee7f66c24f42dddda58663612ee8333d330a24141d0c952`).
Do not mix semantic deltas with parser equivalence. The stream parser already
preserves numeric JSON `value` and its kind, so the character correction requires
no schema exemption or parser change.

The worst measured source unit is `pcb_placement_build.cpp`, with a complete
2,782,939,959-byte unfiltered AST. Raw historical, current in-memory projection,
file-stream projection and real-process stream results have **exactly identical
complete census tuples and all 1,756,877 nodes**. No normalization/deduplication of
the comparison is applied.

Real-process A/B, including Clang compilation, capture, parsing, visitor, macro
preprocessing and census publication (separate processes, same source/compiler):

- Retained-string projection: **12.4352 s; 4,902,125,568-byte peak RSS**.
- Scoped streamed projection: **12.6758 s; 2,119,122,944-byte peak RSS**.

This observation reduces peak RSS **56.8%** with approximately flat end-to-end
time (2% higher in this pair); it is **not a speedup claim**. The standalone stream
parser's timer includes file reading, unlike the old memory-parser timer, so those
two timing columns must not be used as an end-to-end comparison. Machine load can
affect individual timings. Metrics and full tuples are in `worst.process-*` in
the scratch directory. The existing C++ census driver now supports:

```text
--census raw|projected|stream AST_JSON ABSOLUTE_SOURCE RELATIVE_SOURCE OUTPUT [PREPROCESSED]
--compile-census projected|stream ROOT RELATIVE_SOURCE OUTPUT
```

No new permanent shell helper was added. The earlier private manifest loop remains
private; porting that batch loop is not required for this memory fix.

Frozen production SHA-256:

```text
debfd7c497d6bb4482055c2f66ff383a3c886c4e48fd58e69606b39d718f29b2  native/include/schgen/process.hpp
bb393b93f92f3f243db3f5035af12d8034ceb718707ab1ceabc47a432b9fa64e  native/src/process.cpp
09358204081ccf8a3e556e554f57c023bd2a4faf99272064d2ddb679ffbbd546  native/include/schgen/audit_ast_projection.hpp
494d3801540d565487cf7fe0d933cad1e864e5477112a242ff0cd0f1b97c24e9  native/src/audit_ast_projection.cpp
```

## Earlier completed manifest proof (not a coverage waiver)

The pre-enum 55-file proof passed all tuples/nodes. The complete subsequent
**56-file enum-aware proof also passed**: 52,856,766 nodes, 83 constants, 713
functions and 602 quantization tuples. It compared full JSON and field-only
projection before the streaming overload and before the parent's character fix.
Aggregate parse+visitor times were 158.009867 s / 112.056110 s; maximum RSS was
6,985,285,632 / 4,901,797,888 bytes. Logs and per-file exact tuples remain in
`/private/tmp/schgen-ast-projection.BgjhEZ/current-manifest-proof*`.
The stream-specific proof is separately stated above; it does not claim another
complete 56-file replay or a passing board policy/ledger gate.
