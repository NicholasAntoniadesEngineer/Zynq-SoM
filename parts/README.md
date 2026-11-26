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
The native CMake build described in [the build guide](../native/ci/README.md)
compiles every `parts/*/part.json` into
`native/catalog.bin` (interned strings, pin tables, mmap). Runtime `use_part`
looks up that binary — it does not parse JSON or exec Python. Required fields:
`mpn`, `safe_name`, `lcsc`, `description`, `manufacturer`, `package`,
`jlc_class`, `prefix`, `datasheet`, `product_url`, `lib_id`, `footprint`,
`models_3d`, and `pins` (`num` / `name` / `etype`). Unknown keys fail the
compile. Footprint copper stays in `.kicad_mod` (sexpr).

## Adding a part

Find the part on lcsc.com / jlcpcb.com/parts, note its `C`-number, and run:

```bash
native/bin/schgen part-import --parts-root parts --lcsc C132291 --catalog native/catalog.bin
```

This is the native part-import pipeline: fetch the CAD
payload from the public EasyEDA component API, parse it, and write the
`parts/<MPN>/` folder. It either produces a complete folder or fails — no
partial package output. Existing packages require explicit `--overwrite`.
The optional `--catalog` refresh happens after package publication; a catalog
refresh failure returns an error but does not undo the published package.

For a network-free, byte-stable regeneration, point it at the cached payload:

```bash
native/bin/schgen part-import --parts-root parts \
  --from-json parts/FUSB302BMPX/FUSB302BMPX.easyeda.json \
  --overwrite --catalog native/catalog.bin
```

Run these commands from the repository root. The cached-payload command explicitly
replaces an existing package; omit `--overwrite` when replacement is not intended.
To refresh only the catalog after changing part metadata:

```sh
native/bin/schgen catalog-compile parts native/catalog.bin
```

## Part facts (`part_facts.json`)

`parts/part_facts.json` (`schema: schgen.part_facts/6`) is the one reviewed,
hand-kept file in this folder. It holds what the generator cannot know:

- `classes` — the class of every schematic symbol the boards may place, keyed
  by symbol id (`Device:R`, `TF-01A:TF-01A`). The class is one of `resistor`,
  `capacitor`, `inductor`, `ferrite`, `transformer`, `diode`, `led`,
  `transistor`, `integrated_circuit`, `connector`, `header`,
  `module_connector`, `switch`, `test_point`, `crystal`, `battery_holder`,
  `mounting_hole`, `fiducial`. A `connector` mates with a cable or card from
  outside the board; a `header` is a pin header reached from above. The key is
  the symbol id because that is the one identity every authored part carries:
  a part authored with a stock KiCad symbol keeps no link to a part folder.
