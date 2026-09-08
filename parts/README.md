# parts/ — the component library

One folder per physical component, named by its **manufacturer part number**
(MPN). Each folder is self-contained and fully **generated** from the part's
LCSC/EasyEDA data — nothing here is hand-edited; re-run the generator to update
a part.

```
parts/FUSB302BMPX/
  part.json                 # metadata + pin table (compiled into native/catalog.bin)
  FUSB302BMPX.kicad_sym     # schematic symbol
  FUSB302BMPX.kicad_mod     # footprint (pads exact to the physical part)
  FUSB302BMPX.step          # 3D model (MCAD)
  FUSB302BMPX.wrl           # 3D model (KiCad viewer)
  FUSB302BMPX.easyeda.json  # raw EasyEDA API response (provenance + offline regen)
```

`part.json` is the authored electrical contract (`schema: schgen.part/1`).
`scripts/build_native.sh` compiles every `parts/*/part.json` into
`native/catalog.bin` (interned strings, pin tables, mmap). Runtime `use_part`
looks up that binary — it does not parse JSON or exec Python. Required fields:
`mpn`, `safe_name`, `lcsc`, `description`, `manufacturer`, `package`,
`jlc_class`, `prefix`, `datasheet`, `product_url`, `lib_id`, `footprint`,
`models_3d`, and `pins` (`num` / `name` / `etype`). Unknown keys fail the
compile. Footprint copper stays in `.kicad_mod` (sexpr).

## Adding a part

Find the part on lcsc.com / jlcpcb.com/parts, note its `C`-number, and run:

```bash
PYTHONPATH=. python -m schgen part add C132291
```

This is the whole pipeline (`schgen/partlib/part_gen.py`): fetch the CAD
payload from the public EasyEDA component API, parse it, and write the
`parts/<MPN>/` folder. It either produces a complete folder or fails — no
partial output.

For a network-free, byte-stable regeneration, point it at the cached payload:

```bash
PYTHONPATH=. python -m schgen part add C132291 \
  --from-json parts/FUSB302BMPX/FUSB302BMPX.easyeda.json
```

## What the generator produces

- **Symbol (`.kicad_sym`)** — drawn by the generator's own layout rules, not a
  copy of the EasyEDA drawing. Every pin connection point sits on the 1.27 mm
  grid; pins are grouped left = inputs, right = outputs/signals, top = power
  rails, bottom = GND/NC; the body is sized so pin-name text from opposite sides
  can never collide. Two-pin parts and R/C/L/FB prefixes are forced `passive`,
  and protection/ESD arrays that EasyEDA mislabels as all-`input` are
  normalized to `passive` (an all-input table is electrically impossible).
  Before the folder is accepted the symbol is loaded through
  `schgen.core.symbols.Library`, so the build never ships a symbol its own
  loader would reject.

- **Footprint (`.kicad_mod`)** — a faithful conversion of the EasyEDA land:
  pad positions, shapes, drills, slots, and silk/fab/courtyard graphics are
  converted exactly; only decorative lead/paste fills are dropped. A large SMD
  pad (>= 2.0 mm on both sides — exposed/thermal pads, connector tabs) gets
  copper + mask plus a windowed paste grid instead of one full aperture, so it
  does not float or squeeze out under reflow (IPC-7525 paste-volume control).

- **3D model (`.step` + `.wrl`)** — downloaded from EasyEDA when hosted. The
  footprint references the `.wrl` for the KiCad viewer and carries the `.step`
  for MCAD export. An implausible model offset (an EasyEDA unit mismatch that
  would plant a centered package a metre off its pads) is reset to the origin.

### Synthesized EP pad and polarity silk

Some EasyEDA lands omit a center exposed/thermal pad that the datasheet does
dimension, or drop a polarity `+` glyph on the import. The generator
re-synthesizes these from a **datasheet-cited, LCSC-keyed allowlist**
(`PACKAGE_EP`, `PACKAGE_SILK_PLUS` in `part_gen.py`), so the EP lands as a real
pad **and** a real symbol pin nettable to GND — never a prose layout note — and
the `+` lands on `F.SilkS` so a polarized part cannot be inserted reversed. Any
part not on the allowlist regenerates byte-identically; this keeps both fixes
auditable and scoped to the exact parts that need them.

## How parts are used

Subsystems never vendor a symbol into a sheet. They reference a part by MPN:

```python
self.use_part("FUSB302BMPX", "U1")
```

`use_part()` (`schgen/core/model.py`) mmaps `native/catalog.bin` and takes the
`lib_id`, `footprint`, reference prefix, LCSC code, and the **named** pin table
from the compiled record. Inline part metadata is rejected. A missing
`part.json` or a stale/absent catalog is a build error that names
`schgen part add` / `scripts/build_native.sh`. Because the pin table is named,
sheets wire pins by name and the build validates them against the symbol. The
`LCSC` code carried on every part keys the BOM and the datasheet ratings
checks, so a part's orderable identity can never drift from its library folder.
