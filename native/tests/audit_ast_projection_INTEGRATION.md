# Streaming Clang AST projection — field-only checkpoint

This is an allocation optimization, **not a source-audit policy change**.
It preserves every `inner` node, including all header, global, anonymous,
lambda, macro-expansion and unrelated-namespace nodes. There is no source or
namespace exclusion, subtree pruning, declaration generation or coverage waiver.
Clang must still emit its **unfiltered** translation-unit AST.

## Parent-owned integration

1. Add `src/audit_ast_projection.cpp` to `schgen_core`.
2. In `native_cpp_audits.cpp`, include `schgen/audit_ast_projection.hpp` and
   replace only:

   ```cpp
   const auto ast=parse_json_text(compiled.stdout_text,path.string()+" compiler AST");
   ```

   with:

   ```cpp
   const auto ast=parse_audit_ast_projection(compiled.stdout_text,path.string()+" compiler AST");
   ```

   Keep the translation-unit-kind check, both visitor passes, `finish`, macro
   preprocessing, manifest validation and all audit gates unchanged. No public
   result layout or process API changes are required. The input `string_view`
   is borrowed only during parsing; the returned tree owns all its strings.
3. Add the parser test executable from `tests/audit_ast_projection_contracts.cpp`,
   linked to `schgen_core`, and register it in CTest.
4. Add a **separate executable** from `tests/audit_ast_projection_census.cpp`,
   linked to the ordinary static `schgen_core` (do not force-load the archive).
   Its source deliberately includes the actual visitor implementation once so
   it can apply the same unmodified visitor to both DOMs. Do **not** also compile
   `native_cpp_audits.cpp` as another source in this executable.
   Register `EXE --selftest REPOSITORY_ROOT` as the small live-Clang contract.
   `native/src` must be on this target's private include path.

Apply C++17, `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off` as usual.
The compiler census executable is test-only, never a production fallback.
There are no new third-party dependencies, Python inputs or runtime processes
beyond the already-required native Clang audit.

## Parser contract

`parse_audit_ast_projection(string_view, source_name, optional_stats)` builds
only the visitor's reviewed field set, but validates the entire JSON input.
Discarded fields are parsed without allocating their values. All object keys
still participate in duplicate-key detection, including escape-equivalent keys.
Strings validate UTF-8 and surrogate pairs even in skipped subtrees. Invalid or
truncated JSON, trailing content, nonrepresentable numbers and nesting beyond
1024 levels throw. Stats are published only after a complete successful parse.

Preserved fields are enumerated in the public schema predicate and independently
in the parser tests. Source identity retains `loc`, `range.begin`, `expansionLoc`,
`offset`, `file`, `includedFrom`; context identity retains `id`, `previousDecl`,
`parentDeclContextId`, names, mangled names, kinds and types. The visitor does not
read `spellingLoc`, `range.end`, line/column numbers, value categories or definition
metadata. It derives line numbers from the original source and retained offsets.

The enum correction following `2aa404a4` uses only `kind` and `inner`, both already
retained. Future visitor field reads require explicit schema review and the exact
census proof; do not assume a new property is retained automatically.

## Independent proof and reproduction

The pre-enum oracle is the actual visitor at `2aa404a4`, SHA-256:
`69e7c084e6c0bf919f51c5e39245ffb8572dc47a32c696cc971b6ceda4b1461a`.
Its private snapshot and a source/header snapshot of that commit live under
`/private/tmp/schgen-ast-projection.BgjhEZ`. The frozen oracle build uses
`-DSCHGEN_AUDIT_VISITOR_SOURCE="/absolute/path/native_cpp_audits_frozen.cpp"`.
For this historical 55-file run, compile `board_policy_metadata.cpp` from the
same frozen snapshot as well; later production manifests legitimately add new
sources. The proof directory retains its exact `manifest.txt`.
Supporting symbols come from the preserved private core archive, not a running
shared build. A second test build uses the current enum-aware visitor.

The private proof-only loop at
`/private/tmp/schgen-ast-projection.BgjhEZ/run_manifest_proof.sh`
(`EXE FROZEN_ROOT PRIVATE_OUTPUT`) iterates the
explicit 55-file policy manifest. Each file is compiled **once**, with no dump
filter; raw/projected visitor executions then consume exactly the same AST and
preprocessor bytes in separate processes. It compares every ordered constant
tuple `(symbol, site, buried)`, function identity, and ordered quantization tuple
`(site, function, detector)`, including duplicate populations and macro policies.
It separately compares all `inner`-tree node counts. Complete tuples, source/AST
hashes, times and peak RSS are retained in private output; large temporary AST
captures are reclaimed after use. This output is proof, not registry input.
The loop is deliberately **not a repository deliverable**: production and
permanent contract executables are C++ only. A future permanent manifest runner
belongs in the existing C++ census driver, not a new shell tool.

