# Occupancy precision proof

The six operations are checked by `native_occupancy_precision_contracts`.
It independently instruments their compiled function entries and compares those
entries against the producer's exported counters. Real carrier, devkit,
single-side devkit and fixed-outline devkit solves must attribute all work to
the floorplan invocation and import it exactly once. No observer is linked into
the production CLI. Rejected searches, losing candidates, copied geometry,
counter overflow and cached-render replay have separate checks.

The small geometry probe's immutable digest is `fee57f87ab3a0aa5` (FNV-1a over
explicit little-endian words, including binary double values and decision order).
It was captured before integration by compiling the same scenario against the
pre-extraction sources, then comparing the independent before/after executables.
The original files match commit `d03678af`:

- `native/src/occupancy.cpp`: Git blob `fea7e9a7c2d2a44cbc2cf35f7969afb377a45f42`
- `native/src/pack_refine.cpp`: Git blob `147491e4be14a336438def17701c047ba2257a23`

The prepared private patch passed 3,129 strict checks and its ASan/UBSan run;
all three private digests matched. Those sanitizer results precede the later
integration changes and do not claim sanitizer coverage of the entire engine.
Integration additionally tests invalid conversion before single-rectangle
insertion and insertion/query/removal at the INT_MAX bucket boundary.

Existing geometry, ledger-byte and prior-count fixtures are unchanged. Their
adapters separate only these six named additions, whose counts are independently
verified by the new full-solve entry observer; no historical count is replaced.
The registry test binds each exact source identity/arity and executes each real
scalar implementation. The native policy audit also scans this implementation.
