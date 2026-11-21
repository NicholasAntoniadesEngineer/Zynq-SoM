# floorplan_prose origin

## 1. What it was and who used it

The floorplan document (`docs/FLOORPLAN.md`) and drawing (`docs/FLOORPLAN.svg`) carried, besides derived geometry tables, hand-typed placement notes: each chosen by sheet name or part number in `floorplan_notes.cpp` (the carrier fixture holds 21 numbered notes plus the board-wide test point note, devkit_mini 6 plus the same board-wide note), printed as numbered badges on the blocks and a legend in the drawing, as a "notes" column in the two block tables and as a "Placement notes (the WHYs)" section in the document, plus framing sentences naming the carrier, "PLAN.md round 2", the DF40 connectors and J1/J2/J3 and an "Honest limits" section. The reader was the layout engineer who owns the outline; no pipeline step read the notes (`floorplan_output.cpp` produced them and handed them to the two renderers only).

## 2. Files moved

One whole file (`source/`), 24 fragments (text cut out of files that stay, `fragments/`), and two extracted fixture arrays (`tests/`). The updated frozen fixtures (`native/tests/data/floorplan/{carrier,devkit_mini}.{md,svg,json}` and `native/tests/data/output_precision_legacy.txt`) stay in place with the removed text taken out; their previous bytes are in the source commit.

