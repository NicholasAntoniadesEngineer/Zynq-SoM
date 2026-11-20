# firmware_contract origin

## 1. What it was and who used it

`firmware/zynq_carrier_contract.h` was a C header of hardware facts for the system-controller firmware: 249 lines on the carrier, a shorter one on devkit_mini. About 70 percent was derived tables (every controller net with port, pin and connector pin; module-internal nets; rail stages with setpoint and enable net; the expander bit map; the monitor channels with shunt values) and about 30 percent typed text (SWD and boot-select sections, mode codes, bit-bang pins, address descriptions, input notes, template lines). The reader was the system-controller firmware engineer; the scaffold in `removed/sc_firmware_scaffold/` included it. In the pipeline the `firmware` step also produced the controller pin map that the manifest needs (`c.firmware` in the old `Context`), and it performed two checks, the I2C address collision check and the SWD pin drift check (see "What survived" below).

This folder also holds what the four outputs of task R2 shared: the template header, the provenance code and its test, the combined test, the fixtures, and the fact-layer fragments.

## 2. Files moved (18 whole files, 16 fragments)

Fragments are text cut out of files that stay; each is the exact removed lines, named `<original file name>.L<first>-<last>.txt`. The fragments of the three other outputs (`firmware_docs.hpp` declarations) are listed in their own `ORIGIN.md`. `downstream_i2c_contracts.cpp.L1-203.txt` is the whole file as it was before it was cut to its manifest part, because the cut and kept parts interleave.

