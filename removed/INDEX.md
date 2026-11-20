# removed/

Hand-written outputs that were taken out of the schgen tool. Nothing here is deleted: every file was moved with `git mv`, so `git log --follow <archive path>` shows its history.

The owner's ruling: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows".

Each subfolder has an `ORIGIN.md` that records, in order: what the output was and who used it; every file moved (original path, archive path, `git hash-object`); the source commit; what produced it; what it read; why it was removed; what part of it can be generated; what bringing it back would take. The template is `ORIGIN_TEMPLATE.md`.

Rules the tool relies on (enforced by `native_removed_archive_contracts`):

- `removed/board.json` must not exist: a direct child of the repository root holding `board.json` is read as a board folder.
- `removed/project.json` must not exist: a direct child of the repository root holding `project.json` is read as a fallback baseline.
- No `.py`, `.pyc` or `.pyo` file may be placed under `removed/`.
- Never archive under `subsystems/` or `<board>/subsystems/`.

## Subfolders

| folder | what it holds | source commit | move commit |
|---|---|---|---|
| `device_tree/` | firmware/carrier_pl.dtsi and its generator | `9d2961a723a8b27af61bd49606abaea8f8ebaed4` | `` |
| `vivado_script/` | fpga/create_project.tcl and its generator | `9d2961a723a8b27af61bd49606abaea8f8ebaed4` | `` |

## Files

Original path, then archive path.

### device_tree

- `carrier/firmware/carrier_pl.dtsi` -> `removed/device_tree/outputs/carrier/firmware/carrier_pl.dtsi`
- `devkit_mini/firmware/carrier_pl.dtsi` -> `removed/device_tree/outputs/devkit_mini/firmware/carrier_pl.dtsi`
- `native/src/devicetree.cpp` -> `removed/device_tree/source/devicetree.cpp`
- `native/include/schgen/devicetree.hpp` -> `removed/device_tree/source/devicetree.hpp`
- `native/tests/data/devicetree_carrier_golden.dtsi` -> `removed/device_tree/tests/devicetree_carrier_golden.dtsi`
- `native/tests/data/devicetree_cases.json` -> `removed/device_tree/tests/devicetree_cases.json`
- `native/tests/devicetree_contracts.cpp` -> `removed/device_tree/tests/devicetree_contracts.cpp`
- `native/tests/data/devicetree_devkit_mini_golden.dtsi` -> `removed/device_tree/tests/devicetree_devkit_mini_golden.dtsi`

### vivado_script

- `carrier/fpga/create_project.tcl` -> `removed/vivado_script/outputs/carrier/fpga/create_project.tcl`
- `devkit_mini/fpga/create_project.tcl` -> `removed/vivado_script/outputs/devkit_mini/fpga/create_project.tcl`
- `native/src/vivado.cpp` -> `removed/vivado_script/source/vivado.cpp`
- `native/include/schgen/vivado.hpp` -> `removed/vivado_script/source/vivado.hpp`
- `native/tests/vivado_contracts.cpp` -> `removed/vivado_script/tests/vivado_contracts.cpp`
- `native/tests/data/vivado_golden.tcl` -> `removed/vivado_script/tests/vivado_golden.tcl`
