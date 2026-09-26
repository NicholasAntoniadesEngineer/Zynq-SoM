# U30001 genuine model repair — inspected, not applied

The installed stock footprint exists, but its referenced WQFN-14 STEP does not.
The repository already contains the correct **FUSB302BMPX-associated** assets:

- `parts/FUSB302BMPX/FUSB302BMPX.wrl`, SHA-256
  `9208a410339d292bf0fbb899b3641b7d96c4cccb9ecd86b779ac635b5f5b1066`.
- `parts/FUSB302BMPX/FUSB302BMPX.step`, SHA-256
  `72d013515fab7645e63297dfc5d32c7a1111caeb6cde5795493ba0070554c3c7`.

Provenance is repository data, not a filename guess: `part.json` associates both
files with MPN FUSB302BMPX, LCSC C132291, onsemi and package
`MLP-14_L2.5-W2.5-P0.50-BL-EP`. The original EasyEDA record has that MPN and
package and links 3D UUID `15f87957851c46e8a4907d2de7265707`, title
`MLP-14_L2.5-W2.5-H0.8-P0.50`. The actual STEP header/product agrees and identifies
SolidWorks/STEP AP214. This is the part-linked EasyEDA CAD asset, not a claim of
manufacturer-certified CAD. No unrelated 14-pin model is proposed.

## Exact model-only repair

Retain U30001's actual FUSB302BMPX value and existing stock footprint, pad numbers,
pad geometry, nets and placement. Replace **only its 3D model clause** with:

```scheme
(model "${KIPRJMOD}/../parts/FUSB302BMPX/FUSB302BMPX.wrl"
  (offset (xyz 0 0 0))
  (scale (xyz 1 1 1))
  (rotate (xyz 0 0 90)))
```

Keep the sibling STEP asset unchanged. Native `export_board_step` uses KiCad's
`--subst-models` to import that actual STEP for mechanical export. This is a
genuine model reference repair, not a missing-model waiver or placeholder.

**Z=90 degrees is required.** Custom and stock footprints have the same 14 lead
numbers plus EP but different orientation/land patterns. For example custom pad
1 is `(-0.4999, +1.1775)`; stock pad 1 is `(-1.2625, -0.5)`. All 14 numbered
pad positions match the quarter-turn relation `(-y,x)` within 0.086 mm (the
radial land-center difference is about 0.085 mm). Stock EP is centered and 1.45
mm; the custom footprint uses 1.375004 mm. Therefore **do not switch the entire
footprint to the custom part as a shortcut**: that would change copper.

The native KiCad orientation probe renders the actual model against the stock
footprint. Measured pin-1 marker centroids, normalized within each top image:

- Model Z=0: `(0.297855, 0.700869)` — lower-left, wrong for stock pad 1.
- Model Z=90: `(0.297890, 0.298564)` — upper-left, correct.
- Model Z=270: `(0.700161, 0.700835)` — lower-right, wrong.

The real STEP also renders at Z=90 with the marker at the same upper-left corner;
it retains its source EasyEDA surface marking. WRL XY envelope is 2.52019 mm
square and passes native fit/placement checks against the actual stock footprint.
Native KiCad/OpenCascade export using the sibling STEP preserves product
`MLP-14_L2.5-W2.5-H0.8-P0.50` in a 654,799-byte board STEP.

Persist the repair in a project-owned, part-and-footprint-specific model override
or footprint overlay before emission (existing copy point:
`native/src/pcb_embed.cpp`, `Sexpr doc = i.mod->document`). Key it to the genuine
part and exact stock footprint, not every WQFN package. Do not edit installed
KiCad libraries or only patch a generated board that regeneration overwrites.
The authoring choice is `native/src/subsystem_authoring_usb_pd.cpp:11`; keep its
stock copper footprint selection. Parent owns the production integration.

## Proof and one parser limitation

Read-only native probe source: `native/tests/model3d_fusb302_repair_probe.cpp`.
It uses the existing immutable core archive and isolated objects, actual KiCad
rendering, native STEP export and libpng centroid measurement. No Python is run.
Generated probes and logs live only under
`/private/tmp/native-render-models.6MVTPP/fusb302-final` and
`/private/tmp/native-render-models.6MVTPP/fusb302-final.log`.

**Final probe PASS:** the scratch Carrier with exactly this model-only repair
renders **8/8 actual native views**, with no missing-model exception or waiver.
The original Carrier PCB remains byte-identical (SHA-256
`4b45325d224e6376dc43b871484357fad50b1705b37b0389e2c746683c4022f7`).
Both hardware asset hashes above also remain unchanged.

The original SolidWorks STEP uses legal whitespace around `CARTESIAN_POINT (`.
The accepted legacy XY-envelope parser only recognizes compact STEP syntax, so a
**direct `.step` reference would currently be rejected as unmeasurable by that
preflight** despite successful native KiCad import. The recommended WRL reference
plus sibling STEP substitution is tested and does not waive any check. Do not
normalize/rewrite the genuine STEP bytes merely to suit the legacy regex. A
general whitespace-tolerant STEP measurement extension would be a separate
core change coordinated with the parent. The native inspection found 3,130 STEP
coordinate points; their envelope includes CAD construction/control points and
must not be mistaken for exact solid extents.

No source PCB, authoring code, footprint, STEP, WRL or installed library has been
modified. The emitted board in the probe is a scratch copy; only the target model
clause changes semantically, with other KIPRJMOD paths made absolute solely to
keep their original assets resolving from the scratch directory.
