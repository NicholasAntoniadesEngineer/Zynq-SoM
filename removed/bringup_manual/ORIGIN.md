# bringup_manual origin

## 1. What it was and who used it

`docs/BRINGUP.md` was a staged bring-up manual, 219 lines, carrier only: power-off checks, first power with USB-PD negotiation, rails one DIP switch at a time, module load switches, boot modes with JTAG and SWD, and board services. The reader was a bench engineer powering the first board. Other readers in the tree: the manifest hashed it as an artifact when present (`native/src/manufacturing_exports_manifest.cpp:50`), the devkit test plan told the reader to see it (`removed/test_plan/outputs/devkit_mini/docs/TEST_PLAN.md`), and the power sequence drawing text names it (`native/src/firmware_docs_power_sequence.cpp:75`, left for task R6).

## 2. Files moved (3 whole files, 2 fragments)

| original path | archive path | git hash-object |
|---|---|---|
| `carrier/docs/BRINGUP.md` | `removed/bringup_manual/outputs/carrier/docs/BRINGUP.md` | `f17d01971575a0aa5662eaf45bf1bede48f0b73d` |
| `native/src/firmware_docs_manual.cpp` | `removed/bringup_manual/source/firmware_docs_manual.cpp` | `4299f720f9cf0be4b2afe68b2e1d68ceea003888` |
| `native/tests/data/firmware_docs/carrier/BRINGUP.md` | `removed/bringup_manual/tests/data/firmware_docs/carrier/BRINGUP.md` | `41858028fa14e1f5c4d6748ba28a32bdaff553e2` |
| `native/include/schgen/firmware_docs.hpp:27-27` | `removed/bringup_manual/fragments/firmware_docs.hpp.L27-27.txt` | `75237dd1ebf6663b77851c1ad856a26d88fbf5a7` |
| `native/include/schgen/firmware_docs.hpp:31-31` | `removed/bringup_manual/fragments/firmware_docs.hpp.L31-31.txt` | `407b4afac43e1c61fa083c0ee0d583da26dbdb27` |

## 3. Source commit

`f32ac35a280d8cca496f4dbec4dde9f51c63600d` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers below are from that commit unless they name an archive path. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline step and gate `manual` (skipped, not failed, when the project lacks the sheets listed in item 5): `native/src/board_pipeline_documents.cpp:33-34`. Required name at `native/src/board_pipeline.cpp:80`; the skip was allowed at `native/src/board_pipeline.cpp:93`.
- Function `schgen::render_bringup_manual`, `removed/bringup_manual/source/firmware_docs_manual.cpp:9` onward; requirement check `manual_missing_requirements` (the removed header lines are in `fragments/`).
- Command `schgen manual`: `native/src/project_cli.cpp:758-793`; help line `native/src/main.cpp:69`.
- Build: `native/CMakeLists.txt:40` (`src/firmware_docs_manual.cpp`), `native/CMakeLists.txt:1393` (help test list).

## 5. What it read

- Sheets, required: `power`, `power_mon`, `bringup_rails`, `bringup_en`, `bringup_en_modules`, `bringup_modules`, `debug_boot` (`removed/bringup_manual/source/firmware_docs_manual.cpp:12-22`); the DIP switch part symbol `DSHP`, the gate part `74LVC1G08` and the load switch `SY6280` through the fact layer (fragments `bringup_facts.cpp.L49-68`, `.L175-194`).
- Typed in the generator: rail current budgets `{"+5V",3000},{"+3V3",3000},{"+1V8",600},{"+VIN",3000}` (:58), the boot-switch function strings (:92), the special cases `USER_LED` (:71) and `EN_LCD_BL` (:83), the `+1V8` FET-sense sentence (:66), the `+3V3_AUX` services step (:100).
- Typed in `removed/firmware_contract/source/firmware_docs_templates.hpp:69-232`: 164 lines of manual text.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: about 75 percent of the file was typed text (template lines, budgets, special cases); about 25 percent was derived (switch inventory, rails to check, always-on IC table, one block per regulator stage, module table).