- `connectors` — one entry per `connector` symbol, keyed by part name (the
  symbol `TF-01A:TF-01A` is entry `TF-01A`): `mating_face` (`+X`, `-X`, `+Y`
  or `-Y`, the direction the mouth faces at rotation 0, or `+Z` for a part
  mated from above, which is never edge-pinned), `edge_pinned` (the
  floorplan pins the part to a board edge), `overmold` (a cable plug overmold
  spacing rule applies), `pad_row_face_check` (the mating face is cross-checked
  against the pad rows), `handling` (how a person mates it: `grip_sides`,
  `latch`, `card`, `flat_cable`, `pins` or `none`; the board's access
  statements are keyed by it), the optional `mating` block (`plug_width_mm`,
  `plug_depth_mm`, `plug_height_mm`, each a number or `null` when the drawing
  does not give it, and `cite`, required when a number is given), the optional
  `access` block (`side_mm`, `front_mm`, `cite`: a document's figure for this
  part, which wins over the board's statement for its handling class), and the
  optional strings `description` (required when
  edge-pinned; the floorplan edge table), `numbered_label` (silk label stem,
  numbered across the board) and `pair_label` (name of a two-part IN/OUT pair
  in the assembly notes).
- `plug_paths` — keyed by part number (the name of the part's folder), one
  entry per part that a plug, card or cell enters from the side, connector or
  not: `entry` (`face`: `+X`, `-X`, `+Y` or `-Y`, the side of the footprint at
  rotation 0 that the thing arrives over), `depth` (how far in front of that
  side the path runs), the optional `width` (across the mouth; the width of
  the courtyard when left out) and `clear_height` (a part on the same face no
  taller than this may stand in the path). Every one is an object with `mm`
  (`face` for the entry) and its own `cite`. The layout keeps the path on the
  board and free of taller parts, and the `plug_path` board gate reports each
  path with its measured clearance. A `connector` whose `mating_face` is
  lateral must be edge-pinned or have an entry here on the same face.
- `stated_heights` — the height above the board face, in millimetres, of every
  footprint that names no 3D model, keyed by footprint id, each with its
  `basis` and the date it was `reviewed`.
- `thermal` — keyed by part number (the name of the part's folder), one entry
  per part whose junction temperature is checked: `rth_ja`, `tj_max`, `rds_on`
  and `eff`, the `package` and the `cite` of the datasheet, and an optional
  `pour` (`rth_ja`, `cite`, `evidence`) that holds the lower thermal resistance
  credited once the emitted copper is verified.
- `thermal_copper` — keyed by part number: `need` (`min_vias`, `radius_mm`,
  `pour_layers`, what the copper audit looks for) and `field` (`via_offsets_mm`,
  `max_vias`, `pour_box_mm` as x0, y0, x1, y1, `pour_layers`, `cite`, what the
  emitter places).
- `ep_vias` — keyed by part number: `min_pads` ground via pads within
  `radius_mm` of the part's centre.

  `thermal_copper` and `ep_vias` find a placed part by the `label` of the
  part's `regulators` entry: a part whose value begins with that label. A row
  whose part has no `regulators` entry is refused, naming the part.
- `isolation` — keyed by part number: `margin_mm`, the margin of the plane void
  under the part's courtyard.
- `regulators` — keyed by part number: `kind` (one of `buck`, `ldo`,
  `load_switch`, `efuse`, `led_boost`), `label` (the short device name the
  checks print), `eff`, `in_pin`, `out_pin`, `ilim_num`, `note`, and optionally
  `limit_a`, `iset_pin`, `fb_vref`, `out_v`, `iset_v` and `enable`: a `direct` entry
  (`en_pin`, `vin_pins`) or a `network` entry (`ihys_a`, `recommended_max_v`,
  `threshold_v`, the voltage the enable pin must exceed at the low contract
  input), each with the `cite` of the datasheet section it comes from, which
  the check text prints. `out_v` is the output voltage of a fixed-output part
  and `fb_vref` the feedback reference of an adjustable one; a row may not
  state both (see `docs/SUBSYSTEM_FORMAT.md`, board power). A `led_boost`
  is not part of the power tree and states only `kind`, `label` and `iset_v`,
  the voltage its ISET resistor senses. A part is found by the part number on
  its instance: the `MPN` field when it has one, else the symbol name when the
  symbol is the part's own, else its value. An instance with no row whose part number or value starts with the
  `label` of a row is an unreviewed variant of that device: the power tree
  reports it as an error and the SPICE gate as unverified, naming the sheet,
  the reference, the value and the label.
- `zeners` — keyed by the schematic value of the zener (a generic
  `Device:D_Zener` has no folder here, so this key is not checked against the
  folders and is matched exactly): `vz_min_v`, `vz_max_v`, `izt_a`, `zzt_ohm`.
- `reference_pins` — keyed by part number: `label` (the short device name the
  finding prints), `vref1_pin` and `vref2_pin`, the two reference pins that
  must not sit directly on two different rails.
- `control_grid` — keyed by part number: `button_gap_mm`, the gap when the
  part's instances are placed as a grid of controls.
- `model_overrides` — keyed by part number: `footprint`, `path` and
  `rotation_z_deg` of the 3D model that replaces the footprint's own.
- `footprint_aliases` — keyed by footprint id: `footprint`, the footprint id
  that stands in for it.
- `lands` — keyed by part number: `footprint` (the land pattern the board
  emits for the part), `pad_gap_mm` (the land's own smallest pad-to-pad gap),
  `tolerance_mm` (how far the measured gap may differ) and `cite` (the
  manufacturer's recommended land it comes from). A footprint whose own pad gap
  is below its net-class clearance must have a row here.
- `electrical_spacing` — one object, not keyed by part: `source`, `column`,
  `basis` and `rows`, each row `max_volts` and `spacing_mm`, rising in
  `max_volts`. The land-spacing rule takes the minimum electrical spacing for a
  pair of nets from the first row that covers the voltage between them.
- `i2c_devices` — keyed by part number, one row per addressable I2C target:
  `label` (the device name the manifest prints), `base` (the 7-bit address
  with every strap at value 0), `data_pin` and `clock_pin`, `straps` (each a
  `pin` and its `selects`: a map from a pin of the same part to the value added
  to `base` when the strap pin is on that pin's net) and the datasheet `cite`.
  Pins are named by the names in the part's `part.json`; each name must pick
  exactly one pin. The address is `base` plus the selected values and must stay
  within seven bits.
- `i2c_bridges` — keyed by part number, one row per part that carries I2C
  lines from one net to another: `joins` (pairs of pin names, one pair per
  line), `shares_addresses` (true when a target on one side answers the
  controller on the other at its own address, as through a level translator;
  false for a multiplexer or an address translator) and the datasheet `cite`.

The board's I2C inventory reads these two sections: a bus is the pair of nets
on a device's data and clock pins (or a typed `i2c` port pair), named by the
`bus` of its typed ports, else by its data net; buses joined by a bridge that
shares addresses form one address space. A part of class `integrated_circuit`
on a bus net with neither row fails the build.

Each of these sections must be present; an empty one is `{}`. A key naming a
part must be the name of a folder in this folder; the keys of `zeners` (values)
and `footprint_aliases` (footprint ids) are the exceptions. A key of `i2c_devices` or `i2c_bridges` must also have
a `part.json` in its folder. An unknown key, a value of
the wrong type or a repeated key fails the build, naming the file, the section
and the key.

Every other height is measured from the 3D model the part's footprint names
(the highest mesh point of a `.wrl`, the highest vertex of a `.step`, with the
footprint's own offset and scale applied; a model path that starts
`${KIPRJMOD}/../parts/` is read from this folder). The board build fails, naming the
part, when a placed part's symbol has no class, when its footprint has neither
a model nor a stated height, or when it has both. After importing a new part,
add its symbol to `classes`.

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
the native import/catalog workflow above. Because the pin table is named,
sheets wire pins by name and the build validates them against the symbol. The
`LCSC` code carried on every part keys the BOM and the datasheet ratings
checks, so a part's orderable identity can never drift from its library folder.
