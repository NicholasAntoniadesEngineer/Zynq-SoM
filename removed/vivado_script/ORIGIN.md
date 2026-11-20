# vivado_script origin

## 1. What it was and who used it

`fpga/create_project.tcl` was a one-shot Vivado batch script, 71 lines on the carrier: it creates a project for the device read from the SoM netlist, loads the generated pin constraints file, lists the clock-capable ports as commented `create_clock` templates, and ends with a commented Zynq processing-system stub. The reader was an FPGA engineer starting a Vivado project. No pipeline step read it: the pipeline only published it (`native/src/board_pipeline_documents.cpp:30-31`) and the manifest hashes `fpga/*.xdc`, not `*.tcl` (`native/src/manufacturing_exports_manifest.cpp:51`). The only reader in the tree was `native/tests/project_outputs_contracts.cpp:70-72`, which compared a fresh render with the committed file; those lines were removed with the file.

## 2. Files moved (6)

| original path | archive path | git hash-object |
|---|---|---|
| `carrier/fpga/create_project.tcl` | `removed/vivado_script/outputs/carrier/fpga/create_project.tcl` | `6f86de0f3b764d8c24f479c70a3a337316351041` |
| `devkit_mini/fpga/create_project.tcl` | `removed/vivado_script/outputs/devkit_mini/fpga/create_project.tcl` | `10ef73ed91fbd399461750b516d3c78e283992c3` |
| `native/src/vivado.cpp` | `removed/vivado_script/source/vivado.cpp` | `6bf64942715af5e280c172db39ca9ee48a440179` |
| `native/include/schgen/vivado.hpp` | `removed/vivado_script/source/vivado.hpp` | `e2c9a4b5965e220efd4fd5454b13748e1c4f5730` |
| `native/tests/vivado_contracts.cpp` | `removed/vivado_script/tests/vivado_contracts.cpp` | `26d442bb1f89808c33335aadd94950113da85cb8` |
| `native/tests/data/vivado_golden.tcl` | `removed/vivado_script/tests/vivado_golden.tcl` | `b91712ce59cecadea4a0ef711d59a65d25dd4343` |

## 3. Source commit

`9d2961a723a8b27af61bd49606abaea8f8ebaed4` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers below are from that commit. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Pipeline step and gate `vivado`, run after the `xdc` step: native/src/board_pipeline_documents.cpp:30-31; also listed in the required gate names, `native/src/board_pipeline.cpp:80`.
- Function `schgen::render_vivado`, `removed/vivado_script/source/vivado.cpp:29`.
- Commands `schgen vivado` and `schgen fpga` (XDC and Tcl from one live extraction): `native/src/project_cli.cpp:92`, `native/src/project_cli.cpp:970-989`; option `--xdc` accepted only for these two, `native/src/project_cli.cpp:366`; help lines `native/src/main.cpp:75-76`.
- Build files: `native/CMakeLists.txt:30` (`src/vivado.cpp`), `native/CMakeLists.txt:1341-1345` (test `native_vivado_contracts`), `native/CMakeLists.txt:1399` (the `vivado` and `fpga` help tests).

## 5. What it read

- The in-memory XDC result of the `xdc` step: for each port the net, connector pin, ball, pin name; plus the device string and the Zynq reference (`U2`), taken from the live kicad-cli extraction of the SoM schematic (native/src/board_pipeline_documents.cpp:20-26).
- The clock-capable list: pin names classified by `xdc_pin_traits` (MRCC/SRCC), `removed/vivado_script/source/vivado.cpp:43`. The clock-period map defaulted to empty and neither the pipeline nor the command ever passed one, so no clock was ever promoted to a real constraint.
- Typed in the generator: project name `zynq_carrier` (:66), the folder `carrier/fpga` in the header comment (:54), the Tcl atom character set (:13), the processing-system IP name and version `processing_system7:5.5` (:118), and about 25 lines of header and stub text (:50-127).

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: everything in the file that is derived (device, constraints file name, port count, clock-capable list) is already in the constraints file, where each clock candidate is also a comment line; the rest is fixed vendor-flow text typed in the generator.