| original path | archive path | git hash-object |
|---|---|---|
| `carrier/firmware/zynq_carrier_contract.h` | `removed/firmware_contract/outputs/carrier/firmware/zynq_carrier_contract.h` | `b3f599c656ce89102ffc5b0c72f6a14c7d1934f5` |
| `devkit_mini/firmware/zynq_carrier_contract.h` | `removed/firmware_contract/outputs/devkit_mini/firmware/zynq_carrier_contract.h` | `30051feee78d071f5e6d999e1da51ce717f0fbd8` |
| `native/src/firmware_docs.cpp` | `removed/firmware_contract/source/firmware_docs.cpp` | `42cd27b9824ff84d3ddd0e04b0522545c2cf9313` |
| `native/src/firmware_docs_templates.hpp` | `removed/firmware_contract/source/firmware_docs_templates.hpp` | `1a5817069cb62401f6eb7367817dbc2a9d4c8df8` |
| `native/src/firmware_provenance.cpp` | `removed/firmware_contract/source/firmware_provenance.cpp` | `a25263515ce06fb9184d9f9a152a28ba89abff3d` |
| `native/include/schgen/firmware_provenance.hpp` | `removed/firmware_contract/source/firmware_provenance.hpp` | `363cd94e26b47fc256efb5cc1fc0ab6642ada31f` |
| `native/tests/data/downstream_i2c/README.md` | `removed/firmware_contract/tests/data/downstream_i2c/README.md` | `313cf3ed050f05db59e0bfb10b6ae0dd9f44aa67` |
| `native/tests/data/firmware_docs/README.md` | `removed/firmware_contract/tests/data/firmware_docs/README.md` | `136fbe546a664f9c7b9984bee3f4e41b88549877` |
| `native/tests/data/firmware_docs/carrier/mutants.json` | `removed/firmware_contract/tests/data/firmware_docs/carrier/mutants.json` | `7ec36eb466966a45b014d066a3c98e82f4e368e0` |
| `native/tests/data/firmware_docs/carrier/zynq_carrier_contract.h` | `removed/firmware_contract/tests/data/firmware_docs/carrier/zynq_carrier_contract.h` | `5e6f85660c9a4e768340328ae1cd9375721fb485` |
| `native/tests/data/firmware_docs/devkit_mini/mutants.json` | `removed/firmware_contract/tests/data/firmware_docs/devkit_mini/mutants.json` | `da0b4bd6f57933caf6d655d5f4ffbbf4abfc5b62` |
| `native/tests/data/firmware_docs/devkit_mini/zynq_carrier_contract.h` | `removed/firmware_contract/tests/data/firmware_docs/devkit_mini/zynq_carrier_contract.h` | `10fde5633ee731fd34954739dd3a2495062d9e68` |
| `native/tests/data/firmware_provenance/carrier_sources.txt` | `removed/firmware_contract/tests/data/firmware_provenance/carrier_sources.txt` | `7e741356633d0103693ee593336eea409c793e6e` |
| `native/tests/data/firmware_provenance/devkit_mini_sources.txt` | `removed/firmware_contract/tests/data/firmware_provenance/devkit_mini_sources.txt` | `f257812e6af30dd375e2eb35f6a92a4257d3affc` |
| `native/tests/firmware_docs_CORRECTIONS.md` | `removed/firmware_contract/tests/firmware_docs_CORRECTIONS.md` | `036b00c4c6428047b71d9a75a76d8c7a77cbbb26` |
| `native/tests/firmware_docs_NATIVE_NOTICES.md` | `removed/firmware_contract/tests/firmware_docs_NATIVE_NOTICES.md` | `e29dbede4796df9304c0bd334e20c9366db4baa9` |
| `native/tests/firmware_docs_contracts.cpp` | `removed/firmware_contract/tests/firmware_docs_contracts.cpp` | `58b27f929c1ce63f1531ba850a81c13a2af1e44a` |
| `native/tests/firmware_provenance_contracts.cpp` | `removed/firmware_contract/tests/firmware_provenance_contracts.cpp` | `cf81e35bbf7219d47ae2ec1db807d1f9ee2681e5` |
| `native/src/authoring_purity_scope.cpp:66-68` | `removed/firmware_contract/fragments/authoring_purity_scope.cpp.L66-68.txt` | `dad41e3fadec2f21f64a0997c7281f95f80aab27` |
| `native/src/bringup_facts.cpp:11-31` | `removed/firmware_contract/fragments/bringup_facts.cpp.L11-31.txt` | `c720996fd753aaa3e99e66aea1f4ae81b312104f` |
| `native/src/bringup_facts.cpp:175-194` | `removed/firmware_contract/fragments/bringup_facts.cpp.L175-194.txt` | `cdd50fd22179f0e268fe64f8024f29edf5640f69` |
| `native/src/bringup_facts.cpp:3-5` | `removed/firmware_contract/fragments/bringup_facts.cpp.L3-5.txt` | `9511f0ea3ea63da5e2ede1f53478872147dcc652` |
| `native/src/bringup_facts.cpp:49-68` | `removed/firmware_contract/fragments/bringup_facts.cpp.L49-68.txt` | `8cbf49a7f324196875ea0f6f852099fc24714f94` |
| `native/src/bringup_facts.cpp:94-174` | `removed/firmware_contract/fragments/bringup_facts.cpp.L94-174.txt` | `b85e36fed9dbd19fe526075eeebaa29ddce48f1b` |
| `native/include/schgen/bringup_facts.hpp:19-20` | `removed/firmware_contract/fragments/bringup_facts.hpp.L19-20.txt` | `e9e8517c895a060f943c6d021fa26b597ae962cc` |
| `native/include/schgen/bringup_facts.hpp:27-36` | `removed/firmware_contract/fragments/bringup_facts.hpp.L27-36.txt` | `89ed83da0954b33a32d3f750fc771d13f12dc27b` |
| `native/include/schgen/bringup_facts.hpp:38-39` | `removed/firmware_contract/fragments/bringup_facts.hpp.L38-39.txt` | `78e874709f1068bc92b71c24d1fee2f25bb28c98` |
| `native/include/schgen/bringup_facts.hpp:41-44` | `removed/firmware_contract/fragments/bringup_facts.hpp.L41-44.txt` | `a4f9d4f4cf2a1bae344876d76e6bfeaab36f2e06` |
| `native/include/schgen/bringup_facts.hpp:47-51` | `removed/firmware_contract/fragments/bringup_facts.hpp.L47-51.txt` | `6b0989f445ab9943439b955221ed6c9424e04ac9` |
| `native/src/bringup_internal.hpp:112-130` | `removed/firmware_contract/fragments/bringup_internal.hpp.L112-130.txt` | `913e5ba4a0b6c4861d4ac32c1951f8c216a7a117` |
| `native/src/bringup_internal.hpp:134-140` | `removed/firmware_contract/fragments/bringup_internal.hpp.L134-140.txt` | `0ab3d7c69fc5d8a0eefaed2a228fae22aaf0848c` |
| `native/tests/downstream_i2c_contracts.cpp:1-203` | `removed/firmware_contract/fragments/downstream_i2c_contracts.cpp.L1-203.txt` | `011bdcb0228a50c2110327a62cd55b553c6333aa` |
| `native/include/schgen/firmware_docs.hpp:15-26` | `removed/firmware_contract/fragments/firmware_docs.hpp.L15-26.txt` | `6ff9cb151d358bc5cc20471964491a66ed93b551` |
| `native/include/schgen/firmware_docs.hpp:29-30` | `removed/firmware_contract/fragments/firmware_docs.hpp.L29-30.txt` | `2f51cda5be68ce21ae67f4fc009b29669d899a6e` |

