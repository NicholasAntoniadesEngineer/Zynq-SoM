# sc_firmware_scaffold origin

## 1. What it was and who used it

`firmware/sc/*` was a 14-file system-controller firmware scaffold (carrier only): two derived table files (`sc_tables.h`, `sc_tables.c`: rail order, enable nets, I2C devices, module gates, monitors) and twelve files of C code and a readme typed in the generator (a hardware abstraction, a rail sequencer, a watchdog, USB-PD and clock-chip drivers, an example application, a Zephyr port stub). The reader was the firmware engineer for the system controller. Nothing in the pipeline read it.

## 2. Files moved (29 whole files, 2 fragments)

| original path | archive path | git hash-object |
|---|---|---|
| `carrier/firmware/sc/README.md` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/README.md` | `8defd225d9f1bff8d17baca7badfa1e2c57d14ac` |
| `carrier/firmware/sc/sc_app.c` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_app.c` | `685fdc6470b80ddcb74263d5ca112c147f4849cf` |
| `carrier/firmware/sc/sc_hal.h` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_hal.h` | `62c621fe1c3be24561be1f5e903431abb04aed4c` |
| `carrier/firmware/sc/sc_hal_zephyr.c.txt` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_hal_zephyr.c.txt` | `22092c0c006a2f8122597ea77c94a3da924443fe` |
| `carrier/firmware/sc/sc_pd.c` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_pd.c` | `795b4a7adccbe6707b11dbf7b6d40f11e2eb6087` |
| `carrier/firmware/sc/sc_pd.h` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_pd.h` | `9d437edf13fadfc1794e89aa1cf03a31c5d340bb` |
| `carrier/firmware/sc/sc_rtc.c` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_rtc.c` | `170dfd091c020252fe43777b8795cff877f24b72` |
| `carrier/firmware/sc/sc_rtc.h` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_rtc.h` | `3059370c2e57248b26b45f97124cc9e5b292dacd` |
| `carrier/firmware/sc/sc_seq.c` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_seq.c` | `25f7ec1b09a7bea740654bceb33752d0ed5e508c` |
| `carrier/firmware/sc/sc_seq.h` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_seq.h` | `7a410cbbd1908a7dacda4883d8bcb14917e7649e` |
| `carrier/firmware/sc/sc_tables.c` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_tables.c` | `def8f9c291cd67bec85ebdc51aac9c9cc3524288` |
| `carrier/firmware/sc/sc_tables.h` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_tables.h` | `95f35227a537cfcc87c16735e95f946dd269d2c6` |
| `carrier/firmware/sc/sc_wdt.c` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_wdt.c` | `1b913c07cc3007f78df3014b7d2843e630baf15e` |
| `carrier/firmware/sc/sc_wdt.h` | `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_wdt.h` | `e7565a7874f7d2ab20d1c98b7ae9067ce213292c` |
| `native/src/firmware_docs_scfw.cpp` | `removed/sc_firmware_scaffold/source/firmware_docs_scfw.cpp` | `d830f004af401cab6fe7fe840542e3265f75e22b` |
| `native/tests/data/firmware_docs/carrier/sc/README.md` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/README.md` | `5d48a7f15003f0c7cb65fdbbd74830b6f2cf92ab` |
| `native/tests/data/firmware_docs/carrier/sc/sc_app.c` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_app.c` | `93164d40796485641279f68dc58beca350be9c39` |
| `native/tests/data/firmware_docs/carrier/sc/sc_hal.h` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_hal.h` | `645c271297696bb83d7a32937c0281990eacf69f` |
| `native/tests/data/firmware_docs/carrier/sc/sc_hal_zephyr.c.txt` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_hal_zephyr.c.txt` | `7e25feb0ca5803cefa91b5488b9a7d716fc1af3e` |
| `native/tests/data/firmware_docs/carrier/sc/sc_pd.c` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_pd.c` | `3a031df5474064d7a1d116298f04ba378247b468` |
| `native/tests/data/firmware_docs/carrier/sc/sc_pd.h` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_pd.h` | `f39071013e7e3e3f60c2f5227f23ee8c8457c770` |
| `native/tests/data/firmware_docs/carrier/sc/sc_rtc.c` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_rtc.c` | `48c91b1785f5fae3e7ce915df909636db423296a` |
| `native/tests/data/firmware_docs/carrier/sc/sc_rtc.h` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_rtc.h` | `a997d2a5958410c940171c401aeb2cddf9056623` |
| `native/tests/data/firmware_docs/carrier/sc/sc_seq.c` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_seq.c` | `f6aab3965ea32414f33815bcc7573577d6ad6a7e` |
| `native/tests/data/firmware_docs/carrier/sc/sc_seq.h` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_seq.h` | `56462138b91602c7721a3b5539959439a0cb145a` |
| `native/tests/data/firmware_docs/carrier/sc/sc_tables.c` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_tables.c` | `a302c249ee1264ea82e5568ac0f100f7cbab874e` |
| `native/tests/data/firmware_docs/carrier/sc/sc_tables.h` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_tables.h` | `7d6ea098c6a8728578ad175b33ce05ea8117b4b1` |
| `native/tests/data/firmware_docs/carrier/sc/sc_wdt.c` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_wdt.c` | `3828b32781c30b7ae52453d3e89ba2fa1035c2bc` |
| `native/tests/data/firmware_docs/carrier/sc/sc_wdt.h` | `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_wdt.h` | `ed8154e69372fbe16833d25b6a545a99b845262a` |
| `native/include/schgen/firmware_docs.hpp:28-28` | `removed/sc_firmware_scaffold/fragments/firmware_docs.hpp.L28-28.txt` | `a94807d8f225d9818c2bf71ce052b337ded54586` |
| `native/include/schgen/firmware_docs.hpp:40-41` | `removed/sc_firmware_scaffold/fragments/firmware_docs.hpp.L40-41.txt` | `090e20eb52965c9fe52f042b624acc76f36503c4` |