## 7. What could be generated

Nothing beyond what the constraints file already holds (study `programmatic_outputs_study.md` section 2.2, verdict DROP). If wanted later it is ten lines in the product's FPGA repository. No facts needed.

## 8. Bringing it back

1. `git mv` `source/vivado.cpp` to `native/src/vivado.cpp`, `source/vivado.hpp` to `native/include/schgen/vivado.hpp`, `tests/vivado_contracts.cpp` to `native/tests/`, `tests/vivado_golden.tcl` to `native/tests/data/`, and `outputs/<board>/fpga/create_project.tcl` to `<board>/fpga/`.
2. Restore the build lines:

```
src/ratsnest.cpp src/footprint_library.cpp src/xdc.cpp src/vivado.cpp
add_executable(schgen_vivado_contracts tests/vivado_contracts.cpp)
target_link_libraries(schgen_vivado_contracts PRIVATE schgen_core)
target_compile_options(schgen_vivado_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME native_vivado_contracts COMMAND schgen_vivado_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/vivado_golden.tcl")
```

and `vivado fpga` in the help-test command list.
3. Restore the pipeline step:

`native/src/board_pipeline_documents.cpp:30-31` at `9d2961a7`:

```
    c.attempt("vivado",[&]{if(!xi||!xo)throw ProjectError("validated live XDC inputs unavailable");
        publish_text(c.out/"fpga/create_project.tcl",render_vivado(*xo,xi->device,xi->zynq_ref,xi->pins_file,xi->refs));c.gate("vivado",true,"project Tcl published");});
```

4. Restore the CLI as removed:

`native/src/project_cli.cpp:970-989` at `9d2961a7`:

```
    const auto fpga_dir = options.command == "fpga" && !options.output.empty()
                        ? options.output : paths.fpga_dir;
    const auto xdc_path = options.command == "xdc" && !options.output.empty() ? options.output
                        : !options.xdc.empty() ? options.xdc : fpga_dir / input.pins_file;
    const auto vivado_path = options.command == "vivado" && !options.output.empty() ? options.output
                           : fpga_dir / "create_project.tcl";
    std::string vivado;
    if (options.command != "xdc") {
        const auto relative = fs::weakly_canonical(xdc_path).lexically_relative(
            fs::weakly_canonical(vivado_path.parent_path()));
        vivado = render_vivado(xdc, input.device, input.zynq_ref,
                               relative.generic_string(), input.refs);
    }
    // Finish every validation/render before publishing any member of the batch.
    if (options.command != "vivado") publish_text(xdc_path, xdc.text);
    if (options.command != "xdc") publish_text(vivado_path, vivado);
    for (const auto& check : xdc.checks) std::cout << "  check: " << check << '\n';
    if (options.command != "vivado")
        std::cout << "XDC: " << xdc_path.string() << " (" << xdc.entries.size() << " pins)\n";
    if (options.command != "xdc") std::cout << "VIVADO: " << vivado_path.string() << "\n";
```

and the `--xdc` option (`native/src/project_cli.cpp:240`, `native/src/project_cli.cpp:254`, `native/src/project_cli.cpp:366`, the `xdc` member of the options struct at `native/src/project_cli.cpp:61`), the names `vivado` and `fpga` in the command set (`native/src/project_cli.cpp:92`), and the help lines (`native/src/main.cpp:75-76`).
5. Put `"vivado"` back in the required gate list (`native/src/board_pipeline.cpp:80`) and in `native/tests/placement_requirements_closure_contracts.cpp:11`, and restore the Vivado comparison in `native/tests/project_outputs_contracts.cpp:5,70-72`.
6. What changed since: nothing it depends on has changed in `xdc.hpp` (`XdcOutput`, `xdc_pin_traits`) at the time of the move.
