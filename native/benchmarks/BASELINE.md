# Migration performance baseline

The owner's sole authorized comparison baseline is
`0e9bbc913bab77f9cd228940db2a332d25d6bfa1`.

Earlier observations against `4bd47c33` are retained as historical evidence,
not as the requested Python-versus-C++ comparison. That later revision already
used native geometry kernels and must not substitute for the authorized commit.

## Measurement rules

- Run the original baseline implementation in its exact isolated checkout.
  Do not copy later geometry extensions, authoring code, fixtures or generated
  inputs into it. Keep the active migration checkout Python-free.
- Measure carrier and devkit_mini separately, sequentially, with the same
  render policy and external tool versions. Keep all required checks enabled.
- Record full command wall time, exit status, gate results, revision, runtime,
  concurrency and raw log paths. Never call a failed or incomplete run a
  successful build. Never substitute README estimates for observations.
- Record clean generator compilation separately from each board invocation.
  The native generator is shared by both boards, not compiled once per board.
- Native timing rows are exclusive wall intervals: nested scopes pause their
  parent and parallel work is measured around launch/join, not by adding worker
  CPU times. Source auditing, authoring auditing and actual generation calls
  are separately labelled. Mixed generation/validation stages remain mixed.
- The baseline's built-in lap labels are not pure operation timings: its PCB
  worker overlaps document/validation work, and the later PCB lap includes only
  the remaining join wait. Its lap total also excludes final ledger validation.
  External process time is the complete-command measurement.
- Original baseline and current designs differ. Preserve both original
  workloads and disclose sheet/part/net counts, dimensions and design-input
  differences; revision-to-revision elapsed changes are not by themselves
  same-input language speedups.
- Percentage change is `(current_seconds - baseline_seconds) /
  baseline_seconds * 100`; negative is faster. Publish no percentage until
  both named measurements exist, and retain every raw sample.

Timing instrumentation never disables a gate or turns a failed audit green.