## 7. What could be generated

The derived core becomes a generated bring-up checklist (study `programmatic_outputs_study.md` output N2, task G2), ordered by power-tree depth. It needs the regulator facts F2 and board sources F3 for expected voltages, and the I2C address facts F1 for scan steps. The narrative, stage titles, the boot-switch function table and the module hints are product procedure and stay out of the tool.

## 8. Bringing it back

1. `git mv` `source/firmware_docs_manual.cpp` to `native/src/`; `tests/data/firmware_docs/carrier/BRINGUP.md` to `native/tests/data/firmware_docs/carrier/`; `outputs/carrier/docs/BRINGUP.md` to `carrier/docs/`. The templates the manual used are in `removed/firmware_contract/source/firmware_docs_templates.hpp` lines 69-232 (the header moves back whole).
2. Restore the pipeline step, command, help line and build entries below (as removed), and the shared items in `removed/firmware_contract/ORIGIN.md` section 8.

`native/src/board_pipeline_documents.cpp:27-38` at `f32ac35a`:

```
    c.attempt("firmware",[&]{FirmwareDocsInput in;in.sheets=c.circuits;
        in.firmware_sources={c.paths.som_interface_file.string(),c.paths.som_schematic.string()+" (U9 pin map, live kicad-cli extraction)"};
        for(const auto& sc:c.circuits)in.firmware_sources.push_back(sc.path.string());
        in.stm32=stm32_pin_map(extract_som_zynq(c.paths.som_schematic,"U9",{"J1","J2","J3"},c.options.extraction),load_som_interface(c.paths.som_interface_file));
        c.firmware=in;publish_text(c.out/"firmware/zynq_carrier_contract.h",render_firmware_contract(in));c.gate("firmware",true,"contract published; absent optional inputs: "+join(firmware_absent_inputs(in)));});
    FirmwareDocsInput partial;partial.sheets=c.circuits;
    c.attempt("manual",[&]{const auto missing=manual_missing_requirements(partial);if(!missing.empty()){c.status("manual",BoardGateStatus::skipped,"project has no "+join(missing));return;}
        if(!c.firmware)throw ProjectError("firmware facts unavailable");publish_text(c.docs/"BRINGUP.md",render_bringup_manual(*c.firmware));c.gate("manual",true,"bring-up manual published");});
    c.attempt("scfw",[&]{const auto missing=scfw_missing_requirements(partial);if(!missing.empty()){c.status("scfw",BoardGateStatus::skipped,"project has no "+join(missing));return;}
        if(!c.firmware)throw ProjectError("firmware facts unavailable");const auto docs=render_scfw(*c.firmware);for(const auto& d:docs)publish_text(c.out/"firmware/sc"/d.path,d.text);c.gate("scfw",true,std::to_string(docs.size())+" files published");});
    c.attempt("testplan",[&]{if(!c.testpoints||!c.spice)throw ProjectError("coverage/SPICE results unavailable");ProjectStrings probes;for(const auto& [net,locations]:c.testpoints->have)probes.emplace_back(net,join(locations));
        publish_text(c.docs/"TEST_PLAN.md",render_test_plan(c.firmware?*c.firmware:partial,*c.spice,probes));c.gate("testplan",true,"test plan published from current checks");});
```

`native/src/project_cli.cpp:758-793` at `f32ac35a`:

```
    if(options.command=="firmware" || options.command=="manual" || options.command=="scfw" ||
       options.command=="testplan" || options.command=="power-sequence") {
        FirmwareDocsInput in;in.sheets=circuits;in.firmware_sources=firmware_sources(paths);
        std::vector<std::string> missing;
        if(options.command=="manual")missing=manual_missing_requirements(in);
        if(options.command=="scfw")missing=scfw_missing_requirements(in);
        if(!missing.empty()) {
            std::cout<<options.command<<": SKIP — project missing";
            for(const auto& name:missing)std::cout<<' '<<name;
            std::cout<<'\n';return 1;
        }
        if(options.command=="firmware" || options.command=="manual" || options.command=="scfw")
            in.stm32=stm32_pin_map(extract_som_zynq(paths.som_schematic,"U9",{"J1","J2","J3"},{options.kicad_cli}),
                                  load_som_interface(paths.som_interface_file));
        if(options.command=="scfw") {
            const auto artifacts=render_scfw(in);
            const auto directory=options.output.empty()?paths.project_root/"firmware/sc":options.output;
            for(const auto& artifact:artifacts)publish_text(directory/artifact.path,artifact.text);
            std::cout<<"SCFW SCAFFOLD: "<<directory.string()<<" ("<<artifacts.size()<<" files)\n";return 0;
        }
        std::string text;fs::path default_path;
        if(options.command=="firmware") {text=render_firmware_contract(in);default_path="firmware/zynq_carrier_contract.h";}
        else if(options.command=="manual") {text=render_bringup_manual(in);default_path="docs/BRINGUP.md";}
        else if(options.command=="power-sequence") {
            const auto power=analyze_power(circuits);
            text=render_power_sequence_svg(build_power_sequence(circuits,power),power.ok());default_path="docs/power_sequence.svg";
        } else {
            ProjectStrings probes;
            for(const auto& [net,locations]:check_testpoint_coverage(sheets).have) {
                std::string value;for(const auto& location:locations){if(!value.empty())value+=", ";value+=location;}
                probes.emplace_back(net,value);
            }
            text=render_test_plan(in,extract_spice_checks(circuits),probes);default_path="docs/TEST_PLAN.md";
        }
        const auto output=options.output.empty()?paths.project_root/default_path:options.output;
        publish_text(output,text);std::cout<<options.command<<": "<<output.string()<<'\n';return 0;
```

`native/src/main.cpp:69-70` at `f32ac35a`:

```
                         "  firmware | manual | testplan | power-sequence [--project NAME] [-o FILE]\n"
                         "  scfw [--project NAME] [-o DIRECTORY]\n"
```

`native/CMakeLists.txt:40-41` at `f32ac35a`:

```
    src/bringup_facts.cpp src/firmware_docs.cpp src/firmware_docs_manual.cpp src/firmware_provenance.cpp
    src/firmware_docs_testplan.cpp src/firmware_docs_scfw.cpp src/firmware_docs_power_sequence.cpp
```

`native/src/manufacturing_exports_manifest.cpp:50-51` at `f32ac35a`:

```
    for(const auto& rel:std::vector<std::string>{board_file_name(file_stem,BoardFileKind::Schematic),board_file_name(file_stem,BoardFileKind::Project),board_file_name(file_stem,BoardFileKind::Pcb),"manufacturing/SI_CONSTRAINTS.md","docs/BRINGUP.md","docs/FLOORPLAN.md","docs/DESIGN_SPEC.md","docs/COMPLIANCE.md"})add(root/rel);
    for(const auto& [dir,ext]:ProjectStrings{{"schematic",".kicad_sch"},{"fpga",".xdc"},{"firmware",".h"},{"manufacturing",".csv"},{"manufacturing",".txt"},{"manufacturing",".kicad_dru"},{"reports",".txt"},{"docs",".svg"}}){
```

3. The archived test `removed/firmware_contract/tests/firmware_docs_contracts.cpp` checks this output against the fixture `tests/data/firmware_docs/carrier/BRINGUP.md`; it was written against the circuits and the fact layer at the source commit.
Tasks R2 removed four outputs together, so the shared restore steps are in `removed/firmware_contract/ORIGIN.md` section 8 (fact layer fragments, `FirmwareDocsInput`, the pipeline `Context`, the manifest step and the build lists).
