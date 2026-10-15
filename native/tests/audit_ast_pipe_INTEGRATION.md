# Transactional AST pipe integration

Base: `a14031a1fac9bc9929a3b8a838d8933eab44426c`. This patch changes only the
process boundary, the production AST acquisition callsite, and focused tests.
No cache, extra preprocessing, manifest/registry changes or job-cap changes.
The new audit wrapper is inline, so existing production source registration is
sufficient. Existing generic stdout consumers retain their prevalidated,
post-child-exit callback semantics.

## Production behavior

`run_process_transactional_stdout` launches the compiler with stdout on a bounded
pipe and stderr in the existing private capture. A reaper monitors the existing
child deadline independently of parsing. The caller parses speculatively into
private state; complete raw-byte UTF-8 validation and newline normalization run
as the pipe is consumed. Early parser failure/return still drains the pipe.
Every path joins the reaper and reaps the direct child. Timeout cancels its process
group; normal completion also cancels remaining group members. Orphaned descendants
are reaped by the OS, not by a process that is not their parent. A remaining open
writer is never mistaken for EOF or accepted as a complete AST.

Observed precedence is retained: child timeout/wait failure first, stdout
capture/UTF-8 failure, stderr capture/UTF-8 failure, child nonzero/signal exit,
then parser failure. A child failure discards any speculative AST and suppresses
the speculative parser exception. The production caller keeps the same
AuditSyntaxError text, TranslationUnitDecl check, visitor, macro preprocessing,
registry, ledger and manifest-order publication/error selection.

The two-worker dynamic queue is unchanged. One per-scan projection slot bounds
live AST retention: compilers can run ahead into bounded pipes, but only one
projection is parsed and semantically consumed at a time. The slot is acquired
only after output becomes available, so a slow compiler frontend cannot occupy
it while a ready sibling needs to advance the queue. AST storage is released
immediately after `Visitor::finish`, before releasing the slot; the visitor
retains no node references. This is no AST-node filtering or detector change.

Transport storage is 64 KiB per pipe reader plus the existing 64 KiB projection
reader and kernel pipe capacity. There is no raw-AST file or complete stdout
string. The retained AST and existing stderr result remain proportional to their
contents; this is not a hard total-process RSS limit. A compiler blocked on pipe
backpressure remains subject to its normal child deadline, while parser work
after child exit does not extend that deadline.

## Focused proof

- `audit_ast_pipe_contracts.cpp`: complete baseline/pipe precedence matrix for
  parser errors, late invalid stdout, invalid stderr, exit 9, signals and timeouts;
  invalid UTF-8 scalars/truncation and CRLF boundary parity; drain after callback
  failure/early return; no AST on child failure; direct-child reaping and private
  scratch cleanup; descendant cancellation; child/parser handshake proves actual
  overlap; child deadline does not become a parser deadline. The isolated proof
  also ran these checks under ASan/UBSan; ordinary CMake targets use normal flags.
- Existing `process_contracts.cpp`: all 81 generic consumer checks and existing
  text/binary checks remain unchanged and pass.
- `audit_ast_pipe_census_contracts.cpp`: links a symbol-renamed **current** frozen
  auditor, not the historical batch scheduler. Exact ordered census and diagnostic
  parity for one/two workers; real Clang mutations, registry/ledger comparisons,
  newline boundaries, malformed AST/preprocessing, timeout and manifest failures;
  both variants retain the current dynamic queue's liveness.
- `audit_ast_pipe_census.cpp`: runs the actual production scanners on a requested
  manifest with two workers, saves every ordered census tuple, and records wall
  time plus a 20 ms sample of aggregate parent/descendant RSS. Four observed child
  processes mean two Clang drivers plus their cc1 children, not four audit jobs.
  macOS sampling uses libproc; unsupported/unavailable child sampling reports zero
  aggregate RSS instead of mislabeling parent-only memory as aggregate.

The frozen baseline is vendored at
`data/audit_ast_pipe/native_cpp_audits_reference.cpp`, exactly matching
`native/src/native_cpp_audits.cpp` at the base above (SHA-256
`b7aa4e0af628895093ffb1b2294088a227ef9833ce67aff3511cb61d214bd9d6`).
CMake builds it as an independent object with only public entry-point/type names
renamed. No Git command or network access is needed at build/test time. Build
`schgen_audit_ast_pipe_contracts`, `schgen_audit_ast_pipe_census_contracts` and
`schgen_audit_ast_pipe_census`; the first two have registered CTests. The benchmark
accepts:

```
native/build/fast/schgen_audit_ast_pipe_census baseline|pipe ROOT CENSUS_OUTPUT RELATIVE_SOURCE...
```

## Counterexamples retained in the private handoff

An unrestricted two-live-AST pipe was fast (19.77 -> 9.91 s for the four-file
subset), but raised correctly sampled aggregate RSS by about 764 MiB. It failed
the agreed +512 MiB limit and is not the delivered implementation. An earlier
sampler divided the child count as if it were a byte count; those parent-only RSS
rows are explicitly invalid for aggregate memory acceptance. The corrected
sampler observes both Clang drivers and both cc1 children.

Final paired timings, exact census comparisons, compiler/base identities and
commands are in the private handoff's PROOF.md and proof/ logs. Measurements cover
quantize.cpp, pack.cpp, floorplan_build.cpp and pcb_placement_build.cpp, not a full
board. Parent compilation may run concurrently. Do not extrapolate a full-board
speedup from the subset, or treat a previous carrier/devkit gate as a test of this
patch. No full board or render was run privately.