| original path | archive path | git hash-object |
|---|---|---|
| `native/src/floorplan_notes.cpp` | `removed/floorplan_prose/source/floorplan_notes.cpp` | `351daded2af933cfe83e3146580df9fc3f18e6c1` |
| `native/include/schgen/floorplan.hpp:248-251` | `removed/floorplan_prose/fragments/floorplan.hpp.L248-251.txt` | `db87340a58b86eb8f3e407c4162056dbe3cebca9` |
| `native/include/schgen/floorplan.hpp:328-329` | `removed/floorplan_prose/fragments/floorplan.hpp.L328-329.txt` | `b9dd7ebf9996ade2b1423549d4f5847d8caeccb1` |
| `native/include/schgen/floorplan.hpp:331-331` | `removed/floorplan_prose/fragments/floorplan.hpp.L331-331.txt` | `56b11dcfa9c6a7dc86d29f639839a1484b86ad68` |
| `native/include/schgen/floorplan.hpp:334-334` | `removed/floorplan_prose/fragments/floorplan.hpp.L334-334.txt` | `6afeb8d39ffdfc1b48bf8c0c7251ac1267f48ca3` |
| `native/include/schgen/floorplan.hpp:343-343` | `removed/floorplan_prose/fragments/floorplan.hpp.L343-343.txt` | `cbb242960fa7fac30df444256dd1c01e9ff421df` |
| `native/tests/floorplan_contracts.cpp:1298-1301` | `removed/floorplan_prose/fragments/floorplan_contracts.cpp.L1298-1301.txt` | `d216808104ffd05af9299b8b9415dfa01e563b88` |
| `native/tests/floorplan_contracts.cpp:1315-1317` | `removed/floorplan_prose/fragments/floorplan_contracts.cpp.L1315-1317.txt` | `685102807644db4db56caf32e9e69d6f1391f83e` |
| `native/src/floorplan_md.cpp:110-111` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L110-111.txt` | `6d268cc6cb67dab2a23be022768490343aa1b7fe` |
| `native/src/floorplan_md.cpp:112-116` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L112-116.txt` | `6667f5ae770aea7da1f2aa915fcc4149bbb85175` |
| `native/src/floorplan_md.cpp:19-19` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L19-19.txt` | `aaff6ec8c612fceb96c84cbef2e5d0ad49ccd4a8` |
| `native/src/floorplan_md.cpp:20-21` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L20-21.txt` | `6e2ae4d5153badf74732997eb8c8c2a90fac3707` |
| `native/src/floorplan_md.cpp:23-24` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L23-24.txt` | `fd3770553eecde75158d96a35f5fb6d27b75e14f` |
| `native/src/floorplan_md.cpp:26-26` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L26-26.txt` | `21b2fb249cc357ca7127745205d908584fc2037f` |
| `native/src/floorplan_md.cpp:28-28` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L28-28.txt` | `6013952614a2cba37471fd062cb4db95ad20d484` |
| `native/src/floorplan_md.cpp:31-31` | `removed/floorplan_prose/fragments/floorplan_md.cpp.L31-31.txt` | `45fc076a9ff5ffdefbaf733586b9f66e23e449c9` |
| `native/src/floorplan_output.cpp:9-11` | `removed/floorplan_prose/fragments/floorplan_output.cpp.L9-11.txt` | `89bec5cc18f06f2d8456c704142adf6e50c42c38` |
| `native/src/floorplan_svg.cpp:103-107` | `removed/floorplan_prose/fragments/floorplan_svg.cpp.L103-107.txt` | `8f04f4c318bc719304c16940cfa6377592efc259` |
| `native/src/floorplan_svg.cpp:124-130` | `removed/floorplan_prose/fragments/floorplan_svg.cpp.L124-130.txt` | `1963fa6633cae77853c41f77f5e17a8bbf82ab88` |
| `native/src/floorplan_svg.cpp:131-131` | `removed/floorplan_prose/fragments/floorplan_svg.cpp.L131-131.txt` | `8ed490685098d421516a36b9fae718e88c6e5787` |
| `native/src/floorplan_svg.cpp:30-30` | `removed/floorplan_prose/fragments/floorplan_svg.cpp.L30-30.txt` | `3bb2c146fce2a353341497499cde8b848623a820` |
| `native/src/floorplan_svg.cpp:36-38` | `removed/floorplan_prose/fragments/floorplan_svg.cpp.L36-38.txt` | `3e961f466094635d52133159db27bd9e0febcc4e` |
| `native/src/floorplan_svg.cpp:40-40` | `removed/floorplan_prose/fragments/floorplan_svg.cpp.L40-40.txt` | `ddf5d48df71f1281c1564812f10bafb40c1ff872` |
| `native/tests/output_precision_contracts.cpp:129-129` | `removed/floorplan_prose/fragments/output_precision_contracts.cpp.L129-129.txt` | `52ae3691c29d11f0a1736318c6387100853c42b7` |
| `native/tests/output_precision_contracts.cpp:130-133` | `removed/floorplan_prose/fragments/output_precision_contracts.cpp.L130-133.txt` | `51a119ddc9e47b7bd37d4516a2cb6c8dc9359cba` |
| `native/tests/data/floorplan/carrier.json` key `expected.notes` | `removed/floorplan_prose/tests/data/floorplan/carrier_expected_notes.json` | `f85ff48ebfcee33d7a63c6fdd15cb628c11acbd9` |
| `native/tests/data/floorplan/devkit_mini.json` key `expected.notes` | `removed/floorplan_prose/tests/data/floorplan/devkit_mini_expected_notes.json` | `c9742971ffdce816c7d8fa7d56c82054626e10dd` |

Fragment notes: `floorplan_md.cpp.L19-19` and the `floorplan.hpp`, `floorplan_svg.cpp.L30-30`, `L40-40`, `L131-131` fragments are lines that were rewritten rather than deleted (the notes parameter, the legend height term); they are kept as the exact old text. `floorplan_contracts.cpp.L1298-1301` and `L1315-1317` are the test lines that compared the notes with the frozen `expected.notes` and checked the note text for Python source paths; `output_precision_contracts.cpp.L129-133` built the notes from the same frozen array for the drawing oracle.

## 3. Source commit

`9301deeda9d6c31cc06fc5f9230519033cd464c9` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers are from that commit. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline stage `floorplan` (`native/src/board_pipeline_documents.cpp`, gate text "existing solved plan documents published"): the documents come from `render_floorplan_documents` (`native/src/floorplan_output.cpp:5-14`), which called `build_floorplan_notes` (`removed/floorplan_prose/source/floorplan_notes.cpp:21`) and passed the result to `render_floorplan_svg` and `render_floorplan_md`. Command `schgen floorplan`.
- Build: `native/CMakeLists.txt:49` (`src/floorplan_notes.cpp` in `SCHGEN_FLOORPLAN_SOURCES`); audit file lists `native/src/board_policy_metadata.cpp:88` and `native/src/board_pipeline_audits.cpp:8`; vocabulary allow-list entry `native/src/floorplan_notes.cpp` (module 3, part 23, subsystem 14).

## 5. What it read

- Sheets by name: `ethernet`, `power`, `bringup_modules`, `bringup_rails`, `power_mon`, `debug_boot`, `usb_pd`, `user_io` (the `b.name==` tests in the archived `floorplan_notes.cpp`).
- Connector parts by value: `TYPE-C-31-M-12`, `HDMI-019S`, `TF-01A`, `AFC07-S40FCA-00`, `SFW15R-1STE1LF`, `DS1024-2x6R2`; parts by prefix: `TPS2594`, `USBLC`, `TPD`, `TPD12S`, `M24C`, `HX5008`, `SY7201`, `TLV75725`; net `+VIN`; reserved edge `usb_uart_connector`.
- Typed numbers and text: 0.15 mm TMDS intra-pair skew, 2.5 mm SD bus match, 10 mm ESD distance, the "PLAN.md round 5" eFuse remark; in `floorplan_md.cpp`: the paragraph at L24 ("PLAN.md round 2 leaves the form factor free (connector-driven ~120x100 class expected)"), DF40 and J1/J2/J3 at L26, L28 and L31, the four "Honest limits" bullets at L113-116.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: every note was a typed sentence keyed to a sheet name or a part number (only the numbers inside a few sentences, such as TMDS pair count, dissipation and the gated-rail list, were computed), so a new board could never get one, and the document and drawing named the carrier, a planning document and a connector family for any board.

What the document and drawing are now: the "notes" column stays in both block tables and is empty; the numbered badges, the legend and its heading ("placement notes (derived)") and the "Placement notes (the WHYs)" and "Honest limits" sections are gone; the title is the single word "Floorplan" (a title with the board name was tried and rejected: floorplan inputs built without a project name exist in the tests, and a missing name must not be defaulted); the two source bullets and the SoM outline sentence lost their DF40 and J1/J2/J3 wording ("connector positions", "module-connector bindings"). The drawing's own title ("carrier floorplan — SUGGESTION, not constraint") and subtitle (naming "PLAN.md round 2") were not listed for this task and remain in `native/src/floorplan_svg.cpp`.

## 7. What could be generated

Under task R5 follow-ups: a derived "what constrains this block" column (roles present with their reach, number of pairs per kind, regulators and their dissipation, tall parts, connector mating faces), using values already computed in `floorplan_md.cpp` (the dissipation table), the sheet roles, and `parts/part_facts.json` connectors. The per-rule result of the placement gate for the block could be added.

## 8. Bringing it back

1. `git mv removed/floorplan_prose/source/floorplan_notes.cpp native/src/floorplan_notes.cpp`.
2. Restore the build lines: `native/CMakeLists.txt:49` at `9301deed` read `src/floorplan_ledger.cpp src/floorplan_json.cpp src/floorplan_notes.cpp` (add ` src/floorplan_notes.cpp` after `src/floorplan_json.cpp`); put `"floorplan_notes.cpp",` back before `"floorplan_svg.cpp"` in `native/src/board_policy_metadata.cpp:88` and `native/src/board_pipeline_audits.cpp:8`; put `"native/src/floorplan_notes.cpp": {"module": 3, "part": 23, "subsystem": 14},` back in `native/tests/data/vocabulary_allowlist.json`.
3. Re-insert the fragments at the listed ranges (locate by content): the `FloorplanNote` struct and the `build_floorplan_notes` declaration and the notes parameters in `floorplan.hpp`, the `notes` member of `FloorplanDocuments`, the three lines in `render_floorplan_documents`, the note badge and legend code in `floorplan_svg.cpp`, the note column text, the notes section and the framing lines in `floorplan_md.cpp`, and the test lines.
4. Put the `"notes"` arrays from `tests/data/floorplan/*_expected_notes.json` back as the `notes` key after `cross_estimate` in `native/tests/data/floorplan/{carrier,devkit_mini}.json`, and restore the frozen `.md`, `.svg` and `output_precision_legacy.txt` bytes from commit `9301deed` (`git show 9301deed:<path>`).
5. The notes cite constants that have changed since (stack-up, the SI table) only through the live `FloorplanInput`; the part values listed in section 5 must still exist in the part library.
