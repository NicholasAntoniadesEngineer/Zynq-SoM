# test_plan origin

## 1. What it was and who used it

`docs/TEST_PLAN.md` was an acceptance test plan: 131 lines on the carrier and 93 on devkit_mini. About 60 percent was derived rows (each electrical check of the SPICE gate with net, probe pad, expected value and limits; an I2C scan table; a load switch table) and about 40 percent typed text. The reader was a test technician. It read the results of the SPICE and test point gates (`removed/test_plan/source/firmware_docs_testplan.cpp`). The devkit copy told the reader to see `carrier/docs/BRINGUP.md`, a file devkit does not have.

## 2. Files moved (5 whole files, 1 fragments)

| original path | archive path | git hash-object |
|---|---|---|
| `carrier/docs/TEST_PLAN.md` | `removed/test_plan/outputs/carrier/docs/TEST_PLAN.md` | `4a714451a2d9019840ba80e83469a59549fe30ee` |
| `devkit_mini/docs/TEST_PLAN.md` | `removed/test_plan/outputs/devkit_mini/docs/TEST_PLAN.md` | `99f1adb17083c603b48532e249dd08269a9455ed` |
| `native/src/firmware_docs_testplan.cpp` | `removed/test_plan/source/firmware_docs_testplan.cpp` | `35453d11cab9b3bce1a652718c7df0c8d3f01a6b` |
| `native/tests/data/firmware_docs/carrier/TEST_PLAN.md` | `removed/test_plan/tests/data/firmware_docs/carrier/TEST_PLAN.md` | `93593d87558ed9813485368691db7d06acd89f6f` |
| `native/tests/data/firmware_docs/devkit_mini/TEST_PLAN.md` | `removed/test_plan/tests/data/firmware_docs/devkit_mini/TEST_PLAN.md` | `fbe2720b09771d661af2d445eef774f7dfde42c1` |
| `native/include/schgen/firmware_docs.hpp:32-39` | `removed/test_plan/fragments/firmware_docs.hpp.L32-39.txt` | `2100a009434030a90010471fde6976d5957bd876` |

## 3. Source commit

`f32ac35a280d8cca496f4dbec4dde9f51c63600d` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers below are from that commit unless they name an archive path. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline step and gate `testplan`: `native/src/board_pipeline_documents.cpp:37-38`, after the SPICE and test point results exist. Required name at `native/src/board_pipeline.cpp:80`.
- Function `schgen::render_test_plan` (:54) and the scan helper `schgen::testplan_i2c_devices`, both in `removed/test_plan/source/firmware_docs_testplan.cpp`; declarations were `firmware_docs.hpp:32-39` (`fragments/`).
- Command `schgen testplan`: `native/src/project_cli.cpp:758-793`; help line `native/src/main.cpp:69`.
- Build: `native/CMakeLists.txt:41` (`src/firmware_docs_testplan.cpp`), `native/CMakeLists.txt:1393`.

## 5. What it read

- The SPICE result (checks: name, sheet, kind, value, unit, lo, hi) and the test point coverage (net to probe locations), passed in by the pipeline.
- Sheets by name: `power_mon` (INA3221 monitors, line 48), `usb_pd` (FUSB302B at fixed `0x22`, line 49), `board_services` (ID-EEPROM address from straps and fixed `0x52` for the clock chip, line 50), `power`, `bringup_modules` (lines 56-60, 95).
- Typed: the stage map `{"+3V3_SC",1},{"+VIN",1},...,{"+3V3_AUX",6}` (lines 55-61), the module hints `HDMI_TX`, `HDMI_RX`, `LCD`, ... (line 96), the divider and RC check name prefixes (line 21), the `BOOT0_SET` name (line 30).
- Typed in `removed/firmware_contract/source/firmware_docs_templates.hpp:233-285`: 53 lines of text.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: the stage map, stage titles and module hints were typed, and the derived rows depend on thresholds typed in the SPICE gate (`native/src/spice.cpp`).

## 7. What could be generated

The checks, probe pads and limits become steps of the generated bring-up checklist (output N2, task G2): each electrical check is placed in the step of the rail it measures. Needs F1 for the scan steps, F2 and F3 for expected voltages, and F5 if the thresholds are to become data.

## 8. Bringing it back

1. `git mv` `source/firmware_docs_testplan.cpp` to `native/src/`; `tests/data/firmware_docs/<board>/TEST_PLAN.md` to `native/tests/data/firmware_docs/<board>/`; `outputs/<board>/docs/TEST_PLAN.md` to `<board>/docs/`. The text it used is in `removed/firmware_contract/source/firmware_docs_templates.hpp` lines 233-285.
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

3. `testplan_i2c_devices` was also used by `native/tests/downstream_i2c_contracts.cpp` (see the fragment `removed/firmware_contract/fragments/downstream_i2c_contracts.cpp.L1-203.txt`).
Tasks R2 removed four outputs together, so the shared restore steps are in `removed/firmware_contract/ORIGIN.md` section 8 (fact layer fragments, `FirmwareDocsInput`, the pipeline `Context`, the manifest step and the build lists).