## 3. Source commit

`f32ac35a280d8cca496f4dbec4dde9f51c63600d` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers below are from that commit unless they name an archive path. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline step and gate `firmware`: `native/src/board_pipeline_documents.cpp:27-31`, run after the `xdc` step. Required name at `native/src/board_pipeline.cpp:80`; the `Context` member `firmware` (`native/src/board_pipeline_internal.hpp:39`) carried the result to `manual`, `scfw`, `testplan` and `manifest`; the output folder `firmware/` was created at `native/src/board_pipeline.cpp:44`.
- Function `schgen::render_firmware_contract`, `removed/firmware_contract/source/firmware_docs.cpp:44` onward; inputs loaded by `load_firmware_docs_input` (:38-42) and `firmware_sources` (`firmware_provenance.cpp`).
- Command `schgen firmware`: `native/src/project_cli.cpp:758-793`; help line `native/src/main.cpp:69`.
- Build: `native/CMakeLists.txt:40` (`src/firmware_docs.cpp`, `src/firmware_provenance.cpp`), `native/CMakeLists.txt:742` and `native/CMakeLists.txt:1156-1164` (tests `native_firmware_docs_contracts`, `native_firmware_provenance_contracts`), `native/CMakeLists.txt:1393`.

## 5. What it read

- All sheets of the board, by name (`removed/firmware_contract/source/firmware_docs.cpp:45`): `bringup_rails`, `power`, `power_mon`, `bringup_modules`, `usb_pd`, `board_services`, `bringup_en`, `bringup_en_modules`; the live module netlist for controller `U9` through connectors `J1`, `J2`, `J3` (:40) and the module interface contract.
- Parts recognised by substring in the fact layer: TCA9535, INA3221, 24AA025E48, FUSB302, 74LVC1G08, SY6280, DSHP switches (fragments `bringup_facts.cpp.L49-68`, `.L94-174`, `.L175-194`, and the surviving `bringup_expander`, `ina3221_monitors`, `bringup_id_eeprom_addr`).
- Typed numbers: fixed I2C addresses `0x22` (FUSB302B) and `0x52` (clock chip) (:68, :72), SWD reservation `STM32_GPIO6` = PA13 and `STM32_GPIO5` = PA14 (:46), boot request pins `STM32_GPIO7` and `STM32_GPIO8` (:88-89, :103), bit-bang pins `STM32_DAC1`/`STM32_DAC2` at `J1.49` and `J1.55` (:110-113), rail override pins `STM32_GPIO1..3` (fragment `bringup_internal.hpp.L112-130`), interrupt `STM32_GPIO4` (:91, :126), input notes for expander ports `P11`, `P14`, `P15`.
- Typed in `removed/firmware_contract/source/firmware_docs_templates.hpp:7-68`: 62 lines of header text.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: the file is a document with a derived core and a typed shell; the derived core is the manifest's hardware map made complete (the manifest already carries `gpio_map`, `i2c_map` and `rails`), and the header was incomplete in a way a data-driven version would not be (it read monitors only from the sheet `power_mon`, so the third monitor on `motor_sense`, which the manifest lists, was missing from it).

