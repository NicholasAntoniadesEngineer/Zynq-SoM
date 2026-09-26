# Placement precision provenance

This is new additive evidence; no earlier fixture has been rewritten.

The baseline executable was compiled against the frozen pre-extraction six placement
consumers and captured successfully BEFORE the production draft was applied to the
candidate. Snapshot HEAD was 774f0d12e46725b75491c9b584c18b0015c3d42e plus the
then-applied stage, legalizer, constants and numeric working changes.
The exact existing combined core archive was copied privately:
8088be32804eb7589a2dbaf1acfa0c17cb1696f0be4a46b10de3d88922fb9e62 (SHA-256).

legacy_output.txt SHA-256:
8f5db9a4cd9691b42c65cde083bd0e3d0818e85db07393fc01caa26414aa9c50

additive_counts.json SHA-256:
0ae66b0d03f6b31b7c6ac73c26e51d4464b2e080264c871636797673431128a8

The baseline captures devkit_mini, carrier, single-sided devkit_mini, and fixed-outline
devkit_mini; offered shapes, footprint bytes, complete model/floorplan typed output,
ledger/spec bytes, every placement checkpoint's binary64 pose bits, fallback events,
and every prior accounting family. Synthetic inputs exercise connector directions,
member-mirror rejection, bottom/lift variants, and pure turns. The real-footprint
eviction probe forces four exits x nine rejected trials x two coordinates = 72 calls.

Only the 19 exact new placement_precision_fixture names are separated from old counts.
Scalar-only tests do not establish consumer coverage: all 19 names must also occur in
real/synthetic consumer receipts. No prefix filters, registry waivers, scanner-derived
registrations or old-count rewrites are used.

The additive JSON was emitted only after each receipt equaled independent compiled
function-entry observations. Only placement_precision.cpp was compiled with
-finstrument-functions-after-inlining; callers were separate TUs without LTO.
The normal optimized uninstrumented build then passed the same exact baseline and
additive expectations. Counter ownership/replay checks remain active in both builds.
No runtime-performance claim is made.

Private reproduction evidence:
 /private/tmp/placement-precision.x685Rv/proof/
 baseline.txt, baseline.log, after-capture.log, after.log, plain.log, build.sh.

Parent integration: build placement_precision_contracts.cpp with native/src includes,
schgen_core plus a separate observed placement_precision.cpp object (follow existing
stage/occupancy observed-object conventions). Do not define PLACEMENT_PRECISION_BASELINE
or PLACEMENT_PRECISION_PLAIN in the instrumented integrated test. Pass repository root.
The source contract takes [before-root] after-root and performs a real compiler census.
Production registry, registry-size assertions and CMake remain parent-owned.

