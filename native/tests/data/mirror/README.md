# Footprint mirror contracts

`real_parts.json` freezes the original Python transform at commit `317bd055`
for five actual asymmetric footprints before changing the production adapter.
The fixture contains source bytes, normalized source and expected mirrored
bytes; tests never invoke Python or regenerate their expected results.

The native tests additionally pin all supported custom-pad primitive transforms,
angle signs, unchanged layers and unchanged model offsets/rotations. They reject
unknown footprint/pad/primitive children, offset drills, chamfer/rect-delta and
legacy arc geometry. Two intentional correctness improvements are contracted:
failure cannot partly mutate the caller's document, and source-file edits cannot
return stale geometry from a process-global path-only cache. Atomic publication
preserves an earlier valid output after a failed transform and does not rewrite
identical bytes.
