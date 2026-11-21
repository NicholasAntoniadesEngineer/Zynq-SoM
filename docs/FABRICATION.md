# Fabrication and assembly data

Everything the tool knows about the fabricator and about the fabricator's parts library is data with a
source. Nothing is compiled in. A missing file, an unknown key, a wrong unit or a missing source fails the
load with a message naming the file and the key.

## `fabricators/<name>.json` (`schema: schgen.fabricator/1`)

One file per fabricator (`jlcpcb.json`). Sections: `assembly` (service limits per `economic` and
`standard`, edge rails, fiducials, body-to-edge distance, placement-point spacing, designators per BOM
line, the package spacing table, fees), `fab` (per copper weight under `by_copper_oz.1` and `.2`: trace,
space, mask bridge, plated-hole annular ring; then hole-to-hole by kind, via, plated slot width and
length ratio, NPTH, copper-to-edge, silk height, line width and pad clearance, finish, copper weights) and
`order_files` (BOM and placement column names, layer tokens, coordinate suffix, rotation direction).

Every leaf is `{"value", "unit", "source_url", "read_utc", "quote"}`; `quote` is text from the page at
`source_url` read at `read_utc`. A value the source does not state is `{"value": null, "unit",
"unverified": "<reason>"}`; any code that needs it reports UNVERIFIED instead of passing. The loader
(`native/src/fabricator.cpp`) holds the closed key set with the unit of each key.

`schgen.json` selects the profile per board under `fabrication`; the stack-up's published copper
(`outer_oz`, `inner_oz` in `native/stackups.json`) must equal the board's copper, the finish and copper
must be offered, and the service must take the layer count.

What reads it: the fab-profile gate (floors per copper weight, plus measured PTH annular ring, NPTH
drill, plated slot width and ratio, silk height and stroke), the KiCad DRC defaults written to the
`.kicad_pro` (hole-to-hole, text height and thickness, mask bridge, silk clearance), the land-spacing
policy, the silk label floor, and the order files.

## Order files (`<stem>_bom.csv`, `<stem>_cpl.csv`, gate `order_files`)

BOM columns and CPL columns are exactly those of the profile. Both files use the board references of the
emitted `.kicad_pcb`. Coordinates are millimetres with the profile's suffix, origin at the lower-left corner
of the outline, Y up, so every placed part is positive; layer is `T` or `B`; rotation is KiCad's
footprint rotation in degrees counter-clockwise. Parts whose class is listed under `unplaced_classes` in
`parts/assembly_facts.json` (test points, mounting holes, fiducials) are in neither file. The gate
checks columns, designators in both files and none twice, upper case, designators per line, positive
coordinates, layer tokens, minimum point spacing per layer, and prints an ADVISORY line that rotation
offsets are not verified. `<board>/manufacturing/bom_jlc.csv` stays the sheet-qualified human-readable BOM.

## `parts/assembly_facts.json` (`schema: schgen.assembly_facts/1`)

`unplaced_classes`; `needs` (a part class whose presence means the finished board needs an item that is
not a placed BOM part, for example a cell for a battery holder; satisfied only by a BOM line whose code is
in `satisfied_by`); `parts`: one row per LCSC code with `in_library`, `class` (basic, preferred, extended),
`assembly_type`, `assembly_mode`, `pcba_type`, `buyable`, `jlc_stock`, `lcsc_stock`, `msl`, `audit_flag`,
`special_fee`, `jlc_package`, `mpn`, `read_utc`, `source_urls`, and an optional hand-declared `route`
(`pre_order` or `global`) that a refresh keeps.

`schgen assembly-refresh [--config FILE] [--repo DIR] [--code CODE]... [--only] [--dry-run]` reads every order
code on every board's BOM (boards from the run config) from the JLCPCB assembly library search, the part
page and the LCSC detail, spaced one second apart, and rewrites the file sorted. A code that cannot be
read keeps its old row and is listed; no row is ever invented. `--code` adds a code that is on no BOM yet
(to check a replacement); `--only` reads just those codes. A code LCSC has no detail for keeps `lcsc_stock: null`. Builds never use the network.

Gate `assembly_parts` reads only the file. FAILING: a BOM line without a code, a code without a row, a code
outside the library or not buyable, one code on two lines, one value spelled two ways, a placed part the
BOM lacks, an item the finished board needs that is not a placed BOM part. ADVISORY: lines whose stock is
below quantity times `build_count` ("out of stock today"), unless the row declares a route.