What survived: (a) the controller pin extraction (`stm32_pin_map` over the live module netlist and the interface contract) moved into the manifest step, `manifest_stage` in `native/src/board_pipeline_documents.cpp`; (b) the I2C address collision check moved into the manifest step as `schgen::check_i2c_address_collisions` (`native/src/manufacturing_exports_manifest.cpp`, declared in `native/include/schgen/manufacturing_exports.hpp`), keeping the same address list and the same failing condition (the set of addresses is smaller than the list). It is covered by the new test `native/tests/i2c_collision_contracts.cpp`, which checks that both real boards pass, that two collisions built from the real carrier circuits are rejected, and that the manifest step reports them as a failed mandatory gate. (c) The power sequence test was split out to `native/tests/power_sequence_contracts.cpp` and still reads `native/tests/data/firmware_docs/<board>/inputs.json`, `power_sequence.svg` and `power_sequence_fail.svg` in place.

Temporary vocabulary: the three sheet names `bringup_rails`, `power_mon` and `usb_pd` added to `native/src/manufacturing_exports_manifest.cpp` for the collision check (vocabulary allow-list `subsystem` 1 to 4) are temporary and are to be removed by the I2C bus-map task (fact F1, output N8); the allow-list raise was accepted on that basis.

Known blind spot of the collision check, recorded and not fixed here: it reads the monitors only from the sheet named `power_mon`, so the third INA3221 on `motor_sense` (address `0x42`) is never compared; the manifest's `i2c_map` does list it. It also treats the bus `STM32_I2C2` and the isolated `AUX_I2C` as one address space. Task F-B (facts F1 and the bus map N8) is meant to replace it.

SWD pin drift check, archived and not kept: `removed/firmware_contract/source/firmware_docs.cpp:46-51` compared a hand-typed table (`STM32_GPIO6` = PA13 SWDIO, `STM32_GPIO5` = PA14 SWCLK) with the pins the live module netlist gives; it ran against the document's own typed claim ("dossier says"), and the only other uses of those claims were the notes in the removed header and manual. It guarded no circuit-against-circuit relation, so it left with the document. When the module facts F4 carry reserved pins as data, a real check can be written from them.

## 7. What could be generated

The pin and net map (controller pin, module net, connector pin, board net, sheets on the net) is already in the manifest as `gpio_map` and can be rendered by a generic emitter (outputs N1 and G3). Addresses and setpoints need F1 and F2. An optional C rendering of the hardware map, with no comments, is task G3.

## 8. Bringing it back

1. `git mv` every file in `source/` back to `native/src/` (`firmware_provenance.hpp` to `native/include/schgen/`), `tests/*.cpp` and `tests/*.md` to `native/tests/`, `tests/data/...` to `native/tests/data/...` (the path under `tests/` is the path under `native/tests/`), and `outputs/<board>/...` to `<board>/...`. Fragments go back by re-inserting the lines at the ranges in the table (the line numbers are at the source commit; locate by content).
2. Restore the build lines:

`native/CMakeLists.txt:40-41` at `f32ac35a`:

```
    src/bringup_facts.cpp src/firmware_docs.cpp src/firmware_docs_manual.cpp src/firmware_provenance.cpp
    src/firmware_docs_testplan.cpp src/firmware_docs_scfw.cpp src/firmware_docs_power_sequence.cpp
```

`native/CMakeLists.txt:1156-1164` at `f32ac35a`:

```
    add_executable(schgen_firmware_provenance_contracts tests/firmware_provenance_contracts.cpp)
    target_link_libraries(schgen_firmware_provenance_contracts PRIVATE schgen_core)
    target_compile_options(schgen_firmware_provenance_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_firmware_provenance_contracts COMMAND schgen_firmware_provenance_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(schgen_firmware_docs_contracts PRIVATE schgen_core)
    target_compile_options(schgen_firmware_docs_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_firmware_docs_contracts COMMAND schgen_firmware_docs_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/firmware-docs-contract-output")
```

`native/CMakeLists.txt:1393` at `f32ac35a`:

```
            spice firmware manual scfw testplan power-sequence subsystem-check carrier-check check floorplan compose)
```

3. Restore the pipeline steps `firmware`, `manual`, `scfw` and `testplan` (they ran between `xdc` and `power_sequence`):

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

and put the manifest back inside `document_stages`, reading `c.firmware->stm32`:

`native/src/board_pipeline_documents.cpp:50-55` at `f32ac35a`:

