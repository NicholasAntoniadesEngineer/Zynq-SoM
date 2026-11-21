# drawing_titles origin

## 1. What it was and who used it

The typed text of the two power drawings: the title, subtitle and three stage headings of `docs/power_sequence.svg` (naming the carrier, its bring-up manual, DIP switches, a pull-down controller and the SY6280 load switch), the title of `docs/power_tree.svg` ("carrier power tree"), and the typed always-on rail names `+3V3_SC` and `+5V_SOM` that seeded stage 0 of the sequence. The reader of both drawings is the layout or bring-up engineer; no other pipeline step read them (the manifest hashes the files).

## 2. Files moved

Three fragments, text cut out of files that stay. The four frozen drawings `native/tests/data/firmware_docs/{carrier,devkit_mini}/power_sequence{,_fail}.svg` stay in place with their five (four on devkit_mini, which has no switched rails) heading lines replaced; their previous bytes are in the source commit.

| original path | archive path | git hash-object |
|---|---|---|
| `native/src/firmware_docs_power_sequence.cpp:44-44` | `removed/drawing_titles/fragments/firmware_docs_power_sequence.cpp.L44-44.txt` | `421bfcdb298df41c42feea02b7aa736c9f11a2a4` |
| `native/src/firmware_docs_power_sequence.cpp:74-78` | `removed/drawing_titles/fragments/firmware_docs_power_sequence.cpp.L74-78.txt` | `b42872c453dd1f7769def5003707c255c6a21eb5` |
| `native/src/power_checks.cpp:286-286` | `removed/drawing_titles/fragments/power_checks.cpp.L286-286.txt` | `4b2552a15b0fb2deaa47216d365a05e717a628c3` |

## 3. Source commit

`d6f1a6a4a9814aebb8fbf515e2494d38190bc922` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers are from that commit. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline step and gate `power_sequence`: `native/src/board_pipeline_documents.cpp:37` (`render_power_sequence_svg(build_power_sequence(...))`); command `schgen power-sequence`: `native/src/project_cli.cpp:759-764`.
- Pipeline gate `power_tree`: `native/src/board_pipeline_checks.cpp:12` calling `run_power_checks`, which calls `power_svg` (`native/src/power_checks.cpp:318`).
- Build: both functions live in sources that stay (`src/firmware_docs_power_sequence.cpp`, `src/power_checks.cpp`); no build line was removed.

## 5. What it read

- Typed rail names `+3V3_SC` and `+5V_SOM` (`firmware_docs_power_sequence.cpp:44`); `+3V3_SC` is also a source in the compiled power policy, so only `+5V_SOM` carried information.
- Typed text: "carrier", "staged bring-up", "carrier/docs/BRINGUP.md", "pre-DIP / pre-PD", "close one DIP at a time", "SY6280 load switches", and the stage numbers 0, 1-3 and 4 (`:74-78`); "carrier" in `power_checks.cpp:286`.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: the devkit_mini drawing said "carrier power-up sequence" and "matches carrier/docs/BRINGUP.md staging" for a board that has no such file; the headings named parts and a manual; stage numbers 1-3 and 4 were typed and not computed; the module supply rail was a typed name instead of data.

What the drawings are now: the title is the board name from `project.json` plus fixed words ("power-up sequence", "power tree — budget gate"); the sequence headings are "always-on rails (sources, module supply, rails with no enable)", "enabled rails, ordered by depth from the sources" and "switched rails (load switches)"; the subtitle states only that the drawing is derived and that arrows are rail dependencies. The always-on set is seeded from the power sources of the power policy plus the module supply rail, which is the module's draw rail resolved through the board's SoM mapping (`som/module.json` `draw.rail` = `VIN`, `som_mapping.json` `rebound_som_rails` `VIN` -> `+5V_SOM`; `module_supply_rail` in `native/src/firmware_docs_power_sequence.cpp`).

Findings recorded here: (a) the always-on set did not change on either board (stage 0 equals the frozen snapshot list of the fixtures, and the drawings differ only in the heading lines); (b) the study assumed the draw rail is in `board.json` as `+5V_SOM`; it is in the module folder's `module.json` as `VIN` and needs the mapping to become the carrier rail; (c) the power sources are still the compiled table `default_power_policy().sources` in `native/src/power_checks.cpp` (task F-A moves them to board data); (d) `reports/power_tree.txt` still carries the typed line "numbered as in carrier/docs/power_tree.svg" (`native/src/power_checks.cpp:245`); that report line was outside this task.

## 7. What could be generated

The headings could carry computed depth ranges ("depth 1 to n") and the two drawings could be merged into one tree with depth columns and enable nets on the edges (study section 2.7). The sources move to board data with task F-A.

## 8. Bringing it back

1. Re-insert the three fragments at the listed lines (locate by content): line 44 replaces the `always{module_rail}` seed; lines 74-78 replace the five heading lines; line 286 of `power_checks.cpp` replaces the title expression.
2. Restore the signatures: `build_power_sequence(sheets, result, policy)`, `render_power_sequence_svg(seq, ok, policy)`, `power_svg(res, policy)` and `run_power_checks(sheets, reports, docs, policy)`, remove `module_supply_rail`, and put back the call sites in `board_pipeline_documents.cpp`, `board_pipeline_checks.cpp` and `project_cli.cpp`.
3. Restore the four frozen drawings from the source commit (`git show <source commit>:<path>`).