The small adversarial fixtures cover global/anonymous/unrelated policies,
header/main source inheritance, macro expansion, Unicode, semantic out-of-line
class ownership, overloads, local shadows, lambdas, numeric aliases, engineering
defaults, ordinal/physical enums and raw precision. Every object is also tested
with its keys reversed, with array order preserved. Explicit independent negative
assertions ensure uncovered constants/quantization still fail.

## Scope of performance claims

Capture is deliberately separated from parsing. Parent owns the bulk-read/CRLF
process fix; this worker did not modify `process.cpp` or shared process APIs.
This checkpoint only reduces the materialized DOM, not the raw captured stdout.
No included-header expression is pruned. Any later semantic pruning requires a
new exact-census proof against the full visitor, especially for declaration
contexts, macro/source re-entry and helper scans that inspect descendant nodes.

The recommended next memory step is a bounded-buffer `istream` overload, paired
with a **parent-owned** capture-consumer boundary: after reaping Clang and checking
its exit code, invoke the parser while the existing private stdout capture still
exists. `run_process` currently deletes that file before returning its strings;
it cannot safely provide a filename for later consumption without a lifetime/API
change. Keep process isolation, timeout/group killing, stderr diagnostics, strict
UTF-8 and RAII cleanup. Do not run a second compiler, shell-redirection workaround,
or header-filtered dump. This proposal is not implemented by the field-only
checkpoint and is not included in its memory claims.

Measured proof results are recorded below only after their runs finish.

- **18,440 parser contracts PASS** in strict optimized and ASan+UBSan builds.
  This instruments the projector, JSON reference parser and parser test itself;
  it is not a whole-engine sanitizer claim.
- **31 live Clang census contracts PASS** using the current enum-aware visitor,
  including exact semantic-error propagation and reversed object key order.
- Private one-call integration substitution into the actual current visitor:
  **22 existing enum contracts PASS** and **36 existing identity/storage
  contracts PASS**. No shared source or build changed for these checks.
- On the independent adversarial fixture, old versus current visitor differs
  only by the approved removal of `StateTag::Idle` and `StateTag::Busy` (18 versus
  16 constants). Both retain the two explicitly numeric `Physical` constants,
  all ten functions and all thirteen quantization tuples. Raw/projected results
  match within each visitor version.
- **55/55 frozen manifest files PASS**, including macro preprocessing: exact
  ordered census tuples and exact node populations. The complete sweep processed
  84,299,989,888 AST bytes and retained all **52,534,325 inner nodes**. Both sides
  produced **87 constants, 701 function identities and 622 quantization tuples**.
  These are census facts, not a claim that their policy coverage passes.
  Log: `/private/tmp/schgen-ast-projection.BgjhEZ/manifest-proof.log`.
- **4/4 current enum/precision files PASS**, using the same current visitor on
  each full/projected AST: `precision_ops.cpp`, `floorplan_cross.cpp`,
  `pcb_placement_breathe.cpp`, `floorplan_internal.hpp`. The new standalone
  precision unit contributes six function bodies and fourteen precision-site
  tuples identically on both sides. Log:
  `/private/tmp/schgen-ast-projection.BgjhEZ/current-precision-proof.log`.
- The complete **56-file enum-aware replay PASS** uses a separate private source
  snapshot and the same visitor on both ASTs: 52,856,766 nodes, 83 constants,
  713 functions, 602 quantization tuples, all exact. This is before the parent's
  later character-zero semantic correction. Aggregate parse+visitor times were
  158.009867s / 112.056110s; peak RSS 6,985,285,632 / 4,901,797,888 bytes. Log:
  `/private/tmp/schgen-ast-projection.BgjhEZ/current-manifest-proof.log`.
- Across that sweep, summed parse time was **140.53s raw / 95.01s projected**;
  summed parse+visitor/report time was **160.64s / 106.80s**. These exclude Clang,
  initial bulk file read, destruction and the proof's AST hashing. The processes
  ran on a shared machine, so these are observed measurements, not guarantees.
- **Worst raw-RSS unit:** `pcb_placement_model.cpp`, input 2,664,265,469 bytes.
  Peak RSS was **6,653,247,488 / 4,681,318,400 bytes**; parse+visitor/report time
  **4.638s / 3.220s** (raw / projected). Every census tuple and all 1,681,189
  `inner` nodes matched.
- **Largest input and slowest raw visitor unit:** `pcb_placement_build.cpp`,
  input 2,781,945,735 bytes. Peak RSS was **6,267,797,504 / 4,899,995,648 bytes**;
  parse+visitor/report time **5.632s / 3.352s**. All 1,756,877 nodes and tuples
  matched. The remaining multi-GB raw buffer is why a capture-file consumer is
  still worthwhile; this checkpoint does not claim to eliminate that buffer.

Frozen production file SHA-256:

```text
4ae6e0350662a2e1fd819a9f67c9f4cde1b31e19536d2a60076c646753431368  native/include/schgen/audit_ast_projection.hpp
8cdbdcdff617a85fa2ff28af7b7db4cb6becfdb162a2b2c379a5fb69bf6a9912  native/src/audit_ast_projection.cpp
```