```
    c.attempt("manifest",[&]{if(!c.power||!c.testpoints||!c.firmware)throw ProjectError("power/coverage/live STM32 facts unavailable");
        ManufacturingManifestInput in;in.file_stem=c.paths.file_stem;in.sheets=c.circuits;in.power=*c.power;in.stm32=c.firmware->stm32;in.xdc=c.xdc;
        in.coverage={c.testpoints->covered(),c.testpoints->required.size(),c.testpoints->waived.size()};
        if(c.xdc)in.device=c.xdc->device;run_manufacturing_manifest(in,c.out,c.out/"manifest.json");
        c.manifest_input=std::move(in);
        c.gate("manifest",true,"artifacts hashed after SI; final reports rehashed at publication");});
```

Then remove the manifest step's own extraction. Restore the `Context` member `std::optional<FirmwareDocsInput> firmware;` (`native/src/board_pipeline_internal.hpp:39`) and the include of `schgen/spice.hpp` in `firmware_docs.hpp` that `Context` relied on.
4. Restore the gate bookkeeping:

`native/src/board_pipeline.cpp:80` at `f32ac35a`:

```
const std::vector<std::string> required={"inputs","authoring_purity","subsystem_structure","carrier_structure","sheet_gates","cc","symbol_law","link","board_schematic","constraints","diagram","bom_footprints","power_tree","rail_ampacity","testpoints","design_rules","part_rules","bom_values","footprint_pads","spice","pcb","pcb_drc","pcb_geometry","assembly","thermal","copper_debt","fab_profile","xdc","firmware","manual","testplan","gallery","scfw","power_sequence","floorplan","quantize_census","fallbacks","stage_movement","pipeline_doc","model3d","si","manifest","ledger","placement_requirements"};
```

`native/src/board_pipeline.cpp:93` at `f32ac35a`:

```
        if((g.mandatory||board_pipeline_gate_mandatory(g.name)) && g.status!=BoardGateStatus::passed && !(g.status==BoardGateStatus::skipped&&(g.name=="manual"||g.name=="scfw")))return false;}
```

`native/src/board_pipeline.cpp:44` at `f32ac35a`:

```
    for(const auto& d:{out,reports,docs,renders,manufacturing,out/"fpga",out/"firmware"})fs::create_directories(d);
```

and in `native/tests/board_pipeline_contracts.cpp` the loop that allows `manual` and `scfw` to be skipped, and `native/tests/placement_requirements_closure_contracts.cpp:11` (the removed names `firmware`, `manual`, `testplan`, `scfw`).
5. Restore the commands and help (quoted above for each output), and the manifest artifact names and scan:

`native/src/manufacturing_exports_manifest.cpp:50-51` at `f32ac35a`:

```
    for(const auto& rel:std::vector<std::string>{board_file_name(file_stem,BoardFileKind::Schematic),board_file_name(file_stem,BoardFileKind::Project),board_file_name(file_stem,BoardFileKind::Pcb),"manufacturing/SI_CONSTRAINTS.md","docs/BRINGUP.md","docs/FLOORPLAN.md","docs/DESIGN_SPEC.md","docs/COMPLIANCE.md"})add(root/rel);
    for(const auto& [dir,ext]:ProjectStrings{{"schematic",".kicad_sch"},{"fpga",".xdc"},{"firmware",".h"},{"manufacturing",".csv"},{"manufacturing",".txt"},{"manufacturing",".kicad_dru"},{"reports",".txt"},{"docs",".svg"}}){
```

6. Allow-list: the entries removed for the moved files in `native/tests/data/vocabulary_allowlist.json` (`firmware_docs.cpp` module 4 part 8 reference 4 subsystem 42; `firmware_docs_manual.cpp` module 2 part 3 reference 1 subsystem 18; `firmware_docs_scfw.cpp` part 12 subsystem 9; `firmware_docs_templates.hpp` module 7 part 19 subsystem 22; `firmware_docs_testplan.cpp` part 7 reference 3 subsystem 10; `firmware_provenance.cpp` subsystem 14; `bringup_internal.hpp` part 2 subsystem 6) and the purity scope entries in the fragment `authoring_purity_scope.cpp.L66-68`.
7. The two tests added by task R2 (`power_sequence_contracts`, `i2c_collision_contracts`) stay; the collision check should then be called from the restored `firmware` step as well, or the duplicate removed.
8. What changed since: the fact layer, the fixture `inputs.json` and the circuits are those of the source commit; the generated headers and plans reflect the circuits of that time.