## 3. Source commit

`f32ac35a280d8cca496f4dbec4dde9f51c63600d` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers below are from that commit unless they name an archive path. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline step and gate `scfw` (skipped when the project lacks the sheets listed in item 5): `native/src/board_pipeline_documents.cpp:35-36`. Required name at `native/src/board_pipeline.cpp:80`; the skip was allowed at `native/src/board_pipeline.cpp:93`.
- Function `schgen::render_scfw` returning 14 documents, `removed/sc_firmware_scaffold/source/firmware_docs_scfw.cpp:25` onward; requirement check `scfw_missing_requirements` (fragment `firmware_docs.hpp.L28-28`); artifact type `FirmwareDocArtifact` (fragment `firmware_docs.hpp.L40-41`).
- Command `schgen scfw [--project NAME] [-o DIRECTORY]`: `native/src/project_cli.cpp:772-777` inside the combined block `native/src/project_cli.cpp:758-793`; help line `native/src/main.cpp:70`.
- Build: `native/CMakeLists.txt:41` (`src/firmware_docs_scfw.cpp`), `native/CMakeLists.txt:1393`.

## 5. What it read

- Sheets, required: `power`, `power_mon`, `bringup_en`, `bringup_modules`, `bringup_rails`, `usb_pd`, `board_services`, `bringup_en_modules` (`removed/sc_firmware_scaffold/source/firmware_docs_scfw.cpp:26-38`), through the fact layer (regulator chain, module gates, TCA9535 expander, INA3221 monitors, ID-EEPROM address).
- Typed: the settle time `.settle_ms = 5` (:67) and the file list with descriptions (:51-85).
- Typed in `removed/firmware_contract/source/firmware_docs_templates.hpp:286-1000`: 716 lines of C code and readme.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: twelve of the fourteen files are firmware logic, which is product firmware and not design data; the two derived table files are a C rendering of the hardware map that the manifest already carries.

## 7. What could be generated

The two table files are a C rendering of the hardware map (output G3: optional, from manifest sections `gpio_map`, `i2c_map` and the regulator rows). Needs F1, F2, F4. The scaffold itself belongs in the product's firmware repository.

## 8. Bringing it back

1. `git mv` `source/firmware_docs_scfw.cpp` to `native/src/`; `tests/data/firmware_docs/carrier/sc/*` to `native/tests/data/firmware_docs/carrier/sc/`; `outputs/carrier/firmware/sc/*` to `carrier/firmware/sc/`. The text it used is in `removed/firmware_contract/source/firmware_docs_templates.hpp` lines 286-1000.
2. Restore the pipeline step, command, help line and build entries below, and the shared items in `removed/firmware_contract/ORIGIN.md` section 8.

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

3. The generated C files include `zynq_carrier_contract.h`; restore the contract header output too.
Tasks R2 removed four outputs together, so the shared restore steps are in `removed/firmware_contract/ORIGIN.md` section 8 (fact layer fragments, `FirmwareDocsInput`, the pipeline `Context`, the manifest step and the build lists).
