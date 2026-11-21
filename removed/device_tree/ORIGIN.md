# device_tree origin

## 1. What it was and who used it

`firmware/carrier_pl.dtsi` was a Linux device-tree fragment, 76 lines on the carrier: two derived tables (the processor MIO pin table with 7 rows and the SD bus table with 7 rows) and, around them, typed comment templates for the UART and SD host nodes. The reader was a firmware engineer writing the processor's device tree. No pipeline step read it; the pipeline only published it (`native/src/board_pipeline_documents.cpp:32`).

## 2. Files moved (8)

| original path | archive path | git hash-object |
|---|---|---|
| `carrier/firmware/carrier_pl.dtsi` | `removed/device_tree/outputs/carrier/firmware/carrier_pl.dtsi` | `76515313dd2db2a95d2cd95932c6757f94003343` |
| `devkit_mini/firmware/carrier_pl.dtsi` | `removed/device_tree/outputs/devkit_mini/firmware/carrier_pl.dtsi` | `4159cb471c1180a473421455185af23e8a32ce5c` |
| `native/src/devicetree.cpp` | `removed/device_tree/source/devicetree.cpp` | `dbb597c3aa8c768e108c4cd06441b7673a9fbb2c` |
| `native/include/schgen/devicetree.hpp` | `removed/device_tree/source/devicetree.hpp` | `e19106be1dc3b8eee7cf291843636edfeff8747c` |
| `native/tests/data/devicetree_carrier_golden.dtsi` | `removed/device_tree/tests/devicetree_carrier_golden.dtsi` | `9f3e19c3f8c9cc5ef339dc991ec1e2390dde9b10` |
| `native/tests/data/devicetree_cases.json` | `removed/device_tree/tests/devicetree_cases.json` | `fc17e12113337bc21973aad2e02e1bd04a18671d` |
| `native/tests/devicetree_contracts.cpp` | `removed/device_tree/tests/devicetree_contracts.cpp` | `5127442ea9a0804c37a3bae608981fcd900a581e` |
| `native/tests/data/devicetree_devkit_mini_golden.dtsi` | `removed/device_tree/tests/devicetree_devkit_mini_golden.dtsi` | `9f3e19c3f8c9cc5ef339dc991ec1e2390dde9b10` |

## 3. Source commit

`9d2961a723a8b27af61bd49606abaea8f8ebaed4` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers below are from that commit. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline step and gate `devicetree`, run after the `vivado` step: `native/src/board_pipeline_documents.cpp:32`; listed in the required gate names, `native/src/board_pipeline.cpp:80`.
- Functions `schgen::load_devicetree_input` and `schgen::generate_devicetree`, `removed/device_tree/source/devicetree.cpp:239` (`load_devicetree_input`), `:265` (`generate_devicetree`) and `:155` (the text renderer).
- Command `schgen devicetree [--project NAME] [--som FILE] [--contract FILE] [-o FILE]`: `native/src/project_cli.cpp:92`, `native/src/project_cli.cpp:653-665`; help line `native/src/main.cpp:79`.
- Build files: `native/CMakeLists.txt:32` (`src/devicetree.cpp`), `native/CMakeLists.txt:1317-1321` (test `native_devicetree_contracts`), `native/CMakeLists.txt:1399` (the `devicetree` help test).

## 5. What it read

- `<board>/som_mapping.json` keys `function_map` and `pudc_straps` (`removed/device_tree/source/devicetree.cpp:243-257`), the selected module interface contract, and the live extraction of the SoM schematic (pin names starting `IO_` mark programmable-logic nets, :273).
- Typed in the generator: the MIO net prefix `ZYNQ_PS_MIO` (:101), the UART0 nets `ZYNQ_PS_UART0_RXD` and `ZYNQ_PS_UART0_TXD` (:194), the SD bus nets `SDIO_CLK`, `SDIO_CMD`, `SDIO_D0`..`SDIO_D3` with their roles (:304-305), the connector references `J1`, `J2`, `J3` (header default), and the comment templates for the UART and SD nodes (:155-237). The comment text names an "FT232 USB-UART bridge" while `subsystems/uart_bridge` uses a CP2102N, so the typed text was already wrong.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: both node bodies are comments; the only derived content is two pin tables. A truthful generic emitter would produce nothing else, because the devices with known addresses sit on the system controller's bus, not on a bus the Linux processor owns, and the buses the processor can reach go through programmable-logic pins whose controller node depends on gateware the tool does not know.

## 7. What could be generated

The two pin tables, as rows of a module pin map (study `programmatic_outputs_study.md` section 3, output N1, and section 2.5, verdict SPLIT). Facts needed: module references (F4). The `.dtsi` file and node templates are not design data.

## 8. Bringing it back

1. `git mv` `source/devicetree.cpp` to `native/src/devicetree.cpp`, `source/devicetree.hpp` to `native/include/schgen/devicetree.hpp`, `tests/devicetree_contracts.cpp` to `native/tests/`, the two `tests/devicetree_*_golden.dtsi` and `tests/devicetree_cases.json` to `native/tests/data/`, and `outputs/<board>/firmware/carrier_pl.dtsi` to `<board>/firmware/`.
2. Restore the build lines:

```
src/link.cpp src/devicetree.cpp src/symbols.cpp src/validation.cpp
add_executable(schgen_devicetree_contracts tests/devicetree_contracts.cpp)
target_link_libraries(schgen_devicetree_contracts PRIVATE schgen_core)
target_compile_options(schgen_devicetree_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME native_devicetree_contracts COMMAND schgen_devicetree_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/data" "${CMAKE_CURRENT_SOURCE_DIR}/..")
```

and `devicetree` in the help-test command list.
3. Restore the pipeline step:

`native/src/board_pipeline_documents.cpp:32` at `9d2961a7`:

```
    c.attempt("devicetree",[&]{if(!live)throw ProjectError("live SoM extraction unavailable");const auto r=generate_devicetree(load_devicetree_input(c.paths.repository_root,c.paths.project_root,*live,board_file_name(c.paths.file_stem,BoardFileKind::PinConstraints),c.paths.som_interface_file));publish_text(c.out/"firmware/carrier_pl.dtsi",r.text);c.gate("devicetree",true,"device tree published");});
```

4. Restore the CLI command as removed:

`native/src/project_cli.cpp:653-665` at `9d2961a7`:

```
    if (options.command == "devicetree") {
        if (!options.subsystems.empty()) throw std::runtime_error("devicetree takes no subsystem names");
        const auto jrefs = refs(options.refs);
        const auto live = extract_som_zynq(som, "U2", jrefs, {options.kicad_cli});
        const auto input = load_devicetree_input(paths.repository_root, paths.project_root,
                                                live, board_file_name(paths.file_stem, BoardFileKind::PinConstraints), options.contract, jrefs);
        const auto result = generate_devicetree(input);
        const auto output = options.output.empty() ? paths.project_root / "firmware/carrier_pl.dtsi"
                                                   : options.output;
        publish_text(output, result.text);
        std::cout << "DEVICETREE: " << output.string() << " (" << result.mio_rows.size() << " MIO rows)\n";
        return 0;
    }
```

and the name `devicetree` in the command set (`native/src/project_cli.cpp:92`), the help line (`native/src/main.cpp:79`).
5. Put `"devicetree"` back in the required gate list (`native/src/board_pipeline.cpp:80`) and `native/tests/placement_requirements_closure_contracts.cpp:11`.
6. What changed since: the generator uses `link_mapping_from_json` and `BoardDefinition` loaders of the time of the move; re-check them against the current `native/include/schgen/link.hpp` and `board_definition.hpp`.
